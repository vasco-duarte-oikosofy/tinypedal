"""Silverstone National Circuit: packaged names must reach the real track map widget.

The National map is a 2.64 km loop that shares Copse / Maggots / Becketts /
Brooklands / Luffield / Woodcote with the GP tarmac but excludes the Arena
complex and the Hangar Straight. Labelling it with the International or GP
corner set would put six wrong names on a short lap, so the packaged fractions
are checked against the real recorded map's own distance axis.
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

TRACK = 'Silverstone National Circuit'
TURNS = 6
EXPECTED = ['Copse', 'Maggots', 'Becketts', 'Brooklands', 'Luffield', 'Woodcote']
FAILURES = 0


def check(value, label):
    global FAILURES
    print(f"{'[PASS]' if value else '[FAIL]'} {label}")
    FAILURES += not value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--save', type=Path, required=True)
    parser.add_argument('--outline', type=Path, required=True)
    args = parser.parse_args()
    data = turn_labels.load_turn_labels(TRACK)
    check(data is not None, 'runtime loader finds the packaged National labels')
    if data is None:
        return 1
    length, turns = data
    outline = json.loads(args.outline.read_text(encoding='utf8'))
    check(length == outline['lap_length_m'] and len(turns) == TURNS,
          f'{TURNS} reviewed National corners use the authoritative simulator axis')
    check([t['name'] for t in turns] == EXPECTED,
          'official National names survive publishing (Copse, Maggots, Becketts, Brooklands, Luffield, Woodcote)')
    coords, _, _ = load_track_map_file('trackmap/', TRACK)
    check(coords is not None, 'actual National recorded map loads, not a different configuration')
    if coords is None:
        return 1
    distances = []
    for turn, baked in zip(turns, outline['turns']):
        x, y, _, _ = turn_labels.anchor_from_fraction(coords, turn['s_frac'])
        distances.append(math.hypot(x - baked['x'], y + baked['y']))
    # The recorded map axis (2630.2 m) is ~9 m shorter than the simulator axis
    # used for apex distances (2639.1 m), so the last corners drift a little.
    check(max(distances) < 30.0,
          f'normalized anchors remain on real corners (worst {max(distances):.1f}m)')
    app = QApplication.instance() or QApplication([])
    support.load_cfg()
    args.save.mkdir(parents=True, exist_ok=True)
    for size in (400, 600):
        widget = support.make_widget(size)
        check(support.assert_fonts_available(widget.turn_font), f'{size}px native font has real glyphs')
        for angle in (0, 90):
            widget.show_turn_name = True
            placed, dropped, image = support.render_track(widget, TRACK, angle=angle)
            check(len(placed) == TURNS and not dropped,
                  f'{size}px/{angle}deg: {len(placed)}/{TURNS} labels (none dropped)')
            check(all(0 <= p.x and 0 <= p.y and p.x + p.width <= size and p.y + p.height <= size
                      for p in placed), f'{size}px/{angle}deg: all labels on canvas')
            check(not any(support.overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]),
                  f'{size}px/{angle}deg: zero overlapping labels')
            check(all(' ' in p.text for p in placed),
                  f'{size}px/{angle}deg: every label carries its official name, not just a number')
            widget.show_turn_name = False
            without = support.render_track(widget, TRACK, angle=angle)[2].toImage()
            with_labels = image.toImage()
            check(all(any(with_labels.pixel(x, y) != without.pixel(x, y)
                          for y in range(max(0, int(p.y)), min(size, int(p.y + p.height) + 1))
                          for x in range(max(0, int(p.x)), min(size, int(p.x + p.width) + 1)))
                      for p in placed), f'{size}px/{angle}deg: every label changes actual widget pixels')
            path = args.save / f'silverstone-national-{size}-{angle}.png'
            check(image.save(str(path)) and path.stat().st_size > 1000,
                  f'{size}px/{angle}deg: real-widget evidence saved')
        widget.close()
    return bool(FAILURES)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'[FAIL] National widget regression crashed: {error}')
        raise
