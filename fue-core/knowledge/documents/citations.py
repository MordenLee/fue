"""Citation format renderers.

Each function takes a Citation ORM instance and returns a formatted string
in the requested citation style.  These are intentionally simple rule-based
renderers — no external dependency required.

Supported styles:
    apa       — APA 7th edition
    mla       — MLA 9th edition
    chicago   — Chicago 17th (author-date variant)
    gb_t7714  — GB/T 7714-2015 (Chinese national standard)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowledge.documents.models import Citation


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _join_authors_apa(authors: list[str]) -> str:
    """Last, F. M. format joined with commas, '& ' before last."""
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= 20:
        return ", ".join(authors[:-1]) + ", & " + authors[-1]
    # APA: first 19, ellipsis, last
    return ", ".join(authors[:19]) + ", ... " + authors[-1]


def _join_authors_mla(authors: list[str]) -> str:
    """First author "Last, First"; rest "First Last". et al. after 3."""
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= 3:
        return authors[0] + ", et al." if len(authors) > 2 else authors[0] + ", and " + authors[1]
    return authors[0] + ", et al."


def _join_authors_chicago(authors: list[str]) -> str:
    """Last, First, and First Last. Up to 3 names; then et al."""
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) <= 3:
        return ", ".join(authors[:-1]) + ", and " + authors[-1]
    return authors[0] + " et al."


def _join_authors_gb(authors: list[str]) -> str:
    """GB/T 7714: author names separated by commas; et al. (等) after 3."""
    if not authors:
        return ""
    if len(authors) <= 3:
        return ", ".join(authors)
    return ", ".join(authors[:3]) + ", 等"


# ---------------------------------------------------------------------------
# Style renderers
# ---------------------------------------------------------------------------

def format_apa(c: "Citation") -> str:
    """APA 7th edition."""
    parts: list[str] = []
    authors = c.authors or []
    year_str = f"({c.year})" if c.year else "(n.d.)"

    # Authors. (Year).
    if authors:
        parts.append(f"{_join_authors_apa(authors)}. {year_str}.")
    else:
        parts.append(f"{year_str}.")

    # Title.
    if c.title:
        if c.citation_type in ("article", "chapter", "conference", "thesis"):
            parts.append(f"{c.title}.")
        else:
            parts.append(f"*{c.title}*.")

    # Source
    if c.citation_type == "article":
        if c.source:
            vol = f", *{c.volume}*" if c.volume else ""
            iss = f"({c.issue})" if c.issue else ""
            pg  = f", {c.pages}" if c.pages else ""
            parts.append(f"*{c.source}*{vol}{iss}{pg}.")
    elif c.citation_type in ("book", "thesis"):
        if c.publisher:
            parts.append(f"{c.publisher}.")
    elif c.citation_type == "website":
        if c.source:
            parts.append(f"{c.source}.")
        if c.url:
            acc = f" Retrieved {c.accessed_date}," if c.accessed_date else ""
            parts.append(f"{acc} from {c.url}")

    if c.doi and c.citation_type != "website":
        parts.append(f"https://doi.org/{c.doi.lstrip('https://doi.org/')}")

    return " ".join(parts)


def format_mla(c: "Citation") -> str:
    """MLA 9th edition."""
    parts: list[str] = []
    authors = c.authors or []

    if authors:
        parts.append(f"{_join_authors_mla(authors)}.")

    if c.title:
        if c.citation_type in ("article", "chapter", "conference"):
            parts.append(f'"{c.title}."')
        else:
            parts.append(f"*{c.title}*.")

    if c.source:
        parts.append(f"*{c.source}*,")

    vol_iss = ""
    if c.volume:
        vol_iss += f"vol. {c.volume}"
    if c.issue:
        vol_iss += (", " if vol_iss else "") + f"no. {c.issue}"
    if vol_iss:
        parts.append(vol_iss + ",")

    if c.year:
        parts.append(f"{c.year},")

    if c.pages:
        parts.append(f"pp. {c.pages}.")

    if c.doi:
        parts.append(f"https://doi.org/{c.doi.lstrip('https://doi.org/')}")
    elif c.url:
        acc = f" Accessed {c.accessed_date}." if c.accessed_date else ""
        parts.append(c.url + "." + acc)

    return " ".join(parts)


def format_chicago(c: "Citation") -> str:
    """Chicago 17th — author-date variant."""
    parts: list[str] = []
    authors = c.authors or []

    if authors:
        parts.append(f"{_join_authors_chicago(authors)}.")

    if c.year:
        parts.append(f"{c.year}.")

    if c.title:
        if c.citation_type in ("article", "chapter", "conference"):
            parts.append(f'"{c.title}."')
        else:
            parts.append(f"*{c.title}*.")

    if c.source:
        vol = f" {c.volume}" if c.volume else ""
        iss = f", no. {c.issue}" if c.issue else ""
        pg  = f": {c.pages}" if c.pages else ""
        parts.append(f"*{c.source}*{vol}{iss}{pg}.")

    if c.publisher:
        parts.append(f"{c.publisher}.")

    if c.doi:
        parts.append(f"https://doi.org/{c.doi.lstrip('https://doi.org/')}")
    elif c.url:
        parts.append(c.url + ".")

    return " ".join(parts)


def format_gb_t7714(c: "Citation") -> str:
    """GB/T 7714-2015 (顺序编码制基础格式)."""
    parts: list[str] = []
    authors = c.authors or []

    if authors:
        parts.append(f"{_join_authors_gb(authors)}.")

    if c.title:
        type_mark = {
            "article": "[J]", "book": "[M]", "chapter": "[M]",
            "thesis": "[D]", "conference": "[C]", "website": "[EB/OL]",
        }.get(c.citation_type, "[Z]")
        parts.append(f"{c.title}{type_mark}.")

    if c.source:
        parts.append(f"{c.source},")

    if c.year:
        vol = f", {c.volume}" if c.volume else ""
        iss = f"({c.issue})" if c.issue else ""
        pg  = f": {c.pages}" if c.pages else ""
        parts.append(f"{c.year}{vol}{iss}{pg}.")

    if c.doi:
        parts.append(f"DOI: {c.doi}.")
    elif c.url:
        acc = f"[{c.accessed_date}]" if c.accessed_date else ""
        parts.append(f"{c.url}{acc}.")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Dispatch table — easy to extend
# ---------------------------------------------------------------------------

FORMATTERS: dict[str, object] = {
    "apa":      format_apa,
    "mla":      format_mla,
    "chicago":  format_chicago,
    "gb_t7714": format_gb_t7714,
}

SUPPORTED_STYLES: list[str] = list(FORMATTERS.keys())


def format_citation(c: "Citation", style: str) -> str:
    """Format *c* in the given *style*.  Raises ValueError for unknown styles.

    If the citation has a non-empty ``raw_citation`` value it is treated as a
    user-supplied override and returned verbatim, bypassing the rule-based
    renderers.  This allows the inline editor in DocumentTable to persist
    free-form edits across reloads.
    """
    if c.raw_citation and c.raw_citation.strip():
        return c.raw_citation.strip()
    # If no meaningful bibliographic data, return empty rather than '(n.d.).' etc.
    if not any([c.title, c.authors, c.year, c.source, c.doi, c.isbn, c.url]):
        return ""
    fn = FORMATTERS.get(style.lower())
    if fn is None:
        raise ValueError(f"Unknown citation style '{style}'. Supported: {', '.join(SUPPORTED_STYLES)}")
    return fn(c)  # type: ignore[call-arg]
