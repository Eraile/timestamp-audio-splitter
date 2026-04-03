#!/usr/bin/env python3
"""
YouTube Audio Downloader & Splitter
------------------------------------
Downloads a YouTube video's audio and splits it into individual tracks.
Timestamps are auto-fetched from YouTube chapters or the video description.
Generates a VLC-compatible M3U playlist.

Requirements:
  - yt-dlp  (pip install yt-dlp  — bundled automatically in the .exe build)
  - ffmpeg  (must be in PATH — auto-installed via winget when running as .exe)

Usage:
  python download_split.py --url "https://..."
  python download_split.py --url "https://..." --show-info
  python download_split.py --url "https://..." --format ogg --bitrate 192
  python download_split.py --url "https://..." --timestamps fallback.txt
"""

import sys
import os
import re
import subprocess
import argparse
from pathlib import Path

# Ensure UTF-8 output (needed when running as a standalone exe on Windows)
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import yt_dlp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_FORMAT  = "mp3"
DEFAULT_BITRATE = 320
BAR_WIDTH       = 28

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ffmpeg_in_path() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def _reload_path_from_registry():
    """Reload PATH from Windows registry to pick up freshly installed tools."""
    try:
        import winreg
        paths = []
        for hive, subkey in [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment"),
        ]:
            try:
                with winreg.OpenKey(hive, subkey) as key:
                    value, _ = winreg.QueryValueEx(key, "Path")
                    paths.append(value)
            except OSError:
                pass
        if paths:
            os.environ["PATH"] = ";".join(paths)
    except ImportError:
        pass  # Not on Windows


def ensure_ffmpeg() -> bool:
    """Check for ffmpeg; auto-install via winget if missing. Returns True if ready."""
    if _ffmpeg_in_path():
        return True
    print("\n  [!] ffmpeg not found. Attempting automatic install via winget...", flush=True)
    result = subprocess.run(
        ["winget", "install", "--id", "Gyan.FFmpeg", "-e",
         "--accept-source-agreements", "--accept-package-agreements"],
    )
    _reload_path_from_registry()
    if _ffmpeg_in_path():
        print("  [OK] ffmpeg installed and ready.", flush=True)
        return True
    print("\n  [ERROR] Could not find or install ffmpeg automatically.")
    print("  Please install manually and ensure it is in your PATH:")
    print("    winget install Gyan.FFmpeg")
    print("    or: https://ffmpeg.org/download.html")
    return False


def parse_timestamps(text: str) -> list[dict]:
    """Parse timestamp lines from any text block.

    The timestamp (MM:SS or H:MM:SS) may appear at the start or end of a
    line, optionally wrapped in brackets [ ] or ( ).  Any separator
    characters (-, |, –, —, etc.) adjacent to the timestamp are stripped.
    Lines with no title text are labeled 'Track N'.
    """
    TIME_PAT = r"\d{1,2}:\d{2}(?::\d{2})?"
    SEP      = r"[\s\-|–—•·]*"

    # Format A: [timestamp] SEP title  (timestamp at start of line)
    pat_a = re.compile(rf"^[\[(]?({TIME_PAT})[\])]?{SEP}(.*)$", re.MULTILINE)
    # Format B: title SEP [timestamp]  (timestamp at end of line)
    pat_b = re.compile(rf"^(.*?){SEP}[\[(]?({TIME_PAT})[\])]?\s*$", re.MULTILINE)

    def to_seconds(s: str) -> int:
        parts = list(map(int, s.split(":")))
        return parts[0] * 60 + parts[1] if len(parts) == 2 \
               else parts[0] * 3600 + parts[1] * 60 + parts[2]

    def _extract(matches, time_grp: int, title_grp: int) -> list[dict]:
        seen: set[int] = set()
        tracks = []
        n = 0
        for m in matches:
            secs = to_seconds(m.group(time_grp))
            if secs in seen:
                continue
            seen.add(secs)
            title = re.sub(rf"^{SEP}|{SEP}$", "", m.group(title_grp)).strip()
            n += 1
            tracks.append({"time": secs, "title": title or f"Track {n}"})
        tracks.sort(key=lambda x: x["time"])
        return tracks

    matches_a = list(pat_a.finditer(text))
    matches_b = list(pat_b.finditer(text))

    if len(matches_b) > len(matches_a):
        return _extract(matches_b, time_grp=2, title_grp=1)
    return _extract(matches_a, time_grp=1, title_grp=2)


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
    """Fetch full video metadata (no download) via yt_dlp Python module."""
    ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


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
    except Exception:
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
    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": str(dest / "raw_audio.%(ext)s"),
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
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
# Interactive mode  (no arguments — user double-clicked the exe)
# ---------------------------------------------------------------------------

def interactive_mode():
    """Full interactive CLI: ask URL, show track list, ask options, confirm, run."""
    sep  = "  " + "─" * 62
    sep2 = "  " + "═" * 62

    print()
    print(sep2)
    print("   YouTube Audio Downloader & Splitter")
    print(sep2)
    print()

    # ── URL ──────────────────────────────────────────────────────────────
    while True:
        url = input("  YouTube URL : ").strip()
        if url:
            break
        print("  [!] Please enter a URL.")

    # ── Fetch info + show track list ─────────────────────────────────────
    print()
    print("  Fetching video info...", flush=True)
    try:
        info = fetch_video_info(url)
    except Exception:
        print("  [ERROR] Could not access the video. Check the URL and your connection.")
        input("\n  Press Enter to exit.")
        sys.exit(1)

    title    = info.get("title", "Unknown")
    slug     = slug_from_title(title)
    duration = int(info.get("duration") or 0)
    tracks   = extract_tracks(info)

    print()
    print(f"  Title    : {title}")
    print(f"  Duration : {seconds_to_hms(duration)}")
    print()

    if not tracks:
        print("  [!] No timestamps found in chapters or description.")
        input("\n  Press Enter to exit.")
        sys.exit(1)

    print(f"  {len(tracks)} tracks found:")
    print(sep)
    for i, t in enumerate(tracks):
        end_t  = tracks[i + 1]["time"] if i + 1 < len(tracks) else duration
        dur_s  = end_t - t["time"]
        start_fmt = f"{t['time'] // 60:02d}:{t['time'] % 60:02d}"
        dur_fmt   = f"{dur_s // 60:02d}:{dur_s % 60:02d}"
        print(f"  {i + 1:02d}.  {start_fmt}  ({dur_fmt})  {t['title']}")
    print(sep)
    print()

    # ── Output folder ─────────────────────────────────────────────────────
    print(f"  Suggested folder name : {slug}")
    subfolder = input("  Output folder (Enter = use suggestion) : ").strip()
    if not subfolder:
        subfolder = slug
    output_dir = Path(subfolder)

    # ── Format ────────────────────────────────────────────────────────────
    print()
    print("  Audio format:")
    print("    [1]  MP3  (recommended)")
    print("    [2]  OGG  (open format)")
    fmt_choice = input("  Choice [1/2] (Enter = MP3) : ").strip()
    fmt = "ogg" if fmt_choice == "2" else "mp3"

    # ── Quality ───────────────────────────────────────────────────────────
    print()
    print("  Audio quality:")
    print("    [1]  320 kbps  (recommended)")
    print("    [2]  192 kbps")
    print("    [3]  128 kbps")
    print("    [4]   96 kbps")
    q_choice = input("  Choice [1-4] (Enter = 320 kbps) : ").strip()
    bitrate_map = {"2": 192, "3": 128, "4": 96}
    bitrate = bitrate_map.get(q_choice, 320)

    # ── Confirm ───────────────────────────────────────────────────────────
    print()
    print(sep)
    print(f"  URL     : {url}")
    print(f"  Output  : {output_dir.resolve()}")
    print(f"  Format  : {fmt.upper()} @ {bitrate} kbps")
    print(f"  Tracks  : {len(tracks)}")
    print(sep)
    print()
    confirm = input("  Start download? [Y/n] : ").strip().lower()
    if confirm == "n":
        print("  Cancelled.")
        input("\n  Press Enter to exit.")
        sys.exit(0)

    # ── ffmpeg ────────────────────────────────────────────────────────────
    if not ensure_ffmpeg():
        input("\n  Press Enter to exit.")
        sys.exit(1)

    # ── Run ───────────────────────────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_file    = download_audio(url, output_dir)
    track_files = split_audio(raw_file, tracks, output_dir,
                               fmt=fmt, bitrate=bitrate, duration=duration)
    raw_file.unlink(missing_ok=True)

    print("  [3/3] Creating VLC playlist...")
    playlist_path = output_dir / "playlist.m3u"
    create_m3u_playlist(track_files, playlist_path)
    print_recap(track_files, playlist_path, fmt, bitrate)

    input("  Press Enter to exit.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download and split a YouTube video into individual audio tracks."
    )
    parser.add_argument("--url",        default=None)
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

    # No arguments at all → interactive mode (user double-clicked the exe)
    if args.url is None and not args.show_info:
        interactive_mode()
        return

    if not args.no_dep_check and not args.show_info:
        if not ensure_ffmpeg():
            sys.exit(1)

    if args.show_info:
        if not args.url:
            print("[ERROR] --show-info requires --url")
            sys.exit(1)
        cmd_show_info(args.url)
        return

    if not args.url:
        print("[ERROR] --url is required when using CLI flags.")
        sys.exit(1)

    # ── Fetch metadata ─────────────────────────────────────────────────────
    print("\n  Fetching metadata...", flush=True)
    try:
        info = fetch_video_info(args.url)
    except Exception:
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
