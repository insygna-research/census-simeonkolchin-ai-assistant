# Security Policy

## Reporting a vulnerability

If you discover a security vulnerability, please **do not** open a public
issue. Instead, report it privately:

- Use GitHub's [private vulnerability reporting](https://github.com/simeonkolchin/ai-assistant/security/advisories/new), or
- Contact the maintainer directly through their GitHub profile.

Please include:

- A description of the vulnerability and its impact
- Steps to reproduce
- Any relevant logs or proof-of-concept (with secrets redacted)

We aim to acknowledge reports within a few days and will keep you updated on
remediation progress.

## Handling secrets

- All credentials live in `.env`, which is gitignored. Never commit real keys.
- `.env.example` contains **placeholders only**.
- Telegram session files (`*.session`) are gitignored and must never be
  committed — they grant full access to the associated account.
- The web UI is protected by OIDC / JWT; Telegram actions are restricted to an
  allowlist of chats.

## Supported versions

This is an actively developed project; security fixes target the `main` branch.
