import os
import json
import requests
from http.server import BaseHTTPRequestHandler
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
TAIGA_API = os.getenv("TAIGA_API")
TAIGA_USERNAME = os.getenv("TAIGA_USERNAME")
TAIGA_PASSWORD = os.getenv("TAIGA_PASSWORD")
TAIGA_PROJECT_ID = int(os.getenv("TAIGA_PROJECT_ID"))

# ---------- TAIGA AUTH ----------
def get_taiga_token():
    res = requests.post(f"{TAIGA_API}/auth", json={
        "type": "normal",
        "username": TAIGA_USERNAME,
        "password": TAIGA_PASSWORD
    })
    return res.json()["auth_token"]

def taiga_post(endpoint, data):
    token = get_taiga_token()
    res = requests.post(
        f"{TAIGA_API}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        json=data
    )
    return res

# ---------- COMMAND HANDLERS ----------
def create_task(name):
    res = taiga_post("tasks", {
        "subject": name,
        "project": TAIGA_PROJECT_ID,
        "status": 1
    })
    return "✅ Task created" if res.status_code == 201 else "❌ Failed"

def create_story(name):
    res = taiga_post("userstories", {
        "subject": name,
        "project": TAIGA_PROJECT_ID,
        "status": 1
    })
    return "📚 Story created" if res.status_code == 201 else "❌ Failed"

def create_issue(name):
    res = taiga_post("issues", {
        "subject": name,
        "project": TAIGA_PROJECT_ID,
        "status": 1,
        "priority": 2
    })
    return "🐞 Issue created" if res.status_code == 201 else "❌ Failed"

def comment(task_id, text):
    res = taiga_post(f"history/task/{task_id}", {
        "comment": text
    })
    return "💬 Comment added" if res.status_code == 201 else "❌ Failed"

# ---------- DISCORD HANDLER ----------
class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers['Content-Length'])
            body = self.rfile.read(length)
            signature = self.headers.get("X-Signature-Ed25519")
            timestamp = self.headers.get("X-Signature-Timestamp")

            verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))

            try:
                verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
            except BadSignatureError:
                self.send_response(401)
                self.end_headers()
                return

            data = json.loads(body)

            # Ping (Discord verification)
            if data["type"] == 1:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"type": 1}).encode())
                return

            # Slash command
            if data["type"] == 2:
                name = data["data"]["name"]
                options = data["data"].get("options", [])

                if name == "create-task":
                    task_name = options[0]["value"]
                    msg = create_task(task_name)

                elif name == "create-story":
                    msg = create_story(options[0]["value"])

                elif name == "create-issue":
                    msg = create_issue(options[0]["value"])

                elif name == "comment":
                    task_id = options[0]["value"]
                    text = options[1]["value"]
                    msg = comment(task_id, text)

                else:
                    msg = "Unknown command"

                response = {
                    "type": 4,
                    "data": {
                        "content": msg
                    }
                }

                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())