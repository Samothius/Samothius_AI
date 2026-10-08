# Samothius AI

A custom bot system for the **samothius** stream. It runs a shared "SamoBit" economy and chat games on Twitch (and optionally YouTube), announces streams on Discord, serves OBS overlays, and comes with a web admin panel to tune everything live.

## Features

**Twitch bot**
- SamoBit economy with chat games: boss fights, gambling, heists, robbing, fishing, daily rewards, gifting
- Channel Points integration (EventSub WebSocket) for SamoBit purchases and fishing buffs
- Live game settings stored in the database, so balance changes need no redeploy
- Periodic passive SamoBit rewards for active chatters
- Rotating chat messages that remind viewers which commands exist
- Automatic OAuth token refresh

**Discord bot**
- Go-live announcements for Twitch and YouTube with a role-ping toggle button
- On-demand Top 10 leaderboard
- Daily system status report (service health, uptime, most played games)
- Daily Top 50 richest players leaderboard

**OBS overlays** (Flask + WebSocket)
- SamoBit leaderboard
- Scrolling stream credits (subscribers, top gifters, recent followers)
- Live chat with Twitch, BTTV and FFZ emotes
- Fishing event popup

**Admin panel** (Flask, password protected)
- Dashboard with totals and Top 10
- Edit every game setting
- Add, set or blacklist user balances
- Live controls: games on/off, spawn boss, start/stop/restart bots

**YouTube bot** (optional)
- YouTube Live Chat bot sharing the same economy database, with separate YouTube balances

## Chat commands

### Twitch

| Command | Description |
| --- | --- |
| `!samobit balance` | Show your balance |
| `!daily` | Claim your daily reward (24h cooldown) |
| `!first` | Claim the first-in-chat reward (once per stream) |
| `!gamble <amount>` | Bet SamoBit for a chance to win, with a rare jackpot |
| `!heist store\|bank\|vault` | Start a heist on a chosen tier; others join with `!heist` during the lobby |
| `!rob @user` | Try to steal a share of another user's balance |
| `!gift @user <amount>` | Send SamoBit to another user |
| `!fish` | Catch a fish while the fishing window is open (watch the overlay) |
| `!attack` | Attack the active boss |
| `!bossstatus` | Show the current boss and its remaining HP |
| `!games on\|off` | Moderators: enable or disable games |
| `!spawnboss` | Broadcaster only: spawn a boss manually |

### Discord

| Command | Description |
| --- | --- |
| `!leaderboard` | Show the Top 10 richest users |
| `!test_announcement` | Developer: trigger a silent test stream announcement |
| `!test_report` | Developer: generate the daily report and Top 50 immediately |

## Channel Points rewards

The Twitch bot reacts to these custom rewards. The reward titles must match exactly.

| Reward title | Effect |
| --- | --- |
| `Buy 1000 SamoBits` | Adds 1,000 SamoBit |
| `Buy 5000 SamoBits` | Adds 5,000 SamoBit |
| `Fish Buff` | Personal rare-fish boost for 2 hours |
| `Global Fish Buff` | Rare-fish boost for everyone for 30 minutes |

## Project structure

| File | Purpose |
| --- | --- |
| `main.py` | Discord bot |
| `games.py` | Twitch bot, games and chat overlay WebSocket bridge |
| `youtube_bot.py` | YouTube Live Chat bot |
| `web_overlay.py` | Flask server for the OBS overlay pages |
| `admin_panel.py` | Flask admin panel |
| `database.py` | SQLite economy, settings and command queue |
| `config.py` | Environment variable loading |
| `economy_commands.py` | Economy command helpers |
| `twitch_api.py` | Twitch API client (live stream check) |
| `token_manager.py` | Twitch OAuth token refresh |
| `youtube_token_manager.py` | YouTube OAuth token handling |
| `get_token.py` | Token helper script |
| `deploy_server.py`, `deploy_twitch.sh`, `backup_bot.sh` | Deployment and backup scripts |
| `static/` | Static assets for the overlays |

## Requirements

- Linux server with Python 3 (developed on Ubuntu 24.04)
- A Discord bot application and token
- A Twitch application (client ID and secret) with OAuth tokens for the bot account and for Channel Points
- Optional: a Google Cloud project with YouTube Data API access
- `twitchio` must stay on 2.x. Version 3 is not compatible.

## Setup

1. Clone the repository.

   ```bash
   git clone https://github.com/Samothius/Samothius_AI.git
   cd Samothius_AI
   ```

2. Create a virtual environment and install the dependencies.

   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the project root.

   ```env
   DISCORD_TOKEN=
   ANNOUNCEMENT_CHANNEL_ID=
   STREAM_NOTIFICATION_ROLE_ID=

   STREAMER_NAME=
   TWITCH_CLIENT_ID=
   TWITCH_CLIENT_SECRET=
   TMI_TOKEN=
   TMI_REFRESH_TOKEN=
   EVENTSUB_TOKEN=
   EVENTSUB_REFRESH_TOKEN=
   STREAM_CHECK_INTERVAL_MINUTES=5

   CHAT_OVERLAY_WS_PORT=8765

   ADMIN_PANEL_PASSWORD=
   ADMIN_PANEL_SECRET_KEY=
   ADMIN_PANEL_PORT=5050

   YOUTUBE_CLIENT_ID=
   YOUTUBE_CLIENT_SECRET=
   YOUTUBE_REFRESH_TOKEN=
   YOUTUBE_CHANNEL_ID=
   ```

   Never commit this file. It contains secrets.

4. Start the components you need, each in its own process.

   ```bash
   python main.py
   python games.py
   python web_overlay.py
   python admin_panel.py
   python youtube_bot.py
   ```

## Ports

| Component | Port |
| --- | --- |
| Overlay web server | 5000 |
| Chat overlay WebSocket | 8765 (`CHAT_OVERLAY_WS_PORT`) |
| Admin panel | 5050 (`ADMIN_PANEL_PORT`) |

## OBS overlays

Add each one as a Browser Source pointing at the overlay server.

| URL | Overlay |
| --- | --- |
| `http://<server>:5000/leaderboard` | SamoBit leaderboard |
| `http://<server>:5000/credits` | Scrolling credits |
| `http://<server>:5000/chat` | Live chat |
| `http://<server>:5000/game` | Fishing event popup |

The chat and fishing overlays connect to the WebSocket bridge on port 8765, so that port must be reachable from the machine running OBS.

## Running as services

In production each component runs as a systemd unit with `Restart=always`. The admin panel and the daily Discord report expect these unit names:

- `samothius-discord`
- `samothius-twitch`
- `samothius-web`
- `samothius-panel`
- `samothius-youtube`

Typical update flow:

```bash
git pull
sudo systemctl restart samothius-discord samothius-twitch
```

## Game settings

Game parameters (win chances, rewards, cooldowns, boss HP, heist tiers and so on) are stored in the database and read at runtime. Change them from the admin panel under **Settings**. Chance values are fractions between 0 and 1, so write `0.45` for 45%.

## Roadmap

- Fix and update pass on the existing games
- A new game focused on streamer and viewer interaction
- Longer term: package the bot as local software any streamer can run and configure on their own PC
