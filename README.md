# voice-order-agent

A real-time voice agent that takes pickup food orders for a fictional restaurant over WebRTC (LiveKit), plus an eval harness that calls it with simulated callers over real audio and scores every call.

**Status:** early scaffold. No agent behavior or eval results yet. Results will be added here only from runs saved under `reports/`.

## Prerequisites

- [pyenv](https://github.com/pyenv/pyenv) with the Python version in `.python-version` installed (`pyenv install`)
- [uv](https://docs.astral.sh/uv/)
- [nvm](https://github.com/nvm-sh/nvm) with the Node version in `.nvmrc` installed (`nvm install`)
- Docker with Compose

## Setup

```sh
cp .env.example .env   # then add your OPENAI_API_KEY
make setup    # .venv from the pyenv interpreter, uv sync, pre-commit, web deps
make up       # postgres, livekit-server, phoenix
make test
make lint
```

To talk to the agent, run `make dev` (backend, agent worker and web app together) and open http://localhost:5173. `make chat` is a text-only version in the terminal. Each call is saved under `recordings/<session_id>/`, and its traces are in Phoenix.

`make setup` creates `.venv` with `python -m venv` using the pyenv-selected interpreter, then uses uv to install the locked dependencies into it. uv is configured never to download or choose its own Python. To work in the shell, run `source .venv/bin/activate`.

Services once `make up` is healthy:

| Service | URL |
|---|---|
| LiveKit | `ws://localhost:7880` |
| Phoenix UI | http://localhost:6006 |
| Postgres | `localhost:5432` |

Run `make help` for all targets.

## Design decisions

See [docs/adr/](docs/adr/). Problems found along the way, and what I did about them, are in [docs/notes.md](docs/notes.md).
