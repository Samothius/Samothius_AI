from datetime import timedelta, datetime, timezone
import random
import time
import asyncio
import json
import re
import websockets
import aiohttp
from twitchio.ext import commands, routines

BANNED_PHRASES = [
    "ai viewers",
    "ai followers",
    "buy viewers",
    "buy followers",
    "cheap viewers",
    "cheap followers",
    "bigfollows",
    "become famous",
    "viewbot",
    "follower bot",
    "boost your stream",
    "boost viewers",
    "boost followers",
    "grow your channel",
    "grow your stream",
    "get more viewers",
    "increase your viewers",
    "twitch promotion",
    "stream promotion",
    "buy prime subs",
    "cheap subs",
    "add me on discord",
    "add my discord",
    "hit me up on discord",
    "friend me on discord",
    "dm me on discord",
    "msg me on discord",
    "like your gameplay add me",
    "love your stream add me",
    "discord username is",
    "my discord tag",
    "do your graphics",
    "cheap emotes",
    "custom stream overlay"
    "streamboo.com"
    "streamboo. com"
    "streamboo .com"
]

# --- GAME SETTINGS ---
CURRENCY_NAME = "SamoBit"
GAMBLE_MIN_BET = 10
HEIST_LOBBY_SECONDS = 60
HEIST_WIN_MULTIPLIER = 2

# --- CONFIG IMPORTS ---
from config import (
    TMI_TOKEN,
    TWITCH_CLIENT_ID,
    TWITCH_CLIENT_SECRET,
    EVENTSUB_TOKEN,
    STREAMER_NAME,
    CHAT_OVERLAY_WS_PORT,
    SAMOBIT_EMOTE
)
from database import DatabaseManager
from typing import Optional

class SamothiusTwitchBot(commands.Bot):
    def __init__(self):
        super().__init__(
            token=TMI_TOKEN,
            client_id=TWITCH_CLIENT_ID,
            prefix="!",
            initial_channels=[STREAMER_NAME]
        )
        self.db = DatabaseManager()
        
        # Cooldown Memory
        self.cooldowns = {}
        
        # Boss Event Memory
        self.boss_state = "IDLE"
        self.current_boss = None
        self.boss_hp = 0
        self.participants = set()
        
        # Heist Event Memory
        self.heist_lobby_active = False
        self.heist_participants = set()
        self.heist_prison_until = {}
        
        # Chat tracking for engagement loop
        self.chat_active_users = set()
        
        # Chat tracking for Boss spawn logic
        self.boss_active_users = set()

        # !first state (bot restart = yeni stream, tek seferlik)
        self.first_claimer = None

        # Fish buff state (Channel Points ile aktive edilir)
        self.fish_buff_personal = {}    # {username: expires_at_timestamp}
        self.fish_buff_global_until = 0.0

        # Chat Overlay: connected OBS browser-source WebSocket clients
        self.overlay_clients = set()

    async def event_ready(self):
        print(f"✅ Twitch Bot connected as {self.nick}")
        self.gift_samobit_loop.start()
        self.auto_boss_loop.start()
        self.chat_engagement_loop.start()
        self.loop.create_task(self.start_overlay_ws_server())
        self.loop.create_task(self._channel_points_eventsub())

    # --- CHAT OVERLAY WEBSOCKET BRIDGE ---
    async def start_overlay_ws_server(self):
        """Runs a WebSocket server that the OBS browser-source chat overlay
        connects to. Every clean chat message is broadcast to it live."""
        try:
            async with websockets.serve(self._overlay_ws_handler, "0.0.0.0", CHAT_OVERLAY_WS_PORT):
                print(f"✅ Chat overlay WebSocket listening on port {CHAT_OVERLAY_WS_PORT}")
                await asyncio.Future()  # run forever
        except Exception as e:
            print(f"⚠️ Chat overlay WebSocket server failed to start: {e}")

    async def _overlay_ws_handler(self, websocket):
        self.overlay_clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self.overlay_clients.discard(websocket)

    @staticmethod
    def _parse_native_emotes(content, emotes_tag):
        """Parses Twitch's IRC 'emotes' tag, e.g. '25:0-4,12-16/1902:6-10',
        into a list of {id, code, start, end} so the overlay can render the
        official Twitch emote image at the exact position it appeared."""
        emotes = []
        if not emotes_tag:
            return emotes
        try:
            for block in emotes_tag.split('/'):
                if not block:
                    continue
                emote_id, ranges = block.split(':', 1)
                for rng in ranges.split(','):
                    start_str, end_str = rng.split('-')
                    start, end = int(start_str), int(end_str)
                    emotes.append({
                        "id": emote_id,
                        "code": content[start:end + 1],
                        "start": start,
                        "end": end,
                    })
        except Exception as e:
            print(f"⚠️ Failed to parse native emote tag: {e}")
        return emotes

    async def broadcast_chat_message(self, author, content, native_emotes=None):
        if not self.overlay_clients:
            return
        color = getattr(author, "colour", None) or getattr(author, "color", None)
        payload = json.dumps({
            "user": author.display_name or author.name,
            "message": content,
            "color": color,
            "is_mod": bool(author.is_mod),
            "is_vip": bool(author.is_vip),
            "is_broadcaster": author.name.lower() == STREAMER_NAME.lower(),
            "native_emotes": native_emotes or [],
        })
        await asyncio.gather(
            *(client.send(payload) for client in list(self.overlay_clients)),
            return_exceptions=True
        )
        
    async def event_message(self, message):
        if message.echo:
            return
            
        author = message.author
        content = message.content
        content_lower = content.lower() 

        # --- SPAM PROTECTION START ---
        if not author.is_mod and not author.is_vip and author.name.lower() != STREAMER_NAME.lower():
            
            # 1. BOT PHRASE PROTECTION
            if any(phrase in content_lower for phrase in BANNED_PHRASES):
                try:
                    await message.delete()
                    await author.ban(reason="Automated spam bot detection")
                    await message.channel.send(f"🔨 Beep boop! I just banned a spam bot (@{author.name}).")
                except Exception as e:
                    print(f"Failed to ban bot: {e}")
                return 
            
            # 2. LINK PROTECTION
            if re.search(r"(https?://|www\.)[^\s]+", content_lower):
                try:
                    await message.delete()
                    await message.channel.send(f"🚫 @{author.name}, please do not post links!")
                except Exception:
                    pass
                return
            
            # 3. EXCESSIVE CAPS PROTECTION
            if len(content) > 15:
                caps_count = sum(1 for char in content if char.isupper())
                if (caps_count / len(content)) > 0.70:
                    try:
                        await author.timeout(10, reason="Excessive Caps")
                        await message.channel.send(f"🛑 @{author.name}, please turn off your caps lock!")
                    except Exception:
                        pass
                    return
        # --- SPAM PROTECTION END ---

        self.chat_active_users.add(author.name.lower())
        self.boss_active_users.add(author.name.lower())
        tags = getattr(message, "tags", None) or {}
        native_emotes = self._parse_native_emotes(content, tags.get("emotes"))
        await self.broadcast_chat_message(author, content, native_emotes)
        await self.handle_commands(message)
    
    # --- HELPER FUNCTIONS ---
    def _set_cooldown(self, command, user, seconds=120):
        if command not in self.cooldowns:
            self.cooldowns[command] = {}
        self.cooldowns[command][user] = time.time() + seconds

    def _get_remaining_cooldown(self, command, user):
        if command not in self.cooldowns:
            return 0
        end_time = self.cooldowns[command].get(user, 0)
        remaining = int(end_time - time.time())
        return remaining if remaining > 0 else 0

    # --- BACKGROUND LOOPS WITH ERROR PROTECTION ---
    @routines.routine(minutes=5)
    async def gift_samobit_loop(self):
        try:
            chan = self.get_channel(STREAMER_NAME)
            if not chan or not chan.chatters:
                return
            for chatter in chan.chatters:
                self.db.add_samobit_by_twitch_name(chatter.name.lower(), 10)
        except Exception as e:
            print(f"⚠️ Error in gift_samobit_loop: {e}")
            
    @routines.routine(minutes=45)
    async def auto_boss_loop(self):
        try:
            if len(self.boss_active_users) >= 2:
                if self.boss_state == "IDLE":
                    await self.spawn_boss_logic()
                    
            self.boss_active_users.clear()
        except Exception as e:
            print(f"⚠️ Error in auto_boss_loop: {e}")

    @routines.routine(minutes=20)
    async def chat_engagement_loop(self):
        try:
            if len(self.chat_active_users) >= 1:
                messages = [
                    "⚔️ A Boss is lurking in the shadows! Keep an eye on the chat for the portal to open. You have 60 seconds to !attack!",
                    f"🎰 Feeling lucky? Try your chance with !gamble <amount> and double your {CURRENCY_NAME}!",
                    f"🎣 Need some extra {CURRENCY_NAME}? Type !fish to see what you can catch in our channel's waters!",
                    "🦹 Planning a heist? Type !heist to gather your crew and rob the bank. Higher crew size means higher success rate!",
                    f"💰 Don't forget to check your wealth with !samobit balance! Can you reach the top of the leaderboard?",
                    f"☀️ Claim your free daily 200 {CURRENCY_NAME} with !daily — come back every 24 hours!",
                    f"🦹 Feeling bold? Try !rob @username to steal 20% of their {CURRENCY_NAME}. But watch out — you might get caught!",
                    f"🎁 Want to share the wealth? Use !gift @username <amount> to send {CURRENCY_NAME} to a friend!",
                ]
                chan = self.get_channel(STREAMER_NAME)
                if chan:
                    await chan.send(random.choice(messages))
            self.chat_active_users.clear()
        except Exception as e:
            print(f"⚠️ Error in chat_engagement_loop: {e}")

    # --- EVENT LOGIC ---
    async def spawn_boss_logic(self, manual=False):
        self.boss_state = "ACTIVE"
        self.current_boss = random.choice(["Dragon", "Goblin King", "Dark Knight"])
        self.boss_hp = random.randint(300, 1000)
        self.participants.clear()
        
        chan = self.get_channel(STREAMER_NAME)
        if chan:
            await chan.send(
                f"🚨 ⚠️ BOSS SPAWNED ⚠️ 🚨 A wild {self.current_boss} appeared with {self.boss_hp} HP! "
                f"👉 Type !attack NOW to join the fight! You have 60 seconds! ⚔️"
            )
        await asyncio.sleep(60)
        
        if self.boss_state == "ACTIVE":
            if chan:
                if len(self.participants) > 0:
                    # YENİ DÜZELTME: Süre dolduğunda boss ölmemişse, kaçtığını belirtiyoruz.
                    await chan.send(f"💀 Time is up! The {self.current_boss} survived with {self.boss_hp} HP and escaped. Better luck next time!")
                else:
                    await chan.send(f"💀 The {self.current_boss} escaped because no one attacked...")
            self.boss_state = "IDLE"

    async def _resolve_heist_lobby(self, chan):
        await asyncio.sleep(HEIST_LOBBY_SECONDS)
        self.heist_lobby_active = False
        
        if len(self.heist_participants) == 0:
            return
            
        crew_size = len(self.heist_participants)
        success_chance = min(30 + (crew_size * 5), 80)
        roll = random.random() * 100
        
        if roll <= success_chance:
            reward = random.randint(500, 1500) * crew_size
            for p in self.heist_participants:
                self.db.add_samobit_by_twitch_name(p, reward)
            await chan.send(f"🎉 The heist was a SUCCESS! The crew of {crew_size} stole {reward} {SAMOBIT_EMOTE} each!")
        else:
            for p in self.heist_participants:
                self.heist_prison_until[p] = time.time() + 300 
            await chan.send(f"🚨 BUSTED! The heist failed. The crew of {crew_size} was caught and put in prison for 5 minutes!")
            
        self.heist_participants.clear()

    # --- CHANNEL POINTS (EventSub WebSocket) ---
    async def _fetch_broadcaster_id(self) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as session:
                # Önce app access token al
                token_resp = await session.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={
                        "client_id": TWITCH_CLIENT_ID,
                        "client_secret": TWITCH_CLIENT_SECRET,
                        "grant_type": "client_credentials",
                    }
                )
                token_data = await token_resp.json()
                app_token = token_data.get("access_token")
                if not app_token:
                    print(f"⚠️ App token alınamadı: {token_data}")
                    return None

                # Broadcaster ID'yi sorgula
                headers = {
                    "Client-ID": TWITCH_CLIENT_ID,
                    "Authorization": f"Bearer {app_token}",
                }
                resp = await session.get(
                    f"https://api.twitch.tv/helix/users?login={STREAMER_NAME}",
                    headers=headers
                )
                data = await resp.json()
                users = data.get("data", [])
                if users:
                    return users[0]["id"]
        except Exception as e:
            print(f"⚠️ Could not fetch broadcaster ID: {e}")
        return None

    async def _channel_points_eventsub(self):
        """Twitch EventSub WebSocket: Channel Points ödüllerini dinler."""
        EVENTSUB_WS = "wss://eventsub.wss.twitch.tv/ws"
        REWARD_ACTIONS = {
            "Buy 1000 SamoBits": ("samobit", 1000),
            "Buy 5000 SamoBits": ("samobit", 5000),
            "Fish Buff":         ("fish_personal", 7200),   # 2 saat
            "Global Fish Buff":  ("fish_global",   1800),   # 30 dk
        }
        token = EVENTSUB_TOKEN.lstrip("oauth:")
        broadcaster_id = await self._fetch_broadcaster_id()
        if not broadcaster_id:
            print("⚠️ Channel Points EventSub disabled: broadcaster ID alınamadı.")
            return

        while True:
            try:
                async with websockets.connect(EVENTSUB_WS) as ws:
                    # 1. Welcome mesajından session_id al
                    raw = await ws.recv()
                    msg = json.loads(raw)
                    if msg.get("metadata", {}).get("message_type") != "session_welcome":
                        continue
                    session_id = msg["payload"]["session"]["id"]

                    # 2. Channel Points redemption subscribe
                    sub_url = "https://api.twitch.tv/helix/eventsub/subscriptions"
                    headers = {
                        "Client-ID": TWITCH_CLIENT_ID,
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    }
                    body = {
                        "type": "channel.channel_points_custom_reward_redemption.add",
                        "version": "1",
                        "condition": {"broadcaster_user_id": broadcaster_id},
                        "transport": {"method": "websocket", "session_id": session_id},
                    }
                    async with aiohttp.ClientSession() as http:
                        async with http.post(sub_url, headers=headers, json=body) as resp:
                            if resp.status not in (200, 202):
                                text = await resp.text()
                                print(f"⚠️ EventSub subscription failed ({resp.status}): {text}")
                                return
                            print("✅ Channel Points EventSub aktif!")

                    # 3. Olayları dinle
                    async for raw in ws:
                        msg = json.loads(raw)
                        mtype = msg.get("metadata", {}).get("message_type", "")

                        if mtype == "session_keepalive":
                            continue
                        if mtype == "session_reconnect":
                            break  # döngü yeniden bağlanacak

                        if mtype == "notification":
                            event = msg.get("payload", {}).get("event", {})
                            reward_title = event.get("reward", {}).get("title", "")
                            redeemer = event.get("user_login", "").lower()
                            action = REWARD_ACTIONS.get(reward_title)
                            if not action:
                                continue
                            chan = self.get_channel(STREAMER_NAME)
                            kind, value = action

                            if kind == "samobit":
                                self.db.add_samobit_by_twitch_name(redeemer, value)
                                if chan:
                                    await chan.send(
                                        f"  🎉 @{redeemer} redeemed '{reward_title}' and received "
                                        f"{value} {SAMOBIT_EMOTE}! "
                                        f"Balance: {self.db.get_balance_by_twitch_name(redeemer)} {SAMOBIT_EMOTE}"
                                    )
                            elif kind == "fish_personal":
                                self.fish_buff_personal[redeemer] = time.time() + value
                                if chan:
                                    await chan.send(
                                        f"  🎣 @{redeemer} activated Fish Buff! "
                                        f"3x rare fish chance for 2 hours! {SAMOBIT_EMOTE}"
                                    )
                            elif kind == "fish_global":
                                self.fish_buff_global_until = time.time() + value
                                if chan:
                                    await chan.send(
                                        f"  🌊 @{redeemer} activated Global Fish Buff! "
                                        f"2x rare fish chance for EVERYONE for 30 minutes! {SAMOBIT_EMOTE}"
                                    )

            except Exception as e:
                print(f"⚠️ Channel Points EventSub hatası: {e}. 30s sonra yeniden bağlanıyor...")
                await asyncio.sleep(30)

    # --- TWITCH COMMANDS ---
    @commands.command(name="samobit")
    async def samobit(self, ctx):
        user = ctx.author.name.lower()
        msg = ctx.message.content.split()
        if len(msg) > 1 and msg[1].lower() == "balance":
            bal = self.db.get_balance_by_twitch_name(user)
            await ctx.send(f"  @{user}, you currently have {bal} {SAMOBIT_EMOTE}")

    @commands.command(name="bossstatus")
    async def boss_status(self, ctx):
        if self.boss_state == "IDLE":
            await ctx.send("  No active boss right now.")
            return
        await ctx.send(
            f"  Boss: {self.current_boss} | Status: {self.boss_state} | "
            f"Remaining HP: {self.boss_hp} | Participants: {len(self.participants)}"
        )

    @commands.command(name="spawnboss")
    async def spawn_boss(self, ctx):
        user = ctx.author.name.lower()
        if user != STREAMER_NAME.lower():
            await ctx.send("  Only the broadcaster can use this command.")
            return
        if self.boss_state != "IDLE":
            await ctx.send("  There is already an active boss.")
            return
        await ctx.send("  Starting test boss...")
        await self.spawn_boss_logic(manual=True)

    @commands.command(name="attack")
    async def attack(self, ctx):
        user = ctx.author.name.lower()
        if self.boss_state != "ACTIVE":
            await ctx.send(f"  @{user}, there is no active boss to attack right now.")
            return
        if user in self.participants:
            await ctx.send(f"  @{user}, you already attacked the boss!")
            return
        
        self.participants.add(user)
        
        # YENİ DÜZELTME: Hasar hesaplamasında can eksiye düşmemesi için limit koyduk.
        damage = random.randint(50, 150)
        actual_damage = min(damage, self.boss_hp)
        self.boss_hp -= actual_damage
        
        await ctx.send(f"  ⚔️ @{user} dealt {actual_damage} damage to the {self.current_boss}! Remaining HP: {self.boss_hp}")
        
        if self.boss_hp <= 0 and self.boss_state == "ACTIVE":
            self.boss_state = "DEFEATED"
            reward = 500
            for p in self.participants:
                self.db.add_samobit_by_twitch_name(p, reward)
            await ctx.send(f"🎉 The {self.current_boss} was DEFEATED by @{user}! All {len(self.participants)} attackers earned {reward} {SAMOBIT_EMOTE}")
            self.boss_state = "IDLE"

    @commands.command(name="gamble")
    async def gamble(self, ctx, amount: int):
        user = ctx.author.name.lower()
        remaining = self._get_remaining_cooldown("gamble", user)
        if remaining:
            await ctx.send(f"  @{user}, try again in {remaining} seconds.")
            return
            
        bal = self.db.get_balance_by_twitch_name(user)
        if amount < GAMBLE_MIN_BET:
            await ctx.send(f"  @{user}, minimum bet is {GAMBLE_MIN_BET} {SAMOBIT_EMOTE}")
            return
        if amount > bal:
            await ctx.send(f"  @{user}, insufficient balance.")
            return
            
        self._set_cooldown("gamble", user)
        self.db.add_samobit_by_twitch_name(user, -amount)
        roll = random.random()
        
        if roll < 0.05:
            winnings = amount * 5
            self.db.add_samobit_by_twitch_name(user, winnings)
            await ctx.send(
                f"  JACKPOT @{user}! Net +{winnings - amount} {SAMOBIT_EMOTE} "
                f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
            )
        elif roll < 0.45:
            winnings = amount * 2
            self.db.add_samobit_by_twitch_name(user, winnings)
            await ctx.send(
                f"  @{user} won! Net +{amount} {SAMOBIT_EMOTE} "
                f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
            )
        else:
            await ctx.send(
                f"  @{user} lost. -{amount} {SAMOBIT_EMOTE} "
                f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
            )

    @commands.command(name="heist")
    async def heist(self, ctx):
        user = ctx.author.name.lower()
        prison_until = self.heist_prison_until.get(user, 0)
        
        if prison_until > time.time():
            remaining = int((prison_until - time.time()) / 60)
            await ctx.send(f"  @{user}, you are in prison. About {remaining} mins left.")
            return
            
        remaining = self._get_remaining_cooldown("heist", user)
        if remaining:
            await ctx.send(f"  @{user}, heist cooldown: {remaining}s.")
            return
            
        chan = self.get_channel(STREAMER_NAME)
        if not chan:
            return
            
        if not self.heist_lobby_active:
            self.heist_lobby_active = True
            self.heist_participants = {user}
            await ctx.send(
                f"  Heist plan started! Type `!heist` within {HEIST_LOBBY_SECONDS}s to join. "
                f"First: @{user}"
            )
            self.loop.create_task(self._resolve_heist_lobby(chan))
            return
            
        if user in self.heist_participants:
            await ctx.send(f"  @{user}, you are already in the heist crew.")
            return
            
        self.heist_participants.add(user)
        await ctx.send(f"  @{user} joined the heist crew!")

    @commands.command(name="daily")
    async def daily(self, ctx):
        user = ctx.author.name.lower()
        now = datetime.now(timezone.utc)
        last = self.db.get_last_daily(user)
        if last:
            last_dt = datetime.fromisoformat(last)
            diff = now - last_dt
            if diff.total_seconds() < 86400:
                remaining_h = int((86400 - diff.total_seconds()) / 3600)
                remaining_m = int(((86400 - diff.total_seconds()) % 3600) / 60)
                await ctx.send(f"  @{user}, your next daily is in {remaining_h}h {remaining_m}m.")
                return
        self.db.add_samobit_by_twitch_name(user, 200)
        self.db.set_last_daily(user, now.isoformat())
        await ctx.send(
            f"  ☀️ @{user} claimed their daily 200 {SAMOBIT_EMOTE}! "
            f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
        )

    @commands.command(name="rob")
    async def rob(self, ctx):
        user = ctx.author.name.lower()
        parts = ctx.message.content.split()
        if len(parts) < 2:
            await ctx.send(f"  @{user}, usage: !rob @target")
            return
        target = parts[1].lstrip("@").lower()
        if target == user:
            await ctx.send(f"  @{user}, you can't rob yourself!")
            return
        remaining = self._get_remaining_cooldown("rob", user)
        if remaining:
            await ctx.send(f"  @{user}, rob cooldown: {remaining}s.")
            return
        target_bal = self.db.get_balance_by_twitch_name(target)
        if target_bal < 50:
            await ctx.send(f"  @{user}, @{target} doesn't have enough {SAMOBIT_EMOTE} to rob (min 50).")
            return
        self._set_cooldown("rob", user, seconds=300)
        steal = int(target_bal * 0.20)
        if random.random() < 0.40:
            self.db.add_samobit_by_twitch_name(target, -steal)
            self.db.add_samobit_by_twitch_name(user, steal)
            await ctx.send(
                f"  🦹 @{user} successfully robbed @{target} for {steal} {SAMOBIT_EMOTE}! "
                f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
            )
        else:
            penalty = 300
            actual_penalty = min(penalty, self.db.get_balance_by_twitch_name(user))
            self.db.add_samobit_by_twitch_name(user, -actual_penalty)
            await ctx.send(
                f"  🚨 @{user} got caught trying to rob @{target}! "
                f"Penalty: -{actual_penalty} {SAMOBIT_EMOTE}."
            )

    @commands.command(name="gift")
    async def gift(self, ctx):
        user = ctx.author.name.lower()
        parts = ctx.message.content.split()
        if len(parts) < 3:
            await ctx.send(f"  @{user}, usage: !gift @target <amount>")
            return
        target = parts[1].lstrip("@").lower()
        try:
            amount = int(parts[2])
        except ValueError:
            await ctx.send(f"  @{user}, amount must be a number.")
            return
        if target == user:
            await ctx.send(f"  @{user}, you can't gift yourself!")
            return
        if amount < 10:
            await ctx.send(f"  @{user}, minimum gift is 10 {SAMOBIT_EMOTE}.")
            return
        if amount > self.db.get_balance_by_twitch_name(user):
            await ctx.send(f"  @{user}, insufficient balance.")
            return
        self.db.add_samobit_by_twitch_name(user, -amount)
        self.db.add_samobit_by_twitch_name(target, amount)
        await ctx.send(f"  🎁 @{user} gifted {amount} {SAMOBIT_EMOTE} to @{target}!")

    @commands.command(name="first")
    async def first(self, ctx):
        user = ctx.author.name.lower()
        if self.first_claimer is not None:
            await ctx.send(f"  Reward for !first already given to @{self.first_claimer}.")
            return
        self.first_claimer = user
        self.db.add_samobit_by_twitch_name(user, 500)
        await ctx.send(
            f"  🥇 @{user} was FIRST in chat today! +500 {SAMOBIT_EMOTE}! "
            f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
        )

    @commands.command(name="fish")
    async def fish(self, ctx):
        user = ctx.author.name.lower()
        remaining = self._get_remaining_cooldown("fish", user)
        if remaining:
            await ctx.send(f"  @{user}, wait {remaining}s to fish again.")
            return
            
        self._set_cooldown("fish", user)
        roll = random.random() * 100

        # Buff kontrolü (kişisel buff, global buff'tan önce gelir)
        now = time.time()
        has_personal = self.fish_buff_personal.get(user, 0) > now
        has_global = self.fish_buff_global_until > now

        if has_personal:
            rare_pool = 30.0   # 3x nadir şans
            buff_tag = " ✨[FISH BUFF]"
        elif has_global:
            rare_pool = 20.0   # 2x nadir şans
            buff_tag = " 🌊[GLOBAL BUFF]"
        else:
            rare_pool = 10.0   # normal
            buff_tag = ""

        anchovy_max = 100.0 - rare_pool
        if roll < anchovy_max:
            tier, reward = "an Anchovy", random.randint(100, 500)
        elif roll < anchovy_max + rare_pool * 0.65:
            tier, reward = "a Sea Bream", random.randint(500, 2000)
        elif roll < anchovy_max + rare_pool * 0.90:
            tier, reward = "a Bluefish", random.randint(2000, 10000)
        elif roll < anchovy_max + rare_pool * 0.95:
            tier, reward = "a Norwegian Salmon", random.randint(10000, 50000)
        else:
            tier, reward = "a Treasure Chest!", random.randint(50000, 99999)

        self.db.add_samobit_by_twitch_name(user, reward)
        await ctx.send(
            f"  @{user} caught {tier}!{buff_tag} +{reward} {SAMOBIT_EMOTE} "
            f"Balance: {self.db.get_balance_by_twitch_name(user)} {SAMOBIT_EMOTE}"
        )

if __name__ == "__main__":
    bot = SamothiusTwitchBot()
    bot.run()
