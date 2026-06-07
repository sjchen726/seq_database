# BPRdb 子项目 A — Fork 与新数据模型实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 seq_database_v2 fork 出独立的新项目 seq_database_bprdb，替换数据模型（Compound/Strand/Experiment/DataPoint/ExperimentSummary），保留序列着色逻辑和权限体系。

**Architecture:** 完整复制当前项目目录，重命名 Django 项目包（bms → bprdb），清空旧数据模型和相关视图，写入新模型，跑初始迁移，并将 SeqModule/LinkerModule/DeliveryModule/LmsUser 数据从旧库迁移过来。

**Tech Stack:** Python 3.10, Django 5.1, MySQL, django-decouple

**设计文档：** `docs/superpowers/specs/2026-06-07-bprdb-subproject-a-design.md`

**旧项目路径：** `/Users/gutou/Projects/seq_web/seq_database_v2`  
**新项目路径：** `/Users/gutou/Projects/seq_web/seq_database_bprdb`

---

## 文件变更地图

| 文件 | 操作 |
|------|------|
| `seq_database_bprdb/` | 新建（从 v2 复制） |
| `bprdb/settings.py` | 原 `bms/settings.py`，修改 DB 名、项目名引用 |
| `bprdb/urls.py` | 原 `bms/urls.py`，清空旧路由，加 stub |
| `bprdb/wsgi.py` / `asgi.py` | 修改模块路径引用 |
| `manage.py` | 修改 `DJANGO_SETTINGS_MODULE` |
| `app01/models.py` | 全量替换为 5 个新模型 |
| `app01/views.py` | 删除旧视图，保留着色函数，加 stub index |
| `app01/apps.py` | 更新 signal 引用（如有） |
| `app01/tests.py` | 新增基础模型测试 |
| `app01/migrations/` | 删除旧迁移，生成新初始迁移 |

---

## Task 1：复制项目并清理无关文件

**Files:**
- Create: `/Users/gutou/Projects/seq_web/seq_database_bprdb/`

- [ ] **Step 1: 复制项目目录**

```bash
cp -r /Users/gutou/Projects/seq_web/seq_database_v2 \
       /Users/gutou/Projects/seq_web/seq_database_bprdb
```

- [ ] **Step 2: 删除不需要的文件**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb

# 删除 venv（新项目会用同一个 venv 或重建）
rm -rf venv

# 删除日志、临时 csv、截图
rm -f edit_book.log
rm -f *.csv *.png *.bk

# 删除所有旧迁移（保留 __init__.py）
find app01/migrations -name "*.py" ! -name "__init__.py" -delete

# 删除 pycache
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# 删除旧 views.py 备份
rm -f app01/views.py.bk
```

- [ ] **Step 3: 创建新的 .env 文件**

```bash
cat > /Users/gutou/Projects/seq_web/seq_database_bprdb/.env << 'EOF'
SECRET_KEY=bprdb-dev-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DB_NAME=bprdb
DB_USER=root
DB_PASSWORD=
DB_HOST=127.0.0.1
DB_PORT=3306
EOF
```

- [ ] **Step 4: 创建新 MySQL 数据库**

```bash
mysql -u root -e "CREATE DATABASE IF NOT EXISTS bprdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

Expected: Query OK（无错误）

---

## Task 2：重命名 Django 项目包（bms → bprdb）

**Files:**
- Rename: `bms/` → `bprdb/`
- Modify: `manage.py`
- Modify: `bprdb/settings.py`
- Modify: `bprdb/wsgi.py`
- Modify: `bprdb/asgi.py`

- [ ] **Step 1: 重命名包目录**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
mv bms bprdb
```

- [ ] **Step 2: 更新 manage.py**

编辑 `manage.py`，将第 9 行改为：

```python
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bprdb.settings')
```

- [ ] **Step 3: 更新 bprdb/wsgi.py**

找到文件中的 `bms.settings` 引用，改为 `bprdb.settings`：

```python
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bprdb.settings')
```

- [ ] **Step 4: 更新 bprdb/asgi.py**

同上，将 `bms.settings` 改为 `bprdb.settings`：

```python
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bprdb.settings')
```

- [ ] **Step 5: 更新 bprdb/settings.py 中的引用**

找到以下两行并修改：

```python
# 原: ROOT_URLCONF = 'bms.urls'
ROOT_URLCONF = 'bprdb.urls'

# 原: WSGI_APPLICATION = 'bms.wsgi.application'
WSGI_APPLICATION = 'bprdb.wsgi.application'
```

同时更新数据库配置，使用 .env 中的变量（如果原配置是硬编码则替换）：

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='bprdb'),
        'USER': config('DB_USER', default='root'),
        'PASSWORD': config('DB_PASSWORD', default=''),
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='3306'),
        'OPTIONS': {'charset': 'utf8mb4'},
    }
}
```

- [ ] **Step 6: 验证项目可识别**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py check 2>&1 | head -20
```

Expected 输出包含错误（因为 models 还未替换），但不应出现 `ModuleNotFoundError: No module named 'bms'`

---

## Task 3：替换 app01/models.py

**Files:**
- Modify: `app01/models.py`（全量替换）

- [ ] **Step 1: 写入新 models.py**

将 `app01/models.py` 完整替换为以下内容：

```python
import re
from django.db import models
from django.contrib.auth.models import AbstractUser


class LmsUser(AbstractUser):
    USER_TYPE_CHOICES = [
        ('guest', 'guest'),
        ('delivery', 'delivery'),
        ('modify', 'modify'),
        ('project', 'project'),
        ('data_admin', 'data_admin'),
        ('admin', 'admin'),
        ('superadmin', 'superadmin'),
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='guest')
    permissions_project = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'lms_user'


class SeqModule(models.Model):
    keyword = models.CharField(max_length=64, blank=True)
    base_char = models.CharField(max_length=8, blank=True)
    linker_connector = models.CharField(max_length=4, blank=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'seq_module'

    def __str__(self):
        return self.keyword or ''


class LinkerModule(models.Model):
    keyword = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'linker_module'

    def __str__(self):
        return self.keyword or ''


class DeliveryModule(models.Model):
    keyword = models.CharField(max_length=64, blank=True)
    type_code = models.CharField(max_length=32, blank=True)
    description = models.CharField(max_length=256, blank=True)

    class Meta:
        db_table = 'delivery_module'

    def __str__(self):
        return self.keyword or ''


def _parse_compound_id(compound_id):
    """从 BPR_3M03FN01 解析出 project='3M03', target='FN'"""
    m = re.match(r'^BPR_([A-Z0-9]+)([A-Z]{2})(\d{2,3})$', compound_id)
    if m:
        return m.group(1), m.group(2)
    return '', ''


class Compound(models.Model):
    compound_id = models.CharField(max_length=32, primary_key=True)
    project = models.CharField(max_length=32, blank=True)
    target = models.CharField(max_length=32, blank=True)
    transcript_ref = models.CharField(max_length=64, blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'compound'
        ordering = ['compound_id']

    def __str__(self):
        return self.compound_id

    def save(self, *args, **kwargs):
        if self.compound_id and not self.project:
            self.project, self.target = _parse_compound_id(self.compound_id)
        super().save(*args, **kwargs)


class Strand(models.Model):
    STRAND_TYPE_CHOICES = [('SS', 'Sense'), ('AS', 'Antisense')]

    compound = models.ForeignKey(Compound, on_delete=models.CASCADE,
                                  related_name='strands')
    strand_type = models.CharField(max_length=4, choices=STRAND_TYPE_CHOICES)
    sequence_id = models.CharField(max_length=64, blank=True)
    modify_seq = models.TextField(blank=True)

    class Meta:
        db_table = 'strand'
        unique_together = [('compound', 'strand_type')]

    def __str__(self):
        return f"{self.compound_id}_{self.strand_type}"


class Experiment(models.Model):
    EXP_TYPE_CHOICES = [('in_vitro', '体外'), ('in_vivo', '体内')]

    compound = models.ForeignKey(Compound, on_delete=models.CASCADE,
                                  related_name='experiments')
    exp_type = models.CharField(max_length=16, choices=EXP_TYPE_CHOICES)
    assay_name = models.CharField(max_length=128)
    cell_line = models.CharField(max_length=64, blank=True)
    batch_label = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'experiment'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.compound_id} | {self.exp_type} | {self.batch_label}"


class DataPoint(models.Model):
    X_TYPE_CHOICES = [('concentration', '浓度 nM'), ('timepoint', '时间点 天')]
    READOUT_CHOICES = [
        ('mRNA_remaining', 'mRNA 残余%'),
        ('knockdown_pct', 'KD%'),
    ]

    experiment = models.ForeignKey(Experiment, on_delete=models.CASCADE,
                                    related_name='datapoints')
    x_value = models.FloatField()
    x_type = models.CharField(max_length=16, choices=X_TYPE_CHOICES)
    replicate = models.CharField(max_length=8)   # A/B/1/2/3/Mean
    value = models.FloatField()
    readout_type = models.CharField(max_length=32, choices=READOUT_CHOICES)
    is_control = models.BooleanField(default=False)
    is_flagged = models.BooleanField(default=False)
    flag_note = models.CharField(max_length=128, blank=True)
    raw_cp = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = 'data_point'

    def __str__(self):
        return f"{self.experiment_id} | x={self.x_value} rep={self.replicate}"


class ExperimentSummary(models.Model):
    experiment = models.OneToOneField(Experiment, on_delete=models.CASCADE,
                                       related_name='summary')
    max_kd_pct = models.FloatField(null=True, blank=True)
    ic50_nm = models.FloatField(null=True, blank=True)
    rank = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'experiment_summary'

    def __str__(self):
        return f"{self.experiment_id} | IC50={self.ic50_nm}"
```

- [ ] **Step 2: 验证模型可导入**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python -c "from app01.models import Compound, Strand, Experiment, DataPoint, ExperimentSummary; print('OK')"
```

Expected: `OK`

---

## Task 4：清理 app01/views.py

**Files:**
- Modify: `app01/views.py`（约 5100 行）

策略：**保留**原文件中的所有着色工具函数（原文逐字复制，不改动），**删除**所有依赖旧模型的业务视图，**替换**顶部 import，**新增** stub 视图。

原始 views.py 中需保留的函数行号（已从 seq_database_v2 确认）：

| 函数 | 行号 |
|------|------|
| `_module_list_url` | 43 |
| `get_color_map` | 52 |
| `get_delivery_colored` | 85 |
| `_reverse_tokens` | 185 |
| `get_modify_seq_colored` | 218 |
| `split_tokens_at_sep` | 359 |
| `align_duplex_tokens` | 372 |
| `add_o_to_all_rules` | 1153 |
| `detect_embedded_linker` | 1216 |
| `add_o_to_all_rules_safe` | 1247 |
| `normalize_middle_brackets` | 1260 |
| `build_duplex_groups` | 2899 |

- [ ] **Step 1: 用 Python 脚本提取着色函数并生成新 views.py**

在新项目目录下运行：

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python - << 'PYEOF'
import ast, textwrap

src_path = "app01/views.py"
with open(src_path, encoding="utf-8") as f:
    source = f.read()

# 需要保留的函数名
KEEP = {
    "_module_list_url", "get_color_map", "get_delivery_colored",
    "_reverse_tokens", "get_modify_seq_colored", "split_tokens_at_sep",
    "align_duplex_tokens", "add_o_to_all_rules", "detect_embedded_linker",
    "add_o_to_all_rules_safe", "normalize_middle_brackets", "build_duplex_groups",
}

tree = ast.parse(source)
lines = source.splitlines(keepends=True)

# 收集需保留函数的行范围
keep_ranges = []
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if node.name in KEEP:
            start = node.lineno - 1
            end = node.end_lineno
            keep_ranges.append((start, end))

keep_ranges.sort()

# 提取函数体
extracted = []
for start, end in keep_ranges:
    extracted.append("".join(lines[start:end]))

NEW_IMPORTS = '''from collections import defaultdict
import re, json, os, csv
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, Http404, JsonResponse
from django.contrib.auth import authenticate, login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import logging

from app01.models import (
    LmsUser, SeqModule, LinkerModule, DeliveryModule,
    Compound, Strand, Experiment, DataPoint, ExperimentSummary,
)

logger = logging.getLogger("edit_book_log")


# ── Stub views ──────────────────────────────────────────────────────────────

def login_view(request):
    if request.method == "POST":
        user = authenticate(request,
                            username=request.POST.get("username", ""),
                            password=request.POST.get("password", ""))
        if user:
            login(request, user)
            return redirect("index")
        return render(request, "login.html", {"error": "用户名或密码错误"})
    return render(request, "login.html")


def logout_view(request):
    auth_logout(request)
    return redirect("login")


@login_required
def index(request):
    return render(request, "index.html")


# ── Coloring utilities (verbatim from seq_database_v2) ──────────────────────
'''

new_views = NEW_IMPORTS + "\n\n".join(extracted) + "\n"
with open("app01/views.py", "w", encoding="utf-8") as f:
    f.write(new_views)
print(f"Done. Kept {len(extracted)} functions, new file size: {len(new_views)} chars")
PYEOF
```

Expected 输出类似：`Done. Kept 12 functions, new file size: XXXXX chars`

- [ ] **Step 2: 验证 views.py 可导入**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python -c "from app01 import views; print('login_view:', views.login_view); print('get_color_map:', views.get_color_map)"
```

Expected: 两个函数都能找到，无 ImportError。

- [ ] **Step 3: 验证着色函数签名正确**

```bash
python -c "
import inspect
from app01 import views
for fn in ['get_color_map','get_delivery_colored','get_modify_seq_colored',
           'split_tokens_at_sep','detect_embedded_linker','build_duplex_groups']:
    sig = inspect.signature(getattr(views, fn))
    print(f'{fn}{sig}')
"
```

Expected: 打印出 12 个函数签名，无报错。

---

## Task 5：更新 urls.py 和 app01/apps.py

**Files:**
- Modify: `bprdb/urls.py`
- Modify: `app01/apps.py`

- [ ] **Step 1: 替换 bprdb/urls.py**

```python
from django.contrib import admin
from django.urls import path
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
]
```

- [ ] **Step 2: 更新 app01/apps.py**

将 `app01/apps.py` 中的 signal 注册改为不依赖旧模型（如原来有 `Delivery` post_save signal，现在暂时移除）：

```python
from django.apps import AppConfig


class App01Config(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app01'
```

- [ ] **Step 3: 创建 stub 模板 templates/index.html（如不存在）**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
ls templates/index.html 2>/dev/null || echo "<!DOCTYPE html><html><body><h1>BPRdb — Coming Soon</h1></body></html>" > templates/index.html
```

---

## Task 6：运行迁移并验证数据库

**Files:**
- Create: `app01/migrations/0001_initial.py`（自动生成）

- [ ] **Step 1: 生成初始迁移**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py makemigrations app01
```

Expected 输出包含：
```
Migrations for 'app01':
  app01/migrations/0001_initial.py
    - Create model LmsUser
    - Create model SeqModule
    - ...
```

- [ ] **Step 2: 执行迁移**

```bash
python manage.py migrate
```

Expected 末尾：`Running migrations: ... OK`，无报错。

- [ ] **Step 3: 验证表已创建**

```bash
mysql -u root bprdb -e "SHOW TABLES;"
```

Expected 输出包含：`compound`, `strand`, `experiment`, `data_point`, `experiment_summary`, `lms_user`

---

## Task 7：编写基础模型测试

**Files:**
- Modify: `app01/tests.py`

- [ ] **Step 1: 写测试**

将 `app01/tests.py` 替换为：

```python
from django.test import TestCase
from app01.models import (
    Compound, Strand, Experiment, DataPoint,
    ExperimentSummary, _parse_compound_id,
)
import datetime


class ParseCompoundIdTest(TestCase):
    def test_standard_2digit(self):
        project, target = _parse_compound_id('BPR_3M03FN01')
        self.assertEqual(project, '3M03')
        self.assertEqual(target, 'FN')

    def test_standard_3digit(self):
        project, target = _parse_compound_id('BPR_3M03FN001')
        self.assertEqual(project, '3M03')
        self.assertEqual(target, 'FN')

    def test_different_target(self):
        project, target = _parse_compound_id('BPR_4A01CD05')
        self.assertEqual(project, '4A01')
        self.assertEqual(target, 'CD')

    def test_unrecognized_format(self):
        project, target = _parse_compound_id('UNKNOWN_ID')
        self.assertEqual(project, '')
        self.assertEqual(target, '')


class CompoundModelTest(TestCase):
    def test_create_auto_parses_project_target(self):
        c = Compound.objects.create(compound_id='BPR_3M03FN01')
        self.assertEqual(c.project, '3M03')
        self.assertEqual(c.target, 'FN')

    def test_str(self):
        c = Compound(compound_id='BPR_3M03FN01')
        self.assertEqual(str(c), 'BPR_3M03FN01')


class StrandModelTest(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR_3M03FN01')

    def test_create_ss_strand(self):
        s = Strand.objects.create(
            compound=self.compound,
            strand_type='SS',
            sequence_id='BPR_3M03FN01_SS',
            modify_seq='mAmGfUmA',
        )
        self.assertEqual(s.strand_type, 'SS')
        self.assertEqual(s.compound.compound_id, 'BPR_3M03FN01')

    def test_unique_together(self):
        Strand.objects.create(compound=self.compound, strand_type='SS')
        with self.assertRaises(Exception):
            Strand.objects.create(compound=self.compound, strand_type='SS')


class ExperimentAndDataPointTest(TestCase):
    def setUp(self):
        self.compound = Compound.objects.create(compound_id='BPR_3M03FN01')
        self.exp = Experiment.objects.create(
            compound=self.compound,
            exp_type='in_vitro',
            assay_name='FASN knockdown Hepa1-6',
            cell_line='Hepa1-6',
            batch_label='2026-05',
        )

    def test_datapoint_creation(self):
        dp = DataPoint.objects.create(
            experiment=self.exp,
            x_value=100.0,
            x_type='concentration',
            replicate='A',
            value=0.26,
            readout_type='mRNA_remaining',
        )
        self.assertFalse(dp.is_control)
        self.assertFalse(dp.is_flagged)
        self.assertIsNone(dp.raw_cp)

    def test_datapoint_with_raw_cp(self):
        raw = {
            'reference_gene': 'GAPDH',
            'target_gene': 'FASN',
            'cp_values': {
                'GAPDH': {'A': 16.06, 'B': 16.18, 'C': 16.07},
                'FASN': {'A': 23.85, 'B': 23.85, 'C': 23.81},
            },
            'computed': {'GAPDH_mean': 16.07, 'GAPDH_cv': 0.05,
                         'FASN_mean': 23.85, 'FASN_cv': 0.02},
        }
        dp = DataPoint.objects.create(
            experiment=self.exp,
            x_value=100.0, x_type='concentration',
            replicate='A', value=0.26,
            readout_type='mRNA_remaining',
            raw_cp=raw,
        )
        self.assertEqual(dp.raw_cp['reference_gene'], 'GAPDH')
        self.assertAlmostEqual(dp.raw_cp['cp_values']['GAPDH']['A'], 16.06)

    def test_flagged_datapoint(self):
        dp = DataPoint.objects.create(
            experiment=self.exp,
            x_value=56, x_type='timepoint',
            replicate='2', value=-54.22,
            readout_type='knockdown_pct',
            is_flagged=True, flag_note='outlier *',
        )
        self.assertTrue(dp.is_flagged)

    def test_experiment_summary(self):
        s = ExperimentSummary.objects.create(
            experiment=self.exp,
            max_kd_pct=74.71,
            ic50_nm=5.48,
            rank=9,
        )
        self.assertAlmostEqual(s.ic50_nm, 5.48)
        self.assertEqual(self.exp.summary.rank, 9)
```

- [ ] **Step 2: 运行测试，确认全部通过**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py test app01 -v 2
```

Expected:
```
test_create_auto_parses_project_target ... ok
test_str ... ok
test_standard_2digit ... ok
...
Ran 11 tests in X.XXXs
OK
```

- [ ] **Step 3: Commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
git init
git add .
git commit -m "feat: initial BPRdb fork — new data models + passing tests"
```

---

## Task 8：从旧库迁移 lookup 数据

**Goal:** 将 `seq_database_v2` 的 `SeqModule`、`LinkerModule`、`DeliveryModule`、`LmsUser` 数据导入新库。

- [ ] **Step 1: 从旧项目导出 lookup 数据**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_v2
source venv/bin/activate
python manage.py dumpdata app01.SeqModule app01.LinkerModule app01.DeliveryModule \
    --indent 2 > /tmp/lookup_data.json
python manage.py dumpdata app01.LmsUser \
    --indent 2 > /tmp/user_data.json
```

- [ ] **Step 2: 导入到新库**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py loaddata /tmp/lookup_data.json
python manage.py loaddata /tmp/user_data.json
```

Expected: `Installed X object(s) from 1 fixture(s).` 无报错。

- [ ] **Step 3: 验证数据已导入**

```bash
python manage.py shell -c "
from app01.models import SeqModule, LinkerModule, DeliveryModule, LmsUser
print('SeqModule:', SeqModule.objects.count())
print('LinkerModule:', LinkerModule.objects.count())
print('DeliveryModule:', DeliveryModule.objects.count())
print('LmsUser:', LmsUser.objects.count())
"
```

Expected: 各数值与旧库一致，均 > 0。

---

## Task 9：验证开发服务器正常启动

- [ ] **Step 1: 启动开发服务器**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py runserver 8001
```

使用 8001 端口，避免与 seq_database_v2（8000）冲突。

- [ ] **Step 2: 访问 stub 首页**

浏览器访问 `http://127.0.0.1:8001/`

Expected: 页面显示 "BPRdb — Coming Soon"（或 login 重定向）

- [ ] **Step 3: 最终 commit**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
git add -A
git commit -m "feat: BPRdb sub-project A complete — fork, models, migrations, data migration"
```

---

## 完成标准 Checklist

- [ ] `python manage.py check` 无报错
- [ ] `python manage.py test app01` 11 个测试全部通过
- [ ] `SHOW TABLES` 包含 compound/strand/experiment/data_point/experiment_summary
- [ ] SeqModule / LinkerModule / DeliveryModule 数据已从旧库迁移
- [ ] 开发服务器可在 8001 端口正常访问
- [ ] Git 初始 commit 已创建
