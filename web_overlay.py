import json
import time
import urllib.request
import urllib.parse
from flask import Flask, render_template_string
from database import DatabaseManager
from config import CHAT_OVERLAY_WS_PORT, TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, STREAMER_NAME

app = Flask(__name__)
db = DatabaseManager()

# --- BROADCASTER ID (needed for BTTV's channel-emote endpoint) ---
_broadcaster_id_cache = {"id": None, "expires_at": 0}

def get_broadcaster_id():
    """Fetches and caches the streamer's numeric Twitch ID for BTTV emotes.
    Returns None (silently) if Twitch credentials aren't set or the API call fails -
    the chat overlay still works fine without BTTV channel emotes in that case."""
    now = time.time()
    if _broadcaster_id_cache["id"] and now < _broadcaster_id_cache["expires_at"]:
        return _broadcaster_id_cache["id"]
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None
    try:
        token_data = urllib.parse.urlencode({
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }).encode()
        token_req = urllib.request.Request("https://id.twitch.tv/oauth2/token", data=token_data, method="POST")
        with urllib.request.urlopen(token_req, timeout=5) as resp:
            access_token = json.loads(resp.read()).get("access_token")
        if not access_token:
            return None

        user_req = urllib.request.Request(
            f"https://api.twitch.tv/helix/users?login={STREAMER_NAME}",
            headers={"Client-ID": TWITCH_CLIENT_ID, "Authorization": f"Bearer {access_token}"},
        )
        with urllib.request.urlopen(user_req, timeout=5) as resp:
            users = json.loads(resp.read()).get("data", [])
        if users:
            _broadcaster_id_cache["id"] = users[0]["id"]
            _broadcaster_id_cache["expires_at"] = now + 3600
            return _broadcaster_id_cache["id"]
    except Exception as e:
        print(f"⚠️ Could not fetch broadcaster id for BTTV channel emotes: {e}")
    return None

# --- OVERLAY STYLES ---
# Built for OBS browser-source use: solid (not just blurred) panel so it stays
# readable over any gameplay footage, strong type hierarchy, tier-colored
# accents for ranks 1-3.
BASE_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=Inter:wght@400;500;600&display=swap');

    * { box-sizing: border-box; }

    body {
        background-color: rgba(0, 0, 0, 0);
        color: #FFFFFF;
        font-family: 'Inter', sans-serif;
        overflow: hidden;
        margin: 0;
        padding: 0;
    }

    .lb-box {
        background: rgba(14, 14, 20, 0.92);
        padding: 18px 20px;
        width: 600px;
        height: 300px;
        box-sizing: border-box;
        border-radius: 14px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
        display: flex;
        flex-direction: column;
    }

    .lb-title {
        font-family: 'Sora', sans-serif;
        font-size: 17px;
        font-weight: 700;
        color: #FFFFFF;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        text-align: center;
        margin-bottom: 12px;
        text-shadow: 0 1px 3px rgba(0,0,0,0.6);
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }
    .lb-title .accent { color: #FFFFFF; }

    .lb-list {
        display: grid;
        grid-template-columns: 1fr 1fr;
        grid-template-rows: repeat(5, 1fr);
        grid-auto-flow: column;
        gap: 5px 10px;
        flex-grow: 1;
        overflow: hidden;
    }

    .lb-entry {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 5px 8px;
        border-radius: 6px;
        background: rgba(255, 255, 255, 0.03);
        border-left: 3px solid rgba(255, 255, 255, 0.08);
        min-width: 0;
    }
    .lb-entry.tier-1 {
        background: linear-gradient(90deg, rgba(255, 201, 60, 0.16), rgba(255,255,255,0.02));
        border-left: 3px solid #FFC93C;
    }
    .lb-entry.tier-2 {
        background: linear-gradient(90deg, rgba(201, 205, 214, 0.10), rgba(255,255,255,0.02));
        border-left: 3px solid #C9CDD6;
    }
    .lb-entry.tier-3 {
        background: linear-gradient(90deg, rgba(217, 142, 74, 0.12), rgba(255,255,255,0.02));
        border-left: 3px solid #D98E4A;
    }

    .rank-badge {
        font-family: 'Sora', sans-serif;
        font-weight: 800;
        font-size: 14px;
        width: 22px;
        text-align: center;
        color: #FFFFFF;
        flex-shrink: 0;
    }
    .tier-1 .rank-badge { font-size: 16px; }
    .tier-2 .rank-badge { font-size: 15px; }
    .tier-3 .rank-badge { font-size: 15px; }

    .lb-name {
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 15px;
        color: #FFFFFF;
        flex-grow: 1;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        text-shadow: 0 1px 2px rgba(0,0,0,0.5);
    }

    .lb-balance {
        font-family: 'Sora', sans-serif;
        font-weight: 700;
        font-size: 15px;
        color: #FFFFFF;
        display: flex;
        align-items: center;
        gap: 5px;
        flex-shrink: 0;
        text-shadow: 0 1px 2px rgba(0,0,0,0.5);
    }
    .icon { width: 16px; height: 16px; }

    .footer-commands {
        margin-top: 8px;
        padding-top: 8px;
        text-align: center;
        font-size: 12px;
        color: #FFFFFF;
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        letter-spacing: 0.5px;
    }
    .footer-commands b { color: #FFFFFF; font-weight: 600; }

    /* Credits: Cinematic scrolling */
    .scroll-container { position: absolute; top: 100vh; width: 100%; text-align: center; animation: scrollUp 30s linear infinite; }
    @keyframes scrollUp { 0% { top: 100vh; } 100% { top: -100%; } }

    .credits-wrap { width: 560px; margin: 0 auto; }

    .header {
        font-family: 'Sora', sans-serif;
        font-size: 48px;
        font-weight: 800;
        color: #FFFFFF;
        margin-bottom: 50px;
        text-shadow: 0 2px 10px rgba(0,0,0,0.6);
        letter-spacing: 0.5px;
    }
    .header .accent { color: #FFFFFF; }

    .cat {
        font-family: 'Sora', sans-serif;
        font-size: 22px;
        font-weight: 700;
        color: #FFFFFF;
        margin-top: 50px;
        margin-bottom: 18px;
        text-transform: uppercase;
        letter-spacing: 3px;
        text-shadow: 0 2px 6px rgba(0,0,0,0.5);
        padding-bottom: 10px;
        border-bottom: 1px solid rgba(255, 255, 255, 0.12);
    }

    .credit-item {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        font-family: 'Inter', sans-serif;
        font-size: 21px;
        font-weight: 500;
        margin: 8px 0;
        text-shadow: 0 1px 5px rgba(0,0,0,0.5);
    }
    .credit-item .dot { display: inline-flex; align-items: center; }
    .credit-item .dot svg { width: 15px; height: 15px; display: block; }
    .credit-item.sub .dot { color: #9146FF; }
    .credit-item.gift .dot { color: #FFC93C; }
    .credit-item.follow .dot { color: #8B8FA3; }

    .gift-badge {
        font-family: 'Sora', sans-serif;
        font-weight: 700;
        font-size: 16px;
        color: #FFFFFF;
        background: rgba(255, 201, 60, 0.14);
        border: 1px solid rgba(255, 201, 60, 0.35);
        padding: 2px 10px;
        border-radius: 20px;
    }

    .credits-end {
        font-family: 'Sora', sans-serif;
        font-size: 24px;
        font-weight: 600;
        color: #FFFFFF;
        margin-top: 70px;
    }
</style>
"""

# --- LEADERBOARD ROUTE ---
def render_leaderboard_entries():
    users = db.get_top_richest_users(10)
    entries = ""
    for i, (u, b) in enumerate(users):
        rank = i + 1
        tier_class = f"tier-{rank}" if rank <= 3 else ""
        display_name = (u[:10] + '…') if len(u) > 10 else u
        entries += f'''
        <div class="lb-entry {tier_class}">
            <span class="rank-badge">{rank}</span>
            <span class="lb-name">{display_name}</span>
            <span class="lb-balance">{b} <img src="/static/samobit.png" class="icon"></span>
        </div>'''
    return entries

# JSON endpoint the leaderboard page polls for fresh data
@app.route('/leaderboard/data')
def leaderboard_data():
    try:
        return {"html": render_leaderboard_entries()}
    except Exception as e:
        return {"html": "", "error": str(e)}, 500

@app.route('/leaderboard')
def show_leaderboard():
    try:
        entries = render_leaderboard_entries()
        return f"""
        <html><head>{BASE_STYLE}</head><body>
            <div class="lb-box">
                <div class="lb-title"><span class="accent">SamoBit</span> Leaderboard</div>
                <div class="lb-list" id="lb-list">{entries}</div>
                <div class="footer-commands">Earn SamoBit &mdash; <b>!fish</b> &middot; <b>!gamble</b> &middot; <b>!heist</b></div>
            </div>
            <script>
                // Polls for fresh balances every 5s and swaps just the list,
                // Cache-buster parameter prevents OBS from caching old data.
                const REFRESH_MS = 5000;
                async function refreshLeaderboard() {{
                    try {{
                        const res = await fetch('/leaderboard/data?t=' + new Date().getTime());
                        const data = await res.json();
                        if (data.html) {{
                            document.getElementById('lb-list').innerHTML = data.html;
                        }}
                    }} catch (e) {{
                        console.warn('Leaderboard refresh failed', e);
                    }}
                }}
                setInterval(refreshLeaderboard, REFRESH_MS);
            </script>
        </body></html>"""
    except Exception as e:
        return f"Error: {e}"

# --- CREDITS ICONS (inline SVG, colored via CSS currentColor) ---
ICON_STAR = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 .587l3.668 7.568 8.332 1.151-6.064 5.828 1.48 8.279L12 19.771l-7.416 3.642 1.48-8.279L0 9.306l8.332-1.151z"/></svg>'
ICON_GIFT = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 7h-2.18c.11-.31.18-.65.18-1a2.5 2.5 0 0 0-2.5-2.5c-1.4 0-2.31.96-3 2-.69-1.04-1.6-2-3-2A2.5 2.5 0 0 0 7 4c0 .35.07.69.18 1H5a2 2 0 0 0-2 2v2a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9a2 2 0 0 0-2-2zM4 12v7a2 2 0 0 0 2 2h5v-9H4zm9 0v9h5a2 2 0 0 0 2-2v-7h-7z"/></svg>'
ICON_HEART = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.6-10-9.2C.5 8.4 2 5 5.5 5c2 0 3.4 1.2 4.5 2.7C11 6.2 12.4 5 14.5 5 18 5 19.5 8.4 18 11.8 17.5 16.4 12 21 12 21z"/></svg>'

# --- CREDITS ROUTE ---
@app.route('/credits')
def show_credits():
    try:
        subs = db.get_events_by_type('subscriber')
        gifts = db.get_top_gifters()
        follows = db.get_events_by_type('follower')

        content = '<div class="header">Thanks for <span class="accent">Watching</span>!</div>'
        if subs:
            content += '<div class="cat">Subscribers</div>' + "".join(
                [f'<div class="credit-item sub"><span class="dot">{ICON_STAR}</span>{u}</div>' for u, _ in subs]
            )
        if gifts:
            content += '<div class="cat">Top Gifters</div>' + "".join(
                [f'<div class="credit-item gift"><span class="dot">{ICON_GIFT}</span>{u}<span class="gift-badge">{a} Gift{"s" if a != 1 else ""}</span></div>' for u, a in gifts]
            )
        if follows:
            content += '<div class="cat">Recent Followers</div>' + "".join(
                [f'<div class="credit-item follow"><span class="dot">{ICON_HEART}</span>{u}</div>' for u, _ in follows]
            )

        return f"""<html><head>{BASE_STYLE}</head><body>
            <div class='scroll-container'>
                <div class="credits-wrap">
                    {content}
                    <div class="credits-end">See you next time!</div>
                </div>
            </div>
        </body></html>"""
    except Exception as e:
        return f"Error: {e}"

# --- CHAT ROUTE ---
@app.route('/chat')
def show_chat():
    broadcaster_id = get_broadcaster_id() or ""
    return f"""
    <html><head>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=Inter:wght@400;500;600&display=swap');
        * {{ box-sizing: border-box; }}
        body {{
            background-color: rgba(0, 0, 0, 0);
            color: #FFFFFF;
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 0;
            overflow: hidden;
        }}
        #chat-box {{
            width: 420px;
            height: 600px;
            display: flex;
            flex-direction: column;
            justify-content: flex-end;
            gap: 6px;
            padding: 10px;
            overflow: hidden;
        }}
        .msg {{
            background: rgba(14, 14, 20, 0.85);
            border-left: 3px solid rgba(255, 255, 255, 0.15);
            border-radius: 6px;
            padding: 7px 10px;
            font-size: 15px;
            line-height: 1.35;
            text-shadow: 0 1px 2px rgba(0,0,0,0.5);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: slideIn 0.25s ease-out;
            word-wrap: break-word;
        }}
        .msg.mod {{ border-left-color: #2ECC71; }}
        .msg.vip {{ border-left-color: #E91E8C; }}
        .msg.broadcaster {{ border-left-color: #9146FF; }}
        .user {{
            font-family: 'Sora', sans-serif;
            font-weight: 700;
            font-size: 14px;
            margin-right: 6px;
        }}
        .tag {{
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 1px 5px;
            border-radius: 3px;
            margin-right: 6px;
            vertical-align: middle;
        }}
        .tag.mod {{ background: rgba(46, 204, 113, 0.2); color: #2ECC71; }}
        .tag.vip {{ background: rgba(233, 30, 140, 0.2); color: #E91E8C; }}
        .tag.broadcaster {{ background: rgba(145, 70, 255, 0.2); color: #9146FF; }}
        .text {{ color: #FFFFFF; }}
        .emote {{ height: 26px; vertical-align: middle; margin: -4px 1px; }}
        @keyframes slideIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
    </style>
    </head>
    <body>
        <div id="chat-box"></div>
        <script>
            const MAX_MESSAGES = 15;
            const BROADCASTER_ID = "{broadcaster_id}";
            const CHANNEL_NAME = "{STREAMER_NAME}";
            const box = document.getElementById('chat-box');
            let emoteMap = {{}};

            function escapeHtml(str) {{
                const div = document.createElement('div');
                div.textContent = str;
                return div.innerHTML;
            }}

            // --- BTTV + FFZ emote loading (global + channel) ---
            function bestFfzUrl(urls) {{
                const url = urls['2'] || urls['1'] || Object.values(urls)[0];
                return url.startsWith('http') ? url : 'https:' + url;
            }}

            async function loadEmotes() {{
                const map = {{}};

                try {{
                    const g = await fetch('https://api.betterttv.net/3/cached/emotes/global').then(r => r.json());
                    g.forEach(e => map[e.code] = `https://cdn.betterttv.net/emote/${{e.id}}/2x`);
                }} catch (e) {{ console.warn('BTTV global emotes failed to load', e); }}

                if (BROADCASTER_ID) {{
                    try {{
                        const c = await fetch(`https://api.betterttv.net/3/cached/users/twitch/${{BROADCASTER_ID}}`).then(r => r.json());
                        [...(c.channelEmotes || []), ...(c.sharedEmotes || [])].forEach(e => {{
                            map[e.code] = `https://cdn.betterttv.net/emote/${{e.id}}/2x`;
                        }});
                    }} catch (e) {{ console.warn('BTTV channel emotes failed to load', e); }}
                }}

                try {{
                    const g = await fetch('https://api.frankerfacez.com/v1/set/global').then(r => r.json());
                    Object.values(g.sets || {{}}).forEach(set => {{
                        (set.emoticons || []).forEach(em => map[em.name] = bestFfzUrl(em.urls));
                    }});
                }} catch (e) {{ console.warn('FFZ global emotes failed to load', e); }}

                try {{
                    const c = await fetch(`https://api.frankerfacez.com/v1/room/${{CHANNEL_NAME}}`).then(r => r.json());
                    Object.values(c.sets || {{}}).forEach(set => {{
                        (set.emoticons || []).forEach(em => map[em.name] = bestFfzUrl(em.urls));
                    }});
                }} catch (e) {{ console.warn('FFZ channel emotes failed to load', e); }}

                return map;
            }}

            function renderThirdParty(segment) {{
                return segment.split(' ').map(token => {{
                    if (token === '') return '';
                    if (emoteMap[token]) {{
                        return `<img class="emote" src="${{emoteMap[token]}}" alt="${{escapeHtml(token)}}">`;
                    }}
                    return escapeHtml(token);
                }}).join(' ');
            }}

            function renderText(text, nativeEmotes) {{
                const emotes = (nativeEmotes || []).slice().sort((a, b) => a.start - b.start);
                let result = '';
                let cursor = 0;
                for (const em of emotes) {{
                    if (em.start > cursor) {{
                        result += renderThirdParty(text.substring(cursor, em.start));
                    }}
                    result += `<img class="emote" src="https://static-cdn.jtvnw.net/emoticons/v2/${{em.id}}/default/dark/2.0" alt="${{escapeHtml(em.code)}}">`;
                    cursor = em.end + 1;
                }}
                if (cursor < text.length) {{
                    result += renderThirdParty(text.substring(cursor));
                }}
                return result;
            }}

            function addMessage(data) {{
                const row = document.createElement('div');
                let tierClass = '';
                if (data.is_broadcaster) tierClass = 'broadcaster';
                else if (data.is_mod) tierClass = 'mod';
                else if (data.is_vip) tierClass = 'vip';

                row.className = 'msg ' + tierClass;

                let tagHtml = '';
                if (data.is_broadcaster) tagHtml = '<span class="tag broadcaster">Host</span>';
                else if (data.is_mod) tagHtml = '<span class="tag mod">Mod</span>';
                else if (data.is_vip) tagHtml = '<span class="tag vip">VIP</span>';

                const userColor = data.color ? data.color : '#FFFFFF';
                row.innerHTML = tagHtml +
                    '<span class="user" style="color:' + userColor + '">' + escapeHtml(data.user) + ':</span>' +
                    '<span class="text">' + renderText(data.message, data.native_emotes) + '</span>';

                box.appendChild(row);

                // Messages persist on screen - only the oldest is dropped once
                // the box is full, so chat never auto-fades.
                while (box.children.length > MAX_MESSAGES) {{
                    box.removeChild(box.firstChild);
                }}
            }}

            function connect() {{
                const ws = new WebSocket('ws://' + window.location.hostname + ':{CHAT_OVERLAY_WS_PORT}');
                ws.onmessage = (event) => {{
                    try {{
                        const data = JSON.parse(event.data);
                        addMessage(data);
                    }} catch (e) {{ console.error('Bad chat payload', e); }}
                }};
                ws.onclose = () => setTimeout(connect, 3000); // auto-reconnect
                ws.onerror = () => ws.close();
            }}

            loadEmotes().then(m => {{ emoteMap = m; }});
            connect();
        </script>
    </body>
    </html>"""

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
