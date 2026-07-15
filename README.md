# ffupscale
#### A simple video upscaler using FFmpeg — for people who don't want to mess about with commands.

FFmpeg upscaling normally requires using a command prompt, terminal, or batch file, which can be complicated or inconvenient.

ffupscale is a native Windows application for easily upscaling videos with customisable settings and drag-and-drop capability, so you don't have to work with FFmpeg commands directly.

---

### [View progress](progress.md)

---

## Upcoming features

* Adjustable output resolution
* Adjustable output FPS
* Encoding presets
* Quality presets
* Output location
* Target file size

## Requirements

### Required to run from source

* [Python 3.9 or newer](https://www.python.org/downloads/)
* [PyQt6](https://pypi.org/project/PyQt6/)
* [FFmpeg](https://ffmpeg.org/download.html), including `ffmpeg` and `ffprobe`

FFmpeg's `bin` folder must be added to your system `PATH`. Confirm that both programs are available with:

```powershell
ffmpeg -version
ffprobe -version
```

### Development dependency

* [Watchdog](https://pypi.org/project/watchdog/) powers the included VS Code auto-restart task.

Python's standard-library modules such as `json`, `pathlib`, `shutil`, `subprocess`, and `sys` are included with Python and do not need separate installation.

## Installation

Clone the repository, open a terminal in its root folder, and install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the application with:

```powershell
python src/ui.py
```
