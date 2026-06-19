"""自定义选题创作与中文互联网调研建议生成。"""
from dataclasses import dataclass, field
from typing import Any

from app.llm.router import router as llm_router
from app.services.source_importer import clean_text, import_source_from_url, trim


CONTENT_TYPE_LABELS = {
    "auto": "自动判断",
    "tutorial": "教程",
    "pitfall": "避坑",
    "tool_review": "工具测评",
    "case_study": "案例复盘",
    "opinion": "观点",
    "dev_log": "开发日志",
}


@dataclass
class ResearchReference:
    title: str
    url: str = ""
    summary: str = ""
    source_type: str = "manual"
    status: str = "ok"


@dataclass
class CustomTopicIdea:
    title: str
    content_angle: str
    target_audience: str
    summary: str
    reason: str
    risk_tip: str
    recommended_platform: str = "小红书图文"
    source_type: str = "custom_idea"
    score: int = 65
    keywords: list[str] = field(default_factory=list)
    references: list[ResearchReference] = field(default_factory=list)
    verification_status: str = "未核验"


@dataclass
class CustomTopicIdeasResult:
    mode: str
    research_depth: str
    research_status: str
    keywords: list[str]
    references: list[ResearchReference]
    ideas: list[CustomTopicIdea]


async def generate_custom_topic_ideas(
    mode: str,
    theme: str,
    target_audience: str = "",
    viewpoint: str = "",
    personal_case: str = "",
    content_type: str = "auto",
    research_depth: str = "quick",
    source_urls: list[str] | None = None,
    provider: str = "local",
    model: str = "",
) -> CustomTopicIdeasResult:
    """生成自定义选题建议。

    research 模式优先使用用户补充的公开来源链接；provider 可选 doubao/deepseek。
    若模型调用失败或未配置 Key，返回本地规则建议并标记 fallback。
    """
    theme = trim(clean_text(theme), 180)
    if not theme:
        raise ValueError("主题不能为空")
    mode = mode if mode in {"research", "inspiration"} else "inspiration"
    research_depth = research_depth if research_depth in {"quick", "deep"} else "quick"
    content_type = content_type if content_type in CONTENT_TYPE_LABELS else "auto"
    source_urls = [url.strip() for url in (source_urls or []) if url and url.strip()]

    references = await _collect_references(source_urls, limit=8 if research_depth == "deep" else 4)
    keywords = _keywords(theme, target_audience, viewpoint, content_type, research_depth)
    local_result = _generate_local_result(
        mode,
        theme,
        target_audience,
        viewpoint,
        personal_case,
        content_type,
        research_depth,
        keywords,
        references,
    )

    if provider == "local":
        return local_result

    try:
        client = llm_router.get_task_client("topic_ideation", provider=provider or None, model=model or None)
        raw = client.chat_json(
            _system_prompt(),
            _user_prompt(
                mode,
                theme,
                target_audience,
                viewpoint,
                personal_case,
                content_type,
                research_depth,
                keywords,
                references,
            ),
            temperature=0.55,
        )
        result = _normalize_llm_result(raw, local_result, references, keywords, mode, research_depth)
        result.research_status = "model_generated_with_manual_sources" if _has_ok_reference(references) else "model_generated_unverified"
        return result
    except Exception as exc:
        local_result.research_status = f"fallback_local: {str(exc)[:120]}"
        return local_result


async def generate_source_topic_ideas(
    source_title: str,
    source_summary: str = "",
    source_url: str = "",
    source_type: str = "manual",
    target_audience: str = "",
    content_type: str = "auto",
    provider: str = "local",
    model: str = "",
) -> CustomTopicIdeasResult:
    """基于素材库中已有 source 生成一源多题建议。"""
    theme = trim(clean_text(source_title), 180)
    if not theme:
        raise ValueError("素材标题不能为空")
    content_type = content_type if content_type in CONTENT_TYPE_LABELS else "auto"
    reference = ResearchReference(
        title=theme,
        url=source_url or "",
        summary=trim(clean_text(source_summary), 900),
        source_type=source_type or "manual",
        status="ok",
    )
    keywords = _keywords(theme, target_audience, "一源多题", content_type, "quick")
    local_result = _generate_local_result(
        "research",
        theme,
        target_audience,
        "从同一条素材拆出多个不同内容角度",
        "",
        content_type,
        "quick",
        keywords,
        [reference],
    )
    local_result.research_status = "source_library_reference"

    if provider == "local":
        return local_result

    try:
        client = llm_router.get_task_client("topic_ideation", provider=provider or None, model=model or None)
        raw = client.chat_json(
            _system_prompt(),
            _user_prompt(
                "research",
                theme,
                target_audience,
                "从同一条素材拆出多个不同内容角度",
                "",
                content_type,
                "quick",
                keywords,
                [reference],
            ),
            temperature=0.5,
        )
        result = _normalize_llm_result(raw, local_result, [reference], keywords, "research", "quick")
        result.research_status = "model_generated_from_source_library"
        return result
    except Exception as exc:
        local_result.research_status = f"fallback_source_library_local: {str(exc)[:120]}"
        return local_result


async def _collect_references(urls: list[str], limit: int) -> list[ResearchReference]:
    references: list[ResearchReference] = []
    for url in urls[:limit]:
        try:
            imported = await import_source_from_url(url)
            references.append(ResearchReference(
                title=imported.title,
                url=imported.url,
                summary=trim(imported.summary, 520),
                source_type=imported.source_type,
                status="ok",
            ))
        except Exception as exc:
            references.append(ResearchReference(
                title=url,
                url=url,
                summary=f"来源读取失败：{str(exc)[:120]}",
                source_type="other",
                status="failed",
            ))
    return references


def _generate_local_result(
    mode: str,
    theme: str,
    target_audience: str,
    viewpoint: str,
    personal_case: str,
    content_type: str,
    research_depth: str,
    keywords: list[str],
    references: list[ResearchReference],
) -> CustomTopicIdeasResult:
    audience = target_audience or "AI 新手 / 职场人"
    reference_summary = _reference_summary(references)
    base = reference_summary or clean_text(" ".join([theme, viewpoint, personal_case])) or theme
    has_ok_reference = _has_ok_reference(references)
    verification_status = "有公开来源待人工核验" if has_ok_reference else "未核验"
    source_type = "custom_research" if mode == "research" else "custom_idea"
    research_status = "manual_sources_collected" if has_ok_reference else (
        "local_keywords_only" if mode == "research" else "local_inspiration"
    )

    ideas = [
        CustomTopicIdea(
            title=trim(f"普通人怎么用 AI 处理「{theme}」？", 255),
            content_angle="教程",
            target_audience=audience,
            summary=trim(f"把「{theme}」拆成普通人能照着做的流程：准备什么资料、让 AI 做哪一步、哪里必须人工审核。{base}", 900),
            reason="教程型内容收藏价值明确，适合用步骤卡和清单卡承接。",
            risk_tip="如果涉及具体工具、数据或案例，需要保留来源并人工核验。",
            source_type=source_type,
            score=74 if has_ok_reference else 66,
            keywords=keywords[:5],
            references=references,
            verification_status=verification_status,
        ),
        CustomTopicIdea(
            title=trim(f"{theme} 最容易踩的 3 个坑", 255),
            content_angle="避坑",
            target_audience=audience,
            summary=trim(f"从新手视角整理「{theme}」里的误区、失败原因和更稳的替代做法。{base}", 900),
            reason="避坑内容更容易触发收藏和转发，也适合做成小红书多页图文。",
            risk_tip="不要为了制造焦虑而夸大风险，具体结论要标注为经验判断或来源结论。",
            source_type=source_type,
            score=78 if has_ok_reference else 69,
            keywords=keywords[:5],
            references=references,
            verification_status=verification_status,
        ),
        CustomTopicIdea(
            title=trim(f"我会怎么把「{theme}」做成一个 AI 工作流", 255),
            content_angle="案例复盘",
            target_audience=audience,
            summary=trim(f"结合自己的使用场景，把主题改造成一个输入、处理、输出、审核、复盘的工作流。{personal_case or base}", 900),
            reason="能连接账号主线，强化“普通人的 AI 提效实验室”的实践感。",
            risk_tip="如果没有真实实践，要标记为方案设计，不要写成亲测结果。",
            source_type=source_type,
            score=76 if personal_case else 64,
            keywords=keywords[:5],
            references=references,
            verification_status="观点创作 / 未核验" if not personal_case else verification_status,
        ),
        CustomTopicIdea(
            title=trim(f"别只看热度，先看「{theme}」能不能进你的流程", 255),
            content_angle="观点",
            target_audience=audience,
            summary=trim(f"围绕一个判断：工具或方法是否值得用，不看热度，先看它能不能解决真实任务。{viewpoint or base}", 900),
            reason="观点型内容有利于建立账号判断力，不只是搬运资料。",
            risk_tip="观点要保留边界，避免绝对化表达。",
            source_type=source_type,
            score=68,
            keywords=keywords[:5],
            references=references,
            verification_status=verification_status if has_ok_reference else "观点创作 / 未核验",
        ),
        CustomTopicIdea(
            title=trim(f"新手入门「{theme}」，先照着这张清单做", 255),
            content_angle="清单",
            target_audience=audience,
            summary=trim(f"整理一份入门检查清单：适合谁、准备什么、第一步怎么试、怎么判断有没有效果。{base}", 900),
            reason="清单类内容容易被收藏，适合承接低门槛人群。",
            risk_tip="清单要区分通用建议和具体事实，涉及平台规则时要人工核验。",
            source_type=source_type,
            score=70 if has_ok_reference else 63,
            keywords=keywords[:5],
            references=references,
            verification_status=verification_status,
        ),
    ]

    if content_type != "auto":
        preferred = CONTENT_TYPE_LABELS.get(content_type, "")
        ideas = sorted(ideas, key=lambda item: 0 if preferred and preferred in item.content_angle else 1)

    return CustomTopicIdeasResult(
        mode=mode,
        research_depth=research_depth,
        research_status=research_status,
        keywords=keywords,
        references=references,
        ideas=ideas[:5],
    )


def _system_prompt() -> str:
    return """你是中文互联网内容调研员和小红书选题策划。
请根据用户主题、受众、观点、案例和来源摘要，生成 5 个适合小红书图文的选题建议。
不要编造具体数据、平台热榜、亲测经历或不存在的来源。
如果没有来源，请标记为观点创作/未核验。"""


def _user_prompt(
    mode: str,
    theme: str,
    target_audience: str,
    viewpoint: str,
    personal_case: str,
    content_type: str,
    research_depth: str,
    keywords: list[str],
    references: list[ResearchReference],
) -> str:
    refs_text = "\n".join(
        f"- {ref.title} | {ref.url or '无链接'} | {ref.summary[:500]}"
        for ref in references
    ) or "无，按未核验观点创作处理。"
    return f"""模式：{mode}
调研深度：{research_depth}
主题：{theme}
目标人群：{target_audience or '未指定'}
想表达的观点：{viewpoint or '未指定'}
个人经验/案例：{personal_case or '未提供'}
偏好内容类型：{CONTENT_TYPE_LABELS.get(content_type, '自动判断')}
建议搜索关键词：{', '.join(keywords)}
已提供/已读取来源：
{refs_text}

请输出 JSON：
{{
  "keywords": ["关键词1"],
  "ideas": [
    {{
      "title": "选题标题",
      "content_angle": "教程/避坑/工具测评/案例复盘/观点/清单",
      "target_audience": "目标人群",
      "summary": "选题摘要，说明可写内容",
      "reason": "为什么值得写",
      "risk_tip": "风险和核验提醒",
      "recommended_platform": "小红书图文",
      "score": 0-100,
      "verification_status": "有公开来源待人工核验/观点创作 / 未核验"
    }}
  ]
}}"""


def _normalize_llm_result(
    raw: dict[str, Any],
    local_result: CustomTopicIdeasResult,
    references: list[ResearchReference],
    keywords: list[str],
    mode: str,
    research_depth: str,
) -> CustomTopicIdeasResult:
    raw_ideas = raw.get("ideas") if isinstance(raw.get("ideas"), list) else []
    normalized: list[CustomTopicIdea] = []
    for item in raw_ideas[:5]:
        if not isinstance(item, dict):
            continue
        title = trim(str(item.get("title") or ""), 255)
        if not title:
            continue
        normalized.append(CustomTopicIdea(
            title=title,
            content_angle=trim(str(item.get("content_angle") or "观点"), 80),
            target_audience=trim(str(item.get("target_audience") or local_result.ideas[0].target_audience), 120),
            summary=trim(str(item.get("summary") or local_result.ideas[0].summary), 900),
            reason=trim(str(item.get("reason") or "适合转成结构化图文。"), 500),
            risk_tip=trim(str(item.get("risk_tip") or "需要人工核验事实和边界。"), 500),
            recommended_platform=trim(str(item.get("recommended_platform") or "小红书图文"), 80),
            source_type="custom_research" if mode == "research" else "custom_idea",
            score=max(0, min(100, _int(item.get("score"), 65))),
            keywords=[str(k) for k in (raw.get("keywords") if isinstance(raw.get("keywords"), list) else keywords)[:6]],
            references=references,
            verification_status=trim(str(item.get("verification_status") or ("有公开来源待人工核验" if _has_ok_reference(references) else "观点创作 / 未核验")), 80),
        ))

    if not normalized:
        return local_result

    while len(normalized) < 5:
        normalized.append(local_result.ideas[len(normalized)])

    return CustomTopicIdeasResult(
        mode=mode,
        research_depth=research_depth,
        research_status="model_generated",
        keywords=[str(k) for k in (raw.get("keywords") if isinstance(raw.get("keywords"), list) else keywords)[:8]],
        references=references,
        ideas=normalized[:5],
    )


def _keywords(theme: str, target_audience: str, viewpoint: str, content_type: str, depth: str) -> list[str]:
    seeds = [
        theme,
        f"{theme} AI",
        f"{theme} 自动化",
        f"{theme} 小红书",
        f"{theme} 案例",
    ]
    if target_audience:
        seeds.append(f"{target_audience} {theme}")
    if viewpoint:
        seeds.append(trim(viewpoint, 32))
    if content_type != "auto":
        seeds.append(f"{theme} {CONTENT_TYPE_LABELS.get(content_type, '')}")
    if depth == "deep":
        seeds.extend([f"{theme} 工具", f"{theme} 避坑", f"{theme} 教程"])
    seen: set[str] = set()
    result: list[str] = []
    for item in seeds:
        value = trim(clean_text(item), 48)
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result[:8]


def _reference_summary(references: list[ResearchReference]) -> str:
    chunks = [f"{ref.title}：{ref.summary}" for ref in references if ref.status == "ok" and ref.summary]
    return trim("\n".join(chunks), 1200)


def _has_ok_reference(references: list[ResearchReference]) -> bool:
    return any(item.status == "ok" for item in references)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
