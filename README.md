# X-COM Web

Single-container, multi-user web host for **X-COM: Apocalypse** (DOS, 1997).
Runs the game in-browser via [js-dos](https://js-dos.com/) (DOSBox → WebAssembly),
with per-user accounts and 10 server-side save slots each.

## Architecture

```
Browser                          Container (FastAPI, port 8000)
┌────────────────────┐           ┌───────────────────────────────┐
│ js-dos (WASM DOSBox)│◄────────►│ /api/*      users + save slots │
│  plays xcom.jsdos  │           │ /game/*     dosbox.conf + bundle│
│  ci.persist()=save │──PUT────►│ /js-dos/*   js-dos runtime      │
│  ci.restore()=load │◄─GET─────│ /static/*   index.html + app.js │
└────────────────────┘           └───────────────────────────────┘
```

- **Users** — register/login, PBKDF2-hashed passwords, bearer tokens.
- **Save slots** — 10 per user. A "save" is the js-dos `persist()` bundle
  (a zip of the changed filesystem relative to the base bundle). Stored as
  files under `data/saves/u<id>/slot<N>.zip`.
- **Game bundle** — `game/xcom.jsdos`, built from the X-COM Apocalypse CD
  via `game/package.py`. Contains `dosbox.conf` + `XCOM3/` game data.

## Build

### 1. Extract the game ISO (one-time, requires the CD image)
```sh
python3 -m venv /opt/data/dosgame/.venv
/opt/data/dosgame/.venv/bin/pip install pycdlib
/opt/data/dosgame/.venv/bin/python /opt/data/dosgame/extract_iso.py \
    /path/to/xcom.iso /opt/data/dosgame/xcom_apoc
```

### 2. Package the js-dos bundle
```sh
python3 game/package.py   # writes game/xcom.jsdos
```

### 3. Copy js-dos runtime (one-time)
```sh
cp node_modules/js-dos/dist/{js-dos.js,js-dos.css,wdosbox.js,wdosbox.wasm} static/js-dos/
```

### 4. Build & run the container
```sh
docker build -t xcom-web .
docker run -d --name hermes_xcom -p 8000:8000 -v /opt/data/xcom:/app/data xcom-web
```

## API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/api/register` | — | create account |
| POST | `/api/login` | — | get bearer token |
| POST | `/api/logout` | ✓ | invalidate token |
| GET  | `/api/me` | ✓ | current user |
| GET  | `/api/saves` | ✓ | list slots |
| GET  | `/api/saves/{n}` | ✓ | download slot n (zip) |
| PUT  | `/api/saves/{n}` | ✓ | upload slot n (zip) |
| DELETE | `/api/saves/{n}` | ✓ | delete slot n |
| GET  | `/api/health` | — | liveness + slot count |

## Known limitations
- CD audio (the 296 MB `MUSIC` track) is not bundled; the game plays without
  CD music.
- In-memory bearer tokens reset on container restart (users just log in again).
- `dosbox.conf` requires `cycles=3000` (pentium-level timing) — lower values
  cause the game to hang after the intro logo.

## Copyright
The game data (`game/xcom.jsdos`) is not committed — it is built locally from
a game CD the operator owns. Only the game server code lives in this repo.
