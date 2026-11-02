"""Verifica che i radar abbiano completato la scansione giornaliera pianificata."""
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


def _scheduled_success_today(runs: list[dict], today: str) -> bool:
    for run in runs:
        if run.get("event") != "schedule" or run.get("conclusion") != "success":
            continue
        created = run.get("created_at")
        if not created:
            continue
        try:
            local = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(ROME)
        except (TypeError, ValueError):
            continue
        if local.date().isoformat() == today and 8 <= local.hour <= 12:
            return True
    return False


def missing_reports(workflow_runs: dict[str, list[dict]], now: datetime | None = None) -> list[str]:
    """Restituisce i workflow senza un completamento pianificato riuscito oggi."""
    today = (now or datetime.now(ROME)).astimezone(ROME).date().isoformat()
    return [workflow for workflow in WORKFLOWS if not _scheduled_success_today(workflow_runs.get(workflow, []), today)]


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
    missing = missing_reports(runs)
    if missing:
        print("::error::Nessun report giornaliero completato con successo per: " + ", ".join(missing))
        return 1
    print("Verifica OK: entrambi i radar hanno completato il run giornaliero in Europe/Rome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
