# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

```bash
# Run development server
cd /Users/gutou/Projects/seq_web/seq_database
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Lint with ruff (included in requirements.txt)
ruff check .
ruff format .

# Django shell
python manage.py shell

# Run tests
python manage.py test
```

The virtual environment is at `venv/`. Settings module: `bms.settings`.

## Architecture Overview

Single-app Django project: `app01` handles all models, views, and logic. URLs in `bms/urls.py` map directly to views in `app01/views.py` (~2,900 lines, no class-based views — all function-based).

```
seq_database/
├── bms/            # Project config (settings.py, urls.py)
├── app01/          # Main app: models.py, views.py, migrations/
├── templates/      # 31 HTML templates (all at root level, no subdirectories)
└── static/         # css/, js/, bootstrap/, vendors/
```

## Core Data Model & ID Chain

Understanding the ID relationships is critical — naming is intentionally confusing in parts:

```
Sequence.rm_code       → 6-digit zero-padded string PK (e.g. "001234")
  └── Delivery.sequence (FK → Sequence.rm_code, related_name='deliveries')
        ├── Delivery.delivery_id  = "RM_001234.1"   ← visible ID with suffix
        └── Delivery.duplex_id    = "BP000001"       ← links AS+SS pair

DuplexRelationship: as_seq (FK) + ss_seq (FK) + duplex_seq (FK) → all point to Sequence
```

**Critical naming trap in `views.py`:** `build_duplex_groups()` stores `Delivery.id` (auto-increment integer) in a dict keyed as `delivery_id_to_seq_id`, then passes it as the `rm_code` parameter to `build_sequence_data()`. Templates access this as `group.items.0.rm_code` — which is actually `Delivery.id`, not `Sequence.rm_code`. This is intentional for backward compatibility. Edit/BLAST URL links like `/edit_seq/?id={{ rm_code }}` and `/blast_seq/?delivery_id={{ rm_code }}` use this `Delivery.id` value and their views query by `Delivery.id`. Do NOT rename these without tracing all template usages.

## Key Models

- **Sequence**: `rm_code` (PK), `seq`, `seq_type` (duplex/AS/SS)
- **Delivery**: FK to Sequence, `delivery_id`, `duplex_id`, `modify_seq`, `delivery5`, `delivery3`, `Strand_MWs`, `project`, `Target`, `seq_type`
- **SeqInfo**: FK to Sequence, stores target/position/project/remark metadata. Has a redundant `seq` field (duplicates `sequence.seq`)
- **DeliveryModule**: `keyword` (unique), `type_code`, `Strand_MWs` — defines sequence modification components; used for colorizing sequences and in save_deliveries regex substitutions
- **LmsUser** (AUTH_USER_MODEL): extends AbstractUser, `user_type` controls access (superadmin/admin/data_admin/project/delivery/modify/guest), `permissions_project` is comma-separated project codes
- **Author**: legacy model largely superseded by LmsUser, retained for backward compatibility

## Template & CSS Conventions

Templates use **Bootstrap v3** (not v4). Do not use v4 utility classes like `d-flex`, `me-2`, `mb-3`, `justify-content-start` — use Bootstrap v3 patterns (`col-md-*`, `glyphicon`, `btn-xs/sm`) or custom CSS.

**Design system CSS** is appended at the end of `static/css/styles.css` (around line 1367+) as override blocks. The color palette: `#1a6496` (primary blue), `#f0f4f8` (table header bg), `#1a2d3d` (dark text).

**Standard page structure** for main views:
- `.header` div with logo + personal info dropdown
- `.page-content` with Bootstrap grid: `col-md-2` sidebar + `col-md-10` main content
- `.seq-toolbar` above tables with action buttons
- DataTable on `#example` with `#select-all` + `.row-checkbox` for bulk selection
- Toast notifications via `#msg-toast-container` + `.msg-toast` (not `alert()`)

**Recurring broken HTML pattern** (found in some older templates): `<div>` directly inside `<ul class="nav">`. Fix by moving controls to `.seq-toolbar` above the table.

## Views Architecture

`views.py` has three major layers:

1. **Data helpers** (lines ~1–400): `get_color_map()`, `get_delivery_colored()`, `get_modify_seq_colored()`, `build_combo_re()`, `normalize_tmp_seq_with_combo()`

2. **Sequence processing pipeline** (lines ~1400–2100): `parse_uploaded_csv()` → `check_duplicates()` → `assign_duplex_ids()` → `save_deliveries()` → `build_duplex_groups()` → `build_sequence_data()`
   - `save_deliveries()` contains 60+ hardcoded `re.sub()` rules mapping module keywords to base characters (A/U/G/C). These should match entries in the `DeliveryModule` table but are hardcoded.

3. **View functions** (~30 views): all function-based, most require `@login_required`

Permission filtering: `get_permitted_delivery_qs(user)` — call this when filtering Delivery querysets for non-admin users.

## Database

MySQL, database name `bms`. PyMySQL driver (configured in `bms/__init__.py`). 23+ migrations in `app01/migrations/`.

Custom datetime display uses `Asia/Shanghai` timezone.
