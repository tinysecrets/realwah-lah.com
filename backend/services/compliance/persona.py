"""Persona KYC client (thin wrapper around api.withpersona.com).

Scaffolded per the Persona integration playbook. Gracefully degrades when
PERSONA_API_KEY is unset — `create_inquiry()` returns a fallback payload and
the route-layer falls back to manual upload.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import uuid
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


PERSONA_ENABLED = bool(
    _env("PERSONA_API_KEY")
    and _env("PERSONA_TEMPLATE_ID_BASIC")
    and _env("PERSONA_TEMPLATE_ID_ENHANCED")
    and _env("PERSONA_WEBHOOK_SECRET")
)


def _base_url() -> str:
    env = (_env("PERSONA_ENVIRONMENT") or "production").lower()
    return "https://api.sandbox.withpersona.com" if env == "sandbox" else "https://api.withpersona.com"


class PersonaClient:
    """Thin async wrapper; every call is idempotent + guarded by PERSONA_ENABLED."""

    async def create_inquiry(
        self,
        *,
        user_id: str,
        tier: str,  # "basic" | "enhanced"
        redirect_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Returns {inquiry_id, hosted_inquiry_url, reference_id, fallback}."""
        reference_id = str(uuid.uuid4())
        if not PERSONA_ENABLED:
            return {
                "inquiry_id": None,
                "hosted_inquiry_url": None,
                "reference_id": reference_id,
                "fallback": True,
                "message": "Persona not configured. Use manual upload path.",
            }
        template = (
            _env("PERSONA_TEMPLATE_ID_BASIC")
            if tier == "basic"
            else _env("PERSONA_TEMPLATE_ID_ENHANCED")
        )
        payload = {
            "data": {
                "type": "inquiry",
                "attributes": {
                    "inquiry-template-id": template,
                    "reference-id": reference_id,
                    "redirect-uri": redirect_url or "",
                },
            }
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    f"{_base_url()}/api/v1/inquiries",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {_env('PERSONA_API_KEY')}",
                        "Content-Type": "application/json",
                        "Persona-Version": "2023-01-05",
                    },
                )
                r.raise_for_status()
                data = r.json().get("data", {})
                return {
                    "inquiry_id": data.get("id"),
                    "hosted_inquiry_url": (data.get("attributes") or {}).get("hosted-inquiry-url"),
                    "reference_id": reference_id,
                    "fallback": False,
                }
        except Exception as e:
            logger.error(f"Persona create_inquiry failed: {e}")
            return {
                "inquiry_id": None,
                "hosted_inquiry_url": None,
                "reference_id": reference_id,
                "fallback": True,
                "message": f"Persona error: {e}",
            }

    async def fetch_inquiry(self, inquiry_id: str) -> Optional[Dict[str, Any]]:
        if not PERSONA_ENABLED or not inquiry_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{_base_url()}/api/v1/inquiries/{inquiry_id}",
                    headers={
                        "Authorization": f"Bearer {_env('PERSONA_API_KEY')}",
                        "Persona-Version": "2023-01-05",
                    },
                )
                r.raise_for_status()
                return r.json().get("data", {})
        except Exception as e:
            logger.error(f"Persona fetch_inquiry failed: {e}")
            return None

    def verify_webhook_signature(self, raw_body: bytes, signature_header: str) -> bool:
        """Verify X-Persona-Signature. Persona format:
            t=<unix_ts>,v1=<hex_hmac_sha256>
        We accept either that canonical format OR a plain 'sha256=<b64>' fallback.
        """
        secret = _env("PERSONA_WEBHOOK_SECRET").encode()
        if not secret or not signature_header:
            return False
        # Canonical Persona format
        parts = {kv.split("=", 1)[0]: kv.split("=", 1)[1] for kv in signature_header.split(",") if "=" in kv}
        ts = parts.get("t")
        v1 = parts.get("v1")
        if ts and v1:
            signed_payload = f"{ts}.".encode() + raw_body
            expected = hmac.new(secret, signed_payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, v1)
        # Fallback
        if signature_header.startswith("sha256="):
            provided = signature_header.split("sha256=", 1)[1]
            expected = base64.b64encode(hmac.new(secret, raw_body, hashlib.sha256).digest()).decode()
            return hmac.compare_digest(expected, provided)
        return False


persona_client = PersonaClient()
