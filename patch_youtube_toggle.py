path = "/root/samothius_ai/admin_panel.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_route = '''    games_enabled = db.get_setting("games_enabled", True)
    return render_template_string(BASE_STYLE + NAV + """
    <div class="container">
        <h1>🎛️ Live Controls</h1>'''

new_route = '''    games_enabled = db.get_setting("games_enabled", True)
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
        <h1>🎛️ Live Controls</h1>'''

count = content.count(old_route)
assert count == 1, f"Expected 1 match for controls route start, found {count}"
content = content.replace(old_route, new_route)

old_action = '''        elif action in RESTARTABLE_SERVICES:
            service = RESTARTABLE_SERVICES[action]
            try:
                subprocess.run(["systemctl", "restart", service], check=True, timeout=15)
                message = f"{service} restarted successfully."
            except Exception as e:
                message = f"Failed to restart {service}: {e}"'''

new_action = '''        elif action in RESTARTABLE_SERVICES:
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
                message = f"Failed to stop YouTube bot: {e}"'''

count = content.count(old_action)
assert count == 1, f"Expected 1 match for action logic, found {count}"
content = content.replace(old_action, new_action)

old_html = '''        <div class="card">
            <h2>🔁 Bot Restarts</h2>'''

new_html = '''        <div class="card">
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
            <h2>🔁 Bot Restarts</h2>'''

count = content.count(old_html)
assert count == 1, f"Expected 1 match for restarts HTML block, found {count}"
content = content.replace(old_html, new_html)

old_render_call = '''    """, games_enabled=games_enabled, message=message)'''

new_render_call = '''    """, games_enabled=games_enabled, message=message, youtube_running=youtube_running)'''

count = content.count(old_render_call)
assert count == 1, f"Expected 1 match for render_template_string call, found {count}"
content = content.replace(old_render_call, new_render_call)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("patched successfully")
