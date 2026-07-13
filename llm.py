"""AI chat backed by Claude on the Bosch LLM Farm.

The farm serves Claude via Vertex, so we use Anthropic's `AnthropicVertex` client
pointed at the farm's base URL (per the farm's Code Examples doc). The subscription
key is read from the environment; `httpx` picks up `HTTPS_PROXY` automatically, so
the same proxy used for the NHTSA call also routes these requests.

`anthropic` is imported lazily inside chat() so the rest of the app (decode, parts,
pricing, static serving) runs even when the package isn't installed.
"""

import os

# Best Claude model available on the farm (see the farm's Code Examples doc).
MODEL = "claude-sonnet-4-5@20250929"
BASE_URL = "https://aoai-farm.bosch-temp.com/api/google/v1"

# The farm key may be published under any of these env var names.
KEY_ENV_VARS = (
    "GENAIPLATFORM_FARM_SUBSCRIPTION_KEY",
    "FARM_API_KEY",
    "MODEL_FARM_SUBSCRIPTION_KEY",
)

MAX_TOKENS = 1024


class NotConfigured(Exception):
    """Raised when no farm subscription key is available in the environment."""


def _get_key():
    for name in KEY_ENV_VARS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def _system_prompt(vehicle):
    vehicle = vehicle or {}
    year = vehicle.get("modelYear") or "unknown-year"
    make = vehicle.get("make") or "unknown make"
    model = vehicle.get("model") or "unknown model"
    body = vehicle.get("bodyClass") or ""
    descriptor = "{} {} {}".format(year, make, model).strip()
    if body:
        descriptor += " ({})".format(body)
    return (
        "You are a knowledgeable, practical automotive assistant helping the user with "
        "their {}. Answer questions about maintenance, common problems, parts, and "
        "servicing for this specific vehicle. Be concise and concrete; if a question "
        "isn't about the vehicle, answer briefly anyway. Note you are giving general "
        "guidance, not a substitute for a mechanic.".format(descriptor)
    )


def _sanitize(messages):
    """Keep only well-formed user/assistant text turns."""
    clean = []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            clean.append({"role": role, "content": content})
    return clean


def chat(vehicle, messages):
    """Send the conversation to Claude on the farm and return the reply text.

    Raises NotConfigured if no key is set. Other failures propagate to the caller.
    """
    key = _get_key()
    if not key:
        raise NotConfigured(
            "AI chat is not configured. Set GENAIPLATFORM_FARM_SUBSCRIPTION_KEY "
            "(the Bosch LLM Farm subscription key) and restart."
        )

    convo = _sanitize(messages)
    if not convo:
        raise ValueError("No message to send.")

    from anthropic import AnthropicVertex  # lazy import (optional dependency)

    client = AnthropicVertex(
        access_token=key,
        project_id="_",
        region="_",
        base_url=BASE_URL,
    )
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=_system_prompt(vehicle),
        messages=convo,
    )
    parts = [block.text for block in response.content if getattr(block, "type", None) == "text"]
    return "".join(parts).strip() or "(no response)"
