import pytest

from voice_order.menu.loader import load_menu
from voice_order.menu.models import Menu


@pytest.fixture(scope="session")
def menu() -> Menu:
    """The seed menu from data/menu.json, loaded once per test run."""
    return load_menu()
