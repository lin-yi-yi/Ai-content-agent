"""选题 Pydantic Schema"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TopicCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    url: Optional[str] = None
    source_type: str = Field(default="manual")
    raw_summary: Optional[str] = None


class TopicUpdate(BaseModel):
    title: Optional[str] = None
    url: Optional[str] = None
    source_type: Optional[str] = None
    raw_summary: Optional[str] = None
    concise_summary: Optional[str] = None
    target_audience: Optional[str] = None
    content_angle: Optional[str] = None
    recommended_platform: Optional[str] = None
    score: Optional[int] = None
    score_reason: Optional[str] = None
    status: Optional[str] = None
    risk_level: Optional[str] = None


class TopicOut(BaseModel):
    id: int
    source_id: Optional[int] = None
    title: str
    url: Optional[str] = None
    source_type: str
    raw_summary: Optional[str] = None
    concise_summary: Optional[str] = None
    target_audience: Optional[str] = None
    content_angle: Optional[str] = None
    recommended_platform: Optional[str] = None
    score: int
    score_reason: Optional[str] = None
    status: str
    risk_level: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TopicListOut(BaseModel):
    total: int
    items: list[TopicOut]
