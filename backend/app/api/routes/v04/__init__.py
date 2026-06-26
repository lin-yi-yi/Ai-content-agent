"""v0.4 Agent foundation API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent_core.boundaries import (
    get_default_workspace,
    get_knowledge_base_or_default,
    list_capabilities,
    workspace_context,
)
from app.agent_core.langchain_adapter import framework_status
from app.agent_core.rag_service import answer_question, index_source, search_knowledge
from app.agent_core.tools import execute_tool, list_tools
from app.db.session import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.workspace import Workspace

router = APIRouter(prefix="/v04", tags=["v0.4-agent-foundation"])


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    workspace_id: int | None = None
    purpose: str = ""
    boundary_notes: str = ""


class RagIndexSourceRequest(BaseModel):
    source_id: int
    workspace_id: int | None = None
    knowledge_base_id: int | None = None
    ingestion_profile: str = "default"


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    workspace_id: int | None = None
    knowledge_base_id: int | None = None
    top_k: int = Field(5, ge=1, le=12)
    min_score: float = Field(0.08, ge=0, le=1)


class RagAnswerRequest(RagSearchRequest):
    provider: str = "local"
    model: str = ""


class ToolExecuteRequest(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=120)
    workspace_id: int | None = None
    knowledge_base_id: int | None = None
    arguments: dict = Field(default_factory=dict)


@router.get("/architecture")
def architecture(db: Session = Depends(get_db)):
    workspace = get_default_workspace(db)
    knowledge_base = get_knowledge_base_or_default(db, workspace_context(db, workspace.id))
    return {
        "version": "v0.4-foundation",
        "product_boundary": {
            "product": "AI 内容增长 Agent",
            "primary_scenario": "把素材、项目和实践经验转成可审核的内容资产。",
            "in_scope": [
                "素材库 RAG 检索",
                "内容生成前的证据引用",
                "Agent 步骤记录和人工审核",
                "多模型 OpenAI-compatible 调用",
            ],
            "out_of_scope": [
                "自动发布到外部平台",
                "读取本机任意文件",
                "访问浏览器 Cookie、账号密码或外部密钥",
                "跨 workspace 混用知识库数据",
            ],
        },
        "data_isolation": {
            "default_workspace_id": workspace.id,
            "default_knowledge_base_id": knowledge_base.id,
            "rule": "v0.4 RAG 数据必须带 workspace_id 和 knowledge_base_id；检索和回答只能在请求指定边界内执行。",
            "tables": ["workspaces", "knowledge_bases", "knowledge_documents", "knowledge_chunks"],
            "legacy_tables": "sources/topics/drafts/cards 暂不强改 schema；RAG 通过 source_id 只读接入素材库。",
        },
        "retrieval_strategy": {
            "name": "local_hybrid_v1",
            "embedding_provider": "local_hash",
            "embedding_model": "local-hash-embedding-v1",
            "embedding_dim": 128,
            "scoring": "lexical overlap + local hash vector cosine",
            "limitation": "当前是离线开发检索底座，不等同于生产级外部 embedding/vector database。",
        },
        "capabilities": list_capabilities(),
        "tools": list_tools(),
        "framework_status": framework_status(),
        "workflow_boundary": {
            "current": "现有 content_growth_agent 保持线性 v0.3 流程。",
            "v04_extension": "新增 RAG 和工具白名单作为能力层；LangGraph 只作为后续分支工作流入口。",
            "async_boundary": "当前仍使用 FastAPI BackgroundTasks；真正任务队列建议下一阶段引入 Redis + Celery/RQ/ARQ。",
        },
    }


@router.get("/workspaces")
def list_workspaces(db: Session = Depends(get_db)):
    items = db.query(Workspace).order_by(Workspace.id).all()
    return [{
        "id": item.id,
        "name": item.name,
        "slug": item.slug,
        "description": item.description,
        "data_boundary": item.data_boundary,
        "is_default": item.is_default,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    } for item in items]


@router.get("/knowledge-bases")
def list_knowledge_bases(
    workspace_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        context = workspace_context(db, workspace_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    items = (
        db.query(KnowledgeBase)
        .filter(KnowledgeBase.workspace_id == context.workspace_id)
        .order_by(KnowledgeBase.id)
        .all()
    )
    return [_knowledge_base_out(item) for item in items]


@router.post("/knowledge-bases", status_code=201)
def create_knowledge_base(body: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    try:
        context = workspace_context(db, body.workspace_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    item = KnowledgeBase(
        workspace_id=context.workspace_id,
        name=body.name.strip(),
        purpose=body.purpose.strip() or None,
        boundary_notes=body.boundary_notes.strip() or "仅允许当前 workspace 内检索。",
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _knowledge_base_out(item)


@router.post("/rag/index-source", status_code=201)
def index_source_endpoint(body: RagIndexSourceRequest, db: Session = Depends(get_db)):
    try:
        context = workspace_context(db, body.workspace_id)
        return index_source(
            source_id=body.source_id,
            db=db,
            context=context,
            knowledge_base_id=body.knowledge_base_id,
            ingestion_profile=body.ingestion_profile,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/rag/search")
def search_endpoint(body: RagSearchRequest, db: Session = Depends(get_db)):
    try:
        context = workspace_context(db, body.workspace_id)
        hits = search_knowledge(
            query=body.query,
            db=db,
            context=context,
            knowledge_base_id=body.knowledge_base_id,
            top_k=body.top_k,
            min_score=body.min_score,
        )
        return {"items": [item.to_dict() for item in hits], "total": len(hits)}
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/rag/answer")
def answer_endpoint(body: RagAnswerRequest, db: Session = Depends(get_db)):
    try:
        context = workspace_context(db, body.workspace_id)
        return answer_question(
            question=body.query,
            db=db,
            context=context,
            knowledge_base_id=body.knowledge_base_id,
            provider=body.provider,
            model=body.model,
            top_k=body.top_k,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/tools")
def tools_endpoint():
    tools = list_tools()
    return {"items": tools, "total": len(tools)}


@router.post("/tools/execute")
def execute_tool_endpoint(body: ToolExecuteRequest, db: Session = Depends(get_db)):
    try:
        context = workspace_context(db, body.workspace_id)
        return execute_tool(
            tool_name=body.tool_name,
            arguments=body.arguments,
            db=db,
            context=context,
            knowledge_base_id=body.knowledge_base_id,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _knowledge_base_out(item: KnowledgeBase) -> dict:
    return {
        "id": item.id,
        "workspace_id": item.workspace_id,
        "name": item.name,
        "purpose": item.purpose,
        "boundary_notes": item.boundary_notes,
        "status": item.status,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
