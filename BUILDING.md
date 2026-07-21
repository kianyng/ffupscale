# Building ffupscale for Windows

These instructions create the folder-based Windows package used for releases.
The package includes Python, PyQt6, FFmpeg, FFprobe, and the required third-party
notices.

## Prerequisites

- 64-bit Windows 10 or 11
- Python 3.9 or newer
- `ffmpeg.exe` and `ffprobe.exe` from the documented FFmpeg 7.1.1 Gyan full
  build, placed in `vendor\ffmpeg\bin\`

The FFmpeg executables are intentionally excluded from Git because of their
size. Before replacing them, review their license and update
`THIRD_PARTY_NOTICES.md` and `licenses\FFmpeg-BUILD-INFO.txt`.

## Prepare the environment

From the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
```

Calling the virtual environment's Python directly avoids PowerShell execution
policy problems and does not require activation.

## Build the application

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --windowed --name ffupscale --distpath release-folder --workpath build-folder --specpath build-folder --icon assets\icon.ico --add-data "assets\icon.ico;assets" --add-binary "vendor\ffmpeg\bin\ffmpeg.exe;bin" --add-binary "vendor\ffmpeg\bin\ffprobe.exe;bin" src\main.py
```

Copy the legal documents beside the executable so recipients can find them:

```powershell
Copy-Item THIRD_PARTY_NOTICES.md release-folder\ffupscale\
Copy-Item licenses release-folder\ffupscale\licenses -Recurse -Force
```

Do not copy design sources such as PSD files or unused PNG exports into the
release folder.

## Verify the package

Test the package from `release-folder\ffupscale` on a computer without Python
or FFmpeg installed. Confirm that:

1. `ffupscale.exe` starts.
2. Importing a video displays its properties and thumbnail.
3. A short render completes using the bundled tools.
4. `THIRD_PARTY_NOTICES.md`, `licenses\GPL-3.0.txt`, and
   `licenses\FFmpeg-BUILD-INFO.txt` are present.
5. The packaged FFmpeg version matches the build-information file.

## Create the ZIP

```powershell
Compress-Archive -Path release-folder\ffupscale -DestinationPath ffupscale-v0.1.0-beta.2-windows-x64.zip -Force
```

Update the version in the ZIP filename for each release. Users must extract the
whole folder before running the application; `ffupscale.exe` depends on the
adjacent `_internal` directory.
