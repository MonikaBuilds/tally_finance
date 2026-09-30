"""Read-only dashboard exports. Financial amounts are selected, never totalled here."""

import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

from app.tally.client import TallyClient
from app.tally.parsers.common import parse_xml, to_optional_float
from app.tally.xml_builders.financial import (
    build_profit_loss_request,
    build_bills_receivable_request,
    build_bills_payable_request,
)
from app.tally.xml_builders.ledger import build_ledger_list_request


def report_request(xml, *, html=False, as_of=None):
    root = ET.fromstring(xml)
    variables = root.find('.//STATICVARIABLES')
    if html:
        variables.find('SVEXPORTFORMAT').text = '$$SysName:HTML'
    if as_of:
        node = variables.find('SVTODATE')
        if node is None:
            node = ET.SubElement(variables, 'SVTODATE')
        node.text = as_of.strftime('%Y%m%d')
    return ET.tostring(root, encoding='unicode')


def collection_request(company, as_of, kind):
    root = ET.fromstring(build_ledger_list_request(company))
    collection = root.find('.//COLLECTION')
    collection_name = f'Dashboard {kind} Balances'
    root.find('HEADER/ID').text = collection_name
    collection.set('NAME', collection_name)
    collection.find('TYPE').text = kind
    collection.find('FETCH').text = 'NAME,PARENT,CLOSINGBALANCE'
    return report_request(ET.tostring(root, encoding='unicode'), as_of=as_of)


def checked_xml(raw):
    root = parse_xml(raw)
    if root.tag != 'ENVELOPE' or root.find('.//LINEERROR') is not None:
        raise ValueError('Tally did not return a valid report')
    return root


def parse_profit_loss_rows(raw):
    """Read each native P&L label and its adjacent PLAMT, including blanks."""
    children = list(checked_xml(raw))
    rows = []
    for index, node in enumerate(children):
        if node.tag != 'DSPACCNAME':
            continue
        name = node.findtext('DSPDISPNAME')
        if not name:
            continue
        sibling = children[index + 1] if index + 1 < len(children) else None
        main = sub = None
        if sibling is not None and sibling.tag == 'PLAMT':
            main = sibling.findtext('BSMAINAMT')
            sub = sibling.findtext('PLSUBAMT')
        # The verified Purchase row is exported in PLSUBAMT, not BSMAINAMT.
        raw_amount = main if main and main.strip() else sub
        rows.append({
            'name': name.strip(), 'amount': to_optional_float(raw_amount),
            'raw': raw_amount,
            'field': 'PLAMT/BSMAINAMT' if main and main.strip() else 'PLAMT/PLSUBAMT',
        })
    if not rows:
        raise ValueError('No recognizable P&L rows returned by Tally')
    return rows


def parse_balances(raw, kind):
    root = checked_xml(raw)
    if root.find('.//COLLECTION') is None:
        raise ValueError('Tally did not return the requested balance collection')
    return [
        {
            'name': node.get('NAME') or node.findtext('NAME'),
            'reserved_name': node.get('RESERVEDNAME'),
            'parent': node.findtext('PARENT'),
            'amount': to_optional_float(node.findtext('CLOSINGBALANCE')),
            'raw': node.findtext('CLOSINGBALANCE'),
            'field': f'{kind.upper()}/CLOSINGBALANCE',
        }
        for node in root.findall(f'.//{kind.upper()}')
    ]


class ReportTable(HTMLParser):
    """Extract native report cells without executing or rendering Tally HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(''.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def report_date(text):
    for pattern in ('%d-%b-%y', '%d-%b-%Y'):
        try:
            return datetime.strptime(text.strip(), pattern).date().isoformat()
        except ValueError:
            pass
    return None


def parse_native_table(raw):
    table = ReportTable()
    table.feed(raw)
    if not table.rows:
        raise ValueError('Tally did not return a recognizable HTML report')
    periods = set()
    for row in table.rows:
        for cell in row:
            match = re.fullmatch(r'(\d{1,2}-[A-Za-z]{3}-\d{2,4}) to (\d{1,2}-[A-Za-z]{3}-\d{2,4})', cell)
            if match:
                periods.add((report_date(match[1]), report_date(match[2])))
            elif cell.startswith('For '):
                single = report_date(cell[4:])
                if single:
                    periods.add((single, single))
    period = next(iter(periods)) if len(periods) == 1 else (None, None)
    return {'rows': table.rows, 'from_date': period[0], 'to_date': period[1]}


def html_amount(text):
    """Amount cell from a native HTML report; Tally writes negatives as (-)1,000.00."""
    if text and text.strip().startswith('(-)'):
        value = to_optional_float(text.strip()[3:])
        return -value if value is not None else None
    return to_optional_float(text)


def previous_period(start, end):
    """
    The period of the same length just before start..end. Whole
    calendar months shift by months (a financial year compares with the
    previous financial year); any other range shifts by its day count.
    """
    last_day = monthrange(end.year, end.month)[1]
    if start.day == 1 and end.day == last_day:
        months = (end.year - start.year) * 12 + end.month - start.month + 1
        previous_end = start - timedelta(days=1)
        index = previous_end.year * 12 + previous_end.month - 1 - (months - 1)
        return date(index // 12, index % 12 + 1, 1), previous_end

    previous_end = start - timedelta(days=1)
    return previous_end - (end - start), previous_end


def parse_outstanding_table(raw):
    report = parse_native_table(raw)
    rows = report['rows']
    header = next((row for row in rows if 'Pending' in row and "Party's Name" in row), None)
    if header is None:
        raise ValueError('Outstanding report columns were not recognized')
    columns = {label: header.index(label) for label in ('Date', 'Ref. No.', "Party's Name", 'Pending', 'Due on', 'Overdue')}
    bills = []
    totals = []
    for row in rows[rows.index(header) + 1:]:
        if len(row) != len(header):
            continue
        amount_text = row[columns['Pending']]
        party = row[columns["Party's Name"]]
        bill_date = report_date(row[columns['Date']])
        if party and bill_date:
            overdue = row[columns['Overdue']]
            bills.append({
                'party': party,
                'reference': row[columns['Ref. No.']],
                'bill_date': bill_date,
                'amount': to_optional_float(amount_text),
                'raw': amount_text,
                'due_date': report_date(row[columns['Due on']]),
                'days_overdue': int(overdue) if overdue.isdigit() else None,
            })
        elif amount_text and all(not cell for i, cell in enumerate(row) if i != columns['Pending']):
            # The native footer occupies the Pending Amount column alone.
            # Never substitute a bill or a Python sum for this report total.
            totals.append(amount_text)
    raw_total = totals[0] if len(totals) == 1 else None
    return {**report, 'bills': bills, 'total': to_optional_float(raw_total), 'raw_total': raw_total}


async def fetch_dashboard_reports(company, start, end):
    client = TallyClient()
    pl_request = build_profit_loss_request(company_name=company, from_date=start, to_date=end)
    previous_start, previous_end = previous_period(start, end)
    previous_request = build_profit_loss_request(
        company_name=company, from_date=previous_start, to_date=previous_end,
    )
    requests = {
        'profit_loss': (pl_request, parse_profit_loss_rows),
        'profit_loss_totals': (report_request(pl_request, html=True), parse_native_table),
        'previous_profit_loss': (previous_request, parse_profit_loss_rows),
        'previous_profit_loss_totals': (report_request(previous_request, html=True), parse_native_table),
        'groups': (collection_request(company, end, 'Group'), lambda raw: parse_balances(raw, 'Group')),
        'ledgers': (collection_request(company, end, 'Ledger'), lambda raw: parse_balances(raw, 'Ledger')),
        'receivables': (report_request(build_bills_receivable_request(company), html=True, as_of=end), parse_outstanding_table),
        'payables': (report_request(build_bills_payable_request(company), html=True, as_of=end), parse_outstanding_table),
    }
    reports, errors = {}, {}
    for name, (request, parser) in requests.items():
        try:
            reports[name] = parser(await client.send_xml(request))
        except Exception:
            errors[name] = 'Tally report could not be read. Refresh or check the Tally connection.'
    return reports, errors
