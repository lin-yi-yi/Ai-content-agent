"""Optional LangChain/LangGraph adapters.

The app can boot without these packages. When installed, v0.4 RAG indexing uses
LangChain's document and splitter primitives while keeping the same data boundary.
"""
from dataclasses import dataclass
from typing import Any


try:  # pragma: no cover - depends on optional runtime dependency
    from langchain_core.documents import Document
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except Exception:  # pragma: no cover
    Document = None
    RecursiveCharacterTextSplitter = None

try:  # pragma: no cover - depends on optional runtime dependency
    from langgraph.graph import StateGraph
except Exception:  # pragma: no cover
    StateGraph = None


@dataclass
class ChunkPayload:
    content: str
    chunk_index: int
    start_index: int | None
    metadata: dict[str, Any]


def framework_status() -> dict:
    return {
        "langchain_available": Document is not None and RecursiveCharacterTextSplitter is not None,
        "langgraph_available": StateGraph is not None,
        "langchain_usage": "RAG document splitting and future tool wrappers",
        "langgraph_usage": "Optional workflow engine for branching Agent flows",
    }


def split_document(
    text: str,
    metadata: dict[str, Any],
    chunk_size: int = 900,
    chunk_overlap: int = 140,
) -> list[ChunkPayload]:
    cleaned = "\n".join(line.strip() for line in (text or "").replace("\r", "\n").split("\n") if line.strip())
    if not cleaned:
        return []

    if Document is not None and RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            add_start_index=True,
            separators=["\n\n", "\n", "。", "；", ";", "，", ",", " ", ""],
        )
        docs = splitter.split_documents([Document(page_content=cleaned, metadata=metadata)])
        return [
            ChunkPayload(
                content=doc.page_content,
                chunk_index=index,
                start_index=doc.metadata.get("start_index"),
                metadata={k: v for k, v in doc.metadata.items() if k != "start_index"},
            )
            for index, doc in enumerate(docs)
            if doc.page_content.strip()
        ]

    return _fallback_split(cleaned, metadata, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _fallback_split(text: str, metadata: dict[str, Any], chunk_size: int, chunk_overlap: int) -> list[ChunkPayload]:
    chunks: list[ChunkPayload] = []
    cursor = 0
    index = 0
    step = max(1, chunk_size - chunk_overlap)
    while cursor < len(text):
        end = min(len(text), cursor + chunk_size)
        chunk = text[cursor:end].strip()
        if chunk:
            chunks.append(ChunkPayload(content=chunk, chunk_index=index, start_index=cursor, metadata=metadata))
            index += 1
        if end >= len(text):
            break
        cursor += step
    return chunks
