"""Turn label review images, rendered by the REAL widget.

Run with the venv (no display needed, no pytest):

    .venv/Scripts/python.exe tests/test_turn_labels_render.py [--save <folder>]

For every track that has both a TinyPedal track map and exported turn labels,
this builds the real track map widget, feeds it the real recorded map and the
real turn data, and draws the widget's own pixmap. Nothing about the drawing is
duplicated here: the images are the widget's output, so they cannot drift from
what the app shows (an earlier copy of this test painted its own version and
shipped two rounds of unusable review images).

Checks, for every track:
- the widget plans a label for every corner (or reports the few it drops);
- labels never overlap and stay on the canvas;
- the saved picture really contains them.

Do NOT force the offscreen platform: on Windows its plugin has an EMPTY font
database, so every glyph renders as a hollow "tofu" box. Qt's default platform
renders into a pixmap without ever showing a window; on a headless box set
QT_QPA_PLATFORM=offscreen with a fontconfig font set installed.
assert_fonts_available() refuses to run without real glyphs.
"""

import os
import re
import sys
import unicodedata

sys.path.append(".")

from PySide2.QtGui import QFontDatabase, QFontMetricsF, QPixmap
from PySide2.QtWidgets import QApplication

from tinypedal import turn_labels
from tinypedal.const_file import FileExt
from tinypedal.setting import cfg
from tinypedal.userfile.track_map import load_track_map_file

TRACKMAP = "trackmap/"
TURNDATA = "tinypedal/data/turn_labels/"
AREA_SIZE = 400
AREA_MARGIN = 40

FAILURES = []


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    if not condition:
        FAILURES.append(name)


def safe_name(track_name):
    """ASCII file name: git quotes accented paths, which breaks path tooling."""
    ascii_name = unicodedata.normalize("NFKD", track_name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def assert_fonts_available(font):
    """Refuse to render review images with a font that has no glyphs."""
    families = QFontDatabase().families()
    metrics = QFontMetricsF(font)
    check("the platform provides fonts", len(families) > 0,
          f"{len(families)} families on platform {QApplication.platformName()!r}")
    check("the label font can draw letters", metrics.inFont("A"),
          "every glyph would render as a tofu box")
    return bool(families) and metrics.inFont("A")


def load_cfg():
    """A real preset, because importing the widget chain needs one loaded."""
    cfg.load_global()
    cfg.set_next_to_load(f"{cfg.preset_files()[0]}{FileExt.JSON}")
    cfg.load_user()


def make_widget(area_size=AREA_SIZE):
    from tinypedal.widget.track_map import Realtime

    widget = Realtime(cfg, "track_map")
    widget.wcfg["area_size"] = area_size
    widget.wcfg["area_margin"] = AREA_MARGIN
    widget.wcfg["show_turn_name"] = True
    widget.area_size = max(area_size, 100)
    widget.area_margin = min(max(AREA_MARGIN, 0), int(widget.area_size / 4))
    widget.temp_map_size = widget.area_size - widget.area_margin * 2
    widget.resize(widget.area_size, widget.area_size)
    widget.pixmap_map = QPixmap(widget.area_size, widget.area_size)
    return widget


def plan_for(widget, turns, coords):
    """The labels the widget plans for this map (same inputs, same code)."""
    anchors = turn_labels.anchor_turns(
        turns, coords, widget.map_orient_deg,
        widget.map_range, widget.map_scale, widget.map_offset)
    metrics = QFontMetricsF(widget.turn_font)
    size = min(turn_labels.font_size(widget.temp_map_size),
               max(widget.wcfg["font_size"], 5))
    solidify = widget.turn_solidify_width(size)

    def measure(text, _size):
        rect = metrics.boundingRect(text)
        return rect.width() + solidify, rect.height() + solidify

    return turn_labels.plan_turn_labels(
        anchors, widget.temp_map_size, measure,
        map_width=widget.area_size, map_height=widget.area_size)


def overlaps(a, b):
    return (
        min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > 0
        and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > 0
    )


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


def render_track(widget, track_name, save_folder=None, angle=0):
    """Draw one track with the real widget; returns (placed, dropped, pixmap)."""
    coords, _dists, _sectors = load_track_map_file(TRACKMAP, track_name)
    data = turn_labels.load_turn_labels(track_name, [TURNDATA])
    if coords is None or data is None:
        return None
    _lap_length, turns = data

    widget.turn_data = data
    widget.wcfg["display_orientation"] = angle
    path = widget.create_map_path(coords)
    widget.draw_map_image(path, widget.circular_map)
    pixmap = widget.pixmap_map.copy()

    placed, dropped = plan_for(widget, turns, coords)
    if save_folder:
        pixmap.save(os.path.join(save_folder, f"track-{safe_name(track_name)}.png"))
    return placed, dropped, pixmap


def main(argv):
    save_folder = None
    if "--save" in argv:
        save_folder = argv[argv.index("--save") + 1]
        os.makedirs(save_folder, exist_ok=True)

    app = QApplication.instance() or QApplication([])
    load_cfg()
    widget = make_widget()
    if not assert_fonts_available(widget.turn_font):
        print("\nRESULT: FAIL (no usable fonts — leave QT_QPA_PLATFORM unset so Qt "
              "can use a platform with a font database)")
        return 1

    tracks = sorted(
        name[:-len(".turns.json")] for name in os.listdir(TURNDATA)
        if name.endswith(".turns.json")
    )
    print(f"\n-- {len(tracks)} tracks with exported turn labels --")
    check("labels shipped for several tracks", len(tracks) >= 10, f"{len(tracks)} tracks")

    total_turns = total_labels = total_named = named_turns = 0
    geometry_ok = True
    empty_images = []
    for track_name in tracks:
        result = render_track(widget, track_name, save_folder)
        if result is None:
            check(f"{track_name}: has a track map", False, "no map polyline")
            continue
        placed, dropped, pixmap = result
        _lap_length, turns = turn_labels.load_turn_labels(track_name, [TURNDATA])
        total_turns += len(turns)
        total_labels += len(placed)
        total_named += sum(1 for label in placed if " " in label.text)
        named_turns += sum(1 for turn in turns if turn.get("name"))

        clean = not any(overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:])
        on_canvas = all(
            label.x >= 0 and label.y >= 0
            and label.x + label.width <= widget.area_size
            and label.y + label.height <= widget.area_size
            for label in placed
        )
        if ink_inside(pixmap, placed) == 0:
            empty_images.append(track_name)
        geometry_ok = geometry_ok and clean and on_canvas
        if not (clean and on_canvas):
            check(f"{track_name}: {len(placed)}/{len(turns)} labels", False,
                  f"overlaps={not clean} off_canvas={not on_canvas}")
        named = sum(1 for label in placed if " " in label.text)
        print(f"    {track_name}: {len(placed)}/{len(turns)} labels "
              f"({named} named), {len(dropped)} dropped")

    check("no overlaps, nothing off canvas on any shipped track", geometry_ok)
    check("every rendered track actually shows its labels", not empty_images,
          ", ".join(empty_images) or "all tracks inked")

    # Type is 1.6x the compare app's here (see turn_labels.TURN_LABEL_CONFIG), which
    # at the default 400 px map costs the last few crowded corners their label. The
    # numbers below are the measured trade-off, not a guess: a bigger widget buys
    # them back (checked further down).
    check("almost every shipped corner gets a label at 400 px",
          total_labels >= total_turns * 0.98,
          f"{total_labels}/{total_turns} corners labelled")
    check("most named corners keep their names at 400 px",
          total_named >= named_turns * 0.90,
          f"{total_named}/{named_turns} named corners keep a name")

    print("\n-- same tracks on a 600 px widget --")
    big = make_widget(600)
    big_labels = big_turns = big_named = big_named_turns = 0
    for track_name in tracks:
        result = render_track(big, track_name)
        if result is None:
            continue
        placed = result[0]
        _lap_length, turns = turn_labels.load_turn_labels(track_name, [TURNDATA])
        big_turns += len(turns)
        big_labels += len(placed)
        big_named += sum(1 for label in placed if " " in label.text)
        big_named_turns += sum(1 for turn in turns if turn.get("name"))
    check("a 600 px widget labels every corner", big_labels == big_turns,
          f"{big_labels}/{big_turns} corners")
    check("a 600 px widget keeps the names", big_named >= big_named_turns * 0.95,
          f"{big_named}/{big_named_turns} named corners keep a name")

    print("\n-- rotated map --")
    placed, _dropped, _pixmap = render_track(widget, tracks[0], None, angle=90)
    check("labels still fit a 90 degree rotated map",
          bool(placed) and all(
              label.x >= 0 and label.y >= 0
              and label.x + label.width <= widget.area_size
              and label.y + label.height <= widget.area_size for label in placed),
          f"{len(placed)} labels")

    print(f"\n{'RESULT: PASS' if not FAILURES else 'RESULT: FAIL (' + str(len(FAILURES)) + ')'}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
