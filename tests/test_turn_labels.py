"""Tests for turn name labels on the track map.

Run with the project venv (no display needed, no pytest):

    .venv/Scripts/python.exe tests/test_turn_labels.py      # Windows
    .venv/bin/python tests/test_turn_labels.py              # Linux

The layout rule is shared with lap-telemetry's compare app, so these tests check
the same properties the JS tests check: adjacency, no overlap, text degradation,
alternating sides, and the small-map fallbacks.
"""

import sys

sys.path.append(".")

from tinypedal.turn_labels import (
    TURN_LABEL_CONFIG,
    anchor_from_fraction,
    anchor_turns,
    font_size,
    default_data_path,
    load_turn_labels,
    outward_normal,
    plan_turn_labels,
    turn_texts,
)

FAILURES = []


def check(name, condition, detail=""):
    print(f"  [{'PASS' if condition else 'FAIL'}] {name}{' — ' + detail if detail else ''}")
    if not condition:
        FAILURES.append(name)


def measure(text, size):
    """Stand-in for QFontMetrics: ~0.56 em per char, 1.15 em line height."""
    return len(text) * size * 0.56, size * 1.15


def square_track(nodes=200, size=1000.0, elevation=0.0):
    """A closed rectangle recorded as (dist, elevation) + (x, y) pairs."""
    coords, dists = [], []
    sides = 4
    per_side = nodes // sides
    total = size * 4
    corners = ((0.0, 0.0), (size, 0.0), (size, size), (0.0, size))
    for side in range(sides):
        start = corners[side]
        end = corners[(side + 1) % sides]
        for step in range(per_side):
            ratio = step / per_side
            coords.append((
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            ))
            dists.append((total * side / sides + total / sides * ratio, elevation))
    return coords, dists, total


def turns_at(fractions, names=None):
    turns = []
    for index, fraction in enumerate(fractions):
        name = names[index] if names else f"Corner {index + 1}"
        turns.append({
            "number": index + 1,
            "name": name,
            "short_name": None,
            "apex_s_m": 0.0,
            "s_frac": fraction,
        })
    return turns


def overlaps(a, b):
    return (
        min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > 0
        and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > 0
    )


def frame_for(coords, area_size, margin=40, angle=0):
    """The same map frame the widget builds in create_map_path().

    Returns (map_range, map_scale, map_offset, map_size) where map_size is the
    drawn extent (the canvas minus its margin), which is what sizes the type.
    """
    from tinypedal import calculation as calc
    _scaled, map_range, map_scale, map_offset = calc.scale_map(coords, area_size, margin, angle)
    return map_range, map_scale, map_offset, area_size - margin * 2


def test_font_size():
    print("\n-- font size --")
    # The widget draws 1.6x the compare app's type (its map is 100-400 px), so the
    # app's reviewed 5.75 px at 250 px becomes 9.2 px here.
    check("60% larger than the compare app: 9.2 px at a 250 px map",
          abs(font_size(250) - 5.75 * TURN_LABEL_CONFIG["font_scale"]) < 1e-9,
          f"{font_size(250)}")
    check("the scale never overrides the 5 px floor", font_size(120) == 5.0)
    check("5 px floor at a 120 px map", abs(font_size(120) - 5.0) < 1e-9, f"{font_size(120)}")
    check("grows with the map", font_size(400) > font_size(200), f"{font_size(400)}")
    check("ceiling only binds on a huge map",
          abs(font_size(2000) - TURN_LABEL_CONFIG["font_max"]) < 1e-9)


def test_texts():
    print("\n-- text tiers --")
    check("'T1 Abbey' on a roomy map", turn_texts(1, "Abbey", 400)[0] == "T1 Abbey")
    check("no-T variant only on small maps",
          "1 Abbey" not in turn_texts(1, "Abbey", 400) and "1 Abbey" in turn_texts(1, "Abbey", 120))
    check("number only when the corner has no name", turn_texts(5, None, 400) == ("T5",))
    check("no duplicate texts", len(set(turn_texts(1, "Abbey", 100))) == len(turn_texts(1, "Abbey", 100)))


def test_anchors():
    print("\n-- anchoring on the recorded map --")
    coords, _dists, total = square_track()
    recorded = total                 # the loop closes back onto the first node
    x, y, tan_x, tan_y = anchor_from_fraction(coords, 0.0)
    check("s_frac 0 sits at the start", abs(x) < 1e-6 and abs(y) < 1e-6, f"{x:.2f},{y:.2f}")
    x, y, tan_x, tan_y = anchor_from_fraction(coords, 0.25)
    check("s_frac 0.25 sits a quarter of the recording",
          abs(x - recorded * 0.25) < 1e-6 and abs(y) < 1e-6, f"{x:.2f},{y:.2f}")
    check("tangent is a unit vector", abs((tan_x ** 2 + tan_y ** 2) ** 0.5 - 1) < 1e-9)
    x, y, tan_x, tan_y = anchor_from_fraction(coords, 1.0)
    check("s_frac 1 closes the loop back onto the start",
          abs(x - coords[0][0]) < 1e-6 and abs(y - coords[0][1]) < 1e-6, f"{x:.2f},{y:.2f}")
    x, y, tan_x, tan_y = anchor_from_fraction(coords, 0.5)
    check("s_frac 0.5 is the far corner of the lap",
          abs(x - 1000) < 5 and abs(y - 1000) < 5, f"{x:.2f},{y:.2f}")

    nor_x, nor_y = outward_normal(500, 0, 1, 0, (500, 500))
    check("outward normal points away from the centre", nor_y < 0, f"{nor_x:.2f},{nor_y:.2f}")
    nor_x, nor_y = outward_normal(500, 1000, 1, 0, (500, 500))
    check("outward normal flips on the far side", nor_y > 0, f"{nor_x:.2f},{nor_y:.2f}")

    map_range, map_scale, map_offset, map_size = frame_for(coords, 400)
    anchors = anchor_turns(turns_at([0.125, 0.375]), coords, 0,
                           map_range, map_scale, map_offset)
    # An anchor must be the raw point run through the map's own transform.
    raw_x, raw_y, _tx, _ty = anchor_from_fraction(coords, 0.125)
    expected = ((raw_x - map_range[0]) * map_scale + map_offset[0],
                (raw_y - map_range[2]) * map_scale + map_offset[1])
    check("anchors land on the map like the path itself",
          abs(anchors[0].x - expected[0]) < 1e-9 and abs(anchors[0].y - expected[1]) < 1e-9,
          f"{anchors[0].x:.1f},{anchors[0].y:.1f}")
    check("anchors stay on the canvas",
          all(0 <= a.x <= 400 and 0 <= a.y <= 400 for a in anchors))
    check("anchors keep their unit vectors",
          abs((anchors[0].normal_x ** 2 + anchors[0].normal_y ** 2) ** 0.5 - 1) < 1e-9)

    # Rotation must move anchors exactly like the map itself.
    rotated_range, rotated_scale, rotated_offset, _ = frame_for(coords, 400, 40, 45)
    rotated = anchor_turns(turns_at([0.125]), coords, 45,
                           rotated_range, rotated_scale, rotated_offset)
    check("rotated anchors stay on the canvas",
          0 <= rotated[0].x <= 400 and 0 <= rotated[0].y <= 400,
          f"{rotated[0].x:.1f},{rotated[0].y:.1f}")


def test_placement():
    print("\n-- placement --")
    coords, dists, total = square_track()
    map_range, map_scale, map_offset, map_size = frame_for(coords, 400)
    anchors = anchor_turns(turns_at([0.125, 0.375, 0.625, 0.875],
                                    ["Abbey", "Village", "Stowe", "Club"]),
                           coords, 0, map_range, map_scale, map_offset)
    placed, dropped = plan_turn_labels(anchors, map_size, measure,
                                       map_width=400, map_height=400)
    check("every turn on a simple track is labelled", len(placed) == 4, f"{len(placed)}/4")
    check("labels keep their names", all(" " in label.text for label in placed),
          ", ".join(label.text for label in placed))
    check("no two labels overlap",
          not any(overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]))
    check("labels alternate outside/inside",
          {label.side for label in placed} == {1, -1},
          str(sorted(label.side for label in placed)))

    # Adjacency: a label may not run away from its corner. The cap is
    # 2.4 font sizes along the track and min(2.4 fs, 4% of the map) away from it.
    size = font_size(map_size)
    worst = max(
        max(abs(label.x + label.width * 0.5 - label.apex_x),
            abs(label.y + label.height * 0.5 - label.apex_y))
        for label in placed
    )
    cap = max(size * 2.4, map_size * 0.04) + size * 2
    check("labels stay beside their corner", worst <= cap, f"worst {worst:.1f} px, cap {cap:.1f} px")

    print("\n-- dense map degradation --")
    dense = turns_at([0.02 + 0.01 * i for i in range(12)],
                     [f"Corner {i + 1}" for i in range(12)])
    dense_anchors = anchor_turns(dense, coords, 0, map_range, map_scale, map_offset)
    placed, dropped = plan_turn_labels(dense_anchors, map_size, measure,
                                       map_width=400, map_height=400)
    # Degrading the text comes first, dropping a label is the last resort, so on
    # a deliberately absurd cluster every corner must be accounted for.
    check("every crowded corner is either labelled or dropped",
          len(placed) + len(dropped) == 12
          and len({label.number for label in placed + dropped}) == 12,
          f"{len(placed)} placed, {len(dropped)} dropped")
    check("crowded labels never overlap",
          not any(overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]))
    check("crowded labels give up text before position",
          any("T" in label.text and " " not in label.text for label in placed),
          ", ".join(label.text for label in placed[:4]))

    print("\n-- tiny map --")
    tiny_range, tiny_scale, tiny_offset, tiny_size = frame_for(coords, 100, 10)
    tiny_anchors = anchor_turns(turns_at([0.125, 0.375, 0.625, 0.875]),
                                coords, 0, tiny_range, tiny_scale, tiny_offset)
    placed, dropped = plan_turn_labels(tiny_anchors, tiny_size, measure,
                                       map_width=100, map_height=100)
    check("a 100 px map stays inside its bounds",
          all(label.x >= 0 and label.y >= 0
              and label.x + label.width <= 100
              and label.y + label.height <= 100 for label in placed),
          f"{len(placed)} labels")
    check("a 100 px map never overlaps",
          not any(overlaps(a, b) for i, a in enumerate(placed) for b in placed[i + 1:]))


def test_loading():
    print("\n-- loading shipped data --")
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "Test Track.turns.json")
        with open(path, "w", encoding="utf-8") as file:
            file.write('{"lap_length_m": 1000.0, "turns": [{"number": 1, "name": "A",'
                       ' "s_frac": 0.25}]}')
        loaded = load_turn_labels("Test Track", [folder + os.sep])
        check("loads a shipped file", loaded is not None and loaded[0] == 1000.0
              and len(loaded[1]) == 1)
        check("missing file is not an error", load_turn_labels("Nope", [folder + os.sep]) is None)
        with open(path, "w", encoding="utf-8") as file:
            file.write('{"turns": [{"number": 1}]}')
        check("malformed file is rejected", load_turn_labels("Test Track", [folder + os.sep]) is None)
        check("the shipped data folder has files",
              len([n for n in __import__("os").listdir(default_data_path())
                   if n.endswith(".turns.json")]) >= 10)


def main():
    test_font_size()
    test_texts()
    test_anchors()
    test_placement()
    test_loading()
    print(f"\n{'RESULT: PASS' if not FAILURES else 'RESULT: FAIL (' + str(len(FAILURES)) + ')'}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(main())
