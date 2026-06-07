# siRNA 实验数据管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add in vitro and in vivo experimental data management to the siRNA sequence database, linked to duplex_id.

**Architecture:** Three new models (Experiment, DataPoint, ExperimentAttachment) linked to duplex_id string. New views for manual entry, bulk CSV upload (supporting both duplex_id and modify_seq matching), and a detail page. seq_list gets a summary column showing best knockdown %.

**Tech Stack:** Django 5.1, MySQL, pandas (already used), existing ds-* CSS design system, DataTables

---

## Task 1: Configure MEDIA_ROOT and add models

- [ ] Modify `bms/settings.py`: add MEDIA_ROOT and MEDIA_URL after the STATICFILES_DIRS block
- [ ] Modify `bms/urls.py`: import `static` and append media URL serving
- [ ] Add three new models to `app01/models.py` after `DeliveryProject`
- [ ] Run migrations and verify

### 1.1 — `bms/settings.py`

Add these two lines immediately after the `STATICFILES_DIRS` block (after line 126):

```python
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
```

### 1.2 — `bms/urls.py`

Replace the top of the file so it reads:

```python
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view),
    path('login/', views.login_view, name='login'),
    path('signup/', views.register_view, name='signup'),
    path('register/', views.register_view, name='register'),

    path('seq_list/', views.get_sequence_info, name='seq_list'),
    path('reg_seq_list/', views.reg_seq_list, name='reg_seq_list'),

    path('register_seq/', views.register_seq, name='register_seq'),

    path('seq_delivery/', views.upload_delivery_info, name='seq_delivery'),

    path('author_list/', views.author_list, name='author_list'),
    path('add_author/', views.add_author, name='add_author'),
    path('drop_author/', views.drop_author, name='drop_author'),
    path('edit_author/', views.edit_author, name='edit_author'),

    path('edit_seq/', views.edit_seq, name='edit_seq'),
    path('cor_seq/', views.cor_seq, name='cor_seq'),

    path('change_password/', views.change_password, name='change_password'),

    path('edit_reg_seq/', views.edit_reg_seq, name='edit_reg_seq'),

    path('module_list/', views.module_list, name='module_list'),
    path('edit_module/', views.edit_module, name='edit_module'),
    path('upload_modules/', views.upload_modules, name='upload_modules'),
    path('delete_module/', views.delete_module, name='delete_module'),

    path('seqmodule_list/', views.seqmodule_list, name='seqmodule_list'),
    path('edit_seqmodule/', views.edit_seqmodule, name='edit_seqmodule'),
    path('upload_seqmodules/', views.upload_seqmodules, name='upload_seqmodules'),
    path('delete_seqmodule/', views.delete_seqmodule, name='delete_seqmodule'),

    path('search/', views.search, name='search'),
    path('clone_delivery/', views.clone_delivery, name='clone_delivery'),
    path('confirm_share/', views.confirm_share_deliveries, name='confirm_share'),

    path('download_selected/', views.download_selected, name='download_selected'),
    path('blast_seq/', views.blast_seq, name='blast_seq'),
    path('multi_blast/', views.multi_blast, name='multi_blast'),

    # Experiment data
    path('experiment/<str:duplex_id>/', views.experiment_detail, name='experiment_detail'),
    path('experiment/add/', views.add_experiment, name='add_experiment'),
    path('upload_experiment/', views.upload_experiment, name='upload_experiment'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

### 1.3 — `app01/models.py`

Append the following three model classes at the end of the file (after the `SeqModule` class):

```python
class Experiment(models.Model):
    EXP_TYPE_CHOICES = [
        ('in_vitro', '体外 (in vitro)'),
        ('in_vivo',  '体内 (in vivo)'),
    ]
    ASSAY_TYPE_CHOICES = [
        ('single_point',      'Single Point'),
        ('dose_response',     'Dose Response'),
        ('in_vivo_efficacy',  'In Vivo Efficacy'),
        ('pk',                'PK'),
    ]

    duplex_id           = models.CharField('Duplex ID', max_length=24, db_index=True)
    exp_type            = models.CharField('实验类型', max_length=20, choices=EXP_TYPE_CHOICES)
    assay_type          = models.CharField('检测类型', max_length=30, choices=ASSAY_TYPE_CHOICES)
    cell_line           = models.CharField('细胞系', max_length=100, null=True, blank=True)
    animal_species      = models.CharField('动物种属', max_length=100, null=True, blank=True)
    batch               = models.CharField('批次号', max_length=64)
    exp_date            = models.DateField('实验日期', null=True, blank=True)
    transfection_reagent = models.CharField('转染试剂', max_length=100, null=True, blank=True)
    route               = models.CharField('给药途径', max_length=20, null=True, blank=True)
    notes               = models.TextField('备注', null=True, blank=True)
    created_by          = models.CharField('录入人', max_length=64)
    created_at          = models.DateTimeField('录入时间', auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['duplex_id', 'exp_type']),
        ]

    def __str__(self):
        return f"Experiment {self.id} ({self.duplex_id}, {self.exp_type})"


class DataPoint(models.Model):
    CONC_UNIT_CHOICES = [
        ('nM',    'nM'),
        ('uM',    'uM'),
        ('mg_kg', 'mg/kg'),
        ('ug_kg', 'ug/kg'),
    ]
    READOUT_TYPE_CHOICES = [
        ('mRNA_remaining',    'mRNA Remaining (%)'),
        ('protein_remaining', 'Protein Remaining (%)'),
        ('knockdown_pct',     'Knockdown (%)'),
        ('plasma_conc',       'Plasma Concentration'),
        ('tissue_conc',       'Tissue Concentration'),
    ]

    experiment          = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='datapoints')
    concentration_or_dose = models.FloatField('浓度/剂量', null=True, blank=True)
    conc_unit           = models.CharField('浓度单位', max_length=20, choices=CONC_UNIT_CHOICES, blank=True)
    timepoint           = models.CharField('时间点', max_length=32, null=True, blank=True)
    readout_type        = models.CharField('读数类型', max_length=32, choices=READOUT_TYPE_CHOICES)
    value               = models.FloatField('数值')
    value_unit          = models.CharField('单位', max_length=20, null=True, blank=True)
    replicate           = models.CharField('重复信息', max_length=32, null=True, blank=True)

    def __str__(self):
        return f"DataPoint {self.id} (exp={self.experiment_id}, {self.readout_type}={self.value})"


class ExperimentAttachment(models.Model):
    experiment   = models.ForeignKey(Experiment, on_delete=models.CASCADE, related_name='attachments')
    file         = models.FileField('文件', upload_to='exp_attachments/', null=True, blank=True)
    external_url = models.URLField('外部链接', null=True, blank=True)
    label        = models.CharField('描述', max_length=200)

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.file and not self.external_url:
            raise ValidationError('file 和 external_url 至少填写一个。')

    def __str__(self):
        return f"Attachment {self.id} ({self.label})"
```

### 1.4 — Run migrations

```bash
source venv/bin/activate
python manage.py makemigrations app01 --name experiment_models
python manage.py migrate
python manage.py check
```

Expected output: `System check identified no issues (0 silenced).`

---

## Task 2: Add experiment views

- [ ] Add `get_experiment_summary()` helper to `app01/views.py`
- [ ] Add `experiment_detail()` view to `app01/views.py`
- [ ] Add `add_experiment()` view to `app01/views.py`
- [ ] URLs are already wired in Task 1

Append the following block to the end of `app01/views.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Experiment data views
# ─────────────────────────────────────────────────────────────────────────────

def get_experiment_summary(duplex_ids):
    """
    Given a list of duplex_id strings, return a dict mapping each duplex_id
    to a short human-readable summary string for display in seq_list.

    Summary priority:
      - in_vitro: best knockdown_pct or mRNA_remaining (lowest value = best KD)
        shown as "KD XX%@YYnM" (single_point) or "KD XX%@YYnM" (best dose_response point)
      - in_vivo: best knockdown_pct or mRNA_remaining shown as "in vivo XX%@YYmpk"
      - Both present: two lines joined by " / "
      - No data: ""
    """
    from .models import Experiment, DataPoint
    if not duplex_ids:
        return {}

    experiments = (
        Experiment.objects
        .filter(duplex_id__in=duplex_ids)
        .prefetch_related('datapoints')
    )

    # Group experiments by duplex_id
    exp_by_duplex = defaultdict(list)
    for exp in experiments:
        exp_by_duplex[exp.duplex_id].append(exp)

    result = {}
    for duplex_id in duplex_ids:
        exps = exp_by_duplex.get(duplex_id, [])
        if not exps:
            result[duplex_id] = ''
            continue

        vitro_summary = ''
        vivo_summary = ''

        # Collect all datapoints grouped by exp_type
        vitro_points = []
        vivo_points = []
        for exp in exps:
            for dp in exp.datapoints.all():
                if dp.readout_type in ('knockdown_pct', 'mRNA_remaining'):
                    if exp.exp_type == 'in_vitro':
                        vitro_points.append(dp)
                    elif exp.exp_type == 'in_vivo':
                        vivo_points.append(dp)

        # Best in vitro: for knockdown_pct highest value; for mRNA_remaining lowest value
        if vitro_points:
            # Prefer knockdown_pct; fall back to mRNA_remaining converted to KD
            kd_points = [dp for dp in vitro_points if dp.readout_type == 'knockdown_pct']
            mr_points = [dp for dp in vitro_points if dp.readout_type == 'mRNA_remaining']
            if kd_points:
                best = max(kd_points, key=lambda dp: dp.value if dp.value is not None else -999)
                conc_str = f"@{best.concentration_or_dose}{best.conc_unit}" if best.concentration_or_dose is not None else ''
                vitro_summary = f"KD {best.value:.0f}%{conc_str}"
            elif mr_points:
                best = min(mr_points, key=lambda dp: dp.value if dp.value is not None else 9999)
                kd_val = 100 - best.value
                conc_str = f"@{best.concentration_or_dose}{best.conc_unit}" if best.concentration_or_dose is not None else ''
                vitro_summary = f"KD {kd_val:.0f}%{conc_str}"

        # Best in vivo
        if vivo_points:
            kd_points = [dp for dp in vivo_points if dp.readout_type == 'knockdown_pct']
            mr_points = [dp for dp in vivo_points if dp.readout_type == 'mRNA_remaining']
            if kd_points:
                best = max(kd_points, key=lambda dp: dp.value if dp.value is not None else -999)
                dose_str = f"@{best.concentration_or_dose}{best.conc_unit}" if best.concentration_or_dose is not None else ''
                vivo_summary = f"in vivo {best.value:.0f}%{dose_str}"
            elif mr_points:
                best = min(mr_points, key=lambda dp: dp.value if dp.value is not None else 9999)
                kd_val = 100 - best.value
                dose_str = f"@{best.concentration_or_dose}{best.conc_unit}" if best.concentration_or_dose is not None else ''
                vivo_summary = f"in vivo {kd_val:.0f}%{dose_str}"

        parts = [s for s in [vitro_summary, vivo_summary] if s]
        result[duplex_id] = ' / '.join(parts)

    return result


@login_required
def experiment_detail(request, duplex_id):
    """Detail page: all experiments for a given duplex_id, grouped by exp_type."""
    experiments = (
        Experiment.objects
        .filter(duplex_id=duplex_id)
        .prefetch_related('datapoints', 'attachments')
        .order_by('exp_type', '-created_at')
    )

    vitro_exps = [e for e in experiments if e.exp_type == 'in_vitro']
    vivo_exps  = [e for e in experiments if e.exp_type == 'in_vivo']

    can_edit = (
        request.user.is_superuser or
        getattr(request.user, 'user_type', '') in ('data_admin', 'admin', 'superadmin')
    )

    return render(request, 'experiment_detail.html', {
        'duplex_id':  duplex_id,
        'vitro_exps': vitro_exps,
        'vivo_exps':  vivo_exps,
        'can_edit':   can_edit,
    })


@login_required
def add_experiment(request):
    """Manual entry form for a single Experiment + DataPoints + Attachments."""
    if request.method == 'GET':
        duplex_id = request.GET.get('duplex_id', '')
        return render(request, 'add_experiment.html', {
            'duplex_id': duplex_id,
            'exp_type_choices':   Experiment.EXP_TYPE_CHOICES,
            'assay_type_choices': Experiment.ASSAY_TYPE_CHOICES,
            'conc_unit_choices':  DataPoint.CONC_UNIT_CHOICES,
            'readout_type_choices': DataPoint.READOUT_TYPE_CHOICES,
        })

    # POST
    duplex_id  = request.POST.get('duplex_id', '').strip()
    exp_type   = request.POST.get('exp_type', '')
    assay_type = request.POST.get('assay_type', '')
    cell_line  = request.POST.get('cell_line', '').strip() or None
    animal_species = request.POST.get('animal_species', '').strip() or None
    batch      = request.POST.get('batch', '').strip()
    exp_date_str = request.POST.get('exp_date', '').strip()
    transfection_reagent = request.POST.get('transfection_reagent', '').strip() or None
    route      = request.POST.get('route', '').strip() or None
    notes      = request.POST.get('notes', '').strip() or None

    exp_date = None
    if exp_date_str:
        try:
            from datetime import date
            exp_date = date.fromisoformat(exp_date_str)
        except ValueError:
            pass

    if not duplex_id or not exp_type or not assay_type or not batch:
        messages.error(request, '请填写必填字段：Duplex ID、实验类型、检测类型、批次号。')
        return redirect(f'/experiment/add/?duplex_id={duplex_id}')

    with transaction.atomic():
        exp = Experiment.objects.create(
            duplex_id=duplex_id,
            exp_type=exp_type,
            assay_type=assay_type,
            cell_line=cell_line,
            animal_species=animal_species,
            batch=batch,
            exp_date=exp_date,
            transfection_reagent=transfection_reagent,
            route=route,
            notes=notes,
            created_by=request.user.username,
        )

        # DataPoints: form sends parallel lists dp_conc[], dp_conc_unit[], etc.
        concs        = request.POST.getlist('dp_conc')
        conc_units   = request.POST.getlist('dp_conc_unit')
        timepoints   = request.POST.getlist('dp_timepoint')
        readout_types = request.POST.getlist('dp_readout_type')
        values       = request.POST.getlist('dp_value')
        value_units  = request.POST.getlist('dp_value_unit')
        replicates   = request.POST.getlist('dp_replicate')

        for i in range(len(values)):
            raw_value = values[i].strip()
            if not raw_value:
                continue
            try:
                val = float(raw_value)
            except ValueError:
                continue
            raw_conc = concs[i].strip() if i < len(concs) else ''
            conc_val = None
            if raw_conc:
                try:
                    conc_val = float(raw_conc)
                except ValueError:
                    pass
            DataPoint.objects.create(
                experiment=exp,
                concentration_or_dose=conc_val,
                conc_unit=conc_units[i] if i < len(conc_units) else '',
                timepoint=timepoints[i].strip() if i < len(timepoints) else None,
                readout_type=readout_types[i] if i < len(readout_types) else '',
                value=val,
                value_unit=value_units[i].strip() if i < len(value_units) else None,
                replicate=replicates[i].strip() if i < len(replicates) else None,
            )

        # Attachments
        att_labels   = request.POST.getlist('att_label')
        att_urls     = request.POST.getlist('att_url')
        att_files    = request.FILES.getlist('att_file')

        max_att = max(len(att_labels), len(att_urls), len(att_files))
        for i in range(max_att):
            label = att_labels[i].strip() if i < len(att_labels) else ''
            url   = att_urls[i].strip() if i < len(att_urls) else ''
            f     = att_files[i] if i < len(att_files) else None
            if not label and not url and not f:
                continue
            ExperimentAttachment.objects.create(
                experiment=exp,
                file=f,
                external_url=url or None,
                label=label or (f.name if f else url),
            )

    messages.success(request, f'实验记录已保存（ID={exp.id}）。')
    return redirect(f'/experiment/{duplex_id}/')
```

---

## Task 3: Update seq_list to show experiment summary

- [ ] Modify `get_sequence_info` view in `app01/views.py` to call `get_experiment_summary()` and attach `exp_summary` to each group
- [ ] Modify `templates/seq_list.html`: column filter panel, table header, AS row, SS row

### 3.1 — `app01/views.py`: patch `get_sequence_info`

Find the section in `get_sequence_info` where `sequence_groups` is fully built (just before the final `return render(...)` call). Insert the following block immediately before that `return`:

```python
    # Attach experiment summary to each group
    all_duplex_ids = []
    for group in sequence_groups:
        for item in group.get('items', []):
            for d in item.get('deliveries', []):
                did = d.get('duplex_id') or getattr(d, 'duplex_id', None)
                if did:
                    all_duplex_ids.append(did)
    all_duplex_ids = list(set(all_duplex_ids))
    exp_summary_map = get_experiment_summary(all_duplex_ids)
    for group in sequence_groups:
        duplex_id_for_group = None
        for item in group.get('items', []):
            for d in item.get('deliveries', []):
                did = d.get('duplex_id') or getattr(d, 'duplex_id', None)
                if did:
                    duplex_id_for_group = did
                    break
            if duplex_id_for_group:
                break
        group['exp_summary'] = exp_summary_map.get(duplex_id_for_group, '')
        group['exp_duplex_id'] = duplex_id_for_group or ''
```

### 3.2 — `templates/seq_list.html`: column filter panel

In the `#column-controls` div, change the existing 操作 label and add the new 实验数据 label before it:

```html
    <label><input type="checkbox" class="toggle-vis export-field" data-column="14" value="exp_data" checked> 实验数据</label>
    <label><input type="checkbox" class="toggle-vis export-field" data-column="15" value="操作" checked> 操作</label>
```

Replace the old line:
```html
    <label><input type="checkbox" class="toggle-vis export-field" data-column="14" value="操作" checked> 操作</label>
```

### 3.3 — `templates/seq_list.html`: table header

After `<th class="ds-th-sort">Update Time</th>` and before `<th>操作</th>`, insert:

```html
          <th>实验数据</th>
```

### 3.4 — `templates/seq_list.html`: AS row (first row in `{% for group %}`)

After the `Update Time` `<td>` and before the 操作 `<td>`, insert:

```html
          <td>
            {% if group.exp_summary %}
              <a href="/experiment/{{ group.exp_duplex_id }}/" style="font-size:12px;white-space:pre-line;">{{ group.exp_summary }}</a>
            {% else %}
              <span style="color:#94a3b8;">—</span>
            {% endif %}
          </td>
```

### 3.5 — `templates/seq_list.html`: SS row (second row in `{% for group %}`)

After the `Update Time` `<td>` in the SS row and before the 操作 `<td>`, insert an empty cell:

```html
          <td></td>
```

---

## Task 4: 创建实验详情页模板

**Files:**
- Create: `templates/experiment_detail.html`
- Create: `templates/experiment_card.html`（子模板，被 detail 和未来的列表页共用）

- [ ] **Step 1: 创建 `templates/experiment_detail.html`**

```html
{% extends 'base.html' %}

{% block page_title %} — 实验数据 {{ duplex_id }}{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">实验数据</span>
  <span style="font-family:'DM Mono',monospace;font-size:12px;color:#94a3b8;margin-left:6px;">{{ duplex_id }}</span>
  <span class="ds-topbar-spacer"></span>
  <a href="/seq_list/" class="ds-btn ds-btn-ghost">← 返回列表</a>
  <a href="{% url 'add_experiment' %}?duplex_id={{ duplex_id }}" class="ds-btn ds-btn-primary">+ 添加实验</a>
{% endblock %}

{% block content %}
<div style="max-width:1200px;margin:24px auto;padding:0 16px;">

  {% if not vitro_exps and not vivo_exps %}
    <div class="ds-table-card" style="padding:32px;text-align:center;color:#94a3b8;">
      暂无实验数据。点击右上角"+ 添加实验"开始录入。
    </div>
  {% endif %}

  {% if vitro_exps %}
    <h3 style="font-size:14px;font-weight:700;margin:16px 0 8px;">体外实验</h3>
    {% for exp in vitro_exps %}
      {% include 'experiment_card.html' with exp=exp %}
    {% endfor %}
  {% endif %}

  {% if vivo_exps %}
    <h3 style="font-size:14px;font-weight:700;margin:24px 0 8px;">体内实验</h3>
    {% for exp in vivo_exps %}
      {% include 'experiment_card.html' with exp=exp %}
    {% endfor %}
  {% endif %}

</div>
{% endblock %}
```

- [ ] **Step 2: 创建 `templates/experiment_card.html`**

```html
<div class="ds-table-card" style="margin-bottom:14px;padding:14px;">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <div style="font-size:13px;font-weight:600;">
      {{ exp.get_assay_type_display }}
      <span style="color:#94a3b8;font-weight:400;margin-left:8px;font-size:11px;">
        批次 {{ exp.batch }} · {{ exp.exp_date|default:"无日期" }} · 录入人 {{ exp.created_by }}
      </span>
    </div>
  </div>

  <table style="width:100%;font-size:12px;margin-bottom:8px;">
    <tr>
      {% if exp.cell_line %}<td><strong>细胞系：</strong>{{ exp.cell_line }}</td>{% endif %}
      {% if exp.animal_species %}<td><strong>动物种属：</strong>{{ exp.animal_species }}</td>{% endif %}
      {% if exp.transfection_reagent %}<td><strong>转染试剂：</strong>{{ exp.transfection_reagent }}</td>{% endif %}
      {% if exp.route %}<td><strong>给药途径：</strong>{{ exp.route }}</td>{% endif %}
    </tr>
  </table>

  <table class="ds-table" style="width:100%;font-size:11px;">
    <thead>
      <tr>
        <th>浓度/剂量</th><th>单位</th><th>时间点</th><th>读数类型</th><th>数值</th><th>数值单位</th><th>重复</th>
      </tr>
    </thead>
    <tbody>
      {% for dp in exp.datapoints.all %}
      <tr>
        <td>{{ dp.concentration_or_dose|default_if_none:"—" }}</td>
        <td>{{ dp.get_conc_unit_display|default:"—" }}</td>
        <td>{{ dp.timepoint|default:"—" }}</td>
        <td>{{ dp.get_readout_type_display }}</td>
        <td><strong>{{ dp.value }}</strong></td>
        <td>{{ dp.value_unit|default:"—" }}</td>
        <td>{{ dp.replicate|default:"—" }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% if exp.notes %}
    <div style="font-size:11px;color:#64748b;margin-top:6px;"><strong>备注：</strong>{{ exp.notes|linebreaksbr }}</div>
  {% endif %}

  {% if exp.attachments.all %}
    <div style="font-size:11px;margin-top:8px;">
      <strong>附件：</strong>
      {% for att in exp.attachments.all %}
        {% if att.file %}
          <a href="{{ att.file.url }}" target="_blank" style="margin-right:8px;">📎 {{ att.label }}</a>
        {% elif att.external_url %}
          <a href="{{ att.external_url }}" target="_blank" style="margin-right:8px;">🔗 {{ att.label }}</a>
        {% endif %}
      {% endfor %}
    </div>
  {% endif %}
</div>
```

---

## Task 5: 创建手动录入表单模板与 JS

**Files:**
- Create: `templates/add_experiment.html`
- Create: `static/js/add_experiment.js`

- [ ] **Step 1: 创建 `templates/add_experiment.html`**

```html
{% extends 'base.html' %}

{% block page_title %} — 添加实验数据{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">添加实验数据</span>
  <span style="font-family:'DM Mono',monospace;font-size:12px;color:#94a3b8;margin-left:6px;">{{ duplex_id }}</span>
  <span class="ds-topbar-spacer"></span>
  {% if duplex_id %}
    <a href="/experiment/{{ duplex_id }}/" class="ds-btn ds-btn-ghost">← 取消</a>
  {% else %}
    <a href="/seq_list/" class="ds-btn ds-btn-ghost">← 取消</a>
  {% endif %}
{% endblock %}

{% block content %}
<div class="ds-form-page">
  <div class="ds-form-card">
    <div class="ds-form-card-title">实验信息</div>

    <form method="POST" enctype="multipart/form-data">
      {% csrf_token %}

      <div class="ds-form-2col">
        <div>
          <label class="ds-form-label">Duplex ID *</label>
          <input type="text" name="duplex_id" class="ds-form-control" value="{{ duplex_id }}" required>
        </div>

        <div>
          <label class="ds-form-label">批次号 *</label>
          <input type="text" name="batch" class="ds-form-control" required>
        </div>

        <div>
          <label class="ds-form-label">实验类型 *</label>
          <select name="exp_type" id="exp_type_select" class="ds-form-control" required>
            {% for v, label in exp_type_choices %}
              <option value="{{ v }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="ds-form-label">检测类型 *</label>
          <select name="assay_type" class="ds-form-control" required>
            {% for v, label in assay_type_choices %}
              <option value="{{ v }}">{{ label }}</option>
            {% endfor %}
          </select>
        </div>

        <div id="cell_line_wrap">
          <label class="ds-form-label">细胞系</label>
          <input type="text" name="cell_line" class="ds-form-control" placeholder="如 HepG2">
        </div>

        <div id="animal_wrap" style="display:none;">
          <label class="ds-form-label">动物种属</label>
          <input type="text" name="animal_species" class="ds-form-control" placeholder="如 mouse">
        </div>

        <div id="reagent_wrap">
          <label class="ds-form-label">转染试剂</label>
          <input type="text" name="transfection_reagent" class="ds-form-control" placeholder="如 Lipofectamine">
        </div>

        <div id="route_wrap" style="display:none;">
          <label class="ds-form-label">给药途径</label>
          <select name="route" class="ds-form-control">
            <option value="">--</option>
            <option value="SC">SC（皮下）</option>
            <option value="IV">IV（静脉）</option>
            <option value="PO">PO（口服）</option>
          </select>
        </div>

        <div>
          <label class="ds-form-label">实验日期</label>
          <input type="date" name="exp_date" class="ds-form-control">
        </div>

        <div class="ds-form-span-2">
          <label class="ds-form-label">备注</label>
          <textarea name="notes" class="ds-form-control" rows="2"></textarea>
        </div>
      </div>

      <div class="ds-form-card-title" style="margin-top:24px;">数据点</div>
      <table class="ds-table" id="datapoints_table" style="font-size:12px;">
        <thead>
          <tr>
            <th>浓度/剂量</th><th>单位</th><th>时间点</th><th>读数类型 *</th><th>数值 *</th><th>数值单位</th><th>重复</th><th></th>
          </tr>
        </thead>
        <tbody id="datapoints_body"></tbody>
      </table>
      <button type="button" id="addDataPointBtn" class="ds-btn ds-btn-ghost" style="height:30px;font-size:12px;">+ 添加数据点</button>

      <!-- Hidden choice templates for JS to read -->
      <script type="application/json" id="conc_unit_choices">
        [{% for v, label in conc_unit_choices %}{"v":"{{ v }}","l":"{{ label }}"}{% if not forloop.last %},{% endif %}{% endfor %}]
      </script>
      <script type="application/json" id="readout_type_choices">
        [{% for v, label in readout_type_choices %}{"v":"{{ v }}","l":"{{ label }}"}{% if not forloop.last %},{% endif %}{% endfor %}]
      </script>

      <div class="ds-form-card-title" style="margin-top:24px;">附件</div>
      <div id="attachments_wrap">
        <div class="attach-row" style="display:flex;gap:8px;margin-bottom:6px;align-items:center;">
          <input type="file" name="att_file" class="ds-form-control" style="flex:1;">
          <input type="text" name="att_url" class="ds-form-control" placeholder="或填外部链接" style="flex:1;">
          <input type="text" name="att_label" class="ds-form-control" placeholder="描述" style="flex:1;">
        </div>
      </div>
      <button type="button" id="addAttachBtn" class="ds-btn ds-btn-ghost" style="height:30px;font-size:12px;">+ 添加附件</button>

      <div style="margin-top:24px;display:flex;gap:10px;">
        <button type="submit" class="ds-btn ds-btn-primary">保存</button>
      </div>
    </form>
  </div>
</div>
{% endblock %}

{% block extra_scripts %}
<script src="/static/js/add_experiment.js"></script>
{% endblock %}
```

- [ ] **Step 2: 创建 `static/js/add_experiment.js`**

```javascript
(function () {
  var concUnits   = JSON.parse(document.getElementById('conc_unit_choices').textContent);
  var readoutTypes = JSON.parse(document.getElementById('readout_type_choices').textContent);

  function buildSelect(name, choices, required) {
    var s = '<select name="' + name + '" class="ds-form-control"' + (required ? ' required' : '') + '>';
    if (!required) s += '<option value="">--</option>';
    for (var i = 0; i < choices.length; i++) {
      s += '<option value="' + choices[i].v + '">' + choices[i].l + '</option>';
    }
    s += '</select>';
    return s;
  }

  function dpRow() {
    var tr = document.createElement('tr');
    tr.innerHTML = ''
      + '<td><input type="number" step="any" name="dp_conc" class="ds-form-control"></td>'
      + '<td>' + buildSelect('dp_conc_unit', concUnits, false) + '</td>'
      + '<td><input type="text" name="dp_timepoint" class="ds-form-control" placeholder="48h / Day7"></td>'
      + '<td>' + buildSelect('dp_readout_type', readoutTypes, true) + '</td>'
      + '<td><input type="number" step="any" name="dp_value" class="ds-form-control" required></td>'
      + '<td><input type="text" name="dp_value_unit" class="ds-form-control" placeholder="% / ng/mL"></td>'
      + '<td><input type="text" name="dp_replicate" class="ds-form-control" placeholder="n=3"></td>'
      + '<td><button type="button" class="ds-btn ds-btn-ghost remove-dp" style="height:24px;padding:0 6px;">×</button></td>';
    return tr;
  }

  function attachRow() {
    var div = document.createElement('div');
    div.className = 'attach-row';
    div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center;';
    div.innerHTML = ''
      + '<input type="file" name="att_file" class="ds-form-control" style="flex:1;">'
      + '<input type="text" name="att_url" class="ds-form-control" placeholder="或填外部链接" style="flex:1;">'
      + '<input type="text" name="att_label" class="ds-form-control" placeholder="描述" style="flex:1;">'
      + '<button type="button" class="ds-btn ds-btn-ghost remove-attach" style="height:24px;padding:0 6px;">×</button>';
    return div;
  }

  document.getElementById('datapoints_body').appendChild(dpRow());

  document.getElementById('addDataPointBtn').addEventListener('click', function () {
    document.getElementById('datapoints_body').appendChild(dpRow());
  });
  document.getElementById('datapoints_body').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-dp')) {
      var tbody = document.getElementById('datapoints_body');
      if (tbody.children.length > 1) e.target.closest('tr').remove();
    }
  });

  document.getElementById('addAttachBtn').addEventListener('click', function () {
    document.getElementById('attachments_wrap').appendChild(attachRow());
  });
  document.getElementById('attachments_wrap').addEventListener('click', function (e) {
    if (e.target.classList.contains('remove-attach')) {
      e.target.closest('.attach-row').remove();
    }
  });

  function toggleExpType() {
    var t = document.getElementById('exp_type_select').value;
    document.getElementById('cell_line_wrap').style.display = (t === 'in_vitro') ? '' : 'none';
    document.getElementById('reagent_wrap').style.display   = (t === 'in_vitro') ? '' : 'none';
    document.getElementById('animal_wrap').style.display    = (t === 'in_vivo')  ? '' : 'none';
    document.getElementById('route_wrap').style.display     = (t === 'in_vivo')  ? '' : 'none';
  }
  document.getElementById('exp_type_select').addEventListener('change', toggleExpType);
  toggleExpType();
})();
```

---

## Task 6: 批量 CSV 上传视图与模板

**Files:**
- Modify: `app01/views.py`（在 `add_experiment` 视图之后追加）
- Modify: `bms/urls.py`（已在 Task 1 添加路由）
- Create: `templates/upload_experiment.html`

- [ ] **Step 1: 在 `app01/views.py` 末尾追加 `upload_experiment` 视图**

```python
@login_required
def upload_experiment(request):
    """批量上传实验数据 CSV。
    支持两种格式：
    1. duplex_id 列直接指定
    2. modify_seq 列（AS+SS 上下两行为一组），系统匹配 duplex_id
    """
    import pandas as pd
    from collections import defaultdict as _dd

    if request.method == 'POST' and request.FILES.get('csv_file'):
        try:
            df = pd.read_csv(request.FILES['csv_file'], dtype=str).fillna('')
            df.columns = [c.strip() for c in df.columns]
        except Exception as e:
            messages.error(request, f"CSV 解析失败：{e}")
            return render(request, 'upload_experiment.html')

        errors = []
        created_exp = 0
        created_dp = 0

        has_duplex_col = 'duplex_id' in df.columns
        has_modify_col = 'modify_seq' in df.columns

        if not has_duplex_col and not has_modify_col:
            messages.error(request, "CSV 必须包含 duplex_id 或 modify_seq 列")
            return render(request, 'upload_experiment.html')

        # 格式二：modify_seq 配对匹配
        if has_modify_col and not has_duplex_col:
            df = df.reset_index(drop=True)
            if len(df) % 2 != 0:
                messages.error(request, "modify_seq 格式要求 AS+SS 上下两行配对，行数必须为偶数")
                return render(request, 'upload_experiment.html')

            resolved_rows = []
            for i in range(0, len(df), 2):
                r1 = df.iloc[i]
                r2 = df.iloc[i + 1]
                seq1 = r1['modify_seq'].strip()
                seq2 = r2['modify_seq'].strip()
                d1 = set(Delivery.objects.filter(modify_seq=seq1).values_list('duplex_id', flat=True))
                d2 = set(Delivery.objects.filter(modify_seq=seq2).values_list('duplex_id', flat=True))
                common = d1 & d2
                if not common:
                    errors.append(f"行 {i+2}-{i+3}：未找到 AS+SS 匹配的 duplex_id")
                    continue
                if len(common) > 1:
                    errors.append(f"行 {i+2}-{i+3}：匹配到多个 duplex_id ({', '.join(common)})，请改用 duplex_id 列")
                    continue
                duplex_id = common.pop()
                merged = {}
                for col in df.columns:
                    v = r1.get(col, '') or r2.get(col, '')
                    merged[col] = v
                merged['duplex_id'] = duplex_id
                resolved_rows.append(merged)

            if not resolved_rows:
                messages.error(request, "没有可处理的行：" + " | ".join(errors[:5]))
                return render(request, 'upload_experiment.html')

            df = pd.DataFrame(resolved_rows)

        # 统一按 duplex_id 处理：归并相同实验元数据的多行 → 一条 Experiment + N 个 DataPoint
        grouping_keys = ['duplex_id', 'batch', 'assay_type', 'cell_line', 'animal_species', 'exp_date']
        for key in grouping_keys:
            if key not in df.columns:
                df[key] = ''

        groups = _dd(list)
        for idx, row in df.iterrows():
            key = tuple(str(row.get(k, '') or '') for k in grouping_keys)
            groups[key].append(row)

        for key, rows in groups.items():
            first = rows[0]
            try:
                exp = Experiment.objects.create(
                    duplex_id=str(first.get('duplex_id', '')).strip(),
                    exp_type=str(first.get('exp_type', 'in_vitro')).strip() or 'in_vitro',
                    assay_type=str(first.get('assay_type', 'single_point')).strip() or 'single_point',
                    cell_line=str(first.get('cell_line', '')).strip() or None,
                    animal_species=str(first.get('animal_species', '')).strip() or None,
                    batch=str(first.get('batch', '')).strip(),
                    exp_date=str(first.get('exp_date', '')).strip() or None,
                    transfection_reagent=str(first.get('transfection_reagent', '')).strip() or None,
                    route=str(first.get('route', '')).strip() or None,
                    notes=str(first.get('notes', '')).strip() or None,
                    created_by=request.user.username,
                )
                created_exp += 1
            except Exception as e:
                errors.append(f"创建实验失败：{e}")
                continue

            for row in rows:
                val = str(row.get('value', '')).strip()
                if not val:
                    continue
                try:
                    v = float(val)
                except ValueError:
                    continue
                conc = str(row.get('conc', '') or row.get('dose', '')).strip()
                conc_val = None
                if conc:
                    try:
                        conc_val = float(conc)
                    except ValueError:
                        pass
                DataPoint.objects.create(
                    experiment=exp,
                    concentration_or_dose=conc_val,
                    conc_unit=str(row.get('conc_unit', '')).strip(),
                    timepoint=str(row.get('timepoint', '')).strip() or None,
                    readout_type=str(row.get('readout_type', 'mRNA_remaining')).strip() or 'mRNA_remaining',
                    value=v,
                    value_unit=str(row.get('value_unit', '')).strip() or None,
                    replicate=str(row.get('replicate', '')).strip() or None,
                )
                created_dp += 1

        messages.success(request, f"成功创建 {created_exp} 条实验记录，{created_dp} 个数据点。")
        if errors:
            messages.warning(request, "部分行处理失败：" + " | ".join(errors[:10]))

        return render(request, 'upload_experiment.html')

    return render(request, 'upload_experiment.html')
```

- [ ] **Step 2: 创建 `templates/upload_experiment.html`**

```html
{% extends 'base.html' %}

{% block page_title %} — 批量上传实验数据{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">批量上传实验数据</span>
  <span class="ds-topbar-spacer"></span>
  <a href="/seq_list/" class="ds-btn ds-btn-ghost">← 返回</a>
{% endblock %}

{% block content %}
<div class="ds-form-page">
  <div class="ds-form-card">
    <div class="ds-form-card-title">CSV 文件上传</div>

    {% if messages %}
      {% for m in messages %}
        <div style="padding:8px 12px;margin-bottom:8px;border-radius:6px;font-size:13px;
                    background:{% if m.tags == 'success' %}#dcfce7{% elif m.tags == 'warning' %}#fef9c3{% else %}#fee2e2{% endif %};
                    color:{% if m.tags == 'success' %}#15803d{% elif m.tags == 'warning' %}#854d0e{% else %}#b91c1c{% endif %};">
          {{ m }}
        </div>
      {% endfor %}
    {% endif %}

    <div style="font-size:12px;color:#475569;margin-bottom:14px;line-height:1.6;">
      <strong>支持两种格式：</strong>
      <br>1. <strong>duplex_id 格式</strong>：CSV 含 <code>duplex_id</code> 列，直接指定。
      <br>2. <strong>modify_seq 格式</strong>：CSV 含 <code>modify_seq</code> 列，AS 和 SS 上下两行为一组，系统自动匹配 <code>duplex_id</code>。
      <br>必填列：<code>exp_type</code>（in_vitro/in_vivo）、<code>assay_type</code>（single_point/dose_response/in_vivo_efficacy/pk）、<code>batch</code>、<code>readout_type</code>、<code>value</code>。
      <br>可选列：<code>cell_line</code>、<code>animal_species</code>、<code>exp_date</code>、<code>transfection_reagent</code>、<code>route</code>、<code>conc</code>、<code>conc_unit</code>、<code>timepoint</code>、<code>value_unit</code>、<code>replicate</code>、<code>notes</code>。
    </div>

    <form method="POST" enctype="multipart/form-data">
      {% csrf_token %}
      <div style="margin-bottom:14px;">
        <input type="file" name="csv_file" class="ds-form-control" accept=".csv" required>
      </div>
      <button type="submit" class="ds-btn ds-btn-primary">上传</button>
    </form>
  </div>
</div>
{% endblock %}
```

---

## Task 7: 验证与提交

- [ ] **Step 1: Django check**

```bash
source venv/bin/activate && python manage.py check
```

Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 2: 启动服务器人工验证**

```bash
source venv/bin/activate && python manage.py runserver
```

打开 `http://127.0.0.1:8000/seq_list/`，验证：
1. 新增"实验数据"列出现，无数据时显示 `—`
2. 列显示面板能切换"实验数据"列
3. DataTables 无 "Incorrect column count" 警告
4. 点击某 duplex 的 detail 链接（暂时手动访问 `/experiment/<duplex_id>/`），页面正常
5. 点击"+ 添加实验"跳转到表单，填写后保存能跳回 detail 页
6. 上传一个 CSV（duplex_id 格式），后台能看到新建的 Experiment 记录
7. 上传一个 CSV（modify_seq 格式，AS+SS 配对），系统正确匹配 duplex_id

- [ ] **Step 3: Commit**

```bash
git add app01/models.py app01/migrations/0026_experiment_models.py \
        app01/views.py bms/settings.py bms/urls.py \
        templates/experiment_detail.html templates/experiment_card.html \
        templates/add_experiment.html templates/upload_experiment.html \
        templates/seq_list.html static/js/add_experiment.js
git commit -m "$(cat <<'EOF'
feat: add siRNA experimental data management

Three new models (Experiment, DataPoint, ExperimentAttachment) linked to
duplex_id, manual entry form with dynamic datapoints and attachments,
bulk CSV upload supporting both duplex_id and modify_seq matching, and
seq_list summary column showing best in vitro/in vivo knockdown.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 验证方式（端到端）

1. **模型与迁移**：`python manage.py migrate` 无报错；admin 后台能看到三张新表
2. **手动录入**：在 seq_list 点击某行的"+ 添加"链接（或直接访问 `/experiment/add/?duplex_id=BP000001`），填表保存，跳转到 detail 页能看到记录
3. **批量上传（duplex_id 格式）**：上传含 `duplex_id` 列的 CSV，多行同 batch 归并成一条 Experiment + 多条 DataPoint
4. **批量上传（modify_seq 格式）**：上传 AS+SS 配对 CSV，系统正确匹配 duplex_id；匹配到多个时报错提示
5. **附件**：手动录入时上传文件，detail 页能下载；外部链接能跳转
6. **seq_list 摘要**：录入数据后刷新 seq_list，对应行显示摘要文本（如 `KD 85%@10nM / in vivo 82%@3mg_kg`），无数据的行显示 `—`
7. **权限**：用户只能看到有项目权限的 duplex 的实验数据；admin 能看到所有数据
