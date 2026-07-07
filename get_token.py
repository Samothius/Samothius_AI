"""
Tek seferlik kullanım: Twitch user access token üretir.
Çalıştır: python get_token.py
Tarayıcında açılan URL'yi onayla, token otomatik alınır.
"""
import asyncio
import aiohttp
from aiohttp import web
import webbrowser
import os
from dotenv import load_dotenv

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

    # 1. Local server başlat
    app = web.Application()
    app.router.add_get("/", handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", 3000)
    await site.start()

    # 2. Auth URL aç
    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES.replace(' ', '+')}"
    )
    print(f"\n🌐 Şu URL'yi tarayıcında aç:\n{auth_url}\n")

    # 3. Callback bekle
    print("⏳ Twitch onayı bekleniyor...")
    while auth_code is None:
        await asyncio.sleep(0.5)

    await runner.cleanup()

    # 4. Code → Token
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

    token = data.get("access_token")
    if token:
        print(f"\n✅ EVENTSUB_TOKEN={token}")
        print("\n👉 Bu satırı .env dosyana ekle (ya da güncelle):")
        print(f"EVENTSUB_TOKEN={token}")
    else:
        print(f"❌ Token alınamadı: {data}")

asyncio.run(main())
