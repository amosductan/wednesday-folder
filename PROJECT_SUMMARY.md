# Ductan Kids — School Updates Website

## Overview
Automated website that tracks school newsletters for both Ductan children. Emails are fetched from Gmail, processed, and deployed to GitHub Pages on a recurring schedule — fully hands-off.

- **Website**: https://amosductan.github.io/wednesday-folder/
- **GitHub**: amosductan/wednesday-folder (public, GitHub Pages from /docs)

## Children
- **Maya Ductan** — Kindergarten, St. Cloud Elementary School (Jaguars), West Orange School District
- **Isaac Ductan** — PreK Orange, South Orange Country Day School (SOCDS)

## Pipeline (Fully Automated)
Task Scheduler runs `weekly_pipeline.py` every **Wednesday + Friday at 4 PM ET**.

```
1. fetch_email.py      → Download Maya's Wednesday Folder PDF (SchoolMessenger SDD)
2. fetch_socds.py      → Download Isaac's SOCDS newsletter (inline HTML)
3. process_pdf.py      → Extract text from new PDFs → data/YYYY-MM-DD.json
4. auto_curate.py      → Parse PDF text into structured events → events.json
5. extract_socds_images.py → Download newsletter images
6. upload_to_drive.py  → Upload images to Google Drive
7. build_site.py       → Inject data into template → docs/index.html
8. git commit + push   → Deploy via GitHub Pages
9. notify.py           → Telegram alert (success summary or failure)
```

Each step has retry logic (critical steps: 3 retries with 60s delay). Failures trigger a loud Telegram notification via `@SwingLowTraderBot`.

## Data Sources
- **Maya**: Weekly "Wednesday Folder" email from `noreply@westorangeschools.org` with PDF via SchoolMessenger Secure Document Delivery
- **Isaac**: Weekly "SOCDS Update" email from `learn@socds.com` with inline HTML newsletter

## Current Stats (Mar 13, 2026)
- Maya: **19 weeks** archived (Sep 2025 – Mar 2026), **94 events**
- Isaac: **21 weeks** archived (Week #1–26), **795 images** backed up to Google Drive

## Key Files
| File | Purpose |
|------|---------|
| `weekly_pipeline.py` | Master orchestrator (retry, logging, alerts) |
| `weekly_fetch.bat` | Task Scheduler entry point |
| `fetch_email.py` | Maya Gmail fetcher (SchoolMessenger SDD) |
| `fetch_socds.py` | Isaac Gmail fetcher (inline HTML) |
| `process_pdf.py` | PDF text extraction → raw JSON |
| `auto_curate.py` | Heuristic event extraction from PDF text |
| `build_site.py` | Template injection → docs/index.html |
| `parse_socds.py` | Isaac newsletter parser (sections: announcements, art, gardening, upcoming, logistics) |
| `extract_socds_images.py` | Newsletter image downloader |
| `upload_to_drive.py` | Google Drive image uploader |
| `notify.py` | Telegram notifications |
| `build_all_events.py` | Historical event dataset (18 weeks hardcoded, superseded by auto_curate.py) |
| `task_schedule.xml` | Task Scheduler XML config (disaster recovery) |
| `index.html` | Website template (MAYA_DATA_PLACEHOLDER + ISAAC_DATA_PLACEHOLDER) |

## Data Files
| Path | Contents |
|------|----------|
| `data/events.json` | Maya's structured events (website reads this) |
| `data/YYYY-MM-DD.json` | Maya's raw extracted PDF text |
| `data/fetch_state.json` | Email fetch tracking (last date, processed IDs) |
| `socds/data/week_NN.json` | Isaac's raw newsletter text + links |
| `socds/socds_events.json` | Isaac's structured parsed data |
| `socds/emails/` | Isaac's raw HTML emails (gitignored) |
| `socds/images/` | Isaac's newsletter images by week (gitignored) |
| `pdfs/` | Maya's archived PDFs (gitignored) |
| `docs/index.html` | Built website (deployed via GitHub Pages) |
| `backups/` | Last 10 site backups (timestamped) |
| `logs/weekly_fetch.log` | Pipeline execution log |
| `logs/errors.log` | Failed step records |

## Auto-Curation (auto_curate.py)
Extracts structured events from raw PDF text without manual intervention:
- **20+ known event patterns**: PTA Meeting, Ice Skating, Career Week, Trunk or Treat, Book Fair, etc.
- **OCR cleanup**: Fixes spaced-out text artifacts from PDF extraction ("FAM ILY" → "Family Ice Skating Night")
- **Recurring item templates**: Benevity, PTA Membership, Diversity Council — auto-added when detected
- **Category classification**: fundraiser, meeting, deadline, school-spirit, community-event, volunteer, membership, school-event
- **Deduplication**: Merges by folder_date, sorted newest-first

## Authentication
- **Gmail**: OAuth2 read-only, `credentials/gmail_credentials.json` + `credentials/gmail_token.json`
- **Google Drive**: OAuth2 drive.file scope, `credentials/drive_token.json`
- **Telegram**: `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` env vars (shared with SwingLowPro)

## Website Features
- Two-tab layout: Maya (St. Cloud) and Isaac (SOCDS)
- Maya: Event cards with category badges, date display, clickable links
- Isaac: Structured sections with colored headers, announcement cards, collapsible logistics
- Light/dark mode, mobile responsive (768px + 480px breakpoints)

## Task Scheduler
- **Task**: `DuctanKids_SchoolFetch`
- **Triggers**: Wednesday 4 PM ET, Friday 4 PM ET
- **Settings**: StartWhenAvailable (runs on wake if missed), network-required, 30-min timeout
- **Config backup**: `task_schedule.xml`
