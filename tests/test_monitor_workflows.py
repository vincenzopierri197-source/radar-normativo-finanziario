from datetime import datetime, timezone

from radar_normativo.monitor_workflows import missing_reports


def test_accepts_successful_delayed_scheduled_runs_later_in_rome_day():
    runs = {
        "collect.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-03T13:30:00Z",  # 14:30 CET
        }],
        "finance.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-03T13:20:00Z",  # 14:20 CET
        }],
    }

    assert missing_reports(runs, datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)) == []


def test_failure_and_skipped_runs_do_not_count_as_success():
    runs = {
        "collect.yml": [
            {"event": "schedule", "conclusion": "failure", "created_at": "2026-11-03T13:30:00Z"},
            {"event": "schedule", "conclusion": "skipped", "created_at": "2026-11-03T12:30:00Z"},
        ],
        "finance.yml": [
            {"event": "schedule", "conclusion": "success", "created_at": "2026-11-03T13:20:00Z"},
        ],
    }

    assert missing_reports(runs, datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)) == ["collect.yml"]


def test_uses_rome_calendar_date_across_utc_midnight_and_dst():
    runs = {
        "collect.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-03-29T22:30:00Z",  # 30 marzo a Roma
        }],
        "finance.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-03-29T20:30:00Z",  # 29 marzo a Roma
        }],
    }

    assert missing_reports(runs, datetime(2026, 3, 30, 0, 15, tzinfo=timezone.utc)) == ["finance.yml"]


def test_ignores_manual_runs_and_previous_rome_day():
    runs = {
        "collect.yml": [
            {"event": "workflow_dispatch", "conclusion": "success", "created_at": "2026-11-03T13:30:00Z"},
            {"event": "schedule", "conclusion": "success", "created_at": "2026-11-02T13:30:00Z"},
        ],
        "finance.yml": [],
    }

    assert missing_reports(runs, datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)) == [
        "collect.yml", "finance.yml"
    ]
