"""Pytest fixtures and configuration for EmberRoute test suite."""

import os
from pathlib import Path
import sys
import pytest

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (run only with RUN_INTEGRATION=1)"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests unless RUN_INTEGRATION=1 is set."""
    if os.getenv("RUN_INTEGRATION") == "1":
        return

    skip_integration = pytest.mark.skip(
        reason="Skipped: integration test requires RUN_INTEGRATION=1"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)

