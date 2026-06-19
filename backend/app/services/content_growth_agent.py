"""内容增长 Agent 总调度器。"""
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.agent_run import AgentRun, AgentStep
from app.models.card import Card
from app.models.draft import Draft
from app.models.source import Source
from app.models.topic import Topic
from app.schemas.agent_run import AgentRunCreate, AgentRunResult
from app.schemas.card import CardOut
from app.schemas.draft import DraftOut
from app.schemas.topic import TopicOut
from app.services.card_generator import generate_cards
from app.services.compliance_checker import check_compliance
from app.services.custom_topic_creator import CustomTopicIdea, ResearchReference, generate_custom_topic_ideas
from app.services.draft_generator import generate_draft
from app.services.package_evaluator import evaluate_draft
from app.services.topic_scorer import score_topic


REVISION_THRESHOLD = 75

STEP_PLAN = [
    ("topic_ideas", "生成 5 个选题建议"),
    ("create_topic", "推荐最佳选题并入库"),
    ("score_topic", "选题评分"),
    ("generate_draft", "生成发布包"),
    ("generate_cards", "生成图文卡片"),
    ("compliance_check", "合规和事实核验提示"),
    ("evaluate_package", "发布包质量评分"),
    ("revise_package", "自动轻量改稿"),
    ("reevaluate_package", "改稿后再次评分"),
    ("agent_decision", "生成执行决策和下一步建议"),
]


def create_agent_run(req: AgentRunCreate, db: Session) -> AgentRunResult:
    """创建 Agent Run 和步骤，后台任务会继续执行。"""
    provider = req.provider or "local"
    run = AgentRun(
        goal=req.goal.strip(),
        mode=req.mode if req.mode in {"research", "inspiration"} else "inspiration",
        provider=provider,
        model_name=req.model or None,
        status="pending",
        current_step="queued",
        result_json={"_request": req.model_dump()},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    _create_steps(run.id, db)
    return get_agent_run(run.id, db)  # type: ignore[return-value]


async def execute_agent_run(run_id: int) -> None:
    """后台执行 Agent Run，从第一个未完成步骤继续。"""
    db = SessionLocal()
    try:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if not run:
            return
        req = _request_from_run(run)
        if not req:
            run.status = "failed"
            run.error_message = "缺少 Agent 请求参数，无法继续执行"
            db.commit()
            return
        run.status = "running"
        run.error_message = None
        db.commit()
        await _execute_steps(run, req, db)
    finally:
        db.close()


def prepare_retry_agent_run(run_id: int, db: Session) -> AgentRunResult | None:
    """把失败步骤及后续步骤重置为 pending，等待后台重试。"""
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        return None
    failed_step = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id, AgentStep.status == "failed")
        .order_by(AgentStep.step_index)
        .first()
    )
    if not failed_step:
        return get_agent_run(run_id, db)

    downstream = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id, AgentStep.step_index >= failed_step.step_index)
        .order_by(AgentStep.step_index)
        .all()
    )
    for step in downstream:
        step.status = "pending"
        step.error_message = None
        step.started_at = None
        step.completed_at = None
        step.input_json = None
        step.output_json = None
    run.status = "pending"
    run.current_step = "queued"
    run.error_message = None
    run.result_json = _prune_results_for_retry(run.result_json or {}, failed_step.key)
    db.commit()
    return get_agent_run(run_id, db)


def get_agent_run(run_id: int, db: Session) -> AgentRunResult | None:
    run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
    if not run:
        return None
    topic = db.query(Topic).filter(Topic.id == run.selected_topic_id).first() if run.selected_topic_id else None
    draft = db.query(Draft).filter(Draft.id == run.draft_id).first() if run.draft_id else None
    cards = db.query(Card).filter(Card.draft_id == run.draft_id).order_by(Card.page_index).all() if run.draft_id else []
    evaluation = (run.result_json or {}).get("reevaluation") or (run.result_json or {}).get("evaluation")
    return _run_result(run, db, topic=topic, draft=draft, cards=cards, evaluation=evaluation)


async def run_content_growth_agent(req: AgentRunCreate, db: Session) -> AgentRunResult:
    """兼容旧调用：同步执行并返回最终结果。"""
    result = create_agent_run(req, db)
    await execute_agent_run(result.id)
    db.expire_all()
    refreshed = get_agent_run(result.id, db)
    if not refreshed:
        raise RuntimeError("Agent Run 创建后未找到")
    return refreshed


async def _execute_steps(run: AgentRun, req: AgentRunCreate, db: Session) -> None:
    steps = _steps_by_key(run.id, db)
    try:
        selected_idea = await _step_topic_ideas(run, req, steps["topic_ideas"], db)
        topic = await _step_create_topic(run, selected_idea, steps["create_topic"], db)
        topic = await _step_score_topic(run, req, topic, steps["score_topic"], db)
        draft = await _step_generate_draft(run, req, topic, steps["generate_draft"], db)
        cards = await _step_generate_cards(run, req, draft, steps["generate_cards"], db)
        await _step_compliance(run, req, draft, steps["compliance_check"], db)
        evaluation = await _step_evaluate(run, req, draft, cards, steps["evaluate_package"], db, result_key="evaluation")
        final_evaluation = evaluation
        if int(evaluation.get("overall_score") or 0) < REVISION_THRESHOLD:
            await _step_revise(run, draft, cards, evaluation, steps["revise_package"], db)
            cards = db.query(Card).filter(Card.draft_id == draft.id).order_by(Card.page_index).all()
            final_evaluation = await _step_evaluate(run, req, draft, cards, steps["reevaluate_package"], db, result_key="reevaluation")
        else:
            _skip_step(steps["revise_package"], {"reason": f"质量评分已达到 {REVISION_THRESHOLD} 分，无需自动改稿"}, db)
            _skip_step(steps["reevaluate_package"], {"reason": "未触发自动改稿"}, db)
        await _step_agent_decision(run, req, topic, draft, cards, final_evaluation, steps["agent_decision"], db)
        topic.status = "generated"
        run.status = "completed"
        run.current_step = "completed"
        db.commit()
    except Exception as exc:
        _fail_running_step(run.id, str(exc), db)
        run.status = "failed"
        run.error_message = str(exc)
        db.commit()


async def _step_topic_ideas(run: AgentRun, req: AgentRunCreate, step: AgentStep, db: Session) -> CustomTopicIdea:
    existing = _result(run, "topic_ideas")
    if step.status == "completed" and existing:
        return _idea_from_payload(_selected_idea_payload(existing))
    _start_step(run, step, {"goal": req.goal, "mode": run.mode, "provider": req.provider or "local"}, db)
    ideas_result = await generate_custom_topic_ideas(
        mode=run.mode,
        research_depth=req.research_depth,
        theme=req.goal,
        target_audience=req.target_audience,
        viewpoint=req.viewpoint,
        personal_case=req.personal_case,
        content_type=req.content_type,
        source_urls=req.source_urls,
        provider=req.provider or "local",
        model=req.model,
    )
    ideas = sorted(ideas_result.ideas, key=lambda item: item.score, reverse=True)
    selected_idea = ideas[0]
    payload = {
        "research_status": ideas_result.research_status,
        "keywords": ideas_result.keywords,
        "ideas": [_idea_payload(item) for item in ideas],
        "recommended_title": selected_idea.title,
    }
    _set_result(run, "topic_ideas", payload, db)
    _finish_step(step, "completed", payload, db)
    return selected_idea


async def _step_create_topic(run: AgentRun, selected_idea: CustomTopicIdea, step: AgentStep, db: Session) -> Topic:
    if step.status == "completed" and run.selected_topic_id:
        topic = db.query(Topic).filter(Topic.id == run.selected_topic_id).first()
        if topic:
            return topic
    _start_step(run, step, {"recommended_title": selected_idea.title}, db)
    topic = _create_topic_from_idea(selected_idea, db)
    run.selected_topic_id = topic.id
    payload = {
        "topic_id": topic.id,
        "source_id": topic.source_id,
        "title": topic.title,
        "score": topic.score,
        "verification_status": selected_idea.verification_status,
    }
    _set_result(run, "topic", payload, db)
    _finish_step(step, "completed", payload, db)
    return topic


async def _step_score_topic(run: AgentRun, req: AgentRunCreate, topic: Topic, step: AgentStep, db: Session) -> Topic:
    if step.status == "completed":
        db.refresh(topic)
        return topic
    _start_step(run, step, {"topic_id": topic.id, "auto_score": req.auto_score}, db)
    if req.auto_score:
        score_result = await score_topic(topic.id, db, provider=req.provider or "local", model=req.model or None)
        db.refresh(topic)
    else:
        score_result = {"score": topic.score, "reason": topic.score_reason, "skipped": True}
    payload = {
        "topic_id": topic.id,
        "score": topic.score,
        "risk_level": topic.risk_level,
        "result": _compact(score_result),
    }
    _set_result(run, "score", payload, db)
    _finish_step(step, "completed", payload, db)
    return topic


async def _step_generate_draft(run: AgentRun, req: AgentRunCreate, topic: Topic, step: AgentStep, db: Session) -> Draft:
    if step.status == "completed" and run.draft_id:
        draft = db.query(Draft).filter(Draft.id == run.draft_id).first()
        if draft:
            return draft
    _start_step(run, step, {"topic_id": topic.id}, db)
    draft = await generate_draft(topic, db, provider=req.provider or "local", model=req.model or None)
    run.draft_id = draft.id
    payload = {
        "draft_id": draft.id,
        "title_options": draft.title_options or [],
        "cover_text_options": draft.cover_text_options or [],
    }
    _set_result(run, "draft", payload, db)
    _finish_step(step, "completed", payload, db)
    return draft


async def _step_generate_cards(run: AgentRun, req: AgentRunCreate, draft: Draft, step: AgentStep, db: Session) -> list[Card]:
    existing_cards = db.query(Card).filter(Card.draft_id == draft.id).order_by(Card.page_index).all()
    if step.status == "completed" and existing_cards:
        return existing_cards
    _start_step(run, step, {"draft_id": draft.id}, db)
    if existing_cards:
        for card in existing_cards:
            db.delete(card)
        db.commit()
    cards = await generate_cards(draft, db, provider=req.provider or "local", model=req.model or None)
    payload = {
        "draft_id": draft.id,
        "card_count": len(cards),
        "cards": [{"id": card.id, "page_index": card.page_index, "title": card.title} for card in cards],
    }
    _set_result(run, "cards", payload, db)
    _finish_step(step, "completed", payload, db)
    return cards


async def _step_compliance(run: AgentRun, req: AgentRunCreate, draft: Draft, step: AgentStep, db: Session) -> None:
    if step.status == "completed":
        return
    _start_step(run, step, {"draft_id": draft.id}, db)
    compliance = await check_compliance(draft, db, provider=req.provider or "local", model=req.model or None)
    db.refresh(draft)
    payload = _compact(compliance)
    _set_result(run, "compliance", payload, db)
    _finish_step(step, "completed", payload, db)


async def _step_evaluate(
    run: AgentRun,
    req: AgentRunCreate,
    draft: Draft,
    cards: list[Card],
    step: AgentStep,
    db: Session,
    result_key: str,
) -> dict:
    if step.status == "completed":
        return _result(run, result_key) or {}
    _start_step(run, step, {"draft_id": draft.id, "card_count": len(cards)}, db)
    evaluation = await evaluate_draft(draft, cards, db, provider=req.provider or "local", model=req.model or "")
    run.evaluation_score = int(evaluation.get("overall_score") or 0)
    payload = _compact(evaluation)
    _set_result(run, result_key, payload, db)
    _finish_step(step, "completed", payload, db)
    return evaluation


async def _step_revise(run: AgentRun, draft: Draft, cards: list[Card], evaluation: dict, step: AgentStep, db: Session) -> None:
    if step.status == "completed":
        return
    _start_step(run, step, {"draft_id": draft.id, "evaluation_score": evaluation.get("overall_score")}, db)
    payload = _revise_draft_and_cards(draft, cards, evaluation, db)
    _set_result(run, "revision", payload, db)
    _finish_step(step, "completed", payload, db)


async def _step_agent_decision(
    run: AgentRun,
    req: AgentRunCreate,
    topic: Topic,
    draft: Draft,
    cards: list[Card],
    evaluation: dict,
    step: AgentStep,
    db: Session,
) -> None:
    if step.status == "completed":
        return
    _start_step(run, step, {"draft_id": draft.id, "topic_id": topic.id, "evaluation_score": run.evaluation_score}, db)
    payload = _build_agent_decision(run, req, topic, draft, cards, evaluation)
    _set_result(run, "agent_decision", payload, db)
    _finish_step(step, "completed", payload, db)


def _build_agent_decision(
    run: AgentRun,
    req: AgentRunCreate,
    topic: Topic,
    draft: Draft,
    cards: list[Card],
    evaluation: dict,
) -> dict:
    data = run.result_json or {}
    topic_ideas = data.get("topic_ideas") if isinstance(data.get("topic_ideas"), dict) else {}
    selected_idea: dict[str, Any] = {}
    if topic_ideas:
        try:
            selected_idea = _selected_idea_payload(topic_ideas)
        except ValueError:
            selected_idea = {}

    revision = data.get("revision") if isinstance(data.get("revision"), dict) else {}
    score = int(evaluation.get("overall_score") or run.evaluation_score or 0)
    readiness = str(evaluation.get("publish_readiness") or "needs_review")
    verification_status = str(selected_idea.get("verification_status") or "未核验")
    confidence = _decision_confidence(score, verification_status, readiness)
    issues = evaluation.get("issues") if isinstance(evaluation.get("issues"), list) else []
    strengths = evaluation.get("strengths") if isinstance(evaluation.get("strengths"), list) else []
    references = selected_idea.get("references") if isinstance(selected_idea.get("references"), list) else []

    decision_status = "ready_for_review"
    if readiness == "not_ready" or score < 60:
        decision_status = "needs_major_revision"
    elif readiness != "ready" or score < REVISION_THRESHOLD:
        decision_status = "needs_review"

    why_this_topic = [
        item for item in [
            selected_idea.get("reason"),
            f"选题分数 {topic.score}/100，角度是「{topic.content_angle or '未填写'}」。",
            f"目标人群：{topic.target_audience or req.target_audience or 'AI 新手 / 职场人'}。",
        ] if item
    ]

    next_actions = _build_next_actions(score, readiness, bool(revision), issues, references)
    manual_review_focus = _manual_review_focus(draft, issues, verification_status)
    summary = (
        f"Agent 已围绕「{run.goal[:60]}」选择「{topic.title}」，"
        f"生成 {len(cards)} 页图文发布包，当前质量评分 {score}/100。"
    )

    return {
        "summary": summary,
        "decision_status": decision_status,
        "confidence": confidence,
        "selected_topic": {
            "id": topic.id,
            "title": topic.title,
            "score": topic.score,
            "content_angle": topic.content_angle,
            "verification_status": verification_status,
            "reason": selected_idea.get("reason") or topic.score_reason,
        },
        "quality_gate": {
            "score": score,
            "threshold": REVISION_THRESHOLD,
            "publish_readiness": readiness,
            "passed": score >= REVISION_THRESHOLD and readiness != "not_ready",
            "strengths": [str(item) for item in strengths[:4]],
        },
        "revision": {
            "triggered": bool(revision),
            "changes": revision.get("changes") if revision else [],
            "reason": revision.get("reason") if revision else "质量评分达到阈值，未触发自动改稿。",
        },
        "why_this_topic": [str(item) for item in why_this_topic[:4]],
        "manual_review_focus": manual_review_focus,
        "next_actions": next_actions,
        "source_trace": {
            "research_status": topic_ideas.get("research_status") if isinstance(topic_ideas, dict) else None,
            "keywords": topic_ideas.get("keywords") if isinstance(topic_ideas, dict) else [],
            "references": references[:5],
        },
    }


def _decision_confidence(score: int, verification_status: str, readiness: str) -> str:
    if "未" in verification_status or readiness == "not_ready" or score < 60:
        return "low"
    if score >= 80 and readiness == "ready":
        return "high"
    return "medium"


def _build_next_actions(score: int, readiness: str, revised: bool, issues: list, references: list) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if score < 60 or readiness == "not_ready":
        actions.append({
            "priority": "high",
            "label": "先补事实来源或个人案例",
            "reason": "当前发布包还不适合直接进入发布前审核，需要增强可信度和例子。",
            "target": "topic",
        })
    elif score < REVISION_THRESHOLD:
        actions.append({
            "priority": "high",
            "label": "优先改封面和前两页卡片",
            "reason": "质量评分未达到自动通过线，先处理钩子、密度和收藏价值。",
            "target": "cards",
        })
    else:
        actions.append({
            "priority": "high",
            "label": "进入人工审核清单",
            "reason": "内容质量已过基础线，下一步应人工核验事实、风险表达和 AIGC 标识。",
            "target": "review_checklist",
        })

    if revised:
        actions.append({
            "priority": "medium",
            "label": "复查自动改稿处",
            "reason": "Agent 已做过一次轻量修订，建议确认标题和卡片压缩后是否仍然自然。",
            "target": "draft",
        })
    if not references:
        actions.append({
            "priority": "medium",
            "label": "补一个可追溯来源",
            "reason": "本次主要依赖主题灵感，发布前最好补充工具官网、项目 README 或真实操作截图。",
            "target": "source",
        })
    if issues:
        actions.append({
            "priority": "medium",
            "label": "逐条处理质量问题",
            "reason": "质量评分器已经列出具体问题，处理后可以重新评分。",
            "target": "evaluation",
        })
    actions.append({
        "priority": "low",
        "label": "发布后录入数据",
        "reason": "手动发布后记录阅读、点赞、收藏和评论，后续复盘才能反推选题质量。",
        "target": "metrics",
    })
    return actions[:5]


def _manual_review_focus(draft: Draft, issues: list, verification_status: str) -> list[str]:
    focus = []
    if "未" in verification_status:
        focus.append("核验来源和关键事实，避免把观点创作写成事实结论。")
    for issue in issues[:3]:
        if isinstance(issue, dict) and issue.get("message"):
            page = f"第 {issue.get('card_page')} 页：" if issue.get("card_page") else ""
            focus.append(f"{page}{issue.get('message')}")
    if draft.risk_tips:
        focus.append(str(draft.risk_tips[0]))
    if draft.aigc_notice:
        focus.append("保留 AIGC 标识建议，发布前按平台要求处理。")
    return list(dict.fromkeys(focus))[:5]


def _revise_draft_and_cards(draft: Draft, cards: list[Card], evaluation: dict, db: Session) -> dict:
    changes: list[str] = []
    title_options = list(draft.title_options or [])
    if title_options:
        original = str(title_options[0])
        if not any(word in original for word in ["别", "先", "步骤", "清单"]):
            title_options[0] = f"先别急着全自动：{original[:22]}"
            changes.append("强化第一个标题的行动钩子")
    cover_options = list(draft.cover_text_options or [])
    if cover_options:
        cover_options[0] = str(cover_options[0])[:18] or "先跑通这套流程"
        if "流程" not in cover_options[0]:
            cover_options[0] = f"{cover_options[0]}流程"
        changes.append("收紧封面文案")
    if draft.body_text and len(draft.body_text) > 900:
        draft.body_text = draft.body_text[:880] + "\n\n最后发布前我会人工核验事实和边界。"
        changes.append("压缩正文长度并补充人工核验提醒")
    draft.title_options = title_options
    draft.cover_text_options = cover_options
    risks = list(draft.risk_tips or [])
    risk = "发布前确认工具能力、数据来源和个人案例是否真实，不写成保证收益。"
    if risk not in risks:
        risks.append(risk)
        draft.risk_tips = risks
        changes.append("补充风险提示")

    for card in cards:
        if card.body and len(card.body) > 150:
            card.body = card.body[:138].rstrip("，。；;,. ") + "。"
            changes.append(f"精简第 {card.page_index} 页正文")
        if card.page_index == 1 and title_options:
            card.title = str(title_options[0])[:255]
            changes.append("同步封面卡标题")

    db.commit()
    db.refresh(draft)
    for card in cards:
        db.refresh(card)
    return {
        "changed": bool(changes),
        "changes": list(dict.fromkeys(changes)),
        "reason": "质量评分低于阈值，已进行一次本地规则轻量修订。",
    }


def _create_steps(run_id: int, db: Session) -> dict[str, AgentStep]:
    steps: dict[str, AgentStep] = {}
    for index, (key, label) in enumerate(STEP_PLAN, start=1):
        step = AgentStep(run_id=run_id, step_index=index, key=key, label=label, status="pending")
        db.add(step)
        steps[key] = step
    db.commit()
    for step in steps.values():
        db.refresh(step)
    return steps


def _steps_by_key(run_id: int, db: Session) -> dict[str, AgentStep]:
    existing = db.query(AgentStep).filter(AgentStep.run_id == run_id).order_by(AgentStep.step_index).all()
    if not existing:
        return _create_steps(run_id, db)
    existing_keys = {step.key for step in existing}
    missing = [(key, label) for key, label in STEP_PLAN if key not in existing_keys]
    if missing:
        next_index = max(step.step_index for step in existing)
        for key, label in missing:
            next_index += 1
            db.add(AgentStep(run_id=run_id, step_index=next_index, key=key, label=label, status="pending"))
        db.commit()
        existing = db.query(AgentStep).filter(AgentStep.run_id == run_id).order_by(AgentStep.step_index).all()
    return {step.key: step for step in existing}


def _start_step(run: AgentRun, step: AgentStep, input_json: dict[str, Any], db: Session) -> None:
    run.current_step = step.key
    step.status = "running"
    step.started_at = datetime.utcnow()
    step.completed_at = None
    step.error_message = None
    step.input_json = _compact(input_json)
    db.commit()


def _finish_step(step: AgentStep, status: str, output_json: dict[str, Any], db: Session) -> None:
    step.status = status
    step.output_json = _compact(output_json)
    step.completed_at = datetime.utcnow()
    db.commit()


def _skip_step(step: AgentStep, output_json: dict[str, Any], db: Session) -> None:
    if step.status in {"completed", "skipped"}:
        return
    step.status = "skipped"
    step.output_json = _compact(output_json)
    step.completed_at = datetime.utcnow()
    db.commit()


def _fail_running_step(run_id: int, message: str, db: Session) -> None:
    step = (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run_id, AgentStep.status == "running")
        .order_by(AgentStep.step_index.desc())
        .first()
    )
    if step:
        step.status = "failed"
        step.error_message = message[:1000]
        step.completed_at = datetime.utcnow()
        db.commit()


def _create_topic_from_idea(idea: CustomTopicIdea, db: Session) -> Topic:
    first_url = next((ref.url for ref in idea.references if ref.url and ref.status == "ok"), None)
    source = Source(
        source_type=idea.source_type or "custom_idea",
        title=idea.title[:255],
        url=first_url,
        raw_content=_source_raw(idea)[:20000],
        summary=idea.summary,
    )
    db.add(source)
    db.flush()
    topic = Topic(
        source_id=source.id,
        title=idea.title[:255],
        url=first_url,
        source_type=idea.source_type or "custom_idea",
        raw_summary=idea.summary,
        concise_summary=idea.summary[:255],
        target_audience=idea.target_audience[:100] if idea.target_audience else None,
        content_angle=idea.content_angle[:100] if idea.content_angle else None,
        recommended_platform=idea.recommended_platform or "小红书图文",
        score=max(0, min(100, int(idea.score or 0))),
        score_reason=_score_reason(idea),
        status="pending",
        risk_level="low",
    )
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def _source_raw(idea: CustomTopicIdea) -> str:
    refs = "\n".join(
        f"- {ref.title} | {ref.url or '无链接'} | {ref.status} | {ref.summary}"
        for ref in idea.references
    )
    return (
        f"Agent 自动选题：{idea.title}\n"
        f"角度：{idea.content_angle}\n"
        f"目标人群：{idea.target_audience}\n"
        f"核验状态：{idea.verification_status}\n"
        f"关键词：{'、'.join(idea.keywords or [])}\n\n"
        f"摘要：{idea.summary}\n\n"
        f"推荐理由：{idea.reason}\n"
        f"风险提醒：{idea.risk_tip}\n\n"
        f"参考来源：\n{refs or '无'}"
    )


def _score_reason(idea: CustomTopicIdea) -> str:
    return "\n".join(
        part for part in [
            idea.reason,
            f"核验状态：{idea.verification_status}" if idea.verification_status else "",
            f"风险提醒：{idea.risk_tip}" if idea.risk_tip else "",
        ] if part
    )


def _idea_payload(idea: CustomTopicIdea) -> dict[str, Any]:
    return {
        "title": idea.title,
        "content_angle": idea.content_angle,
        "target_audience": idea.target_audience,
        "summary": idea.summary,
        "reason": idea.reason,
        "risk_tip": idea.risk_tip,
        "recommended_platform": idea.recommended_platform,
        "source_type": idea.source_type,
        "score": idea.score,
        "keywords": idea.keywords,
        "verification_status": idea.verification_status,
        "references": [_reference_payload(ref) for ref in idea.references],
    }


def _idea_from_payload(payload: dict[str, Any]) -> CustomTopicIdea:
    return CustomTopicIdea(
        title=str(payload.get("title") or "AI 工作流选题"),
        content_angle=str(payload.get("content_angle") or "教程"),
        target_audience=str(payload.get("target_audience") or "AI 新手 / 职场人"),
        summary=str(payload.get("summary") or ""),
        reason=str(payload.get("reason") or "适合转成小红书图文。"),
        risk_tip=str(payload.get("risk_tip") or "需要人工核验事实和边界。"),
        recommended_platform=str(payload.get("recommended_platform") or "小红书图文"),
        source_type=str(payload.get("source_type") or "custom_idea"),
        score=int(payload.get("score") or 65),
        keywords=[str(item) for item in (payload.get("keywords") or [])],
        references=[_reference_from_payload(item) for item in (payload.get("references") or []) if isinstance(item, dict)],
        verification_status=str(payload.get("verification_status") or "未核验"),
    )


def _selected_idea_payload(payload: dict[str, Any]) -> dict[str, Any]:
    ideas = payload.get("ideas") if isinstance(payload.get("ideas"), list) else []
    if not ideas:
        raise ValueError("缺少选题建议，无法继续执行")
    recommended = payload.get("recommended_title")
    for item in ideas:
        if isinstance(item, dict) and item.get("title") == recommended:
            return item
    first = ideas[0]
    if not isinstance(first, dict):
        raise ValueError("选题建议格式错误")
    return first


def _reference_payload(ref: ResearchReference) -> dict[str, Any]:
    return {
        "title": ref.title,
        "url": ref.url,
        "summary": ref.summary,
        "source_type": ref.source_type,
        "status": ref.status,
    }


def _reference_from_payload(payload: dict[str, Any]) -> ResearchReference:
    return ResearchReference(
        title=str(payload.get("title") or ""),
        url=str(payload.get("url") or ""),
        summary=str(payload.get("summary") or ""),
        source_type=str(payload.get("source_type") or "manual"),
        status=str(payload.get("status") or "ok"),
    )


def _request_from_run(run: AgentRun) -> AgentRunCreate | None:
    data = (run.result_json or {}).get("_request")
    if not isinstance(data, dict):
        return None
    return AgentRunCreate(**data)


def _result(run: AgentRun, key: str) -> Any:
    return (run.result_json or {}).get(key)


def _set_result(run: AgentRun, key: str, value: Any, db: Session) -> None:
    data = dict(run.result_json or {})
    data[key] = _compact(value)
    run.result_json = data
    db.commit()


def _prune_results_for_retry(result_json: dict[str, Any], failed_key: str) -> dict[str, Any]:
    keep = {"_request"}
    order = [key for key, _ in STEP_PLAN]
    result_key_by_step = {
        "topic_ideas": "topic_ideas",
        "create_topic": "topic",
        "score_topic": "score",
        "generate_draft": "draft",
        "generate_cards": "cards",
        "compliance_check": "compliance",
        "evaluate_package": "evaluation",
        "revise_package": "revision",
        "reevaluate_package": "reevaluation",
        "agent_decision": "agent_decision",
    }
    for key in order:
        if key == failed_key:
            break
        result_key = result_key_by_step.get(key)
        if result_key:
            keep.add(result_key)
    return {key: value for key, value in result_json.items() if key in keep}


def _compact(value: Any, max_text: int = 1200) -> Any:
    if isinstance(value, dict):
        return {str(k): _compact(v, max_text=max_text) for k, v in value.items()}
    if isinstance(value, list):
        return [_compact(item, max_text=max_text) for item in value[:20]]
    if isinstance(value, str):
        return value[:max_text]
    return value


def _run_result(
    run: AgentRun,
    db: Session,
    topic: Topic | None = None,
    draft: Draft | None = None,
    cards: list[Card] | None = None,
    evaluation: dict | None = None,
) -> AgentRunResult:
    steps = db.query(AgentStep).filter(AgentStep.run_id == run.id).order_by(AgentStep.step_index).all()
    return AgentRunResult(
        **{
            "id": run.id,
            "goal": run.goal,
            "mode": run.mode,
            "provider": run.provider,
            "model_name": run.model_name,
            "status": run.status,
            "current_step": run.current_step,
            "selected_topic_id": run.selected_topic_id,
            "draft_id": run.draft_id,
            "evaluation_score": run.evaluation_score,
            "result_json": run.result_json,
            "error_message": run.error_message,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "steps": steps,
            "topic": TopicOut.model_validate(topic) if topic else None,
            "draft": DraftOut.model_validate(draft) if draft else None,
            "cards": [CardOut.model_validate(card) for card in (cards or [])],
            "evaluation": evaluation,
        }
    )
