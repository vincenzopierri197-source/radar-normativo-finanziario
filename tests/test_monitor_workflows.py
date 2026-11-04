from datetime import datetime, timezone

from radar_normativo.monitor_workflows import _report_step_succeeded, missing_reports


def test_accepts_successful_delayed_report_steps_later_in_rome_day():
    runs = {
        "collect.yml": [{
            "id": 1, "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-03T13:30:00Z",  # 14:30 CET
        }],
        "finance.yml": [{
            "id": 2, "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-03T13:20:00Z",  # 14:20 CET
        }],
    }

    assert missing_reports(
        runs, {1, 2}, datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
    ) == []


def test_successful_workflow_with_skipped_report_step_is_missing():
    runs = {
        "collect.yml": [{
            "id": 1, "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-03T13:30:00Z",
        }],
        "finance.yml": [{
            "id": 2, "event": "schedule", "conclusion": "success",
            "created_at": "2026-11-03T13:20:00Z",
        }],
    }

    assert missing_reports(
        runs, {2}, datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
    ) == ["collect.yml"]


def test_failure_skipped_run_manual_run_and_previous_day_do_not_count():
    runs = {
        "collect.yml": [
            {"id": 1, "event": "schedule", "conclusion": "failure", "created_at": "2026-11-03T13:30:00Z"},
            {"id": 2, "event": "schedule", "conclusion": "success", "created_at": "2026-11-03T12:30:00Z"},
            {"id": 3, "event": "workflow_dispatch", "conclusion": "success", "created_at": "2026-11-03T13:30:00Z"},
            {"id": 4, "event": "schedule", "conclusion": "success", "created_at": "2026-11-02T13:30:00Z"},
        ],
        "finance.yml": [],
    }

    assert missing_reports(
        runs, {1, 2, 3, 4}, datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
    ) == ["collect.yml", "finance.yml"]


def test_uses_rome_calendar_date_across_utc_midnight_and_dst():
    runs = {
        "collect.yml": [{
            "id": 1, "event": "schedule", "conclusion": "success",
            "created_at": "2026-03-29T22:30:00Z",  # 30 marzo a Roma
        }],
        "finance.yml": [{
            "id": 2, "event": "schedule", "conclusion": "success",
            "created_at": "2026-03-29T20:30:00Z",  # 29 marzo a Roma
        }],
    }

    assert missing_reports(
        runs, {1, 2}, datetime(2026, 3, 30, 0, 15, tzinfo=timezone.utc)
    ) == ["finance.yml"]



def test_report_monitor_requires_the_named_telegram_step_to_succeed():
    step = "Send normative daily Telegram briefing"
    assert _report_step_succeeded(
        [{"steps": [{"name": step, "conclusion": "success"}]}], step
    )
    assert not _report_step_succeeded(
        [{"steps": [{"name": step, "conclusion": "skipped"}]}], step
    )
    assert not _report_step_succeeded(
        [{"steps": [{"name": "Collect regulatory feeds", "conclusion": "success"}]}], step
    )
