# Theridion BE — runbook

## First-time setup

```bash
git clone git@github.com:qa-wave/theridion-be.git
cd theridion-be/apps/studio
pnpm install
pnpm sidecar:bundle          # ~1 min, builds ~46 MB PyInstaller bundle
pnpm tauri:dev               # opens window
```

Dev port: 1420.

## Test stack

```bash
# Sidecar pytest (~1000 tests, < 3s)
cd apps/sidecar && uv run pytest -q

# Frontend typecheck + build
cd apps/studio && pnpm typecheck && pnpm build

# E2E (~10 tests, ~10s)
cd apps/studio && pnpm test:e2e

# Rust unit
cd apps/studio/src-tauri && cargo test --lib
```

## Release `v0.x.y`

1. Update CHANGELOG.md
2. Commit + push to main
3. `git tag vX.Y.Z && git push origin vX.Y.Z`
4. CI builds 4 OS targets → draft release on GitHub
5. Verify draft assets, edit release notes
6. Promote draft to published

## Troubleshooting

### Sidecar not starting

```bash
# Run sidecar standalone for fast Python iter
cd apps/sidecar && THERIDION_PORT=8765 uv run python -m theridion_sidecar.main

# Check port handshake
curl http://localhost:8765/api/health
# Should return {"status":"ok","version":"..."}
```

### Tauri build cargo error

```bash
cd apps/studio/src-tauri
cargo clean
cd .. && pnpm sidecar:bundle && pnpm tauri:build
```

### PyInstaller bundle too large

Check `apps/sidecar/sidecar.spec` excludes. Heavy deps:
- `grpcio` ~8 MB
- `zeep[xmlsec]` ~5 MB
- `aiokafka` + `paho-mqtt` + `stomp-py` ~3 MB
- `psycopg2-binary` ~2 MB

Removing any of these breaks the corresponding protocol. To slim further see
ADR-005 → Theridion FE which drops all of these (~30 MB bundle).

### Code signing issues

Viz `docs/signing.md` — Apple / Windows cert acquisition + GitHub Secrets setup.

### Updater "incorrect updater private key password"

`TAURI_SIGNING_PRIVATE_KEY` secret musí být **raw content** `.key` souboru (single
base64 string), NE base64-encoded value. Pokud máš key v `~/.tauri/X.update.key`:

```bash
cat ~/.tauri/theridion-be.update.key | gh secret set TAURI_SIGNING_PRIVATE_KEY --repo qa-wave/theridion-be
```

## On-call

- **Failed CI run** → `gh run view <id> --repo qa-wave/theridion-be --log-failed`
- **Sidecar deadlock v prod** → User restart aplikace, kill PID z `~/.theridion/sidecar.pid`
- **Updater stuck** → user smaž `~/.theridion/updater/` cache, restart app

## Příbuzné runbooks

- [theridion-fe runbook](../../theridion-fe/wiki/04-RUNBOOK.md)
- [theridion-hub runbook](../../theridion-hub/wiki/04-RUNBOOK.md)
