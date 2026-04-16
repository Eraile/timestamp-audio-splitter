# Audio Downloader & Splitter

Download audio from any yt-dlp supported source and automatically split it into individual tracks based on timestamps — with a VLC-compatible playlist.  
Or download the full video as MP4 in one click.  
Also handles **playlists** — audio (split per-video) or all videos as MP4.  
Timestamps are fetched automatically from chapters, the video description, or even the most-liked viewer comments.

---

## Features

- **Auto-fetch timestamps** from chapters, video description, or **top viewer comments**
- **Split into individual tracks** with proper file names (`01 - Track Name.mp3`)
- **MP3 or OGG output** at your chosen quality (96 – 320 kbps)
- **Full video download** as MP4 (best available quality) — no splitting needed
- **Playlist support** — download an entire playlist as audio or MP4 in one go
- **Cover art** automatically downloaded, embedded in every track, and saved as `cover.jpg`
- **VLC-compatible M3U playlist** generated automatically
- **Interactive BAT launcher** with dependency auto-installer (Windows)
- **Works without Python** if you build the standalone `.exe` with PyInstaller

---

## Quick Start (Windows)

Just double-click `launcher.bat`.

It will:
1. Check for Python, yt-dlp, and ffmpeg — and offer to install any that are missing
2. Ask for a URL
3. Preview the track list fetched from available metadata
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
# Basic usage (auto-fetches timestamps from metadata)
python download_split.py --url "https://..."

# Preview track list without downloading
python download_split.py --url "https://..." --show-info

# OGG format at 192 kbps
python download_split.py --url "https://..." --format ogg --bitrate 192

# Download full video as MP4
python download_split.py --url "https://..." --format mp4

# Download an entire playlist as MP3 audio
python download_split.py --url "https://...playlist..." --format mp3

# Download an entire playlist as MP4 videos at up to 1080p
python download_split.py --url "https://..." --format mp4 --video-quality 1080 --playlist

# Custom output folder
python download_split.py --url "https://..." --output "C:\Music\MyPlaylist"

# Provide your own timestamp file as fallback
python download_split.py --url "https://..." --timestamps my_timestamps.txt
```

### All options

| Argument | Default | Description |
|---|---|---|
| `--url` | — | Video or playlist URL |
| `--format` | `mp3` | Output format: `mp3`, `ogg`, or `mp4` |
| `--bitrate` | `320` | Bitrate in kbps: `96`, `128`, `192`, `256`, `320` (audio only) |
| `--video-quality` | `best` | Max resolution for MP4 mode: `best`, `2160`, `1440`, `1080`, `720`, `480`, `360` |
| `--playlist` | — | Force playlist mode (auto-detected for pure playlist URLs) |
| `--output` | slug from title | Output directory |
| `--timestamps` | *(none)* | Fallback `.txt` file with timestamps (audio mode only) |
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

## Timestamp sources (priority order)

The tool tries each source in order and stops at the first one that works:

| # | Source | Notes |
|---|---|---|
| 1 | **Chapters** | Most reliable; set by the uploader |
| 2 | **Video description** | Common on compilation / DJ mix videos |
| 3 | **Viewer comments** | Top ~30 most-liked comments are scanned; first one with ≥ 3 timestamps wins |
| — | `--timestamps` file | Manual override, always takes priority when specified |

---

## Output

**Audio mode — single video (MP3 / OGG)**
```
output\
└── Title\
    ├── cover.jpg
    ├── 01 - Intro.mp3          ← cover art embedded
    ├── 02 - Act I.mp3
    ├── 03 - Act II.mp3
    ├── 04 - Finale.mp3
    └── playlist.m3u            ← open with VLC
```

**Audio mode — playlist (MP3 / OGG)**
```
output\
└── Playlist_Title\
    ├── cover.jpg
    ├── 01 - Track A.mp3
    ├── 02 - Track B.mp3
    ├── 03 - Full Video.mp3     ← no timestamps = one file
    └── playlist.m3u            ← open with VLC
```

**Video mode — single video (MP4)**
```
output\
└── Title\
    └── Title.mp4
```

**Video mode — playlist (MP4)**
```
output\
└── Playlist_Title\
    ├── 01 - First Video.mp4
    ├── 02 - Second Video.mp4
    └── playlist.m3u
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
URL
    │
    ├─ yt-dlp --dump-json ──► chapters / description / comments ──► track list
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

## Legal Notice

This tool is intended for downloading and processing content you have the right to use.  
Users are responsible for complying with applicable laws and platform terms of service.

---

## License

MIT — do whatever you want, attribution appreciated.
