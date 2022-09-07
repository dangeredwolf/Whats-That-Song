What's That Song?
==

A Discord bot that finds the song given a video or audio file, using Shazam.

Bot written in Rust with Serenity. Interfaces with an internal API written in Python that connects to ShazamIO and yt-dlp.

## Quick start

1. Install Python 3.8 or later (3.10 recommended) and FFmpeg, and Rust toolchain
2. Install the Python API requirements with `pip install -r requirements.txt`
3. Put bot token in `.env`
4. Run `api.py`
5. `cargo build --release && target/release/whats-that-song`
6. Profit

## Limitations

We extract only the first minute of audio out of an audio clip. If music occurs later on in a video or audio clip, it will not be recognized.

Active live streams, and videos longer than 30 minutes, will not be processed using yt-dlp extractor. This is to help keep response times low.
