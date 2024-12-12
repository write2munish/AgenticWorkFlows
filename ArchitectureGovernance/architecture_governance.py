import os
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI  
from langchain.tools import tool
import json
import plotly.graph_objects as go
import pandas as pd
import io
import ollama
import asyncio
from typing import Any, Dict


# Set the environment variable to tell Langchain to use Ollama
os.environ["OPENAI_API_BASE"] = "http://localhost:11434/v1"
os.environ["OPENAI_API_KEY"] = "ollama"  # dummy key

# ---- Custom Tools ----
# Mock CMDB Data (Replace with your actual API calls or DB connections)
@tool("get_cmdb_data")
def get_cmdb_data():
    """Retrieves application details from a mock CMDB."""
    # In a real scenario, this would involve connecting to a CMDB API or database
    cmdb_data = [
        {"application": "App1", "owner": "Team A", "deployment_env": "prod", "compliance": ["PCI","SOC2"]},
        {"application": "App2", "owner": "Team B", "deployment_env": "dev", "compliance": []},
        {"application": "App3", "owner": "Team A", "deployment_env": "prod", "compliance": ["SOC2"]},
        {"application": "App4", "owner": "Team C", "deployment_env": "staging", "compliance": ["GDPR","PCI","SOC2"]}
    ]

    return json.dumps(cmdb_data)


@tool("get_policy_doc")
def get_policy_doc():
    """Retrieves policy document."""
    return """
        PCI Compliance requires all applications to have the following:
            - Encrypted data in transit and at rest.
            - Regular Vulnerability scanning.
        SOC2 requires all applications to have the following:
            - Regular Risk Management assessment.
        GDPR requires all applications to have the following:
            - Data Privacy Controls.
    """


def create_visualizations(report_data: str) -> Dict[str, Any]:
    """
    Creates visualizations based on the given report data.

    Args:
        report_data (str): The report data (including JSON output).

    Returns:
       dict : Dictionary containing the risk heatmap and compliance bar chart as HTML, or error message
    """
    try:
        # Load the data from the generated report
        report_lines = report_data.split('\n')
        # Find the JSON data
        json_data = ""
        for line in report_lines:
            if line.startswith('```json'):
                json_data = line[len('```json'):].strip()
                for i in range(report_lines.index(line) + 1, len(report_lines)):
                    if report_lines[i].startswith("```"):
                        break
                    json_data += report_lines[i]
                break

        if json_data:
            data = json.loads(json_data)
            df = pd.DataFrame(data)

            # Create Risk Heatmap
            risk_fig = go.Figure(data=go.Heatmap(
                z=[[1, 2, 3], [4, 5, 6], [7, 8, 9]],  # Example risk levels, replace with real risk assessment
                x=["App1", "App2", "App3"],  # Example applications, replace with real applications
                y=["Security", "Compliance", "Operational"],  # Example risk categories, replace with real risk categories
                colorscale='Reds'
            ))
            risk_plot = risk_fig.to_html(full_html=False)

            # Create Compliance Bar Chart
            compliance_df = df.explode('compliance')
            compliance_counts = compliance_df['compliance'].value_counts()

            compliance_fig = go.Figure(data=[go.Bar(x=compliance_counts.index, y=compliance_counts.values)])
            compliance_plot = compliance_fig.to_html(full_html=False)

            return {
                "risk_plot": risk_plot,
                "compliance_plot": compliance_plot
            }

    except Exception as e:
        return {"error": f"Error creating visualization: {str(e)}"}


if __name__ == "__main__":
    # Using an Ollama model
    ollama_model = "ollama/llama3:latest"

    # Create a ChatOpenAI instance for Ollama (you can use any openai compatible LLM)
    llm_langchain = ChatOpenAI(
        base_url=os.environ["OPENAI_API_BASE"],
        api_key=os.environ["OPENAI_API_KEY"],
        model=ollama_model,
        temperature=0  
    )

    # ---- Agent Definitions ----

    # Architecture Data Aggregator
    data_aggregator_agent = Agent(
        role="Architecture Data Aggregator",
        goal="Gather architectural data from various sources and prepare it for analysis.",
        backstory="Expert in data extraction and preparation from various sources.",
        verbose=True,
        allow_delegation=True,
        tools=[get_cmdb_data],
        llm=llm_langchain  
    )

    # Compliance and Policy Validator
    compliance_validator_agent = Agent(
        role="Compliance and Policy Validator",
        goal="Evaluate architectural data against defined compliance policies and generate detailed compliance reports.",
        backstory="Expert in architecture policies and compliance frameworks like PCI, SOC2, and GDPR.",
        verbose=True,
        allow_delegation=True,
        tools=[get_policy_doc],
        llm=llm_langchain  
    )

    # Risk and Impact Assessor
    risk_assessor_agent = Agent(
        role="Risk and Impact Assessor",
        goal="Identify potential risks and impacts based on architecture data and deviations from standards.",
        backstory="Expert in risk analysis and dependency management in IT architectures.",
        verbose=True,
        allow_delegation=True,
        llm=llm_langchain  
    )

    # Remediation and Recommendation Agent
    recommendation_agent = Agent(
        role="Remediation and Recommendation Agent",
        goal="Generate recommendations for remediating identified compliance and risk issues.",
        backstory="Expert in best practices, solution catalogs, and remediation strategies.",
        verbose=True,
        allow_delegation=True,
        llm=llm_langchain  
    )
    # Reporting and Visualization Agent
    report_agent = Agent(
        role="Reporting and Visualization Agent",
        goal="Consolidate information from the analysis and generate comprehensive reports and visualizations.",
        backstory="Expert in creating executive summaries, detailed compliance reports, and risk heatmaps.",
        verbose=True,
        allow_delegation=True,
        llm=llm_langchain  
    )

    # ---- Tasks ----

    # Architecture Data Aggregation Task
    data_aggregation_task = Task(
        description="Retrieve architectural data from the CMDB. Ensure all required attributes for each application are captured. Output the data in structured JSON format.",
        agent=data_aggregator_agent,
        expected_output="JSON"
    )

    # Compliance Analysis Task
    compliance_task = Task(
        description="Analyze the extracted architecture data and identify any compliance violations against the defined policies. Generate a detailed report with justification for non-compliant applications.",
        agent=compliance_validator_agent,
        expected_output="Detailed report of compliance violations"
    )

    # Risk assessment task
    risk_assessment_task = Task(
        description="Given the compliance issues identified, assess the risk of each of the identified application with violations. Assess any dependencies which could create cascading failures based on identified violations.",
        agent=risk_assessor_agent,
        expected_output="Risk assessment report"
    )

    # Remediation Recommendation task
    remediation_recommendation_task = Task(
        description="Based on the compliance and risk reports, generate specific actionable recommendations for each identified issue.",
        agent=recommendation_agent,
        expected_output="Recommendations for remediation"
    )

    # Report generation task
    report_generation_task = Task(
        description="Consolidate the findings from the previous tasks into an executive summary report. Include compliance violations, risk assessments, and actionable recommendations with visualization of risk and compliance.",
        agent=report_agent,
        expected_output="Executive summary report with visualizations"
    )

    # ---- Crew ----
    crew = Crew(
        agents=[
            data_aggregator_agent,
            compliance_validator_agent,
            risk_assessor_agent,
            recommendation_agent,
            report_agent
        ],
        tasks=[
            data_aggregation_task,
            compliance_task,
            risk_assessment_task,
            remediation_recommendation_task,
            report_generation_task
        ],
        verbose=False
    )

    # Run the Crew
    result = crew.kickoff()
    print("\n\n----- Final Report -----")
    print(result)

    # Generate the visualizations
    visualizations = create_visualizations(result)

    print("\n\n----- Visualizations -----")
    print(visualizations)