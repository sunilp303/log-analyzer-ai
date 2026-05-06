from typing import List
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_documents(
    documents: List[Document],
    chunk_size: int = 2000,
    chunk_overlap: int = 200,
) -> List[Document]:
    """
    Split documents into chunks while preserving metadata.
    Groups same-minute logs before splitting to keep temporal context together.
    """
    if not documents:
        return []

    groups = _group_by_minute(documents)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", " ", ""],
    )

    chunks: List[Document] = []
    for group_docs in groups:
        combined_text = "\n".join(d.page_content for d in group_docs)
        representative_meta = group_docs[0].metadata.copy()

        sub_chunks = splitter.split_text(combined_text)
        for i, text in enumerate(sub_chunks):
            meta = representative_meta.copy()
            meta["chunk_index"] = i
            meta["chunk_total"] = len(sub_chunks)
            chunks.append(Document(page_content=text, metadata=meta))

    return chunks


def _group_by_minute(documents: List[Document]) -> List[List[Document]]:
    """Group documents by their timestamp minute bucket."""
    buckets: dict[str, List[Document]] = {}
    ungrouped: List[Document] = []

    for doc in documents:
        ts = doc.metadata.get("timestamp", "")
        minute_key = ts[:16] if len(ts) >= 16 else ""
        if minute_key:
            buckets.setdefault(minute_key, []).append(doc)
        else:
            ungrouped.append(doc)

    result = list(buckets.values())
    if ungrouped:
        result.append(ungrouped)
    return result
