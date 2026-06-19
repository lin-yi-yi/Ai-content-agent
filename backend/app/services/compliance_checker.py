"""合规检查服务 — ComplianceAgent"""
from pathlib import Path

from app.llm.router import router as llm_router
from app.models.draft import Draft
from app.services.generation_schema import normalize_compliance_result
from sqlalchemy.orm import Session

PROMPT_PATH = Path(__file__).parent.parent / "agents" / "prompts" / "compliance_check.md"


def _load_prompt() -> str:
    if PROMPT_PATH.exists():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return "你是内容合规审核员，请检查风险。"


async def check_compliance(draft: Draft, db: Session, provider: str = "deepseek", model: str = "") -> dict:
    """检查草稿合规性，更新 fact_checks 和 risk_tips"""
    system_prompt = _load_prompt()
    user_prompt = f"""标题：{draft.title_options[0] if draft.title_options else ''}
正文：{draft.body_text[:800] if draft.body_text else ''}"""

    client = llm_router.get_task_client("compliance_check", provider=provider or None, model=model or None)
    result = normalize_compliance_result(client.chat_json(system_prompt, user_prompt, temperature=0.2))

    # 合并检查结果到草稿
    existing_facts = list(draft.fact_checks or [])
    existing_risks = list(draft.risk_tips or [])
    new_facts = result.get("fact_checks", [])
    new_risks = result.get("risk_tips", [])

    draft.fact_checks = existing_facts + [f for f in new_facts if f not in existing_facts]
    draft.risk_tips = existing_risks + [r for r in new_risks if r not in existing_risks]
    if not draft.aigc_notice:
        draft.aigc_notice = result.get("aigc_notice", "")
    draft.risk_level = result.get("risk_level", draft.risk_level) if hasattr(draft, 'risk_level') else result.get("risk_level", "low")
    draft.status = "draft"
    db.commit()
    db.refresh(draft)

    return result
