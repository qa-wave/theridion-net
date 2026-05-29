# Code signing — Theridion BE

Unsigned builds work on all platforms but trigger OS warnings:
- **macOS** — Gatekeeper blocks "unidentified developer" apps
- **Windows** — SmartScreen flags unsigned executables
- **Linux** — no signing required

For production releases users actually install without friction, you need:

| Cert | Cost | Issued by | Setup time |
|---|---|---|---|
| Apple Developer ID | $99 / year | Apple Developer Program | ~1 day |
| Windows Code Signing (OV) | $200–400 / year | DigiCert / Sectigo / SSL.com | ~1 week (identity verification) |
| Windows Code Signing (EV) | $400–600 / year | Same vendors + hardware HSM | ~2 weeks |
| Linux | Free | n/a | — |

## Tauri updater key (already configured)

Generated locally via `pnpm dlx @tauri-apps/cli signer generate -w ~/.tauri/theridion-be.update.key`.

- Public key — embedded in `src-tauri/tauri.conf.json` `plugins.updater.pubkey`
- Private key — `~/.tauri/theridion-be.update.key` (gitignored)
- GitHub secret `TAURI_SIGNING_PRIVATE_KEY` = base64 of private key file
- GitHub secret `TAURI_SIGNING_PRIVATE_KEY_PASSWORD` = empty (no passphrase)

Updater signatures get verified by every running instance before installing
the update — without them Tauri refuses the download. Already enabled in CI.

## macOS — Apple Developer ID

1. Enroll at https://developer.apple.com/programs/ ($99/year, 1–2 business days)
2. In Xcode → Settings → Accounts, sign in with your Apple ID
3. Go to https://developer.apple.com/account/resources/certificates/list
4. Create **"Developer ID Application"** certificate (not "Mac App Distribution")
5. Download the `.cer` → double-click to install into Keychain
6. In Keychain Access (login keychain), right-click your "Developer ID Application: …" identity → Export → save as `.p12` with password
7. Set GitHub secrets:
   ```bash
   gh secret set APPLE_CERTIFICATE --repo qa-wave/theridion-be < <(base64 -i developer-id.p12)
   gh secret set APPLE_CERTIFICATE_PASSWORD --repo qa-wave/theridion-be
   gh secret set APPLE_SIGNING_IDENTITY --repo qa-wave/theridion-be  # e.g. "Developer ID Application: Tomáš Mertin (TEAMID12)"
   ```

8. For notarization (required for distribution outside App Store):
   - Generate **app-specific password** at https://appleid.apple.com/account/manage → Sign-In and Security → App-Specific Passwords → "Theridion notarize"
   - Find your **Team ID** at https://developer.apple.com/account → Membership Details
   ```bash
   gh secret set APPLE_ID --repo qa-wave/theridion-be             # your Apple ID email
   gh secret set APPLE_PASSWORD --repo qa-wave/theridion-be       # the app-specific password
   gh secret set APPLE_TEAM_ID --repo qa-wave/theridion-be        # 10-char Team ID
   ```

After secrets are set, the next `v*.*.*` tag push will produce signed + notarized `.dmg` artifacts.

## Windows — Code Signing cert

Cheapest path (OV cert from SSL.com via Azure Trusted Signing):

1. Sign up at https://www.ssl.com/certificates/ev-code-signing/ (or any vendor)
2. Go through identity verification (~3–5 business days)
3. Receive `.pfx` via secure download
4. Set GitHub secrets:
   ```bash
   base64 -i theridion-be.pfx | tr -d '\n' | gh secret set WINDOWS_CERTIFICATE_PFX_BASE64 --repo qa-wave/theridion-be
   gh secret set WINDOWS_CERTIFICATE_PASSWORD --repo qa-wave/theridion-be
   ```

After secrets are set, `.msi` artifacts will be Authenticode-signed automatically.

## Linux

No signing required. AppImage supports optional GPG signature (`.AppImage.zsync`)
but it's not enforced by any major distro. Skip for V1.

## Verification post-release

```bash
# macOS — verify signature + notarization
codesign --verify --deep --verbose=2 /Applications/Theridion\ BE.app
spctl --assess --type execute --verbose=4 /Applications/Theridion\ BE.app

# Windows — verify signature (PowerShell)
Get-AuthenticodeSignature "C:\Program Files\Theridion BE\theridion-be.exe"

# Linux — verify checksum from GitHub Release SHA256SUMS
sha256sum --check SHA256SUMS
```
