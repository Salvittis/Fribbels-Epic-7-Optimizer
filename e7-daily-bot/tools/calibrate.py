"""Verify all PNG templates in `assets/` are matchable on the current screen.

Run this after capturing templates and with the game in a 'safe' state where
common UI is visible. It reports per-template confidence so you can tune
thresholds or recapture bad templates.

Usage:
    python tools/calibrate.py [--threshold 0.85] [--filter login/]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e7bot.core.driver import AdbDriver, default_adb_path  # noqa: E402
from e7bot.core.matcher import TemplateMatcher  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--assets-dir", default=str(ROOT / "assets"))
    parser.add_argument("--filter", default="", help="Substring filter for template names")
    args = parser.parse_args()

    driver = AdbDriver(adb_path=default_adb_path(), serial=args.serial)
    matcher = TemplateMatcher(driver, args.assets_dir, default_threshold=args.threshold)
    screen = driver.screenshot()

    assets = Path(args.assets_dir)
    templates = sorted(p.relative_to(assets).with_suffix("").as_posix()
                       for p in assets.rglob("*.png"))
    if args.filter:
        templates = [t for t in templates if args.filter in t]

    if not templates:
        print(f"No templates found in {assets}")
        return 1

    print(f"Calibrating {len(templates)} template(s) at threshold {args.threshold:.2f}\n")
    width = max(len(t) for t in templates)
    fails = 0
    for name in templates:
        try:
            m = matcher.find(name, screenshot=screen, threshold=0.0)
            if m is None:
                print(f"  {name.ljust(width)}  ?? template load failed")
                fails += 1
                continue
            mark = "OK " if m.confidence >= args.threshold else "LOW"
            if m.confidence < args.threshold:
                fails += 1
            print(f"  {mark}  {name.ljust(width)}  conf={m.confidence:.3f}  at ({m.x},{m.y})")
        except Exception as e:
            print(f"  ERR {name.ljust(width)}  {e}")
            fails += 1

    print(f"\n{len(templates) - fails}/{len(templates)} templates passed.")
    return 0 if fails == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
