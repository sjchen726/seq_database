# Design Spec: Multi-Term Grouped Search Results

**Date:** 2026-05-15
**Feature:** Display multiple search terms' results simultaneously in grouped blocks

## Overview

When a user enters 2–5 comma-separated search terms in `seq_list`, results are displayed in visually distinct color-coded blocks—one block per term—rather than a flat merged list. Single-term searches are unchanged.

## Scope

- Affects: `seq_list` view, `seq_list.html` template
- No changes to URL, search input widget, or any other view
- No new models or migrations required

## Backend (`app01/views.py` — `seq_list` view)

### Current behavior

`split_terms(q)` splits the query string into a list of terms. A single OR queryset is built across all terms and passed to the template as `seqs`.

### New behavior

After calling `split_terms(q)`:

- **Single term (or empty):** existing code path unchanged; pass `sequence_groups` to template.
- **Multiple terms (2–5):** silently truncate to 5 terms if more are provided. For each term independently:
  1. Apply the same `delivery_qs` Q-filter logic that currently handles a single term (fields: `duplex_id`, `Target`, `project`, `modify_seq`, `parents`, `delivery_id`, `linker_seq`).
  2. Expand matched rows to full duplex pairs (the existing `matched_pairs` → re-filter pattern).
  3. Call `build_duplex_groups(term_delivery_qs, selected_seq_type)` and attach `exp_summary` per group.
  4. Build `search_term_groups = [{'term': term, 'sequence_groups': [...], 'color_idx': i}, ...]` in input order.
- Pass `search_term_groups` (multi-term) **or** `sequence_groups` (single-term) to the template context. Exactly one will be non-empty.

### Refactoring

Extract the per-term filter logic (currently inlined in `seq_list`) into a private helper `_filter_delivery_qs_by_term(delivery_qs, term)` that returns a filtered queryset. The single-term path calls it once; the multi-term path calls it in a loop.

## Frontend (`templates/seq_list.html`)

### Grouped rendering

Add a conditional at the top of the results table body:

```
{% if search_term_groups %}
  {% for term_group in search_term_groups %}
    <tr class="search-group-header search-group-color-{{ term_group.color_idx }}">
      <td colspan="[all columns]">
        ▸ "{{ term_group.term }}" 的结果（{{ term_group.sequence_groups|length }} 组）
      </td>
    </tr>
    {% if term_group.sequence_groups %}
      {% for group in term_group.sequence_groups %}
        ... existing duplex-group rendering (identical to current single-term loop) ...
      {% endfor %}
    {% else %}
      <tr><td colspan="..." class="search-group-empty">— 无结果 —</td></tr>
    {% endif %}
  {% endfor %}
{% else %}
  ... existing flat iteration over sequence_groups (unchanged) ...
{% endif %}
```

### Color scheme (5 slots, rotating)

| color_idx | Header background | Header text |
|-----------|------------------|-------------|
| 0 | `#eff6ff` | `#1d4ed8` (blue) |
| 1 | `#f0fdf4` | `#166534` (green) |
| 2 | `#fff7ed` | `#9a3412` (orange) |
| 3 | `#f5f3ff` | `#5b21b6` (purple) |
| 4 | `#fdf2f8` | `#86198f` (pink) |

Header rows use `border-left: 3px solid <accent>` matching the mockup in option A.

### Group header CSS

Add to the existing `<style>` block (or inline):

```css
.search-group-header td {
  font-weight: 700;
  font-size: 12px;
  padding: 5px 10px;
  border-left: 3px solid;
}
.search-group-color-0 td { background: #eff6ff; color: #1d4ed8; border-left-color: #3b82f6; }
.search-group-color-1 td { background: #f0fdf4; color: #166534; border-left-color: #22c55e; }
.search-group-color-2 td { background: #fff7ed; color: #9a3412; border-left-color: #f97316; }
.search-group-color-3 td { background: #f5f3ff; color: #5b21b6; border-left-color: #8b5cf6; }
.search-group-color-4 td { background: #fdf2f8; color: #86198f; border-left-color: #d946ef; }
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Term has 0 results | Group header still shown with "0 条结果"; no data rows; "— 无结果 —" placeholder |
| >5 terms entered | Silently use first 5 terms; no error shown |
| 1 term with comma (e.g. `"104,"`) | `split_terms` strips empties → single term → existing flat behavior |
| Same term entered twice | Each occurrence runs its own query and gets its own group block |

## What Does Not Change

- URL structure and query param (`?q=...`) — unchanged
- Search input box — unchanged; no "add another search" button needed
- Pagination — if currently present, it applies to the flat seqs list; in grouped mode, all results are shown without pagination (groups are inherently small since users are searching for specific IDs)
- Column set, sorting, coloring of sequence tokens — all unchanged
- Single-term search — identical to current behavior
