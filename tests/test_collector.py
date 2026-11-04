import json
from types import SimpleNamespace

from radar_normativo.collector import collect_sources


def test_empty_sources_returns_valid_empty_scan(tmp_path):
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"version": 1, "sources": []}), encoding="utf-8")
    result = collect_sources(config)
    assert result["schema_version"] == 1
    assert result["item_count"] == 0
    assert result["items"] == []
    assert result["source_results"] == []
    assert result["generated_at"]


def test_missing_url_is_reported_without_crashing(tmp_path):
    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [{"name": "Fonte test"}]}), encoding="utf-8")
    result = collect_sources(config)
    assert result["item_count"] == 0
    assert result["source_results"][0]["ok"] is False
    assert result["source_results"][0]["error"] == "URL mancante"
    assert result["source_results"][0]["required"] is True


def test_normalizes_url_and_classifies_english_eu_titles(tmp_path, monkeypatch):
    import radar_normativo.collector as collector

    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [{
        "name": "EUR-Lex test", "url": "https://example.test/feed", "language": "en"
    }]}), encoding="utf-8")
    entry = {
        "link": "https://eur-lex.europa.eu/./legal-content/AUTO/?uri=CELEX:32026R1234",
        "title": "Commission Implementing Regulation on VAT and tax credit",
        "summary": "",
    }
    monkeypatch.setattr(collector, "_parse_feed", lambda _: SimpleNamespace(bozo=False, entries=[entry]))
    result = collect_sources(config)
    item = result["items"][0]
    assert item["url"] == "https://eur-lex.europa.eu/legal-content/AUTO/?uri=CELEX:32026R1234"
    assert "fisco" in item["topics"]
    assert item["relevance_score"] >= 30
    assert item["legal_status"] == "non_verificato"


def test_removes_redundant_celex_prefix_but_keeps_identifier_only_title(tmp_path, monkeypatch):
    import radar_normativo.collector as collector

    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [{
        "name": "EUR-Lex test", "url": "https://example.test/feed", "language": "en"
    }]}), encoding="utf-8")
    entries = [
        {"link": "https://eur-lex.europa.eu/legal-content/AUTO/?uri=CELEX:32026R1234",
         "title": "CELEX:32026R1234: Commission Implementing Regulation (EU) 2026/1234 on a test subject", "summary": ""},
        {"link": "https://eur-lex.europa.eu/legal-content/AUTO/?uri=CELEX:32026R1235R(01)",
         "title": "CELEX:32026R1235R(01)", "summary": "The corrigendum does not concern the English version."},
    ]
    monkeypatch.setattr(collector, "_parse_feed", lambda _: SimpleNamespace(bozo=False, entries=entries))
    result = collect_sources(config)
    titles = {item["url"]: item["title"] for item in result["items"]}
    assert titles["https://eur-lex.europa.eu/legal-content/AUTO/?uri=CELEX:32026R1234"] == "Commission Implementing Regulation (EU) 2026/1234 on a test subject"
    assert titles["https://eur-lex.europa.eu/legal-content/AUTO/?uri=CELEX:32026R1235R(01)"] == "CELEX:32026R1235R(01)"


def test_network_error_is_reported_with_detail(tmp_path, monkeypatch):
    import radar_normativo.collector as collector

    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [{
        "name": "Fonte obbligatoria", "url": "https://example.test/feed", "required": True
    }]}), encoding="utf-8")

    def fail(_):
        raise RuntimeError("HTTP 403 durante il download del feed")

    monkeypatch.setattr(collector, "_parse_feed", fail)
    result = collect_sources(config)
    source = result["source_results"][0]
    assert source["ok"] is False
    assert source["required"] is True
    assert "HTTP 403" in source["error"]


def test_valid_empty_feed_is_not_a_network_failure(tmp_path, monkeypatch):
    import radar_normativo.collector as collector

    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [{
        "name": "Fonte test", "url": "https://example.test/feed", "required": True
    }]}), encoding="utf-8")
    monkeypatch.setattr(collector, "_parse_feed", lambda _: SimpleNamespace(bozo=False, entries=[]))
    result = collect_sources(config)
    assert result["source_results"][0]["ok"] is True
    assert result["source_results"][0]["items"] == 0


def test_malformed_empty_feed_is_reported(tmp_path, monkeypatch):
    import radar_normativo.collector as collector

    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [{
        "name": "Fonte test", "url": "https://example.test/feed", "required": True
    }]}), encoding="utf-8")
    monkeypatch.setattr(collector, "_parse_feed", lambda _: SimpleNamespace(
        bozo=True, bozo_exception="syntax error", entries=[]
    ))
    result = collect_sources(config)
    assert result["source_results"][0]["ok"] is False
    assert "syntax error" in result["source_results"][0]["error"]


def test_parses_official_html_archive_titles_dates_and_links():
    from radar_normativo.collector import _parse_html_news

    html = b"""<h2>Nuovo decreto fiscale</h2>
    <a href="/atti/decreto-123">Testo completo</a>
    <time>4 novembre 2026</time>"""
    entries = _parse_html_news(html, "https://www.normattiva.it/showArchivioNews")

    assert len(entries) == 1
    assert entries[0]["title"] == "Nuovo decreto fiscale"
    assert entries[0]["link"] == "https://www.normattiva.it/atti/decreto-123"
    assert entries[0]["published"] == "2026-11-04T00:00:00+00:00"


def test_parses_senato_sparql_results():
    from radar_normativo.collector import _senato_bindings_to_entries

    payload = {
        "results": {"bindings": [{
            "titolo": {"value": "Disegno di legge in materia fiscale"},
            "dataPresentazione": {"value": "2026-11-04"},
            "ddl": {"value": "https://www.senato.it/ddl/123"},
        }]}
    }

    entries = _senato_bindings_to_entries(payload)

    assert entries == [{
        "title": "Disegno di legge in materia fiscale",
        "link": "https://www.senato.it/ddl/123",
        "published": "2026-11-04T00:00:00+00:00",
        "summary": "",
    }]


def test_collects_sources_configured_as_site_or_sparql(tmp_path, monkeypatch):
    import radar_normativo.collector as collector

    config = tmp_path / "sources.json"
    config.write_text(json.dumps({"sources": [
        {"name": "Normattiva", "site": "https://example.test/news", "required": False},
        {"name": "Senato", "sparql": "https://example.test/sparql", "required": False},
    ]}), encoding="utf-8")
    entry = {"title": "Nuova norma fiscale", "link": "https://example.test/atto", "published": "2026-11-04"}

    monkeypatch.setattr(collector, "_parse_normattiva_site", lambda _: [entry])
    monkeypatch.setattr(collector, "_parse_senato_sparql", lambda _: [entry])
    result = collect_sources(config)

    assert result["item_count"] == 1
    assert [source["ok"] for source in result["source_results"]] == [True, True]
    assert result["source_results"][0]["items"] == 1
    assert result["items"][0]["source_url"] == "https://example.test/sparql"
