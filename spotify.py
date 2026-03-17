"""Spotify Web API integration using Client Credentials flow."""

import base64
import time

import aiohttp

from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET

# Token cache
_token = None
_token_expires = 0


async def get_spotify_token():
    """Get Spotify access token using Client Credentials flow."""
    global _token, _token_expires

    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        print("Spotify credentials not configured, skipping Spotify integration")
        return None

    if _token and _token_expires > time.time():
        return _token

    auth_string = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
    auth_bytes = auth_string.encode("utf-8")
    auth_base64 = base64.b64encode(auth_bytes).decode("utf-8")

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://accounts.spotify.com/api/token",
            headers={
                "Authorization": f"Basic {auth_base64}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={"grant_type": "client_credentials"},
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                _token = data.get("access_token")
                expires_in = data.get("expires_in", 3600)
                _token_expires = time.time() + expires_in - 60
                return _token
            else:
                print(f"Failed to get Spotify token: {resp.status}")
                return None


async def search_spotify(artist: str, song: str):
    """Search Spotify for a track and return its URL."""
    token = await get_spotify_token()
    if not token:
        return None

    query = f"{song} {artist}"
    print(f"Searching Spotify for: {query}")

    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.spotify.com/v1/search",
            params={"q": query, "type": "track", "limit": 5},
            headers={"Authorization": f"Bearer {token}"},
        ) as resp:
            if resp.status != 200:
                print(f"Spotify search failed: {resp.status}")
                return None

            data = await resp.json()
            tracks = data.get("tracks", {})
            items = tracks.get("items", [])

            if not items:
                print("No Spotify results found")
                return None

            for item in items:
                artists = item.get("artists", [])
                item_name = item.get("name", "").lower()

                artist_match = False
                for item_artist in artists:
                    artist_name = item_artist.get("name", "").lower()
                    if artist.lower() in artist_name or artist_name in artist.lower():
                        artist_match = True
                        break

                song_match = song.lower() in item_name or item_name in song.lower()

                if artist_match and song_match:
                    url = item.get("external_urls", {}).get("spotify")
                    if url:
                        print(f"Found Spotify match: {url}")
                        return url

            first_item = items[0]
            url = first_item.get("external_urls", {}).get("spotify")
            print(f"Using first Spotify result: {url}")
            return url
