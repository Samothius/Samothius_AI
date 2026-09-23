import os
import subprocess
from flask import Flask, request, redirect, url_for, session, render_template_string
from database import DatabaseManager
from dotenv import load_dotenv

load_dotenv()

ADMIN_PANEL_PASSWORD = os.getenv("ADMIN_PANEL_PASSWORD", "changeme")
ADMIN_PANEL_PORT = int(os.getenv("ADMIN_PANEL_PORT", "5050"))
SECRET_KEY = os.getenv("ADMIN_PANEL_SECRET_KEY", "samothius-panel-secret")

app = Flask(__name__)
app.secret_key = SECRET_KEY
db = DatabaseManager()

BASE_STYLE = """
<style>
body { font-family: -apple-system, sans-serif; background: #0e0e10; color: #efeff1; margin: 0; }
nav { background: #18181b; padding: 16px 24px; display: flex; gap: 20px; align-items: center; }
nav a { color: #efeff1; text-decoration: none; font-weight: 600; }
nav a:hover { color: #9146ff; }
.container { padding: 24px; max-width: 1000px; margin: 0 auto; }
h1, h2 { color: #9146ff; }
table { width: 100%; border-collapse: collapse; margin-top: 16px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #303032; }
th { color: #adadb8; }
input, select, button { padding: 8px 10px; border-radius: 4px; border: 1px solid #303032; background: #1f1f23; color: #efeff1; margin: 4px 0; }
button { background: #9146ff; border: none; cursor: pointer; font-weight: 600; }
button:hover { background: #772ce8; }
.card { background: #18181b; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
.stat { font-size: 28px; font-weight: 700; color: #00ff7f; }
.flash { background: #2d2d33; padding: 10px; border-radius: 4px; margin-bottom: 16px; color: #ffd700; }
</style>
"""

def require_login():
    return session.get("logged_in", False)

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PANEL_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        error = "Incorrect password."
    return render_template_string(BASE_STYLE + """
    <div class="container" style="max-width:400px; margin-top:80px;">
        <div class="card">
            <h1>🎮 Samothius Panel</h1>
            {% if error %}<div class="flash">{{ error }}</div>{% endif %}
            <form method="post">
                <input type="password" name="password" placeholder="Admin password" style="width:100%;box-sizing:border-box;" required>
                <button type="submit" style="width:100%; margin-top:10px;">Login</button>
            </form>
        </div>
    </div>
    """, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

NAV = """
<nav>
    <a href="{{ url_for('dashboard') }}">📊 Dashboard</a>
    <a href="{{ url_for('settings_page') }}">⚙️ Settings</a>
    <a href="{{ url_for('balances_page') }}">💰 Balances</a>
    <a href="{{ url_for('controls_page') }}">🎛️ Controls</a>
    <a href="{{ url_for('logout') }}" style="margin-left:auto;">Logout</a>
</nav>
"""

@app.route("/")
@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect(url_for("login"))
    total_users = db.get_total_users()
    total_volume = db.get_total_samobit_volume()
    top10 = db.get_top_richest_users(10)
    games_enabled = db.get_setting("games_enabled", True)
    return render_template_string(BASE_STYLE + NAV + """
    <div class="container">
        <h1>📊 Dashboard</h1>
        <div class="grid">
            <div class="card"><div>Total Users</div><div class="stat">{{ total_users }}</div></div>
            <div class="card"><div>Total SamoBit Volume</div><div class="stat">{{ total_volume }}</div></div>
            <div class="card"><div>Game Status</div><div class="stat">{{ "ON" if games_enabled else "OFF" }}</div></div>
        </div>
        <div class="card">
            <h2>🏆 Top 10</h2>
            <table>
                <tr><th>#</th><th>User</th><th>Balance</th></tr>
                {% for name, bal in top10 %}
                <tr><td>{{ loop.index }}</td><td>{{ name }}</td><td>{{ bal }}</td></tr>
                {% endfor %}
            </table>
        </div>
    </div>
    """, total_users=total_users, total_volume=total_volume, top10=top10, games_enabled=games_enabled)

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if not require_login():
        return redirect(url_for("login"))
    if request.method == "POST":
        for key in request.form:
            if key.startswith("setting_"):
                real_key = key[len("setting_"):]
                db.set_setting(real_key, request.form[key])
        return redirect(url_for("settings_page"))

    all_settings = db.get_all_settings()
    categories = {}
    for key, value, value_type, category, description in all_settings:
        categories.setdefault(category, []).append((key, value, value_type, description))

    return render_template_string(BASE_STYLE + NAV + """
    <div class="container">
        <h1>⚙️ Game Settings</h1>
        <form method="post">
        {% for category, items in categories.items() %}
            <div class="card">
                <h2>{{ category|capitalize }}</h2>
                <table>
                {% for key, value, value_type, description in items %}
                    <tr>
                        <td>{{ key }}<br><small style="color:#adadb8;">{{ description }}</small></td>
                        <td><input type="text" name="setting_{{ key }}" value="{{ value }}"></td>
                    </tr>
                {% endfor %}
                </table>
            </div>
        {% endfor %}
            <button type="submit">💾 Save All Settings</button>
        </form>
    </div>
    """, categories=categories)

@app.route("/balances", methods=["GET", "POST"])
def balances_page():
    if not require_login():
        return redirect(url_for("login"))
    message = None
    if request.method == "POST":
        action = request.form.get("action")
        target = request.form.get("target", "").strip().lower()
        if action == "add":
            amount = int(request.form.get("amount", 0))
            db.add_samobit_by_twitch_name(target, amount)
            message = f"Added {amount} SamoBit to {target}."
        elif action == "set":
            amount = int(request.form.get("amount", 0))
            db.set_balance(target, amount)
            message = f"Set {target}'s balance to {amount}."
        elif action == "blacklist":
            db.set_blacklisted(target, True)
            message = f"{target} has been blacklisted."

    query = request.args.get("q", "")
    results = db.search_users(query, 20) if query else db.get_top_richest_users(20)

    return render_template_string(BASE_STYLE + NAV + """
    <div class="container">
        <h1>💰 Balance Management</h1>
        {% if message %}<div class="flash">{{ message }}</div>{% endif %}
        <div class="card">
            <form method="get">
                <input type="text" name="q" placeholder="Search user..." value="{{ query }}">
                <button type="submit">Search</button>
            </form>
        </div>
        <div class="card">
            <h2>Add / Set Balance</h2>
            <form method="post">
                <input type="text" name="target" placeholder="twitch username" required>
                <input type="number" name="amount" placeholder="amount" required>
                <select name="action">
                    <option value="add">Add (+)</option>
                    <option value="set">Set (=)</option>
                </select>
                <button type="submit">Apply</button>
            </form>
        </div>
        <div class="card">
            <table>
                <tr><th>User</th><th>Balance</th><th></th></tr>
                {% for name, bal in results %}
                <tr>
                    <td>{{ name }}</td>
                    <td>{{ bal }}</td>
                    <td>
                        <form method="post" style="margin:0;" onsubmit="return confirm('Blacklist {{ name }}? They will stop earning SamoBit.');">
                            <input type="hidden" name="action" value="blacklist">
                            <input type="hidden" name="target" value="{{ name }}">
                            <button type="submit" style="background:#c0392b;">🚫 Blacklist</button>
                        </form>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
    """, results=results, query=query, message=message)

@app.route("/controls", methods=["GET", "POST"])
def controls_page():
    if not require_login():
        return redirect(url_for("login"))
    message = None
    RESTARTABLE_SERVICES = {
        "restart_discord": "samothius-discord",
        "restart_twitch": "samothius-twitch",
        "restart_youtube": "samothius-youtube",
    }
    if request.method == "POST":
        action = request.form.get("action")
        if action == "spawn_boss":
            db.create_command("spawn_boss")
            message = "Boss spawn command sent. The bot will process it within 10 seconds."
        elif action == "games_on":
            db.set_setting("games_enabled", "true")
            message = "Games enabled."
        elif action == "games_off":
            db.set_setting("games_enabled", "false")
            message = "Games disabled."
        elif action in RESTARTABLE_SERVICES:
            service = RESTARTABLE_SERVICES[action]
            try:
                subprocess.run(["systemctl", "restart", service], check=True, timeout=15)
                message = f"{service} restarted successfully."
            except Exception as e:
                message = f"Failed to restart {service}: {e}"
        elif action == "youtube_start":
            try:
                subprocess.run(["systemctl", "start", "samothius-youtube"], check=True, timeout=15)
                message = "YouTube bot started."
            except Exception as e:
                message = f"Failed to start YouTube bot: {e}"
        elif action == "youtube_stop":
            try:
                subprocess.run(["systemctl", "stop", "samothius-youtube"], check=True, timeout=15)
                message = "YouTube bot stopped."
            except Exception as e:
                message = f"Failed to stop YouTube bot: {e}"

    games_enabled = db.get_setting("games_enabled", True)
    try:
        youtube_status = subprocess.run(
            ["systemctl", "is-active", "samothius-youtube"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        youtube_status = "unknown"
    youtube_running = youtube_status == "active"
    return render_template_string(BASE_STYLE + NAV + """
    <div class="container">
        <h1>🎛️ Live Controls</h1>
        {% if message %}<div class="flash">{{ message }}</div>{% endif %}
        <div class="card">
            <h2>Game Status: {{ "🟢 ON" if games_enabled else "🔴 OFF" }}</h2>
            <form method="post" style="display:inline;">
                <input type="hidden" name="action" value="games_on">
                <button type="submit">Enable Games</button>
            </form>
            <form method="post" style="display:inline;">
                <input type="hidden" name="action" value="games_off">
                <button type="submit">Disable Games</button>
            </form>
        </div>
        <div class="card">
            <h2>👹 Boss Control</h2>
            <form method="post">
                <input type="hidden" name="action" value="spawn_boss">
                <button type="submit">Spawn Boss</button>
            </form>
        </div>
        <div class="card">
            <h2>📺 YouTube Bot: {{ "🟢 Running" if youtube_running else "🔴 Stopped" }}</h2>
            <form method="post" style="display:inline;">
                <input type="hidden" name="action" value="youtube_start">
                <button type="submit" {{ "disabled" if youtube_running }}>Start YouTube Bot</button>
            </form>
            <form method="post" style="display:inline;" onsubmit="return confirm('Stop the YouTube bot? It will stop responding in chat until started again.');">
                <input type="hidden" name="action" value="youtube_stop">
                <button type="submit" {{ "disabled" if not youtube_running }}>Stop YouTube Bot</button>
            </form>
        </div>
        <div class="card">
            <h2>🔁 Bot Restarts</h2>
            <form method="post" style="display:inline;" onsubmit="return confirm('Restart the Discord bot?');">
                <input type="hidden" name="action" value="restart_discord">
                <button type="submit">Restart Discord Bot</button>
            </form>
            <form method="post" style="display:inline;" onsubmit="return confirm('Restart the Twitch bot?');">
                <input type="hidden" name="action" value="restart_twitch">
                <button type="submit">Restart Twitch Bot</button>
            </form>
            <form method="post" style="display:inline;" onsubmit="return confirm('Restart the YouTube bot?');">
                <input type="hidden" name="action" value="restart_youtube">
                <button type="submit">Restart YouTube Bot</button>
            </form>
        </div>
    </div>
    """, games_enabled=games_enabled, message=message, youtube_running=youtube_running)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=ADMIN_PANEL_PORT)
