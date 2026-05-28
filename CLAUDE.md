## Project metadata

| Klíč | Hodnota |
|---|---|
| **Name** | `theridion-be` |
| **Group** | `qa-tooling` |
| **GitHub** | [qa-wave/theridion-be](https://github.com/qa-wave/theridion-be) |
| **Type** | Desktop (Tauri 2.11) — distributed Win/macOS/Linux binárka |

## Session start

1. `memory/soul.md` — identita BE
2. `memory/memory.md` — index paměti
3. `apps/studio/README.md` — co BE obsahuje za testy
4. `CHANGELOG.md`

---

# Theridion BE — kontext

Backend testing desktop app — 4 testing kategorie v jedné Tauri binárce:

1. **Integration** (Postman/SoapUI replacement) — REST, GraphQL, gRPC, SOAP/WS-Security, Kafka, JMS, JDBC, MQTT, WebSocket
2. **Load** (K6/JMeter/Gatling) — embedded Locust + external runner launchers
3. **Security** (OWASP ZAP/Burp Suite) — proxy + active scans, injection detector
4. **Network analysis** (Wireshark/Zenmap) — packet capture, port scan, TLS inspect

## Layout

\`\`\`
theridion-be/
├── apps/
│   ├── studio/            Tauri shell + React/TS frontend
│   │   ├── src/           UI (Sidebar, RequestPanel, OWASPScannerModal, LoadTestModal, …)
│   │   ├── src-tauri/     Rust shell (com.theridion.be)
│   │   └── tests/e2e/     Playwright E2E
│   └── sidecar/           Python FastAPI sidecar (PyInstaller bundled)
│       ├── theridion_sidecar/  package (api/, storage.py, …)
│       └── sidecar.spec   PyInstaller config
├── .github/workflows/     CI: gate + matrix build (Win/Mac/Linux) + release
├── CHANGELOG.md
└── README.md
\`\`\`

## Stack

| Vrstva | Verze |
|---|---|
| Node | 24 LTS |
| pnpm | 10 |
| Tauri | 2.11 |
| Rust | 1.95 stable |
| Python | 3.13 |
| uv | 0.9 |

## Časté příkazy

\`\`\`bash
cd apps/sidecar && uv run pytest -q
cd apps/studio && pnpm typecheck && pnpm build
cd apps/studio && pnpm test:e2e
cd apps/studio && pnpm sidecar:bundle
cd apps/studio && pnpm tauri:dev
cd apps/sidecar && THERIDION_PORT=8765 uv run python -m theridion_sidecar.main
cd apps/studio/src-tauri && cargo test --lib
\`\`\`

## CI release

Tag push \`v*.*.*\` → \`.github/workflows/desktop-release.yml\`:
- Matrix: 4 OS targets (macos-arm64, macos-x64, ubuntu, windows)
- Bundle formats: .dmg+.app, .deb+.AppImage, .msi+.nsis
- Code signing + notarization sekrety v Settings → Secrets

## Příbuzné projekty

- **theridion-fe** — sourozenecký pro FE automation
- **theridion-hub** — web dashboard, přijímá run ingest

---

Edituj přímo \`CLAUDE.md\`.
