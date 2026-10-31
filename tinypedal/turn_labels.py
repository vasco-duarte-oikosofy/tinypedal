#  TinyPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#
#  This file is part of TinyPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""Turn name labels for the track map.

Places "T1 Abbey"-style labels beside the corners of the track map.  The layout
rule is shared with the lap-telemetry compare app, where it was designed and
reviewed at map sizes from 100 px to 950 px (see
lap-telemetry `docs/specs/MAP_TURN_NAMES.md`):

- every label is anchored to its corner and may only move by a capped amount,
  so it never drifts away from the corner it names;
- two labels never overlap each other; crossing the track ribbon is allowed;
- the text degrades before it moves: "T2 Roggia 2" -> "T12" -> dropped;
- odd turns are placed outside the loop, even turns inside, which buys room on
  dense circuits without pushing anything away.

Nothing here imports Qt: text metrics are injected by the caller, so the whole
rule can be tested without a display, and the same code works for any painter.

Anchoring
---------
The corner positions come from lap-telemetry outlines, which are in LMU world
coordinates.  TinyPedal records its own map path, so the only thing the two
share is the distance along the lap: each turn carries `s_frac` (0 at the
start/finish line, 1 at the end of the lap), which is interpolated into the
recorded map polyline by accumulated length at runtime.

The polyline's own length is used rather than the SVG `dist` values because
those are not reliable: several shipped maps store a `dist` polyline that runs
backwards (Silverstone GP: 5865 m down to 5863 m), which collapsed every anchor
onto the first node.  Walking the geometry has no such failure mode.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass

from . import calculation as calc

logger = logging.getLogger(__name__)

# Layout constants.  The RULE is shared with product/web/js/turnLabels.js; two
# presentation constants differ on purpose, because the map here is much smaller:
#   - font_scale 1.6: the widget's map is 100-400 px against the compare app's
#     500-950 px, so the same ratio gave 7 px type, which is too small to read on
#     an overlay. The rule (ratio, caps, gaps) is unchanged, everything is 1.6x.
#   - see widget/track_map.py for the halo width, which is size dependent.
TURN_LABEL_CONFIG = {
    "font_ratio": 0.023,      # font size = clamp(map_size * ratio, min, max)
    "font_scale": 1.6,        # widget type is 60% larger than the compare app's
    "font_min": 5.0,          # 5.75 px at a 250 px map
    "font_max": 18.0,         # only stops absurd type on a huge map
    "gap_ratio": 0.75,        # gap from the track, in font sizes
    "along_cap_font": 2.4,    # max slide ALONG the track, in font sizes
    "normal_cap_map": 0.04,   # max move AWAY from the track, fraction of map
    "nudge_steps": (0.0, 1.2, -1.2, 2.4, -2.4),
    "small_map": 150.0,       # below this, also try "<n> <name>" (drops the "T")
}

ANCHOR_SAMPLE_NODES = 2   # nodes either side used for the tangent


@dataclass(frozen=True)
class TurnLabel:
    """One placed label, in map pixels."""

    text: str
    number: int
    x: float
    y: float
    width: float
    height: float
    side: int          # 1 = outside the loop, -1 = inside
    apex_x: float
    apex_y: float


@dataclass(frozen=True)
class TurnAnchor:
    """A corner in map pixels, with unit vectors in the same space."""

    number: int
    name: str | None
    short_name: str | None
    x: float
    y: float
    normal_x: float    # outward from the loop
    normal_y: float
    tangent_x: float
    tangent_y: float


def font_size(map_size: float, config: dict | None = None) -> float:
    """Type size for a map of `map_size` pixels (its shorter side)."""
    cfg = config or TURN_LABEL_CONFIG
    scale = cfg.get("font_scale", 1.0)
    size = map_size * cfg["font_ratio"] * scale
    return max(cfg["font_min"], min(cfg["font_max"], size))


def turn_texts(number: int, name: str | None, map_size: float,
               config: dict | None = None) -> tuple[str, ...]:
    """Text variants for one turn, best first."""
    cfg = config or TURN_LABEL_CONFIG
    texts = []
    if name:
        texts.append(f"T{number} {name}")
        if map_size < cfg["small_map"]:
            texts.append(f"{number} {name}")
    texts.append(f"T{number}")
    return tuple(dict.fromkeys(texts))


def _unit(x: float, y: float) -> tuple[float, float]:
    length = math.hypot(x, y)
    if length < 1e-9:
        return 0.0, 0.0
    return x / length, y / length


def _rotate(point: tuple[float, float], degrees: int) -> tuple[float, float]:
    """Rotate a point the same way the map is rotated for display."""
    if not degrees:
        return point
    return next(iter(calc.rotate_map((point,), degrees)))


def closed_path(coords) -> tuple[list, list]:
    """Track polyline closed into a loop, with its accumulated length."""
    points = list(coords)
    if len(points) > 1 and points[0] != points[-1]:
        points.append(points[0])
    lengths = [0.0]
    for first, second in zip(points, points[1:]):
        lengths.append(lengths[-1] + math.hypot(second[0] - first[0], second[1] - first[1]))
    return points, lengths


def anchor_from_fraction(coords, s_frac: float) -> tuple[float, float, float, float]:
    """Interpolate a map point at `s_frac` of the lap, plus its tangent.

    Returns (x, y, tangent_x, tangent_y) in the map's raw coordinates.
    """
    if not coords or len(coords) < 2:
        raise ValueError("map data too short to anchor")
    points, lengths = closed_path(coords)
    target = lengths[-1] * min(max(s_frac, 0.0), 1.0)
    index = 0
    for index in range(len(lengths) - 1):
        if lengths[index + 1] >= target:
            break
    span = lengths[index + 1] - lengths[index]
    ratio = 0.0 if span <= 0 else (target - lengths[index]) / span
    first, second = points[index], points[index + 1]
    x = first[0] + (second[0] - first[0]) * ratio
    y = first[1] + (second[1] - first[1]) * ratio

    low = max(index - ANCHOR_SAMPLE_NODES, 0)
    high = min(index + 1 + ANCHOR_SAMPLE_NODES, len(points) - 1)
    tangent_x, tangent_y = _unit(
        points[high][0] - points[low][0],
        points[high][1] - points[low][1],
    )
    return x, y, tangent_x, tangent_y


def map_centroid(coords) -> tuple[float, float]:
    """Centre of the recorded track, used to pick the outward normal."""
    if not coords:
        return 0.0, 0.0
    return (
        sum(point[0] for point in coords) / len(coords),
        sum(point[1] for point in coords) / len(coords),
    )


def outward_normal(
    x: float, y: float, tangent_x: float, tangent_y: float,
    centroid: tuple[float, float],
) -> tuple[float, float]:
    """Normal pointing away from the centre of the track.

    The sim's left/right sign convention is not portable, so the side is decided
    by the geometry: the normal that points away from the map centre is outward.
    """
    normal_x, normal_y = _unit(-tangent_y, tangent_x)
    if normal_x * (x - centroid[0]) + normal_y * (y - centroid[1]) < 0:
        return -normal_x, -normal_y
    return normal_x, normal_y


def anchor_turns(turns, coords, angle: int, map_range, map_scale, map_offset,
                 ) -> list[TurnAnchor]:
    """Anchor every turn on the map, rotated and scaled like the map path."""
    centroid = map_centroid(coords)
    min_x, _, min_y, _ = map_range
    anchors = []
    for turn in turns:
        x, y, tan_x, tan_y = anchor_from_fraction(coords, float(turn["s_frac"]))
        nor_x, nor_y = outward_normal(x, y, tan_x, tan_y, centroid)
        # Rotate exactly like the map, then apply its scale & offset.
        (rx, ry), (rtx, rty), (rnx, rny) = (
            _rotate((x, y), angle),
            _rotate((tan_x, tan_y), angle),
            _rotate((nor_x, nor_y), angle),
        )
        anchors.append(TurnAnchor(
            number=int(turn["number"]),
            name=turn.get("name"),
            short_name=turn.get("short_name"),
            x=(rx - min_x) * map_scale + map_offset[0],
            y=(ry - min_y) * map_scale + map_offset[1],
            normal_x=rnx,
            normal_y=rny,
            tangent_x=rtx,
            tangent_y=rty,
        ))
    return anchors


def _overlaps(a: TurnLabel, b: TurnLabel) -> bool:
    return (
        min(a.x + a.width, b.x + b.width) - max(a.x, b.x) > 0
        and min(a.y + a.height, b.y + b.height) - max(a.y, b.y) > 0
    )


def plan_turn_labels(anchors, map_size: float, measure, map_width: float | None = None,
                     map_height: float | None = None, config: dict | None = None,
                     ) -> tuple[list[TurnLabel], list[TurnLabel]]:
    """Place every label; returns (placed, dropped).

    `measure(text, font_size)` must return (width, height) in pixels.
    """
    cfg = config or TURN_LABEL_CONFIG
    map_width = map_size if map_width is None else map_width
    map_height = map_size if map_height is None else map_height
    size = font_size(map_size, cfg)
    gap = size * cfg["gap_ratio"]
    along_cap = cfg["along_cap_font"] * size
    normal_cap = min(cfg["along_cap_font"] * size, cfg["normal_cap_map"] * map_size)

    placed: list[TurnLabel] = []
    dropped: list[TurnLabel] = []

    for index, anchor in enumerate(anchors):
        # Odd turns sit outside the loop, even turns inside; the other side is
        # the first fallback before a label gives up its name.
        preferred = 1 if index % 2 == 0 else -1
        best: TurnLabel | None = None
        fallback: TurnLabel | None = None
        # Order matters: keep the name before changing side, change side before
        # sliding further from the corner.
        for text in turn_texts(anchor.number, anchor.short_name or anchor.name, map_size, cfg):
            width, height = measure(text, size)
            for side in (preferred, -preferred):
                normal_x = anchor.normal_x * side
                normal_y = anchor.normal_y * side
                for step_idx, step in enumerate(cfg["nudge_steps"]):
                    # Odd steps slide ALONG the track, even ones move away from
                    # it.  Sliding keeps a label attached to its corner; pushing
                    # it away does not, so sliding is tried first.
                    along = step_idx % 2 == 1
                    cap = along_cap if along else normal_cap
                    distance = (step / cfg["along_cap_font"]) * cap
                    anchor_x = anchor.x + normal_x * gap
                    anchor_y = anchor.y + normal_y * gap
                    if along:
                        anchor_x += anchor.tangent_x * distance
                        anchor_y += anchor.tangent_y * distance
                    else:
                        anchor_x += normal_x * distance
                        anchor_y += normal_y * distance
                    if normal_x > 0.35:
                        x = anchor_x
                    elif normal_x < -0.35:
                        x = anchor_x - width
                    else:
                        x = anchor_x - width * 0.5
                    if normal_y > 0.35:
                        y = anchor_y
                    elif normal_y < -0.35:
                        y = anchor_y - height
                    else:
                        y = anchor_y - height * 0.5
                    label = TurnLabel(
                        text=text, number=anchor.number, x=x, y=y,
                        width=width, height=height, side=side,
                        apex_x=anchor.x, apex_y=anchor.y,
                    )
                    if fallback is None:
                        fallback = label
                    inside = x >= 0 and y >= 0 and x + width <= map_width and y + height <= map_height
                    if inside and not any(_overlaps(label, other) for other in placed):
                        best = label
                        break
                if best:
                    break
            if best:
                break
        if best:
            placed.append(best)
        elif fallback is not None:
            dropped.append(fallback)

    return placed, dropped


def default_data_path() -> str:
    """Folder of the turn-label files that ship with TinyPedal."""
    return os.path.join(os.path.dirname(__file__), "data", "turn_labels") + os.sep


def load_turn_labels(track_name: str, folders=None) -> tuple[float, tuple] | None:
    """Load the turn-label data for a track, if present.

    Looks in the shipped data folder first, then in the user's track map folder,
    so a user can drop a `<track>.turns.json` next to their own track maps to
    override or add a track.

    Returns (lap_length_m, turns) or None.  Files are generated by lap-telemetry's
    `dev/scripts/export_turn_labels_for_tinypedal.py`.
    """
    for folder in folders or (default_data_path(),):
        try:
            with open(f"{folder}{track_name}.turns.json", encoding="utf-8") as jsonfile:
                data = json.load(jsonfile)
            turns = tuple(data["turns"])
            if not turns or any("s_frac" not in turn for turn in turns):
                raise ValueError
            return float(data.get("lap_length_m", 0.0)), turns
        except FileNotFoundError:
            continue
        except (OSError, KeyError, TypeError, ValueError):
            logger.info("MISSING: invalid turn label data (%s)", track_name)
            return None
    logger.debug("MISSING: turn label data (%s)", track_name)
    return None
