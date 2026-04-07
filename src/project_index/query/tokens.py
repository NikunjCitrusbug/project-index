from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count using a simple heuristic: ~3.5 chars per token."""
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))
