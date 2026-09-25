"""
Generates a Twitch user access + refresh token and writes it to .env automatically.
Run: python3 get_token.py
Approve the URL that opens in your browser; the tokens are saved automatically.
"""
import asyncio
import aiohttp
from aiohttp import web
import os
from dotenv import load_dotenv
from token_manager import _update_env_value

load_dotenv()
CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
REDIRECT_URI = "http://localhost:3000"
SCOPES = "channel:read:redemptions chat:read chat:edit"

auth_code = None

async def handle_callback(request):
    global auth_code
    auth_code = request.rel_url.query.get("code")
    if auth_code:
        return web.Response(text="Token received! You can close this tab and go back to SSH.")
    return web.Response(text="Could not get code.")

async def main():
    global auth_code

    which = input("Which token is this for? [tmi/eventsub]: ").strip().lower()
    if which == "tmi":
        token_key, refresh_key = "TMI_TOKEN", "TMI_REFRESH_TOKEN"
    elif which == "eventsub":
        token_key, refresh_key = "EVENTSUB_TOKEN", "EVENTSUB_REFRESH_TOKEN"
    else:
        print("Invalid choice, enter 'tmi' or 'eventsub'.")
        return

    app = web.Application()
    app.router.add_get("/", handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 3000)
    await site.start()

    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES.replace(' ', '+')}"
    )
    print(f"\nOpen this URL in your browser:\n{auth_url}\n")

    print("Waiting for Twitch authorization...")
    while auth_code is None:
        await asyncio.sleep(0.5)

    await runner.cleanup()

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
            }
        )
        data = await resp.json()

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")

    if access_token and refresh_token:
        _update_env_value(token_key, access_token)
        _update_env_value(refresh_key, refresh_token)
        print(f"\n{token_key} and {refresh_key} written to .env automatically!")
    else:
        print(f"Could not get token: {data}")

asyncio.run(main())
