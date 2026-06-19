from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MetricCreate(BaseModel):
    publish_log_id: Optional[int] = None
    views: int = 0; likes: int = 0; favorites: int = 0
    comments: int = 0; shares: int = 0; new_followers: int = 0
    impressions: Optional[int] = None; click_rate: Optional[float] = None
    profile_visits: Optional[int] = None; follow_conversion_rate: Optional[float] = None
    notes: Optional[str] = None


class MetricOut(BaseModel):
    id: int; publish_log_id: int
    views: int; likes: int; favorites: int; comments: int; shares: int
    new_followers: int; impressions: Optional[int] = None
    click_rate: Optional[float] = None; profile_visits: Optional[int] = None
    follow_conversion_rate: Optional[float] = None
    collected_at: datetime; notes: Optional[str] = None
    model_config = {"from_attributes": True}
