"""Helper: capture a region of the current emulator screen as a PNG template.

Usage:
    python tools/capture.py <output_name> [--region X Y W H]

If --region is omitted, you'll be shown the full screenshot and asked to drag a
selection rectangle (uses opencv selectROI).

Outputs to assets/<output_name>.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from e7bot.core.driver import AdbDriver, default_adb_path  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a template PNG from the emulator")
    parser.add_argument("name", help="Output template name (e.g. 'login/mail_button')")
    parser.add_argument("--serial", help="ADB device serial, e.g. 127.0.0.1:5555")
    parser.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                        help="Region to capture (skip interactive selection)")
    parser.add_argument("--assets-dir", default=str(ROOT / "assets"))
    args = parser.parse_args()

    driver = AdbDriver(adb_path=default_adb_path(), serial=args.serial)
    screen = driver.screenshot()

    if args.region:
        x, y, w, h = args.region
    else:
        print("Drag a selection rectangle, then press SPACE or ENTER to confirm.")
        # selectROI returns (x, y, w, h)
        x, y, w, h = cv2.selectROI("Select template region", screen, fromCenter=False)
        cv2.destroyAllWindows()
        if w == 0 or h == 0:
            print("Empty selection — aborting.")
            return 1

    crop = screen[y:y + h, x:x + w]
    out_path = Path(args.assets_dir) / f"{args.name}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), crop)
    print(f"Saved {out_path}  ({w}x{h} at {x},{y})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
