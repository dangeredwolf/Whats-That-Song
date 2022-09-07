import asyncio
import mimetypes
import os
import random
import time
import aiohttp
import flask
import yt_dlp as yt
from shazamio import Shazam
from urllib.parse import urlparse

# Make ./tmp if it does not already exist
if not os.path.exists("./tmp"):
    os.mkdir("./tmp")

# Delete all files in ./tmp on startup
for file in os.listdir("./tmp"):
    os.remove("./tmp/" + file)
    
def ytdl_filter(info):
    # print json conversion of info
    if (info.get("is_live")):
        return "WTS cannot process currently live streams"
    if (info.get("duration") > 1800): # 30 minutes
        return "WTS cannot process videos longer than 30 minutes"
    
    return None

headers = {
    "sec-ch-ua": '".Not/A)Brand";v="99", "Google Chrome";v="104", "Chromium";v="104"',
    "DNT": '1',
    "sec-ch-ua-mobile": '?0',
    "User-Agent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36',
    "sec-ch-ua-platform": '"Windows"',
    "Accept": '*/*',
    "Sec-Fetch-Site": 'none',
    "Sec-Fetch-Mode": 'no-cors',
    "Accept-Encoding": 'gzip, deflate, br',
    "Accept-Language": 'en',
    "Cache-Control": 'no-cache',
    "Pragma": 'no-cache',
    "Upgrade-Insecure-Requests": '1',
}
mimetypes.init()
shazam = Shazam()

# Create YouTube-Dl but disallow live streams
ytdl = yt.YoutubeDL({ "format" : "worstaudio/worst", "outtmpl": "tmp/%(id)s.%(ext)s", "postprocessors": [{ "key": "FFmpegExtractAudio", "preferredcodec": "aac", "nopostoverwrites": True }], "noplaylist": True, "match_filter": ytdl_filter })

app = flask.Flask("whatsthatsong")

# Twitter fetch API with Tweet ID
@app.route("/twitter/<tweet_id>")
async def twitter_engine(tweet_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.fxtwitter.com/status/{tweet_id}", headers=headers) as resp:
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

@app.route("/ytdl")
async def ytdl_engine():
    url = urlparse(flask.request.args.get("url")).geturl()
    if url is None:
        return "No URL provided", 400
    print(f"Processing {url} with ytdl")
    filepath = None
    try:
        info = ytdl.extract_info(url)
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
            os.remove(filepath)
        except:
            pass
        raise e

@app.route("/direct")
async def direct_engine():
    url = urlparse(flask.request.args.get("url")).geturl()
    if url is None:
        return "No URL provided", 400
    print(f"Processing {url} with direct")
    return await process_video(url)

async def process_video(url):
    print(f"Processing {url} with direct video")
    randomname = str(random.randint(0, 2147483647))
    randomoutput = str(random.randint(0, 2147483647))

    async with aiohttp.ClientSession() as session:
        # TODO: use media-proxy.dangeredwolf.com for non-Discord URLs
        async with session.get(url, headers=headers) as resp:
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

token = None
token_expires = 0

async def get_spotify_token():

    global token
    global token_expires
    # Compare current time ms to token_expires
    if (token_expires > time.time() * 1000):
        print("We already have a hopefully valid token")
        return token
    async with aiohttp.ClientSession() as session:
        async with session.get("https://open.spotify.com/get_access_token?reason=transport&productType=web-player", headers=headers) as resp:
            # If we get a 200, we have a valid token
            if resp.status == 200:
                data = await resp.json()
                token = data.get("accessToken")
                token_expires = data.get("accessTokenExpirationTimestampMs")
                return token
            elif resp.status == 429:
                print("We got rate limited, gimme a sec")
                await asyncio.sleep(1)
                return await get_spotify_token()

@app.route("/spotify")
async def spotify_search():
    song = flask.request.args.get("song")
    artist = flask.request.args.get("artist")
    if song is None:
        return "No song provided", 400
    if artist is None:
        return "No artist provided", 400
    query = song + " " + artist
    print(f"Searching Spotify for {query}")
    token = await get_spotify_token()
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.spotify.com/v1/search?q={query}&type=track&limit=1", headers={**headers, "Authorization": f"Bearer {token}"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                tracks = data.get("tracks")
                if tracks is None:
                    print("Check failed: tracks is None")
                    return "", 404
                items = tracks.get("items")
                if items is None:
                    print("Check failed: items is None")
                    return "", 404
                item = items[0]
                if item is None:
                    print("Check failed: item[0] is None")
                    return "", 404
                # Check through artists to make sure original artist is in the list
                artists = item.get("artists")
                if artists is None:
                    print("Check failed: artists is None")
                    return "", 404
                matched_artist = False
                for artistI in artists:
                    # We have some leniency here because Spotify might include extra things like (feat. etc)
                    if artist.lower() in artistI.get("name").lower() or artistI.get("name").lower() in artist.lower():
                        print("Matched artist")
                        matched_artist = True
                        break
                if not matched_artist:
                    print("Check failed: No matching artist")
                    return "", 404
                matched_song = False
                for songI in items:
                    # We have some leniency here because Spotify might include extra things like (feat. etc)
                    if song.lower() in songI.get("name").lower() or songI.get("name").lower() in song.lower():
                        print("Matched song")
                        matched_song = True
                        break
                if not matched_song:
                    print("Check failed: No matching song title")
                    return "", 404
                resp = flask.Response(item.get("external_urls").get("spotify"))
                resp.headers['Content-Type'] = 'text/plain'
                return resp
            elif resp.status == 429:
                print("We got rate limited, let's try another token")
                token = await get_spotify_token()
                return await spotify_search()

# start server
app.run(host="localhost", port=6799)