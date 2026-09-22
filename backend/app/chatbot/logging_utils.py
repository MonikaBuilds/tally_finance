import logging
import uuid


logger = logging.getLogger(
    "tally_chatbot"
)


def create_request_id() -> str:
    return str(
        uuid.uuid4()
    )


def log_chat_event(
    request_id: str,
    event: str,
    intent: str | None = None,
    source: str | None = None
):
    logger.info(
        "chatbot_event request_id=%s event=%s "
        "intent=%s source=%s",
        request_id,
        event,
        intent,
        source
    )