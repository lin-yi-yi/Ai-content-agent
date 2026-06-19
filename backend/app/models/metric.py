"""平台数据指标表"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    publish_log_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("publish_logs.id", ondelete="CASCADE"), nullable=False)
    views: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    likes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    favorites: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comments: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_followers: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=True)
    click_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    profile_visits: Mapped[int] = mapped_column(Integer, nullable=True)
    follow_conversion_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notes: Mapped[str] = mapped_column(Text, nullable=True)
