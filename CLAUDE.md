# TinyPedal

Telemetry overlay for rFactor 2 and Le Mans Ultimate. Python/PySide2 desktop app.

## Setup & running

See [GETTING_STARTED.md](GETTING_STARTED.md).

## Project layout

- `tinypedal/` — main package (widgets, modules, UI, adapters)
- `run.py` — entry point
- `pyRfactor2SharedMemory/`, `pyLMUSharedMemory/` — git submodules for sim APIs
- `settings/` — user config JSON files (not committed)

## Key conventions

- Primary Python target: 3.10 (PySide2). PySide6 supported via `--pyside 6` flag.
- Widgets live in `tinypedal/widget/`, data modules in `tinypedal/module/`.
- Headless tests exist for the track map turn labels; run them with the venv:
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_turn_labels.py
  QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_turn_labels_render.py
  QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe tests/test_track_map_widget_labels.py
  ```
  (Linux: `.venv/bin/python`.)

## Turn names on the track map

`tinypedal/turn_labels.py` draws `T1 Abbey`-style labels beside the corners
(`show_turn_name` option, on by default). The layout rule is shared with the
lap-telemetry project, which owns the data:

- corner data ships in `tinypedal/data/turn_labels/<Track Name>.turns.json`;
- it is **generated**, not hand-written: run
  `py dev/scripts/export_turn_labels_for_tinypedal.py` in the lap-telemetry repo
  (`--check` verifies the shipped files are current);
- each corner carries `s_frac` (0 at the start/finish line, 1 at the end of the
  lap), which is interpolated into the recorded map polyline by accumulated
  length — the SVG `dist` values in some shipped maps run backwards;
- the plan is in lap-telemetry `docs/specs/MAP_TURN_NAMES.md`.

The labels are filled *and* stroked in `turn_name_color`: at ~12 px a plain fill
leaves only 33 % of the glyph interior opaque, and the text reads as an outline.
The halo is an outside-only ring (glyph stroke subtracted from a thicker stroke),
painted after the text so it never covers a letter.
