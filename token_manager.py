import os
import asyncio
import aiohttp

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _update_env_value(key: str, value: str) -> None:
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    os.environ[key] = value


async def _validate_token(access_token: str) -> bool:
    if not access_token:
        return False
    token = access_token.removeprefix("oauth:")
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={"Authorization": f"OAuth {token}"},
        ) as resp:
            return resp.status == 200


async def _refresh_token(refresh_token: str, client_id: str, client_secret: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        ) as resp:
            data = await resp.json()
            if resp.status != 200:
                print(f"⚠️ Token refresh failed: {data}")
                return None, None
            return data.get("access_token"), data.get("refresh_token")


async def ensure_valid_token_async(token_env_key: str, refresh_env_key: str, client_id: str, client_secret: str) -> str:
    current_token = os.environ.get(token_env_key, "")
    if current_token and await _validate_token(current_token):
        return current_token

    refresh_token = os.environ.get(refresh_env_key, "")
    if not refresh_token:
        print(f"⚠️ {token_env_key} geçersiz ve {refresh_env_key} tanımlı değil. Elle get_token.py çalıştırılmalı.")
        return current_token

    print(f"🔄 {token_env_key} süresi dolmuş, otomatik yenileniyor...")
    new_access, new_refresh = await _refresh_token(refresh_token, client_id, client_secret)
    if not new_access:
        print(f"⚠️ {token_env_key} otomatik yenilenemedi. Elle get_token.py çalıştırılmalı.")
        return current_token

    _update_env_value(token_env_key, new_access)
    if new_refresh:
        _update_env_value(refresh_env_key, new_refresh)
    print(f"✅ {token_env_key} otomatik olarak yenilendi.")
    return new_access


def ensure_valid_token(token_env_key: str, refresh_env_key: str, client_id: str, client_secret: str) -> str:
    """Bot event loop'u başlamadan önce, senkron bağlamda kullanım için."""
    return asyncio.run(ensure_valid_token_async(token_env_key, refresh_env_key, client_id, client_secret))
