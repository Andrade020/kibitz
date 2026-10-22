# Code signing and the Windows "unknown publisher" warning

## What happens today

The beta installer is **not code-signed**. Windows SmartScreen therefore shows *"Windows protected your PC — Unknown
publisher"* the first time you run it (**More info → Run anyway**). Browsers may also add a "not commonly downloaded" notice.
This is not a malware verdict: SmartScreen simply doesn't know the publisher yet.

What the project already does to keep the experience as clean as possible without a certificate:

- a real installer (Inno Setup), per-user (no administrator prompt), with a proper uninstaller;
- PyInstaller in **onedir** mode (no self-extracting `onefile` exe, a common antivirus heuristic) and **no UPX**;
- filled-in version resources (product, company, license) and an icon;
- the exact Stockfish binary is pinned by SHA-256 (the same hash as the `winget-pkgs` manifest);
- a published `.sha256` for every installer and a fully open, scripted build.

## The only real fix: a signing certificate

SmartScreen removes the warning for a *signed* installer once the publisher builds reputation (immediately for EV
certificates). Realistic options, cheapest first:

| Option | Cost | Notes |
|---|---|---|
| **[SignPath Foundation](https://signpath.org/foundation)** | Free for open-source | Needs an application, a public repo and a few releases of history. Integrates with GitHub Actions. |
| **Azure Artifact Signing** (formerly Trusted Signing) | ~US$10/month | Identity validation required; availability for individuals varies by country. |
| **OV / EV certificate** (DigiCert, Sectigo…) | ~US$200–500/year | EV gives instant SmartScreen reputation. |
| **Microsoft Store (MSIX)** | One-time registration fee | Store installs don't trigger SmartScreen at all, but add a certification step. |
| **winget** | Free | Installs via `winget install` skip the Mark-of-the-Web prompt; needs a manifest PR to `microsoft/winget-pkgs`. |

## How signing plugs into this repo

`installer/build_windows.ps1` already signs both the app executable and the installer when these environment variables exist
(GitHub: *Settings → Secrets and variables → Actions*):

- `WINDOWS_CERT_PFX_BASE64` — your `.pfx`, base64-encoded (`[Convert]::ToBase64String([IO.File]::ReadAllBytes("cert.pfx"))`)
- `WINDOWS_CERT_PASSWORD` — its password

The release workflow passes them through. Nothing else needs to change. (For SignPath or Azure Artifact Signing, replace the
`Sign-File` function with the provider's action/CLI.) This path is wired but **untested without a real certificate**.
