# Job Tracker

A job application tracker that replaced my Excel sheet. A FastAPI backend stores everything in PostgreSQL, a keyboard-first kanban UI sits on top, and an optional Gmail sync picks up confirmations, assessment invites, interview requests and rejections from my inbox.

**[Live demo](https://job-tracker-demo.onrender.com)** runs on sample data from invented companies and resets every hour. It's on a free server, so the first visit can take up to a minute to wake it.

![Overview: scoreboard, stage spectrum, Gmail suggestions and the needs-attention queue](docs/screenshots/overview.png)

**Stack:** Python 3.11+, FastAPI, PostgreSQL (psycopg 3, plain SQL migrations), vanilla JS/HTML/CSS, IMAP for Gmail, optional Claude or OpenAI API. Tests run with pytest against a real Postgres database.

## Features

- **Board.** Applications move through Wishlist → Applied → Assessment → Interviewing → Offer → Closed (rejected / withdrawn / ghosted). Drag a card to change its stage, and the move is logged on its timeline with the date.
- **Needs attention.** Shows overdue follow-ups, wishlist deadlines in the next 7 days, and applications that have gone quiet: 21 days with no reply after applying, or 10 days with no update after an assessment or interview.
- **List and Stats.** The list can be sorted and searched. Stats covers reply and interview rates, applications sent per week, and breakdowns by sector, source and job type.
- **Next steps.** Each application can have a "next step" and a date (say, *CodeSignal OA, Thu*), shown on its card and flagged once it's due.
- **Keyboard-first.** Press `?` in the app for the full list of shortcuts.
- **Light and dark.** Follows your system setting. The sun/moon button (or `T`) switches it, and switching back to your system's theme makes the app follow the system again.
- **Excel in and out.** Import an `.xlsx`/`.csv` file, or paste cells copied from Excel. Export to `.xlsx` or CSV.
- **Fill from a job posting (optional).** Paste a posting and Claude or ChatGPT fills in the company, role, location, pay and deadline. See [AI help](#ai-help-optional).
- **Gmail sync.** Finds application confirmations, assessment invites, interview requests and rejections in your inbox. New applications are added automatically, and stage changes wait for you to accept them.
- **Plain SQL underneath.** Two tables and a reporting view. Query them from `psql` (see `sql/queries.sql`).

## Screenshots

| Board | Stats |
| --- | --- |
| ![Kanban board with cards in each stage](docs/screenshots/board.png) | ![Stats: conversion funnel, time to hear back, sent per week, activity heatmap](docs/screenshots/stats.png) |

| Dark mode | Board, dark |
| --- | --- |
| ![Overview in dark mode](docs/screenshots/overview-dark.png) | ![Kanban board in dark mode](docs/screenshots/board-dark.png) |

![Detail panel in dark mode, with stage stepper, next step and fields](docs/screenshots/detail-dark.png)

## Setup

The app runs on Linux and Windows. Pick your system below; after setup, everything works the same way on both.

### Linux (CachyOS / Arch)

**1. PostgreSQL.** Skip any step you've already done.

```fish
sudo pacman -S --needed postgresql uv
sudo -iu postgres initdb -D /var/lib/postgres/data      # first time only
sudo systemctl enable --now postgresql
sudo -iu postgres createuser -s $USER                   # a Postgres role matching your Linux user
```

The default connection string is `postgresql:///jobtracker`. It connects over the local Unix socket as your Linux user, with no password. The app creates the `jobtracker` database the first time it runs.

**2. The app.**

```fish
cd job-tracker
cp .env.example .env         # optional: Gmail app password, Claude key
uv tool install .            # puts `jobtracker` in ~/.local/bin
uv tool update-shell         # first time only, if fish can't find `jobtracker`
jobtracker install           # runs it in the background now and on every login
```

Open http://localhost:8765, or search "Job Tracker" in your app launcher. There's no terminal to keep open. `jobtracker install` does four things:
- copies `.env` to `~/.config/jobtracker/env`, where the app reads its settings from now on;
- creates the database;
- adds a systemd user service;
- adds a launcher entry.

If the app doesn't come up, `journalctl --user -u jobtracker -e` shows why.

### Windows 10 / 11

Run these in PowerShell or Windows Terminal. None of them need an admin window, but the PostgreSQL installer will ask for approval once.

**1. PostgreSQL and uv.**

```powershell
winget install --id PostgreSQL.PostgreSQL.18 -e
winget install --id astral-sh.uv -e
```

Installed this way, PostgreSQL runs as a Windows service that starts with the computer. Its superuser is `postgres`, with the password `postgres`. If you installed it some other way and picked your own password, use that password below. Close and reopen the terminal so `uv` is on your PATH.

**2. The app.** Unzip or clone the project, then:

```powershell
cd job-tracker
copy .env.example .env
notepad .env
```

In Notepad, add this line, then save:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/jobtracker
```

Windows has no Unix socket, so the app needs the address and password spelled out. If your password has symbols such as `@`, `:` or `/`, [URL-encode](https://developer.mozilla.org/en-US/docs/Glossary/Percent-encoding) them. Then run:

```powershell
uv tool install .
uv tool update-shell         # first time only; then open a new terminal
jobtracker install
```

Open http://localhost:8765, or type "Job Tracker" in the Start menu. `jobtracker install` does four things:
- copies `.env` to `%APPDATA%\jobtracker\env`, where the app reads its settings from now on;
- creates the database;
- adds the app to your sign-in programs, so it starts whenever you sign in to Windows;
- adds a Start-menu shortcut.

It runs without a window. If it doesn't come up, its log is at `%LOCALAPPDATA%\jobtracker\jobtracker.log`. To see it in Task Manager or under **Settings → Apps → Startup**, look for `jobtracker-bg`.

### Day to day (both systems)

| To... | Run |
| --- | --- |
| Apply settings changes | `jobtracker restart` |
| Update to a new version | from the project folder: `uv tool install . --reinstall` then `jobtracker restart` |
| Import your data | `jobtracker import-json file.json` (works while the app is running) |
| Remove the background app | `jobtracker uninstall` (keeps your settings and data) |

**Just trying it out?** Run `uv run jobtracker serve --open` from the project folder instead. It stops when you close the terminal.

### Bring your data over

- **From your Excel sheet:** click **Import from Excel**, choose the file, check how the columns were matched, then import.
- **From the claude.ai tracker:** click **Export → Excel** there, then import that file here.

The import skips any row whose company and role (ignoring case) match an application you already have.

## Keyboard shortcuts

| Key | Action |
| --- | --- |
| `N` | New application |
| `/` | Search |
| `1` `2` `3` | Board / List / Stats |
| `↑↓←→` or `h j k l` | Move between cards |
| `Enter` | Open details |
| `]` / `[` | Move the selected card to the next / previous stage |
| `X` | Close out as rejected, withdrawn or ghosted (then `R` / `W` / `G`) |
| `F` | Remind me in 3 days |
| `T` | Switch light / dark mode |
| `Ctrl+S` | Save (in the details panel) |
| `Esc` | Close the panel or dialog |

## Gmail sync

The app reads your mail over IMAP using a Google **app password**. Mail is opened read-only and nothing gets marked as read.

1. Turn on 2-Step Verification for your Google account, if it isn't on already.
2. Create an app password at **myaccount.google.com/apppasswords**. Name it something like "Job Tracker" and copy the 16 characters.
3. Add both to your settings file. That's `~/.config/jobtracker/env` on Linux and `%APPDATA%\jobtracker\env` on Windows once you've run `jobtracker install`, or `.env` in the project folder before that:
   ```
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
   ```
4. Run `jobtracker restart`. A **Sync Gmail** button appears (shortcut `G`). You can also run `jobtracker sync-gmail` from a terminal.

What a sync does:

| Email | Result |
| --- | --- |
| Application confirmation for something you don't track yet | New card in **Applied**, dated the day of the email |
| Assessment invite, interview request, rejection or offer for something you track | A suggestion in the **From Gmail** panel: Accept, Dismiss, or open the email |
| "Application viewed" (LinkedIn) or "assessment completed" | A note on that application's timeline |
| Harper (matchharper.com) job digest | One **Wishlist** card per recommended role, with source "Harper", the employer or Harper link, and Harper's summary in the notes. Skips roles you already track |
| Anything else (newsletters, job alerts, your own sent mail) | Ignored |

Each email is processed once; the app keeps a record of what it has already handled. The first sync looks back 30 days, unless you set `GMAIL_SYNC_SINCE=2026-08-01` or run `jobtracker sync-gmail --since 2026-08-01`. Later syncs pick up from the last one. With [AI help](#ai-help-optional) turned on, Claude or ChatGPT names the company when the built-in rules can't tell, as with emails from job boards or applicant-tracking systems.

To turn it off, remove the two lines from the settings file and run `jobtracker restart`. To revoke access completely, delete the app password in your Google account.

## AI help (optional)

Two features use an AI model. Everything else works without one.

- **Fill from posting:** fills in a new application from a job posting you paste in.
- **Gmail fallback:** names the company in emails that the built-in rules can't place.

You can use **Claude** or **ChatGPT**. Both need an API key, which is billed per use, separately from a claude.ai or ChatGPT subscription.

| | Claude | ChatGPT |
| --- | --- | --- |
| Get a key | console.anthropic.com | platform.openai.com |
| Install (from the project folder) | `uv tool install '.[claude]' --reinstall` | `uv tool install '.[openai]' --reinstall` |
| Setting | `ANTHROPIC_API_KEY=...` | `OPENAI_API_KEY=...` |
| Default model (change with) | `claude-haiku-5-5` (`JOBTRACKER_CLAUDE_MODEL`) | `gpt-6-luna` (`JOBTRACKER_OPENAI_MODEL`) |

Add the key to your settings file and run `jobtracker restart`. A **Fill from posting** button then appears in the top bar. To keep both installed, use `'.[claude,openai]'`. With both keys set, Claude is used; add `JOBTRACKER_AI=openai` to use ChatGPT instead. To turn it off, comment out the key and restart.

## Put it on GitHub

```fish
cd ~/Projects/job-tracker
git init -b main
git add .
git status                     # .env must NOT be listed (it holds your Gmail app password)
git commit -m "Job Tracker: FastAPI + PostgreSQL application tracker"
gh repo create job-tracker --public --source=. --push
```

`gh` is the GitHub CLI (`sudo pacman -S github-cli`, then `gh auth login` once). Without it, create an empty repo named `job-tracker` on github.com and run `git remote add origin git@github.com:EMoon-03/job-tracker.git && git push -u origin main`.

## Live demo (Render + Neon, free)

The public demo runs with `JOBTRACKER_DEMO=1`:

- It loads sample data from invented companies on startup and resets it every hour.
- Gmail sync is simulated (two sample suggestions), and "Fill from a posting" is off, so no email or API keys are involved.
- Visitors can try everything, within limits: at most 150 applications and small request bodies.

Your own applications never go near it.

1. **Database (Neon).** Sign up at neon.com, create a project, and copy the connection string. Turn **Connection pooling** off first so you get the direct connection; the app runs its own pool and uses advisory locks. It looks like `postgresql://…@ep-….neon.tech/neondb?sslmode=require`.
2. **Web service (Render).** Sign up at render.com with GitHub, then choose **New → Blueprint** and pick the `job-tracker` repo. Render reads `render.yaml`, creates a free web service, and asks for `DATABASE_URL`: paste the Neon string.
3. Wait for the first deploy, then open `https://job-tracker-demo.onrender.com` (or whatever name Render gave it) and update the link at the top of this README.

Every push to `main` redeploys. Free Render services sleep after 15 minutes without traffic and take about a minute to wake. Neon's free database doesn't expire. Render's free Postgres does, which is why it isn't used here.

## Host your own tracker (private)

For your real data, the simplest option is to keep running it locally. If you want it reachable from your phone too, deploy a second Render service the same way, but:

- leave `JOBTRACKER_DEMO` unset;
- give it its own Neon database;
- set `JOBTRACKER_PASSWORD` to a long random password.

The app then asks for that password, through the browser's sign-in prompt over HTTPS. Any username works. To move your data across, use `uv run jobtracker backup` locally, then `psql "<neon url>" < jobtracker-YYYY-MM-DD.sql`. Gmail sync works there too if you add `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD`.

## Commands

After `uv tool install .` the command is just `jobtracker`. From a checkout without installing it, prefix each command with `uv run`.

| Command | What it does |
| --- | --- |
| `jobtracker install` / `uninstall` | Run in the background, start on login, add a launcher entry; or undo that |
| `jobtracker restart` | Restart the background app after editing settings or updating |
| `jobtracker serve [--open] [--port 8765]` | Run the app in this terminal (`--reload` for development) |
| `jobtracker migrate` | Create or upgrade the tables |
| `jobtracker backup [-o file.sql]` | `pg_dump` the database to a dated `.sql` file (on Windows it finds `pg_dump` in the PostgreSQL install folder) |
| `jobtracker sync-gmail [--since YYYY-MM-DD]` | Pull new application emails from Gmail (see above) |
| `jobtracker import-json file.json` | Import applications, timelines included, from a JSON file. Works while the app is running. Skips company + role pairs you already have |

To restore a backup into a fresh database: `createdb jobtracker && psql jobtracker < jobtracker-2026-11-17.sql`.

If the app doesn't come up after `jobtracker install`, check its log: `journalctl --user -u jobtracker -e` on Linux, `%LOCALAPPDATA%\jobtracker\jobtracker.log` on Windows.

## Schema

```
applications            one row per application (company, role, stage, dates, source, contact, notes, ...)
application_events      timeline: stage changes and notes, FK → applications ON DELETE CASCADE
application_overview    view: applications + last_activity, sent, heard_back, interviewed, days_to_response
gmail_messages          every email the sync has handled, and what it did with it
gmail_suggestions       stage changes waiting for Accept / Dismiss
schema_migrations       which files in src/jobtracker/migrations have run
```

`stage` is constrained to `wishlist, applied, assessment, interview, offer, rejected, withdrawn, ghosted`. `updated_at` is maintained by a trigger. To change the schema, add the next numbered file (say `004_something.sql`) to `src/jobtracker/migrations/` and run `jobtracker migrate`.

## API

| Method | Path | |
| --- | --- | --- |
| GET | `/api/applications` | All applications, with their timelines |
| GET | `/api/applications/{id}` | One application |
| PUT | `/api/applications/{id}` | Create or replace (UUID chosen by the client) |
| DELETE | `/api/applications/{id}` | Delete, along with its timeline |
| POST | `/api/applications/bulk` | Import many rows in one transaction, skipping duplicates |
| POST | `/api/extract` | Posting text → fields with Claude or ChatGPT (503 without an AI key) |
| GET | `/api/gmail/status`, `/api/gmail/suggestions` | Sync status and pending suggestions |
| POST | `/api/gmail/sync` | Run a Gmail sync now |
| POST | `/api/gmail/suggestions/{id}/accept` or `/dismiss` | Resolve a suggestion |
| GET | `/api/health`, `/api/config` | Liveness check and feature flags |

Interactive docs are at `http://localhost:8765/docs`.

## Development

```fish
createdb jobtracker_test
uv run pytest
```

The tests run against a real Postgres database (`TEST_DATABASE_URL`, default `postgresql:///jobtracker_test`). They wipe that database's `public` schema, so never point it at your real database.

On Windows, create the test database and point the tests at it first: `$env:TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/jobtracker_test"`. The Windows install code is covered by tests that run on any system, using a stand-in for the registry.

```
src/jobtracker/
  main.py         FastAPI app and routes
  db.py           connection pool, migration runner, SQL
  models.py       Pydantic request models (validation)
  extract.py      optional AI (Claude or ChatGPT): posting parser and email fallback
  gmail_sync.py   IMAP fetch, matching, suggestions
  classify.py     rules that read a job email: what happened, which company, which role
  harper.py       turns Harper job digests into wishlist cards
  demo.py         sample data and hourly reset for the public demo
  cli.py          `jobtracker` command
  install.py      `jobtracker install`: login service, launcher entry, settings file
  migrations/     numbered .sql files
  static/         the web UI (single HTML file, no build step) and its self-hosted font
sql/queries.sql   handy reporting queries for psql
render.yaml       Render blueprint for the demo
docs/screenshots/ README images (taken from the demo with headless Chrome)
```

The font (Figtree) is under the SIL Open Font License; see `src/jobtracker/static/fonts/LICENSE.txt`.
