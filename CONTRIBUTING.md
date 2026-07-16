# Contributing to AI Assistant

Thanks for your interest in improving AI Assistant! Contributions of all kinds
are welcome — bug reports, feature ideas, documentation, and code.

## Getting started

1. Fork and clone the repository.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   playwright install --with-deps chromium
   ```
3. Copy `.env.example` to `.env` and add at least one LLM key.
4. Run the app locally:
   ```bash
   python main.py
   ```

## Development workflow

- Create a feature branch off `main`: `git checkout -b feature/my-change`.
- Keep changes focused and write clear commit messages.
- Follow the existing code style. We use [ruff](https://docs.astral.sh/ruff/)
  for linting:
  ```bash
  ruff check .
  ```
- Add or update tests where it makes sense and run them:
  ```bash
  pytest
  ```
- Open a pull request describing **what** changed and **why**.

## Adding an integration

Integrations follow the "empty key = disabled" rule: read credentials from
settings in `src/config.py`, and no-op cleanly when they are absent. New tools
live under `src/tools/` and are registered with the agent in `src/agent/`.

## Reporting bugs

Open an issue with reproduction steps, expected vs. actual behavior, and your
environment. Never paste real secrets, tokens, or session files into an issue.

## Code of conduct

Be respectful and constructive. We want this to be a welcoming project.
