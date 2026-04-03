# Audio Chapter Splitter & Playlist Generator

Download audio from supported sources and automatically split it into
individual tracks based on timestamps --- with a VLC-compatible
playlist.\
Timestamps can be fetched from embedded chapters or metadata when
available. No manual editing required.

------------------------------------------------------------------------

## Features

-   **Auto-fetch timestamps** from chapters or metadata when available
-   **Split into individual tracks** with proper file names
    (`01 - Track Name.mp3`)
-   **MP3 or OGG output** at your chosen quality (96 -- 320 kbps)
-   **VLC-compatible M3U playlist** generated automatically
-   **Interactive BAT launcher** with dependency auto-installer
    (Windows)
-   **Works without Python** if you build the standalone `.exe` with
    PyInstaller

------------------------------------------------------------------------

## Quick Start (Windows)

Just double-click `launcher.bat`.

It will: 1. Check for Python, yt-dlp, and ffmpeg --- and offer to
install any that are missing 2. Ask for a video/audio URL 3. Preview the
track list extracted from available metadata 4. Let you choose the
output folder, format, and quality 5. Download and split everything
automatically

> **Note:** ffmpeg is installed via `winget` (Windows 10/11) or
> Chocolatey if not already present.

------------------------------------------------------------------------

## Requirements

  Tool           Install
  -------------- -----------------------------------
  Python 3.10+   https://www.python.org/downloads/
  yt-dlp         `pip install yt-dlp`
  ffmpeg         https://ffmpeg.org/download.html

------------------------------------------------------------------------

## Command-Line Usage

``` bash
python download_split.py --url "https://example.com/media"
```

------------------------------------------------------------------------

## Timestamp file format

    0:00 Intro
    1:32 Act I — The Journey
    8:45 Act II — The Storm
    23:17 Finale

------------------------------------------------------------------------

## Output

    output/
    └── My_Title/
        ├── 01 - Intro.mp3
        ├── 02 - Act I - The Journey.mp3
        ├── 03 - Act II - The Storm.mp3
        ├── 04 - Finale.mp3
        └── playlist.m3u

------------------------------------------------------------------------

## Legal Notice

This tool is intended for downloading and processing content you have
the right to use.

Users are responsible for complying with applicable laws and platform
terms.

------------------------------------------------------------------------

## License

MIT --- provided as-is, without warranty.
