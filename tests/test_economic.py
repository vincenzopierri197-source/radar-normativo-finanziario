import json

from radar_normativo.economic import render_economic_report


def sample_rows():
    return [
        {"name": "FTSE MIB", "symbol": "FTSEMIB.MI", "region": "Italia", "ok": True, "change_pct": 1.2},
        {"name": "Dow Jones", "symbol": "^DJI", "region": "USA", "ok": True, "change_pct": 0.7},
        {"name": "China fund", "symbol": "CHINA.MI", "region": "Cina", "ok": True, "change_pct": -0.1},
        {"name": "Missing", "symbol": "MISSING", "region": "Altro", "ok": False},
    ]


def test_economic_report_explains_market_score_without_claiming_macro_data():
    text = render_economic_report("economia", sample_rows())
    assert "Punteggio indicativo:" in text
    assert "Motivo principale:" in text
    assert "nessun dato macro ufficiale" in text.lower()


def test_scenario_report_is_conditional():
    text = render_economic_report("stime", sample_rows())
    assert "SCENARI CONDIZIONALI" in text
    assert "non previsioni con probabilità statistiche" in text


def test_risk_report_reports_missing_data():
    text = render_economic_report("rischi", sample_rows())
    assert "Copertura incompleta: 1" in text
    assert "Rischi macro" in text


def test_no_data_does_not_invent_score():
    text = render_economic_report("andamento", [])
    assert "DATI INSUFFICIENTI" in text
    assert "Punteggio indicativo" not in text



class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({
            "choices": [{"message": {"content": "• Il campione mostra rialzi diffusi.\n• Un dato giornaliero non conferma un trend."}}]
        }).encode("utf-8")


def test_economic_report_uses_groq_with_market_metrics():
    calls = []

    def requester(request, timeout):
        calls.append((request, timeout))
        assert request.full_url == "https://api.groq.com/openai/v1/chat/completions"
        assert request.get_header("Authorization") == "Bearer test-key"
        body = json.loads(request.data)
        assert body["model"] == "openai/gpt-oss-20b"
        assert "FTSE MIB" in body["messages"][1]["content"]
        assert timeout == 20
        return FakeResponse()

    report = render_economic_report(
        "analisi", sample_rows(), groq_api_key="test-key", groq_requester=requester
    )

    assert len(calls) == 1
    assert "LETTURA IA GROQ" in report
    assert "rialzi diffusi" in report


def test_economic_report_reports_missing_groq_key():
    report = render_economic_report("analisi", sample_rows(), groq_api_key="")
    assert "Non attiva: chiave GROQ_API_KEY non configurata." in report


def test_economic_report_skips_groq_without_valid_market_data():
    calls = []
    report = render_economic_report(
        "analisi",
        [{"name": "FTSE MIB", "ok": False}],
        groq_api_key="test-key",
        groq_requester=lambda *args, **kwargs: calls.append(args),
    )
    assert calls == []
    assert "Non generata: dati numerici insufficienti." in report



def test_economic_report_falls_back_if_groq_is_unavailable():
    def unavailable(*args, **kwargs):
        raise OSError("connection refused")

    report = render_economic_report(
        "analisi",
        sample_rows(),
        groq_api_key="must-not-leak",
        groq_requester=unavailable,
    )
    assert "Non disponibile: errore di rete o risposta Groq non valida." in report
    assert "must-not-leak" not in report
