from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DraftOut(BaseModel):
    id: int; topic_id: int; platform: str
    title_options: Optional[list] = None; cover_text_options: Optional[list] = None
    body_text: Optional[str] = None; hashtags: Optional[list] = None
    comment_guide: Optional[str] = None; fact_checks: Optional[list] = None
    risk_tips: Optional[list] = None; aigc_notice: Optional[str] = None
    model_provider: Optional[str] = None; model_name: Optional[str] = None
    variant_name: Optional[str] = None
    selected_title: Optional[str] = None
    selected_cover_text: Optional[str] = None
    body_variant_key: Optional[str] = None
    body_variants: Optional[dict] = None
    content_type: Optional[str] = None
    template_key: Optional[str] = None
    theme_key: Optional[str] = None
    max_card_count: Optional[int] = None
    generated_reason: Optional[str] = None
    status: str; created_at: datetime; updated_at: datetime
    model_config = {"from_attributes": True}


class DraftUpdate(BaseModel):
    body_text: Optional[str] = None; hashtags: Optional[list] = None
    comment_guide: Optional[str] = None; status: Optional[str] = None
    title_options: Optional[list] = None; cover_text_options: Optional[list] = None
    fact_checks: Optional[list] = None; risk_tips: Optional[list] = None
    aigc_notice: Optional[str] = None
    variant_name: Optional[str] = None
    selected_title: Optional[str] = None
    selected_cover_text: Optional[str] = None
    body_variant_key: Optional[str] = None
    body_variants: Optional[dict] = None
    content_type: Optional[str] = None
    template_key: Optional[str] = None
    theme_key: Optional[str] = None
    max_card_count: Optional[int] = None
    generated_reason: Optional[str] = None
