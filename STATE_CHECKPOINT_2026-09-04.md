# X-COM Web Deployment State Checkpoint
Date: 2026-09-04

## Current State (Most Progress Achieved)

### Working
- **Container running**: `hermes_xcom` on 192.168.1.16:8001
- **Login/registration**: Working (POST /api/login returns 200 OK with token)
- **UI renders**: Dosbox viewport container appears in browser
- **js-dos files**: Properly served at /static/js-dos/ (js-dos.js, wdosbox.js, wdosbox.wasm)
- **Bundles served**: /game/xcom-jsdos returns 200 OK

### Broken (Game Won't Start)
- **Root cause**: `/app/game/xcom-jsdos` is a 208MB ZIP archive, NOT a directory
- js-dos expects a directory structure at the bundle path to serve game files
- The ZIP contains valid content (.jsdos/dosbox.conf, XCOM3/ game files) but cannot be read as a directory

### Key Files
- `/app/game/dosbox.conf`: Valid DOSBox config (XCOM3, slot=svga_s3)
- `/app/game/package.py`: ZIP extraction script (creates correct directory structure)
- `/app/static/app.js`: Launch logic uses `window.Dos()` factory (v7 API), BUNDLE_URL="/game/xcom-jsdos"
- `/app/static/index.html`: Login + game UI structure

### Dockerfile
- Uses `COPY game/ /app/game/` which copies the ZIP file as-is
- Game bundle not extracted during build

### Next Fix Required
- Extract the ZIP bundle to a directory so js-dos can serve it as a directory structure
- Either: modify Dockerfile to extract during build, or extract on host before deployment
