# Security Policy

## Reporting a vulnerability

This is a personal project built in public, and issues are closed — but security
reports are welcome and are the one channel that stays open.

Report privately through GitHub's
[private vulnerability reporting](https://github.com/anusbutt/Prospector/security/advisories/new)
(Security tab → "Report a vulnerability"). If that is unavailable, contact me
directly via my GitHub profile.

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce, or a proof of concept.
- Any suggested remediation, if you have one.

I will acknowledge your report, investigate, and keep you updated. Please allow a
reasonable opportunity to address the issue before any public disclosure. As a
solo maintainer I cannot promise a fix window, but I will tell you where things
stand rather than leave you waiting.

## Scope and handling of sensitive data

Prospector is a local command-line tool. A few properties are worth keeping in
mind when reporting or reviewing:

- **Secrets live only in `.env`** (gitignored) and provider secret files under
  `secrets/` (gitignored). Credentials must never be logged, printed, committed,
  or embedded in code. A change that does so is a security bug.
- **The tool sends real email** through the configured provider. Anything that
  could cause it to send without explicit human approval, send from the wrong
  identity, or bypass the daily cap or duplicate-send ledger is in scope.
- **Facebook is never contacted.** Any code path that would cause the tool to
  make a network request to a Facebook/Messenger host is a security-relevant
  defect — please report it.

Thank you for helping keep Prospector and its users safe.
