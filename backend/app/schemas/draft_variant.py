from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.card import CardOut
from app.schemas.draft import DraftOut


class DraftVariantGenerateRequest(BaseModel):
    selected_title: str = ""
    selected_cover_text: str = ""
    body_variant_key: str = "first_person"
    body_variants: dict = Field(default_factory=dict)
    content_type: str = ""
    template_key: str = ""
    theme_key: str = ""
    max_card_count: int = 7
    provider: str = "local"
    model: str = ""


class DraftVariantSettingsUpdate(BaseModel):
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


class DraftVariantMeta(BaseModel):
    variant_name: str = ""
    selected_title: str = ""
    selected_cover_text: str = ""
    body_variant_key: str = "first_person"
    body_variants: dict = Field(default_factory=dict)
    content_type: str = ""
    template_key: str = ""
    theme_key: str = ""
    max_card_count: int = 7
    generated_reason: str = ""


class DraftVariantResponse(BaseModel):
    draft: DraftOut
    cards: list[CardOut]
    variant: DraftVariantMeta
