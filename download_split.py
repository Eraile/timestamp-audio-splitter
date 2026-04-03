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
import urllib.request
import urllib.parse
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

VIDEO_QUALITIES = {
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "2160": "bestvideo[height<=2160][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "1440": "bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360":  "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]",
}


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

def fetch_video_info(url: str, with_comments: bool = False) -> dict:
    """Fetch full video metadata (no download) via yt_dlp Python module."""
    ydl_opts = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if with_comments:
        ydl_opts["getcomments"] = True
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def extract_tracks_from_comments(info: dict, top_n: int = 30) -> list[dict]:
    """Search the most-liked comments for a timestamp list (needs ≥ 3 entries)."""
    comments = info.get("comments") or []
    ranked = sorted(comments, key=lambda c: c.get("like_count") or 0, reverse=True)
    for comment in ranked[:top_n]:
        tracks = parse_timestamps(comment.get("text") or "")
        if len(tracks) >= 3:
            return tracks
    return []


def extract_tracks(info: dict, url: str = None) -> "tuple[list[dict], str]":
    """Return (tracks, source) — checks chapters, description, then top comments."""
    chapters = info.get("chapters") or []
    if chapters:
        return (
            [{"time": int(ch["start_time"]), "title": ch["title"]} for ch in chapters],
            "YouTube chapters",
        )
    desc_tracks = parse_timestamps(info.get("description", ""))
    if desc_tracks:
        return desc_tracks, "video description"
    if url:
        print("  [i] No timestamps in chapters/description — scanning top comments...",
              flush=True)
        try:
            info_c = fetch_video_info(url, with_comments=True)
            comment_tracks = extract_tracks_from_comments(info_c)
            if comment_tracks:
                return comment_tracks, "viewer comment"
        except Exception:
            pass
    return [], "none"


def detect_url_type(url: str) -> str:
    """Returns 'playlist', 'video_in_playlist', or 'video'."""
    try:
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        has_list  = bool(params.get("list"))
        has_video = bool(params.get("v")) or "/shorts/" in url
        if has_list and not has_video:
            return "playlist"
        if has_list and has_video:
            return "video_in_playlist"
    except Exception:
        pass
    return "video"


def playlist_url_from(url: str) -> str:
    """Extract the list= param and return a clean playlist URL.
    yt-dlp needs this form to enumerate all entries; a watch?v=...&list=... URL
    is treated as a single video even with yes_playlist=True.
    """
    params   = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    list_ids = params.get("list", [])
    if list_ids:
        return f"https://www.youtube.com/playlist?list={list_ids[0]}"
    return url


def fetch_playlist_info(url: str) -> dict:
    """Fetch playlist title + flat entry list (no download)."""
    ydl_opts = {
        "quiet": True, "no_warnings": True,
        "extract_flat": True, "yes_playlist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


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
    tracks, ts_source = extract_tracks(info, url)
    sep      = "  " + "─" * 62

    print(f"  Title    : {title}")
    print(f"  Duration : {seconds_to_hms(duration)}")
    print()

    if tracks:
        print(f"  {len(tracks)} tracks found  (source: {ts_source}):")
        print(sep)
        for i, t in enumerate(tracks):
            end_t = tracks[i + 1]["time"] if i + 1 < len(tracks) else duration
            dur_s = end_t - t["time"]
            start_fmt = f"{t['time'] // 60:02d}:{t['time'] % 60:02d}"
            dur_fmt   = f"{dur_s // 60:02d}:{dur_s % 60:02d}"
            print(f"  {i + 1:02d}.  {start_fmt}  ({dur_fmt})  {t['title']}")
        print(sep)
    else:
        print("  [!] No timestamps found in chapters, description, or comments.")
        print("      You can provide a fallback .txt file via --timestamps")

    # Slug marker — must stay on the LAST line for bat capture
    print(f"\n__SLUG__={slug}", flush=True)


# ---------------------------------------------------------------------------
# Download + split
# ---------------------------------------------------------------------------

def download_audio(url: str, dest: Path) -> Path:
    print("\n  [1/4] Downloading audio...\n", flush=True)
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


def download_video(url: str, dest: Path, quality: str = "best") -> Path:
    """Download best available video+audio merged as MP4, capped at *quality* resolution."""
    print("\n  Downloading video...\n", flush=True)
    fmt_str = VIDEO_QUALITIES.get(quality, VIDEO_QUALITIES["best"])
    ydl_opts = {
        "format": fmt_str,
        "merge_output_format": "mp4",
        "outtmpl": str(dest / "%(title)s.%(ext)s"),
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    candidates = sorted(dest.glob("*.mp4"))
    if not candidates:
        print("[ERROR] Video download failed.")
        sys.exit(1)
    return candidates[0]


def download_playlist_video(url: str, dest: Path, quality: str = "best") -> list[Path]:
    """Download every video in a playlist as individual MP4 files."""
    print("\n  Downloading playlist videos...\n", flush=True)
    fmt_str = VIDEO_QUALITIES.get(quality, VIDEO_QUALITIES["best"])
    ydl_opts = {
        "format": fmt_str,
        "merge_output_format": "mp4",
        "outtmpl": str(dest / "%(playlist_index)02d - %(title)s.%(ext)s"),
        "yes_playlist": True,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return sorted(dest.glob("*.mp4"))


def download_playlist_audio(
    entries: list[dict],
    output_dir: Path,
    fmt: str,
    bitrate: int,
) -> list[Path]:
    """Download every playlist entry as audio into a single flat folder."""
    total        = len(entries)
    all_files:   list[Path] = []
    global_idx   = 0          # running track counter across all videos
    sep          = "  " + "─" * 62
    saved_cover  = output_dir / "cover.jpg"   # one shared cover for the folder

    for idx, entry in enumerate(entries, 1):
        vid_id  = entry.get("id") or ""
        vid_url = (entry.get("url") or entry.get("webpage_url")
                   or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None))
        if not vid_url:
            continue

        vid_title = entry.get("title") or f"Video {idx}"

        print(f"\n  ── [{idx}/{total}] {vid_title}")
        print(sep, flush=True)

        try:
            info = fetch_video_info(vid_url)
        except Exception:
            print("  [!] Skipped — could not fetch info.")
            continue

        duration = int(info.get("duration") or 0)
        print("  Scanning for timestamps...", flush=True)
        tracks, ts_source = extract_tracks(info, vid_url)

        if not tracks:
            tracks    = [{"time": 0, "title": sanitize_filename(vid_title)}]
            ts_source = "single track"
            print("  No timestamps — saving as one track.")
        else:
            print(f"  {len(tracks)} track(s) found  (from {ts_source})")

        # Cover: keep the first one as cover.jpg; embed per-video cover from a temp path
        temp_cover = output_dir / f"_cover_tmp_{idx}.jpg"
        cover_path = download_thumbnail(info, output_dir,
                                         dest_name=temp_cover.name)
        if cover_path and cover_path.exists() and not saved_cover.exists():
            cover_path.rename(saved_cover)
            cover_path = saved_cover

        try:
            raw_file = _download_audio_safe(vid_url, output_dir)
        except RuntimeError as e:
            print(f"  [!] Skipped — {e}")
            _cleanup_partial(output_dir)
            if temp_cover.exists():
                temp_cover.unlink(missing_ok=True)
            continue

        try:
            vid_files = split_audio(raw_file, tracks, output_dir,
                                     fmt=fmt, bitrate=bitrate,
                                     duration=duration, cover_path=cover_path,
                                     start_index=global_idx)
        except Exception as e:
            print(f"  [!] Skipped — split failed: {e}")
            _cleanup_partial(output_dir)
            continue
        finally:
            raw_file.unlink(missing_ok=True)
            if temp_cover.exists():
                temp_cover.unlink(missing_ok=True)

        global_idx += len(vid_files)
        all_files.extend(vid_files)

    return all_files

    return all_files


def _download_audio_safe(url: str, dest: Path) -> Path:
    """Like download_audio but raises RuntimeError instead of sys.exit on failure."""
    print("\n  Downloading audio...\n", flush=True)
    ydl_opts = {
        "format": "bestaudio",
        "outtmpl": str(dest / "raw_audio.%(ext)s"),
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    candidates = sorted(dest.glob("raw_audio.*"))
    if not candidates:
        raise RuntimeError("audio download failed")
    return candidates[0]


def _cleanup_partial(directory: Path):
    """Remove leftover yt-dlp .part files and raw_audio.* from a failed download."""
    for f in list(directory.glob("raw_audio.*")) + list(directory.glob("*.part")):
        f.unlink(missing_ok=True)


def download_thumbnail(info: dict, dest: Path,
                        dest_name: str = "cover.jpg") -> "Path | None":
    """Download the video thumbnail and save it as dest_name inside dest. Returns path or None."""
    thumb_url = info.get("thumbnail")
    if not thumb_url:
        return None
    raw_path   = dest / "_cover_raw"
    cover_path = dest / dest_name
    try:
        req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_path.write_bytes(resp.read())
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw_path), str(cover_path)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return cover_path
    except Exception:
        return None
    finally:
        raw_path.unlink(missing_ok=True)


def split_audio(
    source: Path,
    tracks: list[dict],
    output_dir: Path,
    fmt: str,
    bitrate: int,
    duration: int = 0,
    cover_path: "Path | None" = None,
    start_index: int = 0,
) -> list[Path]:
    total = len(tracks)
    print(f"\n  Splitting into {total} track(s) ({fmt.upper()} @ {bitrate} kbps)...\n")
    output_files = []

    for i, track in enumerate(tracks):
        start = track["time"]
        end   = tracks[i + 1]["time"] if i + 1 < len(tracks) else None
        title = sanitize_filename(track["title"])
        out_path = output_dir / f"{start_index + i + 1:02d} - {title}.{fmt}"

        label = title[:38] + ("…" if len(title) > 38 else "")
        sys.stdout.write(f"\r  {progress_bar(i + 1, total)}  {label:<40}")
        sys.stdout.flush()

        use_cover = cover_path is not None and cover_path.exists()

        cmd = ["ffmpeg", "-y", "-i", str(source)]
        if use_cover:
            cmd += ["-i", str(cover_path)]
        cmd += ["-ss", seconds_to_hms(start)]
        if end is not None:
            cmd += ["-to", seconds_to_hms(end)]
        if use_cover:
            cmd += ["-map", "0:a", "-map", "1:v:0"]
        if fmt == "mp3":
            cmd += ["-c:a", "libmp3lame", "-b:a", f"{bitrate}k"]
            if use_cover:
                cmd += ["-c:v", "mjpeg",
                        "-id3v2_version", "3",
                        "-metadata:s:v", "title=Album cover",
                        "-metadata:s:v", "comment=Cover (front)"]
        else:
            cmd += ["-c:a", "libvorbis", "-b:a", f"{bitrate}k"]
            if use_cover:
                cmd += ["-c:v", "copy"]
        cmd.append(str(out_path))
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output_files.append(out_path)

    sys.stdout.write(f"\r  {progress_bar(total, total)}  {'Splitting complete!':<40}\n\n")
    sys.stdout.flush()
    return output_files


def create_m3u_playlist(files: list[Path], playlist_path: Path):
    base = playlist_path.parent
    with open(playlist_path, "w", encoding="utf-8") as f:
        f.write("#EXTM3U\n\n")
        for fp in files:
            try:
                rel = fp.relative_to(base).as_posix()
            except ValueError:
                rel = fp.name
            f.write(f"#EXTINF:-1,{fp.stem}\n{rel}\n\n")


def print_recap(files: list[Path], playlist_path: Path, fmt: str, bitrate: int,
                cover_path: "Path | None" = None):
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
    if cover_path and cover_path.exists():
        print(f"  Cover art : {cover_path.name}  (embedded + saved)")
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

    # ── Playlist detection ───────────────────────────────────────────────
    url_type         = detect_url_type(url)
    is_playlist      = False
    playlist_entries = []
    n_videos         = 0
    slug             = ""
    info             = {}
    duration         = 0
    tracks: list[dict] = []
    ts_source        = "none"

    print()
    if url_type in ("playlist", "video_in_playlist"):
        print("  Fetching playlist info...", flush=True)
        try:
            plist_info = fetch_playlist_info(playlist_url_from(url))
        except Exception:
            print("  [ERROR] Could not access the playlist. Check the URL and your connection.")
            input("\n  Press Enter to exit.")
            sys.exit(1)

        playlist_entries = [e for e in (plist_info.get("entries") or []) if e]
        playlist_title   = plist_info.get("title", "Playlist")
        n_videos         = len(playlist_entries)
        slug             = slug_from_title(playlist_title)
        print()

        if url_type == "video_in_playlist":
            print(f"  This video is part of: {playlist_title}  ({n_videos} video(s))")
            print()
            print("  Download:")
            print("    [1]  Just this video")
            print(f"    [2]  Entire playlist  ({n_videos} videos)")
            is_playlist = input("  Choice [1/2] (Enter = just this video) : ").strip() == "2"
            print()
        else:
            print(f"  Playlist : {playlist_title}")
            print(f"  Videos   : {n_videos}")
            is_playlist = True
            print()

    # ── Fetch single-video info ──────────────────────────────────────────
    if not is_playlist:
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
        print()
        print(f"  Title    : {title}")
        print(f"  Duration : {seconds_to_hms(duration)}")
        print()

    # ── Mode ─────────────────────────────────────────────────────────────
    print("  Output mode:")
    print("    [1]  Audio tracks  (MP3 — recommended)")
    print("    [2]  Audio tracks  (OGG — open format)")
    print("    [3]  Full video    (MP4)")
    mode_choice   = input("  Choice [1/2/3] (Enter = MP3 audio) : ").strip()
    is_video_mode = mode_choice == "3"
    fmt           = "ogg" if mode_choice == "2" else "mp3"
    print()

    # ── Timestamps (single-video audio only) ─────────────────────────────
    if not is_playlist and not is_video_mode:
        print("  Scanning for timestamps...", flush=True)
        tracks, ts_source = extract_tracks(info, url)
        print()

        if not tracks:
            print("  [!] No timestamps found in chapters, description, or comments.")
            print()
            ans = input("  Download as a single full-length track? [Y/n] : ").strip().lower()
            if ans == "n":
                print("  Cancelled.")
                input("\n  Press Enter to exit.")
                sys.exit(0)
            title_safe = sanitize_filename(info.get("title", "Full Audio"))
            tracks    = [{"time": 0, "title": title_safe}]
            ts_source = "single track"
            print()

        print(f"  {len(tracks)} tracks found  (source: {ts_source}):")
        print(sep)
        for i, t in enumerate(tracks):
            end_t     = tracks[i + 1]["time"] if i + 1 < len(tracks) else duration
            dur_s     = end_t - t["time"]
            start_fmt = f"{t['time'] // 60:02d}:{t['time'] % 60:02d}"
            dur_fmt   = f"{dur_s // 60:02d}:{dur_s % 60:02d}"
            print(f"  {i + 1:02d}.  {start_fmt}  ({dur_fmt})  {t['title']}")
        print(sep)
        print()

    # ── Output folder ─────────────────────────────────────────────────────
    print(f"  Suggested folder name : {slug}")
    subfolder  = input("  Output folder (Enter = use suggestion) : ").strip()
    output_dir = Path(subfolder or slug)

    # ── Quality ───────────────────────────────────────────────────────────
    vq_key   = "best"
    vq_label = "best available"
    bitrate  = DEFAULT_BITRATE

    if is_video_mode:
        print()
        print("  Video quality:")
        print("    [1]  Best available  (recommended)")
        print("    [2]  4K   / 2160p")
        print("    [3]  2K   / 1440p")
        print("    [4]  1080p  (Full HD)")
        print("    [5]   720p  (HD)")
        print("    [6]   480p")
        print("    [7]   360p  (small file)")
        vq_ch    = input("  Choice [1-7] (Enter = best) : ").strip()
        vq_map   = {"2": "2160", "3": "1440", "4": "1080", "5": "720", "6": "480", "7": "360"}
        vq_key   = vq_map.get(vq_ch, "best")
        vq_label = "best available" if vq_key == "best" else f"up to {vq_key}p"
    else:
        print()
        print("  Audio quality:")
        print("    [1]  320 kbps  (recommended)")
        print("    [2]  192 kbps")
        print("    [3]  128 kbps")
        print("    [4]   96 kbps")
        q_ch    = input("  Choice [1-4] (Enter = 320 kbps) : ").strip()
        bitrate = {"2": 192, "3": 128, "4": 96}.get(q_ch, 320)

    # ── Confirm ───────────────────────────────────────────────────────────
    scope_label = f"playlist — {n_videos} videos" if is_playlist else "single video"
    print()
    print(sep)
    print(f"  URL    : {url}")
    print(f"  Output : {output_dir.resolve()}")
    if is_video_mode:
        print(f"  Format : MP4  ({vq_label})  [{scope_label}]")
    else:
        print(f"  Format : {fmt.upper()} @ {bitrate} kbps  [{scope_label}]")
        if not is_playlist:
            print(f"  Tracks : {len(tracks)}  (from {ts_source})")
    print(sep)
    print()
    if input("  Start download? [Y/n] : ").strip().lower() == "n":
        print("  Cancelled.")
        input("\n  Press Enter to exit.")
        sys.exit(0)

    # ── ffmpeg ────────────────────────────────────────────────────────────
    if not ensure_ffmpeg():
        input("\n  Press Enter to exit.")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ════════════════════════════════════════════════════════════════════
    # EXECUTE
    # ════════════════════════════════════════════════════════════════════
    if is_video_mode:
        if is_playlist:
            video_files   = download_playlist_video(playlist_url_from(url), output_dir, quality=vq_key)
            playlist_path = output_dir / "playlist.m3u"
            create_m3u_playlist(video_files, playlist_path)
            total_mb = sum(f.stat().st_size for f in video_files if f.exists()) / (1024 * 1024)
            print()
            print(sep2)
            print("  DONE")
            print(sep2)
            print(f"  Videos   : {len(video_files)}")
            print(f"  Quality  : {vq_label}")
            print(f"  Total    : {total_mb:.1f} MB")
            print(f"  Folder   : {output_dir.resolve()}")
            print(f"  Playlist : playlist.m3u  (open with VLC)")
            print(sep2)
        else:
            video_file = download_video(url, output_dir, quality=vq_key)
            size_mb    = video_file.stat().st_size / (1024 * 1024)
            print()
            print(sep2)
            print("  DONE")
            print(sep2)
            print(f"  File    : {video_file.name}")
            print(f"  Quality : {vq_label}")
            print(f"  Size    : {size_mb:.1f} MB")
            print(f"  Folder  : {output_dir.resolve()}")
            print(sep2)
    else:
        if is_playlist:
            track_files   = download_playlist_audio(playlist_entries, output_dir, fmt, bitrate)
            playlist_path = output_dir / "playlist.m3u"
            create_m3u_playlist(track_files, playlist_path)
            total_mb = sum(f.stat().st_size for f in track_files if f.exists()) / (1024 * 1024)
            print()
            print(sep2)
            print("  SUMMARY")
            print(sep2)
            print(f"  Videos   : {n_videos}")
            print(f"  Tracks   : {len(track_files)}")
            print(f"  Format   : {fmt.upper()} @ {bitrate} kbps")
            print(f"  Total    : {total_mb:.1f} MB")
            print(f"  Folder   : {output_dir.resolve()}")
            print(f"  Playlist : playlist.m3u  (open with VLC)")
            print(sep2)
        else:
            raw_file   = download_audio(url, output_dir)
            print("  [2/4] Downloading thumbnail...", end=" ", flush=True)
            cover_path = download_thumbnail(info, output_dir)
            print("OK" if cover_path else "skipped", flush=True)
            track_files = split_audio(raw_file, tracks, output_dir,
                                       fmt=fmt, bitrate=bitrate, duration=duration,
                                       cover_path=cover_path)
            raw_file.unlink(missing_ok=True)
            print("  [4/4] Creating VLC playlist...")
            playlist_path = output_dir / "playlist.m3u"
            create_m3u_playlist(track_files, playlist_path)
            print_recap(track_files, playlist_path, fmt, bitrate, cover_path=cover_path)

    print()
    input("  Press Enter to exit.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Download and split a YouTube video into individual audio tracks."
    )
    parser.add_argument("--url",        default=None)
    parser.add_argument("--format",     choices=["mp3", "ogg", "mp4"], default=DEFAULT_FORMAT)
    parser.add_argument("--output",     default=None, help="Output directory")
    parser.add_argument("--timestamps", default=None,
                        help="Fallback .txt file with timestamps if YouTube has none")
    parser.add_argument("--bitrate",      type=int, default=DEFAULT_BITRATE,
                        choices=[320, 256, 192, 128, 96])
    parser.add_argument("--video-quality", default="best",
                        choices=list(VIDEO_QUALITIES.keys()),
                        help="Max resolution for MP4 mode: best, 2160, 1440, 1080, 720, 480, 360")
    parser.add_argument("--playlist",    action="store_true",
                        help="Force playlist mode (auto-detected for pure playlist URLs)")
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
    url_type     = detect_url_type(args.url)
    use_playlist = args.playlist or url_type == "playlist"

    if use_playlist:
        try:
            plist_info = fetch_playlist_info(playlist_url_from(args.url))
        except Exception:
            print("[ERROR] Could not access the playlist.")
            sys.exit(1)
        entries    = [e for e in (plist_info.get("entries") or []) if e]
        output_dir = Path(args.output) if args.output \
                     else Path(slug_from_title(plist_info.get("title", "playlist")))
        output_dir.mkdir(parents=True, exist_ok=True)

        if args.format == "mp4":
            video_files   = download_playlist_video(playlist_url_from(args.url), output_dir,
                                                     quality=args.video_quality)
            playlist_path = output_dir / "playlist.m3u"
            create_m3u_playlist(video_files, playlist_path)
            vq_label = "best available" if args.video_quality == "best" \
                       else f"up to {args.video_quality}p"
            print(f"\n  {len(video_files)} video(s) downloaded  ({vq_label})")
            print(f"  Folder   : {output_dir.resolve()}")
        else:
            track_files   = download_playlist_audio(entries, output_dir,
                                                     args.format, args.bitrate)
            playlist_path = output_dir / "playlist.m3u"
            create_m3u_playlist(track_files, playlist_path)
            total_mb = sum(f.stat().st_size for f in track_files if f.exists()) / (1024 * 1024)
            print(f"\n  {len(track_files)} track(s) from {len(entries)} video(s)  "
                  f"| {args.format.upper()} @ {args.bitrate} kbps  | {total_mb:.1f} MB")
            print(f"  Folder   : {output_dir.resolve()}")
        return

    # ── Single video ───────────────────────────────────────────────────────
    try:
        info = fetch_video_info(args.url)
    except Exception:
        print("[ERROR] Could not access the video.")
        sys.exit(1)

    # ── Output directory ───────────────────────────────────────────────────
    output_dir = Path(args.output) if args.output \
                 else Path(slug_from_title(info.get("title", "video")))
    output_dir.mkdir(parents=True, exist_ok=True)

    duration = int(info.get("duration") or 0)

    # ── Video mode ─────────────────────────────────────────────────────────
    if args.format == "mp4":
        video_file = download_video(args.url, output_dir,
                                    quality=args.video_quality)
        size_mb = video_file.stat().st_size / (1024 * 1024)
        vq_label = "best available" if args.video_quality == "best" else f"up to {args.video_quality}p"
        print(f"\n  Video saved : {video_file.name}  ({size_mb:.1f} MB, {vq_label})")
        print(f"  Folder      : {output_dir.resolve()}")
        return

    # ── Tracks ─────────────────────────────────────────────────────────────
    if args.timestamps:
        ts_file = Path(args.timestamps)
        if not ts_file.exists():
            print(f"[ERROR] Timestamps file not found: {ts_file}")
            sys.exit(1)
        tracks = parse_timestamps(ts_file.read_text(encoding="utf-8"))
    else:
        tracks, _ = extract_tracks(info, args.url)

    if not tracks:
        print("[ERROR] No timestamps found. Provide a fallback file via --timestamps")
        sys.exit(1)

    # ── Download → Split → Playlist ────────────────────────────────────────
    raw_file    = download_audio(args.url, output_dir)
    print("  [2/4] Downloading thumbnail...", end=" ", flush=True)
    cover_path  = download_thumbnail(info, output_dir)
    print("OK" if cover_path else "skipped", flush=True)
    track_files = split_audio(raw_file, tracks, output_dir,
                               fmt=args.format, bitrate=args.bitrate, duration=duration,
                               cover_path=cover_path)
    raw_file.unlink(missing_ok=True)

    print("  [4/4] Creating VLC playlist...")
    playlist_path = output_dir / "playlist.m3u"
    create_m3u_playlist(track_files, playlist_path)

    print_recap(track_files, playlist_path, args.format, args.bitrate, cover_path=cover_path)


if __name__ == "__main__":
    main()
