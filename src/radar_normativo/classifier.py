"""Classificazione tematica euristica multilingue e non giuridicamente vincolante."""
from __future__ import annotations

# Parole chiave italiane e inglesi: i feed EUR-Lex possono essere in inglese.
RULES: dict[str, tuple[str, ...]] = {
    "fisco": (
        "fisco", "tribut", "imposta", "iva", "irpef", "ires", "agenzia delle entrate",
        "accertamento fiscale", "tax", "taxation", "taxes", "vat", "value added tax",
        "income tax", "corporate tax", "excise duty", "customs duty",
    ),
    "lavoro": (
        "lavoro", "lavoratore", "lavoratori", "contratto collettivo", "licenziamento",
        "salario", "stipendio", "occupazione", "employment", "employee", "employees",
        "european works councils", "workers councils", "information and consultation rights",
        "worker", "workers", "labour", "labor", "working conditions", "minimum wage",
    ),
    "previdenza": (
        "previdenza", "pensione", "pensioni", "inps", "contributi previdenziali",
        "ammortizzatori sociali", "social security", "social protection", "pension",
        "pensions", "unemployment benefit",
    ),
    "imprese": (
        "impresa", "imprese", "società", "societario", "camera di commercio",
        "registro delle imprese", "fallimento", "insolvenza", "company", "companies",
        "enterprise", "enterprises", "corporate", "insolvency", "bankruptcy",
        "anti-dumping", "anti dumping", "imports", "import duty",
    ),
    "economia_finanza": (
        "bilancio", "finanza", "banca", "bancario", "mercato finanziario",
        "debito pubblico", "manovra economica", "financial market", "financial markets",
        "banking", "bank", "banks", "capital market", "public debt", "budget",
        "state aid", "competition", "buoni del tesoro", "titoli di stato",
        "consob", "borsa valori", "mercato mobiliare", "financial instruments",
        "settlement discipline", "central securities depository", "central securities depositories",
        "titoli del tesoro", "government bond", "government bonds", "treasury bond",
        "treasury bonds", "securities", "assicurazione", "assicurazioni", "ivass",
        "insurance", "insurer", "insurers",
    ),
    "giustizia_diritto_penale": (
        "codice penale", "reato", "reati", "procedura penale", "sanzione penale",
        "giustizia", "criminal law", "criminal procedure", "court", "courts",
        "judicial", "justice", "offence", "offense", "penalty",
    ),
    "ambiente_energia": (
        "ambiente", "ambientale", "energia", "energetico", "emissioni", "rifiuti",
        "clima", "environment", "environmental", "energy", "renewable", "emissions",
        "waste", "climate", "electricity", "gas supply", "tutela paesaggistica",
        "paesaggio rurale", "paesaggistico", "paesaggistica",
    ),
    "salute_farmaci": (
        "salute", "sanità", "sanitario", "farmaco", "farmaci", "medicinale", "medicinali",
        "biocidal product", "biocidal products",
        "aifa", "medicinali per uso umano", "autorizzazione all'immissione in commercio",
        "health", "healthcare", "public health", "medicine", "medicines", "medicinal product",
        "medicinal products", "pharmaceutical", "pharmaceuticals", "veterinary medicinal",
    ),
    "agricoltura_alimentazione": (
        "agricoltura", "agricolo", "agricoli", "alimentare", "alimenti", "mangimi",
        "pesca", "prodotti agricoli", "agriculture", "agricultural", "food", "feed",
        "fisheries", "fishery", "food additives", "food additive", "geographical indication",
        "avian influenza", "animal health", "animals and goods intended for human consumption",
        "school fruit and vegetables", "school milk", "vine and wine",
        "international organisation of vine and wine",
        "vigneto", "vigneti", "viticolo", "viticoli", "viticoltura", "vineyard", "vineyards",
        "protected geographical indication", "lupin", "nitrate and nitrite",
        "poultry", "fresh meat", "sheep pox", "goat pox", "seed potatoes",
        "fishing effort", "maximum residue levels", "pesticide", "pesticides",
        "plant protection product", "plant protection products", "curdlan",
        "difenoconazole", "acequinocyl", "deltamethrin",
    ),
    "trasporti_infrastrutture": (
        "trasporto", "trasporti", "infrastruttura", "infrastrutture", "strada", "stradale",
        "veicolo", "veicoli", "sicurezza stradale", "transport", "transportation",
        "infrastructure", "road safety", "road transport", "vehicle", "vehicles",
        "aviation", "maritime transport", "vehicle approval", "vehicles of categories m2 or m3",
        "inland navigation", "gsm-r", "railway", "railways", "mobile driving licence",
        "mobile driving licences", "driving licence", "driving licences",
    ),
    "digitale_cyber": (
        "digitale", "cybersecurity", "cyber security", "cybercrime", "cybercriminalità",
        "telecomunicazioni", "comunicazioni elettroniche", "digital", "cyber",
        "high-risk ai systems", "artificial intelligence",
        "electronic communications", "information technology", "space programme",
        "secure connectivity", "satellite communications",
    ),
    "difesa_sicurezza": (
        "difesa", "forze armate", "forze di polizia", "polizia locale", "sicurezza nazionale",
        "defence", "defense", "armed forces", "peace facility", "military",
        "restrictive measures",
    ),
}


def classify_topics(title: str, summary: str = "") -> list[str]:
    """Restituisce tutte le categorie con corrispondenze lessicali nel testo."""
    # Uniforma spazi, tab, newline e spazi Unicode prima del matching lessicale.
    text = " ".join(f"{title} {summary}".casefold().split())
    return [
        topic
        for topic, keywords in RULES.items()
        if any(keyword in text for keyword in keywords)
    ]
