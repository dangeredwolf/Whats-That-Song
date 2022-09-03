What's That Song?
==

A Discord bot that finds the song given a video or audio file, using Shazam.

Written in Discord.py ~~because I like torturing myself~~ because ShazamIO exists only in Python form.

## Quick start

1. Install Python 3.8 or later (3.10 recommended) and FFmpeg
2. Install the requirements with `pip install -r requirements.txt`
3. Put bot token in `token.txt`
4. Run `wts.py`
5. Profit

## Limitations

We extract only the first minute of audio out of an audio clip. If music occurs later on in a video or audio clip, it will not be recognized.

Active live streams, and videos longer than 30 minutes, will not be processed using yt-dlp extractor. This is to help keep response times low and reduce the chance of disruptions to other users.

This bot generally does not use the message content intent. However, [due to a Discord API bug](https://github.com/discord/discord-api-docs/issues/5406), the bot will break deferred media from embeds without the message content intent. Media already cached by, or already hosted by, Discord is not affected. The yt-dlp extractor may assist in making these embeds work anyway, but this might not work in every case. 