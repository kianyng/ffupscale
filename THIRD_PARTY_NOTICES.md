# Third-Party Notices

ffupscale includes third-party software distributed under its own licence.
The inclusion of this software does not transfer ownership of it to the
ffupscale project.

## FFmpeg

ffupscale includes the `ffmpeg` and `ffprobe` programs from the FFmpeg
project.

- Project: FFmpeg
- Bundled version: 7.1.1
- Build: `ffmpeg-7.1.1-full_build-www.gyan.dev`
- Build provider: Gyan Doshi
- Build type: 64-bit static Windows full build
- Licence: GNU General Public License version 3
- Modifications made by ffupscale: None

### Project and build information

- FFmpeg website: https://ffmpeg.org/
- FFmpeg source: https://ffmpeg.org/releases/ffmpeg-7.1.1.tar.xz
- Windows build provider: https://www.gyan.dev/ffmpeg/builds/
- FFmpeg legal information: https://ffmpeg.org/legal.html

The bundled build was configured with GPL and version-3 components, including
libx264 and libx265. Gyan's static Windows FFmpeg builds are distributed under
the GNU General Public License version 3.

The complete GNU General Public License version 3 text is included in:

[`licenses/GPL-3.0.txt`](licenses/GPL-3.0.txt)

The original build configuration and component information is included in:

[`licenses/FFmpeg-BUILD-INFO.txt`](licenses/FFmpeg-BUILD-INFO.txt)

FFmpeg is a trademark of Fabrice Bellard, originator of the FFmpeg project.
FFmpeg and its included libraries are not owned by the ffupscale project.

ffupscale invokes `ffmpeg.exe` and `ffprobe.exe` as separate programs.
