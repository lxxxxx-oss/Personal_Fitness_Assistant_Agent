"""Run a real Milvus collection/index/upsert/search smoke test.

The script uses a deterministic local encoder so it validates Milvus itself
without downloading the project's Sentence-Transformer model.
"""

import argparse
import hashlib
import json
import os
import sys

import numpy as np

from app.tools.retriever import MilvusRetriever


class DeterministicEncoder:
    """Small deterministic encoder used only by the Milvus smoke test."""

    def __init__(self, dimension: int = 16):
        self.dimension = dimension

    def encode(self, texts, normalize_embeddings=False):
        if isinstance(texts, str):
            texts = [texts]
        vectors = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
            vector = np.resize(raw, self.dimension) + 1.0
            vectors.append(vector)
        matrix = np.asarray(vectors, dtype=np.float32)
        if normalize_embeddings:
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms < 1e-8] = 1.0
            matrix = matrix / norms
        return matrix


def run_smoke(uri: str, collection: str, token: str = "", keep: bool = False) -> dict:
    retriever = MilvusRetriever(
        uri=uri,
        token=token,
        collection_name=collection,
        embedding_model="smoke-deterministic",
        index_type="IVF_FLAT",
        metric_type="COSINE",
        nlist=8,
        nprobe=4,
        timeout_seconds=10.0,
    )
    retriever._encoder = DeterministicEncoder()
    documents = [
        "深蹲训练需要保持核心稳定。",
        "减脂期间需要保证蛋白质摄入。",
    ]

    try:
        cleared = retriever.clear()
        if not cleared.ok:
            raise RuntimeError(cleared.error_message)
        added = retriever.add_documents(
            documents,
            sources=["motion.txt", "nutrition.txt"],
        )
        if not added.ok:
            raise RuntimeError(added.error_message)
        searched = retriever.search(documents[0], top_k=2, threshold=0.0)
        if not searched.ok:
            raise RuntimeError(searched.error_message)
        if not searched.data or searched.data[0]["content"] != documents[0]:
            raise RuntimeError(f"Unexpected Milvus search results: {searched.data}")
        return {
            "status": "ok",
            "uri": uri,
            "collection": collection,
            "upserted": added.data["upserted"],
            "row_count": retriever.document_count,
            "top_hit": searched.data[0],
            "index_type": searched.meta["index_type"],
            "metric_type": searched.meta["metric_type"],
        }
    finally:
        if not keep:
            retriever.clear()
        retriever.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--uri",
        default=os.getenv("MILVUS_URI", "http://127.0.0.1:19530"),
    )
    parser.add_argument(
        "--collection",
        default="fitness_milvus_smoke",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MILVUS_TOKEN", ""),
    )
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    try:
        result = run_smoke(
            uri=args.uri,
            collection=args.collection,
            token=args.token,
            keep=args.keep,
        )
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
