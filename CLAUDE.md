# Theridion — kontext pro Claude

Modern, file-based, open-source API testing platform. Pozicování:
**moderní SoapUI + Playwright-style runner** — REST + GraphQL/gRPC/SOAP +
performance + security testing v jednom desktop nástroji. Jméno z rodu
pavouků *Theridion*, kteří staví nepravidelné 3D cobweby — metafora pro
zamotané závislosti API.

## Pracovní styl

Postupuj přímo k řešení. Pokud potřebuješ použít nástroj, analyzovat
data nebo provést výpočet, udělej to rovnou. Neptej se na povolení,
pokud to není kriticky nutné pro bezpečnost.

**Po každé změně testuj.** Sidecar přes pytest, frontend přes
Playwright E2E. Nikdy nespoléhej na "build prošel = funguje" —
TypeScript a cargo prošly i v session, kdy backend/frontend ve
skutečnosti zlobil (CORS, ESM, nesprávný locator). E2E suite tyhle
chyby chytá.

## Architektura

```
┌──────────────────────────────────────────────────────────┐
│ Tauri 2 (Rust shell, ~5 MB) + WebView                    │
│  ┌────────────────────────────────────────────────────┐  │
│  │ React 18 + TypeScript + Tailwind v3 + shadcn vibe  │  │
│  │ Monaco editor (CDN) · lucide-react v1 · vite 6     │  │
│  └────────────────────┬───────────────────────────────┘  │
└────────────────────────┼─────────────────────────────────┘
                         │ HTTP / loopback
                         │ port resolved via Tauri command
┌────────────────────────┴─────────────────────────────────┐
│ Python sidecar — FastAPI 0.115+, httpx[http2], zeep      │
│  /api/health · /api/diagnostics                          │
│  /api/requests/execute (REST + {{var}} substituce)       │
│  /api/collections (CRUD + folders, tree)                 │
│  /api/environments (CRUD + variables)                    │
│  /api/soap/{inspect,execute} (zeep-backed)               │
└──────────────────────────────────────────────────────────┘
```

**Sidecar je v dev módu spawnován Tauri shellem** z bundlovaného
PyInstaller binárka v `apps/desktop/src-tauri/binaries/`. Stdout
ready-line `THERIDION_SIDECAR_READY pid=N port=N home=PATH` Rust
parsuje a port vystaví frontendu přes `get_sidecar_port` Tauri command.
Cold start ~6–8 s (PyInstaller --onefile).

Pro rychlý Python iter přes browser tab fallback: `pnpm dev` (1420) +
sidecar puštěný ručně na `THERIDION_PORT=8765`.

## Layout

```
theridion/
├── apps/
│   ├── desktop/                Tauri + React frontend
│   │   ├── src/                React/TS source
│   │   │   ├── components/     UI komponenty (Sidebar, RequestPanel, …)
│   │   │   ├── lib/sidecar.ts  Sidecar HTTP klient + URL resolver
│   │   │   └── state/types.ts  Sdílené typy + helpers
│   │   ├── src-tauri/          Rust shell (Tauri 2)
│   │   │   ├── src/lib.rs      App setup
│   │   │   ├── src/sidecar.rs  Sidecar spawn + port handshake (3 ut)
│   │   │   ├── binaries/       PyInstaller output (gitignored)
│   │   │   ├── icons/          Tangleweb spider mark + favicons
│   │   │   └── tauri.conf.json
│   │   ├── tests/e2e/          Playwright tests (smoke, collections, env, soap)
│   │   └── playwright.config.ts
│   └── sidecar/                Python FastAPI service
│       ├── theridion_sidecar/  package
│       │   ├── api/            routery (collections, environments, soap, …)
│       │   ├── storage.py      file-backed collection store (tree)
│       │   ├── environments.py file-backed env store + substituce
│       │   ├── soap.py         zeep wrapper
│       │   ├── models.py       pydantic models
│       │   └── main.py         FastAPI app + entry
│       ├── scripts/
│       │   ├── sidecar_entry.py  PyInstaller entrypoint
│       │   └── build-bundle.sh   builds binary, stages do desktopu
│       ├── sidecar.spec        PyInstaller spec
│       ├── tests/              pytest (35 testů, < 1 s)
│       │   └── fixtures/       calculator.wsdl pro SOAP testy
│       └── pyproject.toml
├── logos/                      SVG zdroje (mark + icon)
├── .github/workflows/ci.yml    sidecar / desktop matrix / e2e jobs
├── README.md
└── CLAUDE.md                   ← ty
```

## Stack — ostré hodnoty

| Vrstva | Verze / nástroj |
|---|---|
| Node | 24 LTS |
| pnpm | 10 |
| Tauri | 2.11 |
| Rust | 1.95 stable |
| Python | 3.13 (CI), 3.14 (lokální dev — funguje) |
| uv | 0.9 |
| FastAPI | ≥ 0.115 |
| zeep | 4.3.2 (4.x odebralo `Client.wsdl.target_namespace` — viz `soap.py` fallback) |
| lucide-react | 1.14 (ne 0.x — neměň jen tak) |
| `@monaco-editor/react` | 4.7 |

## Klíčové porty

| Port | Co | Kdy |
|---|---|---|
| 1420 | Vite dev | `pnpm tauri dev` / `pnpm dev` |
| 1421 | Vite test | Playwright |
| 8765 | Sidecar dev (manuální) | standalone Python iter |
| 8766 | Sidecar test | Playwright |
| ?    | Sidecar bundlovaný | Tauri spawnuje na náhodný free port |

## Časté příkazy

```bash
# Sidecar tests (35, < 1 s)
cd apps/sidecar && uv run pytest -q

# Frontend typecheck + build
cd apps/desktop && pnpm typecheck && pnpm build

# E2E (7 testů, ~9 s, izolovaný sidecar+vite na 8766/1421)
cd apps/desktop && pnpm test:e2e
cd apps/desktop && pnpm test:e2e:ui   # interaktivní debugger

# Build sidecar bundle (po Python změnách, nutné před tauri dev)
cd apps/desktop && pnpm sidecar:bundle

# Spustit aplikaci v dev módu
cd apps/desktop && pnpm tauri dev

# Standalone sidecar pro fast Python iter (pak frontend přes pnpm dev v browser tabu)
cd apps/sidecar && THERIDION_PORT=8765 uv run python -m theridion_sidecar.main

# Rust unit tests
cd apps/desktop/src-tauri && cargo test --lib
```

## Konvence

### TypeScript / React
- Strict mode zapnuto (`tsconfig.json`).
- `noUnusedLocals` + `noUnusedParameters` — neuse importy a parametry
  vyhazují, čisti za sebou.
- Tailwind utility classes inline; žádné CSS-in-JS.
- Komponenty v PascalCase, hooks v camelCase.
- State v `App.tsx` + props down (žádný global state lib zatím).
- Color palette: `bg-neutral-950` (canvas), `bg-neutral-925`
  (chrome panely — vlastní token v tailwind.config.js), `bg-neutral-900`
  (cards), borders `border-neutral-800`, akcent `emerald-500/600`.

### Python
- 3.13+ syntax, `from __future__ import annotations`.
- pydantic v2 modely jako wire + on-disk schema (jeden zdroj pravdy).
- Atomic file writes (write-tempfile + `os.replace`) — viz
  `storage._atomic_write`.
- **NE** JavaScript komentáře (`/** */`) v Pythonu. Já jsem to udělal,
  testy se sesypaly. Python = `#` nebo `"""docstring"""`.
- ruff lint + mypy strict (mypy je v CI `continue-on-error`, dokud
  nepodříznem všechen typ-untyped kód).

### Rust
- Idiomatický Tauri 2 (žádný `Window` API z v1).
- Trait imports explicitně (`use tauri::Emitter` — chtělo to kvůli
  `app_handle.emit()`).
- Pro doctest v module-level docs používej ` ```text ` blocks pro
  ne-Rust ukázky, jinak cargo test selže.

### Git
- Commity v angličtině, formát: krátký subject (under 70 chars) +
  motivovaný popis. Co i proč, ne jen co.
- `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
  trailer na konci, bez prázdného řádku navíc.
- Atomic commits — jeden concern jeden commit (J vs E vs G v této
  session jsem dělal odděleně).
- `*.tsbuildinfo`, `dist/`, `target/`, `binaries/`, `__pycache__/`,
  `.venv/` jsou v `.gitignore`. Bundlované binárky se NEcommitují
  (26 MB × 4 platformy = neudržitelné).
- Před commit: `git status -s` a explicitně `git add <paths>` raději
  než `git add -A`. Bezpečnější před secrets.

## Známé gotchas (potkal jsem v session, neopakovat)

1. **PyInstaller cold start ~6–8 s** — bundlovaný --onefile binárky.
   Stdout je až za extrakcí. Když test nedostane odpověď do 4 s,
   neznamená to že crashl — počkej 10 s, zkus znovu.
2. **`__dirname` neexistuje v ESM** — Playwright spec je ESM. Použij
   `path.dirname(fileURLToPath(import.meta.url))`.
3. **Strict-mode locator violations** — `getByText("Add")` chytí 2
   prvky pokud je v tree i v selected header. Použij `{ exact: true }`
   nebo cílový `getByRole("button", { name: "Add", exact: true })`.
4. **macOS `setsid` neexistuje** — Linux-only. Pro detached process
   stačí `nohup … &` + `disown`.
5. **`mv source target` v zsh, když target existuje** — nepřepíše,
   vloží source DOVNITŘ targetu. Před `mv` ověř, že target neexistuje
   nebo je opravdu kontejner.
6. **`pkill -f "pattern"` občas mine** — ověř `ps aux | grep` po něm.
   Ztratil jsem hodinu na "uptime bug" co byla 36h stará instance.
7. **Test ordering matters** — Playwright spustí soubory abecedně,
   workers=1, sdílí storage root. Smoke testy nesmí předpokládat
   prázdný stav, pokud poběží PO collections testu.
8. **CORS allow-list pro localhost je zlo** — v test prostředí
   přidávat porty nikdy nestihneš. Použij regex
   `^https?://(localhost|127\.0\.0\.1)(:\d+)?$`.
9. **lucide-react v1.14 je instalovaná** — má novější API než 0.x.
   Pokud chyba o ikoně, ověř existenci v aktuální verzi.
10. **Sidecar potřebuje rebuild po Python změně** — `pnpm sidecar:bundle`.
    V dev je to nepříjemné (~30 s build). Pro fast iter používej
    standalone sidecar (port 8765) + `pnpm dev`, ne `pnpm tauri dev`.

## Co je hotovo (status k 2026-05-09)

✅ Tauri shell + Python sidecar walking skeleton  
✅ 3-pane UI (sidebar / request / response) + tab strip  
✅ Logo + ikona set (Tangleweb mesh)  
✅ File-based collections store s folder hierarchií  
✅ Save-to picker (collection + name)  
✅ Environment variables s `{{var}}` substitucí  
✅ Monaco editor pro request/response body  
✅ SOAP/WSDL inspect + execute (zeep)  
✅ Playwright E2E suite (7 testů) izolovaný od dev sidecaru  
✅ Sidecar diagnostics endpoint + PID file  
✅ PyInstaller bundling + Tauri sidecar spawn + port handshake  

## Roadmapa (po dokončení A)

### Sprint 1 — credibility (table stakes)
1. **Auth helpers** — Bearer, Basic, OAuth2, API Key, AWS SigV4
   (Auth tab v `RequestPanel.tsx` je teď stub).
2. **Cookies jar** — `httpx.AsyncClient(cookies=...)` + persistovat
   napříč requesty per env.
3. **cURL import + "Copy as cURL"** — bidirekcionální.
4. **Inline rename** + drag-drop v sidebaru (teď `prompt()`, fuj).

### Sprint 2 — automation (Playwright-style)
5. **Tests/Asserts** — declarative DSL (status, JSON path, response
   time, schema). Ne JS sandbox, prozatím.
6. **Pre-request scripts** — JS sandbox v Tauri webview.
7. **Collection runner** + **CLI** (`theridion test … --shard 1/4`)
   s **HTML trace reportem** (Playwright-style, ne JUnit XML).
8. **`theridion test --ui` mode** — sama appka jako interaktivní runner.

### Sprint 3 — protokoly mimo REST
9. **GraphQL** native (introspection, autocomplete, variables panel).
10. **gRPC** native (proto loading, server reflection).
11. **WebSocket** (connect, frames, ping/pong).

### Sprint 4 — SoapUI killer (naše propozice)
12. **WS-Security** — `signxml` + `xmlsec` (XML Signature, Encryption,
    UsernameToken, X.509). Tady je největší konkurenční mezera —
    Postman/Insomnia tohle nepokrývají vůbec.
13. **MTOM/XOP attachments**.
14. **XSD validation** s lidsky čitelnými errors.
15. **Mock SOAP/REST server** (host fake endpoint).

### Sprint 5 — performance & security
16. **Load testing** přes embedded `locust`.
17. **OWASP-style scans** (SQL injection, XSS, boundary, fuzzing).
18. **Schema fuzzing**.

### Sprint 6 — UX polish
19. **History panel**.
20. **Console / timing breakdown** (DNS, TCP, TLS, transfer).
21. **Templating fns** (`{{$timestamp}}`, `{{$uuid}}`, `{{$faker.*}}`).
22. **Multi-scope vars** (global > collection > env > runtime).
23. **Diff response**.
24. **Bulk edit**.

## Strategická poznámka

Nesnažíme se napodobit Postman feature-by-feature. Jejich hodnota je
**team workspaces + cloud sync + 10 let CDN**. Naše propozice je:

> **Theridion = Bruno UI/file-based git ops + SoapUI WS-* síla +
> Playwright-style test runner.**

To, co umíme jednoznačně líp:
1. Plný WS-Security (Postman ani Insomnia to neumí).
2. Performance + security testing v jednom (SoapUI to má, ale UI z 2005).
3. Trace viewer pro test runy (žádný API tester to dnes nemá).
4. Git-friendly file format (proti Postmanovu cloudu — cílíme na týmy
   co chtějí vlastnictví dat).

## Nedělej

- ❌ Nemodifikuj `pyproject.toml` ručně, použij `uv add` / `uv add --dev`.
- ❌ Necommituj `apps/desktop/src-tauri/binaries/*` (.gitignore to chytá,
   ale verifikuj).
- ❌ Nepoužívej `git add -A` — vždy explicitně cesty.
- ❌ Neměň `tsconfig.json` strict pravidla bez diskuze.
- ❌ Nepiš nové tests bez E2E coverage pro UI flow (sidecar pytest
   stačí pro backend, Playwright pro UI).
- ❌ Nedělej `git commit --amend` — vytvoř nový commit.
- ❌ Nepřidávej JS komentáře (`/** */`) do Python souborů.
- ❌ Nepřepisuj sidecar storage formát bez migrace pro starší soubory
   (`models.CollectionItem.is_folder` defaultuje False, takže legacy
   collections načteme bez problému — neporušuj to).

## Mimo scope (zatím)

- Cloud sync, accounts, multi-user.
- Mobilní platformy (iOS/Android via Tauri Mobile — ano až po desktop GA).
- Pluginový systém — Bruno/Insomnia ho mají, my můžeme přidat až po
  Sprint 4.
- AI assistant — atraktivní (Postbot ekvivalent přes Claude API), ale
  neprioritní před credibility features.

---

Pokud potřebuješ tenhle dokument upravit, edituj přímo `CLAUDE.md`
v rootu repa a commitni jako "Update CLAUDE.md: …". Nepřidávej
duplicitní context dokumenty.
