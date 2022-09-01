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

## Notes

This bot generally does not use the message content intent. However, [due to a Discord API bug](https://github.com/discord/discord-api-docs/issues/5406), the bot will break deferred media from embeds without the message content intent. Media already cached by, or already hosted by, Discord is not affected. Message content intent will be removed from production once Discord fixes their API bug.

At the moment, we do not support links from sites that don't embed video files, like YouTube and TikTok. If you want to use them with What's That Song?, download them using something like [Cobalt](https://co.wukko.me/), then either attach the media link or reupload it to Discord.

We extract only the first minute of audio out of an audio clip. If music occurs later on in a video or audio clip, it will not be recognized.