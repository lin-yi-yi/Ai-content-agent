"""卡片生成服务 — CardAgent"""
from pathlib import Path

from app.llm.router import router as llm_router
from app.models.card import Card
from app.models.draft import Draft
from app.services.generation_schema import normalize_cards_result
from sqlalchemy.orm import Session

PROMPT_PATH = Path(__file__).parent.parent / "agents" / "prompts" / "card_generation.md"


def _load_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return "你是小红书图文卡片设计师，请生成卡片内容。"


async def generate_cards(draft: Draft, db: Session, provider: str = "deepseek", model: str = "") -> list[Card]:
    """调用 CardAgent 为草稿生成 7 页卡片"""
    system_prompt = _load_prompt()
    user_prompt = f"""选题：{draft.title_options[0] if draft.title_options else '未指定'}
正文：{draft.body_text[:500] if draft.body_text else '未生成'}"""

    client = llm_router.get_task_client("card_generation", provider=provider or None, model=model or None)
    result = client.chat_json(system_prompt, user_prompt, temperature=0.7)

    cards = []
    for card_data in normalize_cards_result(result, draft):
        card = Card(
            draft_id=draft.id,
            page_index=card_data.get("page_index", len(cards) + 1),
            card_type=card_data.get("card_type", "cover"),
            title=card_data.get("title", ""),
            subtitle=card_data.get("subtitle", ""),
            body=card_data.get("body", ""),
            highlight=card_data.get("highlight", ""),
            footer=card_data.get("footer", "普通人的AI提效实验室"),
            layout_key=card_data.get("layout_key", "clean_knowledge"),
            theme_key=card_data.get("theme_key", "lab_clean"),
        )
        db.add(card)
        cards.append(card)

    db.commit()
    for c in cards:
        db.refresh(c)
    return cards
