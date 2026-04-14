# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| `main`  | Yes       |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Email: open a [GitHub Security Advisory](https://github.com/akkupratap323/clawspan/security/advisories/new) (private disclosure).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

We will acknowledge within 48 hours and aim to patch critical issues within 7 days.

## Threat model

Clawspan runs locally on your machine. It is **not** designed to be exposed to the internet. Key assumptions:

- The machine running Clawspan is trusted and access-controlled.
- API keys in `.env` are secrets — never commit `.env` to version control.
- The voice passphrase gate is a convenience lock, not a strong authentication mechanism. Do not rely on it as your only security layer.
- The `tools/terminal.py` command executor uses an allowlist. Only extend it with commands you trust.

## Known limitations

- Voice passphrase matching relies on speech-to-text transcription, which can be fooled by similar-sounding phrases.
- The terminal tool executes real shell commands — prompt injection via crafted user input is a risk. Mitigated by the command allowlist in `tools/terminal.py`.
- Memory stored in `~/.mempalace/` is unencrypted on disk. Protect it with OS-level disk encryption (FileVault on macOS).

## Dependency security

Run `pip audit` to check for known vulnerabilities in dependencies:

```bash
pip install pip-audit
pip-audit
```
