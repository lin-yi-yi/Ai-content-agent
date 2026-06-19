"""发布包质量评分 Schema"""
from typing import Optional
from pydantic import BaseModel


class Issue(BaseModel):
    level: str = "medium"
    card_page: Optional[int] = None
    message: str = ""


class Scores(BaseModel):
    title_hook: int = 0
    xiaohongshu_fit: int = 0
    collectability: int = 0
    clarity: int = 0
    workflow_usability: int = 0
    card_rhythm: int = 0
    factual_risk: int = 0
    comment_guide: int = 0
    aigc_readiness: int = 0


class EvaluationOut(BaseModel):
    overall_score: int = 0
    publish_readiness: str = "needs_review"
    scores: Scores = Scores()
    strengths: list[str] = []
    issues: list[Issue] = []
    rewrite_suggestions: list[str] = []
