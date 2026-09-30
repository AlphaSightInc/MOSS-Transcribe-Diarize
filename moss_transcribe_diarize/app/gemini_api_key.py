"""Resolve a request's Gemini key, with an operator-owned fallback."""

import os


def gemini_api_key(provided: str | None) -> str | None:
    return (provided or "").strip() or os.environ.get("GEMINI_API_KEY", "").strip() or None
