# Theridion Net — doména

## Co řešíme

Tester nebo SRE potřebuje jediný nástroj na 4 kategorie backend testů, který nezávisí
na cloudu, ukládá scénáře jako soubory (git-friendly) a běží lokálně bez internet
připojení.

## Proč ne Postman / SoapUI / K6 / JMeter / ZAP samostatně

Každý z těch nástrojů řeší jedno: Postman REST + GraphQL, SoapUI SOAP/WS-Security,
K6 / JMeter load, ZAP / Burp security, Wireshark / Zenmap network. Týmy končí s 5+
nástroji, 5 různými formáty scénářů, 5 různými CI integracemi a žádnou možností
sdílet test data napříč kategoriemi (např. spustit security scan po integration testu
proti stejnému endpointu).

Theridion Net sjednocuje: jeden binární, jeden soubor `~/.theridion/`, jeden plugin
sandbox, jeden CI runner.

## Cílový uživatel

- **Backend tester / QA inženýr** — autoruje integration testy, občas spouští load
- **SRE / DevOps** — security scans + network analýza, packet capture pro postmortem
- **Bezpečnostní inženýr** — OWASP scans, intercept proxy
- **Backend vývojář** — quick API smoke testy v devel iteraci

## Co NEdělá

- Frontend automatizace (to dělá **Theridion FE**)
- Team dashboard / quality gates monitoring (to dělá **Theridion Hub**)
- Mobilní native testing (Appium-style) — odloženo na 2.0
- Distributed load (1M+ VU) — pro to existuje k6 Cloud, Gatling Enterprise

## Hlavní entity

- **Collection** — strom request scénářů (REST/GraphQL/gRPC/SOAP/Kafka/JMS/JDBC/MQTT/WS), uložené v `~/.theridion/collections/<name>.json`
- **Environment** — sada proměnných (`{{var}}` substituce), per-env barvení v UI
- **Run** — výsledek spuštění collection nebo subset, persistovaný v `~/.theridion/runs/`
- **LoadProfile** — zátěžový scénář (VU ramp, stages, target RPS), spustitelný embedded Locustem nebo externím K6/JMeter/Gatling
- **SecurityScan** — pasivní (probíhá při běhu requestu) nebo aktivní (vlastní iterace s injection payloady)
- **NetworkCapture** — PCAP soubor + filter expression, spustitelné nad běžící collection
