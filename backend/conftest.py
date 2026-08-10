import os
import pytest

# Skip backend integration tests by default. Set RUN_BACKEND_TESTS=1 to run them.
if os.environ.get("RUN_BACKEND_TESTS", "0") != "1":
    pytest.skip("Skipping backend integration tests (set RUN_BACKEND_TESTS=1 to enable)", allow_module_level=True)
