import logging
from calendar import monthrange
from datetime import date, datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.dashboard_mapper import (
    exact_row,
    map_dashboard_summary,
    purchase_row,
    verified_period,
)
from app.security.auth import get_authorized_company
from app.tally.client import TallyClient
from app.tally.dashboard import (
    fetch_dashboard_reports,
    parse_native_table,
    parse_profit_loss_rows,
    report_request,
)
from app.tally.service import fetch_companies
from app.tally.xml_builders.financial import build_profit_loss_request


logger = logging.getLogger(__name__)

router = APIRouter()


def month_windows(start, end):
    current = start
    while current <= end:
        last = date(current.year, current.month, monthrange(current.year, current.month)[1])
        yield current, min(last, end)
        if last >= end:
            break
        current = date(last.year + (last.month == 12), 1 if last.month == 12 else last.month + 1, 1)


def _series_point(start, end, native_pl, rows, company_name):
    """
    One chart point for this month window.

    native_pl (the HTML P&L) confirms which period Tally used: Tally
    sometimes answers with a different one (see verified_period), and
    such a month is marked unverified and left empty. The amounts come
    from the XML P&L rows, because the HTML report drops the sign of a
    line that has moved to the other side (sales returns, for example).
    """
    point = {
        'month': start.strftime('%b %Y'),
        'from_date': start.isoformat(),
        'to_date': end.isoformat(),
        'income': None,
        'expense': None,
        'status': 'unavailable',
    }

    if native_pl is None:
        return point

    if not verified_period(native_pl, start, end, company_name):
        point['status'] = 'unverified'
        point['tally_from_date'] = native_pl.get('from_date')
        point['tally_to_date'] = native_pl.get('to_date')
        return point

    if rows is None:
        return point

    sales = exact_row(rows, 'Sales Accounts')
    purchases = purchase_row(rows)

    point['income'] = sales['amount'] if sales else None
    point['expense'] = purchases['amount'] if purchases else None

    # Tally omits lines with nothing in them, so a confirmed month
    # without Sales or Purchase lines had no such entries.
    point['status'] = (
        'available'
        if point['income'] is not None or point['expense'] is not None
        else 'no_entries'
    )

    return point


async def _fetch_monthly_income_expense_series(
    company_name,
    from_date,
    to_date,
    today=None,
    is_disconnected=None,
):
    """
    Sales and purchases per calendar month of the selected period.

    Tally handles one request at a time, so each month costs a full
    P&L round trip. Months after today have no vouchers yet and are
    skipped. is_disconnected, when given, is checked before each month
    so a browser that has left the page stops occupying Tally.
    """
    last_day = min(to_date, today or date.today())

    if from_date > last_day:
        return []

    windows = list(month_windows(from_date, last_day))
    client = TallyClient()
    series = []
    started = perf_counter()

    for start, end in windows:
        if is_disconnected is not None and await is_disconnected():
            logger.info('Dashboard monthly series abandoned by the client')
            break

        request_xml = build_profit_loss_request(
            company_name=company_name,
            from_date=start,
            to_date=end,
        )
        native_pl = rows = None

        try:
            native_pl = parse_native_table(
                await client.send_xml(report_request(request_xml, html=True))
            )

            # Values are only worth a second round trip when Tally
            # confirmed it used this month's dates.
            if verified_period(native_pl, start, end, company_name):
                rows = parse_profit_loss_rows(
                    await client.send_xml(request_xml)
                )
        except Exception:
            logger.warning(
                'Dashboard monthly P&L %s -> %s could not be read',
                start,
                end,
                exc_info=True,
            )

        series.append(_series_point(start, end, native_pl, rows, company_name))

    logger.info(
        'Dashboard monthly series: %d months in %.2fs',
        len(windows),
        perf_counter() - started,
    )

    return series


def _resolve_period(from_date, to_date):
    end = to_date or date.today()
    start = from_date or date(
        end.year if end.month >= 4 else end.year - 1,
        4,
        1,
    )

    if start > end:
        raise HTTPException(
            422,
            'From date must not be after To date',
        )

    return start, end


async def _resolve_company(company_name):
    # Wildcard users must not silently read a different loaded company.
    if company_name:
        return company_name

    companies = await fetch_companies()

    if len(companies) != 1:
        raise HTTPException(
            400,
            'Please select a company for the dashboard',
        )

    return companies[0]['name']


@router.get('/summary')
async def get_dashboard_summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
):
    """
    Headline figures, tables and breakdowns. The month-by-month series
    is served separately by /monthly so these appear without waiting
    for one Tally round trip per month.
    """
    start, end = _resolve_period(from_date, to_date)

    try:
        company_name = await _resolve_company(company_name)

        started = perf_counter()

        reports, errors = await fetch_dashboard_reports(
            company_name,
            start,
            end,
        )

        if not reports:
            raise HTTPException(
                502,
                'Unable to read dashboard reports from Tally',
            )

        summary = map_dashboard_summary(
            reports,
            start,
            end,
            company_name,
        )

        summary['report_errors'] = errors
        summary['fetched_at'] = datetime.now(
            timezone.utc
        ).isoformat()

        logger.info(
            'Dashboard summary for %s (%s -> %s) in %.2fs',
            company_name,
            start,
            end,
            perf_counter() - started,
        )

        return {
            'success': True,
            'source': 'tally',
            'data': summary,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            502,
            'Unable to read dashboard reports from Tally',
        ) from exc


@router.get('/monthly')
async def get_dashboard_monthly(
    request: Request,
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
):
    """Sales and purchases per month of the selected period."""
    start, end = _resolve_period(from_date, to_date)

    try:
        company_name = await _resolve_company(company_name)

        series = await _fetch_monthly_income_expense_series(
            company_name,
            start,
            end,
            is_disconnected=request.is_disconnected,
        )

        return {
            'success': True,
            'source': 'tally',
            'data': {
                'company_name': company_name,
                'from_date': start.isoformat(),
                'to_date': end.isoformat(),
                'income_vs_expense': series,
            },
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            502,
            'Unable to read monthly figures from Tally',
        ) from exc
