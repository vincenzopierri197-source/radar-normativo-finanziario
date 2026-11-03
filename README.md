# Radar Normativo + Radar Finanziario 📡📈

Riepilogo giornaliero Telegram che unisce nuove pubblicazioni normative e monitoraggio indicativo di nove strumenti finanziari.

- Fonti normative italiane ed europee e attività parlamentare configurate in `config/sources.json`.
- Archivio e deduplicazione delle notizie già inviate.
- Quote indicative e variazioni per Dow Jones, JGLO, CHINA.MI, 0P0001LMEZ.F, 0P0000CO6N.F, FTSEMIB.MI, 0P0001BRM8.F, IGS1.SG e 0P00000ZJK.F.
- Valutazione complessiva descrittiva basata solo sui dati disponibili, senza inventare valori né attribuire pesi di portafoglio ignoti.

## Programmazione

GitHub Actions avvia i radar con tentativi orari dalle 08:00 alle 12:00 Europe/Rome (gli orari UTC sono definiti nei workflow). I marker giornalieri impediscono invii duplicati. Il monitor parte alle 15:15 UTC, dopo l'ultimo slot di retry con margine per il completamento. Valuta i run schedule usando la data locale Europe/Rome e considera validi anche gli avvii tardivi nella stessa giornata; run manuali e run di date precedenti non sostituiscono il controllo giornaliero. Se il radar è già stato completato, un successivo run saltato per marker non costituisce un nuovo successo operativo.

Configurare i secrets `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`. Per il comando AI `/ia` del Worker Cloudflare, aggiungere `GROQ_API_KEY` come secret nelle impostazioni del repository GitHub Actions; il workflow di deploy lo trasferisce al Worker. Facoltativamente si può impostare `GROQ_MODEL` nel Worker (predefinito `openai/gpt-oss-20b`). La chiave si crea in GroqCloud e non va mai inserita nel codice o committata nel repository. Le quotazioni provengono dall'endpoint chart Yahoo Finance, possono essere ritardate e alcuni simboli potrebbero non essere disponibili.

## Installazione e test

Python 3.11+: `python -m pip install -e ".[dev]"` e `pytest`.

## Comandi

`python -m radar_normativo telegram --input data/new_items.json --ledger data/telegram_sent.json --finance --dry-run`

`python -m radar_normativo bot` avvia il polling interattivo e richiede un host sempre acceso. Comandi AI: `/ia domanda` interroga l’archivio normativo locale; `/ai domanda` e `/economia domanda` cercano notizie economiche recenti tramite Google News RSS e le sintetizzano con Groq, citando titolo, testata, data e link quando disponibili. La ricerca può trovare notizie di Reuters, Bloomberg, Financial Times, CNBC, Yahoo Finance e testate italiane, ma la presenza di ogni singola testata non è garantita. Il feed fornisce metadati e brevi descrizioni, non accesso garantito al testo integrale degli articoli o ai contenuti a pagamento. Le quotazioni sono disponibili con `/mercati`; per fonti e dati non disponibili l’AI deve dichiarare i limiti. Le schede normative non certificano la vigenza e i contenuti economici non sono consulenza finanziaria.
