# Theridion

Modern, open-source API testing platform — REST, GraphQL, gRPC, SOAP, with built-in performance and security testing.

Named after *Theridion*, a genus of spiders that build chaotic three-dimensional cobwebs — a fitting metaphor for the entangled webs of modern API dependencies.

## Status

🚧 **Pre-alpha — under active development.**

## Goals

- **One tool for the full API lifecycle:** design → functional test → contract test → load test → security scan → mock server.
- **Native multiplatform desktop app** for macOS, Linux, and Windows (Tauri + Python).
- **Modern UX** — file-based projects (git-friendly), scriptable, keyboard-first.
- **Best-in-class SOAP support**, including WS-Security, MTOM, schema validation.
- **Open source** — community-owned, no telemetry, no lock-in.

## Architecture

```
┌─────────────────────────────────────────┐
│  Tauri shell (Rust, ~5 MB)              │
│  ┌───────────────────────────────────┐  │
│  │ React + TypeScript + Tailwind      │  │
│  │ Monaco editor, shadcn/ui           │  │
│  └────────────────┬──────────────────┘  │
└───────────────────┼─────────────────────┘
                    │ HTTP/WebSocket
                    │ on localhost:RANDOM
┌───────────────────┴─────────────────────┐
│  Python FastAPI sidecar                  │
│  ┌─────────────────────────────────┐    │
│  │  Protocol executors:             │    │
│  │    REST (httpx) · SOAP (zeep)    │    │
│  │    gRPC · GraphQL                │    │
│  ├─────────────────────────────────┤    │
│  │  Project store (file-based)      │    │
│  │  Assertion engine                │    │
│  │  Load test runner (locust)       │    │
│  │  Security scanner (ZAP API)      │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

## Repository structure

```
theridion/
├── apps/
│   ├── desktop/    # Tauri + React frontend
│   └── sidecar/    # Python FastAPI backend
├── .github/
│   └── workflows/  # Multi-platform CI/CD
└── logos/          # Brand assets
```

## Development

Requires:

- Node.js 24+
- pnpm 10+
- Rust (latest stable)
- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (Python package manager)

### Bundle the sidecar

The desktop app embeds the Python sidecar via Tauri's `externalBin`
mechanism. Before the first `pnpm tauri dev`, build the binary:

```bash
cd apps/desktop
pnpm install
pnpm sidecar:bundle
```

This calls PyInstaller against `apps/sidecar/sidecar.spec` and stages
the resulting binary into `apps/desktop/src-tauri/binaries/` with the
target-triple suffix Tauri expects. Re-run after Python changes.

### Desktop dev

```bash
pnpm tauri dev
```

Tauri spawns the bundled sidecar on a random loopback port, parses
`THERIDION_SIDECAR_READY pid=… port=… home=…` from its stdout, and
exposes the port to the frontend via the `get_sidecar_port` Tauri
command. Cold start of the bundled binary is ~6–8 s.

### Sidecar standalone (for fast Python iteration)

If you'd rather skip the rebundle loop:

```bash
cd apps/sidecar
uv sync
THERIDION_PORT=8765 uv run python -m theridion_sidecar.main
```

…then run the frontend in a regular browser tab via `pnpm dev` (port
1420). Without `__TAURI_INTERNALS__` the frontend falls back to
`http://127.0.0.1:8765`.

### E2E tests

```bash
cd apps/desktop
pnpm test:e2e         # headless run
pnpm test:e2e:ui      # Playwright's interactive UI
```

E2E spawns its own isolated sidecar (port 8766, `/tmp/theridion-e2e`
home) and Vite (port 1421); does not collide with anything you have
running on default dev ports.

## License

MIT — see [LICENSE](./LICENSE).
