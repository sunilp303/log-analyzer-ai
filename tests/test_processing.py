"""Tests for chunker and vectorstore building."""
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document


class TestChunker:
    def test_basic_chunking(self, sample_documents):
        from processing.chunker import chunk_documents

        chunks = chunk_documents(sample_documents)
        assert len(chunks) > 0
        for chunk in chunks:
            assert isinstance(chunk, Document)
            assert chunk.page_content.strip()

    def test_empty_input(self):
        from processing.chunker import chunk_documents

        assert chunk_documents([]) == []

    def test_metadata_preserved(self, sample_documents):
        from processing.chunker import chunk_documents

        chunks = chunk_documents(sample_documents)
        for chunk in chunks:
            assert "source" in chunk.metadata
            assert "timestamp" in chunk.metadata
            assert "service" in chunk.metadata

    def test_chunk_index_added(self, sample_documents):
        from processing.chunker import chunk_documents

        chunks = chunk_documents(sample_documents, chunk_size=100, chunk_overlap=10)
        for chunk in chunks:
            assert "chunk_index" in chunk.metadata
            assert "chunk_total" in chunk.metadata

    def test_groups_by_minute(self):
        from processing.chunker import _group_by_minute

        docs = [
            Document(page_content="a", metadata={"timestamp": "2026-05-06T13:45:10Z"}),
            Document(page_content="b", metadata={"timestamp": "2026-05-06T13:45:30Z"}),
            Document(page_content="c", metadata={"timestamp": "2026-05-06T13:46:05Z"}),
        ]
        groups = _group_by_minute(docs)
        assert len(groups) == 2
        assert len(groups[0]) == 2
        assert len(groups[1]) == 1

    def test_no_timestamp_docs_grouped_together(self):
        from processing.chunker import _group_by_minute

        docs = [
            Document(page_content="a", metadata={}),
            Document(page_content="b", metadata={"timestamp": ""}),
        ]
        groups = _group_by_minute(docs)
        assert len(groups) == 1
        assert len(groups[0]) == 2


class TestVectorstore:
    def _make_fake_embeddings(self):
        """Return a mock embeddings object that produces predictable vectors."""
        mock_emb = MagicMock()
        mock_emb.embed_documents.side_effect = lambda texts: [[float(i)] * 8 for i in range(len(texts))]
        mock_emb.embed_query.return_value = [0.5] * 8
        return mock_emb

    def test_build_vectorstore(self, sample_documents):
        from processing.vectorstore import build_vectorstore
        from langchain_community.vectorstores import FAISS

        with patch("processing.vectorstore.get_embeddings", return_value=self._make_fake_embeddings()):
            with patch("processing.chunker.chunk_documents", return_value=sample_documents):
                vs = build_vectorstore(sample_documents, chunk=False)

        assert isinstance(vs, FAISS)

    def test_build_vectorstore_empty_raises(self):
        from processing.vectorstore import build_vectorstore

        with pytest.raises(ValueError, match="No documents"):
            with patch("processing.vectorstore.get_embeddings", return_value=self._make_fake_embeddings()):
                build_vectorstore([])

    def test_save_and_load_vectorstore(self, tmp_path, sample_documents):
        from processing.vectorstore import build_vectorstore, save_vectorstore, load_vectorstore
        from langchain_community.vectorstores import FAISS

        fake_emb = self._make_fake_embeddings()

        with patch("processing.vectorstore.get_embeddings", return_value=fake_emb):
            vs = build_vectorstore(sample_documents, chunk=False)
            save_vectorstore(vs, str(tmp_path))
            loaded = load_vectorstore(str(tmp_path))

        assert loaded is not None
        assert isinstance(loaded, FAISS)

    def test_load_nonexistent_returns_none(self, tmp_path):
        from processing.vectorstore import load_vectorstore

        result = load_vectorstore(str(tmp_path / "does_not_exist"))
        assert result is None
