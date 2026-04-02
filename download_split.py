#!/usr/bin/env python3
"""
YouTube Audio Downloader & Splitter
------------------------------------
Downloads a YouTube video's audio and splits it into individual tracks.
Timestamps are auto-fetched from YouTube chapters or the video description.
Generates a VLC-compatible M3U playlist.

Requirements:
  - yt-dlp  (pip install yt-dlp)
  - ffmpeg  (must be in PATH)

Usage:
  python download_split.py --url "https://..."
  python download_split.py --url "https://..." --show-info
  python download_split.py --url "https://..." --format ogg --bitrate 192
  python download_split.py --url "https://..." --timestamps fallback.txt
"""

import sys
import re
import json
import subprocess
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_URL    = "https://www.youtube.com/watch?v=Nr82n2P-IDA"
DEFAULT_FORMAT  = "mp3"
DEFAULT_BITRATE = 320
BAR_WIDTH       = 28

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check_dependencies(need_ffmpeg: bool = True):
    tools = ["yt-dlp", "ffmpeg"] if need_ffmpeg else ["yt-dlp"]
    missing = []
    for tool in tools:
        try:
            subprocess.run([tool, "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            missing.append(tool)
    if missing:
        print(f"[ERROR] Missing tools: {', '.join(missing)}")
        print("  yt-dlp : pip install yt-dlp")
        print("  ffmpeg : https://ffmpeg.org/download.html")
        sys.exit(1)


def parse_timestamps(text: str) -> list[dict]:
    """Parse 'MM:SS Title' or 'H:MM:SS Title' lines from any text block."""
    pattern = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$", re.MULTILINE)
    tracks = []
    for time_str, title in pattern.findall(text):
        parts = list(map(int, time_str.split(":")))
        seconds = parts[0] * 60 + parts[1] if len(parts) == 2 \
                  else parts[0] * 3600 + parts[1] * 60 + parts[2]
        tracks.append({"time": seconds, "title": title.strip()})
    return tracks


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name)
    return name.strip(". ") or "track"


def slug_from_title(title: str, max_len: int = 60) -> str:
    """Filesystem-safe slug from a video title, max_len chars."""
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f\'`]', "", title)
    slug = re.sub(r"[^\w\s\-()]", "", slug)
    slug = re.sub(r"\s+", "_", slug.strip())
    return slug[:max_len].rstrip("_.-") or "video"


def seconds_to_hms(s: int) -> str:
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def progress_bar(current: int, total: int) -> str:
    filled = int(BAR_WIDTH * current / total) if total else 0
    return f"[{'█' * filled}{'░' * (BAR_WIDTH - filled)}] {current:02d}/{total:02d}"


# ---------------------------------------------------------------------------
# yt-dlp integration
# ---------------------------------------------------------------------------

def fetch_video_info(url: str) -> dict:
    """Fetch full video metadata (no download) via yt-dlp --dump-json."""
    result = subprocess.run(
        ["yt-dlp", "--dump-json", "--no-playlist", url],
        capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def extract_tracks(info: dict) -> list[dict]:
    """Extract tracks from YouTube chapters, or fall back to description timestamps."""
    chapters = info.get("chapters") or []
    if chapters:
        return [{"time": int(ch["start_time"]), "title": ch["title"]} for ch in chapters]
    return parse_timestamps(info.get("description", ""))


# ---------------------------------------------------------------------------
# --show-info mode  (called by launcher.bat to preview before download)
# ---------------------------------------------------------------------------

def cmd_show_info(url: str):
    """
    Fetches video metadata, displays the track list, then prints
    a __SLUG__=<value> marker on the last line so launcher.bat can
    capture the suggested folder name.
    """
    print("  Fetching video info...\n", flush=True)
    try:
        info = fetch_video_info(url)
    except subprocess.CalledProcessError:
        print("[ERROR] Could not access the video. Check the URL and your connection.")
        sys.exit(1)

    title    = info.get("title", "Unknown")
    slug     = slug_from_title(title)
    duration = int(info.get("duration") or 0)
    tracks   = extract_tracks(info)
    sep      = "  " + "─" * 62

    print(f"  Title    : {title}")
    print(f"  Duration : {seconds_to_hms(duration)}")
    print()

    if tracks:
        print(f"  {len(tracks)} tracks found:")
        print(sep)
        for i, t in enumerate(tracks):
            end_t = tracks[i + 1]["time"] if i + 1 < len(tracks) else duration
            dur_s = end_t - t["time"]
            start_fmt = f"{t['time'] // 60:02d}:{t['time'] % 60:02d}"
            dur_fmt   = f"{dur_s // 60:02d}:{dur_s % 60:02d}"
            print(f"  {i + 1:02d}.  {start_fmt}  ({dur_fmt})  {t['title']}")
        print(sep)
    else:
        print("  [!] No timestamps found in the YouTube description.")
        print("      You can provide a fallback .txt file via --timestamps")

    # Slug marker — must stay on the LAST line for bat capture
    print(f"\n__SLUG__={slug}", flush=True)


# ---------------------------------------------------------------------------
# Download + split
# ---------------------------------------------------------------------------

def download_audio(url: str, dest: Path) -> Path:
    print("\n  [1/3] Downloading audio...\n", flush=True)
    output_template = str(dest / "raw_audio.%(ext)s")
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "--no-playlist", "-o", output_template, url],
        check=True,
    )
    candidates = sorted(dest.glob("raw_audio.*"))
    if not candidates:
        print("[ERROR] Download failed.")
        sys.exit(1)
    return candidates[0]


def split_audio(
    source: Path,
    tracks: list[dict],
    output_dir: Path,
    fmt: str,
    bitrate: int,
    duration: int = 0,
) -> list[Path]:
    total = len(tracks)
    print(f"\n  [2/3] Splitting into {total} tracks ({fmt.upper()} @ {bitrate} kbps)...\n")
    output_files = []

    for i, track in enumerate(tracks):
        start = track["time"]
        end   = tracks[i + 1]["time"] if i + 1 < len(tracks) else None
        title = sanitize_filename(track["title"])
        out_path = output_dir / f"{i + 1:02d} - {title}.{fmt}"

        label = title[:38] + ("…" if len(title) > 38 else "")
        sys.stdout.write(f"\r  {progress_bar(i + 1, total)}  {label:<40}")
        sys.stdout.flush()

        cmd = ["ffmpeg", "-y", "-i", str(source), "-ss", seconds_to_hms(start)]
        if end is not None:
            cmd += ["-to", seconds_to_hms(end)]
        if fmt == "mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"]
        else:
            cmd += ["-c:a", "libvorbis", "-b:a", f"{bitrate}k"]
        cmd.append(str(out_path))
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output_files.append(out_path)

    sys.stdout.write(f"\r  {progress_bar(total, total)}  {'Splitting complete!':<40}\n\n")
    sys.stdout.flush()
    return output_files


def create_m3u_playlist(files: list[Path], playlist_path: Path):
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        for fp in files:
            f.write(f"#EXTINF:-1,{fp.stem}\n{fp.name}\n\n")


def print_recap(files: list[Path], playlist_path: Path, fmt: str, bitrate: int):
    total_mb = sum(f.stat().st_size for f in files if f.exists()) / (1024 * 1024)
    sep = "  " + "═" * 62
    print(sep)
    print("  SUMMARY")
    print(sep)
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  {f.stem[:55]:<55}  {size_kb:6.0f} KB")
    print(sep)
    print(f"  Tracks    : {len(files)}")
    print(f"  Format    : {fmt.upper()} @ {bitrate} kbps")
    print(f"  Total     : {total_mb:.1f} MB")
    print(f"  Folder    : {files[0].parent.resolve()}")
    print(f"  Playlist  : {playlist_path.name}  (open with VLC)")
    print(sep)
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download and split a YouTube video into individual audio tracks."
    )
    parser.add_argument("--url",        default=DEFAULT_URL)
    parser.add_argument("--format",     choices=["mp3", "ogg"], default=DEFAULT_FORMAT)
    parser.add_argument("--output",     default=None, help="Output directory")
    parser.add_argument("--timestamps", default=None,
                        help="Fallback .txt file with timestamps if YouTube has none")
    parser.add_argument("--bitrate",    type=int, default=DEFAULT_BITRATE,
                        choices=[320, 256, 192, 128, 96])
    parser.add_argument("--show-info",  action="store_true",
                        help="Print video title and track list, then exit")
    parser.add_argument("--no-dep-check", action="store_true",
                        help="Skip dependency check (used when called from launcher.bat)")
    args = parser.parse_args()

    if not args.no_dep_check:
        check_dependencies(need_ffmpeg=not args.show_info)

    if args.show_info:
        cmd_show_info(args.url)
        return

    # ── Fetch metadata ─────────────────────────────────────────────────────
    print("\n  Fetching metadata...", flush=True)
    try:
        info = fetch_video_info(args.url)
    except subprocess.CalledProcessError:
        print("[ERROR] Could not access the video.")
        sys.exit(1)

    # ── Tracks ─────────────────────────────────────────────────────────────
    if args.timestamps:
        ts_file = Path(args.timestamps)
        if not ts_file.exists():
            print(f"[ERROR] Timestamps file not found: {ts_file}")
            sys.exit(1)
        tracks = parse_timestamps(ts_file.read_text(encoding="utf-8"))
    else:
        tracks = extract_tracks(info)

    if not tracks:
        print("[ERROR] No timestamps found. Provide a fallback file via --timestamps")
        sys.exit(1)

    # ── Output directory ───────────────────────────────────────────────────
    output_dir = Path(args.output) if args.output \
                 else Path(slug_from_title(info.get("title", "video")))
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = int(info.get("duration") or 0)

    # ── Download → Split → Playlist ────────────────────────────────────────
    raw_file    = download_audio(args.url, output_dir)
    track_files = split_audio(raw_file, tracks, output_dir,
                               fmt=args.format, bitrate=args.bitrate, duration=duration)
    raw_file.unlink(missing_ok=True)

    print("  [3/3] Creating VLC playlist...")
    playlist_path = output_dir / "playlist.m3u"
    create_m3u_playlist(track_files, playlist_path)

    print_recap(track_files, playlist_path, args.format, args.bitrate)


if __name__ == "__main__":
    main()
