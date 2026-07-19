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

[Download ffupscale v0.1.0 Beta 1](https://github.com/kianyng/ffupscale/releases/tag/v0.1.0-beta.1)

After downloading:

1. Extract the ZIP file.
2. Open the extracted `ffupscale` folder.
3. Run `ffupscale.exe`.

Do not run the application directly from inside the ZIP.

## Features

- Drag-and-drop video selection
- Video thumbnail and property display
- Preset and custom output resolutions
- Preset and custom frame rates
- H.264 and H.265 encoding
- Configurable quality and encoding speed
- Live rendering progress
- Render cancellation

## Planned features

- Custom output location
- Target file size and compression
- Automatic FFmpeg detection and installation
- Additional hardware encoders

[View development progress](progress.md)

## Requirements

### Packaged application

- Windows
- [FFmpeg](https://ffmpeg.org/download.html), including `ffmpeg` and `ffprobe`

Python and PyQt6 are included in the packaged application and do not need to be installed separately.

FFmpeg's `bin` folder must be available through your system `PATH`. Confirm that both programs are available by running:

```powershell
ffmpeg -version
ffprobe -version
