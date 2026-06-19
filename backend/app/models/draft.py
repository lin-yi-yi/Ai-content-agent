"""发布包草稿表"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    topic_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False, default="xiaohongshu")
    title_options: Mapped[dict] = mapped_column(JSON, nullable=True)
    cover_text_options: Mapped[dict] = mapped_column(JSON, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=True)
    hashtags: Mapped[dict] = mapped_column(JSON, nullable=True)
    comment_guide: Mapped[str] = mapped_column(Text, nullable=True)
    fact_checks: Mapped[dict] = mapped_column(JSON, nullable=True)
    risk_tips: Mapped[dict] = mapped_column(JSON, nullable=True)
    aigc_notice: Mapped[str] = mapped_column(Text, nullable=True)
    model_provider: Mapped[str] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=True)
    variant_name: Mapped[str] = mapped_column(String(255), nullable=True)
    selected_title: Mapped[str] = mapped_column(String(255), nullable=True)
    selected_cover_text: Mapped[str] = mapped_column(String(255), nullable=True)
    body_variant_key: Mapped[str] = mapped_column(String(50), nullable=True)
    body_variants: Mapped[dict] = mapped_column(JSON, nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=True)
    template_key: Mapped[str] = mapped_column(String(100), nullable=True)
    theme_key: Mapped[str] = mapped_column(String(100), nullable=True)
    max_card_count: Mapped[int] = mapped_column(Integer, nullable=True)
    generated_reason: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
