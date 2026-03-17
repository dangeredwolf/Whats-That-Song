"""Audio processing: download, extract, and recognize with Shazam."""

import asyncio
import mimetypes
import os
import re
import tempfile

import aiohttp
import yt_dlp as yt
from shazamio import Shazam

from config import HEADERS, TWITTER_LINK_REGEX

# Initialize
mimetypes.init()
shazam = Shazam()

# Pattern for start time: "90", "1:30", "1:30:45"
_START_TIME_REGEX = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+)$")


def parse_start_time(value: str | None) -> int | None:
    """Parse start time string to seconds. Supports '90', '1:30', '1:30:45'."""
    if not value or not value.strip():
        return None
    value = value.strip()
    match = _START_TIME_REGEX.match(value)
    if not match:
        return None
    parts = match.groups()
    # parts: (hours or None, minutes or None, seconds)
    if parts[0] is not None and parts[1] is not None:
        # H:MM:SS
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if parts[0] is not None:
        # MM:SS
        return int(parts[0]) * 60 + int(parts[2])
    # SS
    return int(parts[2])


def _ytdl_filter(info):
    if info.get("is_live"):
        return "WTS cannot process currently live streams"
    if info.get("duration", 0) > 3600:
        return "WTS cannot process videos longer than 60 minutes"
    return None


def _make_ytdl(tmpdir: str) -> yt.YoutubeDL:
    return yt.YoutubeDL(
        {
            "format": "worstaudio/worst",
            "outtmpl": os.path.join(tmpdir, "%(id)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "nopostoverwrites": True,
                }
            ],
            "noplaylist": True,
            "match_filter": _ytdl_filter,
            "quiet": True,
            "no_warnings": True,
        }
    )


def should_direct_download(url: str) -> bool:
    """Check if URL points to a direct media file."""
    url_lower = url.lower()
    guessed = mimetypes.guess_type(url_lower)[0]
    if guessed:
        return guessed.startswith("video/") or guessed.startswith("audio/")
    return False


async def process_direct_video(url: str, start_time: int = 0):
    """Download video/audio directly and process with Shazam."""
    print(f"Processing direct video: {url}" + (f" (from {start_time}s)" if start_time else ""))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=HEADERS) as resp:
                if resp.status != 200:
                    print(f"Failed to download: HTTP {resp.status}")
                    return {"timestamp": None, "track": None}

                video_data = await resp.read()

        with tempfile.NamedTemporaryFile(suffix=".media", delete=False) as tmp:
            tmp.write(video_data)
            tmp_path = tmp.name

        try:
            ffmpeg_args = [
                "ffmpeg",
                "-y",
                "-loglevel", "error",
            ]
            if start_time > 0:
                ffmpeg_args.extend(["-ss", str(start_time)])
            ffmpeg_args.extend([
                "-i", tmp_path,
                "-t", "180",
                "-vn",
                "-acodec", "libmp3lame",
                "-f", "mp3",
                "pipe:1",
            ])

            proc = await asyncio.create_subprocess_exec(
                *ffmpeg_args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            audio_data, stderr = await proc.communicate()

            if proc.returncode != 0:
                print(f"FFmpeg extraction failed: {stderr.decode(errors='replace')}")
                return {"timestamp": None, "track": None}

            print(f"Recognizing music from {url}")
            return await shazam.recognize(audio_data)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    except Exception as e:
        print(f"Error processing video: {e}")
        return {"timestamp": None, "track": None}


async def process_twitter(url: str, start_time: int = 0):
    """Process Twitter/X video via fxtwitter API."""
    print(f"Processing Twitter link: {url}")
    tweet_id = url.split("/")[-1]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://api.fxtwitter.com/status/{tweet_id}",
                headers=HEADERS,
            ) as resp:
                if resp.status != 200:
                    return {"timestamp": None, "track": None}

                data = await resp.json()
                tweet = data.get("tweet")
                if not tweet:
                    return {"timestamp": None, "track": None}

                media = tweet.get("media")
                if not media:
                    return {"timestamp": None, "track": None}

                videos = media.get("videos")
                if not videos or len(videos) == 0:
                    return {"timestamp": None, "track": None}

                video_url = videos[0].get("url")
                if not video_url:
                    return {"timestamp": None, "track": None}

                print(f"Found Twitter video URL: {video_url}")
                return await process_direct_video(video_url, start_time)

    except Exception as e:
        print(f"Error processing Twitter link: {e}")
        return {"timestamp": None, "track": None}


async def process_ytdl(url: str, start_time: int = 0):
    """Process URL via yt-dlp."""
    print(f"Processing with yt-dlp: {url}" + (f" (from {start_time}s)" if start_time else ""))

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ytdl = _make_ytdl(tmpdir)
            info = ytdl.extract_info(url, download=True)

            if not info:
                return {"timestamp": None, "track": None}

            requested_downloads = info.get("requested_downloads")
            if requested_downloads and len(requested_downloads) > 0:
                filepath = requested_downloads[0].get("filepath")

                if filepath and os.path.exists(filepath):
                    print(f"Downloaded to: {filepath}")

                    if start_time > 0:
                        proc = await asyncio.create_subprocess_exec(
                            "ffmpeg",
                            "-ss", str(start_time),
                            "-i", filepath,
                            "-t", "180",
                            "-vn",
                            "-acodec", "libmp3lame",
                            "-f", "mp3",
                            "pipe:1",
                            "-y",
                            "-loglevel", "error",
                            stdin=asyncio.subprocess.DEVNULL,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        audio_data, stderr = await proc.communicate()
                        if proc.returncode != 0:
                            print(f"FFmpeg extraction failed: {stderr.decode(errors='replace')}")
                            return {"timestamp": None, "track": None}
                    else:
                        with open(filepath, "rb") as f:
                            audio_data = f.read()

                    return await shazam.recognize(audio_data)

        return {"timestamp": None, "track": None}

    except Exception as e:
        print(f"Error processing with yt-dlp: {e}")
        return {"timestamp": None, "track": None}


async def process_media(url: str, start_time: int = 0):
    """Route media processing based on URL type."""
    if TWITTER_LINK_REGEX.match(url):
        return await process_twitter(url, start_time)

    if should_direct_download(url):
        return await process_direct_video(url, start_time)

    return await process_ytdl(url, start_time)
