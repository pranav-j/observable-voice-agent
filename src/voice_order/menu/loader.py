"""Load and validate the menu file."""

from pathlib import Path

from voice_order.menu.models import Menu

# src/voice_order/menu/loader.py -> repo root
DEFAULT_MENU_PATH = Path(__file__).resolve().parents[3] / "data" / "menu.json"


def load_menu(path: Path = DEFAULT_MENU_PATH) -> Menu:
    """Parse and validate a menu file. Raises pydantic.ValidationError on bad data."""
    return Menu.model_validate_json(path.read_text(encoding="utf-8"))
