import random
import time
from datetime import datetime, timezone

DAILY_COOLDOWN_SECONDS = 86400
ROB_COOLDOWN_SECONDS = 1800


def cmd_samobit(db, platform: str, user_id: str, display_name: str) -> str:
    balance = db.get_balance(platform, user_id)
    return f"@{display_name}, bakiyen: {balance} SamoBit"


def cmd_daily(db, platform: str, user_id: str, display_name: str) -> str:
    last_daily = db.get_last_daily_generic(platform, user_id)
    now = datetime.now(timezone.utc)

    if last_daily:
        last_dt = datetime.fromisoformat(last_daily)
        elapsed = (now - last_dt).total_seconds()
        if elapsed < DAILY_COOLDOWN_SECONDS:
            remaining = int(DAILY_COOLDOWN_SECONDS - elapsed)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            return f"@{display_name}, günlük ödülünü zaten aldın. Kalan süre: {hours}s {minutes}dk"

    reward = random.randint(100, 300)
    db.add_balance(platform, user_id, reward)
    db.set_last_daily_generic(platform, user_id, now.isoformat())
    return f"@{display_name}, günlük ödülün: {reward} SamoBit!"


def cmd_gamble(db, platform: str, user_id: str, display_name: str, amount: int) -> str:
    if amount <= 0:
        return f"@{display_name}, geçerli bir miktar gir."

    balance = db.get_balance(platform, user_id)
    if amount > balance:
        return f"@{display_name}, yetersiz bakiye. Bakiyen: {balance} SamoBit"

    win_chance = 0.35
    jackpot_chance = 0.04

    roll = random.random()
    if roll < jackpot_chance:
        winnings = amount * 4
        db.add_balance(platform, user_id, winnings)
        return f"🎰 JACKPOT! @{display_name}, {winnings} SamoBit kazandın!"
    elif roll < jackpot_chance + win_chance:
        winnings = int(amount * 1.8)
        db.add_balance(platform, user_id, winnings)
        return f"@{display_name}, kazandın! {winnings} SamoBit kazandın."
    else:
        db.add_balance(platform, user_id, -amount)
        return f"@{display_name}, kaybettin. {amount} SamoBit kaybettin."


def cmd_rob(db, platform: str, user_id: str, display_name: str, target_user_id: str, target_display_name: str, last_rob_times: dict) -> str:
    now = time.time()
    last_rob = last_rob_times.get((platform, user_id), 0)
    elapsed = now - last_rob
    if elapsed < ROB_COOLDOWN_SECONDS:
        remaining = int(ROB_COOLDOWN_SECONDS - elapsed)
        minutes = remaining // 60
        seconds = remaining % 60
        return f"@{display_name}, soygun için beklemen lazım: {minutes}dk {seconds}sn"

    target_balance = db.get_balance(platform, target_user_id)
    if target_balance < 50:
        return f"@{display_name}, {target_display_name} soyulamayacak kadar fakir."

    last_rob_times[(platform, user_id)] = now

    success = random.random() < 0.5
    if success:
        stolen = max(50, min(1000, int(target_balance * 0.15)))
        db.add_balance(platform, target_user_id, -stolen)
        db.add_balance(platform, user_id, stolen)
        return f"@{display_name}, {target_display_name}'den {stolen} SamoBit çaldın!"
    else:
        balance = db.get_balance(platform, user_id)
        penalty = max(50, min(1000, int(balance * 0.15)))
        db.add_balance(platform, user_id, -penalty)
        return f"@{display_name}, soygun başarısız! {penalty} SamoBit kaybettin."


def cmd_gift(db, platform: str, sender_id: str, sender_display_name: str, target_user_id: str, target_display_name: str, amount: int) -> str:
    if amount <= 0:
        return f"@{sender_display_name}, geçerli bir miktar gir."

    balance = db.get_balance(platform, sender_id)
    if amount > balance:
        return f"@{sender_display_name}, yetersiz bakiye. Bakiyen: {balance} SamoBit"

    db.add_balance(platform, sender_id, -amount)
    db.add_balance(platform, target_user_id, amount)
    return f"@{sender_display_name}, {target_display_name}'e {amount} SamoBit gönderdin!"


def cmd_first(db, platform: str, user_id: str, display_name: str, first_claimed_today: dict) -> str:
    today_key = (platform, datetime.now(timezone.utc).date().isoformat())
    if first_claimed_today.get(today_key):
        return f"@{display_name}, bugünün ilk ödülü zaten alındı."

    first_claimed_today[today_key] = user_id
    reward = 500
    db.add_balance(platform, user_id, reward)
    return f"@{display_name}, ilk yazan sensin! {reward} SamoBit kazandın!"


def cmd_fish(db, platform: str, user_id: str, display_name: str) -> str:
    roll = random.random()
    if roll < 0.02:
        reward = random.randint(20000, 50000)
        db.add_balance(platform, user_id, reward)
        return f"🎣 @{display_name}, HAZİNE SANDIĞI buldun! {reward} SamoBit!"
    elif roll < 0.30:
        reward = random.randint(10, 50)
        db.add_balance(platform, user_id, reward)
        return f"@{display_name}, bir balık tuttun! {reward} SamoBit kazandın."
    else:
        return f"@{display_name}, bir şey tutamadın, tekrar dene."
