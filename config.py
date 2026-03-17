"""Configuration and constants for What's That Song?"""

import os
import re

from dotenv import load_dotenv

load_dotenv()

# Environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# Regex patterns
TWITTER_LINK_REGEX = re.compile(
    r"(?i)https?://((fx|vx)?twitter|twxtter|twittpr|twitter64|(fixup|fixv)?x)\.com/\w{1,15}/status(es)?/\d+"
)
LINK_REGEX = re.compile(r"(?i)https?://\S+")

# Random fun messages
RANDOM_MESSAGES = [
    "I found it!",
    "This might be the song you're looking for.",
    "I hope this helps.",
    "Hey, I love this song too.",
    "I like your taste.",
    "I was wondering about this song too.",
]

# HTTP headers for requests
HEADERS = {
    "sec-ch-ua": '".Not/A)Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "DNT": "1",
    "sec-ch-ua-mobile": "?0",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "sec-ch-ua-platform": '"Windows"',
    "Accept": "*/*",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "no-cors",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}

# Components V2 flag for Discord
COMPONENTS_V2_FLAG = 1 << 15
