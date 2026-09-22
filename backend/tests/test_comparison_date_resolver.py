from datetime import date

from app.chatbot.date_resolver import resolve_comparison_ranges


TODAY = date(2026, 8, 31)


def test_this_month_vs_last_month():
    result = resolve_comparison_ranges(
        "Compare revenue this month vs last month",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 8, 1
    )
    assert result.first_period.to_date == date(
        2026, 8, 31
    )

    assert result.second_period.from_date == date(
        2026, 7, 1
    )
    assert result.second_period.to_date == date(
        2026, 7, 31
    )


def test_this_quarter_vs_last_quarter():
    result = resolve_comparison_ranges(
        "Compare profit this quarter vs last quarter",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 7, 1
    )
    assert result.first_period.to_date == date(
        2026, 8, 31
    )

    assert result.second_period.from_date == date(
        2026, 4, 1
    )
    assert result.second_period.to_date == date(
        2026, 6, 30
    )


def test_this_fy_vs_last_fy():
    result = resolve_comparison_ranges(
        "Compare profit this FY vs last FY",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 4, 1
    )
    assert result.first_period.to_date == date(
        2026, 8, 31
    )

    assert result.second_period.from_date == date(
        2025, 4, 1
    )
    assert result.second_period.to_date == date(
        2026, 3, 31
    )


def test_this_year_vs_last_year():
    result = resolve_comparison_ranges(
        "Compare revenue this year vs last year",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 1, 1
    )
    assert result.first_period.to_date == date(
        2026, 8, 31
    )

    assert result.second_period.from_date == date(
        2025, 1, 1
    )
    assert result.second_period.to_date == date(
        2025, 12, 31
    )


def test_specific_months_with_vs():
    result = resolve_comparison_ranges(
        "Compare revenue August 2026 vs July 2026",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 8, 1
    )
    assert result.first_period.to_date == date(
        2026, 8, 31
    )

    assert result.second_period.from_date == date(
        2026, 7, 1
    )
    assert result.second_period.to_date == date(
        2026, 7, 31
    )


def test_compare_months_with_keyword():
    result = resolve_comparison_ranges(
        "Compare August 2026 with July 2026",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 8, 1
    )
    assert result.second_period.from_date == date(
        2026, 7, 1
    )


def test_from_old_month_to_new_month():
    result = resolve_comparison_ranges(
        "How did revenue change from July 2026 to August 2026?",
        today=TODAY
    )

    assert result is not None

    # Destination/new period should be first.
    assert result.first_period.from_date == date(
        2026, 8, 1
    )

    # Starting/old period should be second.
    assert result.second_period.from_date == date(
        2026, 7, 1
    )


def test_previous_month_wording():
    result = resolve_comparison_ranges(
        "Compare expenses current month versus previous month",
        today=TODAY
    )

    assert result is not None

    assert result.first_period.from_date == date(
        2026, 8, 1
    )
    assert result.first_period.to_date == date(
        2026, 8, 31
    )

    assert result.second_period.from_date == date(
        2026, 7, 1
    )
    assert result.second_period.to_date == date(
        2026, 7, 31
    )


def test_non_comparison_query_returns_none():
    result = resolve_comparison_ranges(
        "What is my revenue this month?",
        today=TODAY
    )

    assert result is None