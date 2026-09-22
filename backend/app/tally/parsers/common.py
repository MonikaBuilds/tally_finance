"""
Common parsing utilities for Tally XML responses.

This module contains helper functions that are shared by different
Tally parsers such as company, financial, ledger and inventory parsers.

Important:
This file should only contain common parsing/helper logic.
Report-specific business logic should stay inside its own parser module.
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime


# ============================================================
# XML CLEANING
# ============================================================

# Tally data can sometimes contain invalid numeric XML character
# references such as &#4;. This pattern helps us detect them.
_INVALID_CHAR_REF = re.compile(
    r"&#(?:x([0-9A-Fa-f]+)|([0-9]+));"
)


def _is_valid_xml_char(code_point: int) -> bool:
    """
    Check whether a character is allowed by the XML specification.

    Tally data may occasionally contain control characters that
    ElementTree cannot parse. We use this check before parsing XML.
    """
    return (
        code_point in (0x9, 0xA, 0xD)
        or 0x20 <= code_point <= 0xD7FF
        or 0xE000 <= code_point <= 0xFFFD
        or 0x10000 <= code_point <= 0x10FFFF
    )


def _drop_invalid_char_ref(match: re.Match) -> str:
    """
    Remove an invalid numeric XML character reference.

    If the referenced character is valid, we keep it unchanged.
    """
    hex_digits, decimal_digits = match.groups()

    if hex_digits is not None:
        code_point = int(hex_digits, 16)
    else:
        code_point = int(decimal_digits)

    if _is_valid_xml_char(code_point):
        return match.group(0)

    return ""


def clean_tally_xml(xml_text: str) -> str:
    """
    Clean common XML problems found in Tally responses.

    Tally may return:
    - invalid control characters
    - invalid numeric character references
    - UDF tags that ElementTree cannot read directly

    This function cleans those issues before parsing.
    """
    if not xml_text:
        return ""

    # Remove invalid control characters.
    xml_text = re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F]",
        "",
        xml_text,
    )

    # Remove invalid numeric character references.
    xml_text = _INVALID_CHAR_REF.sub(
        _drop_invalid_char_ref,
        xml_text,
    )

    # Tally can return tags like <UDF:FIELD>.
    # ElementTree treats ":" as a namespace separator, so convert
    # these tags into a safe form before parsing.
    xml_text = xml_text.replace("<UDF:", "<UDF_")
    xml_text = xml_text.replace("</UDF:", "</UDF_")

    return xml_text


# ============================================================
# XML ERROR HANDLING
# ============================================================

def _line_col_to_offset(
    text: str,
    lineno: int,
    col: int,
):
    """
    Convert an XML error line/column into the actual position
    of that character inside the complete XML string.
    """
    lines = text.split("\n")

    if lineno < 1 or lineno > len(lines):
        return None

    previous_lines_length = sum(
        len(line) + 1
        for line in lines[:lineno - 1]
    )

    return previous_lines_length + col


def _heal_one_error(
    text: str,
    exc: ET.ParseError,
):
    """
    Try to repair one known XML parsing problem.

    Tally responses are sometimes valid financially but contain
    small XML formatting problems. Instead of rejecting the whole
    response immediately, we repair only problems that we understand.

    If the error is unknown, None is returned and the caller can
    raise the original parsing error.
    """
    message = str(exc)

    # Sometimes extra text appears before or after the real
    # <ENVELOPE>...</ENVELOPE> response.
    if "junk after document element" in message:
        start = text.find("<ENVELOPE")
        end = text.rfind("</ENVELOPE>")

        if start >= 0 and end >= 0:
            trimmed = text[
                start:end + len("</ENVELOPE>")
            ]

            if trimmed != text:
                return trimmed

        return None

    if not exc.position:
        return None

    lineno, col = exc.position

    offset = _line_col_to_offset(
        text,
        lineno,
        col,
    )

    if offset is None:
        return None

    # Handle an invalid numeric character reference.
    # Example: &#4;
    if (
        "invalid character number" in message
        and text[offset:offset + 2] == "&#"
    ):
        semicolon = text.find(";", offset)

        if semicolon == -1:
            return None

        return (
            text[:offset]
            + text[semicolon + 1:]
        )

    # A company, ledger or narration may contain a raw "&",
    # for example "Sharma & Sons".
    # XML expects it to be written as "&amp;".
    if "not well-formed" in message:

        # First check whether unwanted content exists before
        # the actual Tally ENVELOPE.
        if offset < 200:
            start = text.find("<ENVELOPE")

            if start > 0:
                trimmed = text[start:]

                if trimmed != text:
                    return trimmed

        # Look slightly before the reported error position because
        # XML parsers may report the position after the actual "&".
        search_start = max(0, offset - 40)
        window = text[search_start:offset]

        amp_pos = window.rfind("&")

        if (
            amp_pos != -1
            and ";" not in window[amp_pos:]
        ):
            amp_offset = search_start + amp_pos

            return (
                text[:amp_offset]
                + "&amp;"
                + text[amp_offset + 1:]
            )

    # Unknown parsing problem.
    # Do not guess how to repair it.
    return None


def parse_xml(
    xml_text: str,
    max_heal_attempts: int = 200,
):
    """
    Safely convert a Tally XML response into an ElementTree object.

    Before parsing, the XML is cleaned. If ElementTree still finds
    one of the known Tally XML problems, we repair it and try again.
    """
    text = clean_tally_xml(xml_text)

    for _ in range(max_heal_attempts):
        try:
            return ET.fromstring(text)

        except ET.ParseError as exc:
            healed_text = _heal_one_error(
                text,
                exc,
            )

            # We only repair errors that we understand.
            # Unknown XML problems should still be visible to us.
            if healed_text is None:
                raise

            text = healed_text

    raise ET.ParseError(
        f"Tally XML still invalid after "
        f"{max_heal_attempts} automatic repair attempts - "
        f"the export is more corrupted than usual"
    )


# ============================================================
# NUMBER CONVERSION HELPERS
# ============================================================

def to_float(value) -> float:
    """
    Convert a numeric value received from Tally into a float.

    Examples:
        "1,23,456.00" -> 123456.0
        "-100"        -> -100.0
        "₹100"        -> 100.0
        "100 Dr"      -> 100.0

    Note:
    This is the existing general numeric helper. Missing or invalid
    values become 0.0, so it should not be used when we need to
    distinguish between a real zero and a missing Tally value.
    """
    if value is None:
        return 0.0

    text = str(value).strip()

    if not text:
        return 0.0

    # Remove formatting characters that are not part of the number.
    text = text.replace(",", "")
    text = text.replace("₹", "")
    text = text.replace("$", "")

    # Remove Dr/Cr text. This function only extracts the numeric
    # portion; it does not decide accounting meaning here.
    text = re.sub(
        r"\bDR\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\bCR\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    match = re.search(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)",
        text,
    )

    if not match:
        return 0.0

    try:
        return float(match.group(0))

    except (ValueError, TypeError):
        return 0.0


def to_optional_float(
    value: str | None,
) -> float | None:
    """
    Convert an optional Tally value into a float.

    This helper is important for financial data because:
        Tally gives "0.00" -> return 0.0
        Tally gives blank   -> return None
        Tally gives nothing -> return None

    We must not convert a missing Tally value into zero because
    "not available" and "0" have different meanings.
    """
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    normalized = (
        text
        .replace(",", "")
        .replace(" ", "")
    )

    upper_value = normalized.upper()

    # Remove the Dr/Cr suffix only so that the numeric value
    # can be parsed. Accounting interpretation belongs to the
    # report-specific parser, not this common helper.
    if (
        upper_value.endswith("DR")
        or upper_value.endswith("CR")
    ):
        normalized = normalized[:-2]

    normalized = normalized.strip()

    if not normalized:
        return None

    try:
        return float(normalized)

    except (TypeError, ValueError):
        return None


# ============================================================
# XML TEXT HELPERS
# ============================================================

def _text(
    node,
    tag: str,
    default="",
):
    """
    Safely read text from a child XML element.

    Instead of repeatedly checking whether a node or its text exists,
    other parsers can use this helper.
    """
    if node is None:
        return default

    child = node.find(tag)

    if child is None or child.text is None:
        return default

    return child.text.strip()


def _first_text(
    node,
    *tags,
    default="",
):
    """
    Return the first available value from multiple possible Tally tags.

    Different Tally reports may expose the same information using
    slightly different tags, so callers can provide the known tags
    in priority order.
    """
    for tag in tags:
        value = _text(
            node,
            tag,
            "",
        )

        if value:
            return value

    return default


# ============================================================
# DATE HELPER
# ============================================================

def format_tally_date(
    value: str | None,
):
    """
    Convert supported Tally date formats into YYYY-MM-DD.

    If the value does not match one of the known formats,
    it is returned unchanged rather than guessing.
    """
    if not value:
        return None

    value = str(value).strip()

    supported_formats = [
        "%Y%m%d",
        "%d-%b-%y",
        "%d-%b-%Y",
        "%Y-%m-%d",
    ]

    for date_format in supported_formats:
        try:
            parsed_date = datetime.strptime(
                value,
                date_format,
            ).date()

            return parsed_date.isoformat()

        except ValueError:
            continue

    # Do not invent or modify a date format we do not understand.
    return value