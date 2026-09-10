"""Legal / compliance pages served from backend/static.

These routes back the static Terms of Service, Privacy Policy, and Responsible
Gaming pages that the frontend footer links to (``/api/legal/*``). The HTML
files live in ``backend/static/`` and are served with a browser cache header
so repeat visits are cheap.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

_PAGES = {
    "terms": "terms.html",
    "privacy": "privacy.html",
    "responsible-gaming": "responsible-gaming.html",
}

# One hour: legal text changes rarely; no need to re-fetch every visitor hit.
_CACHE_HEADERS = {"Cache-Control": "public, max-age=3600"}


def build_legal_router() -> APIRouter:
    router = APIRouter(prefix="/legal", tags=["legal"])

    @router.get("/{page}", response_class=HTMLResponse)
    async def legal_pages(page: str) -> HTMLResponse:
        filename = _PAGES.get(page)
        if not filename:
            raise HTTPException(status_code=404, detail="Page not found")
        html = (_STATIC_DIR / filename).read_text(encoding="utf-8")
        return HTMLResponse(content=html, headers=_CACHE_HEADERS)

    return router