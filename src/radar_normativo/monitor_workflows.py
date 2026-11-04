"""Verifica i run schedulati giornalieri dei radar in base alla data italiana.

Il monitor gira dopo la finestra di retry. Un run schedulato con conclusione
success nella data Europe/Rome conta anche se GitHub lo ha avviato in ritardo.
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
WORKFLOWS = ("collect.yml", "finance.yml")


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


def missing_reports(workflow_runs: dict[str, list[dict]], now: datetime | None = None) -> list[str]:
    """Workflow senza almeno un run schedulato riuscito nella data italiana."""
    current = now or datetime.now(ROME)
    today = current.astimezone(ROME).date().isoformat()
    missing = []
    for workflow in WORKFLOWS:
        todays = _same_day_runs(workflow_runs.get(workflow, []), today)
        if not any(run.get("conclusion") == "success" for run in todays):
            missing.append(workflow)
    return missing


def _fetch_runs(repo: str, workflow: str, token: str) -> list[dict]:
    query = urllib.parse.urlencode({"branch": "main", "per_page": 100})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?{query}"
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    runs = payload.get("workflow_runs") if isinstance(payload, dict) else None
    if not isinstance(runs, list):
        raise ValueError(f"Risposta GitHub non valida per {workflow}")
    return runs


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        print("::error::GITHUB_TOKEN o GITHUB_REPOSITORY non configurato")
        return 2
    try:
        runs = {workflow: _fetch_runs(repo, workflow, token) for workflow in WORKFLOWS}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        print(f"::error::Impossibile verificare le esecuzioni dei radar: {str(exc)[:240]}")
        return 2

    now = datetime.now(ROME)
    today = now.date().isoformat()
    missing = missing_reports(runs, now)
    for workflow in WORKFLOWS:
        todays = _same_day_runs(runs.get(workflow, []), today)
        if not todays:
            print(f"NESSUN RUN SCHEDULATO OGGI: {workflow}")
            continue
        for run in todays:
            url = run.get("html_url", "")
            conclusion = run.get("conclusion") or run.get("status", "in_progress")
            local = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(ROME)
            print(f"{workflow}: {conclusion}, {local:%H:%M} Europe/Rome — {url}")

    if missing:
        print("::error::Nessun run schedulato riuscito oggi (Europe/Rome) per: " + ", ".join(missing))
        return 1
    print("Verifica OK: entrambi i radar hanno almeno un run schedulato riuscito nella data Europe/Rome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
