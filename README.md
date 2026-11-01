# Radar Normativo + Radar Finanziario 📡📈

Riepilogo giornaliero Telegram che unisce nuove pubblicazioni normative e monitoraggio indicativo di nove strumenti finanziari.

- Fonti normative italiane ed europee e attività parlamentare configurate in `config/sources.json`.
- Archivio e deduplicazione delle notizie già inviate.
- Quote indicative e variazioni per Dow Jones, JGLO, CHINA.MI, 0P0001LMEZ.F, 0P0000CO6N.F, FTSEMIB.MI, 0P0001BRM8.F, IGS1.SG e 0P00000ZJK.F.
- Valutazione complessiva descrittiva basata solo sui dati disponibili, senza inventare valori né attribuire pesi di portafoglio ignoti.

## Programmazione
GitHub Actions riprova la scansione normativa ogni ora dalle 06:17 alle 12:17 UTC, fermandosi dopo il primo invio riuscito. Questo corrisponde alle 07:17–13:17 in ora solare italiana e alle 08:17–14:17 in ora legale. GitHub può avviare in ritardo i workflow pianificati, quindi l'orario effettivo di consegna non è garantito. Il riepilogo normativo Telegram è compatto e ordinato per priorità per restare in un solo messaggio; ogni atto conserva titolo e collegamento ufficiale. Configurare i secrets `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Per il comando AI `/ia` del Worker Cloudflare, aggiungere `GROQ_API_KEY` come secret nelle impostazioni del repository GitHub (Settings → Secrets and variables → Actions); il workflow di deploy lo trasferisce al Worker. Facoltativamente si può impostare `GROQ_MODEL` nel Worker (predefinito `openai/gpt-oss-20b`). La chiave si crea in GroqCloud e non va mai inserita nel codice o committata nel repository. Le quotazioni provengono dall'endpoint chart Yahoo Finance, possono essere ritardate e alcuni simboli potrebbero non essere disponibili.

## Installazione e test
Python 3.11+: `python -m pip install -e ".[dev]"` e `pytest`.

## Comandi
`python -m radar_normativo telegram --input data/new_items.json --ledger data/telegram_sent.json --finance --dry-run`

`python -m radar_normativo bot` avvia il polling interattivo e richiede un host sempre acceso. Comandi AI: `/ia domanda` interroga l’archivio normativo locale; `/ai domanda` e `/economia domanda` cercano notizie economiche recenti tramite Google News RSS e le sintetizzano con Groq, citando titolo, testata, data e link quando disponibili. La ricerca può trovare notizie di Reuters, Bloomberg, Financial Times, CNBC, Yahoo Finance e testate italiane, ma la presenza di ogni singola testata non è garantita. Il feed fornisce metadati e brevi descrizioni, non accesso garantito al testo integrale degli articoli o ai contenuti a pagamento. Le quotazioni sono disponibili con `/mercati`; per fonti e dati non disponibili l’AI deve dichiarare i limiti. Le schede normative non certificano la vigenza e i contenuti economici non sono consulenza finanziaria.
