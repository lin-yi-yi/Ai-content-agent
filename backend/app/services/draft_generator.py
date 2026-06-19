"""发布包生成服务 — DraftAgent"""
from pathlib import Path

from app.llm.router import router as llm_router
from app.models.draft import Draft
from app.models.topic import Topic
from app.services.generation_schema import normalize_draft_result
from sqlalchemy.orm import Session

PROMPT_PATH = Path(__file__).parent.parent / "agents" / "prompts" / "xiaohongshu_draft.md"


def _load_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return "你是小红书内容创作专家，请生成发布包。"


async def generate_draft(topic: Topic, db: Session, provider: str = "deepseek", model: str = "") -> Draft:
    """调用 DraftAgent 生成小红书发布包"""
    system_prompt = _load_prompt()
    user_prompt = f"""选题标题：{topic.title}
选题角度：{topic.content_angle or '未指定'}
目标人群：{topic.target_audience or '职场人'}
摘要：{topic.concise_summary or topic.raw_summary or '无'}
评分：{topic.score}/100"""

    client = llm_router.get_task_client("draft_generation", provider=provider or None, model=model or None)
    result = normalize_draft_result(client.chat_json(system_prompt, user_prompt, temperature=0.7), topic)

    draft = Draft(
        topic_id=topic.id,
        platform="xiaohongshu",
        title_options=result.get("title_options", []),
        cover_text_options=result.get("cover_text_options", []),
        body_text=result.get("body_text", ""),
        hashtags=result.get("hashtags", []),
        comment_guide=result.get("comment_guide", ""),
        fact_checks=result.get("fact_checks", []),
        risk_tips=result.get("risk_tips", []),
        aigc_notice=result.get("aigc_notice", ""),
        model_provider=getattr(client, "provider", provider),
        model_name=model or client.model,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft
