import time
import aiohttp

from config import YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class YouTubeAuthManager:
    def __init__(self):
        self._access_token = None
        self._expires_at = 0

    async def get_access_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token

        async with aiohttp.ClientSession() as session:
            payload = {
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "refresh_token": YOUTUBE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            }
            async with session.post(GOOGLE_TOKEN_URL, data=payload) as resp:
                data = await resp.json()
                if resp.status != 200:
                    raise RuntimeError(f"YouTube token refresh failed: {data}")

                self._access_token = data["access_token"]
                self._expires_at = time.time() + data.get("expires_in", 3600)
                print("YouTube access token refreshed.")
                return self._access_token
