# bin/ - run the app locally

Convenience scripts to build and serve the static site on your machine. The app
has no backend, so "the server" here is just Python's static file server hosting
`public/`.

| Script | What it does |
|---|---|
| `start.sh` | Build data + assemble `public/` + serve it in the background. |
| `stop.sh` | Stop the background server. |
| `restart.sh` | `stop.sh` then `start.sh` (passes flags through). |

## Usage
```bash
bin/start.sh                 # mock data (no network/keys), http://localhost:8000
bin/start.sh --live          # live data (uses .venv if present)
bin/start.sh --port=8137     # different port
bin/start.sh --serve-only    # skip fetch+build, just serve existing public/
bin/stop.sh
bin/restart.sh --live        # rebuild with live data and restart
bin/restart.sh --serve-only  # just bounce the server
```

Environment overrides: `PORT=9000 bin/start.sh`, `PYTHON=python3.12 bin/start.sh`.

## Notes
- Runtime state (`.server.pid`, `server.log`) is written here and git-ignored.
- `--live` needs the Python deps installed (`pip install -r scripts/requirements.txt`);
  it will auto-activate `.venv` at the repo root if you created one.
- If start reports the port is in use, pick another with `--port=`.
