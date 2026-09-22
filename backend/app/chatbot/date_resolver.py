import re

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class DateRange:
    from_date: date
    to_date: date
    label: str


@dataclass(frozen=True)
class ComparisonDateRanges:
    first_period: DateRange
    second_period: DateRange


MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _month_range(
    year: int,
    month: int
) -> tuple[date, date]:
    last_day = monthrange(
        year,
        month
    )[1]

    return (
        date(year, month, 1),
        date(year, month, last_day)
    )


def _financial_year_start(
    current_date: date
) -> date:
    """
    Indian financial year:
    1 April to 31 March.
    """

    if current_date.month >= 4:
        year = current_date.year
    else:
        year = current_date.year - 1

    return date(
        year,
        4,
        1
    )


def _current_quarter_start(
    current_date: date
) -> date:
    quarter_month = (
        ((current_date.month - 1) // 3) * 3
        + 1
    )

    return date(
        current_date.year,
        quarter_month,
        1
    )


def _normalize_text(
    message: str
) -> str:
    return re.sub(
        r"\s+",
        " ",
        message.lower().strip()
    )


def resolve_date_range(
    message: str,
    today: date | None = None
) -> DateRange | None:
    """
    Resolve common natural-language financial periods.

    This function only resolves dates. It does not access
    Tally or calculate any financial values.
    """

    if not message:
        return None

    current_date = today or date.today()

    text = _normalize_text(
        message
    )

    # --------------------------------------------------
    # Explicit date range
        #
        # Examples:
        # "from 01-07-2026 to 11-09-2026"
        # "01-07-2026 to 11-09-2026"
        # --------------------------------------------------

    explicit_range_match = re.search(
        r"(?:from\s+)?"
        r"(\d{1,2}-\d{1,2}-\d{4})"
        r"\s+(?:to|until|till)\s+"
        r"(\d{1,2}-\d{1,2}-\d{4})",
        text,
    )

    if explicit_range_match:
        try:
            from_date = datetime.strptime(
                explicit_range_match.group(1),
                "%d-%m-%Y",
            ).date()

            to_date = datetime.strptime(
                explicit_range_match.group(2),
                "%d-%m-%Y",
            ).date()

            if from_date > to_date:
                return None

            return DateRange(
                from_date=from_date,
                to_date=to_date,
                label="custom date range",
            )

        except ValueError:
            return None
    # --------------------------------------------------
    # Today
    # --------------------------------------------------

    if re.search(
        r"\btoday\b",
        text
    ):
        return DateRange(
            from_date=current_date,
            to_date=current_date,
            label="today"
        )

    # --------------------------------------------------
    # Yesterday
    # --------------------------------------------------

    if re.search(
        r"\byesterday\b",
        text
    ):
        previous_day = (
            current_date
            - timedelta(days=1)
        )

        return DateRange(
            from_date=previous_day,
            to_date=previous_day,
            label="yesterday"
        )

    # --------------------------------------------------
    # Last / previous month
    # --------------------------------------------------

    if re.search(
        r"\b(last|previous)\s+month\b",
        text
    ):
        first_current_month = date(
            current_date.year,
            current_date.month,
            1
        )

        previous_month_end = (
            first_current_month
            - timedelta(days=1)
        )

        previous_month_start = date(
            previous_month_end.year,
            previous_month_end.month,
            1
        )

        return DateRange(
            from_date=previous_month_start,
            to_date=previous_month_end,
            label="last month"
        )

    # --------------------------------------------------
    # This / current month
    # --------------------------------------------------

    if re.search(
        r"\b(this|current)\s+month\b",
        text
    ):
        month_start = date(
            current_date.year,
            current_date.month,
            1
        )

        return DateRange(
            from_date=month_start,
            to_date=current_date,
            label="this month"
        )

    # --------------------------------------------------
    # Last / previous quarter
    # --------------------------------------------------

    if re.search(
        r"\b(last|previous)\s+quarter\b",
        text
    ):
        current_quarter_start = (
            _current_quarter_start(
                current_date
            )
        )

        previous_quarter_end = (
            current_quarter_start
            - timedelta(days=1)
        )

        previous_quarter_start = (
            _current_quarter_start(
                previous_quarter_end
            )
        )

        return DateRange(
            from_date=previous_quarter_start,
            to_date=previous_quarter_end,
            label="last quarter"
        )

    # --------------------------------------------------
    # This / current quarter
    # --------------------------------------------------

    if re.search(
        r"\b(this|current)\s+quarter\b",
        text
    ):
        quarter_start = (
            _current_quarter_start(
                current_date
            )
        )

        return DateRange(
            from_date=quarter_start,
            to_date=current_date,
            label="this quarter"
        )

    # --------------------------------------------------
    # Last / previous financial year
    # --------------------------------------------------

    if (
        re.search(
            r"\b(last|previous)\s+financial\s+year\b",
            text
        )
        or re.search(
            r"\b(last|previous)\s+fy\b",
            text
        )
    ):
        current_fy_start = (
            _financial_year_start(
                current_date
            )
        )

        previous_fy_start = date(
            current_fy_start.year - 1,
            4,
            1
        )

        previous_fy_end = date(
            current_fy_start.year,
            3,
            31
        )

        return DateRange(
            from_date=previous_fy_start,
            to_date=previous_fy_end,
            label="last financial year"
        )

    # --------------------------------------------------
    # This / current financial year
    # --------------------------------------------------

    if (
        re.search(
            r"\b(this|current)\s+financial\s+year\b",
            text
        )
        or re.search(
            r"\b(this|current)\s+fy\b",
            text
        )
    ):
        financial_year_start = (
            _financial_year_start(
                current_date
            )
        )

        return DateRange(
            from_date=financial_year_start,
            to_date=current_date,
            label="this financial year"
        )

    # --------------------------------------------------
    # Last / previous calendar year
    # --------------------------------------------------

    if re.search(
        r"\b(last|previous)\s+year\b",
        text
    ):
        previous_year = (
            current_date.year - 1
        )

        return DateRange(
            from_date=date(
                previous_year,
                1,
                1
            ),
            to_date=date(
                previous_year,
                12,
                31
            ),
            label="last year"
        )

    # --------------------------------------------------
    # This / current calendar year
    # --------------------------------------------------

    if re.search(
        r"\b(this|current)\s+year\b",
        text
    ):
        return DateRange(
            from_date=date(
                current_date.year,
                1,
                1
            ),
            to_date=current_date,
            label="this year"
        )

    # --------------------------------------------------
    # Specific month
    #
    # Examples:
    # "August 2026"
    # "revenue in August"
    # --------------------------------------------------

    month_pattern = (
        r"\b("
        + "|".join(MONTHS.keys())
        + r")"
        r"(?:\s+(\d{4}))?\b"
    )

    month_match = re.search(
        month_pattern,
        text
    )

    if month_match:
        month_name = (
            month_match.group(1)
        )

        supplied_year = (
            month_match.group(2)
        )

        month_number = MONTHS[
            month_name
        ]

        year = (
            int(supplied_year)
            if supplied_year
            else current_date.year
        )

        start, end = _month_range(
            year,
            month_number
        )

        return DateRange(
            from_date=start,
            to_date=end,
            label=(
                f"{month_name.title()} "
                f"{year}"
            )
        )

    return None


def resolve_comparison_ranges(
    message: str,
    today: date | None = None
) -> ComparisonDateRanges | None:
    """
    Resolve two periods from a comparison query.

    Supported examples:
    - this month vs last month
    - this quarter vs last quarter
    - this financial year vs last financial year
    - this year vs last year
    - July 2026 vs August 2026
    - July compared to August
    - from July to August

    This resolver only determines date ranges.
    It never calculates or generates financial values.
    """

    if not message:
        return None

    current_date = today or date.today()

    text = _normalize_text(
        message
    )

    # --------------------------------------------------
    # Pattern:
    # "... first period vs second period"
    # "... first period versus second period"
    # "... first period compared to second period"
    # "... first period compared with second period"
    # --------------------------------------------------

    comparison_patterns = [
        r"\s+vs\.?\s+",
        r"\s+versus\s+",
        r"\s+compared\s+to\s+",
        r"\s+compared\s+with\s+",
    ]

    for pattern in comparison_patterns:
        parts = re.split(
            pattern,
            text,
            maxsplit=1
        )

        if len(parts) != 2:
            continue

        first_period = resolve_date_range(
            parts[0],
            today=current_date
        )

        second_period = resolve_date_range(
            parts[1],
            today=current_date
        )

        if first_period and second_period:
            return ComparisonDateRanges(
                first_period=first_period,
                second_period=second_period
            )

    # --------------------------------------------------
    # Pattern:
    # "compare this month with last month"
    # "compare July with August"
    # --------------------------------------------------

    with_match = re.search(
        r"\bcompare\s+(.+?)\s+with\s+(.+)$",
        text
    )

    if with_match:
        first_text = (
            with_match.group(1)
        )

        second_text = (
            with_match.group(2)
        )

        first_period = resolve_date_range(
            first_text,
            today=current_date
        )

        second_period = resolve_date_range(
            second_text,
            today=current_date
        )

        if first_period and second_period:
            return ComparisonDateRanges(
                first_period=first_period,
                second_period=second_period
            )

    # --------------------------------------------------
    # Pattern:
    # "from July 2026 to August 2026"
    # "change from last month to this month"
    #
    # Here the later destination period becomes
    # first_period because the comparison tool calculates:
    #
    # first value - second value
    #
    # This makes positive values represent an increase.
    # --------------------------------------------------

    from_to_match = re.search(
        r"\bfrom\s+(.+?)\s+to\s+(.+)$",
        text
    )

    if from_to_match:
        old_period_text = (
            from_to_match.group(1)
        )

        new_period_text = (
            from_to_match.group(2)
        )

        old_period = resolve_date_range(
            old_period_text,
            today=current_date
        )

        new_period = resolve_date_range(
            new_period_text,
            today=current_date
        )

        if old_period and new_period:
            return ComparisonDateRanges(
                first_period=new_period,
                second_period=old_period
            )

    return None