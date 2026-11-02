import json

import pytest

from radar_normativo.telegram import _send_message, send_new_items


def test_telegram_429_retries_after_server_delay(monkeypatch):
    from io import BytesIO
    from radar_normativo import telegram

    class Response(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    responses = iter([
        Response(b'{"ok":false,"error_code":429,"parameters":{"retry_after":3}}'),
        Response(b'{"ok":true,"result":{"message_id":1}}'),
    ])
    calls, delays = [], []
    monkeypatch.setattr(telegram.urllib.request, "urlopen", lambda *args, **kwargs: calls.append(1) or next(responses))
    monkeypatch.setattr(telegram.time, "sleep", delays.append)

    _send_message("test-token", "123", "test message")

    assert len(calls) == 2
    assert delays == [3]


def test_telegram_429_retry_is_bounded(monkeypatch):
    from io import BytesIO
    from radar_normativo import telegram

    class Response(BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    calls, delays = [], []
    monkeypatch.setattr(
        telegram.urllib.request, "urlopen",
        lambda *args, **kwargs: calls.append(1) or Response(b'{"ok":false,"error_code":429,"parameters":{"retry_after":1}}'),
    )
    monkeypatch.setattr(telegram.time, "sleep", delays.append)

    with pytest.raises(RuntimeError, match="429"):
        _send_message("test-token", "123", "test message")

    assert len(calls) == 4
    assert delays == [1, 1, 1]


def test_sends_only_unsent_items_and_persists_ledger(tmp_path):
    source = tmp_path / "new_items.json"
    ledger = tmp_path / "telegram_sent.json"
    items = [
        {"id": "already-sent", "title": "Vecchio", "url": "https://example.test/1"},
        {"id": "fresh", "title": "Nuova disposizione IVA", "priority": "alta", "url": "https://example.test/2"},
    ]
    source.write_text(json.dumps({"items": items}), encoding="utf-8")
    ledger.write_text(json.dumps({"schema_version": 1, "sent_ids": {"already-sent": "2026-10-20T00:00:00+00:00"}}), encoding="utf-8")
    sent = []

    result = send_new_items(
        source, ledger, token="fake-token", chat_id="@test",
        sender=lambda token, chat_id, message: sent.append((token, chat_id, message)),
    )

    assert result == {"sent": 1, "pending": 1, "skipped": 1}
    assert len(sent) == 1
    assert sent[0][0:2] == ("fake-token", "@test")
    assert "Nuova disposizione IVA" in sent[0][2]
    assert json.loads(ledger.read_text(encoding="utf-8"))["sent_ids"]["fresh"]


def test_aggregates_all_new_items_into_one_message(tmp_path):
    source = tmp_path / "new_items.json"
    ledger = tmp_path / "ledger.json"
    items = [
        {"id": "it", "title": "Nuova legge italiana", "source_name": "Gazzetta Ufficiale"},
        {"id": "eu", "title": "Nuovo regolamento europeo", "source_name": "EUR-Lex"},
        {"id": "court", "title": "Decisione costituzionale", "source_name": "Corte costituzionale"},
    ]
    source.write_text(json.dumps({"items": items}), encoding="utf-8")
    sent = []

    result = send_new_items(
        source, ledger, token="t", chat_id="c",
        sender=lambda token, chat_id, message: sent.append(message),
    )

    assert result == {"sent": 3, "pending": 3, "skipped": 0}
    assert len(sent) == 1
    assert all(item["title"] in sent[0] for item in items)


def test_dry_run_needs_no_credentials_and_does_not_write_ledger(tmp_path, capsys):
    source = tmp_path / "new_items.json"
    ledger = tmp_path / "telegram_sent.json"
    source.write_text(json.dumps({"items": [{"id": "x", "title": "Atto di prova"}]}), encoding="utf-8")

    result = send_new_items(source, ledger, dry_run=True)

    assert result == {"sent": 0, "pending": 1, "skipped": 0}
    assert "Atto di prova" in capsys.readouterr().out
    assert not ledger.exists()


def test_requires_credentials_for_real_send(tmp_path):
    source = tmp_path / "new_items.json"
    source.write_text(json.dumps({"items": [{"id": "x", "title": "Atto"}]}), encoding="utf-8")

    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        send_new_items(source, tmp_path / "ledger.json", token="", chat_id="")


def test_successfully_sent_item_is_not_sent_twice(tmp_path):
    source = tmp_path / "new_items.json"
    ledger = tmp_path / "ledger.json"
    source.write_text(json.dumps({"items": [{"id": "x", "title": "Atto"}]}), encoding="utf-8")
    calls = []

    send_new_items(source, ledger, token="t", chat_id="c", sender=lambda *args: calls.append(args))
    result = send_new_items(source, ledger, token="t", chat_id="c", sender=lambda *args: calls.append(args))

    assert len(calls) == 2
    assert "Atto" in calls[0][2]
    assert "Nessuna nuova pubblicazione normativa" in calls[1][2]
    assert result == {"sent": 0, "pending": 0, "skipped": 1}


def test_sends_daily_notice_when_no_new_items(tmp_path):
    source = tmp_path / "new_items.json"
    ledger = tmp_path / "ledger.json"
    source.write_text(json.dumps({"items": []}), encoding="utf-8")
    sent = []

    result = send_new_items(
        source, ledger, token="t", chat_id="c",
        sender=lambda token, chat_id, message: sent.append(message),
    )

    assert result == {"sent": 0, "pending": 0, "skipped": 0}
    assert len(sent) == 1
    assert "Nessuna nuova pubblicazione normativa" in sent[0]
