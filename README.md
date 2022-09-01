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

This bot generally does not use the message content intent. However, [due to a Discord API bug](https://github.com/discord/discord-api-docs/issues/5406), the bot will break deferred media from embeds without the message content intent. Media already cached by, or already hosted by, Discord is not affected. Message content intent will be removed from production once Discord fixes their API bug.