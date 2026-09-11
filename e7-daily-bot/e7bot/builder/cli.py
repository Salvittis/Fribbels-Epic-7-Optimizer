"""CLI helpers for the builder/analyzer — printing nice reports.

Kept separate from `run.py` so the table-formatting logic lives near the data.
"""
from __future__ import annotations

from .analyzer import Analyzer, InventoryReport, JunkCandidate, FitSuggestion, HeroPriority


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "..."


def print_priorities(prios: list[HeroPriority]) -> None:
    if not prios:
        print("No owned heroes match a meta build. Add nicknames to data/meta_builds.yaml.")
        return
    print(f"\n=== Build priorities ({len(prios)} owned heroes match meta) ===")
    print(f"{'Tier':<5} {'Hero':<26} {'R':<3} {'Slots':<6} {'Role'}")
    print("-" * 80)
    for p in prios:
        print(f"  {p.tier:<3} {_truncate(p.name, 26):<26} {p.rarity:<3} "
              f"{p.current_gear_completion}/6   {_truncate(p.role_label, 38)}")


def print_junk(junk: list[JunkCandidate], limit: int = 30) -> None:
    print(f"\n=== Junk candidates (showing {min(limit, len(junk))} of {len(junk)}) ===")
    if not junk:
        print("No items below threshold — your inventory is clean!")
        return
    print(f"{'#':<4} {'Score':<7} {'Gear':<10} {'Set':<14} {'Rank':<7} "
          f"{'+':<4} {'Main':<13} {'Substats'}")
    print("-" * 110)
    for i, c in enumerate(junk[:limit], 1):
        it = c.item
        subs = ", ".join(f"{s.stat}={int(s.value)}" for s in it.substats)
        print(f"  {i:<2} {c.best_score:>5.1f}  {it.gear:<10} {_truncate(it.set, 14):<14} "
              f"{it.rank:<7} +{it.enhance:<2} {_truncate(it.main_stat, 13):<13} "
              f"{_truncate(subs, 50)}")


def print_fits(fits: list[FitSuggestion]) -> None:
    if not fits:
        print("No fit suggestions to show.")
        return
    by_gear: dict[str, list[FitSuggestion]] = {}
    for f in fits:
        by_gear.setdefault(f.gear, []).append(f)
    hero = fits[0].hero
    print(f"\n=== Best-fit gear for {hero} ===")
    for gear, lst in by_gear.items():
        print(f"\n[{gear}]")
        for f in lst:
            it = f.item
            subs = ", ".join(f"{s.stat}={int(s.value)}" for s in it.substats)
            print(f"  score={f.score:>6.1f}  {it.set:<14} +{it.enhance:<2} "
                  f"main={it.main_stat:<13} subs=[{_truncate(subs, 70)}]")


def print_wishlist(wishlist, owned_names: set[str]) -> None:
    if not wishlist.entries:
        print("\nWishlist is empty. Edit priorities.yaml to add heroes.")
        return
    print(f"\n=== Wishlist ({len(wishlist.entries)} entries) ===")
    print(f"{'Prio':<5} {'Action':<10} {'Owned':<6} {'Hero':<26} {'Notes'}")
    print("-" * 90)
    for e in sorted(wishlist.entries, key=lambda x: (x.priority, x.name)):
        owned = "yes" if e.name.strip().lower() in owned_names else "NO"
        print(f"  {e.priority:<3} {e.action:<10} {owned:<6} "
              f"{_truncate(e.name, 26):<26} {_truncate(e.notes, 40)}")


def print_readiness(readinesses: list) -> None:
    if not readinesses:
        print("\nNothing to check (no wishlist heroes have meta builds).")
        return
    print(f"\n=== Build readiness ({len(readinesses)} heroes) ===")
    print(f"{'Status':<10} {'%':<6} {'Hero':<26} {'Combo':<35} {'Issues'}")
    print("-" * 110)
    for rd in readinesses:
        combo_label = rd.combo.label if rd.combo else "(no community data)"
        issues = "; ".join(rd.issues[:1]) if rd.issues else ""
        pct = f"{rd.readiness_pct:.0f}%"
        print(f"  {rd.status:<8} {pct:<5} {_truncate(rd.hero_name, 26):<26} "
              f"{_truncate(combo_label, 35):<35} {_truncate(issues, 40)}")


def print_readiness_detail(rd) -> None:
    print(f"\n=== Readiness detail: {rd.hero_name} ===")
    if rd.combo:
        print(f"Targeting community combo: {rd.combo.label} "
              f"({rd.combo.frequency} builds, {rd.combo.pct:.1f}% of submissions)")
    else:
        print("No community combo data — using meta substats only")
    print(f"Status: {rd.status}  ({rd.ready_slots}/{rd.total_slots} slots ready, "
          f"{rd.readiness_pct:.0f}%)")
    print(f"\n{'Slot':<10} {'OK':<4} {'Score':<7} {'Set required':<14} "
          f"{'Set picked':<14} {'+':<4} {'Substats'}")
    print("-" * 105)
    for gear in ("weapon", "helmet", "armor", "necklace", "ring", "boots"):
        s = rd.slots.get(gear)
        if s is None or s.item is None:
            print(f"  {gear:<8} --   ---     "
                  f"{(s.set_required if s else '-') or '-':<14} "
                  f"(none)         -    {(s.note if s else '')}")
            continue
        it = s.item
        subs = ", ".join(f"{x.stat}={int(x.value)}" for x in it.substats)
        print(f"  {gear:<8} {'OK' if s.ready else '!! ':<3} {s.score:>5.1f}  "
              f"{(s.set_required or '-'):<14} {it.set:<14} +{it.enhance:<2} "
              f"{_truncate(subs, 50)}")
    if rd.issues:
        print("\nIssues:")
        for issue in rd.issues:
            print(f"  - {issue}")


def print_upgrade_plan(plan) -> None:
    rd = plan.current_readiness
    print(f"\n=== Upgrade plan: {plan.hero_name} ===")
    print(f"Current readiness: {rd.status} ({rd.readiness_pct:.0f}%)")
    if not plan.actions:
        print("No actions needed — build looks complete.")
        return
    print(f"\nRecommended actions (sorted by estimated impact):")
    print(f"{'Kind':<8} {'Slot':<10} {'Gain':<7} Description")
    print("-" * 110)
    for a in plan.actions[:20]:
        gain = f"+{a.estimated_score_gain:.0f}" if a.estimated_score_gain > 0 else "-"
        print(f"  {a.kind:<6} {a.gear:<10} {gain:<6} {_truncate(a.description, 88)}")


def print_summary(report: InventoryReport) -> None:
    s = report.summary
    print("\n=== Inventory summary ===")
    print(f"  Heroes:                    {s['heroes_total']}")
    print(f"  Heroes with meta build:    {s['priorities_count']}")
    print(f"  Items total:               {s['items_total']}")
    print(f"    locked:                  {s['items_locked']}")
    print(f"    unlocked:                {s['items_unlocked']}")
    print(f"  Junk candidates:           {s['junk_count']}  "
          f"({s['junk_pct']:.1f}% of inventory, threshold={s['junk_threshold']:.0f})")
