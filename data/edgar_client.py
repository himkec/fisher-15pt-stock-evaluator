"""
SEC EDGAR API client — free tier only.
Endpoints used:
  - EDGAR BROWSE  → CIK resolution
  - data.sec.gov/submissions  → filing history
  - data.sec.gov/api/xbrl/companyfacts  → XBRL structured data
  - efts.sec.gov/LATEST/search-index  → full-text filing search
  - www.sec.gov/Archives/edgar/data  → raw filing documents
"""

import re
import time
import html
import hashlib
import requests
import xml.etree.ElementTree as ET
from typing import Any

from config.settings import (
    EDGAR_BROWSE_URL,
    EDGAR_SUBMISSIONS_URL,
    EDGAR_FACTS_URL,
    EFTS_SEARCH_URL,
    EDGAR_ARCHIVES_URL,
    EDGAR_USER_AGENT,
    EDGAR_REQUEST_INTERVAL,
    CACHE_TTL_SECONDS,
    CACHE_TTL_FILING,
    TEN_K_CHAR_LIMIT,
    PROXY_CHAR_LIMIT,
)
from data import cache


class EDGARError(Exception):
    pass


def _headers() -> dict:
    return {"User-Agent": EDGAR_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _get(url: str, params: dict | None = None, timeout: int = 20) -> requests.Response:
    time.sleep(EDGAR_REQUEST_INTERVAL)
    resp = requests.get(url, params=params, headers=_headers(), timeout=timeout)
    if resp.status_code != 200:
        raise EDGARError(f"EDGAR returned HTTP {resp.status_code} for {url}")
    return resp


def _strip_html(raw: str) -> str:
    """Strip HTML tags and decode entities; collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── CIK resolution ────────────────────────────────────────────────────────────

def resolve_cik(ticker: str) -> str:
    """
    Return the 10-digit zero-padded CIK for a ticker.
    Primary: EDGAR BROWSE Atom XML.
    Fallback: EFTS full-text search.
    """
    cache_key = f"edgar:cik"
    cached = cache.get(cache_key, ticker)
    if cached:
        return cached

    # Primary lookup
    try:
        resp = _get(
            EDGAR_BROWSE_URL,
            params={
                "action": "getcompany",
                "CIK": ticker,
                "type": "10-K",
                "dateb": "",
                "owner": "include",
                "count": "5",
                "output": "atom",
            },
        )
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        cik_elem = root.find(".//atom:company-info/atom:cik", ns)
        if cik_elem is None:
            # Try without namespace
            cik_elem = root.find(".//cik")
        if cik_elem is not None and cik_elem.text:
            cik = cik_elem.text.strip().zfill(10)
            cache.set(cache_key, ticker, cik, ttl=CACHE_TTL_FILING)
            return cik
    except Exception:
        pass

    # Fallback: EFTS search
    try:
        resp = _get(EFTS_SEARCH_URL, params={"q": f'"{ticker}"', "forms": "10-K"})
        hits = resp.json().get("hits", {}).get("hits", [])
        if hits:
            entity_id = hits[0].get("_source", {}).get("entity_id", "")
            if entity_id:
                cik = str(entity_id).zfill(10)
                cache.set(cache_key, ticker, cik, ttl=CACHE_TTL_FILING)
                return cik
    except Exception:
        pass

    raise EDGARError(
        f"Could not resolve CIK for ticker '{ticker}'. "
        "Qualitative scoring (Points 7-15) will be unavailable."
    )


# ── Submissions / filing index ─────────────────────────────────────────────────

def get_submissions(cik: str) -> dict:
    """
    Fetch the submissions JSON for a CIK.
    Returns the full dict including filings.recent arrays.
    """
    ticker_key = cik  # cik is unique per company
    cache_key = f"edgar:submissions:{cik}"
    cached = cache.get(cache_key, ticker_key)
    if cached:
        return cached

    url = f"{EDGAR_SUBMISSIONS_URL}/CIK{cik}.json"
    resp = _get(url)
    data = resp.json()
    cache.log_request("edgar", f"submissions/{cik}")
    cache.set(cache_key, ticker_key, data, ttl=CACHE_TTL_SECONDS)
    return data


def _find_latest_accession(submissions: dict, form_type: str) -> tuple[str, str] | tuple[None, None]:
    """
    Scan submissions.filings.recent for the latest filing of form_type.
    Returns (accession_number_dashes, primary_document) or (None, None).
    """
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    filing_dates = recent.get("filingDate", [])

    for i, form in enumerate(forms):
        if form == form_type:
            accession = accessions[i]
            doc = primary_docs[i] if i < len(primary_docs) else ""
            return accession, doc

    return None, None


# ── Filing document retrieval ─────────────────────────────────────────────────

def get_filing_text(cik: str, accession_number: str, primary_doc: str, char_limit: int) -> str:
    """
    Download a filing document and return cleaned plain text up to char_limit.
    Cached permanently (filings are immutable).
    """
    accession_clean = accession_number.replace("-", "")
    cache_key = f"edgar:filing:{accession_clean}"
    cached = cache.get(cache_key, cik)
    if cached:
        return cached

    url = f"{EDGAR_ARCHIVES_URL}/{cik}/{accession_clean}/{primary_doc}"
    try:
        resp = _get(url, timeout=30)
        text = _strip_html(resp.text)[:char_limit]
    except EDGARError:
        # Try the index page to find the main document
        text = _try_index_fallback(cik, accession_clean, char_limit)

    cache.log_request("edgar", f"filing/{accession_number}", cik)
    cache.set(cache_key, cik, text, ttl=CACHE_TTL_FILING)
    return text


def _try_index_fallback(cik: str, accession_clean: str, char_limit: int) -> str:
    """Fetch filing index and download the first .htm document found."""
    index_url = f"{EDGAR_ARCHIVES_URL}/{cik}/{accession_clean}/{accession_clean}-index.htm"
    try:
        resp = _get(index_url, timeout=20)
        # Find first .htm link in the index
        match = re.search(r'href="([^"]+\.htm)"', resp.text, re.IGNORECASE)
        if match:
            doc_url = f"https://www.sec.gov{match.group(1)}"
            doc_resp = _get(doc_url, timeout=30)
            return _strip_html(doc_resp.text)[:char_limit]
    except Exception:
        pass
    return ""


# ── XBRL financial facts ──────────────────────────────────────────────────────

def get_xbrl_facts(cik: str) -> dict:
    """
    Fetch the full XBRL company facts JSON.
    Extracts a subset of key US-GAAP concepts for scoring.
    """
    cache_key = f"edgar:xbrl_facts:{cik}"
    cached = cache.get(cache_key, cik)
    if cached:
        return cached

    url = f"{EDGAR_FACTS_URL}/CIK{cik}.json"
    resp = _get(url, timeout=30)
    raw = resp.json()
    cache.log_request("edgar", f"xbrl_facts/{cik}", cik)

    facts = _extract_xbrl_concepts(raw)
    cache.set(cache_key, cik, facts, ttl=CACHE_TTL_SECONDS)
    return facts


_XBRL_CONCEPTS = [
    "ResearchAndDevelopmentExpense",
    "CommonStockSharesOutstanding",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "OperatingIncomeLoss",
    "NetIncomeLoss",
    "CapitalExpenditureDiscontinuedOperations",
    "PaymentsToAcquirePropertyPlantAndEquipment",
]


def _extract_xbrl_concepts(raw: dict) -> dict:
    """
    Pull the 5 most recent 10-K annual values for each concept.
    Returns {concept: [{end, value, form}]}
    """
    us_gaap = raw.get("facts", {}).get("us-gaap", {})
    result = {}
    for concept in _XBRL_CONCEPTS:
        if concept not in us_gaap:
            continue
        units = us_gaap[concept].get("units", {})
        # Prefer USD units
        entries = units.get("USD", units.get("shares", []))
        # Filter to 10-K annual filings only, sort by end date desc
        annual = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY"]
        annual.sort(key=lambda x: x.get("end", ""), reverse=True)
        result[concept] = annual[:5]
    return result


# ── EFTS full-text search ─────────────────────────────────────────────────────

def search_filings(query: str, entity_name: str, form_type: str, years_back: int = 3) -> list[dict]:
    """
    Full-text search across SEC filings.
    Returns list of {accession, filed, description}.
    """
    from datetime import datetime, timedelta
    start_dt = (datetime.utcnow() - timedelta(days=years_back * 365)).strftime("%Y-%m-%d")
    end_dt = datetime.utcnow().strftime("%Y-%m-%d")

    query_hash = hashlib.sha256(f"{query}|{entity_name}|{form_type}".encode()).hexdigest()[:12]
    cache_key = f"edgar:efts:{query_hash}"
    cached = cache.get(cache_key, entity_name)
    if cached is not None:
        return cached

    params = {
        "q": f'"{query}"',
        "dateRange": "custom",
        "startdt": start_dt,
        "enddt": end_dt,
        "forms": form_type,
        "entity": entity_name,
    }
    try:
        resp = _get(EFTS_SEARCH_URL, params=params)
        hits = resp.json().get("hits", {}).get("hits", [])
        results = [
            {
                "accession": h.get("_id", ""),
                "filed": h.get("_source", {}).get("file_date", ""),
                "description": h.get("_source", {}).get("form_type", form_type),
            }
            for h in hits
        ]
    except Exception:
        results = []

    cache.set(cache_key, entity_name, results, ttl=CACHE_TTL_SECONDS)
    return results


# ── High-level convenience methods (used by scoring layer) ────────────────────

def get_latest_10k_text(ticker: str, cik: str, submissions: dict) -> str:
    """Return plain text of the most recent 10-K, up to TEN_K_CHAR_LIMIT chars."""
    accession, doc = _find_latest_accession(submissions, "10-K")
    if not accession:
        return ""
    return get_filing_text(cik, accession, doc, TEN_K_CHAR_LIMIT)


def get_latest_proxy_text(ticker: str, cik: str, submissions: dict) -> str:
    """Return plain text of the most recent DEF 14A proxy, up to PROXY_CHAR_LIMIT chars."""
    accession, doc = _find_latest_accession(submissions, "DEF 14A")
    if not accession:
        return ""
    return get_filing_text(cik, accession, doc, PROXY_CHAR_LIMIT)


def get_efts_hit_counts(company_name: str) -> dict[str, int]:
    """
    Run several pre-defined EFTS searches and return hit counts.
    Used as quantitative signals in Claude prompts for qualitative points.
    """
    searches = {
        "labor_dispute": ("labor dispute OR strike OR walkout OR NLRB", "10-K"),
        "restatement": ("restatement OR restated financial", ""),
        "sec_investigation": ("SEC investigation OR SEC subpoena OR DOJ investigation", "8-K"),
        "exec_departure": ("resigned OR departure OR terminated", "8-K"),
        "related_party": ("related party transaction", "DEF 14A"),
    }
    counts = {}
    for signal_name, (query, form) in searches.items():
        hits = search_filings(query, company_name, form, years_back=3)
        counts[signal_name] = len(hits)
    return counts
