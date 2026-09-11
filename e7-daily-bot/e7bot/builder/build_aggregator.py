"""Aggregate the 3000 community builds for a hero into actionable patterns.

Input: a list of build rows from `getBuilds` API. Each row looks like::

    {
      "unitName": "Ruele of Light",
      "atk": 1380, "def": 1676, "hp": 21710, "spd": 228,
      "chc": 15, "chd": 150, "eff": 35, "efr": 161,
      "gs": 456,
      "sets": {"set_speed": "4", "set_immunity": "2"},
      "artifactCode": "ef501",
      "createDate": "2026-04-01"
    }

Output: a `BuildArchetype` per top set combo, with median target stats.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import median
from typing import Iterable

# Set name normalization: API returns lowercase keys like 'set_speed'.
# We map to Fribbels' CamelCase set keys used elsewhere in the codebase.
# Mapping discovered by inspecting actual API responses + Fribbels' set enum.
SET_API_TO_FRIBBELS = {
    # 4-piece sets
    "set_speed":     "SpeedSet",
    "set_revenant":  "RevenantSet",
    "set_res":       "ResistSet",
    "set_counter":   "CounterSet",
    "set_rage":      "RageSet",
    "set_vampire":   "LifestealSet",
    "set_riposte":   "RiposteSet",
    "set_penetrate": "PenetrationSet",
    "set_torrent":   "TorrentSet",
    "set_scar":      "InjurySet",
    "set_chase":     "PursuitSet",
    "set_opener":    "WarfareSet",
    "set_revenge":   "RevengeSet",
    "set_destroy":   "DestructionSet",
    "set_unity":     "DailyUnitySet",
    # 2-piece sets
    "set_max_hp":    "HealthSet",
    "set_immune":    "ImmunitySet",
    "set_def":       "DefenseSet",
    "set_shield":    "ProtectionSet",
    "set_acc":       "HitSet",
    "set_cri":       "CriticalSet",
    "set_cri_dmg":   "DestructionSet",
    "set_att":       "AttackSet",
    "set_coop":      "EffectivenessSet",
}

FRIBBELS_TO_API = {v: k for k, v in SET_API_TO_FRIBBELS.items()}


@dataclass
class SetCombo:
    """A specific (set_a, count_a, set_b, count_b) requirement."""
    pieces: tuple[tuple[str, int], ...]   # canonical Fribbels keys, e.g. (("SpeedSet", 4), ("ImmunitySet", 2))
    frequency: int                         # how many community builds use this combo
    pct: float                             # share of total builds

    @property
    def total_pieces(self) -> int:
        return sum(c for _, c in self.pieces)

    @property
    def label(self) -> str:
        return " + ".join(f"{name}({c})" for name, c in self.pieces)


@dataclass
class TargetStats:
    """Median stats community builds achieve, used as your aim."""
    atk: int = 0
    def_: int = 0
    hp: int = 0
    spd: int = 0
    chc: int = 0   # crit chance %
    chd: int = 0   # crit damage %
    eff: int = 0
    efr: int = 0
    gs: int = 0    # gear score


@dataclass
class HeroBuilds:
    hero_name: str
    sample_size: int
    top_combos: list[SetCombo] = field(default_factory=list)
    targets: TargetStats = field(default_factory=TargetStats)
    top_artifacts: list[tuple[str, int]] = field(default_factory=list)


def normalize_combo(api_sets: dict) -> tuple[tuple[str, int], ...]:
    """Convert an API row's `sets` dict into our canonical sorted tuple."""
    canon: list[tuple[str, int]] = []
    for k, v in api_sets.items():
        name = SET_API_TO_FRIBBELS.get(k, k)
        try:
            count = int(v)
        except (TypeError, ValueError):
            continue
        if count > 0:
            canon.append((name, count))
    canon.sort(key=lambda x: (-x[1], x[0]))   # bigger pieces first, then alpha
    return tuple(canon)


def aggregate_builds(rows: list[dict], top_k: int = 5) -> HeroBuilds:
    """Aggregate raw API rows into top set patterns + median target stats."""
    if not rows:
        return HeroBuilds(hero_name="", sample_size=0)

    name = rows[0].get("unitName", "")
    combo_counter: Counter[tuple[tuple[str, int], ...]] = Counter()
    artifacts: Counter[str] = Counter()

    for r in rows:
        sets = r.get("sets") or {}
        combo = normalize_combo(sets)
        if combo:
            combo_counter[combo] += 1
        if (a := r.get("artifactCode")):
            artifacts[a] += 1

    total = sum(combo_counter.values()) or 1
    top_combos = [
        SetCombo(pieces=combo, frequency=count, pct=100.0 * count / total)
        for combo, count in combo_counter.most_common(top_k)
    ]

    # Compute median stats across ALL rows (not just top combos)
    def med(key: str) -> int:
        vals = [int(r.get(key, 0) or 0) for r in rows if r.get(key) is not None]
        return int(median(vals)) if vals else 0

    targets = TargetStats(
        atk=med("atk"), def_=med("def"), hp=med("hp"), spd=med("spd"),
        chc=med("chc"), chd=med("chd"), eff=med("eff"), efr=med("efr"),
        gs=med("gs"),
    )

    return HeroBuilds(
        hero_name=name,
        sample_size=len(rows),
        top_combos=top_combos,
        targets=targets,
        top_artifacts=artifacts.most_common(5),
    )


def aggregate_by_recency(rows: list[dict], top_k: int = 5, recent_n: int = 1000) -> HeroBuilds:
    """Same as aggregate_builds but biases toward the most recent N submissions."""
    sorted_rows = sorted(rows, key=lambda r: r.get("createDate", ""), reverse=True)
    return aggregate_builds(sorted_rows[:recent_n], top_k=top_k)
