import os
import sqlite3
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "economy.db")


class DatabaseManager:
    """Common economy database manager for Discord and Twitch."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._setup()

    def _setup(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Table for SamoBit Economy
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER UNIQUE,
                twitch_name TEXT UNIQUE,
                samobit_balance INTEGER DEFAULT 0,
                last_daily TEXT
            )
            """
        )
        
        # New Table for Stream Events (Credits Screen)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stream_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                username TEXT,
                amount INTEGER DEFAULT 1,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Table for Panel-managed bot settings (game balance values)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'float',
                category TEXT,
                description TEXT
            )
        ''')

        # Table for Panel-triggered live commands (boss spawn, games on/off, etc.)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command TEXT NOT NULL,
                payload TEXT,
                status TEXT DEFAULT 'pending',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        self.conn.commit()
        self._seed_default_settings()

    def close(self) -> None:
        self.conn.close()

    # --- BOT SETTINGS (Panel-managed game balance) ---

    DEFAULT_SETTINGS = [
        # key, value, value_type, category, description
        ("gamble_min_bet", "10", "int", "gamble", "Minimum bet amount"),
        ("gamble_jackpot_chance", "0.03", "float", "gamble", "Chance of jackpot (0-1)"),
        ("gamble_jackpot_multiplier", "4", "float", "gamble", "Jackpot payout multiplier"),
        ("gamble_win_chance", "0.35", "float", "gamble", "Chance of normal win, cumulative with jackpot (0-1)"),
        ("gamble_win_multiplier", "1.8", "float", "gamble", "Normal win payout multiplier"),

        ("heist_lobby_seconds", "60", "int", "heist", "Seconds the heist lobby stays open"),
        ("heist_reward_min", "400", "int", "heist", "Min reward per crew member on success"),
        ("heist_reward_max", "900", "int", "heist", "Max reward per crew member on success"),
        ("heist_cooldown_seconds", "180", "int", "heist", "Cooldown per user after a heist resolves"),
        ("heist_prison_seconds", "600", "int", "heist", "Prison duration on heist failure"),

        ("rob_success_chance", "0.40", "float", "rob", "Chance the rob succeeds (0-1)"),
        ("rob_steal_percent", "0.20", "float", "rob", "Percent of target's balance stolen on success"),
        ("rob_penalty_percent", "0.15", "float", "rob", "Percent of robber's own balance lost on failure"),
        ("rob_penalty_min", "50", "int", "rob", "Minimum penalty on failure"),
        ("rob_penalty_max", "1000", "int", "rob", "Maximum penalty on failure"),
        ("rob_cooldown_seconds", "300", "int", "rob", "Cooldown per user after a rob attempt"),
        ("rob_min_target_balance", "50", "int", "rob", "Minimum balance a target must have to be robbed"),

        ("fish_anchovy_min", "100", "int", "fish", "Anchovy tier min reward"),
        ("fish_anchovy_max", "500", "int", "fish", "Anchovy tier max reward"),
        ("fish_seabream_min", "500", "int", "fish", "Sea Bream tier min reward"),
        ("fish_seabream_max", "2000", "int", "fish", "Sea Bream tier max reward"),
        ("fish_bluefish_min", "2000", "int", "fish", "Bluefish tier min reward"),
        ("fish_bluefish_max", "10000", "int", "fish", "Bluefish tier max reward"),
        ("fish_salmon_min", "10000", "int", "fish", "Norwegian Salmon tier min reward"),
        ("fish_salmon_max", "50000", "int", "fish", "Norwegian Salmon tier max reward"),
        ("fish_treasure_min", "20000", "int", "fish", "Treasure Chest tier min reward"),
        ("fish_treasure_max", "50000", "int", "fish", "Treasure Chest tier max reward"),
        ("fish_rare_pool_base", "10.0", "float", "fish", "Base % chance pool for rare tiers (no buff)"),
        ("fish_rare_pool_personal_buff", "30.0", "float", "fish", "Rare pool % with personal Fish Buff"),
        ("fish_rare_pool_global_buff", "20.0", "float", "fish", "Rare pool % with Global Fish Buff"),

        ("boss_hp_min", "300", "int", "boss", "Minimum boss HP"),
        ("boss_hp_max", "1000", "int", "boss", "Maximum boss HP"),
        ("boss_reward_ratio", "0.6", "float", "boss", "Reward pool = boss_max_hp * this ratio, split among attackers"),
        ("boss_reward_min", "200", "int", "boss", "Minimum reward per attacker"),
        ("boss_reward_max", "800", "int", "boss", "Maximum reward per attacker"),

        ("daily_reward", "200", "int", "economy", "Reward for !daily"),
        ("first_reward", "500", "int", "economy", "Reward for !first"),

        ("games_enabled", "true", "bool", "control", "Master on/off switch for game commands"),
    ]

    def _seed_default_settings(self) -> None:
        cursor = self.conn.cursor()
        for key, value, value_type, category, description in self.DEFAULT_SETTINGS:
            cursor.execute(
                "INSERT OR IGNORE INTO bot_settings (key, value, value_type, category, description) VALUES (?, ?, ?, ?, ?)",
                (key, value, value_type, category, description),
            )
        self.conn.commit()

    @staticmethod
    def _cast_setting(value: str, value_type: str):
        if value_type == "int":
            return int(value)
        if value_type == "float":
            return float(value)
        if value_type == "bool":
            return value.lower() in ("true", "1", "yes")
        return value

    def get_setting(self, key: str, default=None):
        cursor = self.conn.cursor()
        cursor.execute("SELECT value, value_type FROM bot_settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        if not result:
            return default
        value, value_type = result
        return self._cast_setting(value, value_type)

    def set_setting(self, key: str, value) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("SELECT value_type FROM bot_settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        if not result:
            return False
        cursor.execute("UPDATE bot_settings SET value = ? WHERE key = ?", (str(value), key))
        self.conn.commit()
        return True

    def get_all_settings(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT key, value, value_type, category, description FROM bot_settings ORDER BY category, key")
        return cursor.fetchall()

    # --- BOT COMMANDS (Panel-triggered live actions) ---

    def create_command(self, command: str, payload: str = None) -> None:
        cursor = self.conn.cursor()
        cursor.execute("INSERT INTO bot_commands (command, payload) VALUES (?, ?)", (command, payload))
        self.conn.commit()

    def get_pending_commands(self) -> list:
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, command, payload FROM bot_commands WHERE status = \'pending\' ORDER BY created_at ASC")
        return cursor.fetchall()

    def mark_command_done(self, command_id: int) -> None:
        cursor = self.conn.cursor()
        cursor.execute("UPDATE bot_commands SET status = \'done\' WHERE id = ?", (command_id,))
        self.conn.commit()

    # --- ECONOMY METHODS ---

    def get_balance_by_discord_id(self, discord_id: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT samobit_balance FROM users WHERE discord_id = ?",
            (discord_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else 0

    def get_balance_by_twitch_name(self, twitch_name: str) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT samobit_balance FROM users WHERE twitch_name = ?",
            (twitch_name.lower(),),
        )
        result = cursor.fetchone()
        return result[0] if result else 0

    def add_samobit_by_twitch_name(self, twitch_name: str, amount: int) -> None:
        cursor = self.conn.cursor()
        twitch_name = twitch_name.lower()
        cursor.execute(
            """
            INSERT INTO users (twitch_name, samobit_balance)
            VALUES (?, ?)
            ON CONFLICT(twitch_name)
            DO UPDATE SET samobit_balance = samobit_balance + ?
            """,
            (twitch_name, amount, amount),
        )
        self.conn.commit()

    def user_exists_by_twitch_name(self, twitch_name: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM users WHERE twitch_name = ?",
            (twitch_name.lower(),),
        )
        return cursor.fetchone() is not None

    def register_twitch_user(self, twitch_name: str, initial_balance: int = 0) -> bool:
        """Returns True if newly created, False if already existed."""
        twitch_name = twitch_name.lower()
        if self.user_exists_by_twitch_name(twitch_name):
            return False
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO users (twitch_name, samobit_balance) VALUES (?, ?)",
            (twitch_name, initial_balance),
        )
        self.conn.commit()
        return True

    def link_discord_twitch(self, discord_id: int, twitch_name: str) -> None:
        cursor = self.conn.cursor()
        twitch_name = twitch_name.lower()
        cursor.execute(
            """
            INSERT INTO users (discord_id, twitch_name)
            VALUES (?, ?)
            ON CONFLICT(twitch_name)
            DO UPDATE SET discord_id = ?
            """,
            (discord_id, twitch_name, discord_id),
        )
        self.conn.commit()

    def get_twitch_name_by_discord_id(self, discord_id: int) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT twitch_name FROM users WHERE discord_id = ?",
            (discord_id,),
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_total_users(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        result = cursor.fetchone()
        return result[0] if result else 0

    def get_total_samobit_volume(self) -> int:
        cursor = self.conn.cursor()
        cursor.execute("SELECT SUM(samobit_balance) FROM users")
        result = cursor.fetchone()
        return result[0] if result and result[0] is not None else 0

    def get_last_daily(self, twitch_name: str) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT last_daily FROM users WHERE twitch_name = ?", (twitch_name.lower(),))
        result = cursor.fetchone()
        return result[0] if result else None

    def set_last_daily(self, twitch_name: str, timestamp: str) -> None:
        cursor = self.conn.cursor()
        twitch_name = twitch_name.lower()
        cursor.execute(
            """
            INSERT INTO users (twitch_name, last_daily)
            VALUES (?, ?)
            ON CONFLICT(twitch_name)
            DO UPDATE SET last_daily = ?
            """,
            (twitch_name, timestamp, timestamp),
        )
        self.conn.commit()

    BLACKLISTED_USERS = {
    "samothius_ai",
    "streamelements",
    "fossabot",
    "nightbot",
    "moobot",
    "streamlabs",
    }

    def get_top_richest_users(self, limit: int = 10) -> list:
        cursor = self.conn.cursor()
        placeholders = ",".join("?" * len(self.BLACKLISTED_USERS))
        cursor.execute(
            f"SELECT twitch_name, samobit_balance FROM users "
            f"WHERE twitch_name NOT IN ({placeholders}) "
            f"ORDER BY samobit_balance DESC LIMIT ?",
            (*self.BLACKLISTED_USERS, limit)
        )
        return cursor.fetchall()

    def search_users(self, query: str, limit: int = 20) -> list:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT twitch_name, samobit_balance FROM users WHERE twitch_name LIKE ? ORDER BY samobit_balance DESC LIMIT ?",
            (f"%{query.lower()}%", limit)
        )
        return cursor.fetchall()

    def set_balance(self, twitch_name: str, new_balance: int) -> None:
        cursor = self.conn.cursor()
        twitch_name = twitch_name.lower()
        cursor.execute(
            """
            INSERT INTO users (twitch_name, samobit_balance)
            VALUES (?, ?)
            ON CONFLICT(twitch_name)
            DO UPDATE SET samobit_balance = ?
            """,
            (twitch_name, new_balance, new_balance),
        )
        self.conn.commit()

    # --- STREAM EVENTS (CREDITS) METHODS ---
    
    def log_event(self, event_type: str, username: str, amount: int = 1) -> None:
        """
        Logs a stream event. 
        event_type can be: 'subscriber', 'follower', or 'gift'.
        """
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO stream_events (event_type, username, amount)
            VALUES (?, ?, ?)
        ''', (event_type, username, amount))
        self.conn.commit()

    def get_events_by_type(self, event_type: str) -> list:
        """Retrieves all events of a specific type for the current session."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT username, amount FROM stream_events 
            WHERE event_type = ? 
            ORDER BY timestamp ASC
        ''', (event_type,))
        return cursor.fetchall()
        
    def get_top_gifters(self) -> list:
        """Groups and sums gifted subs by user for the credits screen."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT username, SUM(amount) as total_gifts 
            FROM stream_events 
            WHERE event_type = 'gift' 
            GROUP BY username 
            ORDER BY total_gifts DESC
        ''')
        return cursor.fetchall()

    def clear_session_events(self) -> None:
        """
        Clears the event log. 
        We will use this command to reset the credits screen for the next stream.
        """
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM stream_events')
        self.conn.commit()
