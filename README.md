What's That Song?
==

A Discord bot that identifies songs from videos, audio files, and URLs using Shazam.

## Quick Start

### Prerequisites

- Python 3.10 or later
- FFmpeg installed and in your PATH
- Discord bot token from [Discord Developer Portal](https://discord.com/developers/applications)
- Spotify API credentials from [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) (optional but recommended)

### Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your credentials:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
   ```
4. Run the bot:
   ```bash
   python bot.py
   ```

### Setting up Spotify API (Optional)

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Copy the Client ID and Client Secret
4. Add them to your `.env` file

Without Spotify credentials, the bot will still work but won't include Spotify links in responses.

## Usage

There are several ways to use the bot:

1. **`/match` command** - Use the slash command with a file attachment or URL
2. **Message context menu** - Right-click any message and select "Apps > What's That Song?"
3. **Mention the bot** - @ mention the bot in a server with a URL or attachment
4. **DM the bot** - Send a URL or file directly to the bot in a DM

## Limitations

- We extract up to 3 minutes of audio from media files
- Active live streams cannot be processed
- Videos longer than 60 minutes are rejected to keep response times reasonable
- Song recognition depends on Shazam's database coverage

## License

MIT License - see LICENSE.md for details
