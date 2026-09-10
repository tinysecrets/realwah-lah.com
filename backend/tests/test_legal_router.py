"""Self-contained tests for the /api/legal/* pages router.

The legal router only reads static HTML files from backend/static/ and needs
no database or environment, so this file belongs in SELF_CONTAINED_FILES in
conftest.py and runs in CI without a live backend.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.legal import build_legal_router

app = FastAPI()
# server.py includes the router via api_router (prefix="/api")
app.include_router(build_legal_router(), prefix="/api")
client = TestClient(app)


@pytest.mark.parametrize(
    "page,title",
    [
        ("terms", "Terms of Service"),
        ("privacy", "Privacy Policy"),
        ("responsible-gaming", "Responsible Gaming"),
    ],
)
def test_legal_pages_serve_html(page, title):
    resp = client.get(f"/api/legal/{page}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert title in resp.text
    assert "Cache-Control" in resp.headers


def test_unknown_legal_page_404():
    resp = client.get("/api/legal/not-a-page")
    assert resp.status_code == 404