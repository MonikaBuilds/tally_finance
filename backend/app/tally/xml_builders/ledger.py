"""
Tally XML builders for ledger and voucher-related requests.
"""

from datetime import date
from xml.sax.saxutils import escape

from app.tally.xml_builders.common import (
    format_tally_date,
    build_company_variable,
    _date_variable,
)


# ============================================================
# LEDGER LIST
# ============================================================

def build_ledger_list_request(
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Ledger List</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Ledger List">
                        <TYPE>Ledger</TYPE>

                        <FETCH>
                            NAME,
                            PARENT,
                            OPENINGBALANCE,
                            CLOSINGBALANCE,
                            GUID
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# SINGLE LEDGER
# ============================================================

def build_single_ledger_request(
    ledger_name: str,
    company_name: str | None = None,
) -> str:

    safe_ledger_name = escape(ledger_name)
    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Single Ledger</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                {company_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Single Ledger">
                        <TYPE>Ledger</TYPE>
                        <FILTER>SingleLedgerFilter</FILTER>

                        <FETCH>
                            NAME,
                            OPENINGBALANCE,
                            CLOSINGBALANCE,
                            GUID
                        </FETCH>
                    </COLLECTION>

                    <SYSTEM TYPE="Formulae"
                            NAME="SingleLedgerFilter">
                        $Name = "{safe_ledger_name}"
                    </SYSTEM>

                </TDLMESSAGE>
            </TDL>
        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# LEDGER REPORT - NATIVE TALLY REPORT
# ============================================================

def build_ledger_report_request(
    ledger_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
) -> str:

    safe_ledger_name = escape(ledger_name)

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Data</TYPE>
        <ID>Ledger Vouchers</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}

                {from_date_xml}
                {to_date_xml}

                <LEDGERNAME>{safe_ledger_name}</LEDGERNAME>

                <SHOWRUNBALANCE>Yes</SHOWRUNBALANCE>
                <ExplodeNarrFlag>Yes</ExplodeNarrFlag>

            </STATICVARIABLES>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# LEDGER VOUCHER COLLECTION
# ============================================================

def build_ledger_voucher_collection_request(
    ledger_name: str,
    from_date: date | None = None,
    to_date: date | None = None,
    company_name: str | None = None,
) -> str:
    """
    ledger_name is intentionally NOT sent to Tally as a server-side
    <FILTER> here - matching happens entirely in Python instead,
    against every voucher this fetches.

    A TDL formula against ALLLEDGERENTRIES may resolve only against
    the first ledger entry instead of walking every ledger entry.

    Therefore this request fetches vouchers and the existing parser
    performs the ledger-name matching.

    Do not put an XML/HTML-style comment inside the returned request
    because TallyPrime may reject the request.
    """

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Ledger Voucher Collection</ID>
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

                    <COLLECTION NAME="Ledger Voucher Collection">
                        <TYPE>Voucher</TYPE>

                        <FETCH>
                            DATE,
                            GUID,
                            VOUCHERTYPENAME,
                            VOUCHERNUMBER,
                            REFERENCE,
                            PARTYLEDGERNAME,
                            PARTYNAME,
                            NARRATION,
                            ISDELETED,
                            ALLLEDGERENTRIES.*,
                            ALLLEDGERENTRIES.CATEGORYALLOCATIONS.*,
                            ALLLEDGERENTRIES.CATEGORYALLOCATIONS.COSTCENTREALLOCATIONS.*,
                            ALLINVENTORYENTRIES.*
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# VOUCHER DETAIL
# ============================================================

def build_voucher_detail_request(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = None,
) -> str:

    safe_type = escape(voucher_type or "")
    safe_number = escape(voucher_number or "")

    company_xml = build_company_variable(company_name)

    date_xml = ""

    if voucher_date is not None:
        date_xml = (
            _date_variable("SVFROMDATE", voucher_date)
            + _date_variable("SVTODATE", voucher_date)
        )

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Voucher Detail Collection</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {date_xml}

            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Voucher Detail Collection">
                        <TYPE>Voucher</TYPE>

                        <FETCH>
                            DATE,
                            GUID,
                            VOUCHERTYPENAME,
                            VOUCHERNUMBER,
                            REFERENCE,
                            REFERENCEDATE,
                            PARTYLEDGERNAME,
                            PARTYNAME,
                            NARRATION,
                            ISDELETED,
                            ISCANCELLED,
                            ALLLEDGERENTRIES.*
                        </FETCH>

                        <FILTER>VoucherDetailFilter</FILTER>

                    </COLLECTION>

                    <SYSTEM TYPE="Formulae"
                            NAME="VoucherDetailFilter">
                        $VoucherTypeName = "{safe_type}" AND
                        $VoucherNumber = "{safe_number}"
                    </SYSTEM>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# CHATBOT LEDGER REQUEST
# ============================================================

def build_chatbot_ledger_request(
    ledger_name: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
):
    """
    Build a ledger-scoped voucher request for the chatbot.

    Financial values are requested from Tally.
    This builder does not calculate balances or amounts.
    """
    safe_ledger_name = escape(ledger_name.strip())

    company_xml = build_company_variable(
        company_name
    )

    from_date_xml = ""
    to_date_xml = ""

    if from_date:
        from_date_xml = (
            f"<SVFROMDATE>"
            f"{format_tally_date(from_date)}"
            f"</SVFROMDATE>"
        )

    if to_date:
        to_date_xml = (
            f"<SVTODATE>"
            f"{format_tally_date(to_date)}"
            f"</SVTODATE>"
        )

    return f"""
    <ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>Chatbot Ledger Voucher Collection</ID>
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

                        <COLLECTION NAME="Chatbot Ledger Voucher Collection">

                            <TYPE>Vouchers : Ledger</TYPE>

                            <CHILDOF>
                                {safe_ledger_name}
                            </CHILDOF>

                            <FETCH>
                                DATE,
                                GUID,
                                VOUCHERTYPENAME,
                                VOUCHERNUMBER,
                                NARRATION,
                                PARTYLEDGERNAME,
                                ISDELETED,
                                ALLLEDGERENTRIES.*,
                                ALLINVENTORYENTRIES.*
                            </FETCH>

                        </COLLECTION>

                    </TDLMESSAGE>
                </TDL>

            </DESC>
        </BODY>
    </ENVELOPE>
    """
