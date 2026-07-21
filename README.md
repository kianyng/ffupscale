<h1>
  <img
    src="assets/icon.ico"
    alt="ffupscale icon"
    width="48"
    align="absmiddle"
  >
  | ffupscale
</h1>

#### A simple FFmpeg video upscaler for people who don't want to work with commands.

FFmpeg normally requires a command prompt, terminal, or batch file. ffupscale provides a native Windows interface with drag-and-drop video selection and customisable encoding settings.

> [!NOTE]
> ffupscale is currently in beta. Bugs and incomplete features should be expected.

## Download

[Download ffupscale v0.1.0 Beta 2](https://github.com/kianyng/ffupscale/releases/tag/v0.1.0-beta.2)

After downloading:

1. Extract the ZIP file.
2. Open the extracted `ffupscale` folder.
3. Run `ffupscale.exe`.

Do not run the application directly from inside the ZIP or move
`ffupscale.exe` away from its `_internal` folder.

## Features

- Drag-and-drop video selection
- Video thumbnail and property display
- Preset and custom output resolutions
- Preset and custom frame rates
- H.264 and H.265 encoding
- Configurable quality and encoding speed
- Live rendering progress
- Render cancellation
- Bundled FFmpeg and FFprobe in the packaged Windows build

## Planned features

- Custom output location
- Target file size and compression
- Additional hardware encoders
- Render queue

[View development progress](progress.md)

## Requirements

### Packaged application

- 64-bit Windows 10 or Windows 11

Python, PyQt6, FFmpeg, and FFprobe are included in the packaged application and
do not need to be installed separately.

### Running from source

- Python 3.9 or newer
- The packages listed in [requirements.txt](requirements.txt)
- FFmpeg and FFprobe in `vendor/ffmpeg/bin`, or available on the system
  `PATH`

```powershell
py -m pip install -r requirements.txt
py src\main.py
```

See [BUILDING.md](BUILDING.md) for the complete Windows packaging and release
checklist.

## Third-party software

Packaged releases include the unmodified FFmpeg 7.1.1 full Windows build,
licensed under GPLv3. See [Third-Party Notices](THIRD_PARTY_NOTICES.md), the
[complete GPLv3 text](licenses/GPL-3.0.txt), and the
[bundled-build record](licenses/FFmpeg-BUILD-INFO.txt) for licensing, source,
and build information.
