# SeqDB Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace all frontend templates with a unified sidebar-layout design using DM Sans + DM Mono fonts and a sky-blue→indigo gradient accent system, preserving all existing Django template logic and JS hooks.

**Architecture:** Create a new `base.html` Django template that all "app" pages extend, containing the sidebar and topbar shell. Create `design-system.css` as the single source of styling truth. Convert each of the ~20 app templates to `{% extends 'base.html' %}` and strip their boilerplate. Login/register/change_password get standalone redesign (no sidebar).

**Tech Stack:** Django template inheritance (`{% extends %}`/`{% block %}`), Bootstrap 5 (retained), DM Sans + DM Mono (Google Fonts), vanilla CSS (no build step), jQuery (existing, retained).

---

## File Map

| Action | File | Purpose |
|---|---|---|
| **Create** | `static/css/design-system.css` | Full design system CSS; replaces styles.css for app pages |
| **Create** | `templates/base.html` | Shell template: sidebar + topbar; all app pages extend this |
| **Rewrite** | `templates/seq_list.html` | Sequence list — most complex; establishes table patterns |
| **Rewrite** | `templates/seq_edit.html` | Sequence edit form |
| **Rewrite** | `templates/register_seq.html` | CSV registration upload |
| **Rewrite** | `templates/multi_blast.html` | Multi-BLAST query input |
| **Rewrite** | `templates/multi_blast_results.html` | Multi-BLAST results |
| **Rewrite** | `templates/blast_results.html` | Single BLAST results |
| **Rewrite** | `templates/module_list.html` | Delivery module list |
| **Rewrite** | `templates/edit_module.html` | Edit delivery module |
| **Rewrite** | `templates/upload_modules.html` | Upload delivery modules CSV |
| **Rewrite** | `templates/seqmodule_list.html` | SeqModule list |
| **Rewrite** | `templates/edit_seqmodule.html` | Edit seqmodule |
| **Rewrite** | `templates/upload_seqmodules.html` | Upload seqmodules CSV |
| **Rewrite** | `templates/auth_list.html` | User management list |
| **Rewrite** | `templates/auth_edit.html` | Edit user |
| **Rewrite** | `templates/author_add.html` | Add user |
| **Rewrite** | `templates/reg_seq_list.html` | Registered sequence list |
| **Rewrite** | `templates/reg_seq_edit.html` | Edit registered sequence |
| **Rewrite** | `templates/upload_delivery_info.html` | Upload delivery info CSV |
| **Rewrite** | `templates/search_results.html` | Advanced search results |
| **Rewrite** | `templates/cor_seq.html` | Sequence correction page |
| **Rewrite** | `templates/login.html` | Login (standalone, no sidebar) |
| **Rewrite** | `templates/register.html` | Register (standalone, no sidebar) |
| **Rewrite** | `templates/change_password.html` | Change password (standalone) |
| **No change** | `templates/char_block_AS.html` | Partial: colored seq blocks (AS) |
| **No change** | `templates/char_block_SS.html` | Partial: colored seq blocks (SS) |
| **No change** | `templates/clone_modal.html` | Partial: clone modal (style update in CSS) |
| **No change** | `templates/blast_seq_blocks.html` | Partial: BLAST seq blocks |

---

## Task 1: Create design-system.css

**Files:**
- Create: `static/css/design-system.css`

- [ ] **Step 1: Create the CSS file**

```css
/* ================================================================
   SeqDB Design System  —  design-system.css
   Import after Bootstrap 5. Overrides Bootstrap where needed.
   ================================================================ */

/* Fonts */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600;9..40,700&family=DM+Mono:wght@400;500&display=swap');

/* ── Reset / Base ── */
*, *::before, *::after { box-sizing: border-box; }
body {
  font-family: 'DM Sans', sans-serif;
  background: #dde3ed;
  color: #1a2035;
  font-size: 13px;
  margin: 0;
}

/* ── App Shell ── */
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── Sidebar ── */
.ds-sidebar {
  width: 210px;
  flex-shrink: 0;
  background: #fff;
  display: flex;
  flex-direction: column;
  box-shadow: 2px 0 16px rgba(15,23,42,0.06);
  position: relative;
  z-index: 20;
  overflow-y: auto;
}

.ds-sidebar-logo {
  height: 56px;
  padding: 0 18px;
  display: flex;
  align-items: center;
  gap: 11px;
  flex-shrink: 0;
}

.ds-logo-mark {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, #38bdf8, #6366f1);
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 800;
  font-size: 14px;
  box-shadow: 0 3px 10px rgba(99,102,241,0.32);
  flex-shrink: 0;
}

.ds-logo-text { font-size: 14.5px; font-weight: 700; color: #0f172a; letter-spacing: -0.3px; }
.ds-logo-tagline { font-size: 9.5px; color: #94a3b8; }

.ds-nav-section {
  padding: 14px 16px 4px;
  font-size: 9px;
  font-weight: 700;
  color: #c1cad6;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.ds-nav-divider { height: 1px; background: #f1f5f9; margin: 6px 16px; }

.ds-nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 1px 8px;
  padding: 7.5px 10px 7.5px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 400;
  color: #64748b;
  cursor: pointer;
  position: relative;
  text-decoration: none;
  transition: background 0.12s, color 0.12s;
}

.ds-nav-item:hover { background: #f8fafc; color: #334155; text-decoration: none; }

.ds-nav-item.active { background: #eef2ff; color: #4338ca; font-weight: 600; }

.ds-nav-item.active::before {
  content: '';
  position: absolute;
  left: -8px; top: 20%; bottom: 20%;
  width: 3px;
  background: linear-gradient(180deg, #38bdf8, #6366f1);
  border-radius: 0 3px 3px 0;
}

.ds-nav-dot {
  width: 5px; height: 5px; border-radius: 50%;
  background: currentColor; opacity: 0.3; flex-shrink: 0;
}
.ds-nav-item.active .ds-nav-dot { opacity: 1; }

.ds-nav-badge {
  margin-left: auto;
  background: #ede9fe; color: #6d28d9;
  font-size: 10px; font-weight: 700;
  padding: 2px 7px; border-radius: 20px;
  font-family: 'DM Mono', monospace;
}

.ds-sidebar-footer {
  margin-top: auto;
  padding: 12px 14px;
  border-top: 1px solid #f1f5f9;
}

.ds-user-card {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 8px; border-radius: 8px; cursor: pointer;
}
.ds-user-card:hover { background: #f8fafc; }

.ds-user-avatar {
  width: 32px; height: 32px;
  background: linear-gradient(135deg, #38bdf8, #6366f1);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 13px; font-weight: 700; flex-shrink: 0;
}

.ds-user-name { font-size: 12.5px; font-weight: 600; color: #1e293b; }
.ds-user-role { font-size: 10px; color: #94a3b8; display: flex; align-items: center; gap: 4px; margin-top: 1px; }
.ds-online-dot { width: 5px; height: 5px; border-radius: 50%; background: #22c55e; flex-shrink: 0; }

/* ── Main area ── */
.ds-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Topbar ── */
.ds-topbar {
  height: 56px;
  padding: 0 20px;
  background: #fff;
  border-bottom: 1px solid #eef2f7;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.ds-topbar-title { font-size: 15px; font-weight: 700; color: #0f172a; letter-spacing: -0.2px; }

.ds-count-badge {
  font-family: 'DM Mono', monospace;
  font-size: 11px; font-weight: 500;
  color: #94a3b8; background: #f1f5f9;
  border: 1px solid #e8edf4;
  padding: 2px 8px; border-radius: 20px;
}

.ds-topbar-spacer { flex: 1; }

/* ── Buttons ── */
.ds-btn {
  display: inline-flex; align-items: center; gap: 5px;
  border-radius: 8px; font-size: 12px; font-weight: 500;
  cursor: pointer; white-space: nowrap; border: none;
  padding: 0 13px; height: 34px;
  font-family: 'DM Sans', sans-serif;
  text-decoration: none; transition: all 0.12s;
}

.ds-btn-primary {
  background: linear-gradient(135deg, #38bdf8, #6366f1);
  color: #fff;
  box-shadow: 0 2px 8px rgba(99,102,241,0.28);
}
.ds-btn-primary:hover { opacity: 0.9; color: #fff; text-decoration: none; }

.ds-btn-ghost {
  background: #fff; color: #475569;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.ds-btn-ghost:hover { border-color: #c4b5fd; color: #6366f1; text-decoration: none; }

.ds-btn-green {
  background: #16a34a; color: #fff; font-weight: 600;
  box-shadow: 0 2px 8px rgba(22,163,74,0.28);
}
.ds-btn-green:hover { background: #15803d; color: #fff; text-decoration: none; }

/* ── Search box ── */
.ds-search-wrap {
  display: flex; align-items: center; gap: 6px;
  background: #f8fafc; border: 1px solid #e2e8f0;
  border-radius: 8px; padding: 0 10px;
  height: 34px; width: 190px;
  transition: border-color 0.12s;
}
.ds-search-wrap:hover { border-color: #c4b5fd; }
.ds-search-wrap:focus-within { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.ds-search-icon { color: #94a3b8; font-size: 13px; }
.ds-search-input {
  border: none; background: transparent; outline: none;
  font-size: 11.5px; color: #334155; flex: 1;
  font-family: 'DM Sans', sans-serif;
}
.ds-search-input::placeholder { color: #b0bec8; }
.ds-search-kbd {
  background: #e8edf4; color: #64748b;
  font-size: 9px; font-weight: 700;
  padding: 1px 5px; border-radius: 4px;
  font-family: 'DM Mono', monospace;
}

/* ── Content area ── */
.ds-content {
  flex: 1; overflow: auto;
  padding: 16px 20px;
  display: flex; flex-direction: column; gap: 12px;
}

/* ── Toolbar ── */
.ds-toolbar { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }

.ds-tb-btn {
  display: flex; align-items: center; gap: 5px;
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 7px; padding: 5px 11px;
  font-size: 11.5px; font-weight: 500; color: #475569;
  cursor: pointer; font-family: 'DM Sans', sans-serif;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04); white-space: nowrap;
  transition: all 0.12s; text-decoration: none;
}
.ds-tb-btn:hover { border-color: #c4b5fd; color: #6366f1; text-decoration: none; }
.ds-tb-btn.ds-active-filter { border-color: #fdba74; background: #fff7ed; color: #c2410c; }

.ds-tb-badge {
  background: #f97316; color: #fff;
  font-size: 9px; font-weight: 700;
  padding: 1px 5px; border-radius: 20px;
}

/* ── Table card ── */
.ds-table-card {
  background: #fff; border-radius: 12px;
  border: 1px solid #e8edf4;
  box-shadow: 0 1px 4px rgba(15,23,42,0.05);
  overflow: hidden; flex: 1;
  display: flex; flex-direction: column; min-height: 0;
}

.ds-table-scroll { overflow: auto; flex: 1; }

.ds-table {
  border-collapse: collapse; width: 100%;
  min-width: 1080px; font-size: 11.5px;
}

.ds-table thead { position: sticky; top: 0; z-index: 5; }
.ds-table thead tr { background: #f8fafc; border-bottom: 1.5px solid #e8edf4; }

.ds-table th {
  padding: 10px 11px;
  font-size: 10px; font-weight: 700;
  color: #64748b; text-transform: uppercase;
  letter-spacing: 0.07em; white-space: nowrap;
  border-right: 1px solid #f0f4f8;
  cursor: pointer; user-select: none;
  transition: background 0.12s, color 0.12s;
  vertical-align: middle;
}
.ds-table th:first-child { cursor: default; width: 36px; padding: 0 11px; }
.ds-table th:last-child { border-right: none; cursor: default; }
.ds-table th:not(:first-child):not(:last-child):hover { background: #eef2ff; color: #4338ca; }
.ds-table th.sorted { color: #4338ca; background: #eef2ff; }

.ds-sort-icon { display: inline-flex; flex-direction: column; gap: 1.5px; margin-left: 4px; opacity: 0.25; vertical-align: middle; }
.ds-table th:not(:first-child):not(:last-child):hover .ds-sort-icon { opacity: 0.5; }
.ds-table th.sorted .ds-sort-icon { opacity: 1; }
.arr-up { width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent; border-bottom: 3.5px solid currentColor; }
.arr-dn { width: 0; height: 0; border-left: 3px solid transparent; border-right: 3px solid transparent; border-top: 3.5px solid currentColor; }
.ds-table th.desc .arr-up { opacity: 0.2; }

.ds-table tbody tr { border-bottom: 1px solid #f4f7fb; transition: background 0.1s; }
.ds-table tbody tr:last-child { border-bottom: none; }
.ds-table tbody tr:nth-child(even) { background: #fafbfd; }
.ds-table tbody tr:hover { background: #eef2ff !important; }
.ds-table td { padding: 9px 11px; vertical-align: middle; }

/* Table cells */
.cell-check { width: 36px; padding: 0 11px !important; }
.cell-id { font-family: 'DM Mono', monospace; font-size: 11px; font-weight: 500; color: #4338ca; }
.ds-table tbody tr:hover .cell-id { color: #6366f1; }
.cell-code { font-family: 'DM Mono', monospace; font-size: 10.5px; color: #64748b; line-height: 1.5; }
.cell-text { font-size: 12px; color: #334155; }
.cell-dim { font-size: 10.5px; color: #94a3b8; }
.cell-mono-dim { font-family: 'DM Mono', monospace; font-size: 10px; color: #94a3b8; white-space: nowrap; }

/* Sequence + ligand visual blocks */
.ds-seq-row { display: flex; gap: 1px; align-items: flex-end; flex-wrap: wrap; }
.ds-lig-row { display: flex; gap: 2px; align-items: center; flex-wrap: wrap; }
.ds-lig {
  height: 19px; padding: 0 5px; border-radius: 3px;
  font-size: 9px; font-weight: 700; color: #fff;
  font-family: 'DM Mono', monospace; white-space: nowrap;
  display: flex; align-items: center;
}

/* Action buttons */
.ds-actions { display: flex; gap: 4px; white-space: nowrap; }
.ds-act {
  padding: 3px 9px; border-radius: 5px;
  font-size: 10.5px; font-weight: 500; border: 1px solid;
  cursor: pointer; text-decoration: none; display: inline-flex; align-items: center;
  transition: all 0.1s;
}
.ds-act-edit { background: #eff6ff; border-color: #bfdbfe; color: #1d4ed8; }
.ds-act-edit:hover { background: #dbeafe; color: #1d4ed8; text-decoration: none; }
.ds-act-clone { background: #f5f3ff; border-color: #ddd6fe; color: #6d28d9; }
.ds-act-clone:hover { background: #ede9fe; color: #6d28d9; text-decoration: none; }
.ds-act-blast { background: #fefce8; border-color: #fde68a; color: #92400e; }
.ds-act-blast:hover { background: #fef9c3; color: #92400e; text-decoration: none; }

/* ── Table footer / pagination ── */
.ds-table-footer {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 14px;
  border-top: 1px solid #f0f4f8; flex-shrink: 0;
}

.ds-pagesize-wrap { display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: #64748b; }

.ds-pagesize-select {
  appearance: none;
  background: #f8fafc url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='8' height='5'%3E%3Cpath d='M0 0l4 5 4-5z' fill='%2394a3b8'/%3E%3C/svg%3E") no-repeat right 8px center;
  border: 1px solid #e2e8f0; border-radius: 6px;
  padding: 4px 22px 4px 9px;
  font-size: 11.5px; font-family: 'DM Mono', monospace;
  font-weight: 500; color: #334155; cursor: pointer; outline: none;
  transition: border-color 0.12s;
}
.ds-pagesize-select:hover { border-color: #c4b5fd; }
.ds-pagesize-select:focus { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }

.ds-record-info { font-size: 11px; color: #94a3b8; font-family: 'DM Mono', monospace; }

.ds-pagination { margin-left: auto; display: flex; gap: 3px; }
.ds-pg {
  min-width: 28px; height: 28px; border-radius: 6px;
  border: 1px solid #e2e8f0; background: #fff;
  color: #64748b; font-size: 11px; font-weight: 500;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; padding: 0 6px; transition: all 0.12s;
  text-decoration: none;
}
.ds-pg:hover { border-color: #c4b5fd; color: #6366f1; background: #f5f3ff; text-decoration: none; }
.ds-pg.active { background: linear-gradient(135deg, #38bdf8, #6366f1); color: #fff; border-color: transparent; font-weight: 700; box-shadow: 0 2px 6px rgba(99,102,241,0.3); }

/* ── Form card (used in edit/register pages) ── */
.ds-form-page { padding: 24px 20px; display: flex; justify-content: center; }
.ds-form-card {
  background: #fff; border-radius: 14px;
  border: 1px solid #e8edf4;
  box-shadow: 0 1px 4px rgba(15,23,42,0.05);
  padding: 28px 32px; width: 100%; max-width: 900px;
}
.ds-form-card-title { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 22px; }

.ds-form-row { margin-bottom: 16px; }
.ds-form-label { font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; display: block; }

.ds-form-control {
  width: 100%; height: 36px;
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 0 12px; font-size: 13px;
  font-family: 'DM Sans', sans-serif; color: #334155;
  background: #fff; outline: none;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.ds-form-control:focus { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
.ds-form-control[readonly], .ds-form-control:disabled {
  background: #f8fafc; color: #64748b; cursor: default;
}

.ds-form-textarea {
  width: 100%; min-height: 80px;
  border: 1px solid #e2e8f0; border-radius: 8px;
  padding: 10px 12px; font-size: 13px;
  font-family: 'DM Sans', sans-serif; color: #334155;
  background: #fff; outline: none; resize: vertical;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.ds-form-textarea:focus { border-color: #a5b4fc; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }

.ds-readonly-value {
  font-size: 13px; color: #334155; padding: 8px 12px;
  background: #f8fafc; border: 1px solid #e8edf4;
  border-radius: 8px; display: block; min-height: 36px;
}
.ds-readonly-value.mono { font-family: 'DM Mono', monospace; font-size: 11.5px; }

/* ── Upload / drag-drop zone ── */
.ds-upload-zone {
  border: 2px dashed #c7d2e8; border-radius: 12px;
  padding: 32px; text-align: center;
  background: #f8fafc; cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.ds-upload-zone:hover { border-color: #a5b4fc; background: #eef2ff; }
.ds-upload-zone-icon { font-size: 32px; color: #94a3b8; margin-bottom: 10px; }
.ds-upload-zone-text { font-size: 13px; color: #64748b; }
.ds-upload-zone-hint { font-size: 11px; color: #94a3b8; margin-top: 4px; }

/* ── Role badges ── */
.ds-role-badge {
  display: inline-flex; align-items: center;
  padding: 2px 8px; border-radius: 20px;
  font-size: 10.5px; font-weight: 600;
  font-family: 'DM Mono', monospace;
}
.ds-role-guest    { background: #f1f5f9; color: #475569; }
.ds-role-delivery { background: #dbeafe; color: #1d4ed8; }
.ds-role-modify   { background: #e0e7ff; color: #4338ca; }
.ds-role-project  { background: #ede9fe; color: #6d28d9; }
.ds-role-data_admin { background: #fef3c7; color: #92400e; }
.ds-role-admin    { background: #ffedd5; color: #c2410c; }
.ds-role-superadmin { background: #fee2e2; color: #991b1b; }

/* ── Alerts / toasts ── */
.ds-alert {
  padding: 12px 16px; border-radius: 10px;
  font-size: 12.5px; margin-bottom: 12px;
  display: flex; align-items: center; gap: 10px;
}
.ds-alert-success { background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d; }
.ds-alert-error   { background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; }
.ds-alert-info    { background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; }

/* Standalone pages (login / register / change_password) */
.ds-standalone-body {
  min-height: 100vh;
  background: #dde3ed;
  display: flex; align-items: center; justify-content: center;
  font-family: 'DM Sans', sans-serif;
  padding: 32px 16px;
}
.ds-standalone-card {
  background: #fff; border-radius: 16px;
  border: 1px solid #e8edf4;
  box-shadow: 0 4px 24px rgba(15,23,42,0.10);
  padding: 40px 44px; width: 100%; max-width: 400px;
}
.ds-standalone-logo { display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }
.ds-standalone-title { font-size: 20px; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
.ds-standalone-sub { font-size: 12.5px; color: #64748b; margin-bottom: 28px; }

/* Checkbox */
input[type=checkbox] { accent-color: #6366f1; width: 13px; height: 13px; cursor: pointer; }

/* Advanced search panel (existing panel, re-styled) */
.ds-search-panel {
  background: #fff; border: 1px solid #e8edf4;
  border-radius: 12px; box-shadow: 0 4px 20px rgba(15,23,42,0.10);
  padding: 16px 20px; margin-bottom: 8px;
}
.ds-search-panel-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 14px;
  font-size: 13px; font-weight: 600; color: #0f172a;
}

/* Toast container */
#msg-toast-container { position: fixed; top: 16px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 8px; }
.msg-toast {
  background: #fff; border: 1px solid #e8edf4;
  border-radius: 10px; padding: 12px 16px;
  box-shadow: 0 4px 16px rgba(15,23,42,0.12);
  display: flex; align-items: center; gap: 10px;
  font-size: 12.5px; color: #334155;
  animation: slideIn 0.2s ease;
}
@keyframes slideIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
.msg-toast-close { background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 14px; padding: 0; margin-left: auto; }
```

- [ ] **Step 2: Verify the file exists**

```bash
ls -la static/css/design-system.css
```
Expected: file present, ~400+ lines.

- [ ] **Step 3: Commit**

```bash
git add static/css/design-system.css
git commit -m "feat: add design-system CSS — DM Sans/Mono, sidebar shell, component tokens"
```

---

## Task 2: Create base.html

**Files:**
- Create: `templates/base.html`

The base template provides the full app shell. Individual pages `{% extends 'base.html' %}` and fill four blocks:
- `{% block page_title %}` — `<title>` suffix
- `{% block topbar_content %}` — everything inside `.ds-topbar` after the title+spacer
- `{% block extra_head %}` — page-specific `<style>` or `<script>` tags in `<head>`
- `{% block content %}` — the scrollable main content area
- `{% block extra_scripts %}` — page-specific `<script>` tags before `</body>`

The sidebar uses `request.resolver_match.url_name` to determine which nav item is active.

- [ ] **Step 1: Create base.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>SeqDB{% block page_title %}{% endblock %}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <!-- Bootstrap 5 -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">

  <!-- jQuery UI (needed by some pages for drag) -->
  <link href="https://code.jquery.com/ui/1.10.3/themes/redmond/jquery-ui.css" rel="stylesheet">

  <!-- Design system -->
  <link href="/static/css/design-system.css" rel="stylesheet">

  {% block extra_head %}{% endblock %}
</head>
<body>

{# Hidden CSRF holder used by JS fetch calls #}
<form style="display:none;" id="csrf-token-holder" method="post">
  {% csrf_token %}
</form>

<div class="app-shell">

  <!-- ── Sidebar ── -->
  <nav class="ds-sidebar">
    <div class="ds-sidebar-logo">
      <div class="ds-logo-mark">S</div>
      <div>
        <div class="ds-logo-text">SeqDB</div>
        <div class="ds-logo-tagline">Sequence Database</div>
      </div>
    </div>

    <div class="ds-nav-section">序列数据</div>
    <a href="{% url 'seq_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seq_list' %}active{% endif %}">
      <span class="ds-nav-dot"></span> 序列列表
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">功能模块</div>
    <a href="{% url 'register_seq' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'register_seq' %}active{% endif %}">
      <span class="ds-nav-dot"></span> 序列注册
    </a>
    <a href="{% url 'seq_delivery' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seq_delivery' %}active{% endif %}">
      <span class="ds-nav-dot"></span> 序列上传
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">BLAST</div>
    <a href="{% url 'multi_blast' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'multi_blast' or request.resolver_match.url_name == 'multi_blast_results' %}active{% endif %}">
      <span class="ds-nav-dot"></span> 多序列比对
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">模块管理</div>
    <a href="{% url 'module_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'module_list' or request.resolver_match.url_name == 'edit_module' %}active{% endif %}">
      <span class="ds-nav-dot"></span> Delivery 模块
    </a>
    <a href="{% url 'seqmodule_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'seqmodule_list' or request.resolver_match.url_name == 'edit_seqmodule' %}active{% endif %}">
      <span class="ds-nav-dot"></span> 序列修饰模块
    </a>

    {% if request.user.user_type in 'admin,superadmin' or request.user.is_superuser %}
    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">系统</div>
    <a href="{% url 'author_list' %}" class="ds-nav-item {% if request.resolver_match.url_name in 'author_list,add_author,edit_author' %}active{% endif %}">
      <span class="ds-nav-dot"></span> 用户管理
    </a>
    {% endif %}

    <div class="ds-sidebar-footer">
      <div class="ds-user-card">
        <div class="ds-user-avatar">{{ request.user.username|first|upper }}</div>
        <div>
          <div class="ds-user-name">{{ request.user.username }}</div>
          <div class="ds-user-role">
            <span class="ds-online-dot"></span>
            {{ request.user.user_type|default:"user" }}
          </div>
        </div>
      </div>
    </div>
  </nav>

  <!-- ── Main ── -->
  <div class="ds-main">

    <!-- Topbar -->
    <div class="ds-topbar">
      {% block topbar_content %}{% endblock %}
    </div>

    <!-- Scrollable content -->
    <div class="ds-content">
      {% if messages %}
        {% for message in messages %}
          <div class="ds-alert {% if message.tags == 'error' %}ds-alert-error{% elif message.tags == 'success' %}ds-alert-success{% else %}ds-alert-info{% endif %}">
            {{ message }}
          </div>
        {% endfor %}
      {% endif %}

      {% block content %}{% endblock %}
    </div>

  </div><!-- /ds-main -->
</div><!-- /app-shell -->

<!-- Toast container (used by seq_list JS) -->
<div id="msg-toast-container"></div>

<!-- Bootstrap JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>

<!-- jQuery + jQuery UI (some pages need drag) -->
<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
<script src="https://code.jquery.com/ui/1.13.2/jquery-ui.min.js"></script>

{% block extra_scripts %}{% endblock %}

</body>
</html>
```

- [ ] **Step 2: Start dev server and verify base loads**

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/seq_list/` — page should load (even if styling is partially broken until seq_list.html is updated).

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: add base.html — app shell with sidebar, topbar, and template blocks"
```

---

## Task 3: Redesign seq_list.html

**Files:**
- Rewrite: `templates/seq_list.html`

This is the most complex page. Key ID hooks that JS uses (must be preserved):
`#csrf-token-holder`, `#searchInput`, `#searchBtn`, `#clearAllSearch`, `#advancedSearchBtn`, `#advancedSearchPanel`, `#advancedSearchForm`, `#dragHandle`, `#closeSearchPanel`, `#modifySeqInputs`, `#addModifySeq`, `#applyFilters`, `#clearFilters`, `#msg-toast-container`, `#toggleCollapseBtn`, `#show-selected`, `#download-selected`, `#toggleProjectPanel`, `#toggleColumnPanel`, `#projectFilterPanel`, `#projects-select-toggle`, `#projects-apply`, `#projects-clear`, `#projectsFilterForm`, `#projectsCheckboxes`, `#columnFilterPanel`, `#column-controls`, `#example` (table), `#select-all`, `#seq_type_selector`, `.clone-seq-btn`

- [ ] **Step 1: Read the current seq_list.html to identify all template logic**

Read `templates/seq_list.html` lines 1–629 fully. Note: the file has a large `{% for group in page_obj %}` loop with nested delivery rows and `{% include %}` calls for `char_block_AS.html`/`char_block_SS.html`.

- [ ] **Step 2: Rewrite seq_list.html**

Replace the entire file with the following (preserving all Django template logic, IDs, and JS):

```html
{% extends 'base.html' %}

{% block page_title %} — 序列列表{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">序列列表</span>
  {% if page_obj %}
    <span class="ds-count-badge">{{ page_obj.paginator.count }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>

  <!-- Search -->
  <div class="ds-search-wrap">
    <i class="bi bi-search ds-search-icon"></i>
    <input type="text" id="searchInput" class="ds-search-input"
           placeholder="快速搜索 Strand ID / Target…" value="{{ search_q }}">
    <span class="ds-search-kbd">⌘K</span>
  </div>

  <button class="ds-btn ds-btn-ghost" id="advancedSearchBtn" type="button">⚙ 高级搜索{% if has_search and not search_q %} ●{% endif %}</button>
  <button class="ds-btn ds-btn-ghost" id="searchBtn" type="button" style="display:none;">搜索</button>
  <a class="ds-btn ds-btn-ghost" href="{% url 'seq_list' %}{% if selected_seq_type %}?seq_type={{ selected_seq_type }}{% endif %}" id="clearAllSearch" {% if not search_q and not has_search %}style="display:none;"{% endif %}>✕ 清除</a>
  <a class="ds-btn ds-btn-green" href="{% url 'multi_blast' %}">⌗ 多序列比对</a>
{% endblock %}

{% block content %}

<!-- Advanced search panel -->
<div id="advancedSearchPanel" style="display: none;" class="ds-search-panel">
  <div class="ds-search-panel-header" id="dragHandle">
    <span>高级搜索</span>
    <button id="closeSearchPanel" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:16px;">✖</button>
  </div>
  <form id="advancedSearchForm" method="GET" action="{% url 'seq_list' %}">
    <div class="row g-2">
      <div class="col-md-3">
        <label class="ds-form-label">Project</label>
        <input type="text" name="project" class="ds-form-control" value="{{ adv_project|default:'' }}">
      </div>
      <div class="col-md-3">
        <label class="ds-form-label">Target</label>
        <input type="text" name="target" class="ds-form-control" value="{{ adv_target|default:'' }}">
      </div>
      <div class="col-md-3">
        <label class="ds-form-label">Strand ID</label>
        <input type="text" name="rm_code" class="ds-form-control" value="{{ adv_rm_code|default:'' }}">
      </div>
      <div class="col-md-3">
        <label class="ds-form-label">Sequence ID</label>
        <input type="text" name="seq_id" class="ds-form-control" value="{{ adv_seq_id|default:'' }}">
      </div>
      <div class="col-md-6" id="modifySeqInputs">
        <label class="ds-form-label">Modify Seq</label>
        {% for ms in adv_modify_seqs %}
          <input type="text" name="modify_seq" class="ds-form-control mb-1" value="{{ ms }}">
        {% empty %}
          <input type="text" name="modify_seq" class="ds-form-control">
        {% endfor %}
      </div>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;">
      <button type="button" id="addModifySeq" class="ds-btn ds-btn-ghost" style="height:30px;font-size:11px;">+ 添加修饰</button>
      <button type="submit" id="applyFilters" class="ds-btn ds-btn-primary" style="height:30px;font-size:11px;">✅ 应用筛选</button>
      <button type="button" id="clearFilters" class="ds-btn ds-btn-ghost" style="height:30px;font-size:11px;">❌ 清除筛选</button>
    </div>
  </form>
</div>

<!-- Active filter bar -->
<div id="activeFilterBar" style="font-size:12px;color:#64748b;"></div>

<!-- Toolbar -->
<div class="ds-toolbar">
  <button id="toggleCollapseBtn" class="ds-tb-btn">▤ 组合/展开</button>
  <button id="show-selected" type="button" class="ds-tb-btn">☑ 显示选中</button>
  <a id="download-selected" class="ds-tb-btn" href="#">↓ 下载选中</a>
  <button id="toggleProjectPanel" type="button" class="ds-tb-btn {% if selected_projects %}ds-active-filter{% endif %}">
    ▼ 项目筛选 {% if selected_projects %}<span class="ds-tb-badge">{{ selected_projects|length }}</span>{% endif %}
  </button>
  <button id="toggleColumnPanel" type="button" class="ds-tb-btn">◧ 列显示</button>
</div>

<!-- Project filter panel -->
<div id="projectFilterPanel" style="display:none;" class="ds-search-panel">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
    <button id="projects-select-toggle" type="button" class="ds-btn ds-btn-ghost" style="height:28px;font-size:11px;">全选/取消</button>
    <button id="projects-apply" type="button" class="ds-btn ds-btn-primary" style="height:28px;font-size:11px;">应用筛选</button>
    <button id="projects-clear" type="button" class="ds-btn ds-btn-ghost" style="height:28px;font-size:11px;">清除</button>
  </div>
  <form id="projectsFilterForm" method="GET" action="">
    <div id="projectsCheckboxes" style="display:flex;flex-wrap:wrap;gap:8px;">
      {% for proj in all_projects %}
        <label style="display:flex;align-items:center;gap:5px;font-size:12px;cursor:pointer;">
          <input type="checkbox" name="project" value="{{ proj }}" {% if proj in selected_projects %}checked{% endif %}> {{ proj }}
        </label>
      {% endfor %}
    </div>
  </form>
</div>

<!-- Column filter panel -->
<div id="columnFilterPanel" style="display:none;" class="ds-search-panel">
  <div id="column-controls" style="display:flex;flex-wrap:wrap;gap:8px;">
    {# column toggles rendered by existing JS #}
  </div>
</div>

<!-- Seq type selector (for AS/SS toggle) -->
<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
  <select id="seq_type_selector" class="ds-pagesize-select" style="width:auto;">
    <option value="">全部类型</option>
    <option value="AS" {% if selected_seq_type == 'AS' %}selected{% endif %}>AS</option>
    <option value="SS" {% if selected_seq_type == 'SS' %}selected{% endif %}>SS</option>
    <option value="duplex" {% if selected_seq_type == 'duplex' %}selected{% endif %}>Duplex</option>
  </select>
</div>

<!-- Table -->
<div class="ds-table-card">
  <div class="ds-table-scroll">
    <table id="example" class="ds-table">
      <thead>
        <tr>
          <th><input type="checkbox" id="select-all"></th>
          <th>Strand ID <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Project <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Target <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Sequence ID <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Ligand 1</th>
          <th>Sequences</th>
          <th>Ligand 2</th>
          <th>Transcript <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Position <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Strand_MWs <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>Parents</th>
          <th>Remarks</th>
          <th>Update Time <span class="ds-sort-icon"><span class="arr-up"></span><span class="arr-dn"></span></span></th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for group in page_obj %}
        {# ── First row (AS or single) ── #}
        <tr data-rm-code="{{ group.items.0.rm_code }}"
            data-delivery-id="{{ group.items.0.deliveries.0.id }}"
            data-strand-mws="{{ group.items.0.deliveries.0.Strand_MWs }}"
            data-seq-type="{{ group.items.0.deliveries.0.Seq_type }}">
          <td class="cell-check"><input type="checkbox" class="row-check" value="{{ group.items.0.rm_code }}"></td>
          <td class="cell-id">{{ group.items.0.rm_code }}</td>
          <td class="cell-text">{{ group.items.0.seq_info.project|default:"—" }}</td>
          <td class="cell-text">{{ group.items.0.seq_info.target|default:"—" }}</td>
          <td class="cell-code">{{ group.items.0.deliveries.0.id|default:"—" }}</td>
          <td>
            <div class="ds-lig-row">
              {% for seg in group.items.0.deliveries.0.linker_5p_colored %}
                <span class="ds-lig" style="background:{{ seg.color }};">{{ seg.text }}</span>
              {% endfor %}
            </div>
          </td>
          <td>
            <div class="ds-seq-row">
              {% if group.items.0.deliveries.0.Seq_type == 'AS' %}
                {% include "char_block_AS.html" with delivery=group.items.0.deliveries.0 %}
              {% else %}
                {% include "char_block_SS.html" with delivery=group.items.0.deliveries.0 %}
              {% endif %}
            </div>
          </td>
          <td>
            <div class="ds-lig-row">
              {% for seg in group.items.0.deliveries.0.linker_3p_colored %}
                <span class="ds-lig" style="background:{{ seg.color }};">{{ seg.text }}</span>
              {% endfor %}
            </div>
          </td>
          <td class="cell-text">{{ group.items.0.seq_info.transcript|default:"—" }}</td>
          <td class="cell-dim">{{ group.items.0.seq_info.position|default:"—" }}</td>
          <td class="cell-code">{{ group.items.0.deliveries.0.Strand_MWs|default:"—" }}</td>
          <td class="cell-dim">{{ group.items.0.deliveries.0.parents|default:"—" }}</td>
          <td class="cell-dim">{{ group.items.0.deliveries.0.remarks|default:"—" }}</td>
          <td class="cell-mono-dim">{{ group.items.0.formatted_update_time|default:"—" }}</td>
          <td>
            <div class="ds-actions">
              <a class="ds-act ds-act-edit" href="/edit_seq/?id={{ group.items.0.rm_code }}&strand_MWs={{ group.items.0.deliveries.0.Strand_MWs }}&next={{ request.get_full_path|urlencode }}">编辑</a>
              <button class="ds-act ds-act-clone clone-seq-btn" data-strand-id="{{ group.duplex_id }}">克隆序列</button>
              <a class="ds-act ds-act-blast" href="/blast_seq/?delivery_id={{ group.items.0.rm_code }}&seq_type={{ group.items.0.deliveries.0.Seq_type }}" target="_blank">Blast</a>
            </div>
          </td>
        </tr>

        {# ── Second row (SS for duplex) ── #}
        {% if group.items|length > 1 %}
        <tr data-rm-code="{{ group.items.1.rm_code }}"
            data-delivery-id="{{ group.items.1.deliveries.0.id }}"
            data-strand-mws="{{ group.items.1.deliveries.0.Strand_MWs }}"
            data-seq-type="{{ group.items.1.deliveries.0.Seq_type }}">
          <td class="cell-check"><input type="checkbox" class="row-check" value="{{ group.items.1.rm_code }}"></td>
          <td class="cell-id">{{ group.items.1.rm_code }}</td>
          <td class="cell-text">{{ group.items.1.seq_info.project|default:"—" }}</td>
          <td class="cell-text">{{ group.items.1.seq_info.target|default:"—" }}</td>
          <td class="cell-code">{{ group.items.1.deliveries.0.id|default:"—" }}</td>
          <td>
            <div class="ds-lig-row">
              {% for seg in group.items.1.deliveries.0.linker_5p_colored %}
                <span class="ds-lig" style="background:{{ seg.color }};">{{ seg.text }}</span>
              {% endfor %}
            </div>
          </td>
          <td>
            <div class="ds-seq-row">
              {% include "char_block_SS.html" with delivery=group.items.1.deliveries.0 %}
            </div>
          </td>
          <td>
            <div class="ds-lig-row">
              {% for seg in group.items.1.deliveries.0.linker_3p_colored %}
                <span class="ds-lig" style="background:{{ seg.color }};">{{ seg.text }}</span>
              {% endfor %}
            </div>
          </td>
          <td class="cell-text">{{ group.items.1.seq_info.transcript|default:"—" }}</td>
          <td class="cell-dim">{{ group.items.1.seq_info.position|default:"—" }}</td>
          <td class="cell-code">{{ group.items.1.deliveries.0.Strand_MWs|default:"—" }}</td>
          <td class="cell-dim">{{ group.items.1.deliveries.0.parents|default:"—" }}</td>
          <td class="cell-dim">{{ group.items.1.deliveries.0.remarks|default:"—" }}</td>
          <td class="cell-mono-dim">{{ group.items.1.formatted_update_time|default:"—" }}</td>
          <td>
            <div class="ds-actions">
              <a class="ds-act ds-act-edit" href="/edit_seq/?id={{ group.items.1.rm_code }}&strand_MWs={{ group.items.1.deliveries.0.Strand_MWs }}&next={{ request.get_full_path|urlencode }}">编辑</a>
              <button class="ds-act ds-act-clone clone-seq-btn" data-strand-id="{{ group.duplex_id }}">克隆序列</button>
              <a class="ds-act ds-act-blast" href="/blast_seq/?delivery_id={{ group.items.1.rm_code }}&seq_type={{ group.items.1.deliveries.0.Seq_type }}" target="_blank">Blast</a>
            </div>
          </td>
        </tr>
        {% endif %}
        {% endfor %}
      </tbody>
    </table>
  </div>

  <!-- Table footer: page size + info + pagination -->
  <div class="ds-table-footer">
    <div class="ds-pagesize-wrap">
      每页显示
      <select class="ds-pagesize-select" id="pageSizeSelect" onchange="window.location.href=this.dataset.base+'&page_size='+this.value">
        {% for size in page_sizes %}
          <option value="{{ size }}" data-base="{{ request.path }}?{{ query_string_no_page }}"
            {% if page_size == size %}selected{% endif %}>{{ size }}</option>
        {% endfor %}
      </select>
      条
    </div>
    <span class="ds-record-info">
      第 {{ page_obj.start_index }}–{{ page_obj.end_index }} 条，共 {{ page_obj.paginator.count }} 条
    </span>
    <div class="ds-pagination">
      {% if page_obj.has_previous %}
        <a class="ds-pg" href="?{{ query_string_no_page }}&page={{ page_obj.previous_page_number }}">‹</a>
      {% else %}
        <span class="ds-pg" style="opacity:0.4;">‹</span>
      {% endif %}

      {% for p in page_obj.paginator.page_range %}
        {% if p == page_obj.number %}
          <span class="ds-pg active">{{ p }}</span>
        {% elif p == 1 or p == page_obj.paginator.num_pages or p >= page_obj.number|add:"-2" and p <= page_obj.number|add:"2" %}
          <a class="ds-pg" href="?{{ query_string_no_page }}&page={{ p }}">{{ p }}</a>
        {% elif p == page_obj.number|add:"-3" or p == page_obj.number|add:"3" %}
          <span class="ds-pg" style="cursor:default;">…</span>
        {% endif %}
      {% endfor %}

      {% if page_obj.has_next %}
        <a class="ds-pg" href="?{{ query_string_no_page }}&page={{ page_obj.next_page_number }}">›</a>
      {% else %}
        <span class="ds-pg" style="opacity:0.4;">›</span>
      {% endif %}
    </div>
  </div>
</div>

{% include 'clone_modal.html' %}

{% endblock %}

{% block extra_scripts %}
{# Preserve all existing JavaScript from the original seq_list.html — paste the <script> blocks here verbatim #}
{% endblock %}
```

**IMPORTANT NOTE for the implementer:** After writing the above skeleton, open the original `seq_list.html` and copy the full `<script>` section (all JavaScript between the last `<script>` and `</script>` tags) into the `{% block extra_scripts %}` block verbatim. The JS references the preserved IDs so it will continue to work.

Also check the exact context variable names the view passes. Open `app01/views.py` and search for `get_sequence_info` to verify the template variable names for: `page_obj`, `page_sizes`, `page_size`, `query_string_no_page`, `search_q`, `has_search`, `selected_seq_type`, `all_projects`, `selected_projects`, `adv_project`, `adv_target`, `adv_rm_code`, `adv_seq_id`, `adv_modify_seqs`. Adjust template variable names to match exactly what the view passes.

- [ ] **Step 3: Verify in browser**

Navigate to `http://127.0.0.1:8000/seq_list/`. Check:
- Sidebar shows with correct active item "序列列表"
- Topbar shows title, count badge, search box, and green "多序列比对" button
- Table renders with all columns
- Pagination footer appears
- Existing JS (toggle collapse, project filter, column filter, clone modal) still works

- [ ] **Step 4: Commit**

```bash
git add templates/seq_list.html
git commit -m "feat: redesign seq_list with new design system"
```

---

## Task 4: Redesign seq_edit.html

**Files:**
- Rewrite: `templates/seq_edit.html`

- [ ] **Step 1: Read current seq_edit.html to note all form fields and JS**

Open `templates/seq_edit.html`. Identify: all `<input>` names, the form `action`, any JS that auto-fills the datetime field.

- [ ] **Step 2: Rewrite seq_edit.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 编辑序列{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">编辑序列</span>
  <span style="font-family:'DM Mono',monospace;font-size:12px;color:#94a3b8;margin-left:6px;">{{ delivery.rm_code }}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{{ next_url|default:'/' }}" class="ds-btn ds-btn-ghost">← 返回列表</a>
{% endblock %}

{% block content %}
<div class="ds-form-page" style="padding-top:20px;">
  <div class="ds-form-card">
    <div class="ds-form-card-title">序列信息编辑</div>

    <form method="post" action="">
      {% csrf_token %}
      <input type="hidden" name="delivery_id" value="{{ delivery.id }}">
      <input type="hidden" name="next" value="{{ next_url }}">

      <div class="row g-3">
        <div class="col-md-6">
          <label class="ds-form-label">Project</label>
          <span class="ds-readonly-value">{{ delivery.rm_code_obj.seq_info.project|default:"—" }}</span>
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">Target</label>
          <span class="ds-readonly-value">{{ delivery.rm_code_obj.seq_info.target|default:"—" }}</span>
        </div>
        <div class="col-md-12">
          <label class="ds-form-label">Sequence</label>
          <span class="ds-readonly-value mono">{{ delivery.modify_seq|default:"—" }}</span>
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">5' Ligand</label>
          <input type="text" name="linker_5p" class="ds-form-control" value="{{ delivery.linker_5p|default:'' }}">
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">3' Ligand</label>
          <input type="text" name="linker_3p" class="ds-form-control" value="{{ delivery.linker_3p|default:'' }}">
        </div>
        <div class="col-md-4">
          <label class="ds-form-label">Transcript</label>
          <span class="ds-readonly-value">{{ delivery.rm_code_obj.seq_info.transcript|default:"—" }}</span>
        </div>
        <div class="col-md-4">
          <label class="ds-form-label">Position</label>
          <span class="ds-readonly-value">{{ delivery.rm_code_obj.seq_info.position|default:"—" }}</span>
        </div>
        <div class="col-md-4">
          <label class="ds-form-label">Strand_MWs</label>
          <input type="text" name="Strand_MWs" class="ds-form-control" value="{{ delivery.Strand_MWs|default:'' }}">
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">Parents</label>
          <input type="text" name="parents" class="ds-form-control" value="{{ delivery.parents|default:'' }}">
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">更新时间</label>
          <input type="datetime-local" name="update_time" id="updateTimeInput" class="ds-form-control">
        </div>
        <div class="col-md-12">
          <label class="ds-form-label">Remarks</label>
          <textarea name="remarks" class="ds-form-textarea">{{ delivery.remarks|default:'' }}</textarea>
        </div>
      </div>

      <div style="margin-top:24px;display:flex;gap:10px;justify-content:flex-end;">
        <a href="{{ next_url|default:'/' }}" class="ds-btn ds-btn-ghost">取消</a>
        <button type="submit" class="ds-btn ds-btn-primary">保存修改</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script>
  // Auto-fill current datetime on load (preserve original behavior)
  const el = document.getElementById('updateTimeInput');
  if (el && !el.value) {
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    el.value = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  }
</script>
{% endblock %}
```

**Note for implementer:** Read `app01/views.py` `edit_seq` view to verify the exact context variable names (`delivery`, field names on delivery object, `next_url`, etc.) and adjust the template accordingly. The form field `name` attributes must match what the view reads from `request.POST`.

- [ ] **Step 3: Verify in browser**

Navigate to a sequence edit URL (e.g., `http://127.0.0.1:8000/edit_seq/?id=RM230001&strand_MWs=...`). Verify form renders, read-only fields appear correctly, and submit works.

- [ ] **Step 4: Commit**

```bash
git add templates/seq_edit.html
git commit -m "feat: redesign seq_edit with card form layout"
```

---

## Task 5: Redesign register_seq.html

**Files:**
- Rewrite: `templates/register_seq.html`

- [ ] **Step 1: Read current register_seq.html for form fields and JS**

Open `templates/register_seq.html`. Note the form action, file input name, and any validation JS.

- [ ] **Step 2: Rewrite register_seq.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 序列注册{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">序列注册</span>
  <span class="ds-topbar-spacer"></span>
{% endblock %}

{% block content %}
<div class="ds-form-page" style="padding-top:20px;">
  <div class="ds-form-card">
    <div class="ds-form-card-title">CSV 序列注册</div>

    {% if messages %}
      {% for message in messages %}
        <div class="ds-alert {% if message.tags == 'error' %}ds-alert-error{% elif message.tags == 'success' %}ds-alert-success{% else %}ds-alert-info{% endif %}" style="margin-bottom:16px;">
          {{ message }}
        </div>
      {% endfor %}
    {% endif %}

    <form method="post" enctype="multipart/form-data" action="">
      {% csrf_token %}

      <label class="ds-form-label">上传 CSV 文件</label>
      <div class="ds-upload-zone" id="dropZone" onclick="document.getElementById('csvFile').click()">
        <div class="ds-upload-zone-icon"><i class="bi bi-file-earmark-spreadsheet"></i></div>
        <div class="ds-upload-zone-text">点击选择文件，或将 CSV 拖放到此处</div>
        <div class="ds-upload-zone-hint" id="fileNameHint">支持 .csv 格式</div>
      </div>
      <input type="file" id="csvFile" name="file" accept=".csv" style="display:none;"
             onchange="document.getElementById('fileNameHint').textContent = this.files[0]?.name || '支持 .csv 格式'">

      <div style="margin-top:24px;display:flex;justify-content:flex-end;">
        <button type="submit" class="ds-btn ds-btn-primary">上传并注册</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

**Note:** Read the original `register_seq.html` to confirm the file input `name` attribute and any additional form fields, then adjust.

- [ ] **Step 3: Verify in browser, submit a test CSV**

- [ ] **Step 4: Commit**

```bash
git add templates/register_seq.html
git commit -m "feat: redesign register_seq with upload card"
```

---

## Task 6: Redesign multi_blast.html + multi_blast_results.html

**Files:**
- Rewrite: `templates/multi_blast.html`
- Rewrite: `templates/multi_blast_results.html`

- [ ] **Step 1: Read both templates for form fields and results structure**

Open `templates/multi_blast.html` and `templates/multi_blast_results.html`.

- [ ] **Step 2: Rewrite multi_blast.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 多序列比对{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">多序列比对</span>
  <span class="ds-topbar-spacer"></span>
{% endblock %}

{% block content %}
<div class="ds-form-page" style="padding-top:20px;">
  <div class="ds-form-card" style="max-width:800px;">
    <div class="ds-form-card-title">BLAST 多序列比对</div>

    <form method="post" action="">
      {% csrf_token %}

      <div class="ds-form-row">
        <label class="ds-form-label">输入序列（每行一条，FASTA 格式或裸序列）</label>
        <textarea name="sequences" class="ds-form-textarea"
                  style="min-height:160px;font-family:'DM Mono',monospace;font-size:12px;"
                  placeholder=">Seq1&#10;AUGCUAGCUAGCU&#10;>Seq2&#10;GCUAGCUAGCUA">{{ sequences|default:'' }}</textarea>
      </div>

      <div class="row g-2 mt-1">
        <div class="col-md-4">
          <label class="ds-form-label">比对类型</label>
          <select name="blast_type" class="ds-form-control" style="height:36px;">
            <option value="blastn">blastn (核酸)</option>
            <option value="blastp">blastp (蛋白)</option>
          </select>
        </div>
        <div class="col-md-4">
          <label class="ds-form-label">E-value 阈值</label>
          <input type="text" name="evalue" class="ds-form-control" value="{{ evalue|default:'0.001' }}">
        </div>
        <div class="col-md-4">
          <label class="ds-form-label">最大结果数</label>
          <input type="number" name="max_hits" class="ds-form-control" value="{{ max_hits|default:'10' }}">
        </div>
      </div>

      <div style="margin-top:24px;display:flex;justify-content:flex-end;">
        <button type="submit" class="ds-btn ds-btn-green">⌗ 开始比对</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Rewrite multi_blast_results.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 比对结果{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">比对结果</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'multi_blast' %}" class="ds-btn ds-btn-ghost">← 重新查询</a>
{% endblock %}

{% block content %}
  {% if results %}
    {% for result in results %}
    <div class="ds-table-card" style="margin-bottom:12px;">
      <div style="padding:12px 16px;border-bottom:1px solid #f0f4f8;">
        <span style="font-family:'DM Mono',monospace;font-size:12px;font-weight:600;color:#4338ca;">{{ result.query_id }}</span>
        <span style="font-size:11px;color:#94a3b8;margin-left:8px;">{{ result.query_length }} nt</span>
      </div>
      <div class="ds-table-scroll">
        <table class="ds-table" style="min-width:600px;">
          <thead>
            <tr>
              <th>Hit ID</th><th>Description</th><th>Score</th><th>E-value</th><th>Identity</th><th>Coverage</th>
            </tr>
          </thead>
          <tbody>
            {% for hit in result.hits %}
            <tr>
              <td class="cell-id">{{ hit.id }}</td>
              <td class="cell-text">{{ hit.description }}</td>
              <td class="cell-code">{{ hit.score }}</td>
              <td class="cell-dim">{{ hit.evalue }}</td>
              <td class="cell-code">{{ hit.identity }}%</td>
              <td class="cell-code">{{ hit.coverage }}%</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
    {% endfor %}
  {% else %}
    <div class="ds-alert ds-alert-info">暂无比对结果。</div>
  {% endif %}
{% endblock %}
```

**Note:** Read original templates to confirm the exact context variable names (`results`, `hits`, field names) and adjust accordingly.

- [ ] **Step 4: Verify both pages in browser**

- [ ] **Step 5: Commit**

```bash
git add templates/multi_blast.html templates/multi_blast_results.html
git commit -m "feat: redesign multi_blast pages"
```

---

## Task 7: Redesign blast_results.html

**Files:**
- Rewrite: `templates/blast_results.html`

- [ ] **Step 1: Read blast_results.html**

Open `templates/blast_results.html` and note the context variables.

- [ ] **Step 2: Rewrite blast_results.html**

```html
{% extends 'base.html' %}

{% block page_title %} — BLAST 结果{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">BLAST 结果</span>
  <span class="ds-topbar-spacer"></span>
  <a href="javascript:history.back()" class="ds-btn ds-btn-ghost">← 返回</a>
{% endblock %}

{% block content %}
  {# Preserve original blast_results content, re-wrapped with ds-table-card #}
  <div class="ds-table-card">
    <div class="ds-table-scroll">
      <table class="ds-table" style="min-width:700px;">
        <thead>
          <tr>
            {# Column headers from original template — copy verbatim from blast_results.html #}
          </tr>
        </thead>
        <tbody>
          {# Original {% for %} loop — copy verbatim from blast_results.html, replace Bootstrap classes with DS classes #}
        </tbody>
      </table>
    </div>
  </div>
{% endblock %}
```

**Instruction:** Open `templates/blast_results.html`, copy the table `<thead>` and `<tbody>` contents exactly, then replace `class="table table-bordered"` → `class="ds-table"`, `class="btn btn-info btn-sm"` → `class="ds-act ds-act-edit"`, etc.

- [ ] **Step 3: Verify in browser by running a BLAST query**

- [ ] **Step 4: Commit**

```bash
git add templates/blast_results.html
git commit -m "feat: redesign blast_results page"
```

---

## Task 8: Redesign module_list.html + edit_module.html + upload_modules.html

**Files:**
- Rewrite: `templates/module_list.html`
- Rewrite: `templates/edit_module.html`
- Rewrite: `templates/upload_modules.html`

- [ ] **Step 1: Read all three templates**

Open each file. Note context variables and form fields.

- [ ] **Step 2: Rewrite module_list.html**

```html
{% extends 'base.html' %}

{% block page_title %} — Delivery 模块{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">Delivery 模块</span>
  {% if modules %}
    <span class="ds-count-badge">{{ modules|length }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'upload_modules' %}" class="ds-btn ds-btn-ghost">↑ 批量上传</a>
  <a href="{% url 'edit_module' %}" class="ds-btn ds-btn-primary">＋ 新增模块</a>
{% endblock %}

{% block content %}
<div class="ds-table-card">
  <div class="ds-table-scroll">
    <table class="ds-table" style="min-width:600px;">
      <thead>
        <tr>
          <th>关键词</th>
          <th>Type Code</th>
          <th>描述</th>
          <th>颜色</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for mod in modules %}
        <tr>
          <td class="cell-code">{{ mod.keyword }}</td>
          <td><span class="ds-role-badge" style="background:{{ mod.color|default:'#e2e8f0' }};color:#fff;">{{ mod.type_code }}</span></td>
          <td class="cell-text">{{ mod.description|default:"—" }}</td>
          <td>
            <span style="display:inline-block;width:20px;height:20px;border-radius:4px;background:{{ mod.color|default:'#e2e8f0' }};border:1px solid #e2e8f0;vertical-align:middle;"></span>
            <code style="font-size:10px;color:#64748b;margin-left:4px;">{{ mod.color|default:"—" }}</code>
          </td>
          <td>
            <div class="ds-actions">
              <a class="ds-act ds-act-edit" href="{% url 'edit_module' %}?id={{ mod.id }}">编辑</a>
              <a class="ds-act ds-act-blast" href="{% url 'delete_module' %}?id={{ mod.id }}"
                 onclick="return confirm('确定删除此模块？')">删除</a>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="5" style="text-align:center;color:#94a3b8;padding:24px;">暂无模块数据</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Rewrite edit_module.html**

```html
{% extends 'base.html' %}

{% block page_title %} — {% if module %}编辑{% else %}新增{% endif %}模块{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">{% if module %}编辑 Delivery 模块{% else %}新增 Delivery 模块{% endif %}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost">← 返回列表</a>
{% endblock %}

{% block content %}
<div class="ds-form-page" style="padding-top:20px;">
  <div class="ds-form-card" style="max-width:600px;">
    <form method="post" action="">
      {% csrf_token %}
      {% if module %}<input type="hidden" name="id" value="{{ module.id }}">{% endif %}

      <div class="row g-3">
        <div class="col-md-6">
          <label class="ds-form-label">关键词 (keyword)</label>
          <input type="text" name="keyword" class="ds-form-control" value="{{ module.keyword|default:'' }}" required>
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">Type Code</label>
          <input type="text" name="type_code" class="ds-form-control" value="{{ module.type_code|default:'' }}" required>
        </div>
        <div class="col-md-12">
          <label class="ds-form-label">描述</label>
          <input type="text" name="description" class="ds-form-control" value="{{ module.description|default:'' }}">
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">颜色 (hex)</label>
          <input type="text" name="color" class="ds-form-control" value="{{ module.color|default:'#94a3b8' }}" placeholder="#94a3b8">
        </div>
      </div>

      <div style="margin-top:24px;display:flex;gap:10px;justify-content:flex-end;">
        <a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost">取消</a>
        <button type="submit" class="ds-btn ds-btn-primary">保存</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Rewrite upload_modules.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 上传 Delivery 模块{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">批量上传 Delivery 模块</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'module_list' %}" class="ds-btn ds-btn-ghost">← 返回列表</a>
{% endblock %}

{% block content %}
<div class="ds-form-page" style="padding-top:20px;">
  <div class="ds-form-card" style="max-width:600px;">
    <div class="ds-form-card-title">CSV 批量上传</div>
    <form method="post" enctype="multipart/form-data" action="">
      {% csrf_token %}
      <label class="ds-form-label">选择 CSV 文件</label>
      <div class="ds-upload-zone" onclick="document.getElementById('modFile').click()">
        <div class="ds-upload-zone-icon"><i class="bi bi-file-earmark-spreadsheet"></i></div>
        <div class="ds-upload-zone-text">点击选择 CSV 文件</div>
        <div class="ds-upload-zone-hint" id="modFileHint">支持 .csv 格式</div>
      </div>
      <input type="file" id="modFile" name="file" accept=".csv" style="display:none;"
             onchange="document.getElementById('modFileHint').textContent = this.files[0]?.name || '支持 .csv 格式'">
      <div style="margin-top:20px;display:flex;justify-content:flex-end;">
        <button type="submit" class="ds-btn ds-btn-primary">上传</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

**Note:** Confirm form field names and context variable names against the view functions `module_list`, `edit_module`, `upload_modules` in `app01/views.py`.

- [ ] **Step 5: Verify all three pages in browser**

- [ ] **Step 6: Commit**

```bash
git add templates/module_list.html templates/edit_module.html templates/upload_modules.html
git commit -m "feat: redesign delivery module management pages"
```

---

## Task 9: Redesign seqmodule_list.html + edit_seqmodule.html + upload_seqmodules.html

**Files:**
- Rewrite: `templates/seqmodule_list.html`
- Rewrite: `templates/edit_seqmodule.html`
- Rewrite: `templates/upload_seqmodules.html`

These pages are structurally identical to Task 8 but for SeqModule objects. Follow the same pattern.

- [ ] **Step 1: Read all three templates**

- [ ] **Step 2: Rewrite seqmodule_list.html** — same structure as `module_list.html` but with SeqModule columns: `token`, `description`, `type`. Use `{% url 'seqmodule_list' %}`, `{% url 'edit_seqmodule' %}`, `{% url 'upload_seqmodules' %}`, `{% url 'delete_seqmodule' %}`.

- [ ] **Step 3: Rewrite edit_seqmodule.html** — same card form structure as `edit_module.html` with SeqModule fields. Use `{% url 'seqmodule_list' %}` for back/cancel links.

- [ ] **Step 4: Rewrite upload_seqmodules.html** — identical upload zone to `upload_modules.html`, use `{% url 'seqmodule_list' %}` for back link.

- [ ] **Step 5: Verify all three in browser**

- [ ] **Step 6: Commit**

```bash
git add templates/seqmodule_list.html templates/edit_seqmodule.html templates/upload_seqmodules.html
git commit -m "feat: redesign seqmodule management pages"
```

---

## Task 10: Redesign auth_list.html + auth_edit.html + author_add.html

**Files:**
- Rewrite: `templates/auth_list.html`
- Rewrite: `templates/auth_edit.html`
- Rewrite: `templates/author_add.html`

- [ ] **Step 1: Read all three templates**

Note: `auth_list.html` = user management list. `auth_edit.html` = edit user. `author_add.html` = add user.

- [ ] **Step 2: Rewrite auth_list.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 用户管理{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">用户管理</span>
  {% if users %}
    <span class="ds-count-badge">{{ users|length }}</span>
  {% endif %}
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'add_author' %}" class="ds-btn ds-btn-primary">＋ 新增用户</a>
{% endblock %}

{% block content %}
<div class="ds-table-card">
  <div class="ds-table-scroll">
    <table class="ds-table" style="min-width:700px;">
      <thead>
        <tr>
          <th>用户名</th>
          <th>邮箱</th>
          <th>角色</th>
          <th>所属项目</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {% for user in users %}
        <tr>
          <td class="cell-text" style="font-weight:600;">{{ user.username }}</td>
          <td class="cell-dim">{{ user.email|default:"—" }}</td>
          <td>
            <span class="ds-role-badge ds-role-{{ user.user_type|default:'guest' }}">{{ user.user_type|default:"guest" }}</span>
          </td>
          <td class="cell-dim">{{ user.permissions_project|default:"全部" }}</td>
          <td>
            {% if user.is_active %}
              <span style="color:#16a34a;font-size:11px;font-weight:600;">● 启用</span>
            {% else %}
              <span style="color:#94a3b8;font-size:11px;">● 禁用</span>
            {% endif %}
          </td>
          <td>
            <div class="ds-actions">
              <a class="ds-act ds-act-edit" href="{% url 'edit_author' %}?id={{ user.id }}">编辑</a>
              <a class="ds-act ds-act-blast" href="{% url 'drop_author' %}?id={{ user.id }}"
                 onclick="return confirm('确定删除用户 {{ user.username }}？')">删除</a>
            </div>
          </td>
        </tr>
        {% empty %}
        <tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:24px;">暂无用户</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Rewrite auth_edit.html**

```html
{% extends 'base.html' %}

{% block page_title %} — 编辑用户{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">编辑用户</span>
  <span class="ds-topbar-spacer"></span>
  <a href="{% url 'author_list' %}" class="ds-btn ds-btn-ghost">← 返回列表</a>
{% endblock %}

{% block content %}
<div class="ds-form-page" style="padding-top:20px;">
  <div class="ds-form-card" style="max-width:600px;">
    <form method="post" action="">
      {% csrf_token %}
      <input type="hidden" name="id" value="{{ edit_user.id }}">

      <div class="row g-3">
        <div class="col-md-6">
          <label class="ds-form-label">用户名</label>
          <input type="text" name="username" class="ds-form-control" value="{{ edit_user.username }}" required>
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">邮箱</label>
          <input type="email" name="email" class="ds-form-control" value="{{ edit_user.email|default:'' }}">
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">角色</label>
          <select name="user_type" class="ds-form-control" style="height:36px;">
            {% for role in role_choices %}
              <option value="{{ role }}" {% if edit_user.user_type == role %}selected{% endif %}>{{ role }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">所属项目 (逗号分隔)</label>
          <input type="text" name="permissions_project" class="ds-form-control" value="{{ edit_user.permissions_project|default:'' }}" placeholder="P001,P002">
        </div>
        <div class="col-md-12">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" name="is_active" {% if edit_user.is_active %}checked{% endif %}> 启用账户
          </label>
        </div>
        <div class="col-md-6">
          <label class="ds-form-label">新密码 (留空不修改)</label>
          <input type="password" name="password" class="ds-form-control">
        </div>
      </div>

      <div style="margin-top:24px;display:flex;gap:10px;justify-content:flex-end;">
        <a href="{% url 'author_list' %}" class="ds-btn ds-btn-ghost">取消</a>
        <button type="submit" class="ds-btn ds-btn-primary">保存</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Rewrite author_add.html**

Same structure as `auth_edit.html` but without the `id` hidden field and without a pre-filled user. Title "新增用户". Read original `author_add.html` to confirm field names.

- [ ] **Step 5: Verify in browser**

Navigate to `/author_list/`, `/add_author/`, and edit a user. Confirm role badges display correctly.

- [ ] **Step 6: Commit**

```bash
git add templates/auth_list.html templates/auth_edit.html templates/author_add.html
git commit -m "feat: redesign user management pages with role badges"
```

---

## Task 11: Redesign reg_seq_list.html + reg_seq_edit.html

**Files:**
- Rewrite: `templates/reg_seq_list.html`
- Rewrite: `templates/reg_seq_edit.html`

- [ ] **Step 1: Read both templates**

- [ ] **Step 2: Rewrite reg_seq_list.html**

Same table pattern as `module_list.html`. Use `ds-table-card` + `ds-table`. Read the original to find columns and context variable name (likely `reg_seqs` or `page_obj`). URLs: `{% url 'reg_seq_list' %}`, `{% url 'edit_reg_seq' %}`.

- [ ] **Step 3: Rewrite reg_seq_edit.html**

Card form pattern same as `seq_edit.html`. Read original for field names. Back link to `{% url 'reg_seq_list' %}`.

- [ ] **Step 4: Verify in browser**

- [ ] **Step 5: Commit**

```bash
git add templates/reg_seq_list.html templates/reg_seq_edit.html
git commit -m "feat: redesign registered sequence list and edit pages"
```

---

## Task 12: Redesign upload_delivery_info.html + search_results.html + cor_seq.html

**Files:**
- Rewrite: `templates/upload_delivery_info.html`
- Rewrite: `templates/search_results.html`
- Rewrite: `templates/cor_seq.html`

- [ ] **Step 1: Read all three templates**

Note: `search_results.html` is 541 lines — may be a full-page search interface. `cor_seq.html` is 410 lines — sequence correction flow. Read both carefully.

- [ ] **Step 2: Rewrite upload_delivery_info.html**

Upload zone pattern (same as `upload_modules.html`). URL: `{% url 'seq_delivery' %}`. Back link to `{% url 'seq_list' %}`.

- [ ] **Step 3: Rewrite search_results.html**

Wrap with `{% extends 'base.html' %}`. Topbar: "搜索结果". Content: preserve the existing search results table/list structure, replace Bootstrap table classes with `ds-table` classes, replace Bootstrap buttons with `ds-act` / `ds-btn` classes.

- [ ] **Step 4: Rewrite cor_seq.html**

Wrap with `{% extends 'base.html' %}`. Topbar: "序列核实". Preserve all form fields and JS. Replace visual elements with DS components.

- [ ] **Step 5: Verify all three in browser**

- [ ] **Step 6: Commit**

```bash
git add templates/upload_delivery_info.html templates/search_results.html templates/cor_seq.html
git commit -m "feat: redesign upload, search results, and cor_seq pages"
```

---

## Task 13: Redesign login.html + register.html + change_password.html

**Files:**
- Rewrite: `templates/login.html`
- Rewrite: `templates/register.html`
- Rewrite: `templates/change_password.html`

These are standalone pages — no sidebar. They do NOT extend `base.html`. Use `ds-standalone-body` and `ds-standalone-card`.

- [ ] **Step 1: Read all three templates for form fields and validation logic**

- [ ] **Step 2: Rewrite login.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>SeqDB — 登录</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
  <link href="/static/css/design-system.css" rel="stylesheet">
</head>
<body class="ds-standalone-body">

<div class="ds-standalone-card">
  <div class="ds-standalone-logo">
    <div class="ds-logo-mark">S</div>
    <div>
      <div class="ds-logo-text">SeqDB</div>
      <div class="ds-logo-tagline">Sequence Database</div>
    </div>
  </div>

  <div class="ds-standalone-title">欢迎回来</div>
  <div class="ds-standalone-sub">请登录您的账户以继续</div>

  {% if error %}
    <div class="ds-alert ds-alert-error" style="margin-bottom:16px;">{{ error }}</div>
  {% endif %}

  <form method="post" action="">
    {% csrf_token %}
    <div class="ds-form-row">
      <label class="ds-form-label">用户名</label>
      <input type="text" name="username" class="ds-form-control" placeholder="请输入用户名" autofocus required>
    </div>
    <div class="ds-form-row" style="margin-top:12px;">
      <label class="ds-form-label">密码</label>
      <input type="password" name="password" class="ds-form-control" placeholder="请输入密码" required>
    </div>
    <button type="submit" class="ds-btn ds-btn-primary" style="width:100%;margin-top:20px;justify-content:center;">
      登录
    </button>
  </form>

  <div style="text-align:center;margin-top:16px;font-size:12px;color:#64748b;">
    还没有账户？<a href="{% url 'signup' %}" style="color:#6366f1;">立即注册</a>
  </div>
</div>

</body>
</html>
```

- [ ] **Step 3: Rewrite register.html**

Same standalone structure as `login.html`. Form fields: `username`, `password`, `confirm_password`, `email`. Title: "创建账户". Back to login link at bottom.

Read original `register.html` to confirm form field names and action URL.

- [ ] **Step 4: Rewrite change_password.html**

Standalone card. Fields: `old_password`, `new_password`, `confirm_password`. Title: "修改密码".

Read original to confirm field names. Add a back link to the main app (`{% url 'seq_list' %}`).

- [ ] **Step 5: Verify login, register, change_password in browser**

- [ ] **Step 6: Commit**

```bash
git add templates/login.html templates/register.html templates/change_password.html
git commit -m "feat: redesign standalone auth pages (login, register, change_password)"
```

---

## Task 14: Update clone_modal.html partial

**Files:**
- Modify: `templates/clone_modal.html`

The clone modal is included in `seq_list.html`. It uses Bootstrap's Modal component. Update Bootstrap class references to match the new design.

- [ ] **Step 1: Read clone_modal.html**

Open `templates/clone_modal.html`.

- [ ] **Step 2: Style the modal header and buttons**

Keep the Bootstrap modal structure (`modal`, `modal-dialog`, `modal-header`, `modal-body`, `modal-footer`). Update:
- `btn btn-primary` → add `ds-btn ds-btn-primary` class (keep Bootstrap class for JS trigger compatibility)
- `btn btn-default` / `btn-secondary` → add `ds-btn ds-btn-ghost`
- Modal header background: add `style="background:#f8fafc;border-bottom:1px solid #e8edf4;"`
- Modal title: add `style="font-family:'DM Sans',sans-serif;font-weight:700;color:#0f172a;"`

- [ ] **Step 3: Verify clone modal opens from seq_list**

- [ ] **Step 4: Commit**

```bash
git add templates/clone_modal.html
git commit -m "feat: update clone modal styling"
```

---

## Task 15: Final integration check

- [ ] **Step 1: Run dev server and walk through all main flows**

```bash
python manage.py runserver
```

Test these flows in order:
1. Login → redirected to seq_list ✓
2. Seq list loads with sidebar, topbar, table, pagination ✓
3. Sidebar active highlight changes on navigation ✓
4. Advanced search panel opens and filters work ✓
5. Project filter panel opens and filters work ✓
6. Column toggle works ✓
7. Collapse/expand duplex rows works ✓
8. Download selected works ✓
9. Clone modal opens ✓
10. Edit sequence → form loads and saves ✓
11. Register seq → upload CSV ✓
12. Multi BLAST → submit → results ✓
13. Module list → add → edit → delete ✓
14. SeqModule list → add → edit → delete ✓
15. User management → add → edit ✓
16. Page size selector changes rows per page ✓
17. Change password ✓
18. Logout ✓

- [ ] **Step 2: Fix any broken IDs or context variable mismatches found during testing**

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete SeqDB frontend redesign — all pages updated"
```

---

## Quick Reference

### CSS class mapping (Bootstrap → Design System)

| Bootstrap | Design System | Notes |
|---|---|---|
| `btn btn-primary` | `ds-btn ds-btn-primary` | gradient |
| `btn btn-default` / `btn-secondary` | `ds-btn ds-btn-ghost` | white bg |
| `btn btn-success` | `ds-btn ds-btn-green` | #16a34a |
| `btn btn-info btn-sm` | `ds-act ds-act-edit` | table action |
| `btn btn-primary btn-sm` | `ds-act ds-act-clone` | table action |
| `btn btn-warning btn-sm` | `ds-act ds-act-blast` | table action |
| `form-control` | `ds-form-control` | |
| `table table-bordered` | `ds-table` | |
| `alert alert-success` | `ds-alert ds-alert-success` | |
| `container` / `row` / `col-*` | Keep Bootstrap grid | grid unchanged |
