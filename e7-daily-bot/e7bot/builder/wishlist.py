"""User-curated wishlist: which heroes you want to build/improve, in your order.

Lives in `priorities.yaml` at the project root. Format::

    priorities:
      - name: Ruele of Light
        action: improve            # build | improve | maintain | skip
        priority: 1                # lower = higher priority
        notes: Speed teams cleanse
      - name: Martial Artist Ken
        action: build
        priority: 2

If a hero is in priorities.yaml, it overrides the meta-tier ordering.
Heroes NOT in the wishlist still appear in `priorities` command output,
sorted after wishlisted ones, by meta tier.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class WishlistEntry:
    name: str
    action: str = "build"   # build | improve | maintain | skip
    priority: int = 99
    notes: str = ""


@dataclass
class Wishlist:
    entries: list[WishlistEntry] = field(default_factory=list)

    def by_name(self, name: str) -> Optional[WishlistEntry]:
        target = name.strip().lower()
        return next((e for e in self.entries if e.name.strip().lower() == target), None)

    def names(self) -> list[str]:
        return [e.name for e in self.entries]

    def sorted_actionable(self) -> list[WishlistEntry]:
        """Entries you actually want to work on, sorted by priority."""
        return sorted(
            (e for e in self.entries if e.action != "skip"),
            key=lambda e: (e.priority, e.name),
        )


def default_wishlist_path() -> Path:
    return Path(__file__).resolve().parents[2] / "priorities.yaml"


def load_wishlist(path: str | Path | None = None) -> Wishlist:
    p = Path(path) if path else default_wishlist_path()
    if not p.exists():
        return Wishlist()
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    entries: list[WishlistEntry] = []
    for raw in data.get("priorities", []) or []:
        if not raw:
            continue
        entries.append(WishlistEntry(
            name=raw.get("name", ""),
            action=raw.get("action", "build"),
            priority=int(raw.get("priority", 99)),
            notes=raw.get("notes", "") or "",
        ))
    return Wishlist(entries=entries)


def save_wishlist(wl: Wishlist, path: str | Path | None = None) -> None:
    p = Path(path) if path else default_wishlist_path()
    payload = {
        "priorities": [
            {"name": e.name, "action": e.action, "priority": e.priority, "notes": e.notes}
            for e in sorted(wl.entries, key=lambda x: (x.priority, x.name))
        ]
    }
    with p.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
