"""What's That Song? - Discord bot entry point."""

import asyncio
import mimetypes
from typing import Optional

import discord
from discord import app_commands
import discord.ext.voice_recv as voice_recv

from audio import parse_start_time, process_media, should_direct_download
from config import DISCORD_TOKEN, LINK_REGEX, TWITTER_LINK_REGEX
from responses import (
    _edit_original_response_v2,
    _send_components_v2,
    build_error_components,
    build_listening_components,
    build_stopped_components,
    send_track_response,
)
from voice import TOTAL_LISTEN_SECONDS, UI_UPDATE_INTERVAL, listen_and_recognize

# Maps interaction_id -> asyncio.Event for /listen stop button
_listen_stop_events: dict[str, asyncio.Event] = {}

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

intents = discord.Intents.default()
intents.messages = True
intents.voice_states = True

client = discord.AutoShardedClient(intents=intents)
tree = app_commands.CommandTree(client)


def _is_media_attachment(attachment: discord.Attachment) -> bool:
    """Check if attachment is video/audio. Uses content_type first, filename as fallback.

    Discord's content_type can be None for some formats (e.g. .mov, .gz), so we
    fall back to guessing from the filename extension.
    """
    content_type = attachment.content_type or ""
    if "video" in content_type or "audio" in content_type:
        return True
    guessed = mimetypes.guess_type(attachment.filename or "")[0]
    return bool(guessed and (guessed.startswith("video/") or guessed.startswith("audio/")))


@client.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {client.user.name} (ID: {client.user.id})")
    print("Ready to identify music!")
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="your music!",
        )
    )


@client.event
async def on_interaction(interaction: discord.Interaction):
    """Handle component interactions (e.g. Stop listening button)."""
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    if not custom_id.startswith("listen_stop:"):
        return

    interaction_id = custom_id.removeprefix("listen_stop:")
    event = _listen_stop_events.get(interaction_id)
    if event:
        event.set()

    await interaction.response.defer_update()


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild and client.user not in message.mentions:
        return

    if not message.content and not message.attachments and not message.embeds:
        return

    print(f"Processing message from {message.author.name}")

    for attachment in message.attachments:
        if _is_media_attachment(attachment):
            print(f"Found media attachment: {attachment.url}")
            async with message.channel.typing():
                result = await process_media(attachment.url)
                await send_track_response(message, result)
            return

    for embed in message.embeds:
        if embed.url:
            if should_direct_download(embed.url):
                print(f"Found media embed: {embed.url}")
                async with message.channel.typing():
                    result = await process_media(embed.url)
                    await send_track_response(message, result)
                return
            elif TWITTER_LINK_REGEX.match(embed.url):
                print(f"Found Twitter embed: {embed.url}")
                async with message.channel.typing():
                    result = await process_media(embed.url)
                    await send_track_response(message, result)
                return

    links = LINK_REGEX.findall(message.content)
    if links:
        url = links[0]
        print(f"Found URL in message: {url}")
        async with message.channel.typing():
            result = await process_media(url)
            await send_track_response(message, result)
        return


@tree.command(name="match", description="Identify a song from a file or URL")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    file="Audio or video file",
    url="URL to audio/video or a page containing media",
    start_time="Start matching at this time (e.g. 90, 1:30, 1:30:45)",
)
async def match_command(
    interaction: discord.Interaction,
    file: Optional[discord.Attachment] = None,
    url: Optional[str] = None,
    start_time: Optional[str] = None,
):
    if not file and not url:
        await interaction.response.send_message(
            "Please provide either a file or a URL to identify.",
            ephemeral=True,
        )
        return

    start_seconds = parse_start_time(start_time)
    if start_time is not None and start_time.strip() and start_seconds is None:
        await interaction.response.send_message(
            "Invalid start time. Use seconds (e.g. 90), minutes:seconds (e.g. 1:30), "
            "or hours:minutes:seconds (e.g. 1:30:45).",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    if file:
        print(f"Processing attachment from /match: {file.url}")
        result = await process_media(file.url, start_seconds or 0)
    else:
        print(f"Processing URL from /match: {url}")
        result = await process_media(url, start_seconds or 0)

    await send_track_response(interaction, result)


@tree.command(
    name="listen",
    description="Join your voice channel and identify music playing (listens up to 30 seconds)",
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True)
async def listen_command(interaction: discord.Interaction):
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(
            "You need to be in a voice channel to use this command.",
            ephemeral=True,
        )
        return

    if interaction.guild.voice_client is not None:
        await interaction.response.send_message(
            "I'm already in a voice channel. Please wait for me to finish or disconnect me first.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    try:
        vc = await interaction.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
    except Exception as e:
        print(f"Failed to connect to voice channel: {e}")
        await send_track_response(
            interaction, {"timestamp": None, "track": None}, edit_instead=True, source="listen"
        )
        return

    stop_event = asyncio.Event()
    stop_custom_id = f"listen_stop:{interaction.id}"
    _listen_stop_events[str(interaction.id)] = stop_event

    async def update_listening_ui(frame: int, seconds_left: float) -> None:
        components = build_listening_components(seconds_left, stop_custom_id, sample_num=frame)
        await _edit_original_response_v2(interaction, components)

    # Show initial listening UI
    await update_listening_ui(0, float(TOTAL_LISTEN_SECONDS))

    try:
        result = await listen_and_recognize(
            vc,
            stop_event=stop_event,
            progress_callback=update_listening_ui,
        )
        if result.get("stopped"):
            await _edit_original_response_v2(interaction, build_stopped_components())
        else:
            await send_track_response(interaction, result, edit_instead=True, source="listen")
    except Exception as e:
        print(f"Listen command error: {e}")
        try:
            if vc.is_connected():
                await vc.disconnect(force=True)
        except Exception:
            pass
        await send_track_response(
            interaction, {"timestamp": None, "track": None}, edit_instead=True, source="listen"
        )
    finally:
        _listen_stop_events.pop(str(interaction.id), None)


@tree.command(name="help", description="Learn how to use What's That Song?")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def help_command(interaction: discord.Interaction):
    help_text = """# What's That Song?

**Figure out what song is playing with videos, audio files, and web URLs on Discord.**

There are a few ways you can use the bot:

**1.** Use the `/match` command with a file or URL to identify a song. You can optionally specify a start time (e.g. `1:30`) to begin matching from a specific point in the media.

**2.** Use the `/listen` command while in a voice channel to have the bot join and identify music playing in the call (listens for up to 30 seconds).

**3.** If you have access to use application commands in a server, you can right-click a message and choose **Apps > What's That Song?** to identify media in that message. The results will be sent to you privately.

**4.** Send a message in a server **@ mentioning the bot** with a URL or media file.

**5.** **DM the bot** with a URL or media file."""

    container = {
        "type": 17,
        "components": [
            {"type": 10, "content": help_text},
        ],
    }

    await interaction.response.defer(ephemeral=True)
    await _send_components_v2(interaction, [container], ephemeral=True)


@tree.context_menu(name="What's That Song?")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def whats_that_song_context(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    print(f"Context menu invoked on message from {message.author.name}")

    for attachment in message.attachments:
        if _is_media_attachment(attachment):
            print(f"Found media attachment: {attachment.url}")
            result = await process_media(attachment.url)
            await send_track_response(interaction, result, ephemeral=True)
            return

    for embed in message.embeds:
        if embed.url:
            if should_direct_download(embed.url) or TWITTER_LINK_REGEX.match(embed.url):
                print(f"Found media in embed: {embed.url}")
                result = await process_media(embed.url)
                await send_track_response(interaction, result, ephemeral=True)
                return

    links = LINK_REGEX.findall(message.content)
    if links:
        url = links[0]
        print(f"Found URL: {url}")
        result = await process_media(url)
        await send_track_response(interaction, result, ephemeral=True)
        return

    await interaction.followup.send(
        "No media found in this message. Please select a message with a video, audio file, or URL.",
        ephemeral=True,
    )


if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
