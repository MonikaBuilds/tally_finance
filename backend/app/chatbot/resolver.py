import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class ResolutionResult:
    status: str
    value: str | None = None
    matches: list[str] | None = None


def normalize_name(value: str | None) -> str:
    """
    Normalize company/party names for safe comparison.

    Example:
    'Eagle Paradise Pvt. Ltd.'
        -> 'eagle paradise'
    """

    if not value:
        return ""

    normalized = value.strip().lower()

    # Common business suffixes that users may omit.
    suffix_patterns = (
        r"\bpvt\.?\b",
        r"\bprivate\b",
        r"\bltd\.?\b",
        r"\blimited\b",
        r"\bllp\b",
    )

    for pattern in suffix_patterns:
        normalized = re.sub(
            pattern,
            " ",
            normalized,
            flags=re.IGNORECASE
        )

    # Remove punctuation while keeping letters/numbers.
    normalized = re.sub(
        r"[^a-z0-9\s]",
        " ",
        normalized
    )

    # Collapse repeated spaces.
    normalized = re.sub(
        r"\s+",
        " ",
        normalized
    )

    return normalized.strip()


def _similarity(
    first: str,
    second: str
) -> float:
    return SequenceMatcher(
        None,
        first,
        second
    ).ratio()


def resolve_name(
    requested_name: str,
    available_names: list[str]
) -> ResolutionResult:
    """
    Resolve a user-provided name against names that actually
    exist in Tally.

    Resolution order:

    1. Exact original-name match
    2. Exact normalized-name match
    3. Unique partial match
    4. Unique high-confidence fuzzy match
    5. Ambiguous / not found

    The resolver never silently chooses between multiple
    possible matches.
    """

    requested_name = (
        requested_name.strip()
        if requested_name
        else ""
    )

    if not requested_name:
        return ResolutionResult(
            status="invalid",
            value=None,
            matches=[]
        )

    cleaned_available_names = [
        name.strip()
        for name in available_names
        if isinstance(name, str)
        and name.strip()
    ]

    if not cleaned_available_names:
        return ResolutionResult(
            status="not_found",
            value=None,
            matches=[]
        )

    # --------------------------------------------------
    # 1. Exact original-name match
    # --------------------------------------------------

    exact_matches = [
        name
        for name in cleaned_available_names
        if name.casefold()
        == requested_name.casefold()
    ]

    if len(exact_matches) == 1:
        return ResolutionResult(
            status="resolved",
            value=exact_matches[0],
            matches=exact_matches
        )

    # --------------------------------------------------
    # 2. Exact normalized-name match
    # --------------------------------------------------

    normalized_requested = normalize_name(
        requested_name
    )

    if not normalized_requested:
        return ResolutionResult(
            status="invalid",
            value=None,
            matches=[]
        )

    normalized_matches = [
        name
        for name in cleaned_available_names
        if normalize_name(name)
        == normalized_requested
    ]

    if len(normalized_matches) == 1:
        return ResolutionResult(
            status="resolved",
            value=normalized_matches[0],
            matches=normalized_matches
        )

    if len(normalized_matches) > 1:
        return ResolutionResult(
            status="ambiguous",
            value=None,
            matches=normalized_matches
        )

    # --------------------------------------------------
    # 3. Partial match
    # --------------------------------------------------

    partial_matches = []

    for name in cleaned_available_names:
        normalized_available = normalize_name(
            name
        )

        if (
            normalized_requested
            in normalized_available
            or normalized_available
            in normalized_requested
        ):
            partial_matches.append(name)

    if len(partial_matches) == 1:
        return ResolutionResult(
            status="resolved",
            value=partial_matches[0],
            matches=partial_matches
        )

    if len(partial_matches) > 1:
        return ResolutionResult(
            status="ambiguous",
            value=None,
            matches=partial_matches
        )

    # --------------------------------------------------
    # 4. Conservative fuzzy matching
    # --------------------------------------------------

    scored_matches = []

    for name in cleaned_available_names:
        normalized_available = normalize_name(
            name
        )

        score = _similarity(
            normalized_requested,
            normalized_available
        )

        if score >= 0.85:
            scored_matches.append(
                (name, score)
            )

    scored_matches.sort(
        key=lambda item: item[1],
        reverse=True
    )

    if not scored_matches:
        return ResolutionResult(
            status="not_found",
            value=None,
            matches=[]
        )

    # Only one confident candidate.
    if len(scored_matches) == 1:
        return ResolutionResult(
            status="resolved",
            value=scored_matches[0][0],
            matches=[
                scored_matches[0][0]
            ]
        )

    best_name, best_score = scored_matches[0]
    second_name, second_score = scored_matches[1]

    # Resolve only when the best candidate is clearly better.
    if (
        best_score >= 0.90
        and (
            best_score
            - second_score
        ) >= 0.08
    ):
        return ResolutionResult(
            status="resolved",
            value=best_name,
            matches=[
                best_name
            ]
        )

    return ResolutionResult(
        status="ambiguous",
        value=None,
        matches=[
            item[0]
            for item in scored_matches[:5]
        ]
    )


def resolve_company_name(
    requested_name: str,
    company_names: list[str]
) -> ResolutionResult:
    """
    Resolve a company name against actual Tally companies.
    """

    return resolve_name(
        requested_name=requested_name,
        available_names=company_names
    )


def resolve_party_name(
    requested_name: str,
    party_names: list[str]
) -> ResolutionResult:
    """
    Resolve a customer/supplier/party name against actual
    party names retrieved from Tally.
    """

    return resolve_name(
        requested_name=requested_name,
        available_names=party_names
    )