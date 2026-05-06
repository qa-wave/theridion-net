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

### Sidecar (Python)

```bash
cd apps/sidecar
uv sync
uv run uvicorn theridion_sidecar.main:app --reload --port 8765
```

### Desktop (Tauri)

```bash
cd apps/desktop
pnpm install
pnpm tauri dev
```

## License

MIT — see [LICENSE](./LICENSE).
