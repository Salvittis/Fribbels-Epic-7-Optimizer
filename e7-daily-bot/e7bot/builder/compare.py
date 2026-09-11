"""Hero comparison — pick which one to build next.

Side-by-side readiness analysis with a verdict:
  - whose readiness is higher right now?
  - whose 'gap to ready' is cheaper to close (fewer items to farm)?
  - average score of best-fit items per slot

Used by both the CLI (`run.py compare`) and the webapp.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .build_aggregator import HeroBuilds, aggregate_by_recency
from .fribbels_api import FribbelsClient
from .fribbels_io import FribbelsSave
from .meta import MetaLibrary
from .readiness import HeroReadiness, ReadinessChecker
from .scorer import GearScorer


@dataclass
class HeroComparison:
    name: str
    readiness: HeroReadiness
    builds: Optional[HeroBuilds]
    avg_slot_score: float
    farm_gaps: int               # number of slots with no candidate (must farm)


@dataclass
class ComparisonResult:
    a: HeroComparison
    b: HeroComparison

    @property
    def winner(self) -> str:
        # Heuristic: higher readiness wins. Tie-break: fewer farm gaps. Tie-break: avg slot score.
        if self.a.readiness.readiness_pct != self.b.readiness.readiness_pct:
            return self.a.name if self.a.readiness.readiness_pct > self.b.readiness.readiness_pct else self.b.name
        if self.a.farm_gaps != self.b.farm_gaps:
            return self.a.name if self.a.farm_gaps < self.b.farm_gaps else self.b.name
        if self.a.avg_slot_score != self.b.avg_slot_score:
            return self.a.name if self.a.avg_slot_score > self.b.avg_slot_score else self.b.name
        return self.a.name  # arbitrary tie-break

    @property
    def reasoning(self) -> str:
        if self.a.readiness.readiness_pct != self.b.readiness.readiness_pct:
            higher = self.a if self.a.readiness.readiness_pct > self.b.readiness.readiness_pct else self.b
            return (f"{higher.name} is {higher.readiness.readiness_pct:.0f}% ready "
                    f"vs {(self.b if higher is self.a else self.a).readiness.readiness_pct:.0f}% — "
                    f"closer to playable.")
        if self.a.farm_gaps != self.b.farm_gaps:
            cheaper = self.a if self.a.farm_gaps < self.b.farm_gaps else self.b
            return (f"Both at same readiness, but {cheaper.name} has fewer items to farm "
                    f"({cheaper.farm_gaps} vs {self.b.farm_gaps if cheaper is self.a else self.a.farm_gaps}).")
        return "Both equally ready and equally cheap to finish — pick by personal preference."


class HeroComparator:
    def __init__(self, save: FribbelsSave, meta: MetaLibrary, client: Optional[FribbelsClient] = None) -> None:
        self.save = save
        self.meta = meta
        self.client = client or FribbelsClient()
        self.scorer = GearScorer()
        self.checker = ReadinessChecker(save=save, scorer=self.scorer)

    def compare(self, hero_a: str, hero_b: str) -> ComparisonResult:
        return ComparisonResult(
            a=self._summarize(hero_a),
            b=self._summarize(hero_b),
        )

    def _summarize(self, name: str) -> HeroComparison:
        meta = self.meta.get(name)
        if meta is None:
            raise ValueError(f"No meta build for '{name}' — add it to data/meta_builds.yaml")
        try:
            cached = self.client.fetch_builds(name)
            builds = aggregate_by_recency(cached.builds, top_k=3, recent_n=1000)
        except Exception:
            builds = None
        rd = self.checker.check(meta, builds=builds)
        slot_scores = [s.score for s in rd.slots.values() if s.item is not None]
        avg = sum(slot_scores) / len(slot_scores) if slot_scores else 0.0
        gaps = sum(1 for s in rd.slots.values() if s.item is None)
        return HeroComparison(
            name=meta.name, readiness=rd, builds=builds,
            avg_slot_score=avg, farm_gaps=gaps,
        )
