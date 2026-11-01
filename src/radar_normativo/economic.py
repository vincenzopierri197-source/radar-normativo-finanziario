"""Analisi spiegabile dei movimenti di mercato disponibili.

Non è un modello macroeconomico: non stima PIL, inflazione, occupazione o probabilità
di scenario senza serie storiche e fonti macroeconomiche adeguate.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable
from zoneinfo import ZoneInfo

from radar_normativo.finance import collect_market_data

ROME = ZoneInfo("Europe/Rome")


def _snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        row for row in rows
        if row.get("ok") and isinstance(row.get("change_pct"), (int, float))
    ]
    changes = [float(row["change_pct"]) for row in valid]
    positive = sum(value > 0.05 for value in changes)
    negative = sum(value < -0.05 for value in changes)
    neutral = len(changes) - positive - negative
    average = sum(changes) / len(changes) if changes else None
    # Punteggio trasparente di tono dei mercati, NON punteggio dell'economia reale.
    score = None
    if changes:
        breadth = (positive - negative) / len(changes)
        score = max(0, min(100, round(50 + average * 4 + breadth * 25)))
    if score is None:
        label = "DATI INSUFFICIENTI"
    elif score >= 65:
        label = "TONO DI MERCATO POSITIVO"
    elif score >= 55:
        label = "TONO DI MERCATO MODERATAMENTE POSITIVO"
    elif score >= 45:
        label = "TONO MISTO / NEUTRALE"
    elif score >= 35:
        label = "TONO DI MERCATO DEBOLE"
    else:
        label = "TONO DI MERCATO MOLTO DEBOLE"
    return {
        "valid": valid, "changes": changes, "positive": positive,
        "negative": negative, "neutral": neutral, "average": average,
        "score": score, "label": label,
    }


def _headline(snapshot: dict[str, Any]) -> list[str]:
    lines = [f"📊 INDICATORE DI MERCATO: {snapshot['label']}"]
    if snapshot["score"] is None:
        lines.append("Non ci sono abbastanza quotazioni aggiornate per formulare un giudizio.")
        return lines
    lines.append(f"Punteggio indicativo: {snapshot['score']}/100 (50 = tono neutrale).")
    lines.append(
        f"Strumenti in rialzo: {snapshot['positive']} · in ribasso: "
        f"{snapshot['negative']} · quasi stabili: {snapshot['neutral']}."
    )
    lines.append(f"Variazione media semplice giornaliera: {snapshot['average']:+.2f}%.")
    if snapshot["positive"] > snapshot["negative"]:
        lines.append("Motivo principale: prevalgono gli strumenti in rialzo nel campione osservato.")
    elif snapshot["negative"] > snapshot["positive"]:
        lines.append("Motivo principale: prevalgono gli strumenti in ribasso nel campione osservato.")
    else:
        lines.append("Motivo principale: i rialzi e i ribassi sono bilanciati o i dati sono misti.")
    lines.append("Il campione contiene indici e fondi di aree diverse, non rappresenta tutta l'economia.")
    return lines


def _groq_reading(snapshot: dict[str, Any], *, api_key: str | None = None, model: str | None = None, requester: Callable[..., Any] | None = None) -> str:
    """Lettura Groq prudente basata esclusivamente sui dati disponibili."""
    key = api_key or os.environ.get("GROQ_API_KEY")
    if not key:
        return "Non attiva: chiave GROQ_API_KEY non configurata."
    metrics = [
        {"name": row.get("name"), "symbol": row.get("symbol"), "region": row.get("region"),
         "change_pct": row.get("change_pct"), "value": row.get("value"), "currency": row.get("currency")}
        for row in snapshot["valid"]
    ]
    if not metrics:
        return "Non generata: dati numerici insufficienti."
    payload = {
        "model": model or os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b"),
        "temperature": 0.2, "max_tokens": 350,
        "messages": [
            {"role": "system", "content": "Sei un analista quantitativo prudente. Analizza esclusivamente i dati numerici forniti. Scrivi in italiano 3-5 punti brevi: quadro osservato, ampiezza di rialzi/ribassi, differenze regionali e rischi/limiti. Non inventare cause, notizie, dati macro, prezzi o previsioni. Distingui osservazioni e interpretazioni. Il campione di ticker non rappresenta l'intera economia. Nessun consiglio di investimento o probabilità. Un dato giornaliero non dimostra un trend strutturale."},
            {"role": "user", "content": "Valuta questi dati Yahoo Finance, potenzialmente ritardati. I valori numerici sono vincolanti e non vanno modificati: " + json.dumps(metrics, ensure_ascii=False)}
        ]
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="POST",
    )
    send = requester or urllib.request.urlopen
    try:
        with send(request, timeout=20) as response:
            status = getattr(response, "status", 200)
            if status < 200 or status >= 300:
                return "Non disponibile: Groq HTTP " + str(status) + "."
            result = json.loads(response.read().decode("utf-8"))
        answer = result["choices"][0]["message"]["content"].strip()
        return answer[:1800] if answer else "Non disponibile: risposta Groq vuota."
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError, TypeError):
        return "Non disponibile: errore di rete o risposta Groq non valida."


def render_economic_report(
    mode: str,
    rows: list[dict[str, Any]] | None = None,
    *,
    groq_api_key: str | None = None,
    groq_model: str | None = None,
    groq_requester: Callable[..., Any] | None = None,
) -> str:
    """Produce un rapporto motivato con lettura Groq opzionale basata sui dati."""
    data = collect_market_data() if rows is None else rows
    snap = _snapshot(data)
    now = datetime.now(ROME).strftime("%d/%m/%Y %H:%M")
    lines = [f"🧭 RADAR ECONOMICO INTELLIGENTE · {now}", ""]
    lines.extend(_headline(snap))
    valid = snap["valid"]
    regional: dict[str, list[float]] = {}
    for row in valid:
        regional.setdefault(str(row.get("region") or "Altro"), []).append(float(row["change_pct"]))
    ranked = sorted((sum(values) / len(values), region) for region, values in regional.items())

    if mode in {"economia", "analisi"}:
        lines.extend(["", "🧠 LETTURA RAGIONATA"])
        if snap["score"] is None:
            lines.append("Non è possibile distinguere una tendenza dai dati disponibili.")
        elif snap["positive"] > snap["negative"] and (snap["average"] or 0) > 0:
            lines.append("Il movimento è favorevole nel breve periodo osservato: rialzi diffusi e media positiva.")
            lines.append("Questo non dimostra che PIL, occupazione o potere d'acquisto stiano migliorando.")
        elif snap["negative"] > snap["positive"] and (snap["average"] or 0) < 0:
            lines.append("Il movimento è debole nel breve periodo osservato: ribassi diffusi e media negativa.")
            lines.append("Un singolo giorno non basta per dichiarare una crisi o un deterioramento strutturale.")
        else:
            lines.append("I segnali sono contrastanti: non emerge una direzione netta dal campione giornaliero.")
        if ranked:
            lines.append(f"Gruppo relativamente più forte: {ranked[-1][1]} ({ranked[-1][0]:+.2f}%).")
            lines.append(f"Gruppo relativamente più debole: {ranked[0][1]} ({ranked[0][0]:+.2f}%).")

    if mode == "stime":
        lines.extend(["", "🔭 SCENARI CONDIZIONALI · BREVE PERIODO"])
        if snap["score"] is None:
            lines.append("Nessuno scenario: dati insufficienti.")
        else:
            lines.append("🟢 Favorevole: i rialzi restano diffusi e la media continua positiva.")
            lines.append("🟡 Centrale: i movimenti si stabilizzano e gli strumenti restano contrastanti.")
            lines.append("🔴 Avverso: i ribassi si allargano a più aree e la media diventa più negativa.")
            lines.append("Sono scenari condizionali, non previsioni con probabilità statistiche.")
            lines.append("Orizzonte: prossime sedute; nessuna stima affidabile a mesi senza serie storiche.")

    if mode == "andamento":
        lines.extend(["", "📈 COME STA ANDANDO?"])
        if snap["score"] is None:
            lines.append("Giudizio sospeso: quotazioni aggiornate insufficienti.")
        else:
            lines.append(f"Giudizio sui mercati osservati: {snap['label'].lower()}.")
            lines.append("Il giudizio descrive il movimento giornaliero dei ticker disponibili, non l'economia italiana nel suo complesso.")

    if mode == "rischi":
        lines.extend(["", "⚠️ RISCHI E SEGNALI DA CONTROLLARE"])
        falling = sorted(
            (float(row["change_pct"]), str(row.get("name") or row.get("symbol") or "strumento"))
            for row in valid if float(row["change_pct"]) < -0.05
        )
        if falling:
            lines.append("Strumenti in calo nel dato disponibile:")
            lines.extend(f"• {name}: {change:+.2f}%" for change, name in falling[:5])
        else:
            lines.append("Nessun ribasso significativo nel campione disponibile; questo non esclude altri rischi.")
        missing = len(data) - len(valid)
        if missing:
            lines.append(f"Copertura incompleta: {missing} strumenti senza variazione utilizzabile.")
        lines.append("Rischi macro (inflazione, debito, tassi e occupazione) non valutabili da queste sole quotazioni.")

    if mode not in {"economia", "stime", "andamento", "rischi", "analisi"}:
        return "Comando economico non riconosciuto. Usa /aiuto."
    if mode in {"economia", "stime", "analisi"}:
        lines.extend([
            "",
            "🧠 LETTURA IA GROQ",
            _groq_reading(snap, api_key=groq_api_key, model=groq_model, requester=groq_requester),
        ])
    lines.extend([
        "",
        "⚠️ LIMITI E FONTI",
        "Quotazioni indicative Yahoo Finance, potenzialmente ritardate. Nessun dato macro ufficiale è incluso in questa versione.",
        "Il punteggio è una regola trasparente basata su media e ampiezza dei movimenti: non è una probabilità né consulenza finanziaria.",
    ])
    return "\n".join(lines)[:3900]