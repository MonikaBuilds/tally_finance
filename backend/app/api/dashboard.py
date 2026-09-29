from calendar import monthrange
from datetime import date, datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dashboard_mapper import exact_row, map_dashboard_summary, purchase_row
from app.security.auth import get_authorized_company
from app.tally.client import TallyClient
from app.tally.dashboard import fetch_dashboard_reports, parse_profit_loss_rows
from app.tally.service import fetch_companies
from app.tally.xml_builders.financial import build_profit_loss_request


router = APIRouter()


def month_windows(start, end):
    current = start
    while current <= end:
        last = date(current.year, current.month, monthrange(current.year, current.month)[1])
        yield current, min(last, end)
        if last >= end:
            break
        current = date(last.year + (last.month == 12), 1 if last.month == 12 else last.month + 1, 1)


async def _fetch_monthly_income_expense_series(
    company_name,
    from_date,
    to_date,
):
    series = []
    client = TallyClient()

    series_started = perf_counter()

    for start, end in month_windows(from_date, to_date):
        income = expense = None
        status = 'available'

        month_started = perf_counter()

        try:
            raw = await client.send_xml(
                build_profit_loss_request(
                    company_name=company_name,
                    from_date=start,
                    to_date=end,
                )
            )

            rows = parse_profit_loss_rows(raw)
            sales, purchases = (
                exact_row(rows, 'Sales Accounts'),
                purchase_row(rows),
            )

            income = sales['amount'] if sales else None
            expense = purchases['amount'] if purchases else None
            if income is None and expense is None:
                status = 'unavailable'
        except Exception:
            status = 'unavailable'

        month_elapsed = perf_counter() - month_started

        print(
            f'[DASHBOARD TIMING] Monthly P&L '
            f'{start.isoformat()} -> {end.isoformat()}: '
            f'{month_elapsed:.2f}s'
        )

        series.append(
            {
                'month': start.strftime('%b %Y'),
                'from_date': start.isoformat(),
                'to_date': end.isoformat(),
                'income': income,
                'expense': expense,
                'status': status,
            }
        )

    total_elapsed = perf_counter() - series_started

    print(
        f'[DASHBOARD TIMING] Monthly series total: '
        f'{total_elapsed:.2f}s'
    )

    return series


@router.get('/summary')
async def get_dashboard_summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    period: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
):
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

    try:
        # Wildcard users must not silently read a different loaded company.
        if not company_name:
            companies = await fetch_companies()

            if len(companies) != 1:
                raise HTTPException(
                    400,
                    'Please select a company for the dashboard',
                )

            company_name = companies[0]['name']

        dashboard_started = perf_counter()

        # Measure base Dashboard reports
        reports_started = perf_counter()

        reports, errors = await fetch_dashboard_reports(
            company_name,
            start,
            end,
        )

        reports_elapsed = perf_counter() - reports_started

        print(
            f'[DASHBOARD TIMING] Base dashboard reports: '
            f'{reports_elapsed:.2f}s'
        )

        if not reports:
            raise HTTPException(
                502,
                'Unable to read dashboard reports from Tally',
            )

        # Existing Dashboard mapping
        summary = map_dashboard_summary(
            reports,
            start,
            end,
            company_name,
        )

        # Measure Income vs Expense monthly series
        monthly_started = perf_counter()

        summary['income_vs_expense'] = (
            await _fetch_monthly_income_expense_series(
                company_name,
                start,
                end,
            )
        )

        monthly_elapsed = perf_counter() - monthly_started

        print(
            f'[DASHBOARD TIMING] Income vs expense series: '
            f'{monthly_elapsed:.2f}s'
        )

        # Existing metadata
        summary['report_errors'] = errors
        summary['fetched_at'] = datetime.now(
            timezone.utc
        ).isoformat()

        # Total Dashboard request time
        total_elapsed = perf_counter() - dashboard_started

        print(
            f'[DASHBOARD TIMING] TOTAL dashboard request: '
            f'{total_elapsed:.2f}s'
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