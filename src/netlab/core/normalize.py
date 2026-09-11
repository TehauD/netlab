"""Entity resolution and title taxonomy.

Two problems the raw export creates:

1. **Company fragmentation.** "Acme, Inc.", "Acme Inc", and "ACME" are three distinct
   strings and therefore three distinct clusters, which inflates company counts and
   deflates cluster sizes. We canonicalize with a deterministic rule cascade (no fuzzy
   matching) so results are reproducible across runs and machines.

2. **Free-text job titles.** Titles are unstructured. We map them onto two orthogonal
   axes -- an ordinal *seniority* ladder and a nominal *function* -- using ordered regex
   rules. Ordering matters: "VP of Engineering" must resolve to `executive`, not `manager`.

Both passes are intentionally rule-based rather than model-based: deterministic output,
zero inference cost, fully auditable, and no data leaves the machine.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable

from .models import SENIORITY_RANK, Connection

# --------------------------------------------------------------------------------------
# Company canonicalization
# --------------------------------------------------------------------------------------

_LEGAL_SUFFIX = re.compile(
    r"[,\s]+(?:inc|inc\.|llc|l\.l\.c\.|ltd|ltd\.|limited|corp|corp\.|corporation|co|co\.|"
    r"plc|gmbh|s\.a\.|sa|ag|bv|nv|pty|llp|lp|pc|pllc)\s*$",
    re.IGNORECASE,
)
_PARENTHETICAL = re.compile(r"\s*\((?:[^)]*)\)\s*$")
_PUNCT = re.compile(r"[\u2018\u2019\u201c\u201d`'\"]")
_WS = re.compile(r"\s+")

# Applied after generic cleanup. Keys must already be canonical-cased output of the cascade.
CANONICAL_ALIASES: dict[str, str] = {
    "ibm corporation": "IBM",
    "international business machines": "IBM",
    "alphabet": "Google",
    "meta platforms": "Meta",
    "facebook": "Meta",
    "microsoft corporation": "Microsoft",
    "amazon web services": "Amazon",
    "aws": "Amazon",
    "jp morgan chase": "JPMorgan Chase",
    "jpmorgan": "JPMorgan Chase",
    "deloitte consulting": "Deloitte",
    "ey": "EY",
    "ernst & young": "EY",
    "pwc": "PwC",
    "pricewaterhousecoopers": "PwC",
    "kpmg llp": "KPMG",
    "self employed": "Self-Employed",
    "self-employed": "Self-Employed",
    "freelance": "Self-Employed",
    "independent": "Self-Employed",
    "n/a": "",
    "none": "",
    "-": "",
}


def canonical_company(raw: str) -> str:
    """Collapse trivial spelling variants of an employer name to a single canonical key."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", raw)
    s = _PUNCT.sub("", s)
    s = _WS.sub(" ", s).strip(" \t,-–—")
    if not s:
        return ""
    s = _PARENTHETICAL.sub("", s)
    # Strip up to two stacked legal suffixes: "Acme Holdings Ltd, Inc."
    for _ in range(2):
        stripped = _LEGAL_SUFFIX.sub("", s).strip(" ,")
        if stripped == s:
            break
        s = stripped
    if not s:
        return ""
    alias = CANONICAL_ALIASES.get(s.lower())
    if alias is not None:
        return alias
    # Preserve intentional acronyms (NASA, IBM); title-case only SHOUTED multi-word names.
    if s.isupper() and len(s) > 4 and " " in s:
        s = s.title()
    return s


# --------------------------------------------------------------------------------------
# Seniority ladder -- ORDER IS SIGNIFICANT (first match wins)
# --------------------------------------------------------------------------------------

_SENIORITY_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("founder_owner", re.compile(r"\b(founder|co-?founder|owner|proprietor|managing partner|partner)\b", re.I)),
    ("executive", re.compile(r"\b(chief|c[etofimdpr]o\b|cxo|president|vice president|vp|svp|evp|avp|"
                             r"head of|global head|general manager|gm|board member|managing director)\b", re.I)),
    ("director", re.compile(r"\b(director|dir\.|sr\.? director|senior director|dean|chair)\b", re.I)),
    ("manager", re.compile(r"\b(manager|mgr|supervisor|team lead|team leader|foreman|superintendent)\b", re.I)),
    ("staff_principal", re.compile(r"\b(principal|staff|distinguished|fellow|architect|lead|master)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?|sme|specialist iii|iii)\b", re.I)),
    ("student", re.compile(r"\b(student|intern|trainee|apprentice|resident|fellowship|candidate|phd)\b", re.I)),
    ("individual_contributor", re.compile(r"\b(engineer|developer|analyst|scientist|designer|consultant|"
                                          r"associate|coordinator|administrator|technician|nurse|rn|"
                                          r"representative|assistant|officer|advisor|agent|clerk|writer|"
                                          r"recruiter|accountant|attorney|pharmacist|therapist|teacher|controller|"
                                          r"counsel|specialist|paralegal|"
                                          r"professor|instructor|manager i\b)\b", re.I)),
]


def classify_seniority(title: str) -> tuple[str, int]:
    """Map a free-text title onto the ordinal seniority ladder. Returns (label, rank)."""
    if not title:
        return "unknown", SENIORITY_RANK["unknown"]
    t = title.lower()
    for label, pattern in _SENIORITY_RULES:
        if pattern.search(t):
            return label, SENIORITY_RANK[label]
    return "unknown", SENIORITY_RANK["unknown"]


# --------------------------------------------------------------------------------------
# Functional domain -- nominal, first match wins
# --------------------------------------------------------------------------------------

_FUNCTION_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("data_ai", re.compile(r"\b(data scien|machine learning|ml engineer|ai\b|artificial intelligence|"
                           r"data engineer|analytics|statistic|biostat|nlp|mlops|data analyst|"
                           r"business intelligence|bi developer|research scientist)", re.I)),
    ("engineering", re.compile(r"\b(software|engineer|engineering|developer|development|devops|sre|programmer|architect|"
                               r"infrastructure|platform|cloud|security|cyber|qa|full.?stack|"
                               r"backend|frontend|systems)", re.I)),
    ("product", re.compile(r"\b(product manager|product owner|product lead|cpo|product manage|"
                           r"program manager|technical program|scrum|agile coach)", re.I)),
    ("design", re.compile(r"\b(design|ux|ui|user experience|creative|brand|illustrat|architect of record)", re.I)),
    ("healthcare", re.compile(r"\b(nurse|nursing|rn\b|bsn|physician|doctor|md\b|clinical|pharmac|patient|"
                              r"health|medical|surgeon|therap|radiolog|care team|epic analyst)", re.I)),
    ("sales", re.compile(r"\b(sales|account executive|account manager|business development|bdr|sdr|"
                         r"revenue|partnership|customer success|client)", re.I)),
    ("marketing", re.compile(r"\b(marketing|growth|seo|content|communications|brand manager|"
                             r"demand gen|social media|public relations|pr manager)", re.I)),
    ("finance", re.compile(r"\b(financ|account|audit|controller|treasur|investment|equity|banking|"
                           r"actuar|tax|cfo|fp&a)", re.I)),
    ("people_ops", re.compile(r"\b(human resources|hr\b|recruit|talent|people ops|people operations|"
                              r"chro|benefits|compensation|learning and development|l&d)", re.I)),
    ("legal", re.compile(r"\b(legal|attorney|counsel|paralegal|compliance|contract|privacy officer|"
                         r"regulatory)", re.I)),
    ("operations", re.compile(r"\b(operations|supply chain|logistics|procurement|manufactur|"
                              r"quality|facilities|project manager|coo\b)", re.I)),
    ("education_research", re.compile(r"\b(professor|lecturer|teacher|instructor|research|faculty|"
                                      r"academic|postdoc|dean|principal investigator)", re.I)),
    ("executive_general", re.compile(r"\b(chief executive|ceo|president|owner|founder|general manager)", re.I)),
]


def classify_function(title: str) -> str:
    """Assign a functional domain label to a free-text title."""
    if not title:
        return "unclassified"
    for label, pattern in _FUNCTION_RULES:
        if pattern.search(title):
            return label
    return "unclassified"


def clean_title(raw: str) -> str:
    """Light normalization of the position string for display and tokenization."""
    if not raw:
        return ""
    s = unicodedata.normalize("NFKC", raw)
    s = _PUNCT.sub("", s)
    return _WS.sub(" ", s).strip(" \t,-–—|")


# --------------------------------------------------------------------------------------
# Enrichment pass
# --------------------------------------------------------------------------------------

def enrich(connections: Iterable[Connection]) -> list[Connection]:
    """Populate all derived fields in place. Idempotent -- safe to re-run."""
    out: list[Connection] = []
    for c in connections:
        c.company = canonical_company(c.company_raw)
        c.position = clean_title(c.position_raw)
        c.seniority, c.seniority_rank = classify_seniority(c.position)
        c.function = classify_function(c.position)
        out.append(c)
    return out


def resolution_gain(connections: Iterable[Connection]) -> dict[str, int]:
    """Quantify what canonicalization actually bought us -- reported in the UI.

    A high `merged` count is the justification for the normalization layer existing.
    """
    conns = list(connections)
    raw = Counter(c.company_raw.strip() for c in conns if c.company_raw.strip())
    canon = Counter(c.company for c in conns if c.company)
    return {
        "raw_distinct": len(raw),
        "canonical_distinct": len(canon),
        "merged": max(len(raw) - len(canon), 0),
    }
