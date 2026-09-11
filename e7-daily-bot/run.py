"""Entry point.

Daily automation:
    python run.py daily                  # run all routines from config.daily
    python run.py routine login          # run a single routine
    python run.py list                   # list registered routines

Build / inventory analysis:
    python run.py analyze                # full report
    python run.py priorities             # heroes ranked (wishlist + meta tiers)
    python run.py wishlist               # show your priorities.yaml entries
    python run.py junk [--limit 30]      # items below threshold (discard)
    python run.py fit "Ruele of Light"   # best-fit gear for a hero
    python run.py whois <item_id>        # which heroes want this item

Build readiness (uses Fribbels community builds):
    python run.py fetch-builds           # cache builds for wishlist heroes
    python run.py fetch-builds "Ruele of Light"   # one hero
    python run.py readiness              # can I build my wishlist heroes?
    python run.py readiness "Ruele of Light"      # detailed view
    python run.py upgrade "Ruele of Light"        # what to enhance/farm
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import e7bot.routines  # noqa: F401
from e7bot.orchestrator import ROUTINE_REGISTRY, Orchestrator
from e7bot.builder import (
    Analyzer, DropChecker, FribbelsClient, GearScorer, HeroComparator,
    ReadinessChecker, UpgradeRecommender,
    aggregate_by_recency,
    default_save_path, load_meta, load_save, load_wishlist,
)
from e7bot.builder.cli import (
    print_fits, print_junk, print_priorities, print_readiness,
    print_readiness_detail, print_summary, print_upgrade_plan,
    print_wishlist,
)


# -----------------------------------------------------------------------------
# Helpers

def _make_analyzer(args):
    save_path = Path(args.save) if args.save else default_save_path()
    if not save_path.exists():
        print(f"Fribbels save not found at: {save_path}")
        print("Tip: pass --save <path> with your exported gear.txt/json file.")
        sys.exit(2)
    save = load_save(save_path)
    meta = load_meta(args.meta) if args.meta else load_meta()
    print(f"Loaded {len(save.items)} items, {len(save.heroes)} heroes "
          f"from {save.source_path}")
    return save, meta, Analyzer(
        save=save, meta=meta, scorer=GearScorer(),
        junk_threshold=args.junk_threshold,
    )


def _resolve_target_heroes(args, wishlist, save, meta) -> list[str]:
    """If user passed a hero name, use it; else use actionable wishlist; else owned-meta."""
    explicit = getattr(args, "hero", None)
    if explicit:
        return [explicit]
    wl_names = [e.name for e in wishlist.sorted_actionable()]
    if wl_names:
        return wl_names
    # Fallback: owned heroes that have a meta build
    owned = {h.name for h in save.heroes}
    return [b.name for b in meta.builds.values()
            if not b.name.startswith("__") and b.name in owned]


def _readiness_for(name, save, meta, client, recompute_only_top: int = 1000):
    build = meta.get(name)
    if build is None:
        return None, "no meta build for this hero — add it to data/meta_builds.yaml"
    try:
        cached = client.fetch_builds(name)
    except Exception as e:
        return None, f"could not fetch community builds: {e}"
    aggregated = aggregate_by_recency(cached.builds, top_k=5, recent_n=recompute_only_top)
    rd = ReadinessChecker(save).check(build, builds=aggregated)
    return (rd, aggregated), None


# -----------------------------------------------------------------------------
# Main

def main() -> int:
    parser = argparse.ArgumentParser(description="E7 daily bot + inventory + build planner")
    parser.add_argument("--config", default=str(ROOT / "config.yaml"))
    parser.add_argument("--verbose", "-v", action="count", default=0)

    sub = parser.add_subparsers(dest="cmd", required=True)

    # automation
    sub.add_parser("daily")
    p_routine = sub.add_parser("routine")
    p_routine.add_argument("name", choices=list(ROUTINE_REGISTRY) or ["(none)"])
    sub.add_parser("list")

    def add_save_flags(p):
        p.add_argument("--save", help="Path to Fribbels save file")
        p.add_argument("--meta", help="Path to a custom meta_builds.yaml")
        p.add_argument("--wishlist", dest="wishlist_path",
                       help="Path to a custom priorities.yaml")
        p.add_argument("--junk-threshold", type=float, default=30.0)

    p = sub.add_parser("analyze"); add_save_flags(p); p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("priorities"); add_save_flags(p)
    p = sub.add_parser("wishlist"); add_save_flags(p)
    p = sub.add_parser("junk"); add_save_flags(p)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--include-locked", action="store_true")
    p = sub.add_parser("fit"); add_save_flags(p)
    p.add_argument("hero")
    p.add_argument("--top", type=int, default=3)
    p = sub.add_parser("whois"); add_save_flags(p); p.add_argument("item_id")

    # build readiness / upgrade (uses Fribbels community API)
    p = sub.add_parser("fetch-builds")
    add_save_flags(p)
    p.add_argument("hero", nargs="?", help="Hero name; default: fetch all wishlist heroes")
    p.add_argument("--force", action="store_true", help="Bypass cache")

    p = sub.add_parser("readiness")
    add_save_flags(p)
    p.add_argument("hero", nargs="?", help="One hero (detailed view); else summary across wishlist")

    p = sub.add_parser("upgrade")
    add_save_flags(p)
    p.add_argument("hero")

    p = sub.add_parser("compare", help="Compare two heroes side by side")
    add_save_flags(p)
    p.add_argument("hero_a")
    p.add_argument("hero_b")

    p = sub.add_parser("drop", help="Should I keep this dropped item?")
    add_save_flags(p)
    p.add_argument("item_id")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose >= 2 else (logging.INFO if args.verbose else logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # ---- automation paths
    if args.cmd == "list":
        if not ROUTINE_REGISTRY:
            print("No routines registered yet.")
            return 0
        for name, cls in sorted(ROUTINE_REGISTRY.items()):
            print(f"  {name}  ({cls.__module__})")
        return 0

    if args.cmd in ("daily", "routine"):
        orch = Orchestrator(args.config)
        results = orch.run_daily() if args.cmd == "daily" else [orch.run_one(args.name)]
        for r in results:
            status = "OK " if r.succeeded else "FAIL"
            print(f"[{status}] {r.name}: {r.duration_seconds:.1f}s, {len(r.steps)} steps"
                  + (f" — {r.error}" if r.error else ""))
        return 0 if all(r.succeeded for r in results) else 1

    # ---- builder paths
    save, meta, analyzer = _make_analyzer(args)
    wishlist = load_wishlist(getattr(args, "wishlist_path", None))
    owned_names = {h.name.strip().lower() for h in save.heroes}

    if args.cmd == "wishlist":
        print_wishlist(wishlist, owned_names)
        return 0

    if args.cmd == "analyze":
        report = analyzer.full_report()
        print_summary(report)
        print_priorities(report.priorities)
        if wishlist.entries:
            print_wishlist(wishlist, owned_names)
        print_junk(report.junk, limit=args.limit)
        return 0

    if args.cmd == "priorities":
        # Show wishlist first, then meta-based priorities
        if wishlist.entries:
            print_wishlist(wishlist, owned_names)
        print_priorities(analyzer.build_priorities())
        return 0

    if args.cmd == "junk":
        junk = analyzer.junk_candidates(only_unlocked=not args.include_locked)
        print_junk(junk, limit=args.limit)
        return 0

    if args.cmd == "fit":
        try:
            fits = analyzer.fit_suggestions(args.hero, top_n=args.top)
        except ValueError as e:
            print(f"Error: {e}")
            return 2
        print_fits(fits)
        return 0

    if args.cmd == "whois":
        item = next((i for i in save.items if i.id == args.item_id), None)
        if item is None:
            print(f"No item with id '{args.item_id}'")
            return 2
        scores = analyzer.score_item_for_all_heroes(item)
        print(f"\n=== Owners of item {args.item_id} "
              f"({item.gear} {item.set} +{item.enhance}) ===")
        for s in scores[:10]:
            print(f"  {s.total:>6.1f}  {s.build.name}")
        return 0

    # ---- community-build commands
    client = FribbelsClient()

    if args.cmd == "fetch-builds":
        targets = [args.hero] if args.hero else _resolve_target_heroes(args, wishlist, save, meta)
        if not targets:
            print("Nothing to fetch — wishlist is empty and no owned hero has a meta build.")
            return 1
        print(f"Fetching builds for {len(targets)} hero(es)...")
        results = client.fetch_builds_bulk(targets, force=args.force)
        for name, cb in results.items():
            agg = aggregate_by_recency(cb.builds, top_k=3, recent_n=1000)
            top = agg.top_combos[0].label if agg.top_combos else "(no combos)"
            print(f"  {name:<28} {cb.builds and len(cb.builds) or 0} builds, top: {top}")
        return 0

    if args.cmd == "readiness":
        if args.hero:
            result, err = _readiness_for(args.hero, save, meta, client)
            if err:
                print(f"Error: {err}")
                return 2
            rd, _ = result
            print_readiness_detail(rd)
            return 0
        targets = _resolve_target_heroes(args, wishlist, save, meta)
        readinesses = []
        for name in targets:
            result, err = _readiness_for(name, save, meta, client)
            if err:
                print(f"  skip {name}: {err}")
                continue
            readinesses.append(result[0])
        print_readiness(readinesses)
        return 0

    if args.cmd == "upgrade":
        result, err = _readiness_for(args.hero, save, meta, client)
        if err:
            print(f"Error: {err}")
            return 2
        rd, aggregated = result
        plan = UpgradeRecommender(save).plan(meta.get(args.hero), readiness=rd, builds=aggregated)
        print_upgrade_plan(plan)
        return 0

    if args.cmd == "compare":
        try:
            cmp = HeroComparator(save, meta, client).compare(args.hero_a, args.hero_b)
        except ValueError as e:
            print(f"Error: {e}")
            return 2
        a, b = cmp.a, cmp.b
        print(f"\n=== Comparison: {a.name} vs {b.name} ===")
        print(f"\n{'Metric':<22} {a.name[:22]:<24} {b.name[:22]:<24}")
        print("-" * 72)
        print(f"{'Readiness':<22} {a.readiness.status} {a.readiness.readiness_pct:>5.0f}%   "
              f"     {b.readiness.status} {b.readiness.readiness_pct:>5.0f}%")
        print(f"{'Slots ready':<22} {a.readiness.ready_slots}/6                      "
              f"{b.readiness.ready_slots}/6")
        print(f"{'Slots missing item':<22} {a.farm_gaps:<24} {b.farm_gaps}")
        print(f"{'Avg slot score':<22} {a.avg_slot_score:>6.1f}                  "
              f"{b.avg_slot_score:>6.1f}")
        if a.builds and a.builds.top_combos:
            print(f"{'Top combo':<22} {a.builds.top_combos[0].label[:22]:<24} "
                  f"{(b.builds.top_combos[0].label[:22] if b.builds and b.builds.top_combos else '-')}")
        print(f"\n>>> Verdict: build '{cmp.winner}' first")
        print(f"    {cmp.reasoning}")
        return 0

    if args.cmd == "drop":
        wl = load_wishlist(getattr(args, "wishlist_path", None))
        try:
            analysis = DropChecker(save, meta, wl, client).check_by_id(args.item_id)
        except ValueError as e:
            print(f"Error: {e}")
            return 2
        it = analysis.item
        subs = ", ".join(f"{s.stat}={int(s.value)}" for s in it.substats)
        print(f"\n=== Drop analysis: {it.set} {it.gear} +{it.enhance} ({it.rank}) ===")
        print(f"Main: {it.main_stat}={int(it.main_value)}  Substats: {subs}")
        print(f"\nImpact on wishlist heroes:")
        if not analysis.impacts:
            print("  (no wishlist heroes have meta builds — add some to data/meta_builds.yaml)")
        for imp in analysis.impacts:
            arrow = "->"
            mark = "+" if imp.delta > 0 else ""
            label = "UPGRADE" if imp.positive else "(no improvement)"
            print(f"  {imp.hero_name:<28} {imp.current_slot_score:>6.1f} {arrow} {imp.new_score:>6.1f}  "
                  f"({mark}{imp.delta:>+5.1f}) {label}")
        print(f"\n>>> Verdict: {analysis.verdict}")
        if analysis.best_impact:
            best = analysis.best_impact
            print(f"    Replaces {best.current_item.set if best.current_item else 'empty slot'} "
                  f"on {best.hero_name}, +{best.delta:.0f} score gain.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
