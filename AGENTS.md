# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**SeqDB** — a Django 5.1 web application for managing RNA/DNA sequences in pharmaceutical R&D (核酸药物研发). Handles sequence registration, modification tracking, delivery records (5'/3' ligands), BLAST searches, experiment data, and project-level access control. Django project name: `bms`; single app: `app01`.

## Commands

```bash
# Activate virtualenv (Python 3.10)
source venv/bin/activate

# Run development server
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Django shell
python manage.py shell

# Lint
ruff check .
ruff check --fix .
```

Database: MySQL (`bms`, `127.0.0.1:3306`, user `root`). See `bms/settings.py` for credentials.

## Architecture

**Single-file conventions:** All URL routing is in `bms/urls.py` (no per-app `urls.py`). All ~60 views are function-based in `app01/views.py` (~3900 lines). Templates are in the top-level `templates/` directory.

**Signal handler:** `app01/apps.py` registers a `post_save` signal on `Delivery` that auto-creates `DeliveryProject` entries.

**Logging:** File handler writes to `edit_book.log` (project root). Logger name: `edit_book_log`.

### Models (`app01/models.py`)

| Model | Role |
|-------|------|
| `Sequence` | Core entity; `rm_code` (6-digit PK), `seq` (AUGC bases), `seq_type` (AS/SS/duplex) |
| `DuplexRelationship` | Links AS strand + SS strand + duplex `Sequence` together |
| `SeqInfo` | Target/project metadata attached to a `Sequence` |
| `Delivery` | Synthesized form: `modify_seq`, `linker_seq`, `delivery5`/`delivery3`, MW, project |
| `DeliveryProject` | Denormalized link: Delivery → `project_code` (managed by signal) |
| `DeliveryModule` | Lookup: keyword → `type_code` for coloring/grouping delivery sequences |
| `SeqModule` | Lookup: modification token (e.g. `VP25A`, `T(MOE)`) → `base_char`, `linker_connector` |
| `Experiment` | Experimental record: `duplex_id`, `exp_type` (in_vitro/in_vivo), `assay_type`, batch |
| `DataPoint` | Measurement: concentration/dose, timepoint, `readout_type`, value, replicate |
| `ExperimentAttachment` | Files or URLs attached to an `Experiment` |
| `LmsUser` | Extends `AbstractUser`; `user_type` + `permissions_project` (comma-separated codes) |

### User Roles

`guest` → `delivery` → `modify` → `project` → `data_admin` → `admin` → `superadmin`. Superusers bypass all checks. Project-level filtering: `get_permitted_delivery_qs(user)` and `user_can_edit_delivery(user, delivery)` in `views.py`.

### Sequence Coloring (key domain logic in `views.py`)

- **`get_delivery_colored()`** — tokenizes `linker_seq` by longest-match regex against `DeliveryModule.keyword`, assigns color per `type_code`, reverses token order for AS strands.
- **`get_modify_seq_colored()`** — same for `modify_seq`, using `SeqModule` tokens combined with `DeliveryModule` keywords in a two-level regex; handles dual-segment sequences with embedded `SEP` tokens via `split_tokens_at_sep()`.
- **`build_duplex_groups()`** — groups `Delivery` records by `duplex_id`, aligns AS/SS colored tokens for display in `_seq_group_row.html`.
- **`get_color_map()`** — assigns a deterministic color (palette of 30) to each unique `type_code`.

### CSV Upload Pipeline (`upload_delivery_info` view)

1. `parse_uploaded_csv()` → DataFrame
2. `group_sequences()` → AS↔SS pair detection
3. `check_duplicates()` → match on `(delivery5, delivery3, linker_seq)`
4. `assign_duplex_ids()` → generate `BP000001`-style IDs
5. `normalize_tmp_seq_with_combo()` + `add_o_to_all_rules_safe()` → normalize `modify_seq`
6. `save_deliveries()` → bulk insert to `Delivery`

### Static Assets

- `static/css/`: `design-system.css` (layout/sidebar/topbar), `styles.css` (token colors, segment alignment), `forms.css`, `buttons.css`
- `static/js/`: `search.js` (multi-term search UI), `tables.js` (sorting/selection), `forms.js`, `drag.js`, `add_experiment.js`, etc.
- `static/vendors/`: bundled third-party libs (CKEditor, TinyMCE, Flot, Bootstrap)

## Important Notes

- **`USE_TZ = False`** — all datetimes are naive Asia/Shanghai local time; no UTC conversion anywhere.
- **`requirements.txt` has Windows wheels** — on macOS/Linux, install packages manually or use a cleaned requirements file.
- **No test suite** — `app01/tests.py` is empty; no pytest setup.
- **Pending migration** — `0024_add_indexes_and_expand_fields.py` may not yet be applied to your local DB.
- **Dual-segment sequences** — sequences containing `SEP` tokens represent two chemically linked segments; coloring and alignment code must handle these via `split_tokens_at_sep()`.
