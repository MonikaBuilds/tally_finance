"""
Company parser for Tally XML responses.

This module is responsible only for parsing company-related
information returned by Tally.

It does not create, calculate, or modify company information.
The values are taken directly from the Tally XML response.
"""

from app.tally.parsers.common import (
    parse_xml,
    _first_text,
    _text,
    format_tally_date,
)


# ============================================================
# COMPANY PARSER
# ============================================================

def parse_companies(xml_text: str):
    """
    Parse the list of companies returned by Tally.

    For every company, we read the available company details
    directly from the XML response.

    Returned information includes:
    - company name
    - GUID
    - books starting date
    - company starting date
    - GST registration type
    - GSTIN
    """

    # Convert the raw Tally XML response into an XML tree.
    root = parse_xml(xml_text)

    companies = []

    # Tally returns each company inside a COMPANY element.
    for company in root.findall(".//COMPANY"):

        # In some Tally responses the company name is available
        # as a child element.
        name = _first_text(
            company,
            "NAME",
        )

        # In other responses NAME may be an XML attribute.
        # Use it only when the child element did not contain a name.
        if not name:
            name = company.attrib.get(
                "NAME",
                "",
            )

        # A company without a name is not useful to callers,
        # so ignore that incomplete entry.
        if not name:
            continue

        company_data = {
            "name": name,

            # Unique company identifier returned by Tally.
            "guid": _text(
                company,
                "GUID",
            ),

            # Keep the date value from Tally but normalize its
            # technical date format for the API response.
            "books_from": format_tally_date(
                _text(
                    company,
                    "BOOKSFROM",
                )
            ),

            "starting_from": format_tally_date(
                _text(
                    company,
                    "STARTINGFROM",
                )
            ),

            # GST information is read directly from Tally.
            "gst_registration_type": _text(
                company,
                "GSTREGISTRATIONTYPE",
            ),

            "gstin": _text(
                company,
                "GSTIN",
            ),
        }

        companies.append(
            company_data
        )

    return {
        "success": True,
        "companies": companies,
        "count": len(companies),
    }