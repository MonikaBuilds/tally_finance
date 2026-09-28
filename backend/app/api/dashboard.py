from calendar import monthrange
from datetime import date, datetime, timezone

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


async def _fetch_monthly_income_expense_series(company_name, from_date, to_date):
    series = []
    client = TallyClient()
    for start, end in month_windows(from_date, to_date):
        income = expense = None
        status = 'available'
        try:
            raw = await client.send_xml(build_profit_loss_request(company_name=company_name, from_date=start, to_date=end))
            rows = parse_profit_loss_rows(raw)
            sales, purchases = exact_row(rows, 'Sales Accounts'), purchase_row(rows)
            income = sales['amount'] if sales else None
            expense = purchases['amount'] if purchases else None
        except Exception:
            status = 'unavailable'
        series.append({'month': start.strftime('%b %Y'), 'from_date': start.isoformat(), 'to_date': end.isoformat(), 'income': income, 'expense': expense, 'status': status})
    return series


@router.get('/summary')
async def get_dashboard_summary(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    period: str | None = Query(default=None),
    company_name: str | None = Depends(get_authorized_company),
):
    end = to_date or date.today()
    start = from_date or date(end.year if end.month >= 4 else end.year - 1, 4, 1)
    if start > end:
        raise HTTPException(422, 'From date must not be after To date')
    try:
        # Wildcard users must not silently read a different loaded company.
        if not company_name:
            companies = await fetch_companies()
            if len(companies) != 1:
                raise HTTPException(400, 'Please select a company for the dashboard')
            company_name = companies[0]['name']
        reports, errors = await fetch_dashboard_reports(company_name, start, end)
        if not reports:
            raise HTTPException(502, 'Unable to read dashboard reports from Tally')
        summary = map_dashboard_summary(reports, start, end, company_name)
        summary['income_vs_expense'] = await _fetch_monthly_income_expense_series(company_name, start, end)
        summary['report_errors'] = errors
        summary['fetched_at'] = datetime.now(timezone.utc).isoformat()
        return {'success': True, 'source': 'tally', 'data': summary}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, 'Unable to read dashboard reports from Tally') from exc
