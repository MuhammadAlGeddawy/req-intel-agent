import json
import re
import os
from pathlib import Path
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

# Hugging Face local embeddings are optional for startup; load lazily when embeddings are actually needed.
try:
    from transformers import AutoModel, AutoTokenizer
    import torch
except Exception:  # pragma: no cover - graceful fallback for lightweight environments
    AutoModel = None
    AutoTokenizer = None
    torch = None

# Global cache for the embedding model to avoid reloading on every call
_EMBEDDING_TOKENIZER = None
_EMBEDDING_MODEL = None

# ─── OPENROUTER CLIENT ───────────────────────────────────────────────────────
# OpenRouter provides free access to open-source models via OpenAI-compatible API.
# This project continues using OpenRouter for chat completions while generating
# embeddings locally via Hugging Face transformers to avoid remote embedding calls.

# 1. Load environment variables from config/.env relative to this file
ENV_PATH = Path(__file__).resolve().parents[2] / "config" / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# 2. Get the key from the environment
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_FALLBACK_MODEL = os.getenv("OPENROUTER_FALLBACK_MODEL", "gpt-4o-mini")
OPENROUTER_FALLBACK_URL = os.getenv("OPENROUTER_FALLBACK_URL", "https://openrouter.ai/api/v1")

# 3. Simple check to see if it exists
if not OPENROUTER_API_KEY:
    raise ValueError("❌ OPENROUTER_API_KEY not found in .env file or environment variables.")

MODEL = "qwen/qwen-2.5-7b-instruct"
EMBEDDING_MODEL = os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


class JSONParsingException(ValueError):
    def __init__(self, raw: str, schema_hint: str):
        self.raw = raw
        self.schema_hint = schema_hint
        super().__init__(f"JSON parsing failed: {schema_hint}")


def _should_retry(exception: Exception) -> bool:
    message = str(exception).lower()
    retry_errors = [
        "429",
        "rate limit",
        "timeout",
        "timed out",
        "connection error",
        "gateway timeout",
        "service unavailable",
        "internal server error",
        "unauthorized",
    ]
    return any(token in message for token in retry_errors)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
def call_llm(system: str, user: str, max_tokens: int = 1000, model: str | None = None, base_url: str | None = None) -> str:
    """Call OpenRouter API and return text response with retry resilience."""
    target_model = model or MODEL
    target_url = base_url or "https://openrouter.ai/api/v1"

    client_config = OpenAI(base_url=target_url, api_key=OPENROUTER_API_KEY)

    try:
        response = client_config.chat.completions.create(
            model=target_model,
            temperature=0.05,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            extra_headers={
                "HTTP-Referer": "https://github.com/muhammad-algeddawy/requirements-agent",
                "X-Title": "Engineering Requirements Intelligence Agent",
            },
        )
    except Exception as exc:
        message = str(exc)
        if _should_retry(exc):
            raise
        raise RuntimeError(f"LLM request failed: {message}") from exc

    return response.choices[0].message.content.strip()



def _load_embedding_model():
    global _EMBEDDING_TOKENIZER, _EMBEDDING_MODEL
    if _EMBEDDING_TOKENIZER is not None and _EMBEDDING_MODEL is not None:
        return _EMBEDDING_TOKENIZER, _EMBEDDING_MODEL

    if AutoTokenizer is None or AutoModel is None or torch is None:
        raise RuntimeError("Transformers/torch dependencies are not available in this environment.")

    _EMBEDDING_TOKENIZER = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    _EMBEDDING_MODEL = AutoModel.from_pretrained(EMBEDDING_MODEL)
    _EMBEDDING_MODEL.eval()
    return _EMBEDDING_TOKENIZER, _EMBEDDING_MODEL


def _mean_pooling(model_output: Any, attention_mask: Any):
    if torch is None:
        raise RuntimeError("PyTorch is not available in this environment.")

    token_embeddings = model_output.last_hidden_state
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    sum_embeddings = torch.sum(token_embeddings * input_mask_expanded, dim=1)
    sum_mask = torch.clamp(input_mask_expanded.sum(dim=1), min=1e-9)
    return sum_embeddings / sum_mask


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings locally with Hugging Face transformers."""
    if not texts:
        return []

    try:
        tokenizer, model = _load_embedding_model()
        encoded_input = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            model_output = model(**encoded_input)

        embeddings = _mean_pooling(model_output, encoded_input["attention_mask"])
        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
        return [vector.tolist() for vector in embeddings]
    except Exception:
        fallback = []
        for text in texts:
            tokens = re.findall(r"[a-z0-9]+", text.lower())
            vector = [0.0] * 1536
            for token in tokens:
                index = abs(hash(token)) % 1536
                vector[index] += 1.0
            norm = sum(value * value for value in vector) ** 0.5 or 1.0
            fallback.append([value / norm for value in vector])
        return fallback


def call_llm_json(system: str, user: str, max_tokens: int = 1500, schema_hint: str = "expected JSON schema") -> dict:
    """Call LLM, parse JSON response safely, and fallback to alternate model on repeated failures."""
    system_with_json = (
        system
        + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
        "No markdown, no explanation, no code blocks. "
        "Start your response directly with { and end with }."
    )

    raw = None
    try:
        raw = call_llm(system_with_json, user, max_tokens)
    except Exception:
        raw = call_llm(
            system_with_json,
            user,
            max_tokens,
            model=OPENROUTER_FALLBACK_MODEL,
            base_url=OPENROUTER_FALLBACK_URL,
        )

    # Strip any accidental markdown fences
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_exc:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise JSONParsingException(raw=raw, schema_hint=schema_hint) from first_exc
