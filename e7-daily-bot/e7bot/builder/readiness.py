"""Build readiness checker.

Given a hero with community-aggregated build patterns and the user's inventory,
determine: 'can I build this hero NOW with what I have?'

Algorithm per hero:
  1. Pick the top community set combo (e.g. SpeedSet(4) + ImmunitySet(2)).
  2. For each gear slot, find the best inventory item that:
     - Matches the required set (if the slot must contribute to the combo).
     - Has an acceptable main stat (from meta_builds.yaml).
     - Scores high on that hero's substat priorities.
  3. Verify the set requirements are satisfiable: do we have enough items of
     the required sets in the slot positions chosen?
  4. Output a readiness percentage + per-slot status.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .build_aggregator import HeroBuilds, SetCombo
from .fribbels_io import FIXED_MAIN_BY_GEAR, FribbelsSave, Item
from .meta import MetaBuild
from .scorer import GearScorer, ItemScore

log = logging.getLogger(__name__)


# Minimum score a slot's chosen item must reach to count as 'ready'.
SLOT_READY_THRESHOLD = 50.0
# If we can't satisfy the top combo, try the next combos in order.
COMBO_FALLBACK_LIMIT = 3


@dataclass
class SlotPick:
    gear: str
    item: Optional[Item]
    score: float
    set_required: Optional[str] = None
    note: str = ""

    @property
    def ready(self) -> bool:
        return self.item is not None and self.score >= SLOT_READY_THRESHOLD


@dataclass
class HeroReadiness:
    hero_name: str
    combo: Optional[SetCombo]            # which combo we attempted
    slots: dict[str, SlotPick] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    @property
    def ready_slots(self) -> int:
        return sum(1 for s in self.slots.values() if s.ready)

    @property
    def total_slots(self) -> int:
        return len(self.slots)

    @property
    def readiness_pct(self) -> float:
        if not self.slots:
            return 0.0
        return 100.0 * self.ready_slots / self.total_slots

    @property
    def status(self) -> str:
        if not self.slots:
            return "no_data"
        if self.readiness_pct >= 100:
            return "READY"
        if self.readiness_pct >= 66:
            return "ALMOST"
        if self.readiness_pct >= 33:
            return "PARTIAL"
        return "NOT_READY"


class ReadinessChecker:
    GEAR_SLOTS = ("weapon", "helmet", "armor", "necklace", "ring", "boots")

    def __init__(self, save: FribbelsSave, scorer: Optional[GearScorer] = None) -> None:
        self.save = save
        self.scorer = scorer or GearScorer()

    def check(
        self,
        meta: MetaBuild,
        builds: Optional[HeroBuilds] = None,
    ) -> HeroReadiness:
        """Find best slot picks honoring the top community set combo, if any."""
        combo = self._pick_combo(builds)
        rd = HeroReadiness(hero_name=meta.name, combo=combo)
        slot_set_requirements = self._slot_set_requirements(combo)

        # Step 1: pick best item per slot subject to set constraint
        all_items_by_slot: dict[str, list[Item]] = {
            g: self.save.items_by_gear(g) for g in self.GEAR_SLOTS
        }

        for gear in self.GEAR_SLOTS:
            req_set = slot_set_requirements.get(gear)  # may be None (any set)
            candidates = all_items_by_slot.get(gear, [])
            if req_set:
                candidates = [it for it in candidates if it.set == req_set]
            scored: list[ItemScore] = sorted(
                (self.scorer.score(it, meta) for it in candidates),
                key=lambda s: s.total, reverse=True,
            )
            if not scored:
                rd.slots[gear] = SlotPick(
                    gear=gear, item=None, score=0.0,
                    set_required=req_set,
                    note=f"no items of set {req_set}" if req_set else "no items at all",
                )
                continue
            best = scored[0]
            rd.slots[gear] = SlotPick(
                gear=gear, item=best.item, score=best.total,
                set_required=req_set,
            )

        # Step 2: surface global issues
        if combo:
            for set_name, count in combo.pieces:
                actual = sum(1 for s in rd.slots.values()
                             if s.item is not None and s.item.set == set_name)
                if actual < count:
                    rd.issues.append(
                        f"need {count}x {set_name}, have {actual} matching items in chosen slots"
                    )
        return rd

    # -- internal -----------------------------------------------------------

    def _pick_combo(self, builds: Optional[HeroBuilds]) -> Optional[SetCombo]:
        if builds is None or not builds.top_combos:
            return None
        return builds.top_combos[0]

    def _slot_set_requirements(self, combo: Optional[SetCombo]) -> dict[str, str]:
        """Naive assignment: 4-piece sets occupy weapon/helmet/armor/necklace,
        2-piece sets occupy ring/boots. Real game allows freedom but this
        encodes the most common community pattern.
        """
        if combo is None:
            return {}
        slot_order = ["weapon", "helmet", "armor", "necklace", "ring", "boots"]
        assignment: dict[str, str] = {}
        idx = 0
        for set_name, count in combo.pieces:
            for _ in range(count):
                if idx >= len(slot_order):
                    break
                assignment[slot_order[idx]] = set_name
                idx += 1
            if idx >= len(slot_order):
                break
        return assignment
