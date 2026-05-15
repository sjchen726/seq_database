# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Django 5.1 web application for managing RNA/DNA sequence data. It handles sequence registration, modification tracking, delivery records, BLAST searches, user access control, cross-project sample sharing, and bioassay experimental data. Django project name is `bms`; the single app is `app01`.

## Commands

```bash
# Activate virtualenv (Python 3.10)
source venv/bin/activate

# Run development server
python manage.py runserver

# Migrations
python manage.py makemigrations
python manage.py migrate

# Django shell
python manage.py shell

# Lint
ruff check .
ruff check --fix .
```

**Database:** MySQL (`bms` database, `127.0.0.1:3306`, user `root`). Credentials are in `bms/settings.py` (hardcoded; see `.env.example` for reference). No test suite exists.

## Architecture

- All routing is in `bms/urls.py` — no per-app `urls.py` files.
- All views are function-based in `app01/views.py` (one large ~3500-line file).
- Templates live in the top-level `templates/` directory.
- `USE_TZ = False` — all datetimes are naive (Asia/Shanghai local time).
- `requirements.txt` contains Windows-platform wheels; on macOS/Linux install packages individually or use a cleaned requirements file.

## Key Models (`app01/models.py`)

| Model | Purpose |
|---|---|
| `Sequence` | Core entity; `rm_code` (6-digit) is the PK; `seq_type` is `AS`, `SS`, or `duplex` |
| `DuplexRelationship` | Links an AS strand + SS strand + duplex `Sequence` together |
| `SeqInfo` | Target/project metadata (position, transcript, project) for a `Sequence` |
| `Delivery` | Synthesized form of a `Sequence`; holds `linker_seq`, `modify_seq`, delivery 5'/3', MW, and `duplex_id` |
| `DeliveryModule` | Lookup: delivery modification keywords → `type_code` (used for coloring) |
| `SeqModule` | Lookup: sequence modification tokens (e.g. `VP25A`, `GU02`, `T(MOE)`) for parsing `modify_seq` |
| `LmsUser` | Extends `AbstractUser`; `user_type` controls capabilities; `permissions_project` (comma-separated) restricts project access |
| `DeliveryProject` | Join table for cross-project sharing — links a `Delivery` to additional project codes beyond its owner |
| `Experiment` | Bioassay record (in vitro/in vivo, assay type, dose-response/single-point/PK) linked to a `duplex_id` |
| `DataPoint` | Individual readout values (mRNA%, protein%, concentration) belonging to an `Experiment` |
| `ExperimentAttachment` | Files or external URLs linked to an `Experiment` |

## User Roles

`guest` < `delivery` < `modify` < `project` < `data_admin` < `admin` < `superadmin`

Django `is_superuser` bypasses all role checks. `permissions_project` is a comma-separated string of project codes that restricts what sequences/deliveries a user sees. Key permission helpers in `views.py`:
- `get_permitted_delivery_qs()` — filters `Delivery` queryset by user's projects
- `user_can_edit_delivery()` — role + project ownership check
- `_user_can_access_duplex()` — access control for duplex_id-based views

## Sequence Coloring Logic

This is the core visual feature. All coloring resolves `type_code` → hex color via `get_color_map()`, then applies it token-by-token.

- **`get_delivery_colored()`** — tokenizes `linker_seq` using longest-match regex against `DeliveryModule.keyword`; optionally reverses token order for AS strands.
- **`get_modify_seq_colored()`** — two-level regex: `SeqModule` tokens first, then `DeliveryModule` keywords; handles `modify_seq` strings.

Both functions return a list of `(token, color_hex)` tuples rendered in templates.

## Bulk Operations Pattern

CSV uploads drive most data entry. The pattern across `register_seq`, `upload_delivery_info`:
1. `parse_uploaded_csv()` reads the file into a list of dicts
2. `group_sequences()` / similar grouping by key field (SS sequence, duplex_id)
3. Duplicate detection against existing DB records
4. `save_deliveries()` or equivalent wraps inserts in a transaction with collision detection
5. `assign_duplex_ids()` auto-generates 6-digit duplex IDs for new AS-SS pairs

## URL Structure (selected routes)

- Auth: `/`, `/login/`, `/signup/`
- Sequences: `/seq_list/`, `/reg_seq_list/`, `/register_seq/`, `/edit_seq/<rm_code>/`, `/cor_seq/`
- Delivery: `/seq_delivery/`, `/clone_delivery/`, `/confirm_share/`, `/download_selected/`
- Lookup tables: `/module_list/`, `/edit_module/`, `/seqmodule_list/`, `/edit_seqmodule/`, `/upload_modules/`, `/upload_seqmodules/`
- Search: `/search/`, `/blast_seq/`, `/multi_blast/`
- Experiments: `/experiment/add/`, `/experiment/<duplex_id>/`, `/upload_experiment/`, `/download_experiment_template/`

## Design Plans

Ongoing feature specs live in `docs/superpowers/plans/` and `docs/superpowers/specs/`. Check there before implementing changes to understand intent and constraints.

## Logging

File handler writes to `edit_book.log` in the project root. Logger name: `edit_book_log`.
