# Third-Party Notices

This document describes third-party software distributed with packaged builds of
ffupscale. It is not the license for ffupscale itself.

## FFmpeg

Packaged Windows builds of ffupscale include the following unmodified executable
programs:

- `ffmpeg.exe`
- `ffprobe.exe`

The bundled version is **FFmpeg 7.1.1**, using the
`ffmpeg-7.1.1-full_build-www.gyan.dev` 64-bit static Windows build provided by
[Gyan Doshi](https://www.gyan.dev/ffmpeg/builds/).

FFmpeg is Copyright © 2000–2025 the FFmpeg developers. The bundled full build is
licensed under the **GNU General Public License, version 3 or later (GPLv3+)**.
Its reported configuration includes `--enable-gpl`, `--enable-version3`,
`--enable-static`, `--enable-libx264`, and `--enable-libx265`.

- License text: [licenses/GPL-3.0.txt](licenses/GPL-3.0.txt)
- Bundled-build record: [licenses/FFmpeg-BUILD-INFO.txt](licenses/FFmpeg-BUILD-INFO.txt)
- Corresponding FFmpeg 7.1.1 source archive:
  [ffmpeg-7.1.1.tar.xz](https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz)
- FFmpeg source repository: [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg/tree/n7.1.1)
- Build provider and documentation:
  [gyan.dev FFmpeg builds](https://www.gyan.dev/ffmpeg/builds/)
- FFmpeg licensing information: [ffmpeg.org/legal.html](https://ffmpeg.org/legal.html)

ffupscale does not claim ownership of FFmpeg, FFprobe, their source code, or the
libraries incorporated into the supplied FFmpeg build. FFmpeg is a trademark of
Fabrice Bellard, originator of the FFmpeg project.

When redistributing ffupscale, keep this notice, the complete GPLv3 text, and the
build-information file with the bundled FFmpeg binaries.
