#!/usr/bin/env python3
"""Re-vendor the product marks used by figure 1.

D2 always draws an icon at 64x64 and offers no way to resize it, so the
apparent size of a mark, and its inset from the card corner, are set here by
centring the upstream logo on a larger transparent square. Run from this
directory; the output is what `_style.d2` points `icon:` at.
"""

import pathlib
import re

# Fraction of the padded square the mark itself spans. Smaller means a smaller
# logo sitting further in from the corner.
FRAC = 0.46

OODLE_UI = pathlib.Path.home() / "oodle/src/ui/oodle-frontend/public/img"
SOURCES = {
    "temporal.svg": OODLE_UI / "vendors/temporal.svg",
    "oodle.svg": OODLE_UI / "logo.svg",
}


def pad(src: pathlib.Path, label: str) -> str:
    raw = src.read_text()
    root = re.search(r"<svg\b[^>]*>", raw, re.S).group(0)
    box = re.search(r'viewBox="([\d.\s-]+)"', root)
    if box:
        _, _, width, height = (float(v) for v in box.group(1).split())
    else:
        width = float(re.search(r'width="([\d.]+)"', root).group(1))
        height = float(re.search(r'height="([\d.]+)"', root).group(1))

    inner = raw[raw.index(root) + len(root): raw.rindex("</svg>")]
    side = round(max(width, height) / FRAC)
    dx, dy = (side - width) / 2, (side - height) / 2

    return (
        f"<!-- Upstream mark from {label}, centred on a square canvas.\n"
        f"     FRAC = {FRAC}: the mark spans {FRAC:.0%} of the canvas, and the rest is\n"
        f"     transparent padding. D2 always draws icons at 64x64, so this padding is\n"
        f"     what sets the apparent size and the inset from the card corner.\n"
        f"     Regenerate with assets/pad.py rather than editing by hand. -->\n"
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{side}" height="{side}" viewBox="0 0 {side} {side}">\n'
        f'<g transform="translate({dx:.1f},{dy:.1f})">{inner}</g>\n</svg>\n'
    )


def main() -> None:
    here = pathlib.Path(__file__).resolve().parent
    for name, src in SOURCES.items():
        if not src.exists():
            raise SystemExit(f"missing upstream logo: {src}")
        label = "~/" + str(src.relative_to(pathlib.Path.home()))
        (here / name).write_text(pad(src, label))
        print(f"wrote {name} from {label}")


if __name__ == "__main__":
    main()
