"""What's That Song? - Discord bot entry point."""

import discord

from audio import parse_start_time, process_media, should_direct_download
from config import (
    COMPONENTS_V2_FLAG,
    DISCORD_TOKEN,
    LINK_REGEX,
    TWITTER_LINK_REGEX,
)
from responses import send_track_response
from voice import listen_and_recognize

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN not found in environment variables")

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.voice_states = True

bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("Ready to identify music!")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="your music!",
        )
    )


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if message.guild and bot.user not in message.mentions:
        return

    if not message.content and not message.attachments and not message.embeds:
        return

    print(f"Processing message from {message.author.name}")

    for attachment in message.attachments:
        content_type = attachment.content_type or ""
        if "video" in content_type or "audio" in content_type:
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


@bot.slash_command(
    name="match",
    description="Identify a song from a file or URL",
    integration_types={
        discord.IntegrationType.guild_install,
        discord.IntegrationType.user_install,
    },
    contexts={
        discord.InteractionContextType.guild,
        discord.InteractionContextType.bot_dm,
        discord.InteractionContextType.private_channel,
    },
)
async def match_command(
    ctx: discord.ApplicationContext,
    file: discord.Option(
        discord.Attachment,
        description="Audio or video file",
        required=False,
    ),
    url: discord.Option(
        str,
        description="URL to audio/video or a page containing media",
        required=False,
    ),
    start_time: discord.Option(
        str,
        description="Start matching at this time (e.g. 90, 1:30, 1:30:45)",
        required=False,
    ),
):
    """Match a song from a file or URL."""
    if not file and not url:
        await ctx.respond(
            "Please provide either a file or a URL to identify.",
            ephemeral=True,
        )
        return

    start_seconds = parse_start_time(start_time)
    if start_time is not None and start_time.strip() and start_seconds is None:
        await ctx.respond(
            "Invalid start time. Use seconds (e.g. 90), minutes:seconds (e.g. 1:30), or hours:minutes:seconds (e.g. 1:30:45).",
            ephemeral=True,
        )
        return

    await ctx.defer(ephemeral=False)

    if file:
        print(f"Processing attachment from /match: {file.url}")
        result = await process_media(file.url, start_seconds or 0)
    else:
        print(f"Processing URL from /match: {url}")
        result = await process_media(url, start_seconds or 0)

    await send_track_response(ctx, result)


@bot.slash_command(
    name="listen",
    description="Join your voice channel and identify music playing (listens up to 15 seconds)",
    integration_types={
        discord.IntegrationType.guild_install,
        discord.IntegrationType.user_install,
    },
    contexts={
        discord.InteractionContextType.guild,
    },
)
async def listen_command(ctx: discord.ApplicationContext):
    """Join the user's voice channel and identify music from the call."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.respond(
            "You need to be in a voice channel to use this command.",
            ephemeral=True,
        )
        return

    if ctx.guild.voice_client is not None:
        await ctx.respond(
            "I'm already in a voice channel. Please wait for me to finish or disconnect me first.",
            ephemeral=True,
        )
        return

    await ctx.defer(ephemeral=False)

    try:
        vc = await ctx.author.voice.channel.connect()
    except Exception as e:
        print(f"Failed to connect to voice channel: {e}")
        error_response = {"timestamp": None, "track": None}
        await send_track_response(ctx, error_response)
        return

    try:
        result = await listen_and_recognize(vc)
        await send_track_response(ctx, result)
    except Exception as e:
        print(f"Listen command error: {e}")
        try:
            if vc.is_connected():
                await vc.disconnect(force=True)
        except Exception:
            pass
        error_response = {"timestamp": None, "track": None}
        await send_track_response(ctx, error_response)


@bot.slash_command(
    name="help",
    description="Learn how to use What's That Song?",
    integration_types={
        discord.IntegrationType.guild_install,
        discord.IntegrationType.user_install,
    },
    contexts={
        discord.InteractionContextType.guild,
        discord.InteractionContextType.bot_dm,
        discord.InteractionContextType.private_channel,
    },
)
async def help_command(ctx: discord.ApplicationContext):
    """Show help information."""
    help_text = """# What's That Song?

**Figure out what song is playing with videos, audio files, and web URLs on Discord.**

There are a few ways you can use the bot:

**1.** Use the `/match` command with a file or URL to identify a song. You can optionally specify a start time (e.g. `1:30`) to begin matching from a specific point in the media.

**2.** Use the `/listen` command while in a voice channel to have the bot join and identify music playing in the call (listens for up to 15 seconds).

**3.** If you have access to use application commands in a server, you can right-click a message and choose **Apps > What's That Song?** to identify media in that message. The results will be sent to you privately.

**4.** Send a message in a server **@ mentioning the bot** with a URL or media file.

**5.** **DM the bot** with a URL or media file."""

    container = {
        "type": 17,
        "components": [
            {"type": 10, "content": help_text},
        ],
    }

    await ctx.respond(
        components=[container],
        flags=COMPONENTS_V2_FLAG,
        ephemeral=True,
    )


@bot.message_command(
    name="What's That Song?",
    integration_types={
        discord.IntegrationType.guild_install,
        discord.IntegrationType.user_install,
    },
    contexts={
        discord.InteractionContextType.guild,
        discord.InteractionContextType.bot_dm,
        discord.InteractionContextType.private_channel,
    },
)
async def whats_that_song_context(
    ctx: discord.ApplicationContext, message: discord.Message
):
    """Context menu command to identify songs in messages."""
    await ctx.defer(ephemeral=True)

    print(f"Context menu invoked on message from {message.author.name}")

    for attachment in message.attachments:
        content_type = attachment.content_type or ""
        if "video" in content_type or "audio" in content_type:
            print(f"Found media attachment: {attachment.url}")
            result = await process_media(attachment.url)
            await send_track_response(ctx, result, ephemeral=True)
            return

    for embed in message.embeds:
        if embed.url:
            if should_direct_download(embed.url) or TWITTER_LINK_REGEX.match(
                embed.url
            ):
                print(f"Found media in embed: {embed.url}")
                result = await process_media(embed.url)
                await send_track_response(ctx, result, ephemeral=True)
                return

    links = LINK_REGEX.findall(message.content)
    if links:
        url = links[0]
        print(f"Found URL: {url}")
        result = await process_media(url)
        await send_track_response(ctx, result, ephemeral=True)
        return

    await ctx.followup.send(
        "No media found in this message. Please select a message with a video, audio file, or URL.",
        ephemeral=True,
    )


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
