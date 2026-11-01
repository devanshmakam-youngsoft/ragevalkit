"""A short fingerprint of a question set."""
import hashlib

import pandas as pd


def compute_fingerprint(df: pd.DataFrame) -> str:
    """12-char SHA-256 fingerprint of the question set (stable across identical uploads)."""
    content = "\n".join(
        sorted(
            f"{r.chat_id}:{r.turn_no}:{r.question}:{r.expected_answer}"
            for r in df.itertuples(index=False)
        )
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]
