"""Smoke test for v0.4 RAG-backed Agent Run.

Prerequisites:
- Backend is running on http://127.0.0.1:8000
- DATABASE_URL points to the local development database

The script creates temporary source data, indexes it into the default knowledge
base, checks the allowlisted tool API, starts an Agent Run with RAG enabled,
checks the retrieve_context step, checks insufficient-evidence refusal, and
cleans up temporary records.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.agent_core.boundaries import workspace_context  # noqa: E402
from app.agent_core.rag_service import answer_question  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.agent_run import AgentRun, AgentStep  # noqa: E402
from app.models.card import Card  # noqa: E402
from app.models.draft import Draft  # noqa: E402
from app.models.knowledge_base import KnowledgeChunk, KnowledgeDocument  # noqa: E402
from app.models.source import Source  # noqa: E402
from app.models.topic import Topic  # noqa: E402


SAMPLE_SOURCE = """\
LangChain 在内容增长 Agent 里应该作为工具和文档处理层，而不是替换全部业务服务。
RAG 的核心价值是把已入库素材变成可引用证据，所有检索必须限制在 workspace_id 和 knowledge_base_id 内。
当知识库证据不足时，Agent 应该提示人工补来源，或把输出降级为观点草稿。
LangGraph 更适合在后续出现分支、重试、人工确认时作为工作流编排层。
"""


def request_json(base_url: str, path: str, body: dict | None = None, timeout: int = 30) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    if body is None:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.load(resp)
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def cleanup(db, source_id: int | None, run_id: int | None) -> None:
    db.rollback()
    db.expire_all()
    if run_id:
        run = db.query(AgentRun).filter(AgentRun.id == run_id).first()
        if run:
            if run.draft_id:
                db.query(Card).filter(Card.draft_id == run.draft_id).delete(synchronize_session=False)
                db.query(Draft).filter(Draft.id == run.draft_id).delete(synchronize_session=False)
            if run.selected_topic_id:
                topic = db.query(Topic).filter(Topic.id == run.selected_topic_id).first()
                topic_source_id = topic.source_id if topic else None
                db.query(Topic).filter(Topic.id == run.selected_topic_id).delete(synchronize_session=False)
                if topic_source_id:
                    db.query(Source).filter(Source.id == topic_source_id).delete(synchronize_session=False)
            db.query(AgentStep).filter(AgentStep.run_id == run_id).delete(synchronize_session=False)
            db.query(AgentRun).filter(AgentRun.id == run_id).delete(synchronize_session=False)

    if source_id:
        docs = db.query(KnowledgeDocument).filter(KnowledgeDocument.source_id == source_id).all()
        doc_ids = [item.id for item in docs]
        if doc_ids:
            db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id.in_(doc_ids)).delete(synchronize_session=False)
            db.query(KnowledgeDocument).filter(KnowledgeDocument.id.in_(doc_ids)).delete(synchronize_session=False)
        db.query(Source).filter(Source.id == source_id).delete(synchronize_session=False)
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-url", default="http://127.0.0.1:8000")
    parser.add_argument("--poll-seconds", type=int, default=45)
    args = parser.parse_args()

    db = SessionLocal()
    source_id: int | None = None
    run_id: int | None = None
    try:
        request_json(args.backend_url, "/health")

        source = Source(
            source_type="manual",
            title="__v04_smoke_rag_agent__",
            url="",
            raw_content=SAMPLE_SOURCE,
            summary=SAMPLE_SOURCE[:220],
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        source_id = source.id

        index_result = request_json(args.backend_url, "/api/v04/rag/index-source", {"source_id": source_id})
        tools = request_json(args.backend_url, "/api/v04/tools")
        tool_names = {item["name"] for item in tools.get("items") or []}
        required_tools = {"rag.search", "rag.answer", "source.index"}
        if not required_tools.issubset(tool_names):
            raise RuntimeError(f"Missing v0.4 tools: {sorted(required_tools - tool_names)}")

        tool_search = request_json(args.backend_url, "/api/v04/tools/execute", {
            "tool_name": "rag.search",
            "knowledge_base_id": index_result["knowledge_base_id"],
            "arguments": {
                "query": "workspace_id knowledge_base_id RAG 检索边界",
                "top_k": 3,
            },
        })
        tool_items = ((tool_search.get("output") or {}).get("items") or [])
        if not tool_items:
            raise RuntimeError("Allowlisted rag.search tool did not return evidence")

        run = request_json(args.backend_url, "/api/agent-runs", {
            "goal": "LangChain、RAG 和 LangGraph 应该怎么接进内容增长 Agent？",
            "mode": "inspiration",
            "research_depth": "quick",
            "target_audience": "AI 新手 / 自媒体人",
            "viewpoint": "先把 RAG 做成证据层，再考虑 LangGraph 编排",
            "content_type": "tutorial",
            "provider": "local",
            "auto_score": True,
            "use_rag": True,
            "knowledge_base_id": index_result["knowledge_base_id"],
            "rag_top_k": 5,
        })
        run_id = run["id"]

        detail = run
        for _ in range(args.poll_seconds):
            detail = request_json(args.backend_url, f"/api/agent-runs/{run_id}")
            if detail["status"] not in {"pending", "running"}:
                break
            time.sleep(1)

        rag_context = (detail.get("result_json") or {}).get("rag_context") or {}
        steps = {item["key"]: item["status"] for item in detail.get("steps") or []}
        if detail["status"] != "completed":
            raise RuntimeError(f"Agent run did not complete: {detail.get('error_message')}")
        if steps.get("retrieve_context") != "completed":
            raise RuntimeError(f"retrieve_context step failed: {steps}")
        if not rag_context.get("hits"):
            raise RuntimeError("RAG context did not include evidence hits")

        context = workspace_context(db)
        refusal = answer_question(
            "医疗投资收益保证",
            db,
            context,
            knowledge_base_id=index_result["knowledge_base_id"],
            provider="local",
        )
        if not refusal.get("refused"):
            raise RuntimeError("Out-of-domain question was not refused")

        print(json.dumps({
            "ok": True,
            "run_id": run_id,
            "retrieve_context": steps.get("retrieve_context"),
            "evidence_status": rag_context.get("evidence_status"),
            "hit_count": len(rag_context.get("hits") or []),
            "chunk_count": index_result["chunk_count"],
            "embedding_model": "local-hash-embedding-v1",
            "tool_count": tools.get("total"),
            "tool_search_hits": len(tool_items),
            "refusal_reason": refusal.get("refusal_reason"),
        }, ensure_ascii=False, indent=2))
        return 0
    finally:
        cleanup(db, source_id, run_id)
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
