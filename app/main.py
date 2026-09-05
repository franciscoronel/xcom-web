"""X-COM Web — FastAPI backend.

Single-container multi-user DOS game host. Serves:
  - static frontend (index.html, app.js, js-dos runtime)
  - the game bundle (dosbox.conf + game files)
  - a JSON API for user accounts and per-user save slots (10 each)
"""

import os
import sqlite3
import secrets
import hashlib
import hmac
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE / "data"))
SAVES_DIR = DATA_DIR / "saves"
DB_PATH = DATA_DIR / "xcom.db"
STATIC_DIR = BASE / "static"
GAME_DIR = BASE / "game"

SAVE_SLOTS = 10  # save slots per user

DATA_DIR.mkdir(parents=True, exist_ok=True)
SAVES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS saves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                slot INTEGER NOT NULL,
                filename TEXT NOT NULL,
                size INTEGER NOT NULL,
                saved_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (user_id, slot)
            );
            """
        )


@contextmanager
def db():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Auth helpers (PBKDF2 — stdlib only, no native deps)
# ---------------------------------------------------------------------------
def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return dk.hex()


def _verify_password(password: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(_hash_password(password, salt), expected)


def _new_token(user_id: int) -> str:
    return secrets.token_urlsafe(32)


# In-memory token store. Fine for a small family LAN deployment; tokens do not
# survive a container restart, which is acceptable (users just log in again).
_tokens: dict[str, int] = {}


def _user_from_token(token: str):
    uid = _tokens.get(token)
    if uid is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return row


app = FastAPI(title="X-COM Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


init_db()


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------
# helper to read JSON body safely
async def _read_json(req: Request) -> dict:
    try:
        return await req.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")


@app.post("/api/register")
async def register_body(req: Request):
    body = await _read_json(req)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 4:
        raise HTTPException(status_code=400, detail="Password too short (min 4)")
    salt = secrets.token_hex(16)
    h = _hash_password(password, salt)
    try:
        with db() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, h, salt),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Username already taken")
    return {"ok": True}


@app.post("/api/login")
async def login(req: Request):
    body = await _read_json(req)
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not _verify_password(password, row["salt"], row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = _new_token(row["id"])
    _tokens[token] = row["id"]
    return {"ok": True, "token": token, "username": row["username"]}


@app.post("/api/logout")
def logout(req: Request):
    auth = req.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    _tokens.pop(token, None)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Save slots API
# ---------------------------------------------------------------------------
def _get_user(req: Request):
    auth = req.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    return _user_from_token(token)


@app.get("/api/saves")
def list_saves(req: Request):
    user = _get_user(req)
    with db() as conn:
        rows = conn.execute(
            "SELECT slot, filename, size, saved_at FROM saves WHERE user_id = ? ORDER BY slot",
            (user["id"],),
        ).fetchall()
    slots = {r["slot"]: {"filename": r["filename"], "size": r["size"], "saved_at": r["saved_at"]} for r in rows}
    return {"slots": slots}


def _slot_path(user_id: int, slot: int) -> Path:
    return SAVES_DIR / f"u{user_id}" / f"slot{slot}.zip"


@app.get("/api/saves/{slot}")
def download_save(req: Request, slot: int):
    user = _get_user(req)
    if slot < 1 or slot > SAVE_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{SAVE_SLOTS}")
    path = _slot_path(user["id"], slot)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Slot is empty")
    return FileResponse(path, media_type="application/zip", filename=f"slot{slot}.zip")


@app.put("/api/saves/{slot}")
async def upload_save(req: Request, slot: int, file: UploadFile):
    user = _get_user(req)
    if slot < 1 or slot > SAVE_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{SAVE_SLOTS}")
    data = await file.read()
    path = _slot_path(user["id"], slot)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    with db() as conn:
        conn.execute(
            """
            INSERT INTO saves (user_id, slot, filename, size, saved_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(user_id, slot) DO UPDATE SET
                filename = excluded.filename,
                size = excluded.size,
                saved_at = excluded.saved_at
            """,
            (user["id"], slot, file.filename or f"slot{slot}.zip", len(data)),
        )
    return {"ok": True, "slot": slot, "size": len(data)}


@app.delete("/api/saves/{slot}")
def delete_save(req: Request, slot: int):
    user = _get_user(req)
    if slot < 1 or slot > SAVE_SLOTS:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{SAVE_SLOTS}")
    path = _slot_path(user["id"], slot)
    if path.exists():
        path.unlink()
    with db() as conn:
        conn.execute("DELETE FROM saves WHERE user_id = ? AND slot = ?", (user["id"], slot))
    return {"ok": True}


@app.get("/api/me")
def me(req: Request):
    user = _get_user(req)
    return {"username": user["username"]}


@app.get("/api/health")
def health():
    return {"ok": True, "save_slots": SAVE_SLOTS}


# ---------------------------------------------------------------------------
# Static / game bundle serving
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/js-dos", StaticFiles(directory=STATIC_DIR / "js-dos"), name="js-dos")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/game", StaticFiles(directory=GAME_DIR), name="game")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
