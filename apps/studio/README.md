# Theridion BE

Backend testing desktop app covering 4 categories — integration, load, security and network analysis. Standalone Tauri binary for macOS / Linux / Windows, no cloud.

## Capabilities

### 1. Integration testing (Postman / SoapUI replacement)
Strand panel — request authoring + collections.

| Protocol | Auth | Notes |
|---|---|---|
| REST / HTTP | OAuth2 (Client Credentials, PKCE), Bearer, Basic, API Key | Multipart, JSON, form-data, streaming |
| GraphQL | All HTTP auths | Introspection, variables panel, subscriptions over WS |
| gRPC | TLS + metadata | Proto loading, server reflection, unary + streaming |
| SOAP / WSDL | WS-Security | UsernameToken, XML Signature, Timestamp, BinarySecurityToken, MTOM |
| Kafka | SASL/PLAIN, SSL | Producer/consumer with Avro & JSON Schema, consumer group offsets |
| JMS / ActiveMQ | Username/password | Queue + topic, durable subscribers, message selectors |
| JDBC | Connection string | PostgreSQL, MySQL, Oracle, MSSQL — schema introspection, prepared stmts |
| MQTT 3.1.1 + 5.0 | TLS + client certs | QoS 0/1/2, last-will, retained |
| WebSocket | All HTTP auths | Frames inspection, ping/pong, advanced ops |

### 2. Load testing (K6 / JMeter / Gatling style)
Surge panel — embedded Locust + external runner integration.

- Embedded Locust (Python) — VU ramp, latency histogram, p50/p95/p99
- K6 launcher — converts collection to k6 script, runs `k6 run`
- JMeter launcher — exports as `.jmx`, launches Apache JMeter
- Gatling launcher — generates Scala simulation, launches Gatling runtime
- Result trace viewer (HTML), waterfall, perf budget assertions

### 3. Security testing (OWASP ZAP / Burp Suite style)
Snare panel — active + passive scanners.

- OWASP ZAP proxy integration — passive scan during normal request runs, active scan on demand
- Burp Suite-compatible Intercept mode (modify requests in transit)
- Injection scanner: SQLi, XSS, command injection, path traversal, SSRF
- Sensitive data scanner: leaks in responses, cookie attributes, JWT inspection
- Rate-limit detector, CORS test, content-type validator

### 4. Network analysis (Wireshark / Zenmap style)
Mesh panel — packet capture + port scan.

- Live packet capture via `tcpdump` bridge (Wireshark-compatible PCAP export)
- HAR export with timing breakdown (DNS / TCP / TLS / Transfer)
- Port scanner with service detection (Zenmap-style)
- TLS inspector — cert chain, cipher suite, OCSP, HSTS
- DNS inspector — A/AAAA/CNAME/MX/TXT/SOA records
- Connection stats — keep-alive reuse, HTTP/2 frame analysis

## First-time setup

```bash
cd apps/studio
pnpm install
pnpm sidecar:bundle    # builds Python sidecar → src-tauri/binaries/theridion-sidecar
pnpm tauri:dev         # opens the BE app window
```

Dev port: 1420 (FE app uses 1430).

## Build for distribution

```bash
pnpm sidecar:bundle
pnpm tauri:build       # produces dmg/deb/AppImage/msi in src-tauri/target/release/bundle/
```

## CI release pipeline

See [`.github/workflows/desktop-release.yml`](../../.github/workflows/desktop-release.yml).
Tag-triggered (v*.*.*) → 4 OS targets × 2 apps (BE + FE) = 8 artifacts.

## External runner dependencies (optional)

| Feature | External tool | Install |
|---|---|---|
| K6 launcher | k6 binary | `brew install k6` / [k6.io](https://k6.io/docs/get-started/installation/) |
| JMeter launcher | Apache JMeter | [jmeter.apache.org](https://jmeter.apache.org/download_jmeter.cgi) |
| Gatling launcher | Gatling JVM | [gatling.io](https://gatling.io/open-source/) |
| ZAP proxy | OWASP ZAP | `brew install --cask zap` |
| Packet capture | tcpdump (Linux/macOS) / npcap (Windows) | OS-native |
| Port scanner | nmap | `brew install nmap` / [nmap.org](https://nmap.org/) |

Theridion BE auto-detects installed tools on launch (Settings → Tool integrations).
