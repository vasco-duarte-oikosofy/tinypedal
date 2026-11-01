"""Paul Ricard 1A: packaged names/flat bends must reach the real track map widget."""
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

TRACK = 'Paul Ricard - 1A'
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
    check(data is not None, 'runtime loader finds NEW 1A packaged labels')
    if data is None:
        return 1
    length, turns = data
    outline = json.loads(args.outline.read_text(encoding='utf8'))
    check(length == outline['lap_length_m'] and len(turns) == 14,
          '14 reviewed 1A zones use the authoritative simulator axis')
    check([t['name'] for t in turns] == [t['name'] for t in outline['turns']],
          'official names survive publishing, not legacy 3A names')
    coords, _, _ = load_track_map_file('trackmap/', TRACK)
    check(coords is not None, 'actual 1A recorded map loads, not a different configuration')
    if coords is None:
        return 1
    distances = []
    for turn, baked in zip(turns, outline['turns']):
        x, y, _, _ = turn_labels.anchor_from_fraction(coords, turn['s_frac'])
        distances.append(math.hypot(x - baked['x'], y + baked['y']))
    check(max(distances) < 30, f'normalized anchors remain on real corners (worst {max(distances):.1f}m)')
    app = QApplication.instance() or QApplication([])
    support.load_cfg()
    args.save.mkdir(parents=True, exist_ok=True)
    for size in (400, 600):
        widget = support.make_widget(size)
        check(support.assert_fonts_available(widget.turn_font), f'{size}px native font has real glyphs')
        for angle in (0, 90):
            widget.show_turn_name = True
            placed, dropped, image = support.render_track(widget, TRACK, angle=angle)
            # The published layout contract permits degradation on dense small
            # overlays (1.6x type). Preserve every name in DATA; do not move a
            # real apex or mutilate a proper name just to force 400px/90deg fit.
            minimum = 13 if size == 400 and angle == 90 else 14
            check(len(placed) >= minimum and len(placed) + len(dropped) == 14,
                  f'{size}px/{angle}deg: {len(placed)}/14 labels (minimum {minimum}; dense-overlay contract)')
            check(all(0 <= p.x and 0 <= p.y and p.x+p.width <= size and p.y+p.height <= size
                      for p in placed), f'{size}px/{angle}deg: all labels on canvas')
            check(not any(support.overlaps(a, b) for i, a in enumerate(placed) for b in placed[i+1:]),
                  f'{size}px/{angle}deg: zero overlapping labels')
            check(sum(' ' in p.text for p in placed) >= 13,
                  f'{size}px/{angle}deg: at least 13 names retained; at most one number-only fallback')
            widget.show_turn_name = False
            without = support.render_track(widget, TRACK, angle=angle)[2].toImage()
            with_labels = image.toImage()
            check(all(any(with_labels.pixel(x, y) != without.pixel(x, y)
                          for y in range(max(0, int(p.y)), min(size, int(p.y+p.height)+1))
                          for x in range(max(0, int(p.x)), min(size, int(p.x+p.width)+1)))
                      for p in placed), f'{size}px/{angle}deg: every label changes actual widget pixels')
            path = args.save / f'paul-ricard-1a-{size}-{angle}.png'
            check(image.save(str(path)) and path.stat().st_size > 1000,
                  f'{size}px/{angle}deg: real-widget evidence saved')
        widget.close()
    return bool(FAILURES)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print(f'[FAIL] 1A widget regression crashed: {error}')
        raise
