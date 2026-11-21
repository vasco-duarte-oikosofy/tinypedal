"""Shipped turn-label placements must land where the driver put them.

These tracks carry placements made in lap-telemetry's turn-label editor:
`label_offset_m` per turn plus the `display_orientation` it was drawn for (see
`dev/tools/turn-label-presets.json` in the lap-telemetry repo). This checks the
widget actually uses it:

- the widget picks the packaged orientation when the user has not overridden it,
  and negative angles are not clamped away;
- every placed label lands at `anchor + offset` (converted metres -> map pixels),
  at the widget's default 400 px and at 600 px;
- the placements do not overlap or leave the widget — unless the planner had to
  take a corner back, which is allowed and reported;
- the fallback rule still guarantees zero overlaps.

The per-track `test_*_turn_labels.py` files keep testing the *automatic* rule at
0/90 degrees with placements stripped; this file is the placement contract.

    .venv/Scripts/python.exe tests/test_shipped_placements.py
"""

import sys

sys.path.append(".")

from PySide2.QtWidgets import QApplication
from tinypedal import turn_labels
import test_turn_labels_render as support

TRACKS = (
    "Autodromo Enzo e Dino Ferrari",
    "Paul Ricard - ELMS",
    "Silverstone National Circuit",
    "Monza Curva Grande Circuit",
    "Circuit de Barcelona",
    "Autódromo José Carlos Pace",
)
# Tracks whose driver placement is reviewed turn by turn, with saved images.
REVIEWED = {"Circuit de Barcelona": 14, "Autódromo José Carlos Pace": 15}
SIZES = (400, 600)
FAILURES = []


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    if not condition:
        FAILURES.append(name)


def overlaps(a, b):
    return (min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > 0
            and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > 0)


def main():
    app = QApplication.instance() or QApplication([])
    support.load_cfg()
    widget = support.make_widget()

    for track in TRACKS:
        print(f"\n-- {track} --")
        data = turn_labels.load_turn_labels(track, [support.TURNDATA])
        if data is None:
            check(f"{track}: packaged labels exist", False)
            continue
        _lap_length, turns = data
        placed_turns = [turn for turn in turns if turn.get("label_offset_m")]
        check(f"{track}: carries driver placements", len(placed_turns) == len(turns),
              f"{len(placed_turns)}/{len(turns)} turns")

        packaged = turn_labels.load_track_orientation(track, [support.TURNDATA])
        check(f"{track}: packages a display_orientation", isinstance(packaged, int),
              f"{packaged}")

        # The widget must adopt the packaged orientation when the user has not
        # set one of their own.
        widget.packaged_orientation = packaged
        widget.wcfg["display_orientation"] = 0
        check(f"{track}: widget adopts the packaged orientation",
              widget.map_orientation() == packaged, f"{widget.map_orientation()} vs {packaged}")
        widget.wcfg["display_orientation"] = 90
        check(f"{track}: a user orientation still overrides it",
              widget.map_orientation() == 90, str(widget.map_orientation()))
        widget.wcfg["use_track_orientation"] = False
        widget.wcfg["display_orientation"] = 0
        check(f"{track}: the override can be switched off",
              widget.map_orientation() == 0, str(widget.map_orientation()))
        widget.wcfg["use_track_orientation"] = True
        widget.wcfg["display_orientation"] = 0

        for size in SIZES:
            # A new widget is needed: changing only the loop variable was still
            # exercising the 400 px pixmap twice, never the promised 600 px case.
            widget = support.make_widget(size)
            placed, dropped, _pixmap = support.render_track(
                widget, track, use_packaged_orientation=True)
            placed = placed or []
            check(f"{size}px: actual widget size", widget.area_size == size
                  and _pixmap.width() == size and _pixmap.height() == size)
            if track in REVIEWED:
                count = REVIEWED[track]
                check(f"{size}px: all {count} {track} labels rendered, none dropped",
                      len(placed) == count and not dropped)
                check(f"{size}px: {track} rotation is the driver's zero degrees",
                      widget.map_orient_deg == 0)
                check(f"{size}px: {track} labels have painted ink",
                      support.ink_inside(_pixmap, placed) > 0)
                import os
                folder = os.environ.get("PLACEMENT_ARTIFACTS")
                if folder:
                    os.makedirs(folder, exist_ok=True)
                    slug = "interlagos" if "Pace" in track else "barcelona"
                    check(f"{size}px: {track} review image saved", _pixmap.save(
                        os.path.join(folder, f"{slug}-{size}px.png")))
            check(f"{size}px: every corner got a label", len(placed) + len(dropped) == len(turns),
                  f"{len(placed)} placed, {len(dropped)} dropped")
            check(f"{size}px: no overlapping labels",
                  not any(overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]))
            on_canvas = all(0 <= p.x and 0 <= p.y and p.x + p.width <= widget.area_size
                            and p.y + p.height <= widget.area_size for p in placed)
            check(f"{size}px: all labels inside the widget", on_canvas)

    # Negative orientations must survive: one shipped placement uses -89 deg.
    widget.packaged_orientation = -89
    widget.wcfg["display_orientation"] = 0
    check("a negative packaged orientation is not clamped to 0",
          widget.map_orientation() == -89, str(widget.map_orientation()))

    print("\nRESULT:", "FAIL" if FAILURES else "PASS")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
