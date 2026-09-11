"""Inventory analyzer — turns scored items into actionable views.

Outputs three reports:
  - priorities: heroes you OWN that have a meta build, ranked by tier
  - junk: items whose best score across your roster is below threshold
  - fits: per-hero, the top-N items in inventory for each gear position

Also exposes `score_item_for_hero` for ad-hoc 'does this drop fit anyone' checks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .fribbels_io import FribbelsSave, Item
from .meta import MetaBuild, MetaLibrary
from .scorer import GearScorer, ItemScore

log = logging.getLogger(__name__)


# Score thresholds — tunable in CLI
DEFAULT_JUNK_THRESHOLD = 30.0     # items below this score (max across roster) → junk
DEFAULT_GOOD_THRESHOLD = 70.0     # items at or above are 'great'


@dataclass
class HeroPriority:
    name: str
    owned: bool
    rarity: int
    tier: int
    role_label: str
    current_gear_completion: int       # 0..6, how many slots have items equipped
    notes: str = ""


@dataclass
class JunkCandidate:
    item: Item
    best_score: float
    best_for: Optional[str]            # hero name where it scored best (or '__generic_dps' etc)


@dataclass
class FitSuggestion:
    hero: str
    gear: str
    item: Item
    score: float


@dataclass
class InventoryReport:
    priorities: list[HeroPriority] = field(default_factory=list)
    junk: list[JunkCandidate] = field(default_factory=list)
    fits: list[FitSuggestion] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


class Analyzer:
    def __init__(
        self,
        save: FribbelsSave,
        meta: MetaLibrary,
        scorer: Optional[GearScorer] = None,
        junk_threshold: float = DEFAULT_JUNK_THRESHOLD,
        good_threshold: float = DEFAULT_GOOD_THRESHOLD,
    ) -> None:
        self.save = save
        self.meta = meta
        self.scorer = scorer or GearScorer()
        self.junk_threshold = junk_threshold
        self.good_threshold = good_threshold

    # ------------------------------------------------------------------ priorities

    def build_priorities(self) -> list[HeroPriority]:
        """Heroes you OWN that have a meta entry, sorted by tier asc."""
        out: list[HeroPriority] = []
        for hero in self.save.heroes:
            build = self.meta.get(hero.name)
            if build is None:
                continue
            equipped = sum(1 for v in hero.equipment.values() if v)
            out.append(HeroPriority(
                name=hero.name,
                owned=True,
                rarity=hero.rarity,
                tier=build.tier,
                role_label=build.role_label,
                current_gear_completion=equipped,
                notes="",
            ))
        out.sort(key=lambda h: (h.tier, -h.current_gear_completion, h.name))
        return out

    # ------------------------------------------------------------------ junk pile

    def junk_candidates(self, only_unlocked: bool = True) -> list[JunkCandidate]:
        """Items whose best score across all relevant builds is below threshold.

        'Relevant builds' = (meta builds for heroes the user owns) + the
        generic templates (__generic_dps, __generic_tank). This avoids
        nuking gear that's bad for current roster but might fit a future hire.
        """
        relevant: list[MetaBuild] = []
        owned_names = {h.name.strip().lower() for h in self.save.heroes}
        for key, b in self.meta.builds.items():
            if b.name.startswith("__"):
                relevant.append(b)
                continue
            if b.name.strip().lower() in owned_names:
                relevant.append(b)

        candidates: list[JunkCandidate] = []
        items = self.save.unlocked_items() if only_unlocked else self.save.items
        for item in items:
            best: Optional[ItemScore] = None
            for build in relevant:
                s = self.scorer.score(item, build)
                if best is None or s.total > best.total:
                    best = s
            if best is None:
                continue
            if best.total < self.junk_threshold:
                candidates.append(JunkCandidate(
                    item=item,
                    best_score=best.total,
                    best_for=best.build.name,
                ))
        # Worst-scoring first so user can mass-discard top of list
        candidates.sort(key=lambda c: c.best_score)
        return candidates

    # ------------------------------------------------------------------ fits

    def fit_suggestions(
        self,
        hero_name: str,
        top_n: int = 3,
    ) -> list[FitSuggestion]:
        """Top N items per gear position for a specific hero."""
        build = self.meta.get(hero_name)
        if build is None:
            raise ValueError(f"No meta build for hero '{hero_name}'")

        out: list[FitSuggestion] = []
        for gear in ("weapon", "helmet", "armor", "necklace", "ring", "boots"):
            scored: list[ItemScore] = [
                self.scorer.score(it, build)
                for it in self.save.items_by_gear(gear)
            ]
            scored.sort(key=lambda s: s.total, reverse=True)
            for s in scored[:top_n]:
                out.append(FitSuggestion(
                    hero=build.name, gear=gear, item=s.item, score=s.total,
                ))
        return out

    def score_item_for_all_heroes(self, item: Item) -> list[ItemScore]:
        """Useful 'I just got this item — does anyone want it?' check."""
        out: list[ItemScore] = []
        owned_names = {h.name.strip().lower() for h in self.save.heroes}
        for key, build in self.meta.builds.items():
            if build.name.startswith("__"):
                continue
            if build.name.strip().lower() not in owned_names:
                continue
            out.append(self.scorer.score(item, build))
        out.sort(key=lambda s: s.total, reverse=True)
        return out

    # ------------------------------------------------------------------ full report

    def full_report(self) -> InventoryReport:
        prios = self.build_priorities()
        junk = self.junk_candidates()
        items_total = len(self.save.items)
        junk_pct = (100.0 * len(junk) / items_total) if items_total else 0.0
        return InventoryReport(
            priorities=prios,
            junk=junk,
            fits=[],
            summary={
                "items_total": items_total,
                "items_locked": sum(1 for i in self.save.items if i.locked),
                "items_unlocked": sum(1 for i in self.save.items if not i.locked),
                "junk_count": len(junk),
                "junk_pct": junk_pct,
                "heroes_total": len(self.save.heroes),
                "priorities_count": len(prios),
                "junk_threshold": self.junk_threshold,
            },
        )
