"""Offline smoke test for SQLite persistence and FAISS index reconstruction."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.tools.retriever import SQLiteFaissRetriever


class DeterministicEncoder:
    """Avoid model downloads while validating the storage/search lifecycle."""

    def encode(self, texts, normalize_embeddings=True):
        rows = []
        for text in texts:
            value = str(text)
            vector = np.asarray(
                [
                    3.0 if "深蹲" in value or "腿部" in value else 0.1,
                    3.0 if "蛋白" in value or "饮食" in value else 0.1,
                    1.0,
                    0.5,
                ],
                dtype=np.float32,
            )
            if normalize_embeddings:
                vector = vector / np.linalg.norm(vector)
            rows.append(vector)
        return np.asarray(rows, dtype=np.float32)


def run(db_path: Path) -> None:
    encoder = DeterministicEncoder()
    retriever = SQLiteFaissRetriever(
        db_path=str(db_path), embedding_model="offline-smoke-v1", encoder=encoder
    )
    added = retriever.add_documents(
        ["深蹲主要训练腿部肌群。", "蛋白质摄入应结合训练目标。"],
        sources=["strength.md", "nutrition.md"],
    )
    if not added.ok:
        raise RuntimeError(f"ingestion failed: {added.error_code} {added.error_message}")
    retriever.close()

    reopened = SQLiteFaissRetriever(
        db_path=str(db_path), embedding_model="offline-smoke-v1", encoder=encoder
    )
    result = reopened.search("深蹲怎么练腿", top_k=1, threshold=0.0)
    if not result.ok or not result.data or result.data[0]["source"] != "strength.md":
        raise RuntimeError(f"reopen/search validation failed: {result}")
    print(
        "SQLite+FAISS smoke passed: "
        f"rows={reopened.document_count}, top_source={result.data[0]['source']}"
    )
    reopened.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        type=Path,
        help="Optional database to keep; default uses a disposable temp directory.",
    )
    args = parser.parse_args()
    if args.db_path is not None:
        run(args.db_path)
        return
    with tempfile.TemporaryDirectory(prefix="fitness-rag-") as directory:
        run(Path(directory) / "knowledge.db")


if __name__ == "__main__":
    main()
