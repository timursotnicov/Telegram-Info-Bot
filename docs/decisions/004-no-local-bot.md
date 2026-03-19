# 004: No Local Bot Runs

- **Date:** 2026-03
- **Status:** Accepted

## Context

Telegram allows only one active polling connection per bot token. Running the bot locally while it is already running on the server causes polling conflicts -- both instances fight for updates, leading to missed messages and errors.

## Decision

Never run the bot locally. All deployments and testing happen on the production server via SSH (`ubuntu@151.145.86.66`). Use `deploy/setup.sh` for initial setup and `systemctl restart savebot` for updates.

## Consequences

- Local development is limited to writing code, running tests (`pytest`), and linting.
- Every code change must be pushed to git and pulled on the server to test.
- No staging environment exists; the production server is the only runtime.
