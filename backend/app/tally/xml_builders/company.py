"""
Tally XML builders for company-related requests.
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