# Theridion BE — ADR index

## ADR-001 — Single Tauri binárka + Python sidecar
**Stav:** Accepted
**Kontext:** API testing potřebuje Python ekosystém (httpx http2, zeep WS-Security, grpcio, aiokafka, …). Rust nemá ekvivalenty.
**Rozhodnutí:** Tauri shell (Rust) + Python sidecar (PyInstaller --onefile bundle). Komunikace přes loopback HTTP.
**Důsledky:**
- ✅ Plný Python ekosystém k dispozici
- ✅ Bezpečnostní izolace přes auth token + CORS
- ❌ Cold start ~6–8 s (PyInstaller extrakce)
- ❌ Bundle 46 MB navíc

## ADR-002 — File-based storage (`~/.theridion/`)
**Stav:** Accepted
**Kontext:** Komerční testovací nástroje (Postman) cloud-only — uživatelé tracker říkali, že vyžadují vlastnictví dat + offline support.
**Rozhodnutí:** JSON soubory v `~/.theridion/`, atomic writes, žádný cloud sync ve V1.
**Důsledky:**
- ✅ Git-friendly, plný offline
- ✅ Žádné cloud lock-in
- ❌ Žádný real-time team sharing (řeší to Theridion Hub přes ingest)

## ADR-003 — Plugin sandbox Tier 1 only ve V1
**Stav:** Accepted, post-V1 revize
**Kontext:** Subprocess plugins = security RCE risk (viz security review 2026-05-26).
**Rozhodnutí:** V1 podporuje pouze official Tier 1 Rust pluginy. Tier 2 WASM/Extism odloženo post-V1.
**Důsledky:**
- ✅ Bezpečné pro výchozí distribuci
- ❌ Komunitní pluginy nejsou možné ve V1

## ADR-004 — Tauri updater přes GitHub Releases
**Stav:** Accepted
**Kontext:** Updater potřebuje veřejný endpoint s podpisem. Vlastní server = další infra.
**Rozhodnutí:** `latest.json` artefakt v každém GitHub Release, Tauri updater fetch + ed25519 signature verify.
**Důsledky:**
- ✅ Žádná infra
- ✅ Veřejně auditovatelné release historie
- ❌ Update kanály (stable/beta) složitější — vyřešeno přes oddělené release tagy (`v0.1.0` vs `v0.1.0-beta.1`)

## ADR-005 — Slim sidecar split z monorepo
**Stav:** Accepted (2026-05-29)
**Kontext:** Původní monorepo `theridion` mělo apps/studio + apps/studio-fe + apps/hub. Po splitu BE samostatně nepotřebuje FE-only deps.
**Rozhodnutí:** Theridion BE má vlastní repo `qa-wave/theridion-be` s apps/studio + apps/sidecar. FE+Hub separátní repos.
**Důsledky:**
- ✅ Per-produkt release tagy
- ✅ Per-produkt CI matrix bez cross-dependencies
- ❌ Sdílené komponenty (UI primitives, sidecar core) zatím duplikované — packages/* shared workspace post-V1
