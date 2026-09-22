import asyncio
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from app.chatbot.tool_registry import TOOL_DEFINITIONS


logger = logging.getLogger(__name__)


load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

MODEL_NAME = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
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
- Dates passed to tools must use DD-MM-YYYY format.
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
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=message,
                config=config,
            ),
            timeout=GEMINI_TIMEOUT_SECONDS,
        )

    except asyncio.TimeoutError:
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