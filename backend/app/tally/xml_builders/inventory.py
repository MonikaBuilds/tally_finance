"""
Tally XML builders for inventory-related requests.
"""

from datetime import date
from xml.sax.saxutils import escape

from app.tally.xml_builders.common import (
    build_company_variable,
    _date_variable,
)


# ============================================================
# STOCK SUMMARY
# ============================================================
def build_stock_summary_request(
    company_name: str | None = None,
    to_date: date | None = None,
    from_date: date | None = None,
    include_godown_allocations: bool = False,
) -> str:
    company_xml = build_company_variable(company_name)
    from_date_xml = _date_variable("SVFROMDATE", from_date)
    to_date_xml = _date_variable("SVTODATE", to_date)

    # Per-godown opening allocations of each item. Only requested by
    # the Godown Summary, which needs to know where an item's stock
    # sits; every other caller keeps the original, lighter request.
    godown_fetch = (
        ",\n                            BATCHALLOCATIONS.*"
        if include_godown_allocations
        else ""
    )

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
                {from_date_xml}
                {to_date_xml}
            </STATICVARIABLES>

            <TDL>
                <TDLMESSAGE>

                    <COLLECTION NAME="Stock Summary">
                        <TYPE>Stock Item</TYPE>

                        <FETCH>
                            NAME,
                            PARENT,
                            CATEGORY,
                            BASEUNITS,
                            OPENINGBALANCE,
                            OPENINGRATE,
                            OPENINGVALUE,
                            CLOSINGBALANCE,
                            CLOSINGRATE,
                            CLOSINGVALUE{godown_fetch}
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
                            OPENINGRATE,
                            OPENINGVALUE,
                            CLOSINGBALANCE,
                            CLOSINGRATE,
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
                            ISCANCELLED,
                            ISOPTIONAL,
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
# STOCK GROUP ITEMS (Stock Group Summary -> items in that group)
# ============================================================

def build_stock_group_items_request(
    group_name: str,
    company_name: str | None = None,
    to_date: date | None = None,
) -> str:
    """
    Stock items belonging to a single Stock Group.

    Mirrors build_stock_item_request, but filters by $Parent
    (the stock group name) instead of $Name, matching Tally's
    "Stock Group Summary" drill-down into a group's items.
    """

    company_xml = build_company_variable(company_name)
    to_date_xml = _date_variable("SVTODATE", to_date)

    safe_group = escape(group_name)

    return f"""
<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Stock Group Items</ID>
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

                    <COLLECTION NAME="Stock Group Items">
                        <TYPE>Stock Item</TYPE>

                        <FILTER>StockGroupItemFilter</FILTER>

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

                    <SYSTEM TYPE="Formulae"
                            NAME="StockGroupItemFilter">
                        $Parent = "{safe_group}"
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

# ============================================================
# INVENTORY VOUCHER DETAIL
# ============================================================

def build_inventory_voucher_detail_request(
    voucher_type: str,
    voucher_number: str,
    voucher_date: date | None = None,
    company_name: str | None = None,
) -> str:
    """
    Fetch the inventory side of one voucher for the Stock/Inventory
    drill-down. This is separate from the accounting voucher request
    so existing Ledger/Voucher behaviour is not changed.
    """

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
        <ID>Inventory Voucher Detail</ID>
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
                    <COLLECTION NAME="Inventory Voucher Detail">
                        <TYPE>Voucher</TYPE>
                        <FILTER>InventoryVoucherDetailFilter</FILTER>

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
                            ALLINVENTORYENTRIES.*,
                            ALLLEDGERENTRIES.*
                        </FETCH>
                    </COLLECTION>

                    <SYSTEM TYPE="Formulae"
                            NAME="InventoryVoucherDetailFilter">
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
# INVENTORY REGISTER VOUCHERS (one row per voucher)
# ============================================================

def build_register_vouchers_request(
    voucher_type: str,
    company_name: str | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> str:
    """
    Vouchers of one voucher type, with the cancelled / optional flags
    and inventory entries (with units) that the Inventory Books
    registers need. Separate from build_inventory_register_request so
    existing callers are unchanged.
    """

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
        <ID>Register Vouchers</ID>
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

                    <COLLECTION NAME="Register Vouchers">
                        <TYPE>Voucher</TYPE>

                        <FILTER>RegisterVoucherTypeFilter</FILTER>

                        <FETCH>
                            DATE,
                            GUID,
                            VOUCHERTYPENAME,
                            VOUCHERNUMBER,
                            REFERENCE,
                            PARTYLEDGERNAME,
                            PARTYNAME,
                            NARRATION,
                            ISCANCELLED,
                            ISOPTIONAL,
                            ALLINVENTORYENTRIES.*
                        </FETCH>

                    </COLLECTION>

                    <SYSTEM TYPE="Formulae"
                            NAME="RegisterVoucherTypeFilter">
                        $VoucherTypeName = "{safe_voucher_type}"
                    </SYSTEM>

                </TDLMESSAGE>
            </TDL>

        </DESC>
    </BODY>
</ENVELOPE>
"""
