import json
import os

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

app = FastAPI()

DISCORD_PUBLIC_KEY = os.getenv("DISCORD_PUBLIC_KEY")
TAIGA_API = os.getenv("TAIGA_API")
TAIGA_USERNAME = os.getenv("TAIGA_USERNAME")
TAIGA_PASSWORD = os.getenv("TAIGA_PASSWORD")

_taiga_project_raw = os.getenv("TAIGA_PROJECT_ID")
TAIGA_PROJECT_ID = int(_taiga_project_raw) if _taiga_project_raw and _taiga_project_raw.isdigit() else None


def _ensure_taiga_config():
    if not all([TAIGA_API, TAIGA_USERNAME, TAIGA_PASSWORD]) or TAIGA_PROJECT_ID is None:
        raise RuntimeError("Missing Taiga configuration in environment variables")


# ---------- TAIGA AUTH ----------
def get_taiga_token():
    _ensure_taiga_config()
    res = requests.post(
        f"{TAIGA_API}/auth",
        json={
            "type": "normal",
            "username": TAIGA_USERNAME,
            "password": TAIGA_PASSWORD,
        },
        timeout=20,
    )
    if not res.ok:
        raise RuntimeError(f"Taiga auth failed: {res.status_code}")
    return res.json()["auth_token"]


def taiga_post(endpoint, data):
    token = get_taiga_token()
    return requests.post(
        f"{TAIGA_API}/{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
        json=data,
        timeout=20,
    )


# ---------- COMMAND HANDLERS ----------
def create_task(name):
    res = taiga_post(
        "tasks",
        {
            "subject": name,
            "project": TAIGA_PROJECT_ID,
            "status": 1,
        },
    )
    return "✅ Task created" if res.status_code == 201 else "❌ Failed"


def create_story(name):
    res = taiga_post(
        "userstories",
        {
            "subject": name,
            "project": TAIGA_PROJECT_ID,
            "status": 1,
        },
    )
    return "📚 Story created" if res.status_code == 201 else "❌ Failed"


def create_issue(name):
    res = taiga_post(
        "issues",
        {
            "subject": name,
            "project": TAIGA_PROJECT_ID,
            "status": 1,
            "priority": 2,
        },
    )
    return "🐞 Issue created" if res.status_code == 201 else "❌ Failed"


def comment(task_id, text):
    res = taiga_post(
        f"history/task/{task_id}",
        {
            "comment": text,
        },
    )
    return "💬 Comment added" if res.status_code == 201 else "❌ Failed"


def _verify_discord_signature(body, signature, timestamp):
    if not DISCORD_PUBLIC_KEY:
        raise HTTPException(status_code=500, detail="Missing DISCORD_PUBLIC_KEY")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing Discord signature headers")

    try:
        verify_key = VerifyKey(bytes.fromhex(DISCORD_PUBLIC_KEY))
        verify_key.verify(timestamp.encode() + body, bytes.fromhex(signature))
    except (BadSignatureError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid request signature")


@app.get("/")
def root_health():
    return {"status": "ok", "message": "Use POST for Discord interactions"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/")
async def discord_interactions(
    request: Request,
    x_signature_ed25519: str = Header(default=None),
    x_signature_timestamp: str = Header(default=None),
):
    body = await request.body()
    _verify_discord_signature(body, x_signature_ed25519, x_signature_timestamp)

    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if data.get("type") == 1:
        return {"type": 1}

    if data.get("type") != 2:
        raise HTTPException(status_code=400, detail="Unsupported interaction type")

    command_data = data.get("data", {})
    name = command_data.get("name")
    options = command_data.get("options", [])

    try:
        if name == "create-task":
            msg = create_task(options[0]["value"])
        elif name == "create-story":
            msg = create_story(options[0]["value"])
        elif name == "create-issue":
            msg = create_issue(options[0]["value"])
        elif name == "comment":
            msg = comment(options[0]["value"], options[1]["value"])
        else:
            msg = "Unknown command"
    except (IndexError, KeyError, TypeError):
        msg = "Invalid command options"

    return {
        "type": 4,
        "data": {
            "content": msg,
        },
    }

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)