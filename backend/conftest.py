import os
from urllib.parse import urlparse

import pytest

# Backend integration tests need a live deployed backend (or a local one).
# They are skipped by default unless RUN_BACKEND_TESTS=1 is set.
# Self-contained unit tests (e.g. test_hub_http_bridge.py) always run so CI
# can exercise them without a live backend.
SELF_CONTAINED_FILES = {
    "test_hub_http_bridge.py",
    "test_self_distributor_unit.py",
    "test_legal_router.py",
    "test_pool_pull.py",
    "test_deposit_reconciler.py",
    "test_pool_resync.py",
    "test_competition.py",
    "test_distributor_ops.py",
    "test_public_stats.py",
    "test_money_feed.py",
    "test_concierge.py",
    "test_distributor_admin_dates.py",
}


@pytest.fixture(autouse=True)
def reset_login_lockout_between_isolated_tests():
    """Clear account lockouts only in an explicitly disposable loopback test DB.

    Some older integration tests intentionally exercise invalid logins and reuse
    a shared synthetic admin identity. Isolating lockout rows between tests keeps
    those cases independent without weakening the application's lockout logic.
    """
    if os.environ.get("WAH_LAH_ISOLATED_TEST_DB") != "1":
        yield
        return

    mongo_url = os.environ.get("MONGO_URL", "")
    db_name = os.environ.get("DB_NAME", "")
    parsed = urlparse(mongo_url)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        pytest.fail(
            "WAH_LAH_ISOLATED_TEST_DB=1 requires a loopback MongoDB URL; refusing to touch a remote database"
        )
    if not db_name.startswith("wahlah_release_gate_"):
        pytest.fail(
            "WAH_LAH_ISOLATED_TEST_DB=1 requires DB_NAME to start with 'wahlah_release_gate_'"
        )

    from pymongo import MongoClient

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=1500)
    try:
        client[db_name].login_attempts.delete_many({})
    except Exception as exc:
        pytest.fail(f"Unable to isolate disposable login lockouts: {type(exc).__name__}")
    finally:
        client.close()
    yield


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_BACKEND_TESTS", "0") == "1":
        return
    skip = pytest.mark.skip(
        reason="requires live backend; set RUN_BACKEND_TESTS=1 to enable"
    )
    for item in items:
        filename = item.nodeid.split("::", 1)[0].rsplit("/", 1)[-1]
        if filename not in SELF_CONTAINED_FILES:
            item.add_marker(skip)