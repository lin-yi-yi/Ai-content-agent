"""RAG indexing, retrieval, and answer helpers for v0.4."""
from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from sqlalchemy.orm import Session

from app.agent_core.boundaries import (
    WorkspaceContext,
    get_knowledge_base_or_default,
    require_capability,
)
from app.agent_core.langchain_adapter import split_document
from app.llm.router import router as llm_router
from app.models.knowledge_base import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.models.source import Source


LOCAL_EMBEDDING_DIM = 128
LOCAL_EMBEDDING_MODEL = "local-hash-embedding-v1"


@dataclass
class SearchHit:
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    workspace_id: int
    source_id: int | None
    title: str
    source_uri: str
    content: str
    score: float
    chunk_index: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["score"] = round(self.score, 4)
        return data


def index_source(
    source_id: int,
    db: Session,
    context: WorkspaceContext,
    knowledge_base_id: int | None = None,
    ingestion_profile: str = "default",
) -> dict:
    require_capability("source_index", "index")
    knowledge_base = get_knowledge_base_or_default(db, context, knowledge_base_id)
    source = db.query(Source).filter(Source.id == source_id).first()
    if not source:
        raise ValueError("素材不存在")

    raw_content = (source.raw_content or source.summary or "").strip()
    if len(raw_content) < 40:
        raise ValueError("素材内容过短，无法入库检索")

    content_hash = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    _delete_existing_source_documents(db, context, knowledge_base, source.id)

    document = KnowledgeDocument(
        workspace_id=context.workspace_id,
        knowledge_base_id=knowledge_base.id,
        source_id=source.id,
        title=source.title[:255],
        source_uri=source.url or "",
        content_hash=content_hash,
        status="indexed",
        ingestion_profile=ingestion_profile or "default",
        metadata_json={
            "source_type": source.source_type,
            "summary": source.summary or "",
            "isolation": "workspace_scoped",
        },
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    chunks = split_document(
        raw_content,
        metadata={
            "source_id": source.id,
            "source_type": source.source_type,
            "title": source.title,
            "source_uri": source.url or "",
            "knowledge_base_id": knowledge_base.id,
            "workspace_id": context.workspace_id,
        },
    )
    for item in chunks:
        embedding = _embed_text(item.content)
        db.add(KnowledgeChunk(
            workspace_id=context.workspace_id,
            knowledge_base_id=knowledge_base.id,
            document_id=document.id,
            chunk_index=item.chunk_index,
            content=item.content,
            token_count=_approx_token_count(item.content),
            start_index=item.start_index,
            metadata_json=item.metadata,
            embedding_provider="local_hash",
            embedding_model=LOCAL_EMBEDDING_MODEL,
            embedding_hash=hashlib.sha256(item.content.encode("utf-8")).hexdigest(),
            embedding_dim=LOCAL_EMBEDDING_DIM,
            embedding_json=embedding,
        ))
    db.commit()

    return {
        "workspace_id": context.workspace_id,
        "knowledge_base_id": knowledge_base.id,
        "document_id": document.id,
        "source_id": source.id,
        "title": source.title,
        "chunk_count": len(chunks),
        "content_hash": content_hash,
        "ingestion_profile": ingestion_profile or "default",
    }


def source_index_status(
    source_id: int,
    db: Session,
    context: WorkspaceContext,
    knowledge_base_id: int | None = None,
) -> dict:
    knowledge_base = get_knowledge_base_or_default(db, context, knowledge_base_id)
    documents = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.workspace_id == context.workspace_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base.id,
            KnowledgeDocument.source_id == source_id,
        )
        .order_by(KnowledgeDocument.updated_at.desc())
        .all()
    )
    if not documents:
        return {
            "indexed": False,
            "workspace_id": context.workspace_id,
            "knowledge_base_id": knowledge_base.id,
            "document_count": 0,
            "chunk_count": 0,
            "last_document_id": None,
            "updated_at": None,
        }
    document_ids = [item.id for item in documents]
    chunk_count = (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.workspace_id == context.workspace_id,
            KnowledgeChunk.knowledge_base_id == knowledge_base.id,
            KnowledgeChunk.document_id.in_(document_ids),
        )
        .count()
    )
    latest = documents[0]
    return {
        "indexed": chunk_count > 0,
        "workspace_id": context.workspace_id,
        "knowledge_base_id": knowledge_base.id,
        "document_count": len(documents),
        "chunk_count": chunk_count,
        "last_document_id": latest.id,
        "updated_at": latest.updated_at.isoformat() if latest.updated_at else None,
    }


def search_knowledge(
    query: str,
    db: Session,
    context: WorkspaceContext,
    knowledge_base_id: int | None = None,
    top_k: int = 5,
    min_score: float = 0.08,
) -> list[SearchHit]:
    require_capability("rag_retrieve", "search")
    query = " ".join((query or "").split())
    if not query:
        raise ValueError("检索问题不能为空")
    knowledge_base = get_knowledge_base_or_default(db, context, knowledge_base_id)
    chunks = (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.workspace_id == context.workspace_id,
            KnowledgeChunk.knowledge_base_id == knowledge_base.id,
        )
        .order_by(KnowledgeChunk.created_at.desc())
        .limit(1200)
        .all()
    )
    if not chunks:
        return []

    doc_ids = {chunk.document_id for chunk in chunks}
    documents = {
        doc.id: doc
        for doc in db.query(KnowledgeDocument).filter(
            KnowledgeDocument.workspace_id == context.workspace_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base.id,
            KnowledgeDocument.id.in_(doc_ids),
        ).all()
    }
    hits = []
    query_terms = _terms(query)
    query_embedding = _embed_text(query)
    for chunk in chunks:
        lexical_score = _lexical_score(query, query_terms, chunk.content)
        vector_score = _vector_score(query_embedding, chunk.embedding_json, chunk.content)
        score = _hybrid_score(lexical_score, vector_score)
        if score < min_score:
            continue
        document = documents.get(chunk.document_id)
        if not document:
            continue
        metadata = dict(chunk.metadata_json or {})
        metadata["scores"] = {
            "hybrid": round(score, 4),
            "lexical": round(lexical_score, 4),
            "vector": round(vector_score, 4),
            "strategy": "local_hybrid_v1",
        }
        hits.append(SearchHit(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            knowledge_base_id=chunk.knowledge_base_id,
            workspace_id=chunk.workspace_id,
            source_id=document.source_id,
            title=document.title,
            source_uri=document.source_uri or "",
            content=chunk.content,
            score=score,
            chunk_index=chunk.chunk_index,
            metadata=metadata,
        ))
    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:max(1, min(top_k, 12))]


def answer_question(
    question: str,
    db: Session,
    context: WorkspaceContext,
    knowledge_base_id: int | None = None,
    provider: str = "local",
    model: str = "",
    top_k: int = 5,
) -> dict:
    hits = search_knowledge(
        query=question,
        db=db,
        context=context,
        knowledge_base_id=knowledge_base_id,
        top_k=top_k,
        min_score=0.08,
    )
    coverage = _coverage(hits)
    if not _has_enough_evidence(hits):
        return {
            "answer": "当前知识库证据不足，不能可靠回答这个问题。请先导入或索引更相关的素材。",
            "refused": True,
            "refusal_reason": "insufficient_evidence",
            "coverage": coverage,
            "citations": [hit.to_dict() for hit in hits],
        }

    if provider == "local":
        answer = _local_answer(question, hits)
    else:
        client = llm_router.get_task_client("rag_answer", provider=provider or None, model=model or None)
        answer = client.chat(
            "你是严格基于证据回答的 RAG 助手。只能使用给定证据，不确定时必须说明不足。",
            _answer_prompt(question, hits),
            temperature=0.2,
            max_tokens=1200,
        )

    return {
        "answer": answer,
        "refused": False,
        "refusal_reason": "",
        "coverage": coverage,
        "citations": [hit.to_dict() for hit in hits],
    }


def _delete_existing_source_documents(
    db: Session,
    context: WorkspaceContext,
    knowledge_base: KnowledgeBase,
    source_id: int,
) -> None:
    documents = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.workspace_id == context.workspace_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base.id,
            KnowledgeDocument.source_id == source_id,
        )
        .all()
    )
    if not documents:
        return
    document_ids = [item.id for item in documents]
    db.query(KnowledgeChunk).filter(
        KnowledgeChunk.workspace_id == context.workspace_id,
        KnowledgeChunk.knowledge_base_id == knowledge_base.id,
        KnowledgeChunk.document_id.in_(document_ids),
    ).delete(synchronize_session=False)
    for document in documents:
        db.delete(document)
    db.commit()


def _terms(text: str) -> set[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_]{2,}", lowered)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    cjk_bigrams = ["".join(cjk_chars[index:index + 2]) for index in range(max(0, len(cjk_chars) - 1))]
    cjk_trigrams = ["".join(cjk_chars[index:index + 3]) for index in range(max(0, len(cjk_chars) - 2))]
    return set(latin + cjk_bigrams + cjk_trigrams)


def _lexical_score(query: str, query_terms: set[str], content: str) -> float:
    content_lower = content.lower()
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term and term.lower() in content_lower)
    overlap = hits / len(query_terms)
    phrase_bonus = 0.35 if query.lower() in content_lower else 0.0
    density_bonus = min(0.15, hits / max(1, len(content)) * 20)
    return min(1.0, overlap + phrase_bonus + density_bonus)


def _vector_score(query_embedding: list[float], chunk_embedding: Any, content: str) -> float:
    vector = chunk_embedding if isinstance(chunk_embedding, list) else _embed_text(content)
    return max(0.0, _cosine(query_embedding, vector))


def _hybrid_score(lexical_score: float, vector_score: float) -> float:
    if lexical_score <= 0 and vector_score < 0.18:
        return 0.0
    return min(1.0, lexical_score * 0.68 + vector_score * 0.32)


def _embed_text(text: str, dim: int = LOCAL_EMBEDDING_DIM) -> list[float]:
    vector = [0.0] * dim
    terms = _embedding_terms(text)
    if not terms:
        return vector
    for term in terms:
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.4 if len(term) >= 3 else 1.0
        vector[index] += sign * weight
    norm = sum(value * value for value in vector) ** 0.5
    if norm <= 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _embedding_terms(text: str) -> list[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9_]{2,}", lowered)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", text)
    cjk_bigrams = ["".join(cjk_chars[index:index + 2]) for index in range(max(0, len(cjk_chars) - 1))]
    cjk_trigrams = ["".join(cjk_chars[index:index + 3]) for index in range(max(0, len(cjk_chars) - 2))]
    return latin + cjk_bigrams + cjk_trigrams


def _cosine(left: list[float], right: Any) -> float:
    if not isinstance(right, list) or not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size == 0:
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for index in range(size):
        try:
            left_value = float(left[index])
            right_value = float(right[index])
        except (TypeError, ValueError):
            continue
        dot += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / ((left_norm ** 0.5) * (right_norm ** 0.5))


def _coverage(hits: list[SearchHit]) -> dict:
    if not hits:
        return {"top_score": 0, "evidence_count": 0, "distinct_documents": 0, "status": "insufficient"}
    top_score = max(hit.score for hit in hits)
    distinct_docs = len({hit.document_id for hit in hits})
    return {
        "top_score": round(top_score, 4),
        "evidence_count": len(hits),
        "distinct_documents": distinct_docs,
        "status": "sufficient" if _has_enough_evidence(hits) else "weak",
    }


def _has_enough_evidence(hits: list[SearchHit]) -> bool:
    if not hits:
        return False
    return hits[0].score >= 0.18 or (len(hits) >= 2 and hits[0].score >= 0.12)


def _local_answer(question: str, hits: list[SearchHit]) -> str:
    lines = [
        f"基于当前知识库，问题「{question}」可以先这样回答：",
        "",
    ]
    for index, hit in enumerate(hits[:3], start=1):
        excerpt = hit.content[:220].replace("\n", " ")
        lines.append(f"{index}. {excerpt}（来源：{hit.title}，chunk #{hit.chunk_id}）")
    lines.append("")
    lines.append("以上是本地 RAG 摘要，发布或引用前仍需要人工核验来源。")
    return "\n".join(lines)


def _answer_prompt(question: str, hits: list[SearchHit]) -> str:
    evidence = "\n\n".join(
        f"[chunk:{hit.chunk_id}] 标题：{hit.title}\n来源：{hit.source_uri or '无'}\n内容：{hit.content[:900]}"
        for hit in hits
    )
    return f"""问题：{question}

证据：
{evidence}

要求：
1. 只基于证据回答。
2. 每个关键结论后标注 chunk id，例如 [chunk:123]。
3. 如果证据只能支持部分回答，请明确边界。
"""


def _approx_token_count(text: str) -> int:
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin = len(re.findall(r"[A-Za-z0-9_]+", text))
    return max(1, cjk + latin)
