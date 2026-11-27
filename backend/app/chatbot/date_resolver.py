import re

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta


class InvalidDateRange(ValueError):
    """An explicit date was invalid; never substitute a broader period."""


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
    cleaned = message.lower().strip()
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    return re.sub(
        r"\s+",
        " ",
        cleaned
    )


def get_current_financial_year_range(
    today: date | None = None
) -> DateRange:
    """
    Get the DateRange for the current Indian financial year
    (1 April to current date).
    """
    current_date = today or date.today()
    fy_start = _financial_year_start(current_date)
    return DateRange(
        from_date=fy_start,
        to_date=current_date,
        label="this financial year",
    )


def resolve_date_range(
    message: str,
    today: date | None = None
) -> DateRange | None:
    """
    Resolve common natural-language financial periods.

    This function only resolves dates. It does not access
    Tally or calculate any financial values. Explicit invalid dates raise
    InvalidDateRange instead of falling back to a broader reporting period.
    """

    if not message:
        return None

    current_date = today or date.today()

    text = _normalize_text(
        message
    )

    # --------------------------------------------------
    # 1. Explicit date range with digits
    #
    # Examples:
    # "from 01-07-2026 to 11-09-2026"
    # "01-07-2026 to 11-09-2026"
    # "between 01-04-2026 and 30-09-2026"
    # "from 01/04/2026 to 30/09/2026"
    # --------------------------------------------------

    explicit_range_match = re.search(
        r"(?:between\s+|from\s+)?"
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
        r"\s+(?:to|and|until|till)\s+"
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})",
        text,
    )

    if explicit_range_match:
        try:
            d1_str = explicit_range_match.group(1).replace("/", "-")
            d2_str = explicit_range_match.group(2).replace("/", "-")

            from_date = datetime.strptime(
                d1_str,
                "%d-%m-%Y",
            ).date()

            to_date = datetime.strptime(
                d2_str,
                "%d-%m-%Y",
            ).date()

            if from_date > to_date:
                raise InvalidDateRange("The start date must not be after the end date.")

            return DateRange(
                from_date=from_date,
                to_date=to_date,
                label="custom date range",
            )

        except ValueError as exc:
            raise InvalidDateRange("Please provide valid dates in chronological order.") from exc

    # --------------------------------------------------
    # 1a. Explicit start date with a relative end
    #
    # Examples:
    # "from 01-04-2026 till today"
    # "01-04-2026 to now"
    # --------------------------------------------------

    open_range_match = re.search(
        r"(?:between\s+|from\s+)?"
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
        r"\s+(?:to|and|until|till)\s+"
        r"(today|now)\b",
        text,
    )

    if open_range_match:
        try:
            from_date = datetime.strptime(
                open_range_match.group(1).replace("/", "-"),
                "%d-%m-%Y",
            ).date()
        except ValueError as exc:
            raise InvalidDateRange("Please provide a valid start date.") from exc

        if from_date is not None:
            # Never produce a range that ends before it starts.
            if from_date > current_date:
                raise InvalidDateRange("The start date must not be after today.")

            return DateRange(
                from_date=from_date,
                to_date=current_date,
                label="custom date range",
            )

    # Also support ISO format (YYYY-MM-DD to YYYY-MM-DD)
    iso_range_match = re.search(
        r"(?:between\s+|from\s+)?"
        r"(\d{4}-\d{2}-\d{2})"
        r"\s+(?:to|and|until|till)\s+"
        r"(\d{4}-\d{2}-\d{2})",
        text,
    )
    if iso_range_match:
        try:
            from_date = datetime.strptime(
                iso_range_match.group(1),
                "%Y-%m-%d",
            ).date()
            to_date = datetime.strptime(
                iso_range_match.group(2),
                "%Y-%m-%d",
            ).date()
            if from_date > to_date:
                raise InvalidDateRange("The start date must not be after the end date.")
            if from_date <= to_date:
                return DateRange(
                    from_date=from_date,
                    to_date=to_date,
                    label="custom date range",
                )
        except ValueError as exc:
            raise InvalidDateRange("Please provide valid dates in chronological order.") from exc

    # --------------------------------------------------
    # 1b. Explicit date range with day + month name + optional year
    #
    # Examples:
    # "between 1 April 2026 and 30 September 2026"
    # "from 1st April to 30th September"
    # --------------------------------------------------
    months_pattern_str = "|".join(MONTHS.keys())
    day_month_range = re.search(
        r"(?:between\s+|from\s+)?"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + months_pattern_str + r")(?:\s+(\d{4}))?"
        r"\s+(?:to|and|until|till)\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?\s+(" + months_pattern_str + r")(?:\s+(\d{4}))?",
        text,
    )
    if day_month_range:
        try:
            d1 = int(day_month_range.group(1))
            m1 = MONTHS[day_month_range.group(2)]
            y1_str = day_month_range.group(3)
            d2 = int(day_month_range.group(4))
            m2 = MONTHS[day_month_range.group(5)]
            y2_str = day_month_range.group(6)

            yr2 = int(y2_str) if y2_str else (int(y1_str) if y1_str else current_date.year)
            yr1 = int(y1_str) if y1_str else yr2

            from_date = date(yr1, m1, d1)
            to_date = date(yr2, m2, d2)
            if from_date > to_date:
                raise InvalidDateRange("The start date must not be after the end date.")
            if from_date <= to_date:
                return DateRange(
                    from_date=from_date,
                    to_date=to_date,
                    label="custom date range",
                )
        except (ValueError, TypeError) as exc:
            raise InvalidDateRange("Please provide valid dates in chronological order.") from exc

    iso_date_match = re.search(r"(?<![\d-])(\d{4}-\d{2}-\d{2})(?![\d-])", text)
    if iso_date_match:
        try:
            target_date = date.fromisoformat(iso_date_match.group(1))
        except ValueError as exc:
            raise InvalidDateRange("Please provide a valid calendar date.") from exc
        return DateRange(target_date, target_date, target_date.strftime("%d-%m-%Y"))

    # --------------------------------------------------
    # Single date
    #
    # Examples:
    # "for 01-04-2025", "on 01-04-2025", "as on 31-03-2026", "01-04-2025"
    # "on 15th August 2025", "for 1 April 2025"
    # --------------------------------------------------
    single_date_match = re.search(
        r"(?<![\d/-])(\d{1,2}[-/]\d{1,2}[-/]\d{4})(?![\d/-])",
        text,
    )
    if single_date_match:
        d_str = single_date_match.group(1).replace("/", "-")
        try:
            target_date = datetime.strptime(
                d_str,
                "%d-%m-%Y",
            ).date()
            return DateRange(
                from_date=target_date,
                to_date=target_date,
                label=target_date.strftime("%d-%m-%Y"),
            )
        except ValueError as exc:
            raise InvalidDateRange("Please provide a valid calendar date.") from exc

    months_pattern_str = "|".join(MONTHS.keys())
    single_natural_date_match = re.search(
        r"\b(?:on|for|as\s+on|as\s+of)?\s*(\d{1,2})(?:st|nd|rd|th)?\s+("
        + months_pattern_str
        + r")(?:\s+(\d{4}))?\b",
        text,
    )
    if single_natural_date_match:
        try:
            d_val = int(single_natural_date_match.group(1))
            m_val = MONTHS[single_natural_date_match.group(2).lower()]
            y_val = (
                int(single_natural_date_match.group(3))
                if single_natural_date_match.group(3)
                else current_date.year
            )
            target_date = date(y_val, m_val, d_val)
            return DateRange(
                from_date=target_date,
                to_date=target_date,
                label=target_date.strftime("%d-%m-%Y"),
            )
        except (ValueError, TypeError) as exc:
            raise InvalidDateRange("Please provide a valid calendar date.") from exc

    # --------------------------------------------------
    # 2. Explicit Financial Year
    #
    # Examples:
    # "FY 2025-26", "FY 2026-27", "FY 2026-2027", "FY 25-26"
    # "financial year 2025-26", "2025-26 financial year"
    # --------------------------------------------------
    fy_match = re.search(
        r"\b(?:fy\s*|f\.y\.\s*|financial\s+year\s+)?(\d{2,4})\s*[-/]\s*(\d{2,4})(?:\s+financial\s+year|\s+fy)?\b",
        text,
    )
    if fy_match:
        g1, g2 = fy_match.group(1), fy_match.group(2)
        y1 = int(g1) if len(g1) == 4 else (2000 + int(g1))
        y2 = int(g2) if len(g2) == 4 else ((y1 // 100) * 100 + int(g2))
        if y2 == y1 + 1:
            from_date = date(y1, 4, 1)
            to_date = date(y2, 3, 31)
            return DateRange(
                from_date=from_date,
                to_date=to_date,
                label=f"FY {y1}-{str(y2)[-2:]}",
            )

    # A named calendar year must not silently use Tally's active FY.
    calendar_year_match = re.search(
        r"\b(?:in|during|calendar\s+year)\s+(\d{4})\b(?![-/])", text,
    )
    if calendar_year_match:
        year = int(calendar_year_match.group(1))
        if year < 1:
            raise InvalidDateRange("Please provide a valid calendar year.")
        return DateRange(date(year, 1, 1), date(year, 12, 31), str(year))

    # --------------------------------------------------
    # 3. Month to Month range
    #
    # Examples:
    # "from April to September"
    # "between April and September"
    # "April to September 2026"
    # --------------------------------------------------
    month_range_match = re.search(
        r"(?:between\s+|from\s+)?\b(" + months_pattern_str + r")\s+(?:to|and|until|till)\s+(" + months_pattern_str + r")(?:\s+(\d{4}))?\b",
        text,
    )
    if month_range_match:
        m1_name = month_range_match.group(1)
        m2_name = month_range_match.group(2)
        yr_str = month_range_match.group(3)
        m1 = MONTHS[m1_name]
        m2 = MONTHS[m2_name]
        yr = int(yr_str) if yr_str else current_date.year
        from_date = date(yr, m1, 1)
        last_day = monthrange(yr, m2)[1]
        to_date = date(yr, m2, last_day)
        yr_suffix = f" {yr}" if yr_str else ""
        return DateRange(
            from_date=from_date,
            to_date=to_date,
            label=f"{m1_name.title()} to {m2_name.title()}{yr_suffix}",
        )
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

    # "may" is also the modal verb ("what may be my receivables").
    # Treat it as the month only when it is used as one: followed by a
    # year, or preceded by a date preposition / "this"/"last"/"next".
    if month_match and month_match.group(1) == "may":
        preceded_by_marker = re.search(
            r"(?:in|during|for|of|since|until|till|from)\s+"
            r"(?:the\s+)?(?:this\s+|last\s+|next\s+)?may\b",
            text,
        )
        if not month_match.group(2) and not preceded_by_marker:
            month_match = None

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

        # A month named without a year is meant as the most recent one
        # that has already started - "sales in December" asked in
        # October means last December, not a future month with no data.
        if not supplied_year and start > current_date:
            year -= 1
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