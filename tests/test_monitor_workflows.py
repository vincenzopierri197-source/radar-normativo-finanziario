from datetime import datetime, timezone

from radar_normativo.monitor_workflows import missing_reports


def test_requires_successful_scheduled_runs_in_rome_window():
    runs = {
        "collect.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-02T08:05:00+00:00",
        }],
        "finance.yml": [{
            "event": "schedule", "conclusion": "failure",
            "created_at": "2026-11-02T09:05:00+00:00",
        }],
    }

    missing = missing_reports(runs, datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc))

    # In inverno 08:05 UTC sono le 09:05 a Roma; il finanziario è fallito.
    assert missing == ["finance.yml"]


def test_rejects_success_outside_today_or_the_report_window():
    runs = {
        "collect.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-01T08:05:00Z",
        }],
        "finance.yml": [{
            "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-02T06:05:00Z",
        }],
    }

    missing = missing_reports(runs, datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc))

    assert missing == ["collect.yml", "finance.yml"]
