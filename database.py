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
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

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
