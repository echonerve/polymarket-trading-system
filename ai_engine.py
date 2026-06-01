"""
ai_engine.py — An OPTIONAL "AI brain" for the decision step.

It asks a large language model (Claude, GPT, Gemini, Kimi, etc.) whether a given
market is worth a paper bet, and returns a structured decision. It is OFF unless
you provide an API key. With no key, the bot quietly uses the simple maths
strategy instead — nothing breaks.

It uses only Python's standard library (urllib) to call the API, so there is
nothing to pip-install. You can talk to:

  - OpenRouter (one key, many models)  -> set OPENROUTER_API_KEY
  - OpenAI / GPT                       -> set OPENAI_API_KEY
  - Anthropic / Claude                 -> set ANTHROPIC_API_KEY

Put the key(s) in a file called `.env` next to this one (see .env.example).

HONESTY NOTE
------------
An LLM is NOT an oracle and has NO live edge on prices. It can reason about a
market description, but it does not see the order book, cannot predict the
future, and will sometimes be confidently wrong. Treat its "confidence" number
as a vibe, not a probability. This is exactly why every decision here flows into
*paper* trades you can audit, never real money.
"""

import json
import os
import urllib.request

import config

_ENV_LOADED = False


# ---------------------------------------------------------------------------
# Tiny .env loader (so you don't need the python-dotenv package)
# ---------------------------------------------------------------------------

def _load_env(path=".env"):
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _key_for(provider):
    _load_env()
    return {
        "openrouter": os.environ.get("OPENROUTER_API_KEY"),
        "openai": os.environ.get("OPENAI_API_KEY"),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY"),
    }.get(provider)


def ai_available():
    """True only if the configured provider has a key set."""
    return bool(_key_for(config.AI_PROVIDER))


# ---------------------------------------------------------------------------
# The prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a cautious prediction-market analyst helping a PAPER-TRADING simulator.
You never see the live order book and cannot predict the future. Be conservative.

RULES:
- Recommend a trade ONLY if you have a clear, stated reason the market price looks wrong.
- If you are unsure, or it's a coin-flip, or the question is unresolvable noise, return NO_TRADE.
- Account for a 2% fee on entries; small edges are not worth it.
- Never claim certainty. Confidence is a rough 0-100 feeling, not a guarantee.

Return ONLY a JSON object, no prose, in exactly this shape:
{"decision": "BUY_YES" | "BUY_NO" | "NO_TRADE",
 "confidence": 0-100,
 "reasoning": "one or two sentences",
 "risk_level": "LOW" | "MEDIUM" | "HIGH"}"""


def _build_user_prompt(market):
    return (
        f"Market: {market['question']}\n"
        f"Current YES price: {market['yes_price']:.2f}  (implied {market['yes_price']*100:.0f}% chance)\n"
        f"Current NO price:  {market['no_price']:.2f}\n"
        f"24h volume: ${market['volume_24hr']:.0f}   total volume: ${market['volume']:.0f}\n"
        f"Price change last hour: {market['one_hour_change']:+.2f}   last day: {market['one_day_change']:+.2f}\n"
        f"Days until it resolves: {market['days_left']}\n\n"
        "Should we take a paper position? JSON only."
    )


# ---------------------------------------------------------------------------
# Provider calls (stdlib urllib; no external packages)
# ---------------------------------------------------------------------------

def _post_json(url, headers, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_openai_compatible(base_url, key, market):
    """Works for OpenAI and OpenRouter (same chat-completions schema)."""
    payload = {
        "model": config.AI_MODEL,
        "temperature": config.AI_TEMPERATURE,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(market)},
        ],
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    resp = _post_json(f"{base_url}/chat/completions", headers, payload)
    return resp["choices"][0]["message"]["content"]


def _call_anthropic(key, market):
    payload = {
        "model": config.AI_MODEL,
        "max_tokens": 400,
        "temperature": config.AI_TEMPERATURE,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": _build_user_prompt(market)}],
    }
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    resp = _post_json("https://api.anthropic.com/v1/messages", headers, payload)
    return resp["content"][0]["text"]


# ---------------------------------------------------------------------------
# Public: decide()
# ---------------------------------------------------------------------------

def _safe_parse(text):
    """Pull a JSON object out of the model's reply, tolerating stray prose."""
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        obj = json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return _no_trade("could not parse AI reply")
    obj.setdefault("decision", "NO_TRADE")
    obj.setdefault("confidence", 0)
    obj.setdefault("reasoning", "")
    obj.setdefault("risk_level", "MEDIUM")
    return obj


def _no_trade(reason):
    return {"decision": "NO_TRADE", "confidence": 0,
            "reasoning": reason, "risk_level": "LOW"}


def decide(market):
    """Ask the configured AI provider about one market. Always returns a dict.

    Any failure (no key, network error, bad JSON) degrades to NO_TRADE so the
    bot never crashes on the AI step.
    """
    provider = config.AI_PROVIDER
    key = _key_for(provider)
    if not key:
        return _no_trade(f"no API key for provider '{provider}'")
    try:
        if provider == "anthropic":
            text = _call_anthropic(key, market)
        elif provider == "openai":
            text = _call_openai_compatible("https://api.openai.com/v1", key, market)
        else:  # openrouter
            text = _call_openai_compatible("https://openrouter.ai/api/v1", key, market)
        return _safe_parse(text)
    except Exception as exc:  # never let the AI step kill the run
        return _no_trade(f"AI call failed: {exc}")


def mock_decide(market):
    """A deterministic stand-in used for offline demos/tests (no API needed).

    It is NOT intelligent — it just turns the hourly move into a fake 'decision'
    so you can see the AI plumbing run end-to-end without spending API credits.
    """
    move = market["one_hour_change"]
    if move <= -0.05:
        return {"decision": "BUY_YES", "confidence": 62,
                "reasoning": "mock: sharp drop, fading it", "risk_level": "MEDIUM"}
    if move >= 0.05:
        return {"decision": "BUY_NO", "confidence": 62,
                "reasoning": "mock: sharp rise, fading it", "risk_level": "MEDIUM"}
    return _no_trade("mock: no strong move")
