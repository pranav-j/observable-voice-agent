import pytest

from voice_order.menu.models import Menu
from voice_order.tools.base import Session


@pytest.fixture
def session(menu: Menu) -> Session:
    return Session.start(menu, "test-session")
