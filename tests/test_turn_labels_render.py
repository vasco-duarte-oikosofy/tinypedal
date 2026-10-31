"""End-to-end turn label render check against the shipped data.

Runs headless (no display needed):

    QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_turn_labels_render.py

For every track that has both a TinyPedal track map and exported turn labels,
this loads the real SVG, anchors the real corners on it, lays the labels out
with real Qt font metrics, paints the map + labels into a pixmap, and checks:

- every corner gets a label inside the canvas;
- no two labels overlap;
- a PNG is written so the result can be inspected by eye.

Add `--save <folder>` to keep the rendered images.
"""

import os
import sys

sys.path.append(".")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide2.QtCore import QPointF, Qt
from PySide2.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter,
    QPainterPath, QPen,
)

from tinypedal import calculation as calc
from tinypedal import turn_labels
from tinypedal.userfile.track_map import load_track_map_file

TRACKMAP = "trackmap/"
TURNDATA = "tinypedal/data/turn_labels/"
AREA_SIZE = 400
AREA_MARGIN = 40
MAP_COLOR = QColor("#FFFFFF")
TEXT_COLOR = QColor("#CCCCCC")
OUTLINE_COLOR = QColor("#88000000")

FAILURES = []


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    if not condition:
        FAILURES.append(name)


def overlaps(a, b):
    return (
        min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > 0
        and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > 0
    )


def render_track(app, track_name, save_folder=None, angle=0):
    """Render one track; returns (placed, dropped, image)."""
    coords, _dists, _sectors = load_track_map_file(TRACKMAP, track_name)
    data = turn_labels.load_turn_labels(track_name, [TURNDATA])
    if coords is None or data is None:
        return None

    _lap_length, turns = data
    map_scaled, map_range, map_scale, map_offset = calc.scale_map(
        coords, AREA_SIZE, AREA_MARGIN, angle)
    map_size = AREA_SIZE - AREA_MARGIN * 2
    anchors = turn_labels.anchor_turns(
        turns, coords, angle, map_range, map_scale, map_offset)

    font = QFont("Consolas")
    font.setWeight(QFont.Bold)
    size = turn_labels.font_size(map_size)
    font.setPixelSize(max(round(size), 1))
    metrics = QFontMetricsF(font)

    def measure(text, _size):
        rect = metrics.boundingRect(text)
        return rect.width(), rect.height()

    placed, dropped = turn_labels.plan_turn_labels(
        anchors, map_size, measure, map_width=AREA_SIZE, map_height=AREA_SIZE)

    image = QImage(AREA_SIZE, AREA_SIZE, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    for index, point in enumerate(map_scaled):
        if index == 0:
            path.moveTo(*point)
        else:
            path.lineTo(*point)
    path.closeSubpath()
    pen = QPen(MAP_COLOR)
    pen.setWidth(4)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(path)

    painter.setFont(font)
    halo = QPen(OUTLINE_COLOR)
    halo.setWidthF(max(size * 0.16, 1.0))
    halo.setJoinStyle(Qt.RoundJoin)
    brush = QBrush(TEXT_COLOR)
    for label in placed:
        text_path = QPainterPath()
        text_path.addText(QPointF(label.x, label.y + metrics.ascent()), font, label.text)
        painter.setPen(halo)
        painter.setBrush(QBrush(Qt.NoBrush))
        painter.drawPath(text_path)
        painter.fillPath(text_path, brush)
    painter.end()

    if save_folder:
        image.save(os.path.join(save_folder, f"{track_name}.png"))
    return placed, dropped, image


def main(argv):
    save_folder = None
    if "--save" in argv:
        save_folder = argv[argv.index("--save") + 1]
        os.makedirs(save_folder, exist_ok=True)

    app = QGuiApplication.instance() or QGuiApplication([])

    tracks = sorted(
        name[:-len(".turns.json")] for name in os.listdir(TURNDATA)
        if name.endswith(".turns.json")
    )
    print(f"\n-- {len(tracks)} tracks with exported turn labels --")
    check("labels shipped for several tracks", len(tracks) >= 10, f"{len(tracks)} tracks")

    total_turns = total_labels = total_named = named_turns = 0
    for track_name in tracks:
        result = render_track(app, track_name, save_folder)
        if result is None:
            check(f"{track_name}: has a track map", False, "no map polyline")
            continue
        placed, dropped, image = result
        data = turn_labels.load_turn_labels(track_name, [TURNDATA])
        turns = len(data[1])
        named_turns += sum(1 for turn in data[1] if turn.get("name"))
        total_turns += turns
        total_labels += len(placed)
        on_canvas = all(
            label.x >= 0 and label.y >= 0
            and label.x + label.width <= AREA_SIZE
            and label.y + label.height <= AREA_SIZE
            for label in placed
        )
        clean = not any(overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:])
        painted = image.width() > 0
        if not (clean and on_canvas and painted):
            check(f"{track_name}: {len(placed)}/{turns} labels", False,
                  f"overlaps={not clean} off_canvas={not on_canvas}")
        named = sum(1 for label in placed if " " in label.text)
        total_named += named
        print(f"    {track_name}: {len(placed)}/{turns} labels "
              f"({named} named), {len(dropped)} dropped")

    check("every shipped corner gets a label", total_labels == total_turns,
          f"{total_labels}/{total_turns}")
    check("named corners keep their names on a 400 px map",
          total_named >= named_turns * 0.97,
          f"{total_named}/{named_turns} named corners keep a name")
    check("no overlaps, nothing off canvas on any shipped track",
          not any("labels" in failure for failure in FAILURES))

    # Rotation must not break the layout.
    print("\n-- rotated map --")
    placed, _dropped, _image = render_track(app, tracks[0], None, angle=90)
    check("labels still fit a 90 degree rotated map",
          bool(placed) and all(
              label.x >= 0 and label.y >= 0
              and label.x + label.width <= AREA_SIZE
              and label.y + label.height <= AREA_SIZE for label in placed),
          f"{len(placed)} labels")

    print(f"\n{'RESULT: PASS' if not FAILURES else 'RESULT: FAIL (' + str(len(FAILURES)) + ')'}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
