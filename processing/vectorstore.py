from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS

from config import VECTORSTORE_PATH
from llm.providers import get_embeddings
from processing.chunker import chunk_documents


def build_vectorstore(
    documents: List[Document],
    chunk: bool = True,
) -> FAISS:
    """Embed documents and return an in-memory FAISS vectorstore."""
    if chunk:
        documents = chunk_documents(documents)

    if not documents:
        raise ValueError("No documents to index after chunking.")

    embeddings = get_embeddings()
    return FAISS.from_documents(documents, embeddings)


def save_vectorstore(vs: FAISS, path: str = VECTORSTORE_PATH) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    vs.save_local(path)


def load_vectorstore(path: str = VECTORSTORE_PATH) -> Optional[FAISS]:
    if not Path(path).exists():
        return None
    embeddings = get_embeddings()
    return FAISS.load_local(path, embeddings, allow_dangerous_deserialization=True)


def add_documents(vs: FAISS, documents: List[Document], chunk: bool = True) -> FAISS:
    """Add new documents to an existing vectorstore."""
    if chunk:
        documents = chunk_documents(documents)
    if not documents:
        return vs
    vs.add_documents(documents)
    return vs
