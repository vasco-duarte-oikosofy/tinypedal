"""Paul Ricard ELMS: packaged names must reach the real track map widget.

The ELMS map was recorded starting ~165 m past the simulator's timing line, so a
`map` polyline rotated at its own first point would draw the start/finish line in
the wrong place and place every label late along the lap. The packaged data is
only correct on a map whose index 0 is the timing line, which is why the alignment
and the anchors are both checked here against the real recorded map.
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

TRACK = 'Paul Ricard - ELMS'
TURNS = 16
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
    check(data is not None, 'runtime loader finds the packaged ELMS labels')
    if data is None:
        return 1
    length, turns = data
    outline = json.loads(args.outline.read_text(encoding='utf8'))
    check(length == outline['lap_length_m'] and len(turns) == TURNS,
          f'{TURNS} reviewed ELMS zones use the authoritative simulator axis')
    check([t['name'] for t in turns] == [t['name'] for t in outline['turns']],
          'official names survive publishing, including Chicane Nord and Beausset')
    check([t['short_name'] for t in turns] == [t['short_name'] for t in outline['turns']],
          'map aliases survive publishing (Ste-Baume, Chicane 1/2)')
    coords, _, _ = load_track_map_file('trackmap/', TRACK)
    check(coords is not None, 'actual ELMS recorded map loads, not a different configuration')
    if coords is None:
        return 1
    distances = []
    for turn, baked in zip(turns, outline['turns']):
        x, y, _, _ = turn_labels.anchor_from_fraction(coords, turn['s_frac'])
        distances.append(math.hypot(x - baked['x'], y + baked['y']))
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
            # 16 labels on a 5.8 km lap is the densest published overlay; the
            # 400px/0deg case is allowed one dropped label. Data keeps all 16.
            minimum = 15 if size == 400 and angle == 0 else TURNS
            check(len(placed) >= minimum and len(placed) + len(dropped) == TURNS,
                  f'{size}px/{angle}deg: {len(placed)}/{TURNS} labels (minimum {minimum})')
            check(all(0 <= p.x and 0 <= p.y and p.x + p.width <= size and p.y + p.height <= size
                      for p in placed), f'{size}px/{angle}deg: all labels on canvas')
            check(not any(support.overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]),
                  f'{size}px/{angle}deg: zero overlapping labels')
            check(sum(' ' in p.text for p in placed) >= TURNS - 1,
                  f'{size}px/{angle}deg: at most one number-only fallback')
            widget.show_turn_name = False
            without = support.render_track(widget, TRACK, angle=angle)[2].toImage()
            with_labels = image.toImage()
            check(all(any(with_labels.pixel(x, y) != without.pixel(x, y)
                          for y in range(max(0, int(p.y)), min(size, int(p.y + p.height) + 1))
                          for x in range(max(0, int(p.x)), min(size, int(p.x + p.width) + 1)))
                      for p in placed), f'{size}px/{angle}deg: every label changes actual widget pixels')
            path = args.save / f'paul-ricard-elms-{size}-{angle}.png'
            check(image.save(str(path)) and path.stat().st_size > 1000,
                  f'{size}px/{angle}deg: real-widget evidence saved')
        widget.close()
    return bool(FAILURES)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'[FAIL] ELMS widget regression crashed: {error}')
        raise
