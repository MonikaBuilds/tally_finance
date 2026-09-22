from app.chatbot.resolver import (
    normalize_name,
    resolve_company_name,
    resolve_party_name
)


def test_normalize_business_name():
    assert (
        normalize_name(
            "Eagle Paradise Pvt. Ltd."
        )
        == "eagle paradise"
    )


def test_exact_company_match():
    result = resolve_company_name(
        "ABC Company",
        [
            "ABC Company",
            "XYZ Company"
        ]
    )

    assert result.status == "resolved"
    assert result.value == "ABC Company"


def test_company_case_insensitive():
    result = resolve_company_name(
        "abc company",
        [
            "ABC Company",
            "XYZ Company"
        ]
    )

    assert result.status == "resolved"
    assert result.value == "ABC Company"


def test_company_suffix_can_be_omitted():
    result = resolve_company_name(
        "Eagle Paradise",
        [
            "Eagle Paradise Pvt. Ltd.",
            "Apex Office Solutions"
        ]
    )

    assert result.status == "resolved"
    assert (
        result.value
        == "Eagle Paradise Pvt. Ltd."
    )


def test_partial_party_name():
    result = resolve_party_name(
        "Apex",
        [
            "Apex Office Solutions",
            "Eagle Paradise Pvt. Ltd."
        ]
    )

    assert result.status == "resolved"
    assert (
        result.value
        == "Apex Office Solutions"
    )


def test_unknown_party():
    result = resolve_party_name(
        "Unknown Customer",
        [
            "Apex Office Solutions",
            "Eagle Paradise Pvt. Ltd."
        ]
    )

    assert result.status == "not_found"
    assert result.value is None


def test_ambiguous_party():
    result = resolve_party_name(
        "Apex",
        [
            "Apex Office Solutions",
            "Apex Technologies",
            "Eagle Paradise Pvt. Ltd."
        ]
    )

    assert result.status == "ambiguous"
    assert result.value is None
    assert len(result.matches) == 2