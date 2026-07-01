"""Optional integration test against a real Milvus service."""

import os
import uuid

import pytest

from app.tools.retriever import MilvusRetriever
from scripts.smoke_milvus import DeterministicEncoder


@pytest.mark.integration
def test_real_milvus_collection_upsert_and_search():
    uri = os.getenv("MILVUS_TEST_URI")
    if not uri:
        pytest.skip("Set MILVUS_TEST_URI to run the real Milvus integration test")
    pytest.importorskip("pymilvus")

    collection = f"fitness_test_{uuid.uuid4().hex}"
    retriever = MilvusRetriever(
        uri=uri,
        token=os.getenv("MILVUS_TEST_TOKEN", ""),
        collection_name=collection,
        nlist=8,
        nprobe=4,
        timeout_seconds=10.0,
    )
    retriever._encoder = DeterministicEncoder()
    document = "深蹲训练需要保持核心稳定。"

    try:
        added = retriever.add_documents([document], sources=["motion.txt"])
        assert added.ok, added.error_message
        searched = retriever.search(document, top_k=1, threshold=0.0)
        assert searched.ok, searched.error_message
        assert searched.data[0]["content"] == document
        assert searched.data[0]["source"] == "motion.txt"
        assert retriever.document_count == 1
    finally:
        retriever.clear()
        retriever.close()
