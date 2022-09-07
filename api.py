import mimetypes
import os
import random
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

# start server
app.run(host="localhost", port=6799)