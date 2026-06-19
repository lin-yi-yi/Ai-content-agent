"""选题评分服务 — 调用 LLM 进行 7 维度选题评分"""
from pathlib import Path

from sqlalchemy.orm import Session

from app.llm.router import router as llm_router
from app.models.topic import Topic
from app.services.generation_schema import normalize_topic_score_result

PROMPT_PATH = Path(__file__).parent.parent / "agents" / "prompts" / "topic_score.md"


def _load_scoring_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return "你是 AI 内容运营专家，请对选题进行评分。"


async def score_topic(topic_id: int, db: Session, provider: str = "deepseek", model: str = "") -> dict:
    """对选题进行 AI 评分，更新数据库并返回结果"""
    topic = db.query(Topic).filter(Topic.id == topic_id).first()
    if not topic:
        raise ValueError(f"选题 #{topic_id} 不存在")

    system_prompt = _load_scoring_prompt()
    user_prompt = f"""只输出 JSON，不要写任何分析过程。

标题：{topic.title}
来源类型：{topic.source_type}
来源网址：{topic.url or '无'}
原始摘要：{topic.raw_summary or '无'}"""

    client = llm_router.get_task_client("topic_score", provider=provider or None, model=model or None)
    result = normalize_topic_score_result(client.chat_json(system_prompt, user_prompt, temperature=0.3))

    # 写入数据库
    topic.concise_summary = result.get("concise_summary", "")
    topic.target_audience = result.get("target_audience", "")
    topic.content_angle = result.get("content_angle", "")
    topic.recommended_platform = result.get("recommended_platform", "")
    topic.score = max(0, min(100, int(result.get("score", 0))))
    topic.score_reason = result.get("score_reason", "")
    topic.risk_level = result.get("risk_level", "low")
    if topic.status not in {"generated", "published", "reviewed"}:
        topic.status = "discarded" if topic.score < 45 or topic.risk_level == "high" else "pending"
    db.commit()
    db.refresh(topic)

    return {
        "topic_id": topic.id,
        "score": topic.score,
        "score_reason": topic.score_reason,
        "concise_summary": topic.concise_summary,
        "target_audience": topic.target_audience,
        "content_angle": topic.content_angle,
        "recommended_platform": topic.recommended_platform,
        "risk_level": topic.risk_level,
        "status": topic.status,
    }
