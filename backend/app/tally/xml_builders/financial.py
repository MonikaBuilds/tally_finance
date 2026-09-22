"""
Tally XML builders for financial reports.
"""

from datetime import date
from xml.sax.saxutils import escape

from app.tally.xml_builders.common import (
    build_company_variable,
    _date_variable,
)


# ============================================================
# PROFIT & LOSS
# ============================================================

def build_profit_loss_request(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Profit and Loss</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {from_date_xml}
                {to_date_xml}

            </STATICVARIABLES>
        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# GROUP SUMMARY (Profit & Loss drill-down)
#
# Used when the person clicks a P&L line such as "Indirect Expenses",
# "Sales Accounts" or "Purchase Accounts" and expects to see that
# group's ledgers, exactly like double-clicking the line inside Tally
# itself does (Tally's own "Group Summary" display report).
#
# NOTE: <GROUPNAME> is the static variable this app uses to scope the
# built-in "Group Summary" report to one group, matching the common
# Tally XML integration convention. This has not yet been verified
# against a live raw XML dump (Tally wasn't reachable while this was
# written) - if a live drill-down comes back empty, print the raw
# response the same way fetch_profit_loss does and check whether this
# build's Tally expects a different variable name (e.g. SVCURRENTGROUP)
# for the same purpose.
# ============================================================

def build_group_summary_request(
    group_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> str:

    safe_group_name = escape(group_name)

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Group Summary</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {from_date_xml}
                {to_date_xml}

                <GROUPNAME>{safe_group_name}</GROUPNAME>

            </STATICVARIABLES>
        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# TRIAL BALANCE
# ============================================================

def build_trial_balance_request(
    company_name: str | None = None,
    to_date: date | None = None,
) -> str:

    company_xml = build_company_variable(company_name)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Trial Balance</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {to_date_xml}

            </STATICVARIABLES>
        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# BALANCE SHEET
# ============================================================

def build_balance_sheet_request(
    company_name: str | None = None,
    to_date: date | None = None,
) -> str:

    company_xml = build_company_variable(company_name)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Balance Sheet</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {to_date_xml}

            </STATICVARIABLES>
        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# VOUCHER / BILL ALLOCATIONS
# ============================================================

def build_voucher_bills_request(
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Voucher Bills</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {from_date_xml}
                {to_date_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Voucher Bills">
                        <TYPE>Voucher</TYPE>

                        <FETCH>
                            DATE,
                            GUID,
                            VOUCHERTYPENAME,
                            VOUCHERNUMBER,
                            PARTYLEDGERNAME,
                            PARTYNAME,
                            REFERENCE,
                            NARRATION,
                            ISINVOICE,
                            ISDELETED,
                            ALLLEDGERENTRIES.*
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# RECEIVABLES
# ============================================================

def build_bills_receivable_request(
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Bills Receivable</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}

            </STATICVARIABLES>
        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# PAYABLES
# ============================================================

def build_bills_payable_request(
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Bills Payable</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}

            </STATICVARIABLES>
        </DESC>
    </BODY>
</ENVELOPE>
"""