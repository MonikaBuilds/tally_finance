import asyncio
import json
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
import httpx

from app.chatbot.tool_registry import TOOL_DEFINITIONS


logger = logging.getLogger(__name__)


load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)
FALLBACK_MODEL_NAME = os.getenv("GEMINI_FALLBACK_MODEL")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "nvidia/nemotron-3-super-120b-a12b:free",
)
OPENROUTER_CHAT_COMPLETIONS_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

GEMINI_TIMEOUT_SECONDS = 8


client = genai.Client(
    api_key=GEMINI_API_KEY,
)


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
    if not OPENROUTER_API_KEY:
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
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=GEMINI_TOOLS,
        automatic_function_calling=(
            types.AutomaticFunctionCallingConfig(
                disable=True,
            )
        ),
    )

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
