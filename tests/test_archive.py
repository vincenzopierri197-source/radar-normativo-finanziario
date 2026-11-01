import json

import pytest

from radar_normativo.archive import update_archive


def write_scan(path, generated_at, items, source_results=None):
    path.write_text(
        json.dumps({
            "schema_version": 1,
            "generated_at": generated_at,
            "item_count": len(items),
            "source_results": source_results if source_results is not None else [{"name": "Fonte test", "ok": True, "items": len(items)}],
            "items": items,
        }),
        encoding="utf-8",
    )


def test_archive_records_new_items_and_preserves_first_seen(tmp_path):
    latest = tmp_path / "latest.json"
    archive = tmp_path / "archive.json"
    new_items = tmp_path / "new_items.json"
    item = {"id": "abc123", "title": "Atto di prova", "url": "https://example.test/atto"}

    write_scan(latest, "2026-10-20T06:00:00+00:00", [item])
    first = update_archive(latest, archive, new_items)
    assert first["archive_count"] == 1
    assert first["new_item_count"] == 1

    write_scan(latest, "2026-10-21T06:00:00+00:00", [item])
    second = update_archive(latest, archive, new_items)
    saved = json.loads(archive.read_text(encoding="utf-8"))["items"][0]
    new_scan = json.loads(new_items.read_text(encoding="utf-8"))

    assert second["archive_count"] == 1
    assert second["new_item_count"] == 0
    assert saved["first_seen_at"] == "2026-10-20T06:00:00+00:00"
    assert saved["last_seen_at"] == "2026-10-21T06:00:00+00:00"
    assert saved["seen_count"] == 2
    assert new_scan["items"] == []


def test_archive_matches_normalized_url_when_legacy_id_changes(tmp_path):
    latest = tmp_path / "latest.json"
    archive = tmp_path / "archive.json"
    new_items = tmp_path / "new_items.json"
    old_item = {
        "id": "old-id",
        "title": "Atto UE",
        "url": "https://eur-lex.europa.eu/./legal-content/AUTO/?uri=CELEX:32026R1234",
        "first_seen_at": "2026-10-01T00:00:00+00:00",
        "last_seen_at": "2026-10-01T00:00:00+00:00",
        "seen_count": 3,
    }
    archive.write_text(json.dumps({"items": [old_item], "item_count": 1}), encoding="utf-8")
    new_item = {
        "id": "new-id",
        "title": "Atto UE aggiornato",
        "url": "https://eur-lex.europa.eu/legal-content/AUTO/?uri=CELEX:32026R1234",
    }

    write_scan(latest, "2026-10-21T06:00:00+00:00", [new_item])
    result = update_archive(latest, archive, new_items)
    saved = json.loads(archive.read_text(encoding="utf-8"))

    assert result["archive_count"] == 1
    assert result["new_item_count"] == 0
    assert saved["items"][0]["id"] == "old-id"
    assert saved["items"][0]["seen_count"] == 4
    assert saved["items"][0]["first_seen_at"] == "2026-10-01T00:00:00+00:00"


def test_archive_refuses_incomplete_scan(tmp_path):
    latest = tmp_path / "latest.json"
    write_scan(
        latest,
        "2026-10-20T06:00:00+00:00",
        [],
        source_results=[{"name": "Fonte test", "ok": False, "error": "timeout"}],
    )

    with pytest.raises(ValueError, match="scansione incompleta"):
        update_archive(latest, tmp_path / "archive.json", tmp_path / "new_items.json")

    assert not (tmp_path / "archive.json").exists()

def test_archive_does_not_increment_seen_count_twice_on_same_day(tmp_path):
    latest = tmp_path / "latest.json"
    archive = tmp_path / "archive.json"
    new_items = tmp_path / "new_items.json"
    item = {"id": "daily", "title": "Atto giornaliero", "url": "https://example.test/daily"}

    write_scan(latest, "2026-10-20T06:00:00+00:00", [item])
    update_archive(latest, archive, new_items)
    write_scan(latest, "2026-10-20T18:00:00+00:00", [item])
    update_archive(latest, archive, new_items)

    saved = json.loads(archive.read_text(encoding="utf-8"))["items"][0]
    assert saved["seen_count"] == 1
    assert saved["last_seen_at"] == "2026-10-20T18:00:00+00:00"



def test_archive_observation_count_uses_utc_day_across_timezones(tmp_path):
    latest = tmp_path / "latest.json"
    archive = tmp_path / "archive.json"
    new_items = tmp_path / "new_items.json"
    item = {"id": "utc-day", "title": "Atto UTC", "url": "https://example.test/utc-day"}

    # 23:30 in UTC-02 is 01:30 UTC del giorno successivo.
    write_scan(latest, "2026-10-20T23:30:00-02:00", [item])
    update_archive(latest, archive, new_items)

    # È ancora lo stesso giorno UTC, anche se la data locale nel timestamp cambia.
    write_scan(latest, "2026-10-21T01:00:00+00:00", [item])
    update_archive(latest, archive, new_items)

    saved = json.loads(archive.read_text(encoding="utf-8"))["items"][0]
    assert saved["seen_count"] == 1
    assert saved["last_seen_at"] == "2026-10-21T01:00:00+00:00"



def test_archive_reemits_items_first_seen_today_for_telegram_retries(tmp_path):
    latest = tmp_path / "latest.json"
    archive = tmp_path / "archive.json"
    new_items = tmp_path / "new_items.json"
    item = {"id": "retry-me", "title": "Atto da notificare", "url": "https://example.test/retry"}

    # Prima scansione: scoperta alle 08:00 italiane (07:00 UTC in ora solare).
    write_scan(latest, "2026-11-01T07:00:00+00:00", [item])
    first = update_archive(latest, archive, new_items)
    assert first["new_item_count"] == 1

    # Seconda scansione: l'archivio è già stato salvato, ma la notifica
    # potrebbe essere fallita. La scheda deve restare nel flusso di retry.
    write_scan(latest, "2026-11-01T08:00:00+00:00", [item])
    second = update_archive(latest, archive, new_items)
    retry_payload = json.loads(new_items.read_text(encoding="utf-8"))

    assert second["new_item_count"] == 1
    assert [entry["id"] for entry in retry_payload["items"]] == ["retry-me"]

    # Il giorno successivo la scheda non deve più essere riproposta come nuova.
    write_scan(latest, "2026-11-02T07:00:00+00:00", [item])
    third = update_archive(latest, archive, new_items)
    next_day_payload = json.loads(new_items.read_text(encoding="utf-8"))

    assert third["new_item_count"] == 0
    assert next_day_payload["items"] == []
