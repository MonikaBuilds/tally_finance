from datetime import date
from xml.sax.saxutils import escape


# ============================================================
# COMMON HELPERS
# ============================================================

def format_tally_date(value: date | None) -> str | None:
    """
    Convert Python date to Tally date format: YYYYMMDD
    """
    if value is None:
        return None

    return value.strftime("%Y%m%d")


def build_company_variable(company_name: str | None) -> str:
    """
    Build Tally company static variable.
    """
    if not company_name:
        return ""

    safe_company = escape(company_name)

    return f"""
        <SVCURRENTCOMPANY>{safe_company}</SVCURRENTCOMPANY>
    """


def _date_variable(tag_name: str, value: date | None) -> str:
    """
    Build a Tally date static variable.
    """
    if value is None:
        return ""

    tally_date = format_tally_date(value)

    return f"""
        <{tag_name}>{tally_date}</{tag_name}>
    """


# ============================================================
# COMPANIES
# ============================================================

def build_company_request() -> str:
    return """
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>List of Companies</ID>
    </HEADER>

    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="List of Companies">
                        <TYPE>Company</TYPE>

                        <FETCH>
                            NAME,
                            GUID,
                            BOOKSFROM,
                            STARTINGFROM,
                            GSTREGISTRATIONTYPE,
                            GSTIN
                        </FETCH>
                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>
        </DESC>
    </BODY>
</ENVELOPE>
"""


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
# SINGLE LEDGER (lightweight master lookup for one ledger)
#
# Used by fetch_ledger_report() to get just the requested
# ledger's opening/closing balance without pulling the whole
# company's Ledger List, which is a much heavier Tally query
# and was the source of repeated ReadTimeouts.
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
#
# Fallback for cases where native "Ledger Vouchers"
# does not return usable rows.
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
    against every voucher this fetches. Reasoning:

    A TDL formula such as "$AllLedgerEntries.LedgerName = "X"" only
    ever compares against the FIRST ledger entry of each voucher,
    because ALLLEDGERENTRIES.LIST is a repeating list and a bare
    dotted reference to it in a scalar formula resolves to its first
    element - it does not walk every entry. That silently drops any
    voucher where the requested ledger is the second (or later) leg,
    e.g. "Cash" in a Contra voucher whose first leg is a bank ledger,
    causing that ledger's report to come back with zero entries even
    though Tally genuinely has them.

    So instead we fetch every voucher in the date range and let the
    Python-side parser (which correctly walks every entry in
    ALLLEDGERENTRIES.LIST - see parser.py) do the real ledger-name
    matching.

    IMPORTANT: do not put an XML/HTML-style "<!-- -->" comment inside
    the returned request string below. TallyPrime's own request
    parser chokes on those and rejects the entire request with
    "Unknown Request, cannot be processed" - this note has to live
    here in Python instead of in the XML payload itself.
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
# VOUCHER DETAIL - single accounting voucher, all ledger lines
#
# Used when a user drills into one transaction from a Ledger report
# row (date + voucher type + voucher number identify it uniquely
# enough in practice). Returns every ledger allocation in that
# voucher, not just the ledger being browsed, so the frontend can
# render Tally's "Accounting Voucher Alteration" style screen.
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

    # Narrow the collection to the voucher's own date (a single day)
    # so Tally doesn't have to scan the whole company's vouchers -
    # the type/number formula filter below then pins the exact one.
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
# STOCK SUMMARY
# ============================================================

def build_stock_summary_request(
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
        <TYPE>Collection</TYPE>
        <ID>Stock Summary</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
                {to_date_xml}

            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Stock Summary">
                        <TYPE>Stock Item</TYPE>

                        <FETCH>
                            NAME,
                            PARENT,
                            BASEUNITS,
                            OPENINGBALANCE,
                            OPENINGVALUE,
                            CLOSINGBALANCE,
                            CLOSINGVALUE,
                            RATE
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# STOCK ITEM
# ============================================================

def build_stock_item_request(
    company_name: str | None = None,
    stock_item_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> str:

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    filter_xml = ""

    if stock_item_name:
        safe_name = escape(stock_item_name)

        filter_xml = f"""
                        <FILTER>StockItemFilter</FILTER>
        """

        system_formula = f"""
                    <SYSTEM TYPE="Formulae"
                            NAME="StockItemFilter">
                        $Name = "{safe_name}"
                    </SYSTEM>
        """
    else:
        system_formula = ""

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Stock Item Details</ID>
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

                    <COLLECTION NAME="Stock Item Details">
                        <TYPE>Stock Item</TYPE>

                        {filter_xml}

                        <FETCH>
                            NAME,
                            PARENT,
                            BASEUNITS,
                            OPENINGBALANCE,
                            OPENINGVALUE,
                            CLOSINGBALANCE,
                            CLOSINGVALUE,
                            RATE
                        </FETCH>

                    </COLLECTION>

                    {system_formula}

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# STOCK GROUPS
# ============================================================

def build_stock_group_request(
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Stock Groups</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Stock Groups">
                        <TYPE>Stock Group</TYPE>

                        <FETCH>
                            NAME,
                            PARENT,
                            ISADDABLE,
                            BASEUNITS
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# STOCK CATEGORIES
# ============================================================

def build_stock_category_request(
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Stock Categories</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Stock Categories">
                        <TYPE>Stock Category</TYPE>

                        <FETCH>
                            NAME,
                            PARENT
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# GODOWNS
# ============================================================

def build_godown_request(
    company_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Godowns</ID>
    </HEADER>

    <BODY>
        <DESC>

            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>

                {company_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Godowns">
                        <TYPE>Godown</TYPE>

                        <FETCH>
                            NAME,
                            PARENT,
                            ISINTERNAL
                        </FETCH>

                    </COLLECTION>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# STOCK MOVEMENT
# ============================================================

def build_stock_movement_request(
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    stock_item_name: str | None = None,
) -> str:

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    if stock_item_name:
        safe_stock_item = escape(stock_item_name)

        filter_xml = """
                        <FILTER>StockMovementItemFilter</FILTER>
        """

        system_formula = f"""
                    <SYSTEM TYPE="Formulae"
                            NAME="StockMovementItemFilter">
                        $StockItemName = "{safe_stock_item}"
                    </SYSTEM>
        """
    else:
        filter_xml = ""
        system_formula = ""

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Stock Movement</ID>
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

                    <COLLECTION NAME="Stock Movement">
                        <TYPE>Voucher</TYPE>

                        {filter_xml}

                        <FETCH>
                            DATE,
                            GUID,
                            VOUCHERTYPENAME,
                            VOUCHERNUMBER,
                            REFERENCE,
                            PARTYLEDGERNAME,
                            PARTYNAME,
                            NARRATION,
                            ALLINVENTORYENTRIES.*
                        </FETCH>

                    </COLLECTION>

                    {system_formula}

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# INVENTORY REGISTER
# ============================================================

def build_inventory_register_request(
    voucher_type: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> str:

    safe_voucher_type = escape(voucher_type)

    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Inventory Register</ID>
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

                    <COLLECTION NAME="Inventory Register">
                        <TYPE>Voucher</TYPE>

                        <FILTER>InventoryVoucherTypeFilter</FILTER>

                        <FETCH>
                            DATE,
                            GUID,
                            VOUCHERTYPENAME,
                            VOUCHERNUMBER,
                            REFERENCE,
                            PARTYLEDGERNAME,
                            PARTYNAME,
                            NARRATION,
                            ALLINVENTORYENTRIES.*
                        </FETCH>

                    </COLLECTION>

                    <SYSTEM TYPE="Formulae"
                            NAME="InventoryVoucherTypeFilter">
                        $VoucherTypeName = "{safe_voucher_type}"
                    </SYSTEM>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""


# ============================================================
# STOCK ITEM LIST (chatbot)
# ============================================================

def build_stock_item_list_request(
    company_name: str | None = None,
):
    """
    Build a Tally request to fetch stock item details.
    """

    company_xml = build_company_variable(company_name)

    # Native methods tell Tally which stock fields we need.
    # Keeping this list small also avoids fetching unnecessary data.
    return f"""
    <ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>Chat Stock Item Collection</ID>
        </HEADER>

        <BODY>
            <DESC>
                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    {company_xml}
                </STATICVARIABLES>

                <TDL>
                    <TDLMESSAGE>
                        <COLLECTION NAME="Chat Stock Item Collection">
                            <TYPE>StockItem</TYPE>

                            <NATIVEMETHOD>
                                Name,
                                Parent,
                                BaseUnits,
                                OpeningBalance,
                                OpeningRate,
                                OpeningValue,
                                ClosingBalance,
                                ClosingRate,
                                ClosingValue
                            </NATIVEMETHOD>
                        </COLLECTION>
                    </TDLMESSAGE>
                </TDL>
            </DESC>
        </BODY>
    </ENVELOPE>
    """


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
