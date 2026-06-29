import aiohttp
from config import TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, STREAMER_NAME

class TwitchApiClient:
    def __init__(self):
        self.client_id = TWITCH_CLIENT_ID
        self.client_secret = TWITCH_CLIENT_SECRET
        self.streamer_name = STREAMER_NAME
        self.access_token = None
        self.broadcaster_id = None

    async def _fetch_new_token(self):
        """Fetches a new App Access Token from Twitch and saves it."""
        url = "https://id.twitch.tv/oauth2/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.access_token = data.get("access_token")
                    print("✅ Twitch API Token successfully refreshed!")
                else:
                    print(f"⚠️ Failed to get Twitch token. HTTP Status: {resp.status}")

    async def get_live_stream(self):
        """Checks if the channel is live. Auto-refreshes the token if expired."""
        if not self.access_token:
            await self._fetch_new_token()

        url = f"https://api.twitch.tv/helix/streams?user_login={self.streamer_name}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    print("🔄 Twitch API Token expired. Auto-refreshing...")
                    await self._fetch_new_token()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.get(url, headers=headers) as retry_resp:
                        if retry_resp.status == 200:
                            data = await retry_resp.json()
                            return data.get("data", [])
                        return []
                elif resp.status == 200:
                    data = await resp.json()
                    return data.get("data", [])
                return []

    async def get_broadcaster_id(self):
        """Fetches the Broadcaster ID from the username."""
        if not self.access_token:
            await self._fetch_new_token()
        if self.broadcaster_id:
            return self.broadcaster_id

        url = f"https://api.twitch.tv/helix/users?login={self.streamer_name}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        self.broadcaster_id = data["data"][0]["id"]
                        return self.broadcaster_id
        return None

    async def get_latest_clip(self):
        """Fetches the latest clip from the channel (Ready for future use)."""
        b_id = await self.get_broadcaster_id()
        if not b_id:
            return None

        url = f"https://api.twitch.tv/helix/clips?broadcaster_id={b_id}&first=1"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 401:
                    await self._fetch_new_token()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    async with session.get(url, headers=headers) as retry_resp:
                        if retry_resp.status == 200:
                            data = await retry_resp.json()
                            if data.get("data"):
                                return data["data"][0]
                elif resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        return data["data"][0]
        return None
