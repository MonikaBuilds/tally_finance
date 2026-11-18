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


def tdl_string(value: str | None) -> str:
    """
    Make a value safe inside a double-quoted TDL string such as
    $Name = "<value>" in a collection filter.

    The request is XML, so & < > are escaped; inside the TDL string a
    double quote is written twice. Without this a name like 5" PVC Pipe
    ends the string early (a syntax error) and a crafted name could add
    its own filter conditions.
    """
    return escape(str(value or "")).replace('"', '""')


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