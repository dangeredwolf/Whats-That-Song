"""Voice channel listening and music recognition."""

import asyncio
import wave

import discord
from discord.opus import Decoder

from audio import shazam

SAMPLE_INTERVAL = 3
MAX_SAMPLES = 5
CONNECTION_WAIT_TIMEOUT = 10


class ListenWaveSink(discord.sinks.WaveSink):
    """WaveSink compatible with py-cord dev's new voice receive API."""

    __sink_listeners__: list[tuple[str, str]] = []

    def walk_children(self, with_self: bool = False):
        """Required by SinkEventRouter. We have no child sinks."""
        if with_self:
            yield self

    def is_opus(self) -> bool:
        """PacketDecoder expects this; we want PCM decoded to WAV."""
        return False

    def write(self, data, user):
        """Accept VoiceData from the new PacketRouter; base Sink expects (bytes, user_id)."""
        if hasattr(data, "pcm"):
            pcm = data.pcm
            user_id = getattr(user, "id", user) if user else 0
        else:
            pcm = data
            user_id = user
        super().write(pcm, user_id)

    def format_audio(self, audio):
        """Format using opus.Decoder constants; new VoiceClient has no .decoder attr."""
        is_recording = getattr(self.vc, "is_recording", None) if self.vc else None
        if is_recording and is_recording():
            raise discord.sinks.errors.WaveSinkError(
                "Audio may only be formatted after recording is finished."
            )
        data = audio.file
        pcm = data.getvalue()
        data.seek(0)
        data.truncate(0)
        with wave.open(data, "wb") as f:
            f.setnchannels(Decoder.CHANNELS)
            f.setsampwidth(Decoder.SAMPLE_SIZE // Decoder.CHANNELS)
            f.setframerate(Decoder.SAMPLING_RATE)
            f.writeframes(pcm)
        data.seek(0)
        audio.on_format(self.encoding)


async def _wait_until_connected(vc: discord.VoiceClient, timeout: float) -> bool:
    """Wait for the voice client to be fully connected, returning False on timeout."""
    for _ in range(int(timeout * 10)):
        if vc.is_connected():
            return True
        await asyncio.sleep(0.1)
    return False


async def listen_and_recognize(vc: discord.VoiceClient) -> dict:
    """Sample audio from a voice channel every 3 seconds (up to 15s) and recognize with Shazam.

    Returns the same dict shape as process_media: {"timestamp": ..., "track": ...}.
    Exits early on first match. Returns no-match result after all samples are exhausted.
    """
    try:
        if not await _wait_until_connected(vc, CONNECTION_WAIT_TIMEOUT):
            print("Voice connection failed: timed out waiting for connection")
            return {"timestamp": None, "track": None}

        for i in range(MAX_SAMPLES):
            if not vc.is_connected():
                print("Voice connection lost during recording")
                return {"timestamp": None, "track": None}

            sink = ListenWaveSink()
            sink.init(vc)
            done = asyncio.Event()

            def on_done(exception: Exception | None):
                done.set()

            vc.start_recording(sink, on_done)
            await asyncio.sleep(SAMPLE_INTERVAL)

            # if not vc.is_recording():
            #     print("Recording stopped unexpectedly")
            #     done.set()
            # else:
            #     vc.stop_recording()

            try:
                await asyncio.wait_for(done.wait(), timeout=5)
            except asyncio.TimeoutError:
                print("Timed out waiting for recording callback")

            try:
                sink.cleanup()
            except Exception as e:
                print(f"Sink cleanup failed: {e}")

            for user_id, audio in sink.audio_data.items():
                try:
                    data = audio.file.getvalue()
                    if len(data) < 1000:
                        continue
                    print(f"Recognizing sample {i + 1}/{MAX_SAMPLES} ({len(data)} bytes from user {user_id})")
                    result = await shazam.recognize(data)
                    if result.get("track"):
                        return result
                except Exception as e:
                    print(f"Shazam recognition failed for user {user_id}: {e}")
                    continue

        return {"timestamp": 0, "track": None}
    finally:
        if vc.is_connected():
            await vc.disconnect()
