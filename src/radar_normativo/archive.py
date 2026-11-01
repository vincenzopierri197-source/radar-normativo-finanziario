"""Archivio storico e rilevamento delle nuove pubblicazioni."""
from __future__ import annotations

import hashlib
import json
import posixpath
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from radar_normativo.analysis import analyze_item
from radar_normativo.classifier import classify_topics

ROME = ZoneInfo("Europe/Rome")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_day(value: Any) -> str:
    """Restituisce il giorno UTC di un timestamp ISO, anche se ha un offset diverso."""
    timestamp = str(value or "").strip()
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except ValueError:
        return timestamp[:10]


def _rome_day(value: Any) -> str:
    """Giorno civile italiano di un timestamp ISO."""
    timestamp = str(value or "").strip()
    if not timestamp:
        return ""
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ROME).date().isoformat()
    except ValueError:
        return timestamp[:10]


def _canonical_url(value: Any) -> str:
    url = str(value or "").strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return url
    path = posixpath.normpath(parts.path or "/")
    if parts.path.endswith("/") and not path.endswith("/"):
        path += "/"
    if parts.path.startswith("/") and not path.startswith("/"):
        path = "/" + path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, parts.fragment))


def update_archive(
    latest_path: str | Path,
    archive_path: str | Path,
    new_items_path: str | Path,
) -> dict[str, Any]:
    """Unisce una scansione completa all'archivio, deduplicando per ID e URL canonico."""
    latest_file = Path(latest_path)
    archive_file = Path(archive_path)
    new_file = Path(new_items_path)
    latest = json.loads(latest_file.read_text(encoding="utf-8"))
    if not isinstance(latest, dict) or not isinstance(latest.get("items"), list):
        raise ValueError("Scansione non valida: atteso un oggetto JSON con 'items'")

    source_results = latest.get("source_results")
    if not isinstance(source_results, list) or not source_results:
        raise ValueError("Archivio non aggiornato: la scansione non contiene risultati delle fonti")
    failures = [
        source for source in source_results
        if not isinstance(source, dict)
        or (not source.get("ok", False) and source.get("required", True))
    ]
    if failures:
        names = ", ".join(str(source.get("name", "fonte sconosciuta")) for source in failures)
        raise ValueError(f"Archivio non aggiornato: scansione incompleta ({names})")

    scan_time = latest.get("generated_at") or _now()
    if archive_file.exists():
        stored = json.loads(archive_file.read_text(encoding="utf-8"))
        existing_items = stored.get("items", []) if isinstance(stored, dict) else []
    else:
        existing_items = []

    items_by_id: dict[str, dict[str, Any]] = {}
    id_by_url: dict[str, str] = {}
    for original in existing_items:
        item = dict(original)
        item_id = str(item.get("id") or hashlib.sha256(str(item.get("url", "")).encode()).hexdigest()[:20])
        canonical_url = _canonical_url(item.get("url"))
        item["url"] = canonical_url or item.get("url", "")
        if canonical_url and canonical_url in id_by_url:
            kept_id = id_by_url[canonical_url]
            kept = items_by_id[kept_id]
            if len(str(item.get("summary") or "")) > len(str(kept.get("summary") or "")):
                kept["summary"] = item["summary"]
            continue
        item["id"] = item_id
        items_by_id[item_id] = item
        if canonical_url:
            id_by_url[canonical_url] = item_id

    newly_discovered: list[dict[str, Any]] = []
    for current in latest.get("items", []):
        item = dict(current)
        canonical_url = _canonical_url(item.get("url"))
        if canonical_url:
            item["url"] = canonical_url
        candidate_id = str(item.get("id") or hashlib.sha256(canonical_url.encode()).hexdigest()[:20])
        existing_id = candidate_id if candidate_id in items_by_id else id_by_url.get(canonical_url)
        if existing_id is not None:
            previous = items_by_id[existing_id]
            first_seen = previous.get("first_seen_at", scan_time)
            previous_summary = str(previous.get("summary") or "")
            try:
                prior_count = max(1, int(previous.get("seen_count", 1)))
            except (TypeError, ValueError):
                prior_count = 1
            last_seen = previous.get("last_seen_at") or ""
            seen_count = prior_count if _utc_day(last_seen) == _utc_day(scan_time) else prior_count + 1
            item["id"] = existing_id
            previous.update(item)
            if not str(item.get("summary") or "").strip() and previous_summary:
                previous["summary"] = previous_summary
            previous.update(analyze_item(previous))
            previous["first_seen_at"] = first_seen
            previous["last_seen_at"] = scan_time
            previous["seen_count"] = seen_count
            if canonical_url:
                id_by_url[canonical_url] = existing_id
            # Mantiene le schede scoperte oggi nel flusso di notifica finché
            # Telegram non le registra nel ledger. Serve a rendere sicuri i retry
            # quando l'archivio è già stato salvato ma l'invio è fallito.
            if _rome_day(first_seen) == _rome_day(scan_time):
                newly_discovered.append(dict(previous))
        else:
            item["id"] = candidate_id
            item["first_seen_at"] = scan_time
            item["last_seen_at"] = scan_time
            item["seen_count"] = 1
            item = analyze_item(item)
            items_by_id[candidate_id] = item
            if canonical_url:
                id_by_url[canonical_url] = candidate_id
            newly_discovered.append(dict(item))

    refreshed_items = []
    for stored_item in items_by_id.values():
        item = dict(stored_item)
        item["topics"] = classify_topics(str(item.get("title") or ""), str(item.get("summary") or ""))
        refreshed_items.append(analyze_item(item))

    all_items = sorted(
        refreshed_items,
        key=lambda item: (item.get("published_at") or "", item.get("title") or ""),
        reverse=True,
    )
    archive = {
        "schema_version": 1,
        "updated_at": scan_time,
        "item_count": len(all_items),
        "items": all_items,
    }
    new_scan = {
        "schema_version": 1,
        "generated_at": scan_time,
        "new_item_count": len(newly_discovered),
        "items": newly_discovered,
    }

    archive_file.parent.mkdir(parents=True, exist_ok=True)
    new_file.parent.mkdir(parents=True, exist_ok=True)
    archive_file.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    new_file.write_text(json.dumps(new_scan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "archive_count": len(all_items),
        "new_item_count": len(newly_discovered),
        "archive_path": str(archive_file),
        "new_items_path": str(new_file),
    }
