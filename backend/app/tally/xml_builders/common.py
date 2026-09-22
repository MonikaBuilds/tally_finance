"""
Common helper functions used by Tally XML request builders.

These helpers handle Tally date formatting, company selection,
and date static variables shared by multiple request builders.
"""

from datetime import date
from xml.sax.saxutils import escape


# ============================================================
# COMMON HELPERS
# ============================================================

def format_tally_date(value: date | None) -> str | None:
    """
    Convert Python date to Tally date format: YYYYMMDD
    """
    if value is None:
        return None

    return value.strftime("%Y%m%d")


def build_company_variable(company_name: str | None) -> str:
    """
    Build Tally company static variable.
    """
    if not company_name:
        return ""

    safe_company = escape(company_name)

    return f"""
        <SVCURRENTCOMPANY>{safe_company}</SVCURRENTCOMPANY>
    """


def _date_variable(tag_name: str, value: date | None) -> str:
    """
    Build a Tally date static variable.
    """
    if value is None:
        return ""

    tally_date = format_tally_date(value)

    return f"""
        <{tag_name}>{tally_date}</{tag_name}>
    """