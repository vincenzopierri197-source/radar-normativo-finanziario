// Radar Normativo — bot Telegram su Cloudflare Workers (webhook).
// Porting dei comandi di src/radar_normativo/bot.py + finance.py.

const TZ = "Europe/Rome";

const HELP = `Comandi Radar Normativo e Finanziario:
/start — avvia il bot
/aiuto — mostra questo elenco
/ultime — ultime pubblicazioni normative
/oggi — pubblicazioni normative di oggi
/ieri — pubblicazioni normative di ieri
/ultimi7giorni — pubblicazioni normative degli ultimi 7 giorni
/cerca parola — cerca nei titoli e nelle sintesi
/ia domanda — risponde usando l'archivio normativo con IA
/ai domanda — risponde su economia e mercati da notizie recenti
/economia domanda — cerca notizie economiche e le sintetizza con IA
/fonti — fonti normative monitorate
/filtri — mostra o configura i filtri personali
/stato — stato dell'archivio normativo e delle fonti
/mercati — quotazioni e valutazione IA dei nove strumenti finanziari
/groqtest — verifica in tempo reale del collegamento Groq
/finanza — riepilogo finanziario attuale
/finanzaoggi — alias di /finanza
/finanzieri — ultima seduta disponibile entro ieri
/finanza7giorni — andamento finanziario degli ultimi 7 giorni
/miepac — quotazioni dei quattro fondi PAC personali

Nota: dati automatici e indicativi; quotazioni eventualmente ritardate. Le schede normative non certificano la vigenza degli atti. I dati finanziari non costituiscono consulenza.`;

export const BOT_COMMANDS = [
  ["start", "Avvia il bot"],
  ["aiuto", "Mostra tutti i comandi disponibili"],
  ["ultime", "Ultime pubblicazioni normative"],
  ["oggi", "Pubblicazioni normative di oggi"],
  ["ieri", "Pubblicazioni normative di ieri"],
  ["ultimi7giorni", "Pubblicazioni normative degli ultimi 7 giorni"],
  ["cerca", "Cerca nei titoli e nelle sintesi"],
  ["ia", "Risponde usando l'archivio normativo con IA"],
  ["ai", "Risponde su economia e mercati da notizie recenti"],
  ["economia", "Cerca notizie economiche recenti e le sintetizza con IA"],
  ["fonti", "Elenca le fonti normative monitorate"],
  ["filtri", "Mostra o configura i filtri personali"],
  ["stato", "Stato dell'archivio e delle fonti"],
  ["mercati", "Quotazioni e valutazione IA dei nove strumenti finanziari"],
  ["groqtest", "Verifica il collegamento al servizio IA Groq"],
  ["finanza", "Riepilogo finanziario attuale"],
  ["finanzaoggi", "Alias del riepilogo finanziario"],
  ["finanzieri", "Quotazioni dell'ultima seduta entro ieri"],
  ["finanza7giorni", "Andamento finanziario degli ultimi 7 giorni"],
  ["miepac", "Quotazioni dei quattro fondi PAC personali"],
];

const MY_PAC_FUNDS = [
  ["FF Global Industrials", "0P0000CO6N.F", "LU0114723033"],
  ["JPM China A-Share", "0P0001LMEZ.F", "LU1255011097"],
  ["Fidelity Funds Italy", "0P0001BRM8.F", "LU0283901063"],
  ["FF India Focus", "0P00000ZJK.F", "LU2178498379"],
];

const INSTRUMENTS = [
  ["Dow Jones Industrial Average", "^DJI", "USA"],
  ["JPMorgan Global Select Equity", "JGLO", "Globale"],
  ["UBS MSCI China A", "CHINA.MI", "Cina"],
  ["JPM China A-Share Opportunities", "0P0001LMEZ.F", "Cina"],
  ["Fidelity Global Industrials", "0P0000CO6N.F", "Industriali"],
  ["FTSE MIB", "FTSEMIB.MI", "Italia"],
  ["1ST SICAV - Italy I EUR Acc", "0P0001BRM8.F", "Italia"],
  ["India Globalization Capital", "IGS1.SG", "India"],
  ["Fidelity India Focus A-EUR", "0P00000ZJK.F", "India"],
];

// ---------- utilità data ----------
const dayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });
const romeDay = (d) => dayFmt.format(d); // YYYY-MM-DD
const shiftDay = (iso, days) => {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};
export function publishedDay(item) {
  const v = String(item.published_at || "").trim();
  if (!v) return null;
  const d = new Date(v);
  if (!isNaN(d)) return romeDay(d);
  return /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : null;
}

// ---------- accesso dati ----------
export async function ghJson(env, path, fetchFn = fetch) {
  const repo = String(env?.GITHUB_REPO || "").trim();
  const branch = String(env?.GITHUB_BRANCH || "main").trim();
  if (!repo || repo.split("/").length !== 2 || repo.split("/").some((part) => !part.trim())) throw new Error("GITHUB_REPO non configurato correttamente");
  const url = `https://raw.githubusercontent.com/${repo}/${branch}/${path}`;
  let response;
  try { response = await fetchFn(url, { cf: { cacheTtl: 120 }, signal: AbortSignal.timeout(8000) }); }
  catch { throw new Error(`GitHub non raggiungibile durante la lettura di ${path}`); }
  if (!response.ok) throw new Error(`GitHub ha restituito HTTP ${response.status} per ${path}`);
  try { return await response.json(); }
  catch { throw new Error(`GitHub ha restituito JSON non valido per ${path}`); }
}
export const archiveItems = async (env, fetchFn = fetch) => {
  const archive = await ghJson(env, "data/archive.json", fetchFn);
  if (!archive || typeof archive !== "object" || Array.isArray(archive) || !Array.isArray(archive.items)) {
    throw new Error("Archivio GitHub non valido: manca la lista items");
  }
  return { archive, items: archive.items.filter((i) => i && typeof i === "object") };
};

async function getFilters(env, chat) {
  if (!env.STATE) return [];
  try {
    const v = JSON.parse((await env.STATE.get(`filters:${chat}`)) || "[]");
    return Array.isArray(v) ? v.map((t) => String(t).trim().toLowerCase()).filter(Boolean) : [];
  } catch {
    return [];
  }
}

function matchesFilter(item, terms) {
  if (!terms.length) return true;
  const topics = Array.isArray(item.topics) ? item.topics.join(" ") : String(item.topics || "");
  const text = [item.title, item.summary, item.source_name, topics].map((x) => String(x || "")).join(" ").toLowerCase();
  return terms.some((t) => text.includes(t));
}

function formatItems(items, empty, limit = 10) {
  if (!items.length) return empty;
  const rows = items.slice(0, limit).map((it, i) => {
    const title = String(it.title || "Titolo non disponibile").trim().slice(0, 220);
    const url = String(it.url || "").trim();
    const src = String(it.source_name || "Fonte non indicata").trim();
    const pub = String(it.published_at || "data non indicata").trim();
    return `${i + 1}. ${title}\nFonte: ${src} · Data: ${pub}` + (url ? `\n${url}` : "");
  });
  const suffix = items.length > limit ? `\n\nMostrate ${limit} di ${items.length} pubblicazioni.` : "";
  return (rows.join("\n\n") + suffix).slice(0, 3900);
}

// ---------- ricerca assistita con IA ----------
async function answerWithGroq(question, env, deps = {}) {
  if (!env.GROQ_API_KEY) {
    return "La funzione IA non è ancora configurata. L'amministratore deve aggiungere il secret GROQ_API_KEY nelle impostazioni del Worker Cloudflare.";
  }
  const { items } = await archiveItems(env, deps.fetchGithub || fetch);
  const terms = question.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter((t) => t.length > 2);
  const relevant = items.map((item) => {
    const title = String(item.title || "");
    const summary = String(item.summary || "");
    const topics = Array.isArray(item.topics) ? item.topics.join(" ") : String(item.topics || "");
    const haystack = `${title} ${summary} ${topics} ${item.source_name || ""}`.toLowerCase();
    const score = terms.reduce((n, term) => n + (haystack.includes(term) ? 1 : 0), 0);
    return { item, score };
  }).filter((row) => row.score > 0).sort((a, b) => b.score - a.score)
    .slice(0, 10).map(({ item }) => ({
      titolo: item.title || "Titolo non disponibile",
      sintesi: item.summary || "",
      fonte: item.source_name || "Fonte non indicata",
      data: item.published_at || "Data non indicata",
      url: item.url || ""
    }));
  if (!relevant.length) {
    return "Non trovo nell'archivio normativo documenti pertinenti alla domanda. Prova con termini più specifici oppure usa /cerca parola.";
  }
  const fetchFn = deps.fetchGroq || fetch;
  let response;
  try {
    response = await fetchFn("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.GROQ_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: env.GROQ_MODEL || "openai/gpt-oss-20b",
        temperature: 0.2,
        max_tokens: 900,
        messages: [
          { role: "system", content: "Sei un assistente di informazione normativa italiana. Rispondi in italiano usando esclusivamente i documenti forniti. Distingui sempre fatti e interpretazioni; non inventare norme, date, obblighi o vigenza. Se i documenti non bastano, dichiaralo. Alla fine indica le fonti pertinenti con titolo, data, fonte e URL. Non fornire consulenza legale definitiva." },
          { role: "user", content: `Domanda: ${question}\n\nDocumenti disponibili (JSON):\n${JSON.stringify(relevant)}` }
        ]
      }),
      signal: AbortSignal.timeout(25000)
    });
  } catch {
    return "Non riesco a contattare il servizio IA in questo momento. Riprova più tardi.";
  }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) return "La chiave Groq non è valida o non è autorizzata. Verifica il secret GROQ_API_KEY su Cloudflare.";
    return `Il servizio IA ha restituito un errore (HTTP ${response.status}). Riprova più tardi.`;
  }
  let payload;
  try { payload = await response.json(); } catch { return "Il servizio IA ha restituito una risposta non valida."; }
  const answer = payload?.choices?.[0]?.message?.content;
  return typeof answer === "string" && answer.trim()
    ? answer.trim().slice(0, 3900)
    : "Il servizio IA non ha prodotto una risposta. Riprova con una domanda più specifica.";
}

// ---------- ricerca economica su notizie recenti ----------
// Google News RSS aggrega link e metadati pubblici; non si tenta di aggirare paywall
// né di scaricare o riprodurre integralmente gli articoli degli editori.
function decodeXml(value) {
  return String(value || "")
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&apos;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16)))
    .trim();
}
function rssTag(block, tag) {
  const match = block.match(new RegExp("<" + tag + "(?:\\s[^>]*)?>([\\s\\S]*?)<\\/" + tag + ">", "i"));
  return match ? decodeXml(match[1]) : "";
}
export function parseEconomicRss(xml) {
  const blocks = String(xml || "").match(/<item\b[\s\S]*?<\/item>/gi) || [];
  return blocks.map((block) => ({
    title: rssTag(block, "title"),
    url: rssTag(block, "link"),
    source: rssTag(block, "source") || "Fonte non identificata",
    published_at: rssTag(block, "pubDate"),
    description: rssTag(block, "description")
  })).filter((item) => item.title && item.url).slice(0, 15);
}
async function searchEconomicNews(question, fetchFn = fetch) {
  const q = String(question || "").replace(/[\r\n]+/g, " ").slice(0, 240).trim();
  // Prima ricerca mirata sulle testate finanziarie; poi ricerche generiche.
  // Non rendere obbligatoria la presenza di una testata specifica: Google News
  // spesso non restituisce risultati quando si combinano molti site: con OR.
  const queries = [
    { q: `${q} when:7d`, hl: "it", gl: "IT", ceid: "IT:it" },
    { q: `${q} when:7d`, hl: "en-US", gl: "US", ceid: "US:en" },
    { q: `(${q}) (site:reuters.com OR site:bloomberg.com OR site:ft.com OR site:cnbc.com OR site:finance.yahoo.com OR site:marketwatch.com) when:7d`, hl: "en-US", gl: "US", ceid: "US:en" }
  ];
  const feeds = await Promise.all(queries.map(async (query) => {
    const url = "https://news.google.com/rss/search?" + new URLSearchParams({
      q: query.q, hl: query.hl, gl: query.gl, ceid: query.ceid
    }).toString();
    try {
      const response = await fetchFn(url, { headers: { "User-Agent": "RadarNormativoBot/1.0" }, signal: AbortSignal.timeout(9000) });
      if (!response.ok) return [];
      return parseEconomicRss(await response.text());
    } catch {
      return [];
    }
  }));
  const seen = new Set();
  return feeds.flat().filter((item) => {
    const key = item.url || item.title;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 18);
}
async function answerWithEconomicNews(question, env, deps = {}) {
  if (!env.GROQ_API_KEY) {
    return "La funzione IA non è configurata. L'amministratore deve impostare il secret GROQ_API_KEY nel Worker Cloudflare.";
  }
  const fetchNews = deps.fetchEconomicNews || searchEconomicNews;
  let articles;
  try { articles = await fetchNews(question, deps.fetchRss || fetch); }
  catch { articles = []; }
  if (!Array.isArray(articles) || !articles.length) {
    return "Non ho trovato notizie economiche recenti pertinenti. Prova a specificare società, indice, paese o argomento; per le quotazioni usa /mercati.";
  }
  const sources = articles.slice(0, 14).map((a) => ({
    titolo: String(a.title || "").slice(0, 350),
    fonte: String(a.source || "Fonte non identificata").slice(0, 100),
    data: String(a.published_at || "data non disponibile").slice(0, 100),
    descrizione: String(a.description || "").replace(/<[^>]*>/g, " ").slice(0, 500),
    url: String(a.url || "").slice(0, 700)
  }));
  const fetchFn = deps.fetchGroq || fetch;
  let response;
  try {
    response = await fetchFn("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.GROQ_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: env.GROQ_MODEL || "openai/gpt-oss-20b",
        temperature: 0.2,
        max_tokens: 1000,
        messages: [
          { role: "system", content: "Sei un analista informativo di economia e mercati. Rispondi in italiano alla domanda usando con prudenza le notizie e i metadati forniti. Le fonti possono includere Reuters, Bloomberg, Financial Times, CNBC, Yahoo Finance e testate italiane; non dichiarare che una testata ha pubblicato qualcosa se non compare nell'elenco. I dati possono contenere solo titoli e brevi descrizioni, non il testo integrale degli articoli: non inventare dettagli, numeri, quotazioni o cause non presenti nelle fonti. Se gli elementi non bastano, dillo chiaramente e separa i fatti riportati dalla tua interpretazione. Riporta in fondo 3-6 fonti pertinenti con titolo, testata, data se disponibile e link completo. Non fornire raccomandazioni personalizzate di investimento. Specifica che si tratta di informazione, non consulenza finanziaria." },
          { role: "user", content: `Domanda: ${String(question).slice(0, 500)}\n\nNotizie recenti trovate (RSS, JSON):\n${JSON.stringify(sources)}` }
        ]
      }),
      signal: AbortSignal.timeout(25000)
    });
  } catch {
    return "Non riesco a contattare il servizio IA in questo momento. Riprova più tardi.";
  }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) return "La chiave Groq non è valida o non è autorizzata. Verifica GROQ_API_KEY su Cloudflare.";
    return `Il servizio IA ha restituito un errore (HTTP ${response.status}). Riprova più tardi.`;
  }
  let payload;
  try { payload = await response.json(); } catch { return "Il servizio IA ha restituito una risposta non valida."; }
  const answer = payload?.choices?.[0]?.message?.content;
  return typeof answer === "string" && answer.trim()
    ? (answer.trim() + "\n\nFonti raccolte da Google News RSS; gli articoli possono essere soggetti a paywall. Dati e sintesi a scopo informativo, non consulenza finanziaria.").slice(0, 3900)
    : "Il servizio IA non ha prodotto una risposta. Riprova con una domanda più specifica.";
}

// ---------- mercati ----------
async function fetchChart(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=5d&interval=1d`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 RadarNormativo/1.0" }, signal: AbortSignal.timeout(9000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const payload = await r.json();
  const res = payload?.chart?.result?.[0];
  if (!res) throw new Error("quotazione non disponibile");
  const meta = res.meta || {};
  const closes = (res.indicators?.quote?.[0]?.close || []).filter((x) => x != null).map(Number);
  let current = meta.regularMarketPrice ?? (closes.length ? closes[closes.length - 1] : null);
  if (current == null) throw new Error("nessun prezzo");
  let prev = meta.chartPreviousClose || meta.previousClose;
  if (!prev && closes.length > 1) prev = closes[closes.length - 2];
  return {
    value: Number(current),
    change: prev ? (Number(current) / Number(prev) - 1) * 100 : null,
    currency: String(meta.currency || ""),
    time: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000) : null,
  };
}

// Dati storici giornalieri per i comandi finanziari con data.
async function fetchChartHistory(symbol) {
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(symbol)}?range=1mo&interval=1d`;
  const r = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0 RadarNormativo/1.0" }, signal: AbortSignal.timeout(9000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const payload = await r.json();
  const result = payload?.chart?.result?.[0];
  if (!result) throw new Error("storico non disponibile");
  const timestamps = result.timestamp || [];
  const closes = result.indicators?.quote?.[0]?.close || [];
  return timestamps.map((ts, i) => ({ day: romeDay(new Date(ts * 1000)), close: closes[i] == null ? null : Number(closes[i]) }))
    .filter((row) => row.close != null && Number.isFinite(row.close))
    .sort((a, b) => a.day.localeCompare(b.day));
}

export async function renderHistoricalMarkets(mode, fetchFn = fetchChartHistory, now = new Date()) {
  const today = romeDay(now);
  const target = mode === "yesterday" ? shiftDay(today, -1) : today;
  const start = shiftDay(today, -7);
  const rows = await Promise.all(INSTRUMENTS.map(async ([name, symbol, region]) => {
    try {
      const history = await fetchFn(symbol);
      if (!history.length) throw new Error("nessuna seduta disponibile");
      let latest;
      let baseline;
      if (mode === "yesterday") {
        latest = [...history].reverse().find((p) => p.day <= target);
        if (!latest || latest.day < shiftDay(target, -4)) throw new Error("nessuna seduta recente");
        const idx = history.findIndex((p) => p.day === latest.day);
        baseline = idx > 0 ? history[idx - 1] : null;
      } else {
        latest = [...history].reverse().find((p) => p.day <= today);
        baseline = history.find((p) => p.day >= start && p.day < latest?.day);
        if (!baseline) baseline = [...history].reverse().find((p) => p.day < (latest?.day || today));
        if (!latest || !baseline) throw new Error("storico insufficiente");
      }
      return { name, symbol, region, latest, baseline, ok: true };
    } catch (e) {
      return { name, symbol, region, ok: false, error: String(e.message || e) };
    }
  }));
  const title = mode === "yesterday" ? `📈 RADAR FINANZIARIO — ultima seduta disponibile entro ieri (${target})` : `📈 RADAR FINANZIARIO — andamento ultimi 7 giorni`;
  const lines = [title, ""];
  for (const row of rows) {
    if (!row.ok) { lines.push(`⚪ ${row.name}: dati storici non disponibili`); continue; }
    const pct = row.baseline ? (row.latest.close / row.baseline.close - 1) * 100 : null;
    const change = pct == null ? "variazione n.d." : `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
    const icon = pct == null ? "⚪" : pct > 0.05 ? "🟢" : pct < -0.05 ? "🔴" : "🟡";
    lines.push(`${icon} ${row.name}: ${row.latest.close.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} (${change}) · dato ${row.latest.day}${row.baseline ? ` · base ${row.baseline.day}` : ""}`);
  }
  lines.push("", "Dati storici indicativi da Yahoo Finance, eventualmente ritardati. Alcuni strumenti possono non avere una quotazione per ogni giorno. Non è consulenza finanziaria.");
  return lines.join("\n").slice(0, 3900);
}

const stampFmt = new Intl.DateTimeFormat("it-IT", { timeZone: TZ, day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
const nowFmt = new Intl.DateTimeFormat("it-IT", { timeZone: TZ, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
const sgn = (n) => (n >= 0 ? "+" : "") + n.toFixed(2);

async function requestGroq(env, messages, deps = {}, maxTokens = 500) {
  if (!env?.GROQ_API_KEY) return { ok: false, status: 0, error: "chiave_mancante" };
  const fetchFn = deps.fetchGroq || fetch;
  try {
    const response = await fetchFn("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: { "Authorization": `Bearer ${env.GROQ_API_KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: env.GROQ_MODEL || "openai/gpt-oss-20b",
        temperature: 0.2,
        max_tokens: maxTokens,
        messages
      }),
      signal: AbortSignal.timeout(25000)
    });
    if (!response.ok) return { ok: false, status: response.status, error: response.status === 401 || response.status === 403 ? "chiave_non_valida" : "errore_api" };
    const payload = await response.json();
    const answer = payload?.choices?.[0]?.message?.content;
    if (typeof answer !== "string" || !answer.trim()) return { ok: false, status: 200, error: "risposta_vuota" };
    return { ok: true, status: 200, text: answer.trim() };
  } catch {
    return { ok: false, status: 0, error: "rete_o_timeout" };
  }
}

function groqErrorLabel(result) {
  if (result.error === "chiave_mancante") return "Groq non configurato: manca GROQ_API_KEY.";
  if (result.error === "chiave_non_valida") return "Groq non ha accettato la chiave (HTTP 401/403): controllare il secret GROQ_API_KEY su Cloudflare.";
  if (result.status) return `Groq temporaneamente non disponibile (HTTP ${result.status}).`;
  return "Groq non raggiungibile o in timeout; valutazione numerica mantenuta senza IA.";
}

export async function renderMarkets(fetchFn = fetchChart, env = null, deps = {}) {
  const rows = await Promise.all(
    INSTRUMENTS.map(async ([name, symbol, region]) => {
      try {
        return { name, symbol, region, ok: true, ...(await fetchFn(symbol)) };
      } catch (e) {
        return { name, symbol, region, ok: false, error: String(e.message || e).slice(0, 100) };
      }
    })
  );
  const lines = ["📈 RADAR FINANZIARIO", `🕒 Rilevazione: ${nowFmt.format(new Date()).replace(",", "")} (ora italiana)`, ""];
  const changes = [];
  const regions = {};
  const available = [];
  for (const r of rows) {
    if (!r.ok) { lines.push(`⚪ ${r.name} (${r.symbol}): dato non disponibile`); continue; }
    const value = `${r.value.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} ${r.currency}`.trim();
    let icon = "⚪", change = "variazione n.d.";
    if (r.change != null && Number.isFinite(Number(r.change))) {
      const pct = Number(r.change);
      change = `${sgn(pct)}%`;
      icon = pct > 0.05 ? "🟢" : pct < -0.05 ? "🔴" : "🟡";
      changes.push(pct);
      (regions[r.region] ||= []).push(pct);
      available.push({ nome: r.name, area: r.region, variazione_percentuale: Number(pct.toFixed(4)) });
    }
    const when = r.time ? stampFmt.format(r.time).replace(",", "") : "ora n.d.";
    lines.push(`${icon} ${r.name}: ${value} (${change}) · ${when}`);
  }
  lines.push("", "VALUTAZIONE QUANTITATIVA");
  let metrics = null;
  if (!changes.length) {
    lines.push("Dati insufficienti per una valutazione complessiva.");
  } else {
    const avg = changes.reduce((a, b) => a + b, 0) / changes.length;
    const pos = changes.filter((x) => x > 0.05).length;
    const neg = changes.filter((x) => x < -0.05).length;
    const neu = changes.length - pos - neg;
    const mood = avg > 0.15 && pos > neg ? "prevalentemente positivo" : avg < -0.15 && neg > pos ? "prevalentemente negativo" : "misto o stabile";
    const reg = Object.entries(regions).map(([k, v]) => [v.reduce((a, b) => a + b, 0) / v.length, k]).sort((a, b) => a[0] - b[0]);
    metrics = { strumenti_disponibili: changes.length, positivi: pos, negativi: neg, stabili: neu, media_semplice_percentuale: Number(avg.toFixed(4)), quadro_regola: mood, gruppi: reg.map(([media, area]) => ({ area, media_percentuale: Number(media.toFixed(4)) })) };
    lines.push(`Quadro ${mood}; media semplice indicativa dei ${changes.length} strumenti disponibili: ${sgn(avg)}%.`);
    lines.push(`Positivi: ${pos}; negativi: ${neg}; stabili: ${neu}.`);
    if (reg.length) lines.push(`Gruppo più forte: ${reg.at(-1)[1]} (${sgn(reg.at(-1)[0])}%); più debole: ${reg[0][1]} (${sgn(reg[0][0])}%).`);
    lines.push("La media non è il rendimento di un portafoglio: non considera pesi, costi, valute o correlazioni.");
  }

  if (env?.GROQ_API_KEY && metrics) {
    const result = await requestGroq(env, [
      { role: "system", content: "Sei un analista quantitativo prudente. Analizza esclusivamente i dati numerici forniti. Scrivi in italiano, in 3-5 punti brevi: lettura del quadro, ampiezza dei rialzi/ribassi, differenze geografiche, rischi e cosa servirebbe per confermare il segnale. Non inventare cause, notizie, dati macro, prezzi o previsioni. Distingui sempre osservazioni e interpretazioni. Un campione di ETF, fondi e indici non rappresenta l'intera economia. Non dare consigli di investimento né probabilità. Specifica che un dato giornaliero non dimostra un trend strutturale." },
      { role: "user", content: `Valutazione dei mercati basata sui seguenti dati Yahoo Finance, potenzialmente ritardati. I numeri sono la fonte vincolante e non vanno modificati. Metriche: ${JSON.stringify(metrics)}. Variazioni osservate: ${JSON.stringify(available)}.` }
    ], deps, 450);
    lines.push("", "🧠 LETTURA IA GROQ");
    lines.push(result.ok ? result.text : groqErrorLabel(result));
  } else if (env?.GROQ_API_KEY && !metrics) {
    lines.push("", "🧠 LETTURA IA GROQ", "Non generata: dati insufficienti.");
  } else {
    lines.push("", "🧠 LETTURA IA GROQ", "Non attiva: chiave GROQ_API_KEY non configurata.");
  }
  lines.push("", "⚠️ LIMITI E FONTI", "Quotazioni indicative da Yahoo Finance, eventualmente ritardate. Nessun dato macro ufficiale è incluso. Il punteggio/regola quantitativa descrive solo il campione osservato: non è una probabilità né consulenza finanziaria.");
  return lines.join("\n").slice(0, 3900);
}

async function testGroqConnection(env, deps = {}) {
  const result = await requestGroq(env, [
    { role: "system", content: "Rispondi solo con: OK" },
    { role: "user", content: "Verifica tecnica del collegamento." }
  ], deps, 10);
  if (result.ok) return `✅ Collegamento Groq riuscito. Modello: ${env.GROQ_MODEL || "openai/gpt-oss-20b"}. La chiave è stata accettata e il modello ha risposto.`;
  return `❌ Verifica Groq non riuscita. ${groqErrorLabel(result)} La chiave non viene mai mostrata.`;
}

export async function renderMyPac(fetchFn = fetchChart, now = new Date()) {
  const quotes = await Promise.all(MY_PAC_FUNDS.map(async ([name, symbol, isin]) => {
    try {
      const quote = await fetchFn(symbol);
      const value = Number(quote.value);
      if (!Number.isFinite(value)) throw new Error("prezzo non valido");
      return { name, symbol, isin, quote: { ...quote, value }, ok: true };
    } catch {
      return { name, symbol, isin, ok: false };
    }
  }));
  const lines = ["💼 I MIEI PAC — FONDI PERSONALI", `🕒 ${nowFmt.format(now).replace(",", "")} (ora italiana)`, ""];
  for (const row of quotes) {
    if (!row.ok) {
      lines.push(`⚪ ${row.name} (${row.isin}): quotazione non disponibile (${row.symbol})`);
      continue;
    }
    const { value, change, currency, time } = row.quote;
    const variation = change == null || !Number.isFinite(Number(change)) ? "n.d." : `${sgn(Number(change))}%`;
    const icon = change == null ? "⚪" : change > 0.05 ? "🟢" : change < -0.05 ? "🔴" : "🟡";
    const stamp = time ? stampFmt.format(time).replace(",", "") : "ora n.d.";
    lines.push(`${icon} ${row.name} (${row.isin})\\n   Quota: ${value.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 })} ${currency || ""} · variazione: ${variation} · ${stamp}`);
  }
  lines.push("", "Dati indicativi da Yahoo Finance, eventualmente ritardati; variazione giornaliera, non rendimento del PAC. Non è consulenza finanziaria.");
  return lines.join("\\n").slice(0, 3900);
}

// ---------- comandi ----------
export async function handleCommand(text, chatId, env, deps = {}) {
  const raw = text.trim();
  const sp = raw.search(/\s/);
  const head = sp === -1 ? raw : raw.slice(0, sp);
  const argument = sp === -1 ? "" : raw.slice(sp + 1).trim();
  const command = head.split("@")[0].toLowerCase();
  const chat = String(chatId);

  switch (command) {
    case "/start":
      return "Radar Normativo è pronto. Usa /aiuto per vedere i comandi.";
    case "/aiuto":
    case "/help":
      return HELP;
    case "/miepac":
      return renderMyPac(deps.fetchChart || fetchChart, deps.now || new Date());
    case "/mercati":
    case "/finanza":
    case "/finanzaoggi":
      return renderMarkets(deps.fetchChart || fetchChart, env, deps);
    case "/groqtest":
      return testGroqConnection(env, deps);
    case "/finanzieri":
      return renderHistoricalMarkets("yesterday", deps.fetchChartHistory || fetchChartHistory, deps.now || new Date());
    case "/finanza7giorni":
      return renderHistoricalMarkets("week", deps.fetchChartHistory || fetchChartHistory, deps.now || new Date());
    case "/filtri": {
      if (!env.STATE) return "Filtri non disponibili: manca il KV 'STATE' del Worker.";
      if (argument.toLowerCase() === "off") {
        await env.STATE.delete(`filters:${chat}`);
        return "Filtri disattivati.";
      }
      if (argument) {
        const terms = [...new Set(argument.split(",").map((t) => t.trim()).filter(Boolean))].slice(0, 20);
        if (!terms.length) return "Scrivi i termini separati da virgola, oppure /filtri off.";
        await env.STATE.put(`filters:${chat}`, JSON.stringify(terms));
        return "Filtri salvati: " + terms.join(", ");
      }
      const f = await getFilters(env, chat);
      return f.length ? "Filtri attivi: " + f.join(", ") : "Nessun filtro attivo. Imposta con /filtri lavoro, fisco oppure usa /filtri off.";
    }
    case "/fonti": {
      const cfg = await ghJson(env, "config/sources.json", deps.fetchGithub || fetch);
      const sources = Array.isArray(cfg?.sources) ? cfg.sources : [];
      if (!sources.length) return "Non riesco a leggere le fonti configurate.";
      return "Fonti configurate:\n" + sources.map((s) => `• ${s.name || "Fonte senza nome"}\n  ${s.url || ""}`).join("\n");
    }
    case "/stato": {
      const fetchGithub = deps.fetchGithub || fetch;
      const [archiveResult, sourcesResult, healthResult] = await Promise.allSettled([
        archiveItems(env, fetchGithub),
        ghJson(env, "config/sources.json", fetchGithub),
        ghJson(env, "data/source_health.json", fetchGithub)
      ]);
      const lines = ["Radar Normativo: bot attivo (Cloudflare Workers)."];
      if (archiveResult.status === "fulfilled") {
        const { archive, items } = archiveResult.value;
        lines.push(`Archivio: OK · ${items.length} elementi · aggiornato ${archive.updated_at || "data non disponibile"}`);
      } else {
        lines.push(`Archivio: ERRORE · ${String(archiveResult.reason?.message || "lettura non riuscita").slice(0, 180)}`);
      }
      if (sourcesResult.status === "fulfilled" && Array.isArray(sourcesResult.value?.sources)) {
        lines.push(`Fonti configurate: OK · ${sourcesResult.value.sources.length}`);
      } else {
        const reason = sourcesResult.status === "rejected" ? sourcesResult.reason?.message : "configurazione fonti non valida";
        lines.push(`Fonti configurate: ERRORE · ${String(reason || "lettura non riuscita").slice(0, 180)}`);
      }
      if (healthResult.status === "fulfilled" && Array.isArray(healthResult.value?.source_results)) {
        const results = healthResult.value.source_results.filter((s) => s && typeof s === "object");
        const ok = results.filter((s) => s.ok).length;
        lines.push(`Ultima scansione: ${ok === results.length ? "OK" : "ATTENZIONE"} · ${ok}/${results.length} fonti OK · ${healthResult.value.generated_at || "data non disponibile"}`);
        for (const source of results.filter((s) => !s.ok)) {
          const required = source.required === false ? "opzionale" : "obbligatoria";
          lines.push(`• ERRORE (${required}) — ${source.name || "fonte"}: ${String(source.error || "errore non specificato").slice(0, 140)}`);
        }
      } else {
        lines.push("Ultima scansione: non disponibile (nessun esito persistito o archivio remoto non raggiungibile).");
      }
      lines.push("Lo stato giuridico degli atti non è certificato automaticamente.");
      return lines.join("\n");
    }
    case "/ia": {
      if (!argument) return "Uso: /ia seguito dalla domanda normativa. Esempio: /ia quali novità fiscali sono state pubblicate?";
      return answerWithGroq(argument, env, deps);
    }
    case "/ai":
    case "/economia": {
      if (!argument) return "Uso: /ai o /economia seguito da una domanda su economia, aziende, borse, tassi, inflazione o mercati.";
      return answerWithEconomicNews(argument, env, deps);
    }
    case "/cerca": {
      if (!argument) return "Uso: /cerca parola o argomento";
      const term = argument.toLowerCase();
      const filters = await getFilters(env, chat);
      const { items } = await archiveItems(env, deps.fetchGithub || fetch);
      const found = items.filter((i) => `${i.title || ""} ${i.summary || ""}`.toLowerCase().includes(term) && matchesFilter(i, filters));
      return formatItems(found, `Nessun risultato per «${argument}».`);
    }
    case "/ultime":
    case "/oggi":
    case "/ieri":
    case "/ultimi7giorni": {
      const filters = await getFilters(env, chat);
      let { items } = await archiveItems(env, deps.fetchGithub || fetch);
      items = items.sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || ""))).filter((i) => matchesFilter(i, filters));
      const today = romeDay(deps.now || new Date());
      let heading = "Ultime pubblicazioni";
      if (command === "/oggi") {
        items = items.filter((i) => publishedDay(i) === today);
        heading = "Pubblicazioni di oggi";
      } else if (command === "/ieri") {
        const y = shiftDay(today, -1);
        items = items.filter((i) => publishedDay(i) === y);
        heading = `Pubblicazioni di ieri (${y})`;
      } else if (command === "/ultimi7giorni") {
        const start = shiftDay(today, -6);
        items = items.filter((i) => { const d = publishedDay(i); return d && d >= start && d <= today; });
        heading = `Pubblicazioni ultimi 7 giorni (${start} — ${today})`;
      }
      if (!items.length && filters.length) return `Nessuna pubblicazione trovata con i filtri attivi: ${filters.join(", ")}.`;
      return heading + "\n\n" + formatItems(items, "Nessuna pubblicazione disponibile.");
    }
    default:
      return "Comando non riconosciuto. Usa /aiuto per l'elenco dei comandi.";
  }
}

// ---------- webhook ----------
export async function sendMessage(env, chatId, text, fetchFn = fetch) {
  if (!env?.TELEGRAM_BOT_TOKEN) throw new Error("TELEGRAM_BOT_TOKEN non configurato");
  let response;
  try {
    response = await fetchFn(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: text.slice(0, 4000), disable_web_page_preview: true }),
      signal: AbortSignal.timeout(10000)
    });
  } catch { throw new Error("Telegram non raggiungibile o timeout durante sendMessage"); }
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error(`Telegram ha restituito una risposta non valida (HTTP ${response.status})`); }
  if (!response.ok || payload?.ok !== true) {
    const description = String(payload?.description || "errore API").slice(0, 180);
    throw new Error(`Invio Telegram fallito (HTTP ${response.status}): ${description}`);
  }
  return payload.result;
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== "POST") return new Response("Radar Normativo bot attivo.", { status: 200 });
    // Solo Telegram conosce questo segreto (impostato in setWebhook).
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    let update;
    try { update = await request.json(); } catch { return new Response("ok"); }
    const msg = update?.message;
    const text = String(msg?.text || "").trim();
    // Come nel bot originale: solo la chat autorizzata, solo comandi.
    if (!msg || String(msg.chat?.id) !== String(env.TELEGRAM_CHAT_ID) || !text.startsWith("/")) return new Response("ok");
    ctx.waitUntil(
      (async () => {
        let reply;
        try { reply = await handleCommand(text, msg.chat.id, env); }
        catch { reply = "Errore temporaneo nell'elaborazione del comando. Riprova tra poco."; }
        try { await sendMessage(env, msg.chat.id, reply); }
        catch (error) { console.error("Telegram sendMessage failed:", String(error?.message || error).slice(0, 240)); }
      })()
    );
    return new Response("ok");
  },
};
