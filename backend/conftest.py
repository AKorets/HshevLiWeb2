import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: live integration tests against a deployed backend (require DEMO_BACKEND_URL env var)",
    )
