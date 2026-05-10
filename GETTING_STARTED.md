# Getting Started

TinyPedal is a Python/PySide2 overlay app for rFactor 2 and Le Mans Ultimate.

## Prerequisites

- Python 3.10 (3.8–3.10 for PySide2; 3.11+ requires PySide6)
- Git with submodules initialized

## Clone with submodules

```
git clone --recursive https://github.com/TinyPedal/TinyPedal.git
```

If already cloned without `--recursive`:

```
git submodule update --init
```

## Set up the virtual environment

A `.venv` using Python 3.10.11 already exists in this repo. Activate it:

```powershell
.venv\Scripts\activate.ps1
```

If you need to recreate it:

```powershell
py -3.10 -m venv .venv
.venv\Scripts\activate.ps1
pip install -r requirements.txt
```

## Run

```
python run.py
```

Useful flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--log-level 0` | 1 | Warning/error only |
| `--log-level 2` | 1 | Log to file |
| `--pyside 6` | 2 | Use PySide6 instead of PySide2 |
| `--single-instance 0` | 1 | Allow multiple instances |

## Game setup

The overlay requires the game to run in **Borderless** or **Windowed** mode.

- **Le Mans Ultimate (Windows):** No plugin needed — enable `Plugins` in Settings → Gameplay.
- **rFactor 2:** Install [rF2SharedMemoryMapPlugin](https://github.com/TheIronWolfModding/rF2SharedMemoryMapPlugin) into `rFactor 2\Bin64\Plugins\`, enable it in Settings → Gameplay, then restart the game.
