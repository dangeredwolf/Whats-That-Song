"""Voice channel listening and music recognition."""

import asyncio
import io
import os
from datetime import datetime
from typing import Awaitable, Callable

import discord.ext.voice_recv as voice_recv

from audio import shazam

SAMPLE_INTERVAL = 2
MAX_SAMPLES = 15
TOTAL_LISTEN_SECONDS = SAMPLE_INTERVAL * MAX_SAMPLES  # 30 seconds

# How often (in seconds) the listening UI is refreshed. Independent of the audio
# sample rate — increase if you hit Discord rate limits, decrease for snappier animation.
UI_UPDATE_INTERVAL = 0.1

# Set to a directory path to save debug output (raw PCM + MP3). Example: "debug_voice"
DEBUG_SAVE_VOICE_DIR: str | None = None#"debug_voice"


class _PerUserPCMSink(voice_recv.AudioSink):
    """Writes decoded PCM into per-user BytesIO buffers.

    Accepts an existing buffers dict so audio accumulates across successive
    listen windows without re-creating the dict.
    """

    def __init__(self, buffers: dict[int, io.BytesIO]) -> None:
        super().__init__()
        self._buffers = buffers

    def wants_opus(self) -> bool:
        return False

    def write(self, user, data: voice_recv.VoiceData) -> None:
        if user is None or not data.pcm:
            return
        uid = user.id
        if uid not in self._buffers:
            self._buffers[uid] = io.BytesIO()
        self._buffers[uid].write(data.pcm)

    def cleanup(self) -> None:
        pass


async def _pcm_to_mp3(pcm: bytes) -> bytes | None:
    """Convert raw 48 kHz stereo 16-bit LE PCM to MP3 via ffmpeg.

    Matches the audio format used by the /match pipeline, which is what
    ShazamIO's fingerprinting engine is tuned to handle.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y", "-loglevel", "error",
        "-f", "s16le", "-ar", "48000", "-ac", "2",
        "-i", "pipe:0",
        "-acodec", "libmp3lame",
        "-f", "mp3", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    audio_data, stderr = await proc.communicate(input=pcm)
    if proc.returncode != 0:
        print(f"FFmpeg PCM→MP3 failed: {stderr.decode(errors='replace')}")
        return None
    return audio_data


async def listen_and_recognize(
    vc: voice_recv.VoiceRecvClient,
    *,
    stop_event: asyncio.Event | None = None,
    progress_callback: Callable[[int, float], Awaitable[None]] | None = None,
    ui_update_interval: float = UI_UPDATE_INTERVAL,
) -> dict:
    """Sample audio from a voice channel and recognise with Shazam.

    Accumulates PCM per-user across all windows so that each successive attempt
    gives Shazam more context.  Audio is converted to MP3 before each recognition
    call to match the /match pipeline.

    Returns a dict shaped like process_media's output: {"timestamp": ..., "track": ...}.
    Returns early on the first match, or a no-match result after all samples.
    If stop_event is set, returns early with {"timestamp": None, "track": None, "stopped": True}.

    progress_callback(frame, seconds_left) is called on a separate task at
    ui_update_interval, independent of the audio sample rate.
    """
    accumulated_buffers: dict[int, io.BytesIO] = {}

    async def _ui_loop() -> None:
        loop = asyncio.get_running_loop()
        start = loop.time()
        frame = 0
        while True:
            seconds_left = max(0.0, TOTAL_LISTEN_SECONDS - (loop.time() - start))
            try:
                await progress_callback(frame, seconds_left)
            except Exception as e:
                print(f"UI update error: {e}")
            frame += 1
            await asyncio.sleep(ui_update_interval)

    ui_task = asyncio.create_task(_ui_loop()) if progress_callback else None

    try:
        for i in range(MAX_SAMPLES):
            if stop_event and stop_event.is_set():
                print("Listening stopped by user")
                return {"timestamp": None, "track": None, "stopped": True}

            if not vc.is_connected():
                print("Voice connection lost during listening")
                return {"timestamp": None, "track": None}

            sink = _PerUserPCMSink(accumulated_buffers)
            vc.listen(sink)
            await asyncio.sleep(SAMPLE_INTERVAL)
            vc.stop_listening()

            if stop_event and stop_event.is_set():
                print("Listening stopped by user")
                return {"timestamp": None, "track": None, "stopped": True}

            for uid, buf in list(accumulated_buffers.items()):
                pcm = buf.getvalue()
                if len(pcm) < 1000:
                    continue

                print(
                    f"Sample {i + 1}/{MAX_SAMPLES}: recognizing user {uid} "
                    f"({len(pcm):,} cumulative PCM bytes)"
                )

                try:
                    mp3_data = await _pcm_to_mp3(pcm)
                    if not mp3_data:
                        continue

                    if DEBUG_SAVE_VOICE_DIR:
                        os.makedirs(DEBUG_SAVE_VOICE_DIR, exist_ok=True)
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        pcm_path = os.path.join(DEBUG_SAVE_VOICE_DIR, f"user_{uid}_sample{i+1}_{ts}.raw")
                        mp3_path = os.path.join(DEBUG_SAVE_VOICE_DIR, f"user_{uid}_sample{i+1}_{ts}.mp3")
                        with open(pcm_path, "wb") as f:
                            f.write(pcm)
                        with open(mp3_path, "wb") as f:
                            f.write(mp3_data)
                        print(f"Debug: saved PCM ({len(pcm):,} bytes) and MP3 ({len(mp3_data):,} bytes) to {DEBUG_SAVE_VOICE_DIR}/")

                    result = await shazam.recognize(mp3_data)
                    if result.get("track"):
                        return result
                    print(f"No match yet (sample {i + 1}/{MAX_SAMPLES})")
                except Exception as e:
                    print(f"Shazam recognition failed for user {uid}: {e}")

        return {"timestamp": 0, "track": None}
    finally:
        if ui_task is not None:
            ui_task.cancel()
            try:
                await ui_task
            except asyncio.CancelledError:
                pass
        if vc.is_connected():
            await vc.disconnect()
