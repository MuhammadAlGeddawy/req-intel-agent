import json
import re
import os
from openai import OpenAI
from dotenv import load_dotenv

# ─── OPENROUTER CLIENT ───────────────────────────────────────────────────────
# OpenRouter provides free access to open-source models via OpenAI-compatible API.
# Get your free API key at: https://openrouter.ai/keys
#
# Free models available on OpenRouter (no credits needed):
#   - mistralai/mistral-7b-instruct          (fast, good instruction following)
#   - meta-llama/llama-3.2-3b-instruct       (small, fast)
#   - meta-llama/llama-3.1-8b-instruct       (balanced quality/speed)
#   - qwen/qwen-2.5-7b-instruct              (strong structured output)
#   - google/gemma-3-4b-it                   (lightweight, good JSON)
#   - microsoft/phi-3-mini-128k-instruct     (very fast, small)
#
# Recommended for this agent: qwen/qwen-2.5-7b-instruct
# (strongest JSON output reliability among free models)

# 1. This looks for a .env file and loads variables into os.environ
load_dotenv(dotenv_path="../config/.env")

# 2. Get the key from the environment
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# 3. Simple check to see if it exists
if not OPENROUTER_API_KEY:
    raise ValueError("❌ OPENROUTER_API_KEY not found in .env file or environment variables.")

MODEL = "qwen/qwen-2.5-7b-instruct"

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def call_llm(system: str, user: str, max_tokens: int = 1000) -> str:
    """Call OpenRouter API and return text response."""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.01,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            extra_headers={
                "HTTP-Referer": "https://github.com/muhammad-algeddawy/requirements-agent",
                "X-Title": "Engineering Requirements Intelligence Agent",
            }
        )
    except Exception as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    return response.choices[0].message.content.strip()

def call_llm_json(system: str, user: str, max_tokens: int = 1500) -> dict:
    """Call LLM and parse JSON response safely."""
    system_with_json = (
        system
        + "\n\nIMPORTANT: Respond ONLY with valid JSON. "
        "No markdown, no explanation, no code blocks. "
        "Start your response directly with { and end with }."
    )
    raw = call_llm(system_with_json, user, max_tokens)
    # Strip any accidental markdown fences
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON object if wrapped in text
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {"error": "Could not parse LLM response", "raw": raw}