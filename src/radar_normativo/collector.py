"""Raccolta RSS/Atom e fonti ufficiali HTML/SPARQL."""
from __future__ import annotations

import hashlib
import json
import posixpath
import re
from calendar import timegm
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import feedparser

from radar_normativo.analysis import analyze_item
from radar_normativo.classifier import classify_topics

USER_AGENT = "RadarNormativo/1.1 (+https://github.com/vincenzopierri197-source/radar-normativo)"


def _first_text(entry: Any, *keys: str) -> str:
    for key in keys:
        value = entry.get(key)
        if value:
            return str(value).strip()
    return ""


def _canonical_url(value: str) -> str:
    """Normalizza URL senza cambiare query o identificatori dell'atto."""
    value = value.strip()
    parts = urlsplit(value)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return value
    path = posixpath.normpath(parts.path or "/")
    if parts.path.endswith("/") and not path.endswith("/"):
        path += "/"
    if parts.path.startswith("/") and not path.startswith("/"):
        path = "/" + path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment))


def _entry_title(entry: Any) -> str:
    """Rimuove il prefisso CELEX ridondante solo se dopo c'è un vero titolo."""
    title = _first_text(entry, "title")
    match = re.match(r"^CELEX:[^:]+:\s*(.+?)\s*$", title, flags=re.IGNORECASE)
    if match:
        cleaned_title = match.group(1).strip()
        if cleaned_title:
            return cleaned_title
    return title


def _entry_summary(entry: Any) -> str:
    summary = _first_text(entry, "summary", "description")
    if summary:
        return summary
    content = entry.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("value"):
                return str(part["value"]).strip()
    return ""


def _entry_date(entry: Any) -> str | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(timegm(parsed), tz=timezone.utc).isoformat()
    return _first_text(entry, "published", "updated") or None


def _download(url: str, accept: str) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    try:
        with urlopen(request, timeout=25) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                raise RuntimeError(f"HTTP {status} durante il download")
            payload = response.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} durante il download") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"errore di rete durante il download: {reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError("timeout durante il download (25 secondi)") from exc
    if not payload.strip():
        raise ValueError("il server ha restituito una risposta vuota")
    return payload


def _parse_feed(url: str) -> Any:
    """Scarica un feed con timeout e User-Agent espliciti, poi lo analizza."""
    return feedparser.parse(_download(
        url,
        "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    ))


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    months = {
        "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
        "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
        "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    }
    match = re.search(r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})\b", value, re.IGNORECASE)
    if match and match.group(2).lower() in months:
        try:
            return datetime(
                int(match.group(3)), months[match.group(2).lower()], int(match.group(1)),
                tzinfo=timezone.utc,
            )
        except ValueError:
            return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class _NewsHTMLParser(HTMLParser):
    """Estrae titoli, collegamenti e date da pagine ufficiali di archivio."""
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.in_heading = False
        self.heading: list[str] = []
        self.in_anchor = False
        self.anchor: list[str] = []
        self.anchor_href = ""
        self.events: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag.lower() in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.in_heading = True
            self.heading = []
        if tag.lower() == "a":
            self.in_anchor = True
            self.anchor = []
            self.anchor_href = attrs_dict.get("href") or ""

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self.in_heading:
            title = re.sub(r"\s+", " ", "".join(self.heading)).strip()
            if title and title.casefold() not in ("archivio news", "archivio novità"):
                self.events.append(("heading", title, ""))
            self.in_heading = False
        if tag == "a" and self.in_anchor:
            label = re.sub(r"\s+", " ", "".join(self.anchor)).strip()
            if self.anchor_href:
                self.events.append(("link", label, urljoin(self.base_url, self.anchor_href)))
            self.in_anchor = False

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.heading.append(data)
        if self.in_anchor:
            self.anchor.append(data)
        date_match = re.search(r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]+\s+\d{4}\b", data)
        if date_match:
            self.events.append(("date", date_match.group(0), ""))


def _parse_html_news(raw: bytes, base_url: str, charset: str = "utf-8") -> list[dict[str, Any]]:
    parser = _NewsHTMLParser(base_url)
    parser.feed(raw.decode(charset, errors="replace"))
    entries: list[dict[str, Any]] = []
    current_title = ""
    last_entry: dict[str, Any] | None = None
    for kind, value, link in parser.events:
        if kind == "heading":
            current_title = value.strip(' "“”')
        elif kind == "link" and link:
            label = value.casefold()
            if current_title and label in ("testo completo", "leggi", "approfondisci", ""):
                last_entry = {"title": current_title, "link": link, "published": "", "summary": ""}
                entries.append(last_entry)
            elif value and len(value) > 12 and not label.startswith(("rss", "home", "salta")):
                last_entry = {"title": value, "link": link, "published": "", "summary": ""}
                entries.append(last_entry)
        elif kind == "date" and last_entry and not last_entry["published"]:
            parsed = _parse_date(value)
            if parsed:
                last_entry["published"] = parsed.isoformat()
    return entries


def _parse_normattiva_site(url: str) -> list[dict[str, Any]]:
    """Usa un feed RSS se la pagina lo è già; altrimenti legge titoli e date HTML."""
    raw = _download(url, "application/rss+xml, application/atom+xml, application/xml, text/html, */*")
    parsed = feedparser.parse(raw)
    if parsed.entries:
        return list(parsed.entries)
    return _parse_html_news(raw, url)


def _senato_bindings_to_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    bindings = payload.get("results", {}).get("bindings", [])
    entries = []
    for row in bindings:
        title = row.get("titolo", {}).get("value", "").strip()
        date = _parse_date(row.get("dataPresentazione", {}).get("value", ""))
        link = row.get("ddl", {}).get("value", "").strip()
        if title and date:
            entries.append({"title": title, "link": link, "published": date.isoformat(), "summary": ""})
    return entries


def _parse_senato_sparql(endpoint: str) -> list[dict[str, Any]]:
    """Legge i DDL presentati al Senato dalla banca dati Linked Open Data."""
    since = (datetime.now(timezone.utc) - timedelta(hours=30)).date().isoformat()
    query = f"""PREFIX osr: <http://dati.senato.it/osr/>
SELECT DISTINCT ?ddl ?titolo ?dataPresentazione ?ramo ?presentatoTrasmesso
WHERE {{
  ?ddl a osr:Ddl ;
       osr:legislatura 19 ;
       osr:titolo ?titolo ;
       osr:dataPresentazione ?dataPresentazione ;
       osr:ramo ?ramo ;
       osr:presentatoTrasmesso ?presentatoTrasmesso .
  FILTER(str(?dataPresentazione) >= "{since}")
  FILTER(?ramo = "S")
  FILTER(?presentatoTrasmesso = "presentato")
}}
ORDER BY DESC(?dataPresentazione)
LIMIT 200
"""
    url = endpoint + "?" + urlencode({
        "query": query,
        "format": "application/sparql-results+json",
    })
    payload = json.loads(_download(url, "application/sparql-results+json, application/json").decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Risposta SPARQL del Senato non valida")
    return _senato_bindings_to_entries(payload)


def collect_sources(config_path: str | Path) -> dict[str, Any]:
    """Legge feed RSS, pagine ufficiali e fonti SPARQL, restituendo una scansione."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    items: dict[str, dict[str, Any]] = {}
    source_results: list[dict[str, Any]] = []

    for source in config.get("sources", []):
        name = str(source.get("name", "Fonte senza nome"))
        url = str(source.get("url", "")).strip()
        site = str(source.get("site", "")).strip()
        sparql = str(source.get("sparql", "")).strip()
        source_url = url or site or sparql
        required = source.get("required", True)
        if not source_url:
            source_results.append({"name": name, "ok": False, "required": required, "error": "URL mancante"})
            continue
        try:
            if url:
                feed = _parse_feed(url)
                if getattr(feed, "bozo", False) and not feed.entries:
                    raise ValueError(f"RSS/Atom non valido: {getattr(feed, 'bozo_exception', 'errore di parsing sconosciuto')}")
                entries = feed.entries
            elif site:
                entries = _parse_normattiva_site(site)
            else:
                entries = _parse_senato_sparql(sparql)

            count = 0
            for entry in entries:
                link = _canonical_url(_first_text(entry, "link"))
                title = _entry_title(entry)
                if not link or not title:
                    continue
                item_id = hashlib.sha256(link.encode("utf-8")).hexdigest()[:20]
                summary = _entry_summary(entry)
                item = {
                    "id": item_id,
                    "title": title,
                    "url": link,
                    "source_name": name,
                    "source_url": source_url,
                    "published_at": _entry_date(entry),
                    "summary": summary,
                    "language": source.get("language"),
                    "topics": classify_topics(title, summary),
                    "legal_status": "non_verificato",
                    "detection_status": "rilevato_da_feed",
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }
                items[item_id] = analyze_item(item)
                count += 1
            source_results.append({"name": name, "ok": True, "required": required, "items": count})
        except Exception as exc:
            source_results.append({"name": name, "ok": False, "required": required, "error": f"{type(exc).__name__}: {exc}"[:300]})

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "item_count": len(items),
        "source_results": source_results,
        "items": sorted(
            items.values(),
            key=lambda item: (item.get("published_at") or "", item["title"]),
            reverse=True,
        ),
    }
