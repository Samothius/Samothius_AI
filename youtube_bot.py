import asyncio
import random
import time
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import YOUTUBE_CHANNEL_ID
from database import DatabaseManager
from youtube_token_manager import YouTubeAuthManager

CURRENCY_LABEL = "SamoBit"

FISH_COOLDOWN_SECONDS = 60


class SamothiusYouTubeBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.auth = YouTubeAuthManager()

        self.live_chat_id = None
        self.next_page_token = None

        self.cooldowns = {}
        self.first_claimer = None
        self.fish_last_used = {}

        # display_name.lower() -> channel_id, built up as chat messages arrive
        self.known_users = {}

    # --- YOUTUBE CLIENT (google-api-python-client, proven to work against liveChatMessages) ---
    async def _get_client(self):
        token = await self.auth.get_access_token()
        creds = Credentials(token=token)
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    async def send_message(self, text: str):
        if not self.live_chat_id:
            return
        try:
            youtube = await self._get_client()
            await asyncio.to_thread(
                youtube.liveChatMessages()
                .insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "liveChatId": self.live_chat_id,
                            "type": "textMessageEvent",
                            "textMessageDetails": {"messageText": text},
                        }
                    },
                )
                .execute
            )
        except HttpError as e:
            print(f"⚠️ Failed to send YouTube message: {e}")

    # --- FINDING THE ACTIVE LIVE CHAT ---
    async def _find_live_chat_id(self):
        while True:
            try:
                youtube = await self._get_client()
                data = await asyncio.to_thread(
                    youtube.liveBroadcasts()
                    .list(part="snippet", broadcastStatus="active", broadcastType="all")
                    .execute
                )
                items = data.get("items", [])
                if items:
                    chat_id = items[0]["snippet"].get("liveChatId")
                    if chat_id:
                        print(f"✅ Found active YouTube live chat: {chat_id}")
                        return chat_id
            except Exception as e:
                print(f"⚠️ Error while looking for active broadcast: {e}")
            await asyncio.sleep(30)

    # --- HELPER FUNCTIONS (mirrors games.py exactly) ---
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

    def _games_enabled(self) -> bool:
        return self.db.get_setting("games_enabled", True)

    def _resolve_target(self, name: str):
        return self.known_users.get(name.lstrip("@").lower())

    # --- MAIN POLL LOOP ---
    async def run(self):
        self.live_chat_id = await self._find_live_chat_id()
        while True:
            try:
                youtube = await self._get_client()
                kwargs = {"liveChatId": self.live_chat_id, "part": "snippet,authorDetails"}
                if self.next_page_token:
                    kwargs["pageToken"] = self.next_page_token

                data = await asyncio.to_thread(youtube.liveChatMessages().list(**kwargs).execute)
                self.next_page_token = data.get("nextPageToken")
                polling_interval_ms = data.get("pollingIntervalMillis", 5000)

                for item in data.get("items", []):
                    await self._handle_message(item)

                await asyncio.sleep(polling_interval_ms / 1000)
            except Exception as e:
                print(f"⚠️ Error in YouTube poll loop: {e}")
                await asyncio.sleep(10)

    async def _handle_message(self, item):
        snippet = item.get("snippet", {})
        author = item.get("authorDetails", {})

        if snippet.get("type") != "textMessageEvent":
            return

        text = snippet.get("textMessageDetails", {}).get("messageText", "")
        channel_id = author.get("channelId")
        display_name = author.get("displayName", "someone")

        if not channel_id or not text.startswith("!"):
            return

        self.known_users[display_name.lower()] = channel_id

        parts = text.strip().split()
        command = parts[0][1:].lower()
        args = parts[1:]

        handler = {
            "gamble": self._cmd_gamble,
            "daily": self._cmd_daily,
            "rob": self._cmd_rob,
            "gift": self._cmd_gift,
            "first": self._cmd_first,
            "fish": self._cmd_fish,
            "samobit": self._cmd_samobit,
        }.get(command)

        if handler:
            await handler(channel_id, display_name, args)

    # --- COMMANDS (mirrors games.py exactly, using db.get_setting for shared config) ---
    async def _cmd_samobit(self, channel_id, display_name, args):
        if args and args[0].lower() == "balance":
            bal = self.db.get_balance_by_youtube_id(channel_id)
            await self.send_message(f"@{display_name}, you currently have {bal} {CURRENCY_LABEL}")

    async def _cmd_daily(self, channel_id, display_name, args):
        now = datetime.now(timezone.utc)
        last = self.db.get_last_daily_youtube(channel_id)
        if last:
            last_dt = datetime.fromisoformat(last)
            diff = now - last_dt
            if diff.total_seconds() < 86400:
                remaining_h = int((86400 - diff.total_seconds()) / 3600)
                remaining_m = int(((86400 - diff.total_seconds()) % 3600) / 60)
                await self.send_message(f"@{display_name}, your next daily is in {remaining_h}h {remaining_m}m.")
                return
        self.db.increment_command_usage("daily")
        reward = self.db.get_setting("daily_reward", 200)
        self.db.add_samobit_by_youtube_id(channel_id, reward)
        self.db.set_last_daily_youtube(channel_id, now.isoformat())
        bal = self.db.get_balance_by_youtube_id(channel_id)
        await self.send_message(f"☀️ @{display_name} claimed their daily {reward} {CURRENCY_LABEL}! Balance: {bal} {CURRENCY_LABEL}")

    async def _cmd_gamble(self, channel_id, display_name, args):
        if not self._games_enabled():
            await self.send_message(f"@{display_name}, games are currently disabled.")
            return
        if not args:
            await self.send_message(f"@{display_name}, usage: !gamble <amount>")
            return
        try:
            amount = int(args[0])
        except ValueError:
            await self.send_message(f"@{display_name}, amount must be a number.")
            return

        self.db.increment_command_usage("gamble")
        remaining = self._get_remaining_cooldown("gamble", channel_id)
        if remaining:
            await self.send_message(f"@{display_name}, try again in {remaining} seconds.")
            return

        bal = self.db.get_balance_by_youtube_id(channel_id)
        min_bet = self.db.get_setting("gamble_min_bet", 10)
        if amount < min_bet:
            await self.send_message(f"@{display_name}, minimum bet is {min_bet} {CURRENCY_LABEL}")
            return
        if amount > bal:
            await self.send_message(f"@{display_name}, insufficient balance.")
            return

        self._set_cooldown("gamble", channel_id)
        self.db.add_samobit_by_youtube_id(channel_id, -amount)
        roll = random.random()

        jackpot_chance = self.db.get_setting("gamble_jackpot_chance", 0.03)
        jackpot_mult = self.db.get_setting("gamble_jackpot_multiplier", 4)
        win_chance = self.db.get_setting("gamble_win_chance", 0.35)
        win_mult = self.db.get_setting("gamble_win_multiplier", 1.8)

        if roll < jackpot_chance:
            winnings = int(amount * jackpot_mult)
            self.db.add_samobit_by_youtube_id(channel_id, winnings)
            bal = self.db.get_balance_by_youtube_id(channel_id)
            await self.send_message(f"JACKPOT @{display_name}! Net +{winnings - amount} {CURRENCY_LABEL} Balance: {bal} {CURRENCY_LABEL}")
        elif roll < win_chance:
            winnings = int(amount * win_mult)
            self.db.add_samobit_by_youtube_id(channel_id, winnings)
            bal = self.db.get_balance_by_youtube_id(channel_id)
            await self.send_message(f"@{display_name} won! Net +{amount} {CURRENCY_LABEL} Balance: {bal} {CURRENCY_LABEL}")
        else:
            bal = self.db.get_balance_by_youtube_id(channel_id)
            await self.send_message(f"@{display_name} lost. -{amount} {CURRENCY_LABEL} Balance: {bal} {CURRENCY_LABEL}")

    async def _cmd_rob(self, channel_id, display_name, args):
        if not self._games_enabled():
            await self.send_message(f"@{display_name}, games are currently disabled.")
            return
        self.db.increment_command_usage("rob")
        if not args:
            await self.send_message(f"@{display_name}, usage: !rob <display name>")
            return

        target_id = self._resolve_target(args[0])
        target_name = args[0].lstrip("@")
        if not target_id:
            await self.send_message(f"@{display_name}, couldn't find {target_name} in chat.")
            return
        if target_id == channel_id:
            await self.send_message(f"@{display_name}, you can't rob yourself!")
            return

        remaining = self._get_remaining_cooldown("rob", channel_id)
        if remaining:
            await self.send_message(f"@{display_name}, rob cooldown: {remaining}s.")
            return

        min_target_balance = self.db.get_setting("rob_min_target_balance", 50)
        target_bal = self.db.get_balance_by_youtube_id(target_id)
        if target_bal < min_target_balance:
            await self.send_message(f"@{display_name}, {target_name} doesn't have enough {CURRENCY_LABEL} to rob (min {min_target_balance}).")
            return

        cooldown_seconds = self.db.get_setting("rob_cooldown_seconds", 300)
        self._set_cooldown("rob", channel_id, seconds=cooldown_seconds)
        steal_percent = self.db.get_setting("rob_steal_percent", 0.20)
        success_chance = self.db.get_setting("rob_success_chance", 0.40)
        steal = int(target_bal * steal_percent)

        if random.random() < success_chance:
            self.db.add_samobit_by_youtube_id(target_id, -steal)
            self.db.add_samobit_by_youtube_id(channel_id, steal)
            bal = self.db.get_balance_by_youtube_id(channel_id)
            await self.send_message(f"🦹 @{display_name} successfully robbed {target_name} for {steal} {CURRENCY_LABEL}! Balance: {bal} {CURRENCY_LABEL}")
        else:
            penalty_percent = self.db.get_setting("rob_penalty_percent", 0.15)
            penalty_min = self.db.get_setting("rob_penalty_min", 50)
            penalty_max = self.db.get_setting("rob_penalty_max", 1000)
            robber_balance = self.db.get_balance_by_youtube_id(channel_id)
            penalty = max(penalty_min, min(int(robber_balance * penalty_percent), penalty_max))
            actual_penalty = min(penalty, robber_balance)
            self.db.add_samobit_by_youtube_id(channel_id, -actual_penalty)
            await self.send_message(f"🚨 @{display_name} got caught trying to rob {target_name}! Penalty: -{actual_penalty} {CURRENCY_LABEL}.")

    async def _cmd_gift(self, channel_id, display_name, args):
        self.db.increment_command_usage("gift")
        if len(args) < 2:
            await self.send_message(f"@{display_name}, usage: !gift <display name> <amount>")
            return

        target_id = self._resolve_target(args[0])
        target_name = args[0].lstrip("@")
        try:
            amount = int(args[1])
        except ValueError:
            await self.send_message(f"@{display_name}, amount must be a number.")
            return

        if not target_id:
            await self.send_message(f"@{display_name}, couldn't find {target_name} in chat.")
            return
        if target_id == channel_id:
            await self.send_message(f"@{display_name}, you can't gift yourself!")
            return
        if amount < 10:
            await self.send_message(f"@{display_name}, minimum gift is 10 {CURRENCY_LABEL}.")
            return
        if amount > self.db.get_balance_by_youtube_id(channel_id):
            await self.send_message(f"@{display_name}, insufficient balance.")
            return

        self.db.add_samobit_by_youtube_id(channel_id, -amount)
        self.db.add_samobit_by_youtube_id(target_id, amount)
        await self.send_message(f"🎁 @{display_name} gifted {amount} {CURRENCY_LABEL} to {target_name}!")

    async def _cmd_first(self, channel_id, display_name, args):
        if self.first_claimer is not None:
            await self.send_message(f"Reward for !first already given to {self.first_claimer}.")
            return
        self.first_claimer = display_name
        self.db.increment_command_usage("first")
        reward = self.db.get_setting("first_reward", 500)
        self.db.add_samobit_by_youtube_id(channel_id, reward)
        bal = self.db.get_balance_by_youtube_id(channel_id)
        await self.send_message(f"🥇 @{display_name} was FIRST in chat today! +{reward} {CURRENCY_LABEL}! Balance: {bal} {CURRENCY_LABEL}")

    async def _cmd_fish(self, channel_id, display_name, args):
        if not self._games_enabled():
            await self.send_message(f"@{display_name}, games are currently disabled.")
            return
        self.db.increment_command_usage("fish")

        remaining = FISH_COOLDOWN_SECONDS - (time.time() - self.fish_last_used.get(channel_id, 0))
        if remaining > 0:
            await self.send_message(f"@{display_name}, you already fished recently! Wait {int(remaining)}s.")
            return
        self.fish_last_used[channel_id] = time.time()

        roll = random.random() * 100

        base_pool = self.db.get_setting("fish_rare_pool_base", 10.0)
        anchovy_min = self.db.get_setting("fish_anchovy_min", 100)
        anchovy_max_reward = self.db.get_setting("fish_anchovy_max", 500)
        seabream_min = self.db.get_setting("fish_seabream_min", 500)
        seabream_max = self.db.get_setting("fish_seabream_max", 2000)
        bluefish_min = self.db.get_setting("fish_bluefish_min", 2000)
        bluefish_max = self.db.get_setting("fish_bluefish_max", 10000)
        salmon_min = self.db.get_setting("fish_salmon_min", 10000)
        salmon_max = self.db.get_setting("fish_salmon_max", 50000)
        treasure_min = self.db.get_setting("fish_treasure_min", 20000)
        treasure_max = self.db.get_setting("fish_treasure_max", 50000)

        rare_pool = base_pool
        anchovy_max = 100.0 - rare_pool

        if roll < anchovy_max:
            tier, reward = "an Anchovy", random.randint(anchovy_min, anchovy_max_reward)
        elif roll < anchovy_max + rare_pool * 0.65:
            tier, reward = "a Sea Bream", random.randint(seabream_min, seabream_max)
        elif roll < anchovy_max + rare_pool * 0.90:
            tier, reward = "a Bluefish", random.randint(bluefish_min, bluefish_max)
        elif roll < anchovy_max + rare_pool * 0.95:
            tier, reward = "a Norwegian Salmon", random.randint(salmon_min, salmon_max)
        else:
            tier, reward = "a Treasure Chest!", random.randint(treasure_min, treasure_max)

        self.db.add_samobit_by_youtube_id(channel_id, reward)
        bal = self.db.get_balance_by_youtube_id(channel_id)
        await self.send_message(f"@{display_name} caught {tier}! +{reward} {CURRENCY_LABEL} Balance: {bal} {CURRENCY_LABEL}")


if __name__ == "__main__":
    bot = SamothiusYouTubeBot()
    asyncio.run(bot.run())
