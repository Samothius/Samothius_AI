import os
from dotenv import load_dotenv

load_dotenv()

def _to_int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

# Discord
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
ANNOUNCEMENT_CHANNEL_ID = _to_int(os.getenv("ANNOUNCEMENT_CHANNEL_ID"))
STREAM_NOTIFICATION_ROLE_ID = _to_int(os.getenv("STREAM_NOTIFICATION_ROLE_ID"))
LOG_THREAD_ID = 1517792028862320640

# Twitch
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
TMI_TOKEN = os.getenv("TMI_TOKEN", "")
STREAMER_NAME = os.getenv("STREAMER_NAME", "samothius").lower()

STREAM_CHECK_INTERVAL_MINUTES = _to_int(os.getenv("STREAM_CHECK_INTERVAL_MINUTES", "5"), 5)

# Chat Overlay (WebSocket bridge from games.py -> browser source)
CHAT_OVERLAY_WS_PORT = _to_int(os.getenv("CHAT_OVERLAY_WS_PORT", "8765"), 8765)
