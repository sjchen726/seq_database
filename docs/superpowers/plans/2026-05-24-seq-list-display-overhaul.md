# seq_list 展示页面全面美化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 seq_list 页面中 Ligand 列与 Sequences 列垂直错位、segment_sep token 偏高、char_block 定位逻辑错误等共 11 处布局与样式问题。

**Architecture:** 将原来三个独立外层 td（Ligand 1 / Sequences / Ligand 2）合并为单个 td，内部使用统一嵌套表（`nested-align-table`），SS 行和 AS 行各含 Ligand 列与 Sequence 列，浏览器 table 布局天然同步行高。char_block 模板简化为纯水平 token 排列，垂直定位由 td 的 `vertical-align` 属性负责。

**Tech Stack:** Django 5.1 templates, vanilla CSS (无框架), jQuery + DataTables 1.x

---

## 文件修改总览

| 文件 | 操作 |
|------|------|
| `static/css/styles.css` | 新增：delivery-item override、ligand-col 样式、hide-ligand CSS class、seq-count line-height 修复 |
| `templates/char_block_SS.html` | 重写：去掉 flex-column 包装，只保留 token span 水平排列 |
| `templates/char_block_AS.html` | 重写：同 char_block_SS，两者结构统一 |
| `templates/_seq_group_row.html` | 核心重构：移除 Ligand 1/2 外层 td，Sequences td 内改用统一嵌套表，修复 segment_sep 结构，统一单链回退 |
| `templates/seq_list.html` | 移除 2 个 `<th>`，更新所有 `data-column` 值（原 8-15 → 6-13），更新 Ligand checkbox |
| `static/js/tables.js` | 新增 `.toggle-ligand` handler，更新 `columnDefs` indices |

---

## Task 1：CSS 基础新增

> 这一步纯增量，不改变任何已有样式，改完页面外观无变化。

**Files:**
- Modify: `static/css/styles.css`（在文件末尾，design-system override 区块之后追加）

- [ ] **Step 1：在 styles.css 末尾追加以下 CSS 规则**

在文件最后找到末尾，追加：

```css
/* ══════════════════════════════════════════════════════════
   seq-list 展示美化 2026-05-24
   ══════════════════════════════════════════════════════════ */

/* ① delivery-item 统一化：覆盖旧 inline-block 残留规则 */
.delivery-item {
  display: inline-flex !important;
  vertical-align: baseline !important;
  min-width: 22px !important;
  align-items: center !important;
  justify-content: center !important;
}

/* ② nested 嵌套表内 seq-count 行高固定为 1.3（设计意图），覆盖全局 1.4 */
.nested-align-table .seq-count {
  line-height: 1.3 !important;
}

/* ③ Ligand 列：在统一嵌套表中的内列样式 */
.ligand-col-l,
.ligand-col-r {
  white-space: nowrap;
  padding: 0 4px !important;
}

/* ④ Ligand 列之间的视觉分隔线 */
.ligand-seq-sep {
  width: 4px;
  min-width: 4px;
  padding: 0 !important;
  border-left: 1px dashed #e2e8f0;
}

/* ⑤ 列切换 CSS class — body 上挂 hide-ligand-l / hide-ligand-r */
.hide-ligand-l .ligand-col-l { display: none !important; }
.hide-ligand-r .ligand-col-r { display: none !important; }
.hide-ligand-l .ligand-seq-sep:first-of-type { display: none !important; }
.hide-ligand-r .ligand-seq-sep:last-of-type  { display: none !important; }
```

- [ ] **Step 2：验证无视觉变化**

启动开发服务器（若未运行）：
```bash
source venv/bin/activate
python manage.py runserver
```

打开 http://127.0.0.1:8000/seq_list/，确认页面外观与修改前一致（这些 class 目前没有元素使用）。

- [ ] **Step 3：Commit**

```bash
git add static/css/styles.css
git commit -m "style: add CSS foundations for unified strand display overhaul"
```

---

## Task 2：简化 char_block 模板

> char_block_SS 和 char_block_AS 去掉垂直定位技巧，只做水平 token 排列。
> 垂直对齐交给外层 td 的 `vertical-align:bottom/top`。
> **注意**：此步改完后页面 Ligand 列会暂时显示异常（flex-column 包装消失），
> 需要紧接 Task 3 完成后才恢复正常。

**Files:**
- Modify: `templates/char_block_SS.html`
- Modify: `templates/char_block_AS.html`

- [ ] **Step 1：完整替换 char_block_SS.html**

用以下内容完整替换 `templates/char_block_SS.html`（16 行 → 9 行）：

```html
{% for char_item in delivery_colored %}
  <span class="delivery-item"
        style="{% if char_item.type == 'unknown' %}color:black;background-color:transparent;{% else %}background-color:{{ char_item.color }};{% if char_item.type == 's' %}color:black;{% endif %}{% endif %}">
    {{ char_item.char }}
  </span>
{% endfor %}
```

- [ ] **Step 2：完整替换 char_block_AS.html**

用以下内容完整替换 `templates/char_block_AS.html`（20 行 → 9 行）：

```html
{% for char_item in delivery_colored %}
  <span class="delivery-item"
        style="{% if char_item.type == 'unknown' %}color:black;background-color:transparent;{% else %}background-color:{{ char_item.color }};{% if char_item.type == 's' %}color:black;{% endif %}{% endif %}">
    {{ char_item.char }}
  </span>
{% endfor %}
```

- [ ] **Step 3：不单独提交（与 Task 3 合并提交）**

继续执行 Task 3。

---

## Task 3：核心重构 _seq_group_row.html

> 这是最大的改动。移除两个独立 Ligand td，把所有内容合并进 Sequences td 内的统一嵌套表。
> 同时修复 segment_sep 结构（②）和单链回退（④）。

**Files:**
- Modify: `templates/_seq_group_row.html`

- [ ] **Step 1：完整替换 `_seq_group_row.html`**

用以下内容完整替换整个文件（注意：原来有 3 个 td 对应 Ligand1/Sequences/Ligand2，现在合并为 1 个 td）：

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

          {# ── 统一展示列：Ligand 1 + Sequences + Ligand 2 合并为单 td ── #}
          <td style="padding:4px 2px;vertical-align:middle;">
            <table class="nested-align-table">

              {# ── SS 行 ── #}
              <tr>
                <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}SS 3'{% else %}SS 5'{% endif %}</td>

                {# Ligand 1 SS #}
                <td class="ligand-col-l" style="vertical-align:bottom;">
                  <div class="delivery-container" style="justify-content:flex-end;">
                    {% for d in group.items.0.deliveries %}
                      {% if selected_seq_type == "SS" %}
                        {% with d.delivery3_colored as delivery_colored %}{% include "char_block_SS.html" %}{% endwith %}
                      {% else %}
                        {% with d.delivery5_colored as delivery_colored %}{% include "char_block_SS.html" %}{% endwith %}
                      {% endif %}
                    {% endfor %}
                  </div>
                </td>

                <td class="ligand-seq-sep"></td>

                {# Sequence 列 #}
                {% if group.aligned_columns %}
                  {% for col in group.aligned_columns %}
                    {% if col.col_type == 'segment_sep' %}
                      <td class="seq-segment-sep-col" style="vertical-align:bottom;">
                        <div style="display:flex;flex-direction:column;align-items:center;">
                          <span class="seq-count" style="visibility:hidden;">0</span>
                          <div style="display:flex;flex-direction:row;flex-wrap:nowrap;gap:0;">
                            {% for lk in col.linker_tokens %}
                              <span class="seq-container seq-wide" style="background-color:rgba(112,203,248,1);">{{ lk.char }}</span>
                            {% endfor %}
                          </div>
                        </div>
                      </td>
                    {% elif col.col_type == 'linker' %}
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
                {% else %}
                  {# 单链回退：无 aligned_columns，直接平铺 modify_seq_colored #}
                  <td style="vertical-align:middle;padding:0;">
                    <div style="display:flex;gap:0;align-items:center;">
                      {% for item in group.items.0.modify_seq_colored %}
                        {% if item.type == 'SEP' %}
                          <span class="seq-seg-divider">&#124;</span>
                        {% elif item.type == 'LINKER_DASH' %}
                          <span class="seq-linker-dash">{{ item.char }}</span>
                        {% else %}
                          <span class="seq-container {% if item.char == 's' or item.char == 'o' or item.char == 'ss' %}seq-narrow{% else %}seq-wide{% endif %}" style="background-color:{% if item.type == 'normal' %}rgb(189,199,248){% elif item.type == 'f' %}rgb(22,245,22){% elif item.type == 'm' %}rgb(68,68,68);color:white{% elif item.type == 'd' or item.type == 'ss' or item.type == 'moe' or item.type == 'OCF3' or item.type == 'GNA' or item.type == 'I' %}rgb(212,93,245){% elif item.type == 's' %}rgb(253,246,61){% elif item.type == 'o' %}rgb(198,196,198){% elif item.type == 'TNA' %}rgb(245,86,86);color:white{% elif item.type == 'unknown' %}rgb(163,163,163){% elif item.type == 'others' %}rgba(112,203,248,1){% endif %};">{{ item.char }}</span>
                        {% endif %}
                      {% endfor %}
                    </div>
                  </td>
                {% endif %}

                <td class="ligand-seq-sep"></td>

                {# Ligand 2 SS #}
                <td class="ligand-col-r" style="vertical-align:bottom;">
                  <div class="delivery-container" style="justify-content:flex-start;">
                    {% for d in group.items.0.deliveries %}
                      {% if selected_seq_type == "SS" %}
                        {% with d.delivery5_colored as delivery_colored %}{% include "char_block_SS.html" %}{% endwith %}
                      {% else %}
                        {% with d.delivery3_colored as delivery_colored %}{% include "char_block_SS.html" %}{% endwith %}
                      {% endif %}
                    {% endfor %}
                  </div>
                </td>

                <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}5'{% else %}3'{% endif %}</td>
              </tr>

              {# ── AS 行（仅 duplex 时渲染） ── #}
              {% if group.items.1 %}
              <tr class="ss-align-row">
                <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}AS 5'{% else %}AS 3'{% endif %}</td>

                {# Ligand 1 AS #}
                <td class="ligand-col-l" style="vertical-align:top;">
                  <div class="delivery-container" style="justify-content:flex-end;">
                    {% for d in group.items.1.deliveries %}
                      {% if selected_seq_type == "SS" %}
                        {% with d.delivery5_colored as delivery_colored %}{% include "char_block_AS.html" %}{% endwith %}
                      {% else %}
                        {% with d.delivery3_colored as delivery_colored %}{% include "char_block_AS.html" %}{% endwith %}
                      {% endif %}
                    {% endfor %}
                  </div>
                </td>

                <td class="ligand-seq-sep"></td>

                {# Sequence 列 AS 行 #}
                {% for col in group.aligned_columns %}
                  {% if col.col_type == 'segment_sep' %}
                    {# 等宽占位 — 内容在 SS 行已渲染；下方隐藏 seq-count 充当底部锚点 #}
                    <td class="seq-segment-sep-col" style="vertical-align:top;">
                      <div style="display:flex;flex-direction:column;align-items:center;">
                        <span style="visibility:hidden;display:block;height:1px;"></span>
                        <span class="seq-count" style="visibility:hidden;">0</span>
                      </div>
                    </td>
                  {% elif col.col_type == 'linker' %}
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

                <td class="ligand-seq-sep"></td>

                {# Ligand 2 AS #}
                <td class="ligand-col-r" style="vertical-align:top;">
                  <div class="delivery-container" style="justify-content:flex-start;">
                    {% for d in group.items.1.deliveries %}
                      {% if selected_seq_type == "SS" %}
                        {% with d.delivery3_colored as delivery_colored %}{% include "char_block_AS.html" %}{% endwith %}
                      {% else %}
                        {% with d.delivery5_colored as delivery_colored %}{% include "char_block_AS.html" %}{% endwith %}
                      {% endif %}
                    {% endfor %}
                  </div>
                </td>

                <td class="align-dir-cell">{% if selected_seq_type == 'SS' %}3'{% else %}5'{% endif %}</td>
              </tr>
              {% endif %}{# end group.items.1 #}

            </table>
          </td>
          {# ── 统一展示列结束 ── #}

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
          <td>{{ group.latest_update_time|default_if_none:'' }}</td>
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

- [ ] **Step 2：在浏览器中验证基本渲染**

打开 http://127.0.0.1:8000/seq_list/ ，检查：
- [ ] BP000013：Vp 与 AS 序列行垂直对齐（不再偏高）
- [ ] BP000016：LK1-L96-LK1 与序列字符底边对齐
- [ ] 单链序列（无 AS 的行）：序列正常显示，无报错
- [ ] 方向标签（SS 3' / AS 5' 等）正常显示
- [ ] Ligand 2（右侧）正常显示

注意：此时列数还未更新（seq_list.html 的 th 还有 Ligand 1/2 独立列），DataTables 列计数可能报 warning，忽略即可，Task 4 会修复。

- [ ] **Step 3：提交 Task 2 + Task 3 变更**

```bash
git add templates/char_block_SS.html templates/char_block_AS.html templates/_seq_group_row.html
git commit -m "refactor: unify Ligand+Sequences into single nested table, fix segment_sep anchor, simplify char_block templates"
```

---

## Task 4：更新 seq_list.html（表头 + 列控件）

> 移除外层表的 Ligand 1 / Ligand 2 独立 `<th>`，更新列控件 checkbox 的 data-column 值。

**Files:**
- Modify: `templates/seq_list.html`

- [ ] **Step 1：更新表头 `<thead>` — 移除 Ligand 1 / Ligand 2 th**

找到以下内容（原文件约 187-195 行）：
```html
          <th>Ligand 1</th>
          <th style="text-align:center;">
            Sequences<br>
            <select id="seq_type_selector" class="ds-seq-type-selector">
              <option value="SS" {% if selected_seq_type == 'SS' %}selected{% endif %}>AS: 5'-3'; SS: 3'-5'</option>
              <option value="AS" {% if selected_seq_type == 'AS' %}selected{% endif %}>SS: 5'-3'; AS: 3'-5'</option>
            </select>
          </th>
          <th>Ligand 2</th>
```

替换为（只保留 Sequences th，去掉 Ligand 1 / Ligand 2）：
```html
          <th style="text-align:center;">
            Sequences<br>
            <select id="seq_type_selector" class="ds-seq-type-selector">
              <option value="SS" {% if selected_seq_type == 'SS' %}selected{% endif %}>AS: 5'-3'; SS: 3'-5'</option>
              <option value="AS" {% if selected_seq_type == 'AS' %}selected{% endif %}>SS: 5'-3'; AS: 3'-5'</option>
            </select>
          </th>
```

- [ ] **Step 2：更新列控件 checkbox（`#column-controls` 区块）**

找到原有的 `#column-controls` div 中的所有 checkbox label，完整替换为以下内容（注意 data-column 从原来 8-15 下移到 6-13，Ligand 1/2 改用 toggle-ligand class）：

```html
  <div id="column-controls" style="display:flex;flex-wrap:wrap;gap:8px;font-size:12px;">
    <label><input type="checkbox" class="toggle-vis export-field" data-column="1" value="duplex_id" checked> Strand ID</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="2" value="project" checked> Project</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="3" value="Target" checked> Target</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="4" value="id" checked> Sequence ID</label>
    <label><input type="checkbox" class="toggle-ligand export-field" data-toggle-class="hide-ligand-l" value="delivery5" checked> Ligand 1</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="5" value="modify_seq" checked> Sequences</label>
    <label><input type="checkbox" class="toggle-ligand export-field" data-toggle-class="hide-ligand-r" value="delivery3" checked> Ligand 2</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="6" value="Transcript" checked> Transcript</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="7" value="Pos" checked> Position</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="8" value="Strand_MWs" checked> Strand_MWs</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="9" value="parents" checked> Parents</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="10" value="remarks" checked> Remarks</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="11" value="created_at" checked> Update Time</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="12" value="exp_data" checked> 实验数据</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="13" value="操作" checked> 操作</label>
  </div>
```

- [ ] **Step 3：验证表头列数正确**

刷新 http://127.0.0.1:8000/seq_list/，确认：
- [ ] 表头现在是：checkbox | Strand ID | Project | Target | Sequence ID | Sequences | Transcript | Position | Strand_MWs | Parents | Remarks | Update Time | 实验数据 | 操作（共 14 列）
- [ ] 无 JavaScript 报错（打开浏览器 DevTools Console 检查）

- [ ] **Step 4：Commit**

```bash
git add templates/seq_list.html
git commit -m "feat: merge Ligand columns into unified Sequences td, update column header and toggles"
```

---

## Task 5：更新 tables.js（DataTables 配置 + Ligand toggle handler）

> 修正 columnDefs 中的列索引，新增 `.toggle-ligand` handler。

**Files:**
- Modify: `static/js/tables.js`

- [ ] **Step 1：更新 `columnDefs` 中的 orderable:false 列索引**

找到（约第 23-25 行）：
```js
        columnDefs: [
            { targets: [0, 5, 6, 7, 14, 15], orderable: false },
        ],
```

替换为（原 5/6/7 三个 Ligand/Seq 列合并为 1 个 Seq 列 index 5，原 14→12, 15→13）：
```js
        columnDefs: [
            { targets: [0, 5, 12, 13], orderable: false },
        ],
```

- [ ] **Step 2：在 `.toggle-vis` handler 之后新增 `.toggle-ligand` handler**

找到（约第 111-115 行）：
```js
    // 列显示切换
    $('.toggle-vis').on('change', function() {
        let column = table.column($(this).attr('data-column'));
        column.visible($(this).prop('checked'));
    });
```

在其后追加：
```js
    // Ligand 列内部显隐（CSS class 切换，不走 DataTables column API）
    $('.toggle-ligand').on('change', function() {
        const toggleClass = $(this).data('toggle-class');
        if (toggleClass) {
            $('body').toggleClass(toggleClass, !$(this).prop('checked'));
        }
    });
```

- [ ] **Step 3：验证列切换功能**

刷新页面，打开列控件面板，测试：
- [ ] 取消勾选 "Ligand 1" → Ligand 1 内容消失，序列和 Ligand 2 不受影响
- [ ] 取消勾选 "Ligand 2" → Ligand 2 内容消失，序列和 Ligand 1 不受影响
- [ ] 取消勾选 "Sequences" → 整个合并列（含 Ligand 1/2 内容）消失
- [ ] 取消勾选 "Transcript" / "Position" 等其他列 → 正常隐藏，无列计数错误

- [ ] **Step 4：Commit**

```bash
git add static/js/tables.js
git commit -m "fix: update DataTables columnDefs indices and add toggle-ligand CSS class handler"
```

---

## Task 6：视觉回归验证

> 全面检查所有已知问题是否已修复，无遗漏。

- [ ] **Step 1：打开 seq_list 并验证各项修复**

打开 http://127.0.0.1:8000/seq_list/ ，逐项确认：

| # | 验证项 | 预期结果 |
|---|--------|---------|
| ① | BP000013 AS 行 "Vp" Ligand 位置 | 与 AS 序列字符行垂直对齐（不再偏高） |
| ② | BP000016 "LK1 L96 LK1" token 高度 | 与相邻序列字符底边对齐，不偏高 |
| ③ | Ligand token 宽度 | 单字符 token 最小宽度 22px，与序列字符宽度一致 |
| ④ | 单链序列行（无 AS 链） | SS 序列正常展示，无 AS 空白行 |
| ⑤ | 双链序列 SS/AS 计数数字 | SS 行计数在字符上方，AS 行计数在字符下方 |
| ⑥ | 方向标签 | SS 3' / 5'、AS 5' / 3' 标签居中显示 |
| ⑦ | Ligand 1 / 2 列控件 | 单独切换 L1/L2 显隐，不影响序列列 |
| ⑧ | Sequences 列控件 | 整列（含 Ligand）一并隐藏 |
| ⑨ | 其他列（Transcript, Position 等）排序/隐藏 | 正常 |
| ⑩ | 浏览器 Console | 无 JavaScript 错误 |

- [ ] **Step 2：若发现问题，定点修复并 commit**

常见问题排查：
- Ligand token 颜色丢失 → 检查 char_block_SS/AS 中 `char_item.color` 属性名是否正确
- 单链序列报错 `group.items.0.modify_seq_colored` → 检查 `None` guard
- DataTables 报"column not found" → 检查 task 5 中 columnDefs 的 targets 数组

---

## 最终提交总结

完成所有 task 后，共 4 个主要 commit：
1. `style: add CSS foundations for unified strand display overhaul`
2. `refactor: unify Ligand+Sequences into single nested table, fix segment_sep anchor, simplify char_block templates`
3. `feat: merge Ligand columns into unified Sequences td, update column header and toggles`
4. `fix: update DataTables columnDefs indices and add toggle-ligand CSS class handler`
