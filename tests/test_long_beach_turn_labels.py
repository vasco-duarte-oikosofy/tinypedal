"""Regression: Long Beach must ship turn data AND paint it in the real widget.

Run from the TinyPedal root with its venv, optionally --save DIR --outline JSON.
Leave QT_QPA_PLATFORM unset on Windows so real system fonts are available.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.append('.')
from PySide2.QtWidgets import QApplication
from tinypedal import turn_labels
from tinypedal.userfile.track_map import load_track_map_file
import test_turn_labels_render as support

TRACK = 'Grand Prix of Long Beach'
FAILURES = 0


def check(value, label):
    global FAILURES
    print(f"{'[PASS]' if value else '[FAIL]'} {label}")
    FAILURES += not value


def changed_pixels(with_image, without_image, label):
    return sum(with_image.pixel(x, y) != without_image.pixel(x, y)
               for y in range(max(0, int(label.y)), min(with_image.height(), int(label.y + label.height) + 1))
               for x in range(max(0, int(label.x)), min(with_image.width(), int(label.x + label.width) + 1)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save', type=Path)
    parser.add_argument('--outline', type=Path)
    args = parser.parse_args()
    data = turn_labels.load_turn_labels(TRACK)
    check(data is not None, 'Long Beach packaged turn data is available to the runtime loader')
    if data is None:
        return 1
    length, turns = data
    check(length == 3185.3 and [t['number'] for t in turns] == list(range(1, 12)),
          'all 11 official turns ship on the simulator lap-distance axis')
    check(all(t.get('name') is None and t.get('short_name') is None for t in turns),
          'map labels use T1..T11 rather than speech-specific names')
    coords, _, _ = load_track_map_file('trackmap/', TRACK)
    check(coords is not None, 'real Long Beach recorded map is available')
    if coords is None:
        return 1
    if args.outline:
        outline = json.loads(args.outline.read_text(encoding='utf-8'))
        distances = []
        for turn, baked in zip(turns, outline['turns']):
            x, y, _, _ = turn_labels.anchor_from_fraction(coords, turn['s_frac'])
            # This actual fixture stores world X/-Z; compare app stores X/Z.
            # Only a regression check, not a shared-coordinate runtime assumption.
            distances.append(math.hypot(x - baked['x'], y + baked['y']))
        check(len(distances) == 11 and max(distances) < 20,
              f'normalized anchors stay beside their real corners (worst {max(distances):.1f}m)')
    app = QApplication.instance() or QApplication([])
    support.load_cfg()
    if args.save:
        args.save.mkdir(parents=True, exist_ok=True)
    for size in (400, 600):
        widget = support.make_widget(size)
        check(support.assert_fonts_available(widget.turn_font), f'{size}px widget has real letter glyphs')
        for angle in (0, 90):
            widget.show_turn_name = True
            placed, dropped, with_labels = support.render_track(widget, TRACK, angle=angle)
            check(len(placed) == 11 and not dropped and
                  {label.text for label in placed} == {f'T{i}' for i in range(1, 12)},
                  f'{size}px/{angle}deg: all 11 official labels planned')
            check(all(0 <= p.x and 0 <= p.y and p.x + p.width <= size and p.y + p.height <= size
                      for p in placed), f'{size}px/{angle}deg: labels stay on canvas')
            check(not any(support.overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]),
                  f'{size}px/{angle}deg: no label overlaps')
            widget.show_turn_name = False
            without_labels = support.render_track(widget, TRACK, angle=angle)[2]
            check(len(placed) == 11 and all(changed_pixels(with_labels.toImage(), without_labels.toImage(), p) > 0
                                           for p in placed),
                  f'{size}px/{angle}deg: every label actually changes painted pixels')
            if args.save:
                path = args.save / f'long-beach-{size}-{angle}.png'
                check(with_labels.save(str(path)) and path.stat().st_size > 1000,
                      f'{size}px/{angle}deg: real-widget review image saved')
        widget.close()
    return bool(FAILURES)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'[FAIL] Long Beach real-widget regression crashed: {error}')
        raise
