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
- No test suite currently.
- Widgets live in `tinypedal/widget/`, data modules in `tinypedal/module/`.
