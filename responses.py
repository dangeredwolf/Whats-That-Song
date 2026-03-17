"""Discord Components V2 response builders."""

import random
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import discord
from discord.http import Route

from config import COMPONENTS_V2_FLAG, RANDOM_MESSAGES
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


async def _send_components_v2(
    ctx: discord.Interaction | discord.Message,
    components: list[dict[str, Any]],
    ephemeral: bool = False,
) -> None:
    """Send a Components V2 payload via raw HTTP.

    discord.py's high-level helpers don't expose the MESSAGE_COMPONENTS_V2 flag
    (1 << 15), so we construct the request manually.

    For interactions the caller must have already deferred so this always hits
    the followup webhook endpoint.  For plain messages it POSTs to the channel
    messages endpoint with a reply reference.
    """
    flags = COMPONENTS_V2_FLAG
    if ephemeral:
        flags |= 1 << 6  # EPHEMERAL

    if isinstance(ctx, discord.Interaction):
        route = Route(
            "POST",
            f"/webhooks/{ctx.application_id}/{ctx.token}",
        )
        await ctx.client.http.request(route, json={"components": components, "flags": flags})
    else:
        payload: dict[str, Any] = {
            "components": components,
            "flags": COMPONENTS_V2_FLAG,  # ephemeral is meaningless for channel messages
            "message_reference": {"message_id": str(ctx.id)},
            "allowed_mentions": {"replied_user": True},
        }
        route = Route("POST", "/channels/{channel_id}/messages", channel_id=ctx.channel.id)
        await ctx._state.http.request(route, json=payload)


async def _edit_original_response_v2(
    interaction: discord.Interaction,
    components: list[dict[str, Any]],
    ephemeral: bool = False,
) -> None:
    """Edit the original (deferred) interaction response with Components V2."""
    flags = COMPONENTS_V2_FLAG
    if ephemeral:
        flags |= 1 << 6  # EPHEMERAL
    route = Route(
        "PATCH",
        f"/webhooks/{interaction.application_id}/{interaction.token}/messages/@original",
    )
    await interaction.client.http.request(route, json={"components": components, "flags": flags})


# Tips shown during voice listening
LISTEN_TIPS = [
    "Turn off noise suppression (Krisp, NVIDIA Broadcast, Apple Voice Isolation)",
    "Turn up voice sensitivity or use push-to-talk",
    "Hold your speaker or phone closer to the microphone",
    "If possible, try a more recognizable part of the song (chorus, drop, etc.)"
]
# Error tips for match (file/URL) - no match
MATCH_ERROR_TIPS = [
    "If the song starts later, try the start_time parameter in /match",
    "Loud voiceovers can make it hard to recognize music.",
    "The song may not be in Shazam's database.",
    "If possible, try a more recognizable part of the song (chorus, drop, etc.)"
]


_BAR_WIDTH = 15
_BAR_WINDOW = 5
_BAR_BOUNCE = _BAR_WIDTH - _BAR_WINDOW  # 15 positions
_BAR_STEP = 3  # Positions to jump per sample (faster, less granular)


def build_listening_components(
    seconds_left: float,
    stop_custom_id: str,
    sample_num: int = 0,
    tips: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build Components V2 payload for the listening-in-progress UI."""

    tips = tips or LISTEN_TIPS
    tip_text = "\n".join(f"• {t}" for t in tips[:3])

    # Indeterminate bouncing bar driven by sample_num (steps by _BAR_STEP for faster motion)
    cycle = _BAR_BOUNCE * 2
    step = (sample_num * _BAR_STEP) % cycle
    pos = step if step <= _BAR_BOUNCE else cycle - step
    # Use ◐/◑ (half-circles) at the ends for a pill-shaped appearance
    filled = ("<:leftbar:1483317410143539360>" + "<:centerbar:1483317425398218936>" * (_BAR_WINDOW - 2) + "<:rightbar:1483317447028379730>")
    bar = "<:transbar:1483317456838594610>" * pos + filled + "<:transbar:1483317456838594610>" * (_BAR_BOUNCE - pos)
    seconds_display = round(seconds_left)

    content = (
        f"# Listening for music…\n\n"
        f"{bar} **{seconds_display}s**\n\n"
        f"**Pro tips:**\n{tip_text}"
    )

    container = {
        "type": 17,
        "components": [
            {"type": 10, "content": content},
            {"type": 1, "components": [
                {"type": 2,
                    "style": 4,
                    "label": "Stop listening", 
                    "emoji": {"id": "1483310327587278919", "name": "Stop"},
                    "custom_id": stop_custom_id
                }
            ]},
        ],
    }
    return [container]


def build_stopped_components() -> list[dict[str, Any]]:
    """Build Components V2 payload for when the user stops listening early."""
    container = {
        "type": 17,
        "components": [
            {"type": 10, "content": "# Listening stopped\n\nYou stopped listening before we could identify the song. Use `/listen` again when you're ready."},
        ],
        "accent_color": 0x95A5A6,
    }
    return [container]


def build_components_v2_components(
    track_data: dict,
    spotify_url: str = None,
    youtube_url: str = None,
) -> list[dict[str, Any]] | None:
    """Return a Components V2 component list for a successful track match, or None."""

    # print out track data
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
    section_component: dict[str, Any] = {
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

    metadata_text.append(f"**Genre**: {track.get('genres', {}).get('primary', 'Unknown')}")

    if metadata_text:
        components.append({"type": 10, "content": "\n".join(metadata_text)})
        components.append({"type": 14})

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

    container = {"type": 17, "components": components, "accent_color": 0x3498DB}
    return [container]


def build_error_components(has_timestamp: bool, source: str = "match") -> list[dict[str, Any]]:
    """Return a Components V2 component list for a no-match or processing-error state.

    source: "listen" for /listen (voice channel), "match" for /match (file/URL).
    """
    if has_timestamp:
        if source == "listen":
            title = "No matches found"
            tips = LISTEN_TIPS
        else:
            title = "No matches found"
            tips = MATCH_ERROR_TIPS
        tip_text = "\n".join(f"• {t}" for t in tips[:4])
        description = (
            "We couldn't identify the song.\n\n"
            f"**Pro tips:**\n{tip_text}"
        )
        accent_color = 0xFFA500
    else:
        title = "Failed to process media"
        description = (
            "We tried processing the media you requested, but an error occurred somewhere along the way. "
            "Sorry about that.\n\n"
        )
        accent_color = 0xED4245

    container = {
        "type": 17,
        "components": [
            {"type": 10, "content": f"# {title}\n\n{description}"},
        ],
        "accent_color": accent_color,
    }
    return [container]


async def send_track_response(
    ctx_or_message: discord.Interaction | discord.Message,
    track_data: dict,
    ephemeral: bool = False,
    edit_instead: bool = False,
    source: str = "match",
) -> None:
    """Send a track response (success or error) to Discord.

    For interactions, the caller must have already deferred before calling this.
    If edit_instead is True and ctx is an Interaction, edits the original response instead of sending.
    source: "listen" for /listen (voice channel), "match" for /match (file/URL).
    """
    track = track_data.get("track")

    if not track:
        has_timestamp = track_data.get("timestamp") is not None
        components = build_error_components(has_timestamp, source=source)
        if edit_instead and isinstance(ctx_or_message, discord.Interaction):
            await _edit_original_response_v2(ctx_or_message, components, ephemeral=ephemeral)
        else:
            await _send_components_v2(ctx_or_message, components, ephemeral=ephemeral)
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
    components = build_components_v2_components(
        track_data, spotify_url=spotify_url, youtube_url=youtube_url
    )

    if not components:
        components = build_error_components(False, source=source)

    if edit_instead and isinstance(ctx_or_message, discord.Interaction):
        await _edit_original_response_v2(ctx_or_message, components, ephemeral=ephemeral)
    else:
        await _send_components_v2(ctx_or_message, components, ephemeral=ephemeral)
