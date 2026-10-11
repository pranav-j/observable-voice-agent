"""`python -m evals.annotate <session_id>` (or `make annotate SESSION=<id>`).

Prints a recorded call and starts its annotation, evals/recorded/<session_id>.yaml,
from the agent's final order. The person who made the call then corrects it to what
they actually wanted, which is the point: the agent's version is only a starting place.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from evals.recorded import RECORDED_DIR
from voice_order.config import get_settings
from voice_order.order.models import Order
from voice_order.store.postgres import PostgresOrderStore

HEADER = """\
# What the caller WANTED, not what the agent took down. This started as a copy of the
# agent's final order (status: {status}). Fix anything it got wrong, then save.
# Phone numbers must stay obviously fake (90000 and five more digits).
"""


def draft(session_id: str, order: Order | None) -> str:
    expect: dict[str, Any] = {"status": "confirmed"}
    if order is not None:
        items = [
            {
                "item": line.item_id,
                **({"size": line.size_id} if line.size_id else {}),
                "quantity": line.quantity,
                "modifiers": list(line.modifier_ids),
            }
            for line in order.lines
        ]
        expect["order"] = {"items": items}
        if order.customer is not None:
            expect["order"]["customer"] = {
                "name": order.customer.name,
                "phone": order.customer.phone,
            }
    body = {"session_id": session_id, "description": "", "tags": ["human"], "expect": expect}
    header = HEADER.format(status=order.status if order else "no order saved")
    return header + yaml.safe_dump(body, sort_keys=False, allow_unicode=True)


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Start the annotation for a recorded call.")
    p.add_argument("session_id")
    p.add_argument("--force", action="store_true", help="overwrite an existing annotation")
    args = p.parse_args(argv)
    settings = get_settings()
    folder = Path(settings.recordings_dir) / args.session_id
    out = RECORDED_DIR / f"{args.session_id}.yaml"
    if not folder.is_dir():
        print(f"No recording at {folder}.", file=sys.stderr)
        return 2
    if out.exists() and not args.force:
        print(f"{out} already exists. Pass --force to start over.", file=sys.stderr)
        return 2
    for row in json.loads((folder / "transcript.json").read_text()):
        print(f"{'caller' if row['role'] == 'user' else 'agent':>6}: {row['text']}")
    async with await PostgresOrderStore.connect(settings.database_url) as store:
        order = await store.get(args.session_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(draft(args.session_id, order), encoding="utf-8")
    print(f"\nWrote {out}. Edit it to what the caller wanted.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
