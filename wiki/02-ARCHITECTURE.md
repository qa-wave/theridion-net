# Theridion BE — architektura

```
┌────────────────────────────────────────────────────────────────┐
│  Tauri 2.11 shell (Rust, ~5 MB)                                │
│  ├── src-tauri/src/lib.rs       app setup                      │
│  ├── src-tauri/src/sidecar.rs   spawn + port handshake         │
│  └── WebView (system)                                          │
│       │                                                        │
│       ▼ React 18 + TypeScript + Tailwind                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ App.tsx → ActivityBar → Strand/Mesh/Surge/Snare panely  │  │
│  │ + RequestPanel, ResponsePanel, ServiceMap, SilkPanel-no │  │
│  └─────────────────────────┬────────────────────────────────┘  │
└────────────────────────────┼───────────────────────────────────┘
                             │ loopback HTTP, X-Theridion-Token
                             ▼
┌────────────────────────────────────────────────────────────────┐
│  Python sidecar — apps/sidecar (PyInstaller --onefile, ~46 MB) │
│  ├── theridion_sidecar/main.py     ~150 routers                │
│  ├── api/{requests,graphql,grpc,soap,kafka,jms,jdbc,mqtt,...}  │
│  ├── api/{loadtest,owasp_scanner,injection_scan,...}            │
│  ├── api/{network analysis: ssl_inspect, dns_inspect, ...}      │
│  └── storage.py — file-backed (~/.theridion/)                  │
└────────────────────────────────────────────────────────────────┘
```

## Vrstvy odpovědnosti

| Vrstva | Co dělá | Co NEdělá |
|---|---|---|
| Tauri shell (Rust) | Spawn sidecar, port handshake, OS dialog, updater, IPC | Business logika, protokol decoding |
| React frontend (TS) | UI, state management, request authoring, response rendering | Network calls — to dělá sidecar |
| Python sidecar | Protocol execution (httpx, grpcio, zeep, aiokafka, paho-mqtt, psycopg2, stomp), assertions, storage | UI rendering |

## Dynamický port handshake

1. Tauri spawn `binaries/theridion-sidecar-<triple>` při startu
2. Sidecar bind 127.0.0.1:0 (random free port), čte token z `~/.theridion/sidecar-token`
3. Tisk `THERIDION_SIDECAR_READY pid=N port=N home=PATH` na stdout
4. Tauri parsuje řádek, vystaví port frontendu přes `get_sidecar_port` Tauri command
5. Frontend dostane port + token, posílá všechny requesty s `X-Theridion-Token` header

Cold start ~6–8 s (PyInstaller --onefile extrakce).

## Plugin sandbox (Tier 1 — V1 only)

V1 podporuje pouze official **Tier 1 Rust pluginy** s Tauri capabilities. Komunitní
Tier 2 (WASM/Extism) odložen post-V1. Subprocess pluginy zakázány — security review
identifikoval RCE riziko.

## File storage layout

```
~/.theridion/
├── collections/
│   ├── default.json              fallback collection
│   └── <name>.json               named collections
├── environments/
│   ├── dev.json, prod.json, ...
├── runs/
│   ├── 2026-05-29T08-15-30Z.json  per-run report
├── load-profiles/
├── security-scans/
├── network-captures/             PCAP files
├── sidecar-token                  chmod 600
├── sidecar.pid                    pid:port watchdog
└── settings.json                  user preferences
```

Atomic writes přes `tempfile + os.replace` v `storage.py`.

## Bundle sizes (per platform)

| OS | Tauri | Sidecar | Total |
|---|---|---|---|
| macOS arm64 | ~5 MB | ~46 MB | ~51 MB |
| macOS x86_64 | ~5 MB | ~46 MB | ~51 MB |
| Linux x64 | ~6 MB | ~50 MB | ~56 MB |
| Windows x64 | ~7 MB | ~48 MB | ~55 MB |

## CI release

`.github/workflows/desktop-release.yml` — tag-triggered, 4 OS targets, code signing
hooks (Apple Developer ID + Windows OV/EV), Tauri updater ed25519 signature.

Viz [`docs/signing.md`](../docs/signing.md).
