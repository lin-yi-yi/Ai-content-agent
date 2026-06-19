"""Agent 执行记录 Schema"""
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.card import CardOut
from app.schemas.draft import DraftOut
from app.schemas.topic import TopicOut


class AgentRunCreate(BaseModel):
    goal: str = Field(..., min_length=1, max_length=1000)
    mode: str = "inspiration"
    research_depth: str = "quick"
    target_audience: str = ""
    viewpoint: str = ""
    personal_case: str = ""
    content_type: str = "auto"
    source_urls: list[str] = []
    provider: str = "local"
    model: str = ""
    auto_score: bool = True


class AgentStepOut(BaseModel):
    id: int
    run_id: int
    step_index: int
    key: str
    label: str
    status: str
    input_json: dict | None = None
    output_json: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentRunOut(BaseModel):
    id: int
    goal: str
    mode: str
    provider: str
    model_name: str | None = None
    status: str
    current_step: str | None = None
    selected_topic_id: int | None = None
    draft_id: int | None = None
    evaluation_score: int | None = None
    result_json: dict | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    steps: list[AgentStepOut] = []

    model_config = {"from_attributes": True}


class AgentRunResult(AgentRunOut):
    topic: TopicOut | None = None
    draft: DraftOut | None = None
    cards: list[CardOut] = []
    evaluation: dict | None = None
