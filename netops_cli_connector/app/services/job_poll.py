from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import settings
from app.services.job_executor import execute_job
from app.services.netops_credentials import credentials_configured, resolve_netops_credentials
from app.storage import read_json, write_json_secure

logger = logging.getLogger("netops-cli.jobs")

JOBS_STATE_PATH = settings.runtime_dir / "jobs_poll.json"


def _record_state(update: dict[str, Any]) -> None:
    state = read_json(JOBS_STATE_PATH, {})
    state.update(update)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_json_secure(JOBS_STATE_PATH, state)


def poll_once() -> dict[str, Any]:
    if not credentials_configured():
        result = {"ok": False, "error": "NETOPS credentials not configured", "processed": 0}
        _record_state(result)
        return result

    url, token = resolve_netops_credentials()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        response = requests.get(f"{url}/api/connectors/jobs/pending", headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        jobs = data if isinstance(data, list) else data.get("jobs", [])
    except requests.RequestException as exc:
        result = {"ok": False, "error": str(exc), "processed": 0}
        _record_state(result)
        return result

    processed = 0
    last_job: dict[str, Any] | None = None
    for job in jobs:
        job_id = job.get("id")
        logger.info("executing job id=%s type=%s target=%s", job_id, job.get("job_type"), job.get("target_ip"))
        result = execute_job(job)
        try:
            requests.post(
                f"{url}/api/connectors/jobs/{job_id}/result",
                json=result,
                headers=headers,
                timeout=60,
            ).raise_for_status()
            processed += 1
            last_job = {
                "id": job_id,
                "type": job.get("job_type"),
                "target": job.get("target_ip"),
                "success": result.get("success"),
            }
            logger.info("job id=%s completed success=%s", job_id, result.get("success"))
        except requests.RequestException as exc:
            logger.error("failed to submit job %s result: %s", job_id, exc)

    summary = {"ok": True, "processed": processed, "last_job": last_job}
    _record_state(summary)
    return summary


def jobs_state() -> dict[str, Any]:
    return read_json(JOBS_STATE_PATH, {})


async def loop() -> None:
    while True:
        try:
            await asyncio.to_thread(poll_once)
        except Exception as exc:
            logger.exception("job poll failed: %s", exc)
            _record_state({"ok": False, "error": str(exc), "processed": 0})
        await asyncio.sleep(settings.job_poll_interval_seconds)
