"""人工审核清单 Schema"""
from typing import Optional
from pydantic import BaseModel


class ChecklistItemOut(BaseModel):
    id: int
    draft_id: int
    key: str
    label: str
    checked: bool
    note: Optional[str] = None
    model_config = {"from_attributes": True}


class ChecklistUpdateItem(BaseModel):
    key: str
    checked: bool
    note: Optional[str] = None


class ChecklistUpdateRequest(BaseModel):
    items: list[ChecklistUpdateItem]
