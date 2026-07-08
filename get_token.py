"""
Twitch user access + refresh token üretir, otomatik .env'e yazar.
Çalıştır: python3 get_token.py
Tarayıcında açılan URL'yi onayla, tokenlar otomatik kaydedilir.
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
        return web.Response(text="✅ Token alındı! Bu sekmeyi kapatabilirsin. SSH'e dön.")
    return web.Response(text="❌ Kod alınamadı.")

async def main():
    global auth_code

    which = input("Bu token hangisi için? [tmi/eventsub]: ").strip().lower()
    if which == "tmi":
        token_key, refresh_key = "TMI_TOKEN", "TMI_REFRESH_TOKEN"
    elif which == "eventsub":
        token_key, refresh_key = "EVENTSUB_TOKEN", "EVENTSUB_REFRESH_TOKEN"
    else:
        print("❌ Geçersiz seçim, 'tmi' veya 'eventsub' yazmalısın.")
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
    print(f"\n🌐 Şu URL'yi tarayıcında aç:\n{auth_url}\n")

    print("⏳ Twitch onayı bekleniyor...")
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
        print(f"\n✅ {token_key} ve {refresh_key} otomatik olarak .env dosyasına yazıldı!")
    else:
        print(f"❌ Token alınamadı: {data}")

asyncio.run(main())
