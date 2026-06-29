import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # GitHub'dan gelen güncellemeyi çek
        print("🚀 New update on Github. Pull stared")
        subprocess.run(["git", "pull"], cwd="/root/samothius_ai")
        # Botları yeniden başlat
        subprocess.run(["sudo", "systemctl", "restart", "samothius-discord"])
        subprocess.run(["sudo", "systemctl", "restart", "samothius-twitch"])
        self.send_response(200)
        self.end_headers()

server = HTTPServer(('0.0.0.0', 9000), WebhookHandler)
print("✅ Webhook active on port 9000 ")
server.serve_forever()
