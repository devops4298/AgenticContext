"""Module 4 — Query Understanding & Rewriting.

Defines the `query_rewriter_tool`, a Google ADK FunctionTool that
leverages Gemini via the `google.genai` SDK to expand or clarify user
queries before retrieval. Credentials are supplied through environment
variables (GOOGLE_AI_API_KEY or Google Cloud default credentials).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from functools import lru_cache

from google.adk.tools import FunctionTool

try:
    import google.genai as genai
    from google.genai.types import GenerateContentConfig
except ImportError as exc:  # pragma: no cover - surfaced during runtime
    raise RuntimeError(
        "The google-genai package is required for Module 4. Install it via "
        "'pip install google-genai'."
    ) from exc

from dotenv import load_dotenv


DEFAULT_MODEL = "gemini-2.0-flash"
SYSTEM_PROMPT = (
    "Rewrite the incoming enterprise user query so that it maximises semantic "
    "retrieval quality. Preserve intent, expand abbreviations, and add key terms."
)


@dataclass(frozen=True)
class GeminiConfig:
    model: str = DEFAULT_MODEL
    system_instruction: str = SYSTEM_PROMPT


class GeminiNotConfiguredError(RuntimeError):
    """Raised when Gemini credentials are missing."""


@lru_cache(maxsize=1)
def _load_env() -> None:
    """Load environment variables from the nearest .env file."""

    candidates = [
        Path(__file__).resolve().parents[2] / ".env",  # workspace root
        Path(__file__).resolve().parents[1] / ".env",
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if path.exists():
            load_dotenv(dotenv_path=path, override=False)
            break


@lru_cache(maxsize=1)
def _get_client() -> genai.Client:
    _load_env()
    api_key = os.getenv("GOOGLE_AI_API_KEY")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

    if api_key:
        return genai.Client(api_key=api_key)
    if project:
        return genai.Client(vertexai={"project": project, "location": location})
    raise GeminiNotConfiguredError(
        "Gemini credentials not configured. Provide GOOGLE_AI_API_KEY for direct "
        "access or GOOGLE_CLOUD_PROJECT (with Application Default Credentials)."
    )


def rewrite_query(
    query: str,
    *,
    model_name: str = DEFAULT_MODEL,
    system_instruction: str = SYSTEM_PROMPT,
    temperature: float = 0.3,
    max_output_tokens: int = 64,
) -> str:
    """Rewrite ``query`` to improve downstream retrieval."""

    if not query or not query.strip():
        raise ValueError("Query must be a non-empty string")

    client = _get_client()
    config = GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    prompt = (
        f"{system_instruction}\n\n"
        f"Original Query: {query.strip()}\n"
        "Rewritten Query:"
    )

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt],
        config=config,
    )

    if not response.candidates:
        raise RuntimeError("Gemini returned no candidates for the rewritten query.")

    rewritten = response.candidates[0].content.parts[0].text.strip()
    if not rewritten:
        raise RuntimeError("Gemini response was empty.")
    return rewritten


query_rewriter_tool = FunctionTool(rewrite_query)


def _demo() -> None:
    """Manual smoke test. Requires Gemini credentials to be configured."""

    sample = "car policy"
    try:
        rewritten = rewrite_query(sample)
    except GeminiNotConfiguredError as err:
        print(f"Gemini credentials missing: {err}")
    except Exception as exc:  # pragma: no cover - debug helper
        print(f"Rewriter call failed: {exc}")
    else:
        print(f"Original: {sample}\nRewritten: {rewritten}")


if __name__ == "__main__":
    _demo()
