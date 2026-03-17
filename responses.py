"""Discord Components V2 response builders."""

import random
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import discord

from config import RANDOM_MESSAGES
from audio import shazam
from spotify import search_spotify


def _extract_youtube_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    if not url:
        return None
    # youtube.com/watch?v=ID, youtu.be/ID, music.youtube.com/watch?v=ID
    parsed = urlparse(url)
    if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
        if parsed.path == "/watch" and parsed.query:
            qs = parse_qs(parsed.query)
            return qs.get("v", [None])[0]
        if parsed.path.startswith("/watch/"):
            return parsed.path.split("/")[-1]
        if "youtu.be" in parsed.netloc and parsed.path:
            return parsed.path.lstrip("/").split("?")[0]
    return None


class _RawComponentsV2View(discord.ui.View):
    """Wraps a raw Components V2 dict list so it can be passed via py-cord's view= API."""

    def __init__(self, components: list[dict[str, Any]]):
        super().__init__(timeout=None)
        self._raw_components = components

    def to_components(self) -> list[dict[str, Any]]:
        return self._raw_components

    def is_components_v2(self) -> bool:
        return True

    def is_finished(self) -> bool:
        return True

    def is_dispatchable(self) -> bool:
        return False


def build_components_v2_response(
    track_data: dict,
    spotify_url: str = None,
    youtube_url: str = None,
):
    """Build a Components V2 response for a successful track match."""
    track = track_data.get("track")
    if not track:
        return None

    title = track.get("title", "Unknown")
    artist = track.get("subtitle", "Unknown Artist")
    images = track.get("images", {})
    cover_url = images.get("coverarthq") if images else None
    sections = track.get("sections", [])
    hub = track.get("hub", {})

    message = random.choice(RANDOM_MESSAGES)
    components = []

    section_text = f"## {title}\n### {artist}"
    section_component = {
        "type": 9,
        "components": [{"type": 10, "content": section_text}],
    }

    if cover_url:
        section_component["accessory"] = {
            "type": 11,
            "media": {"url": cover_url},
        }

    components.append(section_component)
    components.append({"type": 14})

    metadata_text = []
    for section in sections:
        section_metadata = section.get("metadata")
        if section_metadata:
            for item in section_metadata:
                field_title = item.get("title", "")
                field_text = item.get("text", "")
                if field_title and field_text:
                    metadata_text.append(f"**{field_title}**: {field_text}")

    if metadata_text:
        components.append({"type": 10, "content": "\n".join(metadata_text)})
        components.append({"type": 14})

    # Italic muted message near the buttons
    components.append({"type": 10, "content": f"*{message}*"})

    buttons = []

    if spotify_url:
        buttons.append({
            "type": 2, "style": 5, "label": "Spotify", "url": spotify_url,
            "emoji": {"id": "1014768475593506836", "name": "Spotify"},
        })

    apple_url = None
    hub_options = hub.get("options", [])
    for option in hub_options:
        provider_name = option.get("providername")
        if provider_name == "applemusic":
            actions = option.get("actions", [])
            if actions:
                url = actions[0].get("uri", "")
                if url and url.startswith("https://") and "subscribe" not in url:
                    apple_url = url
                    break

    if apple_url:
        buttons.append({
            "type": 2, "style": 5, "label": "Apple Music", "url": apple_url,
            "emoji": {"id": "1014769073277640765", "name": "Apple Music"},
        })

    if youtube_url and (video_id := _extract_youtube_video_id(youtube_url)):
        yt_music_url = f"https://music.youtube.com/watch?v={video_id}"
    else:
        query = quote(f"{title} {artist}")
        yt_music_url = f"https://music.youtube.com/search?q={query}"
    buttons.append({
        "type": 2, "style": 5, "label": "YouTube Music", "url": yt_music_url,
        "emoji": {"id": "1016942966012661762", "name": "YouTube Music"},
    })

    if buttons:
        components.append({"type": 1, "components": buttons})

    # Blue accent for successful match
    container = {"type": 17, "components": components, "accent_color": 0x3498DB}
    return {"view": _RawComponentsV2View([container])}


def build_error_response(has_timestamp: bool):
    """Build error response using Components V2."""
    if has_timestamp:
        title = "No matches found"
        description = (
            "We searched your media for a matching song, and couldn't find anything.\n\n"
            "**What are common causes for this?**\n"
            "• There is no music in the first few minutes of the media (we can only send so much data to Shazam)\n"
            "• Loud voiceovers can make it harder to recognize music\n"
            "• The song is not in Shazam's database"
        )
        # Orange accent for no match
        accent_color = 0xFFA500
    else:
        title = "Failed to process media"
        description = (
            "We tried processing the media you requested, but an error occurred somewhere along the way. "
            "Sorry about that.\n\n"
            "**What are common causes for this?**\n"
            "• You tried processing media longer than 1 hour\n"
            "• You tried processing a currently active live stream\n"
            "• You uploaded a corrupt media file, or one not supported by FFmpeg."
        )
        # Red accent for processing error
        accent_color = 0xED4245

    container = {
        "type": 17,
        "components": [
            {"type": 10, "content": f"# {title}\n\n{description}"},
        ],
        "accent_color": accent_color,
    }

    return {"view": _RawComponentsV2View([container])}


async def send_track_response(ctx_or_message, track_data: dict, ephemeral: bool = False):
    """Send a track response (success or error) to Discord."""
    track = track_data.get("track")

    if not track:
        has_timestamp = track_data.get("timestamp") is not None
        response = build_error_response(has_timestamp)

        if isinstance(ctx_or_message, discord.ApplicationContext):
            if ctx_or_message.response.is_done():
                await ctx_or_message.followup.send(**response, ephemeral=ephemeral)
            else:
                await ctx_or_message.respond(**response, ephemeral=ephemeral)
        else:
            await ctx_or_message.reply(**response)
        return

    title = track.get("title", "Unknown")
    artist = track.get("subtitle", "Unknown Artist")

    print(f"Found track: {title} by {artist}")

    youtube_url = None
    youtube_link = track.get("sections") and next(
        (s.get("youtubeurl") for s in track["sections"] if s.get("type") == "VIDEO"),
        None,
    )
    if youtube_link:
        try:
            youtube_data = await shazam.get_youtube_data(link=youtube_link)
            for action in youtube_data.get("actions") or []:
                if isinstance(action, dict) and action.get("uri"):
                    youtube_url = action["uri"]
                    break
            if not youtube_url and _extract_youtube_video_id(youtube_link):
                youtube_url = youtube_link
        except Exception as e:
            print(f"Failed to fetch YouTube data: {e}")
            if _extract_youtube_video_id(youtube_link):
                youtube_url = youtube_link

    spotify_url = await search_spotify(artist, title)
    response = build_components_v2_response(
        track_data, spotify_url=spotify_url, youtube_url=youtube_url
    )

    if not response:
        response = build_error_response(False)

    if isinstance(ctx_or_message, discord.ApplicationContext):
        if ctx_or_message.response.is_done():
            await ctx_or_message.followup.send(**response, ephemeral=ephemeral)
        else:
            await ctx_or_message.respond(**response, ephemeral=ephemeral)
    else:
        await ctx_or_message.reply(**response)
