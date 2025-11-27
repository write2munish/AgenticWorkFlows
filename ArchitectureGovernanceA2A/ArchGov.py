import json
import os
import asyncio
import warnings

# Third-party imports
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Union, Optional

# Google GenAI and ADK imports
from google.genai import types
import google.generativeai as genai
from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService

# --- Configuration ---
warnings.filterwarnings("ignore")

# Configure Google GenAI client
# (Ideally set this in your environment variables for security)
os.environ["GOOGLE_API_KEY"] = "XX"
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=7,
    initial_delay=1,
    http_status_codes=[429, 500, 503, 504],
)

# --- Data Models & CMDB Data ---

class DeploymentEnv:
    PROD = "prod"
    UAT = "uat"
    SANDBOX = "sandbox"
    QA = "qa"

class Compliance:
    PCI = "PCI"
    GDPR = "GDPR"
    SOC2 = "SOC2"

# We define the Pydantic model for the output to ensure structure
class ComplianceResult(BaseModel):
    applicationId: int
    appName: str
    isCompliant: bool
    reason: Optional[str] = None

cmdb_data = [
    { "id": 1, "name": "Customer Payments Gateway", "owner": "Finance Team", "technology": "Java/Spring", "deployment": DeploymentEnv.PROD, "compliance": [Compliance.PCI, Compliance.SOC2], "users": 150000 },
    { "id": 2, "name": "User Data Analytics", "owner": "Marketing Team", "technology": "Python/Flask", "deployment": DeploymentEnv.UAT, "compliance": [Compliance.GDPR], "users": 25000 },
    { "id": 3, "name": "PCI Feature Dev", "owner": "Payments Dev Team", "technology": "Java/Spring", "deployment": DeploymentEnv.SANDBOX, "compliance": [Compliance.PCI], "users": 15 },
    { "id": 4, "name": "Internal HR Portal", "owner": "HR Team", "technology": "Node.js/React", "deployment": DeploymentEnv.PROD, "compliance": [Compliance.SOC2], "users": 800 },
    { "id": 5, "name": "SOC2 Staging Env", "owner": "Core Platform", "technology": "Go", "deployment": DeploymentEnv.SANDBOX, "compliance": [Compliance.SOC2], "users": 50 },
]

# --- Tools ---

def get_cmdb_data(applicationName: str = "") -> str:
    """
    Retrieves application details from a mock CMDB.
    Pass 'all', 'list', or empty string to get all applications.
    """
    applicationName_lower = applicationName.lower().strip()
    
    # 1. Return ALL data if requested
    if applicationName_lower in ["all", "list", "everything", ""]:
        return json.dumps(cmdb_data, indent=2, default=str)
    
    # 2. Search for specific application
    for app in cmdb_data:
        if app["name"].lower() == applicationName_lower:
            return json.dumps(app, indent=2, default=str)
    
    # 3. Handle Not Found
    available = ", ".join(app["name"] for app in cmdb_data)
    return f"Sorry, I don't have information for '{applicationName}'. Available applications: {available}"

# --- Agents ---

# 1. The Standard CMDB Lookup Agent
cmdb_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
    name="cmdb_agent",
    description="Helpful agent for looking up application details.",
    instruction="""
    You are a CMDB agent. Use get_cmdb_data to answer questions about applications.
    If the user asks for everything, fetch all data.
    """,
    tools=[get_cmdb_data],
)

# 2. The Compliance Validator Agent (The Logic you requested)
compliance_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config), # Using 1.5-flash for strong reasoning
    name="compliance_validator",
    description="Analyzes applications for security compliance violations.",
    instruction="""
    You are a Compliance Validator Agent.
    
    Your goal is to:
    1. Fetch the list of applications using the get_cmdb_data tool (ask for 'all').
    2. Analyze each application against the following Rules:
    
       - NON-COMPLIANT if: Subject to 'PCI' compliance but deployed in a 'sandbox' or 'qa' environment.
       - NON-COMPLIANT if: Subject to 'GDPR' compliance but has more than 10,000 users in a 'uat' environment.
       - NON-COMPLIANT if: Subject to 'SOC2' compliance but deployed in a 'sandbox' environment.
    
    3. Return a JSON array of objects. Do not wrap in markdown blocks. Just the raw JSON.
       Each object must have:
       - 'applicationId': (number, mapped from 'id')
       - 'appName': (string, mapped from 'name')
       - 'isCompliant': (boolean)
       - 'reason': (string if non-compliant, explain specifically which rule failed. null if compliant)
    """,
    tools=[get_cmdb_data], 
)

riskassessment_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config), # Using 1.5-flash for strong reasoning
    name="riskassessment",
    description="Analyzes applications for security compliance violations.",
    instruction="""""
        As a Risk Assessment Agent, analyze the following non-compliant applications.
        For each application, identify a primary business or security risk associated with its non-compliance and assign a severity level ('Low', 'Medium', 'High', 'Critical').

        Non-compliant applications:
        ${JSON.stringify(nonCompliantApps, null, 2)}

        Return a JSON array of objects. Each object should contain 'applicationId', 'appName', 'risk' description, and 'severity'.
    """,    
)

recommendation_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config), # Using 1.5-flash for strong reasoning
    name="recommendation",
    description="Analyzes applications and provide recommendations for security compliance violations.",
    instruction="""""
        As a Recommendation Agent, your task is to create a well-defined, actionable recommendation for each identified risk. 
        Each recommendation must be a specific, single-step action item that can be assigned to a team to mitigate the risk. 
        Start each recommendation with an action verb (e.g., "Migrate", "Remove", "Update", "Disable"). 
        For example, instead of "Improve security", a good recommendation would be "Migrate the 'PCI Feature Dev' application from the non-compliant 'sandbox' to a secure, PCI-certified development environment."
        Also, assign a priority for implementing the recommendation ('Low', 'Medium', 'High').

        Identified risks:
        ${JSON.stringify(risks, null, 2)}

        Return a JSON array of objects. Each object should contain the original 'risk', a 'recommendation', and a 'priority'.    
    """,    
)

reporting_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config), # Using 1.5-flash for strong reasoning
    name="reporting",
    description="Provides reporting for security compliance violations.",
    instruction="""""
        As a Reporting Agent, create a concise daily compliance report based on the following data.
        The report should contain a brief 'summary' of the overall compliance status and a list of key 'actionItems'. 
        Action items should be created for all recommendations with a 'High' and 'Medium' priority. 
        Additionally, ensure an action item is created for any risk related to SOC2 or PCI compliance in non-production environments, as these are critical regulatory concerns.

        Compliance check results: ${JSON.stringify(complianceResults.filter(r => !r.isCompliant))}
        Identified risks: ${JSON.stringify(risks)}
        Mitigation recommendations: ${JSON.stringify(recommendations)}

        Return a single JSON object with 'summary' (string) and 'actionItems' (array of strings).
    """,    
)

evaluation_agent = LlmAgent(
    model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config), # Using 1.5-flash for strong reasoning
    name="evaluation",
    description="Evaluates the effectiveness of recommendations for security compliance violations.",
    instruction="""""
        As an Evaluation Agent, assess the quality and completeness of the generated compliance report based on the workflow's output.
        - Did the report correctly summarize the situation?
        - Did the report identify the most critical action items based on the identified risks?
        - Were all high-priority risks addressed in the action items?

        Based on your assessment, provide a quantitative 'score' from 1 to 100 and brief 'feedback' explaining your reasoning.
        
        Workflow Output to Evaluate:
        Report: ${JSON.stringify(report)}
        Risks: ${JSON.stringify(risks)}

        Return a single JSON object with 'score' (number) and 'feedback' (string).
    """,    
)

print("✅ Agents created successfully.")

# --- Runners ---

session_service = InMemorySessionService()
APP_NAME = "adk_demo"

root_agent = SequentialAgent(
    name="ArchGovernancePipeline",
    sub_agents=[compliance_agent,riskassessment_agent,recommendation_agent,reporting_agent,evaluation_agent],
)

print("✅ Sequential Agent created.")

runner = InMemoryRunner(agent=root_agent)

def extract_json_from_events(events):
    """
    Extracts and parses JSON text from the last event's content part.
    """
    # If response is a single event, wrap in list
    if not isinstance(events, list):
        events = [events]
    for event in reversed(events):
        if hasattr(event, "content") and hasattr(event.content, "parts"):
            for part in event.content.parts:
                if hasattr(part, "text") and part.text.strip().startswith("["):
                    try:
                        return json.loads(part.text)
                    except Exception as e:
                        print("Error parsing JSON:", e)
                        print("Raw text:", part.text)
                        return None
    return None

# --- Main Execution ---
async def main():

    response = await runner.run_debug(
        "Run the compliance validation on all applications and return the JSON report"
    )
    #print(response)
    # Only print the parsed JSON result
    result = extract_json_from_events(response)
    print(json.dumps(result, indent=2))

    await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())

    print("\n✅ Completed execution.")