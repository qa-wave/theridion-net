//! Sidecar lifecycle: spawn the bundled Python binary, parse its ready
//! line for the port number and auth token, and let the frontend ask for
//! both via Tauri commands.
//!
//! The Python sidecar prints a single line on stdout when it's listening:
//!
//! ```text
//! THERIDION_SIDECAR_READY pid=<n> port=<n> token=<token> home=<path>
//! ```
//!
//! We capture that line, store the port and token in app state, and expose
//! `get_sidecar_port` and `get_sidecar_token` as Tauri commands for the
//! frontend to call at startup. If the sidecar dies, we surface a
//! `sidecar://terminated` event so the UI can show a helpful message.

use std::sync::Mutex;

use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
pub struct SidecarState {
    /// Set by the spawn task once the sidecar logs its ready line.
    pub port: Mutex<Option<u16>>,
    /// Auth token extracted from the ready line; sent as X-Theridion-Token.
    pub token: Mutex<Option<String>>,
}

/// Spawn the bundled Python sidecar and wire its stdout to the app state.
///
/// Returns immediately — the actual readiness handshake happens
/// asynchronously inside a background task. Frontend code should poll
/// `get_sidecar_port` until it returns Some.
pub fn spawn(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let sidecar = app.shell().sidecar("theridion-sidecar")?;
    let (mut rx, _child) = sidecar.spawn()?;

    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let text = String::from_utf8_lossy(&line);
                    log::info!("[sidecar stdout] {}", text.trim_end());
                    if let Some((port, token)) = parse_ready_line(&text) {
                        let state: State<SidecarState> = app_handle.state();
                        *state.port.lock().unwrap() = Some(port);
                        *state.token.lock().unwrap() = Some(token);
                        let _ = app_handle.emit("sidecar://ready", port);
                    }
                }
                CommandEvent::Stderr(line) => {
                    log::info!("[sidecar stderr] {}", String::from_utf8_lossy(&line).trim_end());
                }
                CommandEvent::Terminated(payload) => {
                    log::warn!("sidecar terminated: code={:?} signal={:?}", payload.code, payload.signal);
                    let _ = app_handle.emit("sidecar://terminated", ());
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(())
}

/// Public command: returns the port the sidecar is listening on, or
/// None if it hasn't reported ready yet (cold start can take ~8 s for
/// the bundled --onefile binary).
#[tauri::command]
pub fn get_sidecar_port(state: State<'_, SidecarState>) -> Option<u16> {
    *state.port.lock().unwrap()
}

/// Public command: returns the auth token the sidecar expects in
/// `X-Theridion-Token`, or None if the sidecar hasn't started yet.
#[tauri::command]
pub fn get_sidecar_token(state: State<'_, SidecarState>) -> Option<String> {
    state.token.lock().unwrap().clone()
}

/// Parse a sidecar ready line and return `(port, token)`.
///
/// Expected format (field order is not significant):
///
/// ```text
/// THERIDION_SIDECAR_READY pid=42 port=8765 token=abc home=/tmp/x
/// ```
fn parse_ready_line(line: &str) -> Option<(u16, String)> {
    if !line.contains("THERIDION_SIDECAR_READY") {
        return None;
    }
    let port = line
        .split_whitespace()
        .find_map(|tok| tok.strip_prefix("port="))
        .and_then(|v| v.parse::<u16>().ok())?;
    let token = line
        .split_whitespace()
        .find_map(|tok| tok.strip_prefix("token="))
        .map(str::to_owned)?;
    Some((port, token))
}

#[cfg(test)]
mod tests {
    use super::parse_ready_line;

    #[test]
    fn parses_a_well_formed_ready_line() {
        let line = "THERIDION_SIDECAR_READY pid=42 port=8765 token=abc123xyz home=/tmp/x\n";
        let result = parse_ready_line(line);
        assert_eq!(result, Some((8765, "abc123xyz".to_owned())));
    }

    #[test]
    fn ignores_unrelated_lines() {
        assert_eq!(parse_ready_line("INFO: Started server process [42]"), None);
    }

    #[test]
    fn returns_none_when_port_is_garbage() {
        let line = "THERIDION_SIDECAR_READY pid=1 port=NaN token=tok\n";
        assert_eq!(parse_ready_line(line), None);
    }

    #[test]
    fn returns_none_when_token_is_missing() {
        let line = "THERIDION_SIDECAR_READY pid=1 port=8765 home=/tmp\n";
        assert_eq!(parse_ready_line(line), None);
    }
}
