import os

import pytest
from dotenv import load_dotenv

load_dotenv()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests that call the Gemini API (needs GEMINI_API_KEY).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: calls the real Gemini API")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    run_live = config.getoption("--live") and bool(os.environ.get("GEMINI_API_KEY"))
    if run_live:
        return
    reason = "live tests need --live and GEMINI_API_KEY"
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)
