import os
import pytest

# Backend integration tests need a live deployed backend (or a local one).
# They are skipped by default unless RUN_BACKEND_TESTS=1 is set.
# Self-contained unit tests (e.g. test_hub_http_bridge.py) always run so CI
# can exercise them without a live backend.
SELF_CONTAINED_FILES = {"test_hub_http_bridge.py", "test_self_distributor_unit.py"}


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