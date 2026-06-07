# Multi-Term Grouped Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a user searches for 2–5 comma-separated terms in `seq_list`, display results in separate color-coded blocks per term instead of a flat merged list.

**Architecture:** Add a `_filter_delivery_qs_by_term` helper that runs the existing single-term filter logic per term and expands to full duplex pairs. The `seq_list` view detects multi-term mode, builds a `search_term_groups` list, and passes it alongside the existing `sequence_groups`. The template renders group-header rows between term blocks when `search_term_groups` is non-empty; DataTables is skipped in this mode to avoid conflicts with extra header rows.

**Tech Stack:** Django 5.1, Django template language, existing `DeliveryModule` / `build_duplex_groups` / `get_experiment_summary` helpers, vanilla JS (no new libraries).

---

## Files

- Modify: `app01/views.py` (add helper before line 1968, modify `seq_list` block lines 2106–2199)
- Create: `templates/_seq_group_row.html` (extracted duplex-group `<tr>` partial)
- Modify: `templates/seq_list.html` (topbar, table tag, tbody, CSS)

---

## Task 1: Add `_filter_delivery_qs_by_term` helper to `views.py`

**Files:**
- Modify: `app01/views.py` — insert before `def build_duplex_groups` (line 1968)

- [ ] **Step 1: Insert the helper function**

  In `app01/views.py`, insert the following block immediately before the line `def build_duplex_groups(delivery_qs, selected_seq_type):` (currently line 1968):

  ```python
  def _filter_delivery_qs_by_term(base_qs, term):
      """Filter base_qs by a single search term and expand result to full duplex pairs (AS+SS)."""
      q_obj = (
          Q(duplex_id__icontains=term) |
          Q(Target__icontains=term) |
          Q(project__icontains=term) |
          Q(modify_seq__icontains=term) |
          Q(parents__icontains=term) |
          Q(delivery_id__icontains=term) |
          Q(linker_seq__icontains=term)
      )
      matched_qs = base_qs.filter(q_obj)
      if not matched_qs.exists():
          return base_qs.none()
      matched_pairs = matched_qs.values_list('project', 'duplex_id').distinct()
      q_objects = Q()
      for proj, dup_id in matched_pairs:
          q_objects |= Q(project=proj, duplex_id=dup_id)
      return base_qs.filter(q_objects)
  ```

- [ ] **Step 2: Verify the server starts without errors**

  ```bash
  source venv/bin/activate && python manage.py check
  ```
  Expected: `System check identified no issues (0 silenced).`

---

## Task 2: Modify `seq_list` view for multi-term mode

**Files:**
- Modify: `app01/views.py` — the search block starting at line 2106

The goal is to:
1. Compute `terms` and `is_multi_term` right after reading `q`
2. In `if q:`, skip the OR-filter when multi-term (leave `search_qs` as field-filtered base)
3. Skip the `matched_pairs` expansion and "no results" warning when multi-term
4. After the `has_search` block, branch: multi-term builds `search_term_groups`, single-term runs existing logic
5. Add `search_term_groups` and `is_multi_term` to context

- [ ] **Step 1: Replace the search block (lines 2106–2199)**

  Find this exact block in `app01/views.py`:

  ```python
      # === 搜索过滤 ===
      # 全局快速搜索（单框搜索多字段）
      q = request.GET.get('q', '').strip()

      # 高级字段搜索
      SEARCH_FIELD_MAP = {
          'filterSequence':    'duplex_id__icontains',
          'filterNakedSeq':    'sequence__seq__icontains',
          'filter5Delivery':   'delivery5__icontains',
          'filter3Delivery':   'delivery3__icontains',
          'filterTarget':      'Target__icontains',
          'filterProject':     'project__icontains',
          'filterSeqType':     'seq_type__iexact',
          'filterTranscript':  'linker_seq__icontains',
          'filterParents':     'parents__icontains',
          'filterRemarks':     'Remark__icontains',
      }
      field_filters = {k: request.GET.get(k, '').strip() for k in SEARCH_FIELD_MAP}
      # filterSeq 支持多值（列表），每个值之间为 AND 关系（同时包含所有片段）
      filter_seq_list = [v.strip() for v in request.GET.getlist('filterSeq') if v.strip()]
      field_filters['filterSeq'] = filter_seq_list
      has_search = bool(q) or any(field_filters.get(k) for k in SEARCH_FIELD_MAP) or bool(filter_seq_list)

      if has_search:
          search_qs = delivery_qs

          if q:
              terms = split_terms(q)
              if terms:
                  q_obj = Q()
                  for term in terms:
                      q_obj |= (
                          Q(duplex_id__icontains=term) |
                          Q(Target__icontains=term) |
                          Q(project__icontains=term) |
                          Q(modify_seq__icontains=term) |
                          Q(parents__icontains=term) |
                          Q(delivery_id__icontains=term) |
                          Q(linker_seq__icontains=term)
                      )
                  search_qs = search_qs.filter(q_obj)

          for form_key, lookup in SEARCH_FIELD_MAP.items():
              search_qs = apply_or_terms(search_qs, lookup, field_filters.get(form_key))

          # Modify Sequence 多值 AND 过滤：每个值单独 .filter()，要求同时包含所有片段
          # 构建正则 token[os-]*token[os-]*... 以匹配任意骨架连接符（o/s/-）
          # 同时搜索 modify_seq 和 linker_seq
          for val in filter_seq_list:
              pattern = build_seq_search_regex(val)
              if pattern:
                  search_qs = search_qs.filter(
                      Q(modify_seq__iregex=pattern) | Q(linker_seq__iregex=pattern)
                  )

          if not search_qs.exists():
              messages.warning(request, '没有搜索到指定内容')
              delivery_qs = Delivery.objects.none()
          else:
              # 展开到完整的 duplex 对（保证 AS+SS 同时显示）
              matched_pairs = search_qs.values_list('project', 'duplex_id').distinct()
              q_objects = Q()
              for proj, dup_id in matched_pairs:
                  q_objects |= Q(project=proj, duplex_id=dup_id)
              delivery_qs = delivery_qs.filter(q_objects)
              # 若用户指定了 Seq Type，展开后重新收窄，只显示匹配的链型
              if field_filters.get('filterSeqType'):
                  delivery_qs = delivery_qs.filter(seq_type__iexact=field_filters['filterSeqType'])

      sequence_groups = build_duplex_groups(delivery_qs, selected_seq_type)

      # Attach experiment summary to each group
      all_duplex_ids = []
      for group in sequence_groups:
          did = group.get('duplex_id')
          if did:
              all_duplex_ids.append(did)
      all_duplex_ids = list(set(all_duplex_ids))
      exp_summary_map = get_experiment_summary(all_duplex_ids)
      for group in sequence_groups:
          group['exp_summary'] = exp_summary_map.get(group.get('duplex_id'), '')

      context = {
          'user_type': user_type,
          'sequence_groups': sequence_groups,
          'selected_seq_type': selected_seq_type,
          'allowed_projects': allowed_projects,
          'selected_projects': selected_projects,
          'search_q': q,
          'field_filters': field_filters,
          'has_search': has_search,
      }

      return render(request, 'seq_list.html', context)
  ```

  Replace it with:

  ```python
      # === 搜索过滤 ===
      # 全局快速搜索（单框搜索多字段）
      q = request.GET.get('q', '').strip()
      terms = split_terms(q)[:5] if q else []
      is_multi_term = len(terms) > 1

      # 高级字段搜索
      SEARCH_FIELD_MAP = {
          'filterSequence':    'duplex_id__icontains',
          'filterNakedSeq':    'sequence__seq__icontains',
          'filter5Delivery':   'delivery5__icontains',
          'filter3Delivery':   'delivery3__icontains',
          'filterTarget':      'Target__icontains',
          'filterProject':     'project__icontains',
          'filterSeqType':     'seq_type__iexact',
          'filterTranscript':  'linker_seq__icontains',
          'filterParents':     'parents__icontains',
          'filterRemarks':     'Remark__icontains',
      }
      field_filters = {k: request.GET.get(k, '').strip() for k in SEARCH_FIELD_MAP}
      # filterSeq 支持多值（列表），每个值之间为 AND 关系（同时包含所有片段）
      filter_seq_list = [v.strip() for v in request.GET.getlist('filterSeq') if v.strip()]
      field_filters['filterSeq'] = filter_seq_list
      has_search = bool(q) or any(field_filters.get(k) for k in SEARCH_FIELD_MAP) or bool(filter_seq_list)

      if has_search:
          search_qs = delivery_qs

          if q and not is_multi_term:
              if terms:
                  q_obj = Q()
                  for term in terms:
                      q_obj |= (
                          Q(duplex_id__icontains=term) |
                          Q(Target__icontains=term) |
                          Q(project__icontains=term) |
                          Q(modify_seq__icontains=term) |
                          Q(parents__icontains=term) |
                          Q(delivery_id__icontains=term) |
                          Q(linker_seq__icontains=term)
                      )
                  search_qs = search_qs.filter(q_obj)

          for form_key, lookup in SEARCH_FIELD_MAP.items():
              search_qs = apply_or_terms(search_qs, lookup, field_filters.get(form_key))

          # Modify Sequence 多值 AND 过滤：每个值单独 .filter()，要求同时包含所有片段
          # 构建正则 token[os-]*token[os-]*... 以匹配任意骨架连接符（o/s/-）
          # 同时搜索 modify_seq 和 linker_seq
          for val in filter_seq_list:
              pattern = build_seq_search_regex(val)
              if pattern:
                  search_qs = search_qs.filter(
                      Q(modify_seq__iregex=pattern) | Q(linker_seq__iregex=pattern)
                  )

          if not is_multi_term:
              if not search_qs.exists():
                  messages.warning(request, '没有搜索到指定内容')
                  delivery_qs = Delivery.objects.none()
              else:
                  # 展开到完整的 duplex 对（保证 AS+SS 同时显示）
                  matched_pairs = search_qs.values_list('project', 'duplex_id').distinct()
                  q_objects = Q()
                  for proj, dup_id in matched_pairs:
                      q_objects |= Q(project=proj, duplex_id=dup_id)
                  delivery_qs = delivery_qs.filter(q_objects)
                  # 若用户指定了 Seq Type，展开后重新收窄，只显示匹配的链型
                  if field_filters.get('filterSeqType'):
                      delivery_qs = delivery_qs.filter(seq_type__iexact=field_filters['filterSeqType'])

      if is_multi_term:
          search_term_groups = []
          base_qs = search_qs  # field-filtered base; q-filter applied per term below
          for i, term in enumerate(terms):
              term_qs = _filter_delivery_qs_by_term(base_qs, term)
              term_seq_groups = build_duplex_groups(term_qs, selected_seq_type)
              duplex_ids = list({g['duplex_id'] for g in term_seq_groups if g.get('duplex_id')})
              term_exp_map = get_experiment_summary(duplex_ids)
              for g in term_seq_groups:
                  g['exp_summary'] = term_exp_map.get(g.get('duplex_id'), '')
              search_term_groups.append({
                  'term': term,
                  'sequence_groups': term_seq_groups,
                  'color_idx': i,
              })
          sequence_groups = []
      else:
          search_term_groups = []
          sequence_groups = build_duplex_groups(delivery_qs, selected_seq_type)
          all_duplex_ids = list({g['duplex_id'] for g in sequence_groups if g.get('duplex_id')})
          exp_summary_map = get_experiment_summary(all_duplex_ids)
          for group in sequence_groups:
              group['exp_summary'] = exp_summary_map.get(group.get('duplex_id'), '')

      context = {
          'user_type': user_type,
          'sequence_groups': sequence_groups,
          'search_term_groups': search_term_groups,
          'is_multi_term': is_multi_term,
          'selected_seq_type': selected_seq_type,
          'allowed_projects': allowed_projects,
          'selected_projects': selected_projects,
          'search_q': q,
          'field_filters': field_filters,
          'has_search': has_search,
      }

      return render(request, 'seq_list.html', context)
  ```

- [ ] **Step 2: Verify no Python errors**

  ```bash
  source venv/bin/activate && python manage.py check
  ```
  Expected: `System check identified no issues (0 silenced).`

---

## Task 3: Extract group row to a partial template

**Files:**
- Create: `templates/_seq_group_row.html`
- Modify: `templates/seq_list.html` (lines 205–418)

The group rendering `<tr>` block (currently lines 207–417 in `seq_list.html`) will be moved to a partial so it can be reused inside both single-term and multi-term loops without duplication.

- [ ] **Step 1: Create `templates/_seq_group_row.html`**

  Copy the content from `{% for group in sequence_groups %}` ... `{% endfor %}` in `seq_list.html` (the inner `<tr>...</tr>` block, lines 207–417) into a new file `templates/_seq_group_row.html`:

  ```html
  {# Renders one duplex-group row. Requires: group, selected_seq_type, user_type, request #}
  <tr data-rm-code="{{ group.items.0.rm_code }}"
      data-delivery-id="{{ group.items.0.deliveries.0.id }}"
      data-strand-mws="{{ group.items.0.deliveries.0.Strand_MWs }}"
      data-seq-type="{{ group.items.0.deliveries.0.Seq_type }}">
    <td><input type="checkbox" class="row-checkbox"></td>
    <td>
      {% for d in group.items.0.deliveries %}
        {{ d.duplex_id|default_if_none:'' }}
      {% endfor %}
    </td>
    <td>{{ group.items.0.Project }}</td>
    <td>
      {% for d in group.items.0.deliveries %}
        {{ d.Target|default_if_none:'' }}
      {% endfor %}
    </td>
    <td>
      {% for d in group.items.0.deliveries %}
        {{ d.Seq_type|default_if_none:'' }}_{{ d.delivery_id|default_if_none:'' }}<br>
      {% endfor %}
      {% if group.items.1 %}
        {% for d in group.items.1.deliveries %}
          {{ d.Seq_type|default_if_none:'' }}_{{ d.delivery_id|default_if_none:'' }}<br>
        {% endfor %}
      {% endif %}
    </td>
    <td>
      <div class="delivery-container" style="justify-content:flex-end;">
        {% for d in group.items.0.deliveries %}
          {% if selected_seq_type == "SS" %}
            {% with d.delivery3_colored as delivery_colored %}
            {% include "char_block_SS.html" %}
            {% endwith %}
          {% else %}
            {% with d.delivery5_colored as delivery_colored %}
            {% include "char_block_SS.html" %}
            {% endwith %}
          {% endif %}
        {% endfor %}
      </div>
      {% if group.items.1 %}
      <div class="delivery-container" style="justify-content:flex-end;">
        {% for d in group.items.1.deliveries %}
          {% if selected_seq_type == "SS" %}
            {% with d.delivery5_colored as delivery_colored %}
            {% include "char_block_AS.html" %}
            {% endwith %}
          {% else %}
            {% with d.delivery3_colored as delivery_colored %}
            {% include "char_block_AS.html" %}
            {% endwith %}
          {% endif %}
        {% endfor %}
      </div>
      {% endif %}
    </td>
    <td style="padding:4px 2px;vertical-align:middle;">
      {% if group.aligned_columns %}
      <table class="nested-align-table">
        <tr>
          <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}SS 3'{% else %}SS 5'{% endif %}</td>
          {% for col in group.aligned_columns %}
            {% if col.col_type == 'linker' %}
              <td style="vertical-align:bottom;padding:0;">
                <div style="display:flex;flex-direction:column;align-items:center;">
                  <span class="seq-count" style="width:auto;">&nbsp;</span>
                  <span class="seq-delivery-placeholder">&nbsp;</span>
                  {% if col.row0 %}<span class="seq-container seq-narrow" style="background-color:{% if col.row0.char == 's' %}rgb(253,246,61){% else %}rgb(198,196,198){% endif %};">{{ col.row0.char }}</span>{% else %}<span class="seq-container seq-narrow" style="visibility:hidden;">s</span>{% endif %}
                </div>
              </td>
            {% else %}
              <td style="vertical-align:bottom;padding:0;">
                <div style="display:flex;flex-direction:column;align-items:center;">
                  {% if col.row0 %}
                    <span class="seq-count" style="width:auto;">{% if col.row0.count %} {{ col.row0.count }} {% else %}&nbsp;{% endif %}</span>
                    {% if col.row0.is_combo %}<span class="seq-delivery-label" style="background-color:{{ col.row0.delivery_color }};">{{ col.row0.delivery_label }}</span>{% else %}<span class="seq-delivery-placeholder">&nbsp;</span>{% endif %}
                    <span class="seq-container seq-wide" style="background-color:{% if col.row0.type == 'normal' %}rgb(189,199,248){% elif col.row0.type == 'f' %}rgb(22,245,22){% elif col.row0.type == 'm' %}rgb(68,68,68);color:white{% elif col.row0.type == 'd' %}rgb(212,93,245){% elif col.row0.type == 's' %}rgb(253,246,61){% elif col.row0.type == 'o' %}rgb(198,196,198){% elif col.row0.type == 'ss' or col.row0.type == 'moe' or col.row0.type == 'OCF3' or col.row0.type == 'GNA' or col.row0.type == 'I' %}rgb(212,93,245){% elif col.row0.type == 'TNA' %}rgb(245,86,86);color:white{% elif col.row0.type == 'unknown' %}rgb(163,163,163){% elif col.row0.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ col.row0.char }}</span>
                  {% else %}
                    <span class="seq-count" style="width:auto;">&nbsp;</span>
                    <span class="seq-delivery-placeholder">&nbsp;</span>
                    <span class="seq-container seq-wide" style="visibility:hidden;">A</span>
                  {% endif %}
                </div>
              </td>
            {% endif %}
          {% endfor %}
          <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}5'{% else %}3'{% endif %}</td>
        </tr>
        <tr class="ss-align-row">
          <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}AS 5'{% else %}AS 3'{% endif %}</td>
          {% for col in group.aligned_columns %}
            {% if col.col_type == 'linker' %}
              <td style="vertical-align:top;padding:0;">
                <div style="display:flex;flex-direction:column;align-items:center;">
                  <span class="seq-delivery-placeholder">&nbsp;</span>
                  {% if col.row1 %}<span class="seq-container seq-narrow" style="background-color:{% if col.row1.char == 's' %}rgb(253,246,61){% else %}rgb(198,196,198){% endif %};">{{ col.row1.char }}</span>{% else %}<span class="seq-container seq-narrow" style="visibility:hidden;">s</span>{% endif %}
                  <span class="seq-count" style="width:auto;">&nbsp;</span>
                </div>
              </td>
            {% else %}
              <td style="vertical-align:top;padding:0;">
                <div style="display:flex;flex-direction:column;align-items:center;">
                  {% if col.row1 %}
                    {% if col.row1.is_combo %}<span class="seq-delivery-label" style="background-color:{{ col.row1.delivery_color }};">{{ col.row1.delivery_label }}</span>{% else %}<span class="seq-delivery-placeholder">&nbsp;</span>{% endif %}
                    <span class="seq-container seq-wide" style="background-color:{% if col.row1.type == 'normal' %}rgb(189,199,248){% elif col.row1.type == 'f' %}rgb(22,245,22){% elif col.row1.type == 'm' %}rgb(68,68,68);color:white{% elif col.row1.type == 'd' %}rgb(212,93,245){% elif col.row1.type == 's' %}rgb(253,246,61){% elif col.row1.type == 'o' %}rgb(198,196,198){% elif col.row1.type == 'ss' or col.row1.type == 'moe' or col.row1.type == 'OCF3' or col.row1.type == 'GNA' or col.row1.type == 'I' %}rgb(212,93,245){% elif col.row1.type == 'TNA' %}rgb(245,86,86);color:white{% elif col.row1.type == 'unknown' %}rgb(163,163,163){% elif col.row1.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ col.row1.char }}</span>
                    <span class="seq-count" style="width:auto;">{% if col.row1.count %} {{ col.row1.count }} {% else %}&nbsp;{% endif %}</span>
                  {% else %}
                    <span class="seq-delivery-placeholder">&nbsp;</span>
                    <span class="seq-container seq-wide" style="visibility:hidden;">A</span>
                    <span class="seq-count" style="width:auto;">&nbsp;</span>
                  {% endif %}
                </div>
              </td>
            {% endif %}
          {% endfor %}
          <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}3'{% else %}5'{% endif %}</td>
        </tr>
      </table>
      {% else %}
      <div style="display:flex;gap:0;">
        {% for item in group.items.0.modify_seq_colored %}
          <span class="seq-container {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}seq-narrow{% else %}seq-wide{% endif %}" style="background-color:{% if item.type == 'normal' %}rgb(189,199,248){% elif item.type == 'f' %}rgb(22,245,22){% elif item.type == 'm' %}rgb(68,68,68);color:white{% elif item.type == 'd' or item.type == 'ss' or item.type == 'moe' or item.type == 'OCF3' or item.type == 'GNA' or item.type == 'I' %}rgb(212,93,245){% elif item.type == 's' %}rgb(253,246,61){% elif item.type == 'o' %}rgb(198,196,198){% elif item.type == 'TNA' %}rgb(245,86,86);color:white{% elif item.type == 'unknown' %}rgb(163,163,163){% elif item.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ item.char }}</span>
        {% endfor %}
      </div>
      {% endif %}
    </td>
    <td>
      <div class="delivery-container" style="justify-content:flex-start;">
        {% for d in group.items.0.deliveries %}
          {% if selected_seq_type == "SS" %}
            {% with d.delivery5_colored as delivery_colored %}
            {% include "char_block_SS.html" %}
            {% endwith %}
          {% else %}
            {% with d.delivery3_colored as delivery_colored %}
            {% include "char_block_SS.html" %}
            {% endwith %}
          {% endif %}
        {% endfor %}
      </div>
      {% if group.items.1 %}
      <div class="delivery-container" style="justify-content:flex-start;">
        {% for d in group.items.1.deliveries %}
          {% if selected_seq_type == "SS" %}
            {% with d.delivery3_colored as delivery_colored %}
            {% include "char_block_AS.html" %}
            {% endwith %}
          {% else %}
            {% with d.delivery5_colored as delivery_colored %}
            {% include "char_block_AS.html" %}
            {% endwith %}
          {% endif %}
        {% endfor %}
      </div>
      {% endif %}
    </td>
    <td>{{ group.items.0.Transcript|default_if_none:'' }}</td>
    <td>{{ group.items.0.Pos|default_if_none:'' }}</td>
    <td>
      {% for d in group.items.0.deliveries %}
        {{ d.Strand_MWs|default_if_none:'' }}
      {% endfor %}
      {% if group.items.1 %}
        {% for d in group.items.1.deliveries %}
          <br>{{ d.Strand_MWs|default_if_none:'' }}
        {% endfor %}
      {% endif %}
    </td>
    <td>
      {% for d in group.items.0.deliveries %}
        {{ d.Parents|default_if_none:'' }}
      {% endfor %}
      {% if group.items.1 %}
        {% for d in group.items.1.deliveries %}
          <br>{{ d.Parents|default_if_none:'' }}
        {% endfor %}
      {% endif %}
    </td>
    <td>
      {{ group.items.0.Remark|linebreaksbr|default_if_none:'' }}
      {% if group.items.1 and group.items.1.Remark %}
        <br>{{ group.items.1.Remark|linebreaksbr }}
      {% endif %}
    </td>
    <td>
      {{ group.items.0.formatted_update_time|default_if_none:'' }}
      {% if group.items.1 and group.items.1.formatted_update_time %}
        <br>{{ group.items.1.formatted_update_time }}
      {% endif %}
    </td>
    <td>
      {% if group.exp_summary %}
        <a href="{% url 'experiment_detail' duplex_id=group.duplex_id %}" style="font-size:11px;line-height:1.4;color:#0369a1;text-decoration:none;">{{ group.exp_summary }}</a>
      {% else %}
        {% if user_type == 'modify' or user_type == 'project' or user_type == 'data_admin' or user_type == 'admin' or user_type == 'superadmin' or request.user.is_superuser %}
        <a href="{% url 'add_experiment' %}?duplex_id={{ group.duplex_id }}" style="font-size:11px;color:#94a3b8;">+ 添加</a>
        {% else %}
        <span style="color:#e2e8f0;">—</span>
        {% endif %}
      {% endif %}
    </td>
    <td>
      <div class="ds-actions">
        <a class="ds-act ds-act-edit" href="/edit_seq/?id={{ group.items.0.rm_code }}&strand_MWs={{ group.items.0.deliveries.0.Strand_MWs }}&next={{ request.get_full_path|urlencode }}">编辑SS</a>
        {% if group.items.1 %}
        <a class="ds-act ds-act-edit" href="/edit_seq/?id={{ group.items.1.rm_code }}&strand_MWs={{ group.items.1.deliveries.0.Strand_MWs }}&next={{ request.get_full_path|urlencode }}">编辑AS</a>
        {% endif %}
        <button class="ds-act ds-act-clone clone-seq-btn" data-strand-id="{{ group.duplex_id }}">克隆序列</button>
      </div>
    </td>
  </tr>
  ```

- [ ] **Step 2: Replace the tbody block in `seq_list.html`**

  In `templates/seq_list.html`, find:

  ```html
        <tbody>
          {% for group in sequence_groups %}
          {# ── First row ── #}
          <tr data-rm-code="{{ group.items.0.rm_code }}"
  ```

  (This starts at the `<tbody>` tag and the entire block ends at `{% endfor %}` before `</tbody>`.)

  Replace the entire `<tbody>...</tbody>` block (lines 204–419) with:

  ```html
        <tbody>
          {% if search_term_groups %}
            {% for term_group in search_term_groups %}
              <tr class="search-group-header search-group-color-{{ term_group.color_idx }}">
                <td colspan="16">▸ "{{ term_group.term }}" 的结果（{{ term_group.sequence_groups|length }} 组）</td>
              </tr>
              {% for group in term_group.sequence_groups %}
                {% include "_seq_group_row.html" %}
              {% endfor %}
              {% if not term_group.sequence_groups %}
                <tr>
                  <td colspan="16" style="text-align:center;padding:10px 8px;color:#94a3b8;font-size:12px;">— 无结果 —</td>
                </tr>
              {% endif %}
            {% endfor %}
          {% else %}
            {% for group in sequence_groups %}
              {% include "_seq_group_row.html" %}
            {% endfor %}
          {% endif %}
        </tbody>
  ```

---

## Task 4: Update `seq_list.html` — topbar, table id, CSS

**Files:**
- Modify: `templates/seq_list.html`

- [ ] **Step 1: Update topbar count badge (lines 7–9)**

  Find:

  ```html
    {% if sequence_groups %}
      <span class="ds-count-badge">{{ sequence_groups|length }}</span>
    {% endif %}
  ```

  Replace with:

  ```html
    {% if search_term_groups %}
      <span class="ds-count-badge">{{ search_term_groups|length }} 词</span>
    {% elif sequence_groups %}
      <span class="ds-count-badge">{{ sequence_groups|length }}</span>
    {% endif %}
  ```

- [ ] **Step 2: Disable DataTables in multi-term mode (line 177)**

  Find:

  ```html
      <table id="example" class="ds-table" style="width:100%">
  ```

  Replace with:

  ```html
      <table {% if not is_multi_term %}id="example"{% endif %} class="ds-table" style="width:100%">
  ```

- [ ] **Step 3: Add group header CSS**

  In `templates/seq_list.html`, find the closing `</style>` tag just before the DataTables script includes (around line 446). Insert before `</style>`:

  ```css
  .search-group-header td { font-weight:700; font-size:12px; padding:6px 10px; border-left:3px solid; }
  .search-group-color-0 td { background:#eff6ff; color:#1d4ed8; border-left-color:#3b82f6; }
  .search-group-color-1 td { background:#f0fdf4; color:#166534; border-left-color:#22c55e; }
  .search-group-color-2 td { background:#fff7ed; color:#9a3412; border-left-color:#f97316; }
  .search-group-color-3 td { background:#f5f3ff; color:#5b21b6; border-left-color:#8b5cf6; }
  .search-group-color-4 td { background:#fdf2f8; color:#86198f; border-left-color:#d946ef; }
  ```

- [ ] **Step 4: Verify `python manage.py check` still passes**

  ```bash
  source venv/bin/activate && python manage.py check
  ```

---

## Task 5: Manual smoke test + commit

- [ ] **Step 1: Start dev server**

  ```bash
  source venv/bin/activate && python manage.py runserver
  ```

- [ ] **Step 2: Single-term search (regression check)**

  Open `http://127.0.0.1:8000/seq_list/?q=BP000104` in the browser.
  - Expected: flat table, DataTables pagination footer visible, no group header rows.

- [ ] **Step 3: Multi-term search (new feature)**

  Open `http://127.0.0.1:8000/seq_list/?q=BP000104,BP000107` in the browser.
  - Expected: two colored group-header rows ("BP000104" blue, "BP000107" green), each followed by their respective duplex rows. No DataTables pagination footer.

- [ ] **Step 4: Empty term in multi-term**

  Open `http://127.0.0.1:8000/seq_list/?q=BP000104,NONEXISTENT999` in the browser.
  - Expected: "BP000104" group has rows; "NONEXISTENT999" group shows "— 无结果 —" placeholder row.

- [ ] **Step 5: Commit**

  ```bash
  git add app01/views.py templates/_seq_group_row.html templates/seq_list.html
  git commit -m "$(cat <<'EOF'
  feat: multi-term grouped search results in seq_list

  Searching 2-5 comma-separated terms now displays results in separate
  color-coded blocks per term instead of a flat merged list. Single-term
  search behavior is unchanged.

  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  EOF
  )"
  ```
