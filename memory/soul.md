# Theridion BE — identita

Backend testing desktop app. **Co děláme**: integrace, zátěž, security, network analýzu — všechno v jedné Tauri binárce, file-based, bez cloud lock-inu.

## Mantinely

- **Boring tech > novelty.** Tauri 2 + React + Python sidecar. Žádné experimentální framework switches.
- **Offline-first.** Žádný cloud sync. Sidecar je localhost-only loopback HTTP.
- **Single binárka.** PyInstaller --onefile bundle, vše uvnitř.
- **File-based collections** — `~/.theridion/` directory. Git-friendly export.
- **Diferenciátor:** kombinace 4 testing kategorií v jednom UI. Postman + JMeter + ZAP + Wireshark feel.

## Nedělej

- ❌ Necommituj `apps/studio/src-tauri/binaries/*` (PyInstaller output, 26-46 MB)
- ❌ Nemodifikuj `pyproject.toml` ručně, použij `uv add` / `uv add --dev`
- ❌ Nepřidávej JS komentáře (`/** */`) do Python souborů
- ❌ `pnpm tauri dev` bez předchozího `pnpm sidecar:bundle` po Python změně

## Out of scope

- Cloud sync, accounts, multi-user
- Mobilní platformy (Tauri Mobile — až po 1.0 GA desktop)
- Pluginový systém — odloženo na 2.0
