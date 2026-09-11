"""Drop checker — should I keep this item?

Given a recently-dropped (or any) item ID, simulate equipping it on each
wishlist hero and report:
  - which heroes get a score upgrade and by how much
  - which heroes have NO use for it
  - whether it should be kept (any positive impact) or discarded
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .build_aggregator import aggregate_by_recency
from .fribbels_api import FribbelsClient
from .fribbels_io import FribbelsSave, Item
from .meta import MetaBuild, MetaLibrary
from .readiness import ReadinessChecker, SlotPick
from .scorer import GearScorer
from .wishlist import Wishlist


@dataclass
class HeroImpact:
    hero_name: str
    current_slot_score: float    # score of the item currently in that slot (0 if empty)
    new_score: float              # score of the candidate item for this hero
    delta: float                  # new_score - current_slot_score
    current_item: Optional[Item] = None
    fits_set: bool = True         # does the candidate match this hero's preferred set?

    @property
    def positive(self) -> bool:
        return self.delta > 5

    @property
    def replaces_current(self) -> bool:
        return self.current_item is not None and self.delta > 5


@dataclass
class DropAnalysis:
    item: Item
    impacts: list[HeroImpact] = field(default_factory=list)

    @property
    def best_impact(self) -> Optional[HeroImpact]:
        positives = [i for i in self.impacts if i.positive]
        return max(positives, key=lambda i: i.delta) if positives else None

    @property
    def verdict(self) -> str:
        if self.best_impact is None:
            return "DISCARD"
        return f"KEEP for {self.best_impact.hero_name}"


class DropChecker:
    def __init__(
        self,
        save: FribbelsSave,
        meta: MetaLibrary,
        wishlist: Wishlist,
        client: Optional[FribbelsClient] = None,
    ) -> None:
        self.save = save
        self.meta = meta
        self.wishlist = wishlist
        self.client = client or FribbelsClient()
        self.scorer = GearScorer()

    def check_by_id(self, item_id: str) -> DropAnalysis:
        item = next((i for i in self.save.items if i.id == item_id), None)
        if item is None:
            raise ValueError(f"No item with id '{item_id}' in save")
        return self.check(item)

    def check(self, item: Item) -> DropAnalysis:
        analysis = DropAnalysis(item=item)
        targets = self._target_heroes()
        for name in targets:
            meta = self.meta.get(name)
            if meta is None:
                continue
            impact = self._impact_on_hero(item, meta)
            if impact:
                analysis.impacts.append(impact)
        analysis.impacts.sort(key=lambda i: i.delta, reverse=True)
        return analysis

    # ------------------------------------------------------------ internal

    def _target_heroes(self) -> list[str]:
        actionable = [e.name for e in self.wishlist.sorted_actionable()]
        if actionable:
            return actionable
        # Fallback: all owned heroes that have a meta build
        owned = {h.name for h in self.save.heroes}
        return [b.name for b in self.meta.builds.values()
                if not b.name.startswith("__") and b.name in owned]

    def _impact_on_hero(self, item: Item, meta: MetaBuild) -> Optional[HeroImpact]:
        # Score the candidate for this hero
        candidate_score = self.scorer.score(item, meta).total

        # Find the user's current best item for this slot (without the candidate)
        current_best_for_slot: Optional[Item] = None
        current_best_score: float = 0.0
        for it in self.save.items_by_gear(item.gear):
            if it.id == item.id:
                continue  # skip the candidate itself if it's already in inventory
            s = self.scorer.score(it, meta).total
            if s > current_best_score:
                current_best_score = s
                current_best_for_slot = it

        # Check if the set fits this hero's top community combo (if known)
        fits_set = self._fits_top_combo(item, meta)

        return HeroImpact(
            hero_name=meta.name,
            current_slot_score=current_best_score,
            new_score=candidate_score,
            delta=candidate_score - current_best_score,
            current_item=current_best_for_slot,
            fits_set=fits_set,
        )

    def _fits_top_combo(self, item: Item, meta: MetaBuild) -> bool:
        try:
            cached = self.client.fetch_builds(meta.name)
            agg = aggregate_by_recency(cached.builds, top_k=1, recent_n=500)
            if not agg.top_combos:
                return item.set in meta.sets_priority
            top = agg.top_combos[0]
            return any(set_name == item.set for set_name, _ in top.pieces)
        except Exception:
            # Fallback: compare against meta's set priorities
            return item.set in meta.sets_priority
