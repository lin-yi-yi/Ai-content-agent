from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel


class CardOut(BaseModel):
    id: int; draft_id: int; page_index: int; card_type: str
    title: str; subtitle: Optional[str] = None; body: Optional[str] = None
    highlight: Optional[str] = None; footer: Optional[str] = None
    layout_key: str; theme_key: str; style_json: Optional[dict] = None
    created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


class CardUpdate(BaseModel):
    title: Optional[str] = None; subtitle: Optional[str] = None
    body: Optional[str] = None; highlight: Optional[str] = None
    footer: Optional[str] = None; layout_key: Optional[str] = None
    theme_key: Optional[str] = None; style_json: Optional[dict] = None


class CardCreate(BaseModel):
    page_index: Optional[int] = None
    card_type: str = "concept"
    title: str = "新的内容卡"
    subtitle: Optional[str] = None
    body: Optional[str] = None
    highlight: Optional[str] = None
    footer: Optional[str] = "普通人的AI提效实验室"
    layout_key: str = "clean_knowledge"
    theme_key: str = "lab_clean"
    style_json: Optional[dict] = None


class CardMove(BaseModel):
    direction: Literal["up", "down"]
