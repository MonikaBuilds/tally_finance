from datetime import date

from app.chatbot.date_resolver import (
    resolve_date_range
)


TODAY = date(
    2026,
    8,
    31
)


def test_today():
    result = resolve_date_range(
        "What is my revenue today?",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        8,
        31
    )

    assert result.to_date == date(
        2026,
        8,
        31
    )


def test_yesterday():
    result = resolve_date_range(
        "What was my profit yesterday?",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        8,
        30
    )

    assert result.to_date == date(
        2026,
        8,
        30
    )


def test_this_month():
    result = resolve_date_range(
        "Show revenue this month",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        8,
        1
    )

    assert result.to_date == date(
        2026,
        8,
        31
    )


def test_last_month():
    result = resolve_date_range(
        "Show last month's expenses",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        7,
        1
    )

    assert result.to_date == date(
        2026,
        7,
        31
    )


def test_this_quarter():
    result = resolve_date_range(
        "Profit for this quarter",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        7,
        1
    )

    assert result.to_date == date(
        2026,
        8,
        31
    )


def test_last_quarter():
    result = resolve_date_range(
        "Revenue for previous quarter",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        4,
        1
    )

    assert result.to_date == date(
        2026,
        6,
        30
    )


def test_current_financial_year():
    result = resolve_date_range(
        "Revenue for this financial year",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        4,
        1
    )

    assert result.to_date == date(
        2026,
        8,
        31
    )


def test_last_financial_year():
    result = resolve_date_range(
        "Profit for last financial year",
        today=TODAY
    )

    assert result.from_date == date(
        2025,
        4,
        1
    )

    assert result.to_date == date(
        2026,
        3,
        31
    )


def test_specific_month_and_year():
    result = resolve_date_range(
        "What was my revenue in July 2026?",
        today=TODAY
    )

    assert result.from_date == date(
        2026,
        7,
        1
    )

    assert result.to_date == date(
        2026,
        7,
        31
    )


def test_no_date_expression():
    result = resolve_date_range(
        "What are my receivables?",
        today=TODAY
    )

    assert result is None