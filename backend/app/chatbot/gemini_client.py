import asyncio
import functools
import json
import logging
import os
import re

from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
import httpx

from app.chatbot.tool_registry import TOOL_DEFINITIONS


logger = logging.getLogger(__name__)


_BACKEND_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_BACKEND_ENV)
load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)
FALLBACK_MODEL_NAME = os.getenv("GEMINI_FALLBACK_MODEL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# Opt-in only: user questions contain party names and must not be sent to
# a second provider (especially free models that may log prompts) by default.
OPENROUTER_FALLBACK_ENABLED = os.getenv(
    "OPENROUTER_FALLBACK_ENABLED", "false"
).strip().lower() in {"1", "true", "yes", "on"}
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openrouter/free",
)
OPENROUTER_CHAT_COMPLETIONS_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

GEMINI_TIMEOUT_SECONDS = 8

# Optional thinking budget for tool selection. Tool choice is a short
# classification task; thinking tokens are billed as output, so a small or
# zero budget (when the model allows it) cuts cost and latency.
_THINKING_BUDGET_TEXT = os.getenv("GEMINI_THINKING_BUDGET", "").strip()
GEMINI_THINKING_BUDGET = (
    int(_THINKING_BUDGET_TEXT)
    if _THINKING_BUDGET_TEXT.lstrip("-").isdigit()
    else None
)

# Running token totals for this process (read by monitoring and tests).
LLM_USAGE = {
    "calls": 0,
    "prompt_tokens": 0,
    "output_tokens": 0,
    "thinking_tokens": 0,
    "subset_calls": 0,
    "full_schema_retries": 0,
}


client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY,
        )
    except Exception as exc:
        logger.warning("Could not initialize genai.Client: %s", exc)
        client = None


SYSTEM_INSTRUCTION = """
You are a read-only Tally financial assistant.

Your job is only to understand the user's financial question
and choose the correct approved read-only tool.

Rules:

- Never provide financial values yourself.
- Never invent, estimate, assume, or reuse financial information.
- Never create, update, modify, delete, alter, post, or write anything.
- Never request a tool that is not provided.
- Use the available tools for Tally financial questions.
- Dates passed to tools must use DD-MM-YYYY or YYYY-MM-DD format.
- If the question is outside the supported Tally financial scope,
  do not call any tool.
"""


def _build_gemini_tools():
    function_declarations = []

    for definition in TOOL_DEFINITIONS:
        function_declarations.append(
            {
                "name": definition["name"],
                "description": definition["description"],
                "parameters": definition["parameters"],
            }
        )

    return [
        types.Tool(
            function_declarations=function_declarations,
        )
    ]


# Build once instead of rebuilding the complete tool schema
# for every chatbot request.
GEMINI_TOOLS = _build_gemini_tools()

_DEFINITIONS_BY_NAME = {d["name"]: d for d in TOOL_DEFINITIONS}

# ------------------------------------------------------------------
# Relevant-tool pre-selection (cost)
# ------------------------------------------------------------------
# Sending all tool schemas costs roughly 9,000 input tokens per call.
# Most questions clearly belong to a few tools, so only those schemas are
# sent. If the model then picks nothing, the full schema is tried once, so
# accuracy never depends on this shortcut.

_SYNONYMS = {
    "receivable": {"owe", "owes", "owed", "debtor", "debtors", "collect",
                   "collection", "due", "outstanding", "customer", "customers"},
    "payable": {"pay", "creditor", "creditors", "supplier", "suppliers",
                "vendor", "vendors", "outstanding", "due"},
    "sales": {"sale", "sold", "sell", "selling", "revenue", "turnover",
              "income", "customer", "customers"},
    "revenue": {"sale", "sales", "turnover", "income", "earning", "earnings"},
    "purchase": {"purchases", "bought", "buy", "buying", "supplier", "suppliers"},
    "expenses": {"expense", "spend", "spent", "cost", "costs", "spending"},
    "profit": {"loss", "margin", "earning", "earnings", "p&l", "pl"},
    "stock": {"inventory", "item", "items", "product", "products", "godown",
              "quantity", "goods"},
    "bank": {"banks", "account", "accounts", "hdfc", "sbi", "icici", "axis"},
    "cash": {"money", "hand"},
    "gst": {"tax", "cgst", "sgst", "igst", "itc"},
    "tds": {"tax", "deducted", "withholding"},
    "ledger": {"account", "statement", "party", "transactions"},
    "invoice": {"bill", "bills", "invoices", "voucher", "vouchers"},
    "overdue": {"late", "aging", "ageing", "aged", "delayed"},
    "comparison": {"compare", "versus", "vs", "growth", "change"},
    "trend": {"trends", "monthly", "growth"},
    "day": {"daybook", "diary", "dairy", "daily", "today"},
    "balance": {"closing", "opening"},
    "note": {"return", "returns", "credit", "debit"},
}

_STOP_TOKENS = {"get", "by", "of", "the", "a", "an", "my", "our", "is", "are",
                "what", "show", "me", "for", "and", "to", "in", "all", "list"}

_MAX_TOOLS_PER_CALL = 15


def _tokens(text: str) -> set[str]:
    words = set()
    for raw in re.findall(r"[a-z&]+", text.lower()):
        if raw in _STOP_TOKENS:
            continue
        words.add(raw)
        if raw.endswith("s") and len(raw) > 3:
            words.add(raw[:-1])
    return words


def _tool_keywords(name: str) -> set[str]:
    words = _tokens(name.replace("_", " "))
    expanded = set(words)
    for word in words:
        expanded |= _SYNONYMS.get(word, set())
    return expanded


_TOOL_KEYWORDS = {name: _tool_keywords(name) for name in _DEFINITIONS_BY_NAME}


def relevant_tool_names(message: str) -> list[str] | None:
    """
    Tools whose names (plus synonyms) overlap the question, best first.
    None means "no confident match - send every tool".
    """
    words = _tokens(message)
    scored = []
    for name, keywords in _TOOL_KEYWORDS.items():
        score = len(words & keywords)
        if score:
            scored.append((score, name))

    if not scored:
        return None

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [name for _score, name in scored[:_MAX_TOOLS_PER_CALL]]


@functools.lru_cache(maxsize=512)
def _gemini_tools_for(names: tuple[str, ...]):
    return [
        types.Tool(
            function_declarations=[
                {
                    "name": _DEFINITIONS_BY_NAME[name]["name"],
                    "description": _DEFINITIONS_BY_NAME[name]["description"],
                    "parameters": _DEFINITIONS_BY_NAME[name]["parameters"],
                }
                for name in names
            ]
        )
    ]


def _record_usage(response, model_name: str, tool_count: int) -> None:
    usage = getattr(response, "usage_metadata", None)
    prompt = getattr(usage, "prompt_token_count", None) or 0
    output = getattr(usage, "candidates_token_count", None) or 0
    thinking = getattr(usage, "thoughts_token_count", None) or 0

    LLM_USAGE["calls"] += 1
    LLM_USAGE["prompt_tokens"] += prompt
    LLM_USAGE["output_tokens"] += output
    LLM_USAGE["thinking_tokens"] += thinking

    logger.info(
        "llm_usage model=%s tools=%d prompt_tokens=%d output_tokens=%d "
        "thinking_tokens=%d",
        model_name,
        tool_count,
        prompt,
        output,
        thinking,
    )


def _build_openrouter_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": definition["name"],
                "description": definition["description"],
                "parameters": definition["parameters"],
            },
        }
        for definition in TOOL_DEFINITIONS
    ]


OPENROUTER_TOOLS = _build_openrouter_tools()


async def _select_tool_with_openrouter(message: str) -> dict | None:
    """Use OpenRouter as a tool-selection fallback after Gemini fails."""
    if not OPENROUTER_FALLBACK_ENABLED or not OPENROUTER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        # Tool selection needs a complete function call, so use the
        # non-streaming response and parse its structured arguments.
        "stream": False,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": message},
        ],
        "tools": OPENROUTER_TOOLS,
        "tool_choice": "auto",
    }

    try:
        async with httpx.AsyncClient(
            timeout=GEMINI_TIMEOUT_SECONDS,
        ) as http_client:
            response = await http_client.post(
                OPENROUTER_CHAT_COMPLETIONS_URL,
                headers=headers,
                json=payload,
            )
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            raise ValueError("OpenRouter returned no choices.")

        message_result = choices[0].get("message") or {}
        tool_calls = message_result.get("tool_calls") or []
        if not tool_calls:
            return {
                "tool_name": None,
                "arguments": {},
                "error": None,
            }

        function = tool_calls[0].get("function") or {}
        tool_name = function.get("name")
        raw_arguments = function.get("arguments") or "{}"
        arguments = (
            raw_arguments
            if isinstance(raw_arguments, dict)
            else json.loads(raw_arguments)
        )
        if not isinstance(arguments, dict):
            raise ValueError("OpenRouter returned invalid tool arguments.")

        logger.info(
            "Chatbot tool selection used OpenRouter fallback model %s.",
            OPENROUTER_MODEL,
        )
        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "error": None,
        }

    except Exception as exc:
        status_code = getattr(
            getattr(exc, "response", None),
            "status_code",
            None,
        )
        logger.warning(
            "OpenRouter fallback failed: status=%s error_type=%s",
            status_code,
            type(exc).__name__,
        )
        return {
            "tool_name": None,
            "arguments": {},
            "error": "model_unavailable",
        }


async def select_tool(
    message: str,
) -> dict:
    """
    Ask the model which approved tool answers the question.

    Only the relevant tool schemas are sent first; if the model then calls
    no tool, the full schema is tried once before concluding the question
    is unsupported.
    """
    names = relevant_tool_names(message)

    if names is None:
        return await _select_tool_once(message, GEMINI_TOOLS, len(TOOL_DEFINITIONS))

    LLM_USAGE["subset_calls"] += 1
    selection = await _select_tool_once(
        message, _gemini_tools_for(tuple(names)), len(names)
    )

    if selection.get("error") is None and not selection.get("tool_name"):
        LLM_USAGE["full_schema_retries"] += 1
        selection = await _select_tool_once(
            message, GEMINI_TOOLS, len(TOOL_DEFINITIONS)
        )

    return selection


async def _select_tool_once(
    message: str,
    tools,
    tool_count: int,
) -> dict:
    if client is None:
        logger.info("Gemini client is not configured; attempting OpenRouter fallback.")
        fallback_selection = await _select_tool_with_openrouter(message)
        if fallback_selection is not None:
            return fallback_selection
        return {
            "tool_name": None,
            "arguments": {},
            "error": "authentication",
        }
    config_kwargs = {
        "system_instruction": SYSTEM_INSTRUCTION,
        "tools": tools,
        # Tool choice must be repeatable: same question, same tool.
        "temperature": 0.0,
        "automatic_function_calling": (
            types.AutomaticFunctionCallingConfig(
                disable=True,
            )
        ),
    }
    if GEMINI_THINKING_BUDGET is not None:
        config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_budget=GEMINI_THINKING_BUDGET,
        )
    config = types.GenerateContentConfig(**config_kwargs)

    try:
        model_candidates = [MODEL_NAME]
        if (
            FALLBACK_MODEL_NAME
            and FALLBACK_MODEL_NAME != MODEL_NAME
        ):
            model_candidates.append(FALLBACK_MODEL_NAME)

        response = None
        for index, model_name in enumerate(model_candidates):
            for attempt in range(2 if index == 0 else 1):
                try:
                    async_models = getattr(
                        getattr(client, "aio", None),
                        "models",
                        None,
                    )
                    async_generate = getattr(
                        async_models,
                        "generate_content",
                        None,
                    )
                    if async_generate is None:
                        # Keep compatibility with synchronous clients and
                        # test doubles while running their network call off
                        # the event loop.
                        generate = asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=message,
                            config=config,
                        )
                    else:
                        generate = async_generate(
                            model=model_name,
                            contents=message,
                            config=config,
                        )
                    response = await asyncio.wait_for(
                        generate,
                        timeout=GEMINI_TIMEOUT_SECONDS,
                    )
                    _record_usage(response, model_name, tool_count)
                    break
                except (errors.ServerError, errors.ClientError) as exc:
                    retryable = (
                        getattr(exc, "code", None) == 503
                        or getattr(exc, "code", None) == 429
                    )
                    if not retryable:
                        raise

                    if index == 0 and attempt == 0:
                        logger.warning(
                            "Gemini model %s returned %s; retrying once.",
                            model_name,
                            getattr(exc, "code", "server error"),
                        )
                        await asyncio.sleep(0.35)
                        continue

                    if index + 1 < len(model_candidates):
                        logger.warning(
                            "Gemini model %s returned %s; trying configured fallback model.",
                            model_name,
                            getattr(exc, "code", "server error"),
                        )
                        break
                    raise

            if response is not None:
                break

    except asyncio.TimeoutError:
        fallback_selection = await _select_tool_with_openrouter(message)
        if fallback_selection is not None:
            return fallback_selection
        return {
            "tool_name": None,
            "arguments": {},
            "error": "timeout",
        }

    except errors.ClientError as exc:
        status_code = getattr(
            exc,
            "code",
            None,
        )

        error_text = str(exc).lower()

        logger.error(
            "Gemini ClientError: status=%s error=%s",
            status_code,
            exc,
        )

        fallback_selection = await _select_tool_with_openrouter(message)
        if fallback_selection is not None:
            return fallback_selection

        if (
            status_code == 429
            or "resource_exhausted" in error_text
            or "quota" in error_text
        ):
            return {
                "tool_name": None,
                "arguments": {},
                "error": "rate_limit",
            }

        if status_code in (401, 403):
            return {
                "tool_name": None,
                "arguments": {},
                "error": "authentication",
            }

        if status_code == 404:
            return {
                "tool_name": None,
                "arguments": {},
                "error": "model_not_found",
            }

        return {
            "tool_name": None,
            "arguments": {},
            "error": "model_error",
        }

    except errors.ServerError as exc:
        logger.exception(
            "Gemini ServerError: %s",
            exc,
        )

        fallback_selection = await _select_tool_with_openrouter(message)
        if fallback_selection is not None:
            return fallback_selection

        return {
            "tool_name": None,
            "arguments": {},
            "error": "model_unavailable",
        }

    except Exception as exc:
        logger.exception(
            "Unexpected Gemini error: %s",
            exc,
        )

        fallback_selection = await _select_tool_with_openrouter(message)
        if fallback_selection is not None:
            return fallback_selection

        return {
            "tool_name": None,
            "arguments": {},
            "error": "model_unavailable",
        }

    function_calls = response.function_calls or []

    if not function_calls:
        return {
            "tool_name": None,
            "arguments": {},
            "error": None,
        }

    tool_call = function_calls[0]

    return {
        "tool_name": tool_call.name,
        "arguments": dict(
            tool_call.args or {}
        ),
        "error": None,
    }
