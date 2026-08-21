import os
import yaml

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional, List

from crewai import Agent, Task, Crew, Flow, LLM
from crewai.flow.flow import listen, start

from crewai_tools import ScrapeWebsiteTool, TavilySearchTool

load_dotenv()


# ============================================================
# LLM
# ============================================================

llm = LLM(
    model="openai/gpt-5.6-luna"
)


# ============================================================
# LOAD YAML CONFIGURATION
# ============================================================

files = {
    "lead_agents": "config/lead_qualification_agents.yaml",
    "lead_tasks": "config/lead_qualification_tasks.yaml",
    "email_agents": "config/email_engagement_agents.yaml",
    "email_tasks": "config/email_engagement_tasks.yaml",
}

configs = {}

for config_type, file_path in files.items():
    with open(file_path, "r", encoding="utf-8") as file:
        configs[config_type] = yaml.safe_load(file)

lead_agents_config = configs["lead_agents"]
lead_tasks_config = configs["lead_tasks"]
email_agents_config = configs["email_agents"]
email_tasks_config = configs["email_tasks"]


# ============================================================
# PYDANTIC OUTPUT MODELS
# ============================================================

class LeadPersonalInfo(BaseModel):
    name: str = Field(..., description="The full name of the lead.")
    job_title: str = Field(..., description="The job title of the lead.")
    role_relevance: int = Field(..., ge=0, le=10, description="A score representing how relevant the lead's role is to the decision-making process (0-10).")
    professional_background: Optional[str] = Field(..., description="A brief description of the lead's professional background.")

class CompanyInfo(BaseModel):
    company_name: str = Field(..., description="The name of the company the lead works for.")
    industry: str = Field(..., description="The industry in which the company operates.")
    company_size: int = Field(..., description="The size of the company in terms of employee count.")
    revenue: Optional[float] = Field(None, description="The annual revenue of the company, if available.")
    market_presence: int = Field(..., ge=0, le=10, description="A score representing the company's market presence (0-10).")

class LeadScore(BaseModel):
    score: int = Field(..., ge=0, le=100, description="The final score assigned to the lead (0-100).")
    scoring_criteria: List[str] = Field(..., description="The criteria used to determine the lead's score.")
    validation_notes: Optional[str] = Field(None, description="Any notes regarding the validation of the lead score.")

class LeadScoringResult(BaseModel):
    personal_info: LeadPersonalInfo = Field(..., description="Personal information about the lead.")
    company_info: CompanyInfo = Field(..., description="Information about the lead's company.")
    lead_score: LeadScore = Field(..., description="The calculated score and related information for the lead.")


# ============================================================
# TOOLS
# ============================================================

search_tool = TavilySearchTool()
scrape_tool = ScrapeWebsiteTool()


# ============================================================
# LEAD SCORING AGENTS
# ============================================================

lead_data_agent = Agent(
    config=lead_agents_config["lead_data_agent"],
    llm=llm,
    tools=[search_tool, scrape_tool]
)

cultural_fit_agent = Agent(
    config=lead_agents_config["cultural_fit_agent"],
    llm=llm,
    tools=[search_tool, scrape_tool]
)

scoring_validation_agent = Agent(
    config=lead_agents_config["scoring_validation_agent"],
    llm=llm,
    tools=[search_tool, scrape_tool]
)


# ============================================================
# LEAD SCORING TASKS
# ============================================================

lead_data_task = Task(
    config=lead_tasks_config["lead_data_collection"],
    agent=lead_data_agent
)

cultural_fit_task = Task(
    config=lead_tasks_config["cultural_fit_analysis"],
    agent=cultural_fit_agent
)

scoring_validation_task = Task(
    config=lead_tasks_config["lead_scoring_and_validation"],
    agent=scoring_validation_agent,
    context=[lead_data_task, cultural_fit_task],
    output_pydantic=LeadScoringResult
)


# ============================================================
# LEAD SCORING CREW
# ============================================================

lead_scoring_crew = Crew(
    agents=[
        lead_data_agent,
        cultural_fit_agent,
        scoring_validation_agent
    ],
    tasks=[
        lead_data_task,
        cultural_fit_task,
        scoring_validation_task
    ],
    verbose=True
)


# ============================================================
# EMAIL AGENTS
# ============================================================

email_content_specialist = Agent(
    config=email_agents_config["email_content_specialist"],
    llm=llm
)

engagement_strategist = Agent(
    config=email_agents_config["engagement_strategist"],
    llm=llm
)


# ============================================================
# EMAIL TASKS
# ============================================================

email_drafting = Task(
    config=email_tasks_config["email_drafting"],
    agent=email_content_specialist
)

engagement_optimization = Task(
    config=email_tasks_config["engagement_optimization"],
    agent=engagement_strategist
)


# ============================================================
# EMAIL CREW
# ============================================================

email_writing_crew = Crew(
    agents=[
        email_content_specialist,
        engagement_strategist
    ],
    tasks=[
        email_drafting,
        engagement_optimization
    ],
    verbose=True
)

print("------------------")
# ============================================================
# CREWAI FLOW
# ============================================================
from crewai import Flow
from crewai.flow.flow import start


class SalesPipeline(Flow):

    @start()
    def score_lead(self):

        # The HTML form places one lead into the Flow state.
        lead = self.state["lead"]

        # Score exactly ONE lead
        result = lead_scoring_crew.kickoff(
            inputs=lead
        )

        # Extract the structured Pydantic result
        scoring_result = result.pydantic

        # Store it in Flow state
        self.state["scoring_result"] = scoring_result

        return scoring_result


def run_sales_pipeline(lead_data):

    flow = SalesPipeline()

    # One lead only
    flow.state["lead"] = {
        "lead_data": lead_data
    }

    scoring_result = flow.kickoff()

    # ------------------------------------------------
    # Email only if score > 70
    # ------------------------------------------------

    if scoring_result.lead_score.score > 70:
        scored_lead = scoring_result.model_dump()
        email_result = email_writing_crew.kickoff(
            inputs={
                "personal_info": scored_lead["personal_info"],
                "company_info": scored_lead["company_info"],
                "lead_score": scored_lead["lead_score"]
            }
        )
        email_output = email_result.raw
    else:
        email_output = (
            f"No Email because lead score "
            f"is {scoring_result.lead_score.score}, "
            f"which is below the qualification threshold of 70."
        )

    return {
        "scoring": scoring_result,
        "email": email_output
    }

