"""On-duty watchdog — automated 24/7 health monitor for WAH-LAH.

Runs as a background task inside the deployed API. Every
``ON_DUTY_INTERVAL_MIN`` (default 15) minutes it probes the core surfaces and
emails a human operator when something degrades:

  * database reachability (Mongo ping)
  * the public API on its own public URL (``api.wah-lah.com/api/health``)
  * the public frontend (``wah-lah.com``)
  * auth middleware health (``/api/amoe/status`` must 401, not 500)
  * stale pending Bitcoin deposits (created > 4h ago, still pending) — flags
    funding/webhook tickets that need eyes

Alerts go to ``ALERT_EMAILS`` (comma-separated) via the existing Resend email
service. A recovery email is sent once the checks pass again. Pure-python
stdlib + requests/motor — no new services, no external uptime provider.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

STALE_DEPOSIT_HOURS = 4
_STALE_LIMIT = 10


async def _probe(url: str, timeout: int = 12) -> tuple[bool, str]:
    """Blocking HTTP probe run off-loop. Returns (ok, note)."""
    try:
        resp = await asyncio.to_thread(
            requests.get, url, timeout=timeout, headers={"User-Agent": "wahlah-on-duty/1.0"}
        )
        return resp.status_code < 500, f"HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:140]


async def _mongo_ping(db) -> tuple[bool, str]:
    try:
        await db.client.admin.command("ping")
        return True, "mongo pong"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:140]


async def _stale_deposits(db) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=STALE_DEPOSIT_HOURS)).isoformat()
    cursor = db.btc_deposits.find(
        {
            "$or": [
                {"status": "pending", "created_at": {"$lte": cutoff}},
                # A "settling" deposit stranded mid-credit (timed out / crashed
                # process) is just as stuck and must keep alerting.
                {"status": "settling", "settling_at": {"$lte": cutoff}},
            ]
        }
    ).sort("created_at", 1).limit(_STALE_LIMIT)
    return await cursor.to_list(length=_STALE_LIMIT)


async def _auth_spot_check() -> tuple[bool, str]:
    """Auth middleware sanity: unauth /api/amoe/status must 401, never 500."""
    api_url = os.environ.get("PUBLIC_API_URL", "https://api.wah-lah.com").rstrip("/")
    try:
        resp = await asyncio.to_thread(
            requests.get, api_url + "/api/amoe/status", timeout=12,
            headers={"User-Agent": "wahlah-on-duty/1.0"},
        )
        return resp.status_code == 401, f"auth middleware HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:140]


def _deliver(emails: list[str], subject: str, text: str) -> None:
    from services.email_service import EmailService

    svc = EmailService()
    html_body = "<pre>" + html.escape(text) + "</pre>"
    for addr in emails:
        ok, note = svc.send_email(addr, subject, html_body, text)
        logger.info("Alert to %s -> %s", addr, note if ok else f"FAILED ({note})")


class OnDuty:
    """Long-lived watchdog task, restart-safe."""

    def __init__(self, db):
        self.db = db
        self.last_report: dict | None = None
        self.failed_since: datetime | None = None
        self._task: asyncio.Task | None = None
        self._interval = max(5, int(os.environ.get("ON_DUTY_INTERVAL_MIN", "15"))) * 60
        self._emails = [e.strip() for e in os.environ.get("ALERT_EMAILS", "").split(",") if e.strip()]
        if not self._emails:
            # No hardcoded fallback: a personal address baked into source is
            # both a PII leak and a missed-alert risk after handoffs. The
            # watchdog still runs and reports via /api/onduty/status.
            logger.warning("ALERT_EMAILS is unset — on-duty email alerts are DISABLED.")

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        logger.info("On-duty watchdog started (every %ss, alerting %s).", self._interval, self._emails)
        while True:
            try:
                await self.maybe_alert()
            except Exception:  # noqa: BLE001 — watchdog must never die
                logger.exception("On-duty watchdog iteration crashed")
                try:
                    _deliver(self._emails, "WAH-LAH on-duty crashed", "The watchdog itself hit an unexpected exception. See Render logs.")
                except Exception:  # noqa: BLE001
                    logger.exception("On-duty crash alert failed to send")
            await asyncio.sleep(self._interval)

    async def maybe_alert(self) -> dict:
        results = {
            "mongo": await _mongo_ping(self.db),
            "api": await _probe(os.environ.get("PUBLIC_API_URL", "https://api.wah-lah.com").rstrip("/") + "/api/health"),
            "frontend": await _probe("https://wah-lah.com/"),
            "auth": await _auth_spot_check(),
        }
        stale = await _stale_deposits(self.db)
        stale_pending = [
            {
                "id": d.get("id"),
                "amount_usd": d.get("amount_usd"),
                "created_at": d.get("created_at"),
                "platform": d.get("platform"),
            }
            for d in stale
        ]

        bad = [f"{name}: {'UP' if ok else 'DOWN'} ({note})" for name, (ok, note) in results.items() if not ok]
        if stale_pending:
            bad.append(
                f"stale-pending-deposits: {len(stale_pending)} older than {STALE_DEPOSIT_HOURS}h "
                f"(sample: {', '.join(str(d['id']) for d in stale_pending[:3])})"
            )
        ok_all = not bad

        if ok_all:
            if self.failed_since is not None:
                self._emit(True, results, stale_pending, "All checks green again.")
            logger.info("On duty: all green.")
        else:
            self.failed_since = self.failed_since or datetime.now(timezone.utc)
            self._emit(False, results, stale_pending, "; ".join(bad) or "degraded")

        self.last_report = {
            "ok": ok_all,
            "time": datetime.now(timezone.utc).isoformat(),
            "checks": {k: note for k, (_, note) in results.items()},
            "stale_deposits": stale_pending,
        }
        return self.last_report

    def _emit(self, ok: bool, results: dict, stale_pending: list, summary: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [
            f"WAH-LAH on-duty report — {now} UTC",
            "",
            summary,
            "",
        ]
        for name, (good, note) in results.items():
            lines.append(f"  {name:<10} {'UP' if good else 'DOWN'}  {note}")
        lines.append(f"  stale-deposits {'none' if not stale_pending else f'{len(stale_pending)} older than {STALE_DEPOSIT_HOURS}h'}")
        lines.append("")
        lines.append("If anything is DOWN: check Render logs for the service, then the database.")
        _deliver(self._emails, ("WAH-LAH DEGRADED" if not ok else "WAH-LAH RECOVERED"), "\n".join(lines))