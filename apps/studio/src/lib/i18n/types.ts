// ─── i18n types ───────────────────────────────────────────────────────────────

export type Locale = "cs" | "en";
export const LOCALE_KEY = "theridion_net_locale";
export const DEFAULT_LOCALE: Locale = "en";
export const SUPPORTED_LOCALES: Locale[] = ["en", "cs"];

export interface Messages {
  // ── Sidebar ───────────────────────────────────────────────────────────────
  "sidebar.branding": string;
  "sidebar.favorites": string;
  "sidebar.collections": string;
  "sidebar.refresh": string;
  "sidebar.generateTests": string;
  "sidebar.generateTests.shortcut": string;
  "sidebar.newCollection": string;
  "sidebar.importCollection": string;
  "sidebar.filter.placeholder": string;
  "sidebar.collapse": string;
  "sidebar.expand": string;
  "sidebar.shortcuts": string;
  "sidebar.dropImport": string;
  "sidebar.empty.title": string;
  "sidebar.empty.description": string;
  "sidebar.empty.saveHint": string;
  "sidebar.empty.newButton": string;
  "sidebar.folder.newAtRoot": string;
  "sidebar.folder.newSubfolder": string;
  "sidebar.folder.delete": string;
  "sidebar.folder.rename": string;
  "sidebar.collection.rename": string;
  "sidebar.collection.delete": string;
  "sidebar.collection.run": string;
  "sidebar.collection.exportCurl": string;
  "sidebar.collection.exportPostman": string;
  "sidebar.collection.viewStats": string;
  "sidebar.collection.generateDocs": string;
  "sidebar.request.rename": string;
  "sidebar.request.delete": string;
  "sidebar.request.addFavorite": string;
  "sidebar.request.removeFavorite": string;
  "sidebar.collection.health.allPassed": string;
  "sidebar.collection.health.someFailures": string;
  "sidebar.collection.health.errors": string;
  "sidebar.inlineNew.collection": string;
  "sidebar.inlineNew.folder": string;

  // ── Settings modal ────────────────────────────────────────────────────────
  "settings.title": string;
  "settings.tab.general": string;
  "settings.tab.ai": string;
  "settings.tab.editor": string;
  "settings.tab.proxy": string;
  "settings.tab.hub": string;
  "settings.tab.publish": string;
  "settings.tab.shortcuts": string;
  "settings.tab.about": string;
  "settings.cancel": string;
  "settings.save": string;
  "settings.saved": string;

  // Settings > General
  "settings.general.theme": string;
  "settings.general.requestDefaults": string;
  "settings.general.timeout": string;
  "settings.general.followRedirects": string;
  "settings.general.http2": string;
  "settings.general.globalVars": string;
  "settings.general.data": string;
  "settings.general.dataPath": string;

  // Settings > AI
  "settings.ai.provider": string;
  "settings.ai.ollamaBaseUrl": string;
  "settings.ai.ping": string;
  "settings.ai.model": string;
  "settings.ai.refresh": string;
  "settings.ai.privacy": string;
  "settings.ai.connected": string;

  // Settings > Editor
  "settings.editor.fontSize": string;
  "settings.editor.options": string;
  "settings.editor.wordWrap": string;
  "settings.editor.minimap": string;
  "settings.editor.lineNumbers": string;

  // Settings > Proxy
  "settings.proxy.http": string;
  "settings.proxy.http.description": string;
  "settings.proxy.url": string;
  "settings.proxy.bypassLocalhost": string;
  "settings.proxy.ssl": string;
  "settings.proxy.verifySSL": string;
  "settings.proxy.caBundle": string;

  // Settings > Hub
  "settings.hub.title": string;
  "settings.hub.description": string;
  "settings.hub.url": string;
  "settings.hub.token": string;
  "settings.hub.testConnection": string;
  "settings.hub.testConnecting": string;
  "settings.hub.privacy": string;

  // Settings > Publish
  "settings.publish.weave.title": string;
  "settings.publish.weave.description": string;
  "settings.publish.weave.ingestUrl": string;
  "settings.publish.weave.token": string;
  "settings.publish.weave.tokenSet": string;
  "settings.publish.weave.tokenPlaceholderSet": string;
  "settings.publish.weave.tokenPlaceholderEmpty": string;
  "settings.publish.hub.title": string;
  "settings.publish.hub.description": string;
  "settings.publish.hub.ingestUrl": string;
  "settings.publish.hub.token": string;
  "settings.publish.hub.tokenSet": string;
  "settings.publish.status.title": string;
  "settings.publish.status.enable": string;
  "settings.publish.privacy": string;

  // Settings > Shortcuts
  "settings.shortcuts.sendRequest": string;
  "settings.shortcuts.saveRequest": string;
  "settings.shortcuts.saveAs": string;
  "settings.shortcuts.newTab": string;
  "settings.shortcuts.closeTab": string;
  "settings.shortcuts.commandPalette": string;
  "settings.shortcuts.settings": string;
  "settings.shortcuts.closeModal": string;

  // Settings > About
  "settings.about.tagline": string;
  "settings.about.description": string;
  "settings.about.protocols": string;
  "settings.about.stack": string;
  "settings.about.spiderNote": string;

  // Settings > Global Vars editor
  "settings.globalVars.description": string;
  "settings.globalVars.col.on": string;
  "settings.globalVars.col.name": string;
  "settings.globalVars.col.value": string;
  "settings.globalVars.add": string;
  "settings.globalVars.remove": string;
  "settings.globalVars.save": string;
  "settings.globalVars.saved": string;
  "settings.globalVars.loading": string;

  // ── Load workspace panel ──────────────────────────────────────────────────
  "load.header": string;
  "load.targetUrl": string;
  "load.savedRequest": string;
  "load.savedRequest.placeholder": string;
  "load.virtualUsers": string;
  "load.duration": string;
  "load.advanced": string;
  "load.rampUp": string;
  "load.thinkTime": string;
  "load.start": string;
  "load.running": string;
  "load.reset": string;
  "load.empty.title": string;
  "load.empty.description": string;
  "load.recentRuns": string;
  "load.savedRun": string;
  "load.timeline": string;
  "load.timeline.rps": string;
  "load.timeline.avgLatency": string;
  "load.timeline.errors": string;
  "load.metric.totalRequests": string;
  "load.metric.rps": string;
  "load.metric.successful": string;
  "load.metric.failed": string;
  "load.metric.avgLatency": string;
  "load.metric.p50": string;
  "load.metric.p95": string;
  "load.metric.p99": string;
  "load.metric.min": string;
  "load.metric.max": string;
  "load.metric.duration": string;
  "load.errors": string;
  "load.toast.complete": string;
  "load.toast.failed": string;

  // ── Security workspace panel ──────────────────────────────────────────────
  "security.header": string;
  "security.targetUrl": string;
  "security.savedRequest": string;
  "security.savedRequest.placeholder": string;
  "security.queryParams": string;
  "security.queryParams.hint": string;
  "security.scanTypes": string;
  "security.run": string;
  "security.scanning": string;
  "security.reset": string;
  "security.interceptor.open": string;
  "security.interceptor.hint": string;
  "security.empty.title": string;
  "security.empty.description": string;
  "security.recentScans": string;
  "security.savedScan": string;
  "security.score": string;
  "security.noFindings": string;
  "security.findings": string;
  "security.finding": string;
  "security.findingsDetected": string;
  "security.noVulnerabilities": string;
  "security.elapsed": string;
  "security.errors.singular": string;
  "security.errors.plural": string;
  "security.critHigh": string;
  "security.toast.critHigh": string;
  "security.toast.complete": string;
  "security.toast.failed": string;

  // ── Intercept modal ───────────────────────────────────────────────────────
  "intercept.title": string;
  "intercept.connected": string;
  "intercept.disconnected": string;
  "intercept.flows": string;
  "intercept.toggle.intercept": string;
  "intercept.toggle.breakAll": string;
  "intercept.toggle.autoScan": string;
  "intercept.clear": string;
  "intercept.empty.title": string;
  "intercept.empty.hint": string;
  "intercept.selectFlow": string;
  "intercept.forward": string;
  "intercept.editForward": string;
  "intercept.sendEdited": string;
  "intercept.cancel": string;
  "intercept.sendToRequest": string;
  "intercept.edit.label": string;
  "intercept.edit.method": string;
  "intercept.edit.url": string;
  "intercept.edit.body": string;
  "intercept.flags": string;
  "intercept.section.request": string;
  "intercept.section.response": string;

  // ── Common / dialogs ──────────────────────────────────────────────────────
  "common.save": string;
  "common.cancel": string;
  "common.close": string;
  "common.delete": string;
  "common.rename": string;
  "common.confirm": string;
  "common.loading": string;
  "common.noResults": string;
  "common.error": string;
  "common.saved": string;
  "common.reset": string;
  "common.refresh": string;
  "common.add": string;
  "common.remove": string;
  "common.search": string;

  // ── Lang switcher ─────────────────────────────────────────────────────────
  "lang.switcher.aria": string;
  "lang.en": string;
  "lang.cs": string;
}
