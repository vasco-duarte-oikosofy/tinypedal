"""Widget-level check: the real track map widget draws turn labels.

Runs headless:

    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_track_map_widget_labels.py

Unlike tests/test_turn_labels.py (which tests the layout rule) and
tests/test_turn_labels_render.py (which renders every shipped track standalone),
this one builds the **real widget class** from `tinypedal/widget/track_map.py`,
feeds it a real recorded map, and checks the pixmap the widget would show:

- the option is on by default and the labels are planned for the corners;
- turning the option off draws strictly fewer pixels;
- a track with no turn data, and a track with no map at all, still render.
"""

import os
import sys

sys.path.append(".")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide2.QtWidgets import QApplication

from tinypedal.const_file import FileExt
from tinypedal.setting import cfg
from tinypedal import turn_labels
from tinypedal.userfile.track_map import load_track_map_file

TRACK = "Monza Curva Grande Circuit"
TRACKMAP = "trackmap/"

FAILURES = []


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    if not condition:
        FAILURES.append(name)


def painted_pixels(pixmap, step=2):
    """Sample the pixmap; anything not fully transparent counts as painted."""
    image = pixmap.toImage()
    total = 0
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            if image.pixelColor(x, y).alpha() > 40:
                total += 1
    return total


def render(widget, coords):
    """Rebuild the map image the way the widget does on a map update."""
    widget.turn_coords = coords
    path = widget.create_map_path(coords)
    widget.draw_map_image(path, widget.circular_map)
    return widget.pixmap_map


def main():
    app = QApplication.instance() or QApplication([])
    # The widget chain imports the API controller, which needs a loaded preset.
    cfg.load_global()
    cfg.set_next_to_load(f"{cfg.preset_files()[0]}{FileExt.JSON}")
    cfg.load_user()

    from tinypedal.widget.track_map import Realtime

    widget = Realtime(cfg, "track_map")
    check("turn names are on by default", widget.show_turn_name is True)
    check("the config exposes the label colours",
          all(key in widget.wcfg for key in
              ("show_turn_name", "turn_name_color", "turn_name_outline_color")))

    coords, _dists, _sectors = load_track_map_file(TRACKMAP, TRACK)
    check("a real track map is available", coords is not None, TRACK)

    data = turn_labels.load_turn_labels(TRACK, (turn_labels.default_data_path(), cfg.path.track_map))
    widget.turn_data = data
    check("turn data is available for the track", data is not None,
          f"{len(data[1]) if data else 0} turns")

    planned = {}
    original = turn_labels.plan_turn_labels

    def spy(anchors, map_size, measure, **kwargs):
        placed, dropped = original(anchors, map_size, measure, **kwargs)
        planned["placed"] = placed
        planned["map_size"] = map_size
        return placed, dropped

    turn_labels.plan_turn_labels = spy
    try:
        with_labels = render(widget, coords)
        with_count = painted_pixels(with_labels)
        placed = planned.get("placed", [])
        check("the widget plans a label for every corner",
              len(placed) == len(data[1]), f"{len(placed)}/{len(data[1])}")
        check("labels are laid out inside the widget canvas",
              all(label.x >= 0 and label.y >= 0
                  and label.x + label.width <= widget.area_size
                  and label.y + label.height <= widget.area_size for label in placed))
        check("the type is readable at the default map size",
              5 <= turn_labels.font_size(planned.get("map_size", 0)) <= 18,
              f"{turn_labels.font_size(planned.get('map_size', 0)):.1f} px")

        widget.show_turn_name = False
        without_labels = render(widget, coords)
        without_count = painted_pixels(without_labels)
        check("turning the option off draws fewer pixels",
              with_count > without_count, f"{with_count} vs {without_count} painted samples")

        widget.show_turn_name = True
        widget.turn_data = None
        no_data_count = painted_pixels(render(widget, coords))
        check("a track without turn data still draws its map",
              no_data_count > 0 and no_data_count < with_count,
              f"{no_data_count} painted samples")

        widget.turn_data = data
        empty_count = painted_pixels(render(widget, ()))
        check("an empty map renders without raising", empty_count >= 0, f"{empty_count} samples")
    finally:
        turn_labels.plan_turn_labels = original

    if "--save" in sys.argv:
        folder = sys.argv[sys.argv.index("--save") + 1]
        os.makedirs(folder, exist_ok=True)
        widget.turn_data = data
        widget.show_turn_name = True
        pixmap = render(widget, coords)
        for angle in (0, 90):
            widget.wcfg["display_orientation"] = angle
            path = widget.create_map_path(coords)
            widget.draw_map_image(path, widget.circular_map)
            widget.pixmap_map.save(os.path.join(folder, f"widget-{TRACK}-{angle}.png"))
        pixmap.save(os.path.join(folder, f"widget-{TRACK}.png"))
        print(f"\n  saved images to {folder}")

    print(f"\n{'RESULT: PASS' if not FAILURES else 'RESULT: FAIL (' + str(len(FAILURES)) + ')'}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
