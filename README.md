# YouTube Audio Downloader & Splitter

Download a YouTube video's audio and automatically split it into individual tracks based on timestamps — with a VLC-compatible playlist.  
Timestamps are fetched directly from YouTube chapters or the video description. No manual editing required.

---

## Features

- **Auto-fetch timestamps** from YouTube chapters or video description
- **Split into individual tracks** with proper file names (`01 - Track Name.mp3`)
- **MP3 or OGG output** at your chosen quality (96 – 320 kbps)
- **VLC-compatible M3U playlist** generated automatically
- **Interactive BAT launcher** with dependency auto-installer (Windows)
- **Works without Python** if you build the standalone `.exe` with PyInstaller

---

## Quick Start (Windows)

Just double-click `launcher.bat`.

It will:
1. Check for Python, yt-dlp, and ffmpeg — and offer to install any that are missing
2. Ask for a YouTube URL
3. Preview the track list fetched from YouTube
4. Let you choose the output folder, format, and quality
5. Download and split everything automatically

> **Note:** ffmpeg is installed via `winget` (Windows 10/11) or Chocolatey if not already present.

---

## Requirements

| Tool | Install |
|---|---|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) — check *"Add to PATH"* |
| yt-dlp | `pip install yt-dlp` (or let the launcher do it) |
| ffmpeg | [ffmpeg.org](https://ffmpeg.org/download.html), `winget install Gyan.FFmpeg`, or `choco install ffmpeg` |

---

## Command-Line Usage

```bash
# Basic usage (auto-fetches timestamps from YouTube)
python download_split.py --url "https://www.youtube.com/watch?v=..."

# Preview track list without downloading
python download_split.py --url "https://..." --show-info

# OGG format at 192 kbps
python download_split.py --url "https://..." --format ogg --bitrate 192

# Custom output folder
python download_split.py --url "https://..." --output "C:\Music\MyPlaylist"

# Provide your own timestamp file as fallback
python download_split.py --url "https://..." --timestamps my_timestamps.txt
```

### All options

| Argument | Default | Description |
|---|---|---|
| `--url` | (hardcoded demo URL) | YouTube video URL |
| `--format` | `mp3` | Output format: `mp3` or `ogg` |
| `--bitrate` | `320` | Bitrate in kbps: `96`, `128`, `192`, `256`, `320` |
| `--output` | slug from video title | Output directory |
| `--timestamps` | *(none)* | Fallback `.txt` file with timestamps |
| `--show-info` | — | Print track list and exit (no download) |
| `--no-dep-check` | — | Skip dependency check (used by launcher) |

### Timestamp file format

```
0:00 Intro
1:32 Act I — The Journey
8:45 Act II — The Storm
23:17 Finale
```

---

## Output

```
output\
└── My_Video_Title\
    ├── 01 - Intro.mp3
    ├── 02 - Act I - The Journey.mp3
    ├── 03 - Act II - The Storm.mp3
    ├── 04 - Finale.mp3
    └── playlist.m3u          ← open with VLC
```

---

## Build a Standalone .exe (no Python required)

Run `build.bat` to package `download_split.py` into a single executable using PyInstaller:

```
build.bat
```

Output: `dist\ytdl-splitter.exe`

`launcher.bat` automatically detects the compiled exe and uses it instead of the Python script — so end users only need yt-dlp and ffmpeg (the launcher installs both).

> **What gets bundled:** Python runtime + yt-dlp (Python module).  
> **What still needs system install:** ffmpeg (external binary — the launcher handles it).

---

## How It Works

```
YouTube URL
    │
    ├─ yt-dlp --dump-json ──► chapters / description ──► track list
    │
    ├─ yt-dlp bestaudio ────► raw_audio.webm / .m4a
    │
    └─ ffmpeg (per track) ──► 01 - Title.mp3
                               02 - Title.mp3
                               ...
                               playlist.m3u
```

---

## Project Structure

```
youtube_download_playlist/
├── download_split.py     # Core engine (download + split + playlist)
├── launcher.bat          # Interactive Windows launcher
├── build.bat             # PyInstaller build script
├── requirements.txt      # Python dependencies (yt-dlp)
└── config.ini            # Auto-generated: saves your base output folder
```

---

## License

MIT — do whatever you want, attribution appreciated.
