import re


READ_ONLY_MESSAGE = (
    "This assistant has read-only access to Tally. "
    "I can retrieve and explain financial information, "
    "but I cannot create, modify, update, or delete "
    "accounting records."
)


# Words that indicate the user is merely *asking about* something
# (e.g. "any update on receivables") rather than instructing the
# assistant to act on a record. A write verb followed directly by
# one of these should not count as a write attempt.
_NON_OBJECT_PREPOSITIONS = (
    r"on|in|about|for|regarding|with|of|from|to"
)

# Accounting objects that can actually be written to in Tally.
_WRITE_OBJECT = (
    r"(?:voucher|invoice|ledger|payment|payable|receivable|"
    r"entry|entries|bill|account|record|transaction|company)"
)

# Up to two filler words (articles/adjectives such as "a new",
# "this", "the") between the verb and its object. Filler words
# cannot themselves be one of the prepositions above, so phrases
# like "update on receivables" or "change in net profit" are not
# treated as a write attempt.
_FILLER = (
    rf"(?:(?!\b(?:{_NON_OBJECT_PREPOSITIONS})\b)\w+\s+){{0,2}}"
)

WRITE_PATTERNS = (
    rf"\b(?:delete|remove|update|modify|edit|change|alter|create|insert)"
    rf"\s+{_FILLER}{_WRITE_OBJECT}s?\b",
    r"\badd\s+(?:a\s+)?(?:voucher|invoice|ledger|payment)\b",
    r"\bpost\s+(?:a\s+)?payment\b",
    r"\bcancel\s+(?:a\s+)?(?:invoice|voucher)\b",
)


def is_write_request(message: str) -> bool:
    normalized_message = message.strip().lower()

    return any(
        re.search(
            pattern,
            normalized_message,
            flags=re.IGNORECASE
        )
        for pattern in WRITE_PATTERNS
    )