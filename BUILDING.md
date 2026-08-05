# Building ffupscale for Windows

These instructions explain how to run ffupscale from source, create the portable
Windows package and build the standard Windows installer.

Packaged builds include Python, PyQt6, FFmpeg, FFprobe and the required licence
and third-party notices.

## Prerequisites

You will need:

- 64-bit Windows 10 or Windows 11
- [Python 3.9 or newer](https://www.python.org/downloads/)
- [Git](https://git-scm.com/download/win)
- The FFmpeg 8.1.2 Gyan full Windows build
- [Inno Setup](https://jrsoftware.org/isdl.php) for building the installer

The FFmpeg executables are intentionally excluded from Git because of their
size. They must be added locally before running or packaging ffupscale.

## Clone the repository

Open PowerShell and run:

```powershell
git clone https://github.com/kianyng/ffupscale.git
cd ffupscale
```

All commands in this document should be run from the repository root unless
stated otherwise.

## Add FFmpeg and FFprobe

Download the **FFmpeg 8.1.2 full Windows build** from
[Gyan's FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/).

The build recorded for the current ffupscale distribution is:

```text
ffmpeg-8.1.2-full_build.7z
```

Extract the archive and locate:

```text
bin/ffmpeg.exe
bin/ffprobe.exe
```

Create this directory inside the cloned repository:

```text
vendor/ffmpeg/bin/
```

Copy both executables into it:

```text
vendor/
└── ffmpeg/
    └── bin/
        ├── ffmpeg.exe
        └── ffprobe.exe
```

Confirm that both programs work:

```powershell
.\vendor\ffmpeg\bin\ffmpeg.exe -version
.\vendor\ffmpeg\bin\ffprobe.exe -version
```

Both commands should report FFmpeg version 8.1.2.

The expected build information is recorded in:

```text
licenses/FFmpeg-BUILD-INFO.txt
```

If the bundled FFmpeg build is replaced with a different version or
configuration, update both of these files before distributing it:

```text
THIRD_PARTY_NOTICES.md
licenses/FFmpeg-BUILD-INFO.txt
```

Review the new FFmpeg build's licence before redistributing it.

## Prepare the Python environment

Create a virtual environment:

```powershell
py -m venv .venv
```

Install the Python dependencies and PyInstaller:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
```

Calling the virtual environment's Python executable directly avoids PowerShell
execution-policy problems and does not require activating the environment.

## Run ffupscale from source

Run the application with:

```powershell
.\.venv\Scripts\python.exe src\main.py
```

Before creating a packaged build, confirm that:

1. ffupscale starts successfully.
2. Importing a video displays its properties and thumbnail.
3. FFmpeg and FFprobe are detected.
4. A short render completes.
5. CPU and available hardware encoders work.
6. The render queue and target-size mode work.

## Build the portable application

The build command writes its generated specification and temporary files into
`build-folder` and the completed application into `release-folder`.

Absolute paths are used because the generated specification is placed inside
`build-folder`. Without them, PyInstaller may incorrectly look for `assets` and
`vendor` inside that directory.

Run:

```powershell
$repoRoot = (Get-Location).Path

.\.venv\Scripts\python.exe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name ffupscale `
    --distpath "$repoRoot\release-folder" `
    --workpath "$repoRoot\build-folder" `
    --specpath "$repoRoot\build-folder" `
    --icon "$repoRoot\assets\icon.ico" `
    --add-data "$repoRoot\assets\icon.ico;assets" `
    --add-binary "$repoRoot\vendor\ffmpeg\bin\ffmpeg.exe;bin" `
    --add-binary "$repoRoot\vendor\ffmpeg\bin\ffprobe.exe;bin" `
    "$repoRoot\src\main.py"
```

The completed application will be created at:

```text
release-folder/ffupscale/
```

Its structure should resemble:

```text
release-folder/
└── ffupscale/
    ├── ffupscale.exe
    └── _internal/
        ├── bin/
        │   ├── ffmpeg.exe
        │   └── ffprobe.exe
        └── ...
```

## Add the licence and third-party documents

Copy ffupscale's licence, the third-party notices and the FFmpeg legal documents
into the portable package:

```powershell
Copy-Item LICENSE.txt release-folder\ffupscale\ -Force
Copy-Item THIRD_PARTY_NOTICES.md release-folder\ffupscale\ -Force
Copy-Item licenses release-folder\ffupscale\licenses -Recurse -Force
```

The completed package should now resemble:

```text
release-folder/
└── ffupscale/
    ├── ffupscale.exe
    ├── LICENSE.txt
    ├── THIRD_PARTY_NOTICES.md
    ├── licenses/
    │   ├── FFmpeg-BUILD-INFO.txt
    │   └── GPL-3.0.txt
    └── _internal/
        ├── bin/
        │   ├── ffmpeg.exe
        │   └── ffprobe.exe
        └── ...
```

Do not copy design sources such as PSD files or unused image exports into the
release folder.

## Verify the portable package

Close any copy of ffupscale that is running, then launch the packaged
application:

```powershell
.\release-folder\ffupscale\ffupscale.exe
```

Test the application from `release-folder\ffupscale`, not from the source
directory.

Confirm that:

1. `ffupscale.exe` starts.
2. The window and taskbar icons appear correctly.
3. Importing a video displays its properties and thumbnail.
4. A short render completes using the bundled FFmpeg programs.
5. CPU encoding completes a short render.
6. Every detected hardware encoder completes a short render.
7. Target-size mode rejects an impractical size.
8. Target-size mode completes successfully with a practical size.
9. Queueing, rendering next, rendering now, cancelling and retrying work.
10. The selected output folder and filename are respected.
11. Opening the completed output folder works.
12. `LICENSE.txt` is present.
13. `THIRD_PARTY_NOTICES.md` is present.
14. `licenses/GPL-3.0.txt` is present.
15. `licenses/FFmpeg-BUILD-INFO.txt` is present.
16. The packaged FFmpeg and FFprobe versions match the build-information file.

The packaged FFmpeg version can be checked directly with:

```powershell
.\release-folder\ffupscale\_internal\bin\ffmpeg.exe -version
.\release-folder\ffupscale\_internal\bin\ffprobe.exe -version
```

## Create the portable ZIP

Choose the version being built:

```powershell
$version = "1.0.1"
```

Create the portable ZIP:

```powershell
Compress-Archive `
    -Path release-folder\ffupscale `
    -DestinationPath "ffupscale-v$version-windows-x64-portable.zip" `
    -Force
```

The resulting archive will be created in the repository root:

```text
ffupscale-v1.0.1-windows-x64-portable.zip
```

Update `$version` for each release.

Users must extract the complete folder before running ffupscale.
`ffupscale.exe` depends on the adjacent `_internal` directory and must not be
moved away from it.

## Build the Windows installer

ffupscale uses [Inno Setup](https://jrsoftware.org/isinfo.php) to package the
folder-based PyInstaller build as a standard Windows application.

The installer provides:

- Installation into `Program Files`
- Start-menu integration
- Optional Desktop shortcut creation
- An entry under Windows Installed Apps
- Uninstall support
- Upgrade support for future versions

### Install Inno Setup

Download and install the current stable version of
[Inno Setup](https://jrsoftware.org/isdl.php).

The default installation options are sufficient.

After installation, open **Inno Setup Compiler** from the Windows Start menu.

### Check the installer configuration

The repository must contain:

```text
installer.iss
```

This file must be in the repository root, beside `BUILDING.md` and
`LICENSE.txt`.

Before compiling, open `installer.iss` and confirm that its application version
matches the version being built:

```ini
#define MyAppVersion "1.0.1"
```

Also update its Windows file-version value:

```ini
VersionInfoVersion=1.0.1.0
```

The installer must use the repository's actual licence filename:

```ini
LicenseFile=LICENSE.txt
```

The installer must read the completed PyInstaller package from:

```ini
Source: "release-folder\ffupscale\*"; \
    DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
```

The permanent ffupscale application ID must not be changed:

```ini
AppId={{ECCB0D6B-746C-4606-BC95-0986F8C1D130}
```

Changing the `AppId` would cause Windows to treat a future version as a separate
application instead of updating the existing installation.

### Compile the installer

The portable application and legal documents must already be present in:

```text
release-folder/ffupscale/
```

In Inno Setup Compiler:

1. Select **File → Open**.
2. Open `installer.iss`.
3. Select **Build → Compile**.

Alternatively, press:

```text
Ctrl + F9
```

The completed installer will be created in:

```text
installer-output/
```

For version 1.0.1, the expected filename is:

```text
installer-output/ffupscale-v1.0.1-setup.exe
```

The filename is controlled by `OutputBaseFilename` inside `installer.iss`.

### Compile from PowerShell

If Inno Setup is installed in its default location, the installer can also be
compiled from PowerShell:

```powershell
$repoRoot = (Get-Location).Path

& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" `
    "$repoRoot\installer.iss"
```

If this path does not exist, compile the installer using Inno Setup Compiler
instead.

## Verify the installed application

Run the generated setup file and complete the installation.

The default installation directory should be:

```text
C:\Program Files\ffupscale
```

Launch ffupscale from the Windows Start menu and confirm that:

1. Installation completes without errors.
2. ffupscale appears in the Start menu.
3. The optional Desktop shortcut works when selected.
4. ffupscale appears under Windows Installed Apps.
5. The displayed version number is correct.
6. The window and taskbar icons appear.
7. Video properties and thumbnails load.
8. Bundled FFmpeg and FFprobe are detected.
9. A short CPU render completes.
10. A short hardware-encoder render completes when supported.
11. Target-size mode works.
12. Queue operations work.
13. Output files are created in the selected location.
14. ffupscale can be uninstalled successfully.

Test the installed application with the repository and VS Code closed. This
helps confirm that it is using the files installed into `Program Files` rather
than files from the source directory.

## Verify installer upgrades

Before distributing an update, install the previous ffupscale version and then
run the new installer.

Confirm that:

1. The installer updates the existing installation.
2. Windows displays only one ffupscale entry under Installed Apps.
3. The displayed version number is updated.
4. Start-menu and Desktop shortcuts continue to work.
5. The updated application starts and renders successfully.
6. Uninstalling removes the installed application.

Every installer version must retain this application ID:

```ini
AppId={{ECCB0D6B-746C-4606-BC95-0986F8C1D130}
```

## Build outputs

A completed Windows build produces two distributable files:

```text
ffupscale-v1.0.1-setup.exe
ffupscale-v1.0.1-windows-x64-portable.zip
```

The setup executable is the recommended package for normal installation.

The portable ZIP is available for users who prefer not to install ffupscale.

FFmpeg and FFprobe must remain bundled inside both packages and must not be
distributed separately from the applicable licence and third-party notices.