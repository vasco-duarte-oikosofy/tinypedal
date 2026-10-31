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

# Do NOT force the offscreen platform: on Windows its plugin has an EMPTY font
# database, so every glyph renders as a hollow "tofu" box and the layout is
# measured against the wrong metrics. Qt's default platform renders happily into
# a QImage without ever showing a window. On a headless box set
# QT_QPA_PLATFORM=offscreen with a fontconfig font set installed;
# assert_fonts_available() below refuses to run without real glyphs.

from PySide2.QtGui import QFontDatabase, QFontMetricsF
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


def measure_for(widget):
    """The same text metrics the widget draws with."""
    metrics = QFontMetricsF(widget.turn_font)
    return lambda text, _size: (metrics.boundingRect(text).width(),
                                metrics.boundingRect(text).height())


def interior_pixels(widget, placed):
    """Pixels strictly inside the glyphs, as (x, y) pairs."""
    from PySide2.QtGui import QPainterPath
    from PySide2.QtCore import QPointF

    metrics = QFontMetricsF(widget.turn_font)
    points = []
    for label in placed:
        path = QPainterPath()
        path.addText(QPointF(label.x, label.y + metrics.ascent()),
                     widget.turn_font, label.text)
        points.extend(
            (x, y)
            for y in range(int(label.y) - 2, int(label.y + label.height) + 3)
            for x in range(int(label.x) - 2, int(label.x + label.width) + 3)
            if path.contains(QPointF(x + 0.5, y + 0.5))
        )
    return points


def interior_colours(pixmap, points):
    """Colours of the given pixels, so two renders can be compared exactly."""
    image = pixmap.toImage()
    colours = []
    for x, y in points:
        if 0 <= x < image.width() and 0 <= y < image.height():
            colour = image.pixelColor(x, y)
            colours.append((colour.red(), colour.green(), colour.blue(), colour.alpha()))
        else:
            colours.append(None)
    return colours


def ink_inside(pixmap, placed):
    """Painted pixels inside the label boxes of a rendered pixmap."""
    image = pixmap.toImage()
    total = 0
    for label in placed:
        for y in range(int(label.y), int(label.y + label.height) + 1):
            for x in range(int(label.x), int(label.x + label.width) + 1):
                if 0 <= x < image.width() and 0 <= y < image.height():
                    if image.pixelColor(x, y).alpha() > 60:
                        total += 1
    return total


def render(widget, coords):
    """Rebuild the map image the way the widget does on a map update."""
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
    families = QFontDatabase().families()
    metrics = QFontMetricsF(widget.turn_font)
    check("the platform provides fonts", len(families) > 0,
          f"{len(families)} families on platform {QApplication.platformName()!r}")
    check("the label font can draw letters", metrics.inFont("A"),
          "labels would be tofu boxes")
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
        # The label text must be SOLID and white: at ~12 px a plain fill leaves the
        # stems half transparent (measured 33 % of the interior opaque), which is
        # exactly what "it is just the outline" looks like. The self-stroke in the
        # text colour is what fixes it.
        interior = interior_pixels(widget, planned.get("placed", []))
        colours = interior_colours(widget.pixmap_map, interior)
        worst_alpha = min(c[3] for c in colours if c is not None)
        worst_red = min(c[0] for c in colours if c is not None)
        check("every glyph interior pixel is solid white",
              bool(interior) and worst_alpha > 230 and worst_red > 235,
              f"{len(interior)} interior px, worst alpha {worst_alpha}, worst red {worst_red}")

        # The halo is drawn OUTSIDE the letters only: with it on there is dark ink,
        # with it off there is none - and the text above stays untouched either way.
        def dark_pixels(pixmap, labels):
            # Only around the labels: the map's own dark outline must not be counted.
            image = pixmap.toImage()
            boxes = {(x, y)
                     for label in labels
                     for y in range(int(label.y) - 3, int(label.y + label.height) + 4)
                     for x in range(int(label.x) - 3, int(label.x + label.width) + 4)}
            return sum(
                1 for (x, y) in boxes
                if 0 <= x < image.width() and 0 <= y < image.height()
                and image.pixelColor(x, y).alpha() > 40
                and image.pixelColor(x, y).red() < 120
            )

        placed_now = planned.get("placed", [])
        dark_with = dark_pixels(widget.pixmap_map, placed_now)
        widget.wcfg["turn_name_outline_color"] = "#00000000"
        dark_without = dark_pixels(render(widget, coords), placed_now)
        widget.wcfg["turn_name_outline_color"] = "#88000000"
        check("the halo ring is drawn outside the letters",
              dark_with > dark_without * 2 and dark_with - dark_without > 500,
              f"{dark_with} dark px around the labels with the halo, "
              f"{dark_without} without")

        check("the halo scales with the type",
              abs(widget.turn_halo_width(11.8) - 0.71) < 0.01
              and abs(widget.turn_halo_width(20) - 1.2) < 0.01,
              f"{widget.turn_halo_width(11.8):.2f} px at 11.8 px, "
              f"{widget.turn_halo_width(20):.2f} px at 20 px")
        check("the self-stroke scales with the type",
              abs(widget.turn_solidify_width(11.8) - 1.0) < 0.02
              and abs(widget.turn_solidify_width(20) - 1.7) < 0.05,
              f"{widget.turn_solidify_width(11.8):.2f} px at 11.8 px")
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
        for angle in (0, 90):
            widget.wcfg["display_orientation"] = angle
            path = widget.create_map_path(coords)
            widget.draw_map_image(path, widget.circular_map)
            # copy(): the widget reuses one pixmap, so a saved reference would be
            # overwritten by the next render.
            pixmap = widget.pixmap_map.copy()
            pixmap.save(os.path.join(folder, f"widget-{angle}-degrees.png"))
            if angle == 0:
                placed_now = turn_labels.plan_turn_labels(
                    turn_labels.anchor_turns(
                        data[1], coords, widget.map_orient_deg,
                        widget.map_range, widget.map_scale, widget.map_offset),
                    widget.temp_map_size, measure_for(widget),
                    map_width=widget.area_size, map_height=widget.area_size)[0]
                # A plan that is never painted looks exactly like a track without
                # corners, so check the pixels of the saved picture itself.
                ink = ink_inside(pixmap, placed_now)
                check("the saved review image contains the labels", ink > 0,
                      f"{ink} painted px inside {len(placed_now)} label boxes")
        widget.wcfg["display_orientation"] = 0
        print(f"\n  saved images to {folder}")

    print(f"\n{'RESULT: PASS' if not FAILURES else 'RESULT: FAIL (' + str(len(FAILURES)) + ')'}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
