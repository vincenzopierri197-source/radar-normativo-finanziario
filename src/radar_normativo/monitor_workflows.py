"""Verifica che i report giornalieri siano stati davvero consegnati.

Un run GitHub Actions può concludersi con successo anche quando il filtro
temporale salta i passi operativi. Il monitor controlla quindi il passo
Telegram, non soltanto la conclusione complessiva del run.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
WORKFLOWS = {
    "collect.yml": "Send normative daily Telegram briefing",
    "finance.yml": "Send independent financial briefing to Telegram",
}


def _local_day(run: dict) -> str | None:
    created = run.get("created_at")
    if not created:
        return None
    try:
        return datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(ROME).date().isoformat()
    except (TypeError, ValueError):
        return None


def _same_day_runs(runs: list[dict], today: str) -> list[dict]:
    return [
        run for run in runs
        if run.get("event") == "schedule" and _local_day(run) == today
    ]


def missing_reports(
    workflow_runs: dict[str, list[dict]],
    successful_report_ids: set[int],
    now: datetime | None = None,
) -> list[str]:
    """Workflow senza invio Telegram riuscito nella data italiana."""
    current = now or datetime.now(ROME)
    today = current.astimezone(ROME).date().isoformat()
    missing = []
    for workflow in WORKFLOWS:
        todays = _same_day_runs(workflow_runs.get(workflow, []), today)
        if not any(
            run.get("conclusion") == "success"
            and run.get("id") in successful_report_ids
            for run in todays
        ):
            missing.append(workflow)
    return missing


def _request_json(url: str, token: str) -> dict:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Risposta GitHub non valida")
    return payload


def _fetch_runs(repo: str, workflow: str, token: str) -> list[dict]:
    query = urllib.parse.urlencode({"branch": "main", "per_page": 100})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?{query}"
    payload = _request_json(url, token)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError(f"Risposta GitHub non valida per {workflow}")
    return runs


def _report_step_succeeded(jobs: list[dict], step_name: str) -> bool:
    return any(
        isinstance(step, dict)
        and step.get("name") == step_name
        and step.get("conclusion") == "success"
        for job in jobs if isinstance(job, dict)
        for step in job.get("steps", [])
    )


def _fetch_report_succeeded(repo: str, run_id: int, step_name: str, token: str) -> bool:
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    payload = _request_json(url, token)
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError(f"Risposta GitHub non valida per il run {run_id}")
    return _report_step_succeeded(jobs, step_name)


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        print("::error::GITHUB_TOKEN o GITHUB_REPOSITORY non configurato")
        return 2

    try:
        runs = {workflow: _fetch_runs(repo, workflow, token) for workflow in WORKFLOWS}
        now = datetime.now(ROME)
        today = now.date().isoformat()
        successful_report_ids = set()
        for workflow, step_name in WORKFLOWS.items():
            for run in _same_day_runs(runs.get(workflow, []), today):
                run_id = run.get("id")
                if run_id and run.get("conclusion") == "success" and _fetch_report_succeeded(
                    repo, run_id, step_name, token
                ):
                    successful_report_ids.add(run_id)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"::error::Impossibile verificare le consegne dei radar: {str(exc)[:240]}")
        return 2

    missing = missing_reports(runs, successful_report_ids, now)
    for workflow in WORKFLOWS:
        todays = _same_day_runs(runs.get(workflow, []), today)
        if not todays:
            print(f"NESSUN RUN SCHEDULATO OGGI: {workflow}")
            continue
        for run in todays:
            local = _local_day(run)
            print(
                f"{workflow}: run {run.get('id')} "
                f"{'report inviato' if run.get('id') in successful_report_ids else 'invio non riuscito o saltato'} "
                f"(data Europe/Rome {local}) — {run.get('html_url', '')}"
            )

    if missing:
        print("::error::Nessun invio Telegram riuscito oggi (Europe/Rome) per: " + ", ".join(missing))
        return 1
    print("Verifica OK: entrambi i radar hanno consegnato il report giornaliero a Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
