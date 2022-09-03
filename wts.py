import asyncio
import os
import re
import aiohttp
import random
import discord
import mimetypes
import yt_dlp as yt

from discord import app_commands
from shazamio import Shazam, Serialize

# Make ./tmp if it does not already exist
if not os.path.exists("./tmp"):
    os.mkdir("./tmp")

# Delete all files in ./tmp on startup
for file in os.listdir("./tmp"):
    os.remove("./tmp/" + file)

random_messages = [
    "I found it!",
    "This might be the song you're looking for.",
    "I hope this helps.",
    "Hey, I love this song too.",
    "I like your taste.",
    "I was wondering about this song too."
]

# Dict of pending media
pending_media = {}

mimetypes.init()
shazam = Shazam()
ydl = yt.YoutubeDL({ "format" : "worstaudio/worst", "outtmpl": "%(id)s.%(ext)s", "postprocessors": [{ "key": "FFmpegExtractAudio", "preferredcodec": "aac", "nopostoverwrites": True }] })

blacklist_ytdl_domains = [
    "fxtwitter.com",
    "vxtwitter.com",
    "twxtter.com",
    "twitter64.com"
]

twitter_domains = [
    "twitter.com",
    "fxtwitter.com",
    "vxtwitter.com",
    "twxtter.com",
    "twitter64.com"
]

blacklist_direct_domains = [
    "youtube.com",
    "youtu.be",
    "twitter.com"
]

async def process_twitter(url):
    print(f"Processing {url} with twitter")
    # Extract Tweet ID from Twitter URL
    tweet_id = re.search(r"status\/(\d+)", url).group(1)
    # Get Tweet JSON
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.fxtwitter.com/status/{tweet_id}") as resp:
            data = await resp.json()
            tweet = data.get("tweet")
            if tweet is None:
                return None
            media = tweet.get("media")
            if media is None:
                return None
            videos = media.get("videos")
            if videos is None:
                return None
            video = videos[0]
            if video is None:
                return None
            video_url = video.get("url")
            print("video_url", video_url)
            if video_url is None:
                return None
            return await process_video(video_url)

async def process_ytdl(url):
    print(f"Processing {url} with ytdl")
    filename = None
    try:
        info = ydl.extract_info(url)
        if info.get("requested_downloads") is not None and info.get("requested_downloads")[0] is not None:
            download = info.get("requested_downloads")[0]
            filepath = download.get("filepath")
            print(f"Requested download: {download}")
            print(f"File path: {filepath}")
            out = await shazam.recognize_song(filepath)
            os.remove(filepath)
            return out
    except Exception as e:
        print(e)
        try:
            os.remove(filename)
        except:
            pass
        raise e


async def process_video(url):
    print(f"Processing {url} with direct video")
    randomname = str(random.randint(0, 2147483647))
    randomoutput = str(random.randint(0, 2147483647))

    async with aiohttp.ClientSession() as session:
        async with session.get("https://media-proxy.dangeredwolf.com/" + url) as resp:
            print(f"Response status code: {str(resp.status)}")
            filename = "./tmp/" + randomname
            audiofilename = "./tmp/" + randomoutput + ".aac"
            with open(filename, 'wb') as f:
                while True:
                    chunk = await resp.content.read(1024)
                    if not chunk:
                        break
                    f.write(chunk)
            try:
                print(f"Extracting audio from {url}")
                # Call system ffmpeg to convert to aac
                os.system(f"ffmpeg -i {filename} -t 60 -vn -acodec aac {audiofilename}")
                os.remove(filename)
                print(f"Finding music in {url}")
                out = await shazam.recognize_song(audiofilename)
                print(f"Music lookup finished for {url}")
                os.remove(audiofilename)
                # shazamio's serializer is useless and returns None for stuff like album art for no reason, so it's unusable
                return out
            except Exception as e:
                print(e)
                try:
                    os.remove(filename)
                except:
                    pass
                try:
                    os.remove(audiofilename)
                except:
                    pass
                raise e

async def generate_embed(match):
    if match is None or match.get("track") is None:
        return None

    serialized = Serialize.full_track(match)

    print("Generating embed...")

    # i hate dicts and their .get() chaining hell
    track = match.get("track")
    embed = discord.Embed(title=track.get("title"),
                          description=track.get("subtitle"),
                          color=discord.Color.blue())
    
    if track.get("sections") is not None and track.get("sections")[0] is not None and track.get("sections")[0].get("metadata") is not None:
        metadata = track.get("sections")[0].get("metadata")
        # Loop over metadata list and add each property to the embed
        for prop in metadata:
            embed.add_field(name=prop.get("title"), value=prop.get("text"), inline=True)

    if (track.get("images")):
        embed.set_thumbnail(url= track.get("images").get("coverarthq"))

    embed.set_footer(text="Shazam", icon_url="https://cdn.discordapp.com/attachments/165560751363325952/1014753423045955674/84px-Shazam_icon.svg1.png")
    return embed

async def generate_view(match):
    if match is None or match.get("track") is None:
        return None

    serialized = Serialize.full_track(match)

    view = discord.ui.View()
    
    if serialized.track.spotify_url:
        view.add_item(discord.ui.Button(emoji=discord.PartialEmoji(name="Spotify", id="1014768475593506836"), label="Spotify", url=serialized.track.spotify_url.replace("spotify:search:", "https://open.spotify.com/search/")))
    
    if serialized.track.apple_music_url:
        view.add_item(discord.ui.Button(emoji=discord.PartialEmoji(name="Apple Music", id="1014769073277640765"), label="Apple Music", url=serialized.track.apple_music_url))

    
    return view

class Bot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tree = app_commands.CommandTree(self)

intents = discord.Intents.default()
intents.messages = True
# Message content required when uncached embeds are updated. This is a Discord API bug.
# https://github.com/discord/discord-api-docs/issues/5406
# We'll remove message content requirement when the bug is fixed, as we don't need message content normally.
intents.message_content = True

client = Bot(intents=intents)
client.activity = discord.Activity(type=discord.ActivityType.listening, name="your music!")

async def handle_message(message: discord.Message, interaction: discord.Interaction = None):
    url = None

    if message.guild is not None:
       print("Song request from guild " + str(message.guild.name))

    for embed in message.embeds:
        if embed.video is not None and embed.video.url is not None:
            # Make sure the domain is not a blacklisted domain
            if not any(domain in embed.video.url for domain in blacklist_direct_domains):
                url = embed.video.url
                break
            else:
                print("URL contains domain not eligible for direct download: " + embed.video.url)
    for attachment in message.attachments:
        # Check if attachment is any video or audio file
        mimetype = mimetypes.guess_type(attachment.filename)[0]
        if mimetype is not None and (mimetype.startswith("video/") or mimetype.startswith("audio/")):
            print("Found suitable media")
            url = attachment.url
            break
    if url is None:
        print("Checking URLs for YouTube-DL-able URLs")
        # Check if message contains a link, then extract the URL
        for match in re.finditer(r"(?P<url>https?://[^\s]+)", message.content):
            url = match.group("url")
            # Make sure the domain is not a blacklisted domain
            if any(domain in url for domain in twitter_domains):
                print("Using twitter engine")
                if interaction is None:
                    async with message.channel.typing():
                        await _handle_message(url, message, interaction, False, True)
                else:
                    await _handle_message(url, message, interaction, False, True)
                return
            if not any(domain in url for domain in blacklist_ytdl_domains):
                print("Using ytdl engine")
                if interaction is None:
                    async with message.channel.typing():
                        await _handle_message(url, message, interaction, True)
                else:
                    await _handle_message(url, message, interaction, True)
                return
            else:
                print("URL contains domain not eligible for ytdl: " + url)

    if url is not None:
        # Show that bot is typing
        print("Downloading video...")
        # Only show typing indicator for non-interaction messages
        if interaction is None:
            async with message.channel.typing():
                await _handle_message(url, message, interaction)
        else:
            await _handle_message(url, message, interaction)
    else:
        pending_media[message.id] = True
        # wait 10 seconds for media to be added
        await asyncio.sleep(5)
        if message.id in pending_media:
            del pending_media[message.id]
            if interaction is not None:
                await interaction.followup.send(embed=discord.Embed(title="Media not found", description="We couldn't find any media in the message you requested", color=discord.Color.red()), ephemeral=True)
            else:
                await message.channel.send(reference=message, embed=discord.Embed(title="Media not found", description="We couldn't find any media in the message you requested", color=discord.Color.red()))

async def _handle_message(url: str, message: discord.Message, interaction: discord.Interaction = None, ytdl: bool = False, twitter: bool = False):
    songinfo = None
    try:
        if ytdl:
            songinfo = await process_ytdl(url)
        elif twitter:
            songinfo = await process_twitter(url)
        else:
            songinfo = await process_video(client, url)
        print("Song info acquired")
        random_message = random.choice(random_messages)
        embed = await generate_embed(songinfo)
        if embed is None:
            if interaction is not None:
                await interaction.followup.send(embed=discord.Embed(title="No matches", description="Sorry, we had no song matches for that video or audio file", color=discord.Color.orange()), ephemeral=True)
            else:
                await message.channel.send(reference=message, embed=discord.Embed(title="No matches", description="Sorry, we had no song matches for that video or audio file", color=discord.Color.orange()))
            return
        if interaction is not None:
            await interaction.followup.send(random_message, embed=await generate_embed(songinfo), view=await generate_view(songinfo), ephemeral=True)
        else:
            await message.channel.send(random_message, reference=message, embed=await generate_embed(songinfo), view=await generate_view(songinfo))
    except Exception as e:
        print(e)
        if interaction is not None:
            await interaction.followup.send(embed=discord.Embed(title="Error", description="An error occurred while processing the media you sent\n\nThis may be a temporary issue downloading the media, please try again in a little while, or report this as a bug.", color=discord.Color.red()), ephemeral=True)
        else:
            await message.channel.send(reference=message, embed=discord.Embed(title="Error", description="An error occurred while processing the media you sent\n\nThis may be a temporary issue downloading the media, please try again in a little while, or report this as a bug.", color=discord.Color.red()))


@client.event
async def on_message(message: discord.Message):
    if f"<@{client.user.id}>" in message.content or message.guild is None:
        if message.author.id != client.user.id:
            print("Let's go process this message")
            await handle_message(message)

# @client.event
# async def on_raw_message_edit(payload: discord.RawMessageUpdateEvent):
#     print("on_raw_message_edit payload.data")
#     print(payload.data)

@client.event
async def on_message_edit(before_message: discord.Message, message: discord.Message):
    if f"<@{client.user.id}>" in message.content or message.guild is None:
        if message.author.id != client.user.id:
            print("Message containing ping edited")
            print("Embeds count before " + str(len(before_message.embeds)))
            print("Embeds count after " + str(len(message.embeds)))
            if message.id in pending_media and len(message.embeds) > 0:
                print("Media was pending and has now arrived")
                del pending_media[message.id]
                await handle_message(message)

@client.event
async def on_ready():
    print(f'READY ({client.user} {client.user.id})')

@client.event
async def on_resumed():
    print('RESUME')

@client.tree.command()
async def help(interaction: discord.Interaction):
    await interaction.response.send_message(f'There are two ways to use *What\'s That Song?*\n\n1. Tag me in a message containing a video, audio file, or video embed. My reply will be public.\n2. Right click on an existing message with a video, audio file, or video embed and select **Apps > What\'s That Song?**. I will reply privately to you.', ephemeral=True)

@client.tree.context_menu(name="What's That Song?")
async def whatsong(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True, thinking=True)
    await handle_message(message, interaction)

# Read token file
with open('token.txt', 'r') as f:
    token = f.read()
    client.run(token)
