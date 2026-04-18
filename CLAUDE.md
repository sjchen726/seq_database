# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Django 5.1 web application for managing RNA/DNA sequence data ("seq_database"). It handles sequence registration, modification tracking, delivery records, BLAST searches, and user access control. The project name in Django is `bms`; the single app is `app01`.

## Commands

```bash
# Activate virtualenv (Python 3.10)
source venv/bin/activate

# Run development server
python manage.py runserver

# Run migrations
python manage.py makemigrations
python manage.py migrate

# Open Django shell
python manage.py shell

# Lint (ruff is in requirements)
ruff check .
ruff check --fix .
```

Database: MySQL (`bms` database, host `127.0.0.1:3306`, user `root`). Requires a running MySQL instance. See `bms/settings.py` for credentials.

## Architecture

All routing is in `bms/urls.py` — no per-app `urls.py`. All views are function-based views in `app01/views.py` (single large file). Templates live in the top-level `templates/` directory.

### Key Models (`app01/models.py`)

- **`Sequence`** — core entity; `rm_code` (6-digit, PK) identifies each bare RNA/DNA sequence; `seq_type` is `AS`, `SS`, or `duplex`.
- **`DuplexRelationship`** — links an AS strand, SS strand, and duplex sequence together.
- **`SeqInfo`** — target/project metadata attached to a `Sequence`.
- **`Delivery`** — a synthesized/delivered form of a `Sequence` with modification codes, linker sequences, delivery attachments (5'/3'), and molecular weight.
- **`DeliveryModule`** — lookup table of delivery modification keywords mapped to `type_code` for coloring/grouping.
- **`SeqModule`** — lookup table of sequence modification tokens (e.g. `VP25A`, `GU02`, `T(MOE)`) used to parse `modify_seq` strings.
- **`LmsUser`** — extends `AbstractUser`; `user_type` controls what each user can see/do; `permissions_project` (comma-separated) restricts which project numbers a user can access.

### User roles (`user_type`)
`guest` → `delivery` → `modify` → `project` → `data_admin` → `admin` → `superadmin`. Superusers bypass all role checks. Project-level filtering uses `permissions_project`.

### Sequence coloring logic (in `views.py`)
- `get_delivery_colored()` — tokenizes a `linker_seq` string by matching against `DeliveryModule` keywords (longest-match regex), assigns a color per `type_code`, and optionally reverses token order for AS strands.
- `get_modify_seq_colored()` — same idea for `modify_seq`, but uses `SeqModule` tokens combined with `DeliveryModule` keywords in a two-level regex.

### Static files
Bundled vendor libs live in `static/vendors/` (CKEditor, TinyMCE, Flot, Bootstrap form helpers). Project-specific JS/CSS is in `static/`.

### Logging
File handler writes to `edit_book.log` in the project root. Logger name is `edit_book_log`.

## Important notes

- `USE_TZ = False` — all datetimes are naive (Asia/Shanghai local time, no timezone conversion).
- `requirements.txt` contains Windows-platform wheels; on macOS/Linux install packages manually or use a cleaned requirements file.
- Migrations directory is `app01/migrations/`. A pending unapplied migration `0024_add_indexes_and_expand_fields.py` exists.
