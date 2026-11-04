"""Quote indicative per il riepilogo giornaliero dei mercati."""
from __future__ import annotations
import json, urllib.error, urllib.parse, urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo
ROME=ZoneInfo("Europe/Rome")
INSTRUMENTS=[
("Dow Jones Industrial Average","^DJI","USA"),
("JPMorgan Global Select Equity","JGLO","Globale"),
("UBS MSCI China A","CHINA.MI","Cina"),
("JPM China A-Share Opportunities","0P0001LMEZ.F","Cina"),
("Fidelity Global Industrials","0P0000CO6N.F","Industriali"),
("FTSE MIB","FTSEMIB.MI","Italia"),
("1ST SICAV - Italy I EUR Acc","0P0001BRM8.F","Italia"),
("India Globalization Capital","IGS1.SG","India"),
("Fidelity India Focus A-EUR","0P00000ZJK.F","India")]
def _fetch_chart(symbol:str)->dict[str,Any]:
 q=urllib.parse.urlencode({"range":"5d","interval":"1d"})
 url=f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol,safe='^')}?{q}"
 req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 RadarNormativo/1.0"})
 with urllib.request.urlopen(req,timeout=12) as response: payload=json.loads(response.read().decode())
 result=payload.get("chart",{}).get("result") or []
 if not result: raise ValueError("quotazione non disponibile")
 chart=result[0]; meta=chart.get("meta") or {}
 quote=(chart.get("indicators",{}).get("quote") or [{}])[0]
 closes=[float(x) for x in quote.get("close",[]) if x is not None]
 current=meta.get("regularMarketPrice")
 if current is None and closes: current=closes[-1]
 if current is None: raise ValueError("nessun prezzo")
 previous=meta.get("chartPreviousClose") or meta.get("previousClose")
 if previous is None and len(closes)>1: previous=closes[-2]
 change=(float(current)/float(previous)-1)*100 if previous else None
 stamp=datetime.fromtimestamp(int(meta["regularMarketTime"]),timezone.utc).astimezone(ROME) if meta.get("regularMarketTime") else None
 return {"value":float(current),"change_pct":change,"currency":str(meta.get("currency") or ""),"time":stamp}
def collect_market_data()->list[dict[str,Any]]:
 rows=[]
 for name,symbol,region in INSTRUMENTS:
  try: rows.append({"name":name,"symbol":symbol,"region":region,"ok":True,**_fetch_chart(symbol)})
  except (urllib.error.URLError,TimeoutError,ValueError,KeyError,TypeError,json.JSONDecodeError) as exc:
   rows.append({"name":name,"symbol":symbol,"region":region,"ok":False,"error":str(exc)[:100]})
 return rows
def render_market_briefing(rows:list[dict[str,Any]]|None=None)->str:
 data=collect_market_data() if rows is None else rows
 lines=["📈 RADAR FINANZIARIO",f"🕒 Rilevazione: {datetime.now(ROME).strftime('%d/%m/%Y %H:%M')} (ora italiana)",""]
 changes=[]; regions={}
 for row in data:
  if not row.get("ok"):
   lines.append(f"⚪ {row['name']} ({row['symbol']}): dato non disponibile"); continue
  val=row.get("value"); ch=row.get("change_pct"); cur=row.get("currency") or ""
  value=f"{val:,.4f} {cur}".strip() if val is not None else "valore n.d."
  if ch is None: change="variazione n.d."; icon="⚪"
  else:
   change=f"{ch:+.2f}%"; icon="🟢" if ch>0.05 else "🔴" if ch< -0.05 else "🟡"
   changes.append(ch); regions.setdefault(row["region"],[]).append(ch)
  stamp=row.get("time"); when=stamp.strftime("%d/%m %H:%M") if stamp else "ora n.d."
  lines.append(f"{icon} {row['name']}: {value} ({change}) · {when}")
 lines.extend(["","VALUTAZIONE COMPLESSIVA"])
 if not changes: lines.append("Dati insufficienti per una valutazione complessiva.")
 else:
  avg=sum(changes)/len(changes); pos=sum(x>0.05 for x in changes); neg=sum(x< -0.05 for x in changes); neu=len(changes)-pos-neg
  mood="prevalentemente positivo" if avg>0.15 and pos>neg else "prevalentemente negativo" if avg< -0.15 and neg>pos else "misto o stabile"
  lines.append(f"Quadro {mood}; media semplice indicativa dei {len(changes)} strumenti disponibili: {avg:+.2f}%.")
  lines.append(f"Positivi: {pos}; negativi: {neg}; stabili: {neu}.")
  regional=sorted((sum(v)/len(v),k) for k,v in regions.items())
  if regional: lines.append(f"Gruppo più forte: {regional[-1][1]} ({regional[-1][0]:+.2f}%); più debole: {regional[0][1]} ({regional[0][0]:+.2f}%).")
  lines.append("La media non è il rendimento del portafoglio: non considera pesi, costi o cambi.")
 lines.extend(["","Nota: dati indicativi da Yahoo Finance, eventualmente ritardati; ticker non disponibili segnalati senza stimare valori. Non è consulenza finanziaria."])
 return "\n".join(lines)



def _fetch_history(symbol: str, period: str = "1mo") -> list[dict[str, Any]]:
    """Restituisce chiusure giornaliere reali con data locale, senza inventare valori."""
    query = urllib.parse.urlencode({"range": period, "interval": "1d"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='^')}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RadarNormativo/1.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode())
    result = payload.get("chart", {}).get("result") or []
    if not result:
        raise ValueError("storico non disponibile")
    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = (chart.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    points = []
    for stamp, close in zip(timestamps, closes):
        if close is None:
            continue
        local_date = datetime.fromtimestamp(int(stamp), timezone.utc).astimezone(ROME).date()
        points.append({"date": local_date, "close": float(close)})
    if not points:
        raise ValueError("nessuna chiusura storica disponibile")
    return points


def render_finance_report(mode: str = "current") -> str:
    """Riepilogo sintetico, ultima seduta entro ieri o variazione su sette giorni."""
    if mode not in {"current", "yesterday", "seven_days"}:
        raise ValueError("modalità finanziaria non valida")
    today = datetime.now(ROME).date()
    cutoff = today - timedelta(days=1) if mode == "yesterday" else today
    start = today - timedelta(days=7)
    lines = ["📊 RADAR FINANZIARIO — " + {
        "current": "RIEPILOGO ATTUALE",
        "yesterday": "ULTIMA SEDUTA ENTRO IERI",
        "seven_days": "ANDAMENTO DEGLI ULTIMI 7 GIORNI",
    }[mode], ""]
    changes: list[float] = []
    available = 0
    for name, symbol, region in INSTRUMENTS:
        try:
            points = _fetch_history(symbol, "1mo")
            eligible = [point for point in points if point["date"] <= cutoff]
            if not eligible:
                lines.append(f"⚪ {name}: storico non disponibile entro {cutoff.isoformat()}")
                continue
            latest = eligible[-1]
            if mode == "seven_days":
                earlier = [point for point in points if point["date"] <= latest["date"] - timedelta(days=7)]
                if not earlier:
                    lines.append(f"⚪ {name}: storico insufficiente per il confronto a 7 giorni")
                    continue
                baseline = earlier[-1]
                label = f"{baseline['date'].strftime('%d/%m')} → {latest['date'].strftime('%d/%m')}"
            else:
                prior = [point for point in points if point["date"] < latest["date"]]
                if not prior:
                    lines.append(f"⚪ {name}: chiusura precedente non disponibile")
                    continue
                baseline = prior[-1]
                label = latest["date"].strftime("%d/%m")
            change = (latest["close"] / baseline["close"] - 1) * 100 if baseline["close"] else None
            if change is None:
                lines.append(f"⚪ {name}: variazione non disponibile")
                continue
            icon = "🟢" if change > 0.05 else "🔴" if change < -0.05 else "🟡"
            lines.append(f"{icon} {name}: {change:+.2f}% · {label}")
            changes.append(change)
            available += 1
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            lines.append(f"⚪ {name}: dato non disponibile")
    lines.extend(["", "VALUTAZIONE SINTETICA"])
    if changes:
        average = sum(changes) / len(changes)
        positive = sum(value > 0.05 for value in changes)
        negative = sum(value < -0.05 for value in changes)
        mood = "prevalentemente positivo" if average > 0.15 and positive > negative else "prevalentemente negativo" if average < -0.15 and negative > positive else "misto o stabile"
        lines.append(f"Quadro {mood}; media semplice indicativa: {average:+.2f}% su {available} strumenti disponibili.")
        lines.append(f"Positivi: {positive}; negativi: {negative}; stabili: {available - positive - negative}.")
    else:
        lines.append("Dati insufficienti per una valutazione complessiva.")
    lines.append("Dati storici indicativi da Yahoo Finance, eventualmente ritardati. La media non rappresenta il rendimento di un portafoglio e non è consulenza finanziaria.")
    return "\n".join(lines)


# Fondi personali: separati dal radar generale, ma riusano i ticker Yahoo già configurati.
MY_PAC_FUNDS = [
    ("FF Global Industrials", "0P0000CO6N.F", "LU0114723033"),
    ("JPM China A-Share", "0P0001LMEZ.F", "LU1255011097"),
    ("Fidelity Funds Italy", "0P0001BRM8.F", "LU0283901063"),
    ("FF India Focus", "0P00000ZJK.F", "LU2178498379"),
]

def render_my_pac_report() -> str:
    """Riepilogo separato dei quattro fondi personali con quotazioni indicative."""
    lines = ["💼 I MIEI PAC — FONDI PERSONALI",
             f"🕒 {datetime.now(ROME).strftime('%d/%m/%Y %H:%M')} (ora italiana)", ""]
    for name, symbol, isin in MY_PAC_FUNDS:
        try:
            quote = _fetch_chart(symbol)
            value = f"{quote['value']:,.4f} {quote.get('currency') or ''}".strip()
            change = quote.get("change_pct")
            variation = f"{change:+.2f}%" if change is not None else "n.d."
            icon = "🟢" if change is not None and change > 0.05 else "🔴" if change is not None and change < -0.05 else "🟡"
            stamp = quote.get("time")
            when = stamp.strftime("%d/%m %H:%M") if stamp else "ora n.d."
            lines.append(f"{icon} {name} ({isin})\n   Quota: {value} · variazione: {variation} · {when}")
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            lines.append(f"⚪ {name} ({isin}): quotazione non disponibile ({symbol})")
    lines.extend(["", "Dati indicativi Yahoo Finance, potenzialmente ritardati; variazione giornaliera, non rendimento del PAC."])
    return "\n".join(lines)
