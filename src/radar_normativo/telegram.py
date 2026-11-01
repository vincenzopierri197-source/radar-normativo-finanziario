"""Invio del riepilogo giornaliero normativo e finanziario a Telegram."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from radar_normativo.economic import render_economic_report
from radar_normativo.finance import collect_market_data, render_market_briefing

TELEGRAM_SAFE_LIMIT = 3900
ROME = ZoneInfo("Europe/Rome")
TITLE_LIMIT = 100


def _item_key(item: dict[str, Any]) -> str:
    if item.get("id"):
        return str(item["id"])
    identity = str(item.get("url") or item.get("title") or json.dumps(item, sort_keys=True))
    return hashlib.sha256(identity.encode()).hexdigest()[:24]


def _load_items(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError("JSON deve contenere una lista o una chiave items")
    return [item for item in items if isinstance(item, dict)]


def _send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=20) as response:
            payload = json.loads(response.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("Invio Telegram non riuscito (rete o risposta non valida)") from None
    if not payload.get("ok"):
        raise RuntimeError(
            f"Telegram ha rifiutato il messaggio: {str(payload.get('description') or 'errore API')[:200]}"
        )


def _score(item: dict[str, Any]) -> int:
    try:
        return max(0, min(100, int(item.get("relevance_score") or 0)))
    except (TypeError, ValueError):
        return 0


def _rank(item: dict[str, Any]) -> tuple[int, int, str]:
    priority = {"alta": 3, "media": 2, "bassa": 1}.get(
        str(item.get("priority") or "bassa").casefold(), 0
    )
    return priority, _score(item), str(item.get("published_at") or "")


def _clean_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_line(index: int, item: dict[str, Any]) -> str:
    priority = str(item.get("priority") or "bassa").upper()
    if priority not in {"ALTA", "MEDIA", "BASSA"}:
        priority = "DA VALUTARE"
    title = _clean_text(item.get("title")) or "Titolo non disponibile"
    if len(title) > TITLE_LIMIT:
        title = title[: TITLE_LIMIT - 1].rstrip() + "…"
    url = str(item.get("url") or "").strip()
    suffix = f" — {url}" if url else ""
    return f"{index}. [{priority} {_score(item)}] {title}{suffix}"


def _render_compact_digest(items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    today = datetime.now(ROME).strftime("%d/%m/%Y")
    ranked = sorted(items, key=_rank, reverse=True)
    header = f"📡 RADAR NORMATIVO — {today}\n{len(items)} nuove pubblicazioni\n\n"
    lines: list[str] = []
    included: list[dict[str, Any]] = []
    omitted = 0

    for item in ranked:
        line = _compact_line(len(lines) + 1, item)
        candidate_lines = lines + [line]
        # Reserve space for the largest possible omitted count so the final
        # footer cannot push the message over Telegram's limit.
        candidate_omitted = max(0, len(ranked) - len(candidate_lines))
        footer = (
            "\n\nNota: priorità automatica; stato giuridico non verificato."
            if candidate_omitted == 0
            else f"\n\nAltri {candidate_omitted} atti non riportati per il limite Telegram."
        )
        reserve_omitted = len(ranked) if candidate_omitted else 0
        if candidate_omitted:
            footer = f"\n\nAltri {reserve_omitted} atti non riportati per il limite Telegram."
        if len(header + "\n".join(candidate_lines) + footer) <= TELEGRAM_SAFE_LIMIT:
            lines.append(line)
            included.append(item)
        else:
            omitted += 1

    if not lines:
        raise ValueError("Nessun atto entra nel limite Telegram: controllare titolo e collegamento.")
    footer = (
        "\n\nNota: priorità automatica; stato giuridico non verificato."
        if omitted == 0
        else f"\n\nAltri {omitted} atti non riportati per il limite Telegram."
    )
    message = header + "\n".join(lines) + footer
    if len(message) > TELEGRAM_SAFE_LIMIT:
        raise ValueError("Il riepilogo normativo supera il limite di sicurezza Telegram.")
    return message, included


def _render_chunks(
    items: list[dict[str, Any]], include_finance: bool
) -> list[tuple[list[dict[str, Any]], str]]:
    finance = ""
    if include_finance:
        market_rows = collect_market_data()
        finance = render_market_briefing(market_rows) + "\n\n" + render_economic_report("analisi", market_rows)

    if items:
        text, included = _render_compact_digest(items)
    else:
        text = "📡 RADAR NORMATIVO — RIEPILOGO GIORNALIERO\nNessuna nuova pubblicazione normativa rilevata oggi."
        included = []

    if finance:
        text += "\n\n" + finance
    if len(text) > TELEGRAM_SAFE_LIMIT:
        raise ValueError(
            f"Il riepilogo completo è lungo {len(text)} caratteri e supera il limite Telegram "
            f"di {TELEGRAM_SAFE_LIMIT}; nessun contenuto è stato troncato o inviato."
        )
    return [(included, text)]


def send_new_items(
    input_path: str | Path,
    ledger_path: str | Path,
    *,
    dry_run: bool = False,
    token: str | None = None,
    chat_id: str | None = None,
    sender: Callable[[str, str, str], None] | None = None,
    include_finance: bool = False,
) -> dict[str, int]:
    items = _load_items(input_path)
    ledger = Path(ledger_path)
    if ledger.exists():
        payload = json.loads(ledger.read_text(encoding="utf-8"))
        sent_ids = payload.get("sent_ids", {})
        if not isinstance(sent_ids, dict):
            raise ValueError("Registro Telegram non valido")
    else:
        sent_ids = {}

    pending = [(item, _item_key(item)) for item in items if _item_key(item) not in sent_ids]
    chunks = _render_chunks([item for item, _ in pending], include_finance)
    if dry_run:
        for _, message in chunks:
            print(message)
            print("---")
        return {"sent": 0, "pending": len(pending), "skipped": len(items) - len(pending)}

    if not chunks:
        return {"sent": 0, "pending": 0, "skipped": len(items)}
    token_value = token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_value = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not token_value or not chat_value:
        raise ValueError("Configurare TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID, oppure usare --dry-run")

    send = sender or _send_message
    ledger.parent.mkdir(parents=True, exist_ok=True)
    keys = {_item_key(item): key for item, key in pending}
    count = 0
    for chunk_items, message in chunks:
        send(token_value, chat_value, message)
        for item in chunk_items:
            sent_ids[keys[_item_key(item)]] = datetime.now(timezone.utc).isoformat()
            count += 1
        if chunk_items:
            ledger.write_text(
                json.dumps({"schema_version": 1, "sent_ids": sent_ids}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return {"sent": count, "pending": len(pending), "skipped": len(items) - len(pending)}
