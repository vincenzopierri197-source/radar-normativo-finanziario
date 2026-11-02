import json
from datetime import datetime, timezone

from radar_normativo.bot import handle_command


def _fixtures(tmp_path):
    archive = tmp_path / "archive.json"
    sources = tmp_path / "sources.json"
    state = tmp_path / "bot_state.json"
    latest = tmp_path / "latest.json"
    today = datetime.now(timezone.utc).isoformat()
    archive.write_text(json.dumps({
        "updated_at": today,
        "items": [
            {"id": "1", "title": "Nuovo decreto fiscale", "summary": "Misure IVA e imposte", "url": "https://example.test/1", "source_name": "Gazzetta Ufficiale", "published_at": today, "topics": ["fisco"]},
            {"id": "2", "title": "Regolamento agricolo", "summary": "Norme per le aziende", "url": "https://example.test/2", "source_name": "EUR-Lex", "published_at": "2020-01-01T00:00:00+00:00", "topics": ["agricoltura"]},
        ],
    }), encoding="utf-8")
    sources.write_text(json.dumps({"sources": [{"name": "Gazzetta Ufficiale", "url": "https://example.test/feed"}]}), encoding="utf-8")
    latest.write_text(json.dumps({"source_results": [{"name": "Gazzetta Ufficiale", "ok": True}]}), encoding="utf-8")
    return archive, sources, state, latest


def test_start_help_and_sources(tmp_path):
    archive, sources, state, latest = _fixtures(tmp_path)
    args = {"archive_path": archive, "sources_path": sources, "state_path": state, "latest_path": latest}
    assert "pronto" in handle_command("/start", 123, **args)
    assert "/ultime" in handle_command("/aiuto", 123, **args)
    assert "Gazzetta Ufficiale" in handle_command("/fonti", 123, **args)


def test_search_latest_and_status(tmp_path):
    archive, sources, state, latest = _fixtures(tmp_path)
    args = {"archive_path": archive, "sources_path": sources, "state_path": state, "latest_path": latest}
    assert "decreto fiscale" in handle_command("/cerca fiscale", 123, **args)
    assert "Ultime pubblicazioni" in handle_command("/ultime", 123, **args)
    status = handle_command("/stato", 123, **args)
    assert "Elementi in archivio: 2" in status
    assert "OK" in status


def test_filters_are_saved_applied_and_cleared(tmp_path):
    archive, sources, state, latest = _fixtures(tmp_path)
    args = {"archive_path": archive, "sources_path": sources, "state_path": state, "latest_path": latest}
    assert "Filtri salvati" in handle_command("/filtri fiscale", 123, **args)
    assert "fiscale" in handle_command("/filtri", 123, **args)
    latest_text = handle_command("/ultime", 123, **args)
    assert "decreto fiscale" in latest_text
    assert "Regolamento agricolo" not in latest_text
    assert "disattivati" in handle_command("/filtri off", 123, **args)



def test_markets_command_returns_financial_briefing(tmp_path, monkeypatch):
    from radar_normativo import bot

    archive, sources, state, latest = _fixtures(tmp_path)
    monkeypatch.setattr(bot, "render_market_briefing", lambda: "📈 RADAR FINANZIARIO\\nValutazione complessiva: misto")
    response = handle_command(
        "/mercati", 123, archive_path=archive, sources_path=sources,
        state_path=state, latest_path=latest,
    )
    assert "RADAR FINANZIARIO" in response
    assert "Valutazione complessiva" in response


def test_yesterday_and_last_seven_days_commands(tmp_path):
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    archive, sources, state, latest = _fixtures(tmp_path)
    today = datetime.now(ZoneInfo("Europe/Rome")).date()
    yesterday = today - timedelta(days=1)
    older = today - timedelta(days=10)
    archive.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": [
            {"id": "y", "title": "Atto pubblicato ieri", "summary": "", "url": "https://example.test/y", "source_name": "GU", "published_at": yesterday.isoformat(), "topics": []},
            {"id": "t", "title": "Atto pubblicato oggi", "summary": "", "url": "https://example.test/t", "source_name": "GU", "published_at": today.isoformat(), "topics": []},
            {"id": "o", "title": "Atto più vecchio", "summary": "", "url": "https://example.test/o", "source_name": "GU", "published_at": older.isoformat(), "topics": []},
        ],
    }), encoding="utf-8")
    args = {"archive_path": archive, "sources_path": sources, "state_path": state, "latest_path": latest}

    yesterday_result = handle_command("/ieri", 123, **args)
    assert "Atto pubblicato ieri" in yesterday_result
    assert "Atto pubblicato oggi" not in yesterday_result

    week_result = handle_command("/ultimi7giorni", 123, **args)
    assert "Atto pubblicato ieri" in week_result
    assert "Atto pubblicato oggi" in week_result
    assert "Atto più vecchio" not in week_result



def test_financial_commands_and_aliases(tmp_path, monkeypatch):
    from radar_normativo import bot

    archive, sources, state, latest = _fixtures(tmp_path)
    calls = []
    def fake_report(mode):
        calls.append(mode)
        return f"report:{mode}"

    monkeypatch.setattr(bot, "render_finance_report", fake_report)
    args = {
        "archive_path": archive,
        "sources_path": sources,
        "state_path": state,
        "latest_path": latest,
    }

    assert handle_command("/finanza", 123, **args) == "report:current"
    assert handle_command("/finanzaoggi", 123, **args) == "report:current"
    assert handle_command("/finanzieri", 123, **args) == "report:yesterday"
    assert handle_command("/finanza7giorni", 123, **args) == "report:seven_days"
    assert calls == ["current", "current", "yesterday", "seven_days"]


def test_help_lists_official_normative_and_financial_commands(tmp_path):
    archive, sources, state, latest = _fixtures(tmp_path)
    help_text = handle_command(
        "/aiuto", 123, archive_path=archive, sources_path=sources,
        state_path=state, latest_path=latest,
    )
    for command in (
        "/start", "/aiuto", "/ultime", "/oggi", "/ieri", "/ultimi7giorni",
        "/cerca", "/fonti", "/filtri", "/stato", "/mercati", "/finanza",
        "/economia", "/finanzaoggi", "/finanzieri", "/finanza7giorni",
    ):
        assert command in help_text


def test_economia_command_returns_market_based_economic_report(tmp_path, monkeypatch):
    from radar_normativo import bot

    archive, sources, state, latest = _fixtures(tmp_path)
    calls = []
    monkeypatch.setattr(bot, "render_economic_report", lambda mode: calls.append(mode) or "Rapporto economico")

    result = handle_command(
        "/economia", 123, archive_path=archive, sources_path=sources,
        state_path=state, latest_path=latest,
    )

    assert result == "Rapporto economico"
    assert calls == ["economia"]



def test_ai_command_requires_a_question(tmp_path):
    archive, sources, state, latest = _fixtures(tmp_path)
    args = {"archive_path": archive, "sources_path": sources, "state_path": state, "latest_path": latest}
    response = handle_command("/ia", 123, **args)
    assert "Uso: /ia" in response


def test_ai_command_forwards_question_and_archive(tmp_path, monkeypatch):
    from radar_normativo import bot

    archive, sources, state, latest = _fixtures(tmp_path)
    calls = []
    monkeypatch.setattr(bot, "answer_with_groq", lambda question, archive_path: calls.append((question, archive_path)) or "Risposta AI")
    args = {"archive_path": archive, "sources_path": sources, "state_path": state, "latest_path": latest}
    response = handle_command("/ia quali novità fiscali?", 123, **args)
    assert response == "Risposta AI"
    assert calls == [("quali novità fiscali?", archive)]
