# BPRdb 项目独立化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 BPRdb 从 seq_database_v2 的 fork 状态彻底独立：品牌重命名为"BPRdb / 核酸实验数据管理库"、清理遗留视图/路由/模板、修复环境配置、实现最小 user_profile 页面。

**Architecture:** 改动分六个独立任务依次执行，每完成一个即提交。唯一有新代码的任务是 Task 3（user_profile），采用 TDD。其余任务均为删除或文本替换，不引入新依赖。

**Tech Stack:** Django 5.1, Python 3.10, design-system.css（已有）

---

## 文件变更一览

| 文件 | 操作 |
|------|------|
| `bprdb/settings.py` | 修改注释、logger 名称、文件名、ENTREZ_EMAIL |
| `app01/views.py` | 改 logger 引用；删 9 个 stub 视图；改 `index` 和 `author_list`；实现 `user_profile` |
| `bprdb/urls.py` | 删除 9 条 legacy 路由 |
| `templates/base.html` | 品牌重命名；侧边栏重构；删 2 行 JS |
| `templates/login.html` | 品牌重命名；改副标题；删注册链接 |
| `templates/profile.html` | 完整重写 |
| `templates/*.html`（35 个） | 删除 |
| `app01/tests.py` | 追加 `UserProfileViewTest`（6 个用例） |

---

## Task 1：Settings & 环境变量清理

**Files:**
- Modify: `bprdb/settings.py`
- Modify: `app01/views.py`（logger 引用）

---

- [ ] **Step 1：修改 `bprdb/settings.py` 第 2 行注释**

将：
```python
Django settings for bms project.
```
改为：
```python
Django settings for bprdb.
```

- [ ] **Step 2：修改 `bprdb/settings.py` 的 LOGGING 块**

找到 LOGGING 配置（约第 144–163 行），将：
```python
'handlers': {
    'file': {
        'level': 'INFO',
        'class': 'logging.FileHandler',
        'filename': 'edit_book.log',
    },
},
'loggers': {
    'edit_book_log':{
        'handlers': ['file'],
        'level': 'INFO',
        'propagate': True,
    }
},
```
改为：
```python
'handlers': {
    'file': {
        'level': 'INFO',
        'class': 'logging.FileHandler',
        'filename': 'bprdb.log',
    },
},
'loggers': {
    'bprdb_log': {
        'handlers': ['file'],
        'level': 'INFO',
        'propagate': True,
    }
},
```

- [ ] **Step 3：修改 `bprdb/settings.py` 的 ENTREZ_EMAIL**

将：
```python
ENTREZ_EMAIL = 'admin@seqdb.local'
```
改为：
```python
ENTREZ_EMAIL = 'admin@bprdb.local'
```

- [ ] **Step 4：修改 `app01/views.py` 第 19 行 logger 引用**

将：
```python
logger = logging.getLogger("edit_book_log")
```
改为：
```python
logger = logging.getLogger("bprdb_log")
```

- [ ] **Step 5：确认 Django 能正常启动**

```bash
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
python manage.py check
```

期望：`System check identified no issues (0 silenced).`

- [ ] **Step 6：提交**

```bash
git add bprdb/settings.py app01/views.py
git commit -m "fix: rename logger to bprdb_log, update log filename and ENTREZ_EMAIL"
```

---

## Task 2：URL & 视图清理

**Files:**
- Modify: `bprdb/urls.py`
- Modify: `app01/views.py`

---

- [ ] **Step 1：删除 `bprdb/urls.py` 中的 9 条 legacy 路由**

将整个 `urlpatterns` 列表替换为：

```python
from django.contrib import admin
from django.urls import path
from app01 import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('upload/', views.upload_view, name='upload'),
    path('upload/confirm/', views.upload_confirm_view, name='upload_confirm'),
    path('upload/success/', views.upload_success_view, name='upload_success'),
    path('compounds/', views.compound_list, name='compound_list'),
    path('compounds/<str:compound_id>/', views.compound_detail, name='compound_detail'),
    path('authors/', views.author_list, name='author_list'),
    path('profile/', views.user_profile, name='user_profile'),
]
```

- [ ] **Step 2：删除 `app01/views.py` 中旧项目引用注释（约第 46 行）**

找到并删除这一行：
```python
# ── Coloring utilities (verbatim from seq_database_v2/app01/views.py) ───────
```

- [ ] **Step 3：修改 `app01/views.py` 中的 `index` 视图**

将：
```python
@login_required
def index(request):
    return render(request, "index.html")
```
改为：
```python
@login_required
def index(request):
    return redirect('compound_list')
```

- [ ] **Step 4：删除 `app01/views.py` 中的 9 个 stub 视图**

找到并整体删除以下函数（约第 732–784 行，每个函数 4–5 行）：

```python
@login_required
def seq_list(request):
    return render(request, 'index.html', {})

@login_required
def reg_seq_list(request):
    return render(request, 'index.html', {})

@login_required
def register_seq(request):
    return render(request, 'index.html', {})

@login_required
def seq_delivery(request):
    return render(request, 'index.html', {})

@login_required
def upload_experiment(request):
    return render(request, 'index.html', {})

@login_required
def multi_blast(request):
    return render(request, 'index.html', {})

@login_required
def module_list(request):
    return render(request, 'index.html', {})

@login_required
def seqmodule_list(request):
    return render(request, 'index.html', {})

@login_required
def linkermodule_list(request):
    return render(request, 'index.html', {})
```

- [ ] **Step 5：修改 `author_list` 视图**

将：
```python
@login_required
def author_list(request):
    return render(request, 'index.html', {})
```
改为：
```python
@login_required
def author_list(request):
    return redirect('/admin/')
```

- [ ] **Step 6：运行测试，确认无回归**

```bash
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py test app01 --verbosity=0 --keepdb
```

期望：`Ran 79 tests ... OK`

- [ ] **Step 7：提交**

```bash
git add bprdb/urls.py app01/views.py
git commit -m "refactor: remove legacy stub views and routes, redirect index to compound_list"
```

---

## Task 3：user_profile 视图 + 模板（TDD）

**Files:**
- Modify: `app01/tests.py`（追加 `UserProfileViewTest`）
- Modify: `app01/views.py`（实现 `user_profile`）
- Modify: `templates/profile.html`（完整重写）

---

### 写测试

- [ ] **Step 1：在 `app01/tests.py` 末尾追加 `UserProfileViewTest`**

```python
# ---- UserProfileViewTest ----
class UserProfileViewTest(TestCase):
    def setUp(self):
        self.user = LmsUser.objects.create_user(
            username='profiler', password='testpass123',
            user_type='admin', permissions_project='3M03,4A01'
        )
        self.client.login(username='profiler', password='testpass123')

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get('/profile/')
        self.assertRedirects(resp, '/login/?next=/profile/',
                             fetch_redirect_response=False)

    def test_returns_200(self):
        resp = self.client.get('/profile/')
        self.assertEqual(resp.status_code, 200)

    def test_context_has_projects(self):
        resp = self.client.get('/profile/')
        self.assertEqual(resp.context['projects'], ['3M03', '4A01'])

    def test_password_change_success(self):
        resp = self.client.post('/profile/', {
            'old_password': 'testpass123',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['msg'][0], 'success')
        # 新密码可用
        self.assertTrue(
            LmsUser.objects.get(username='profiler').check_password('newpass456')
        )

    def test_password_change_wrong_old(self):
        resp = self.client.post('/profile/', {
            'old_password': 'wrongpass',
            'new_password': 'newpass456',
            'confirm_password': 'newpass456',
        })
        self.assertEqual(resp.context['msg'][0], 'error')
        # 原密码未变
        self.assertTrue(
            LmsUser.objects.get(username='profiler').check_password('testpass123')
        )

    def test_password_change_mismatch(self):
        resp = self.client.post('/profile/', {
            'old_password': 'testpass123',
            'new_password': 'newpass456',
            'confirm_password': 'different789',
        })
        self.assertEqual(resp.context['msg'][0], 'error')
```

- [ ] **Step 2：运行测试，确认失败**

```bash
source /Users/gutou/Projects/seq_web/seq_database_v2/venv/bin/activate
python manage.py test app01.tests.UserProfileViewTest --verbosity=1 --keepdb
```

期望：`ERRORS` 或 `FAIL`（视图尚未实现，context 缺少 `msg`/`projects`）

### 实现视图

- [ ] **Step 3：在 `app01/views.py` 中将 `user_profile` stub 替换为完整实现**

找到：
```python
@login_required
def user_profile(request):
    return render(request, 'index.html', {})
```

替换为：
```python
@login_required
def user_profile(request):
    user = request.user
    msg = None
    if request.method == 'POST':
        old_pw = request.POST.get('old_password', '')
        new_pw = request.POST.get('new_password', '')
        confirm_pw = request.POST.get('confirm_password', '')
        if not user.check_password(old_pw):
            msg = ('error', '旧密码不正确')
        elif new_pw != confirm_pw:
            msg = ('error', '两次输入的新密码不一致')
        elif len(new_pw) < 6:
            msg = ('error', '新密码长度不能少于 6 位')
        else:
            user.set_password(new_pw)
            user.save()
            login(request, user)
            msg = ('success', '密码已修改')
    projects = [p.strip() for p in user.permissions_project.split(',') if p.strip()]
    return render(request, 'profile.html', {'msg': msg, 'projects': projects})
```

### 运行测试确认通过

- [ ] **Step 4：运行 UserProfileViewTest**

```bash
python manage.py test app01.tests.UserProfileViewTest --verbosity=1 --keepdb
```

期望：`OK (6 tests)`（此时 profile.html 尚未改写，部分测试可能因模板缺失 context 变量而失败；若全部通过则跳过 Step 5）

### 重写模板

- [ ] **Step 5：完整重写 `templates/profile.html`**

```html
{% extends "base.html" %}
{% block page_title %} — 我的资料{% endblock %}

{% block topbar_content %}
  <span class="ds-topbar-title">我的资料</span>
{% endblock %}

{% block content %}
<div style="max-width:560px;margin:0 auto;">

  {# 消息提示 #}
  {% if msg %}
  <div style="margin-bottom:14px;padding:10px 14px;border-radius:7px;font-size:13px;
              {% if msg.0 == 'success' %}background:#f0fdf4;border:1px solid #86efac;color:#166534;
              {% else %}background:#fef2f2;border:1px solid #fca5a5;color:#991b1b;{% endif %}">
    {{ msg.1 }}
  </div>
  {% endif %}

  {# 用户信息卡片 #}
  <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;
              padding:20px 24px;margin-bottom:16px;">
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;">
      <div style="width:48px;height:48px;border-radius:50%;
                  background:linear-gradient(135deg,#1e40af,#3b82f6);
                  color:#fff;font-size:20px;font-weight:700;
                  display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        {{ request.user.username|first|upper }}
      </div>
      <div>
        <div style="font-size:16px;font-weight:700;color:#1e293b;">
          {{ request.user.username }}
        </div>
        <div style="font-size:12px;color:#64748b;margin-top:2px;">
          {{ request.user.email|default:"（未设置邮箱）" }}
        </div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:13px;align-items:baseline;">
      <span style="color:#64748b;font-weight:500;">角色</span>
      <span style="color:#1e293b;font-weight:600;">{{ request.user.user_type }}</span>

      <span style="color:#64748b;font-weight:500;">项目权限</span>
      <div style="display:flex;flex-wrap:wrap;gap:5px;">
        {% if projects %}
          {% for p in projects %}
          <span style="background:#eff6ff;color:#1d4ed8;font-size:11px;font-weight:600;
                       border-radius:10px;padding:2px 9px;border:1px solid #bfdbfe;">
            {{ p }}
          </span>
          {% endfor %}
        {% else %}
          <span style="color:#94a3b8;font-size:12px;">全部项目</span>
        {% endif %}
      </div>
    </div>
  </div>

  {# 修改密码 #}
  <div style="background:white;border:1px solid #e2e8f0;border-radius:8px;padding:20px 24px;">
    <div style="font-size:13px;font-weight:700;color:#374151;margin-bottom:14px;
                border-bottom:1px solid #f1f5f9;padding-bottom:8px;">
      修改密码
    </div>
    <form method="POST" action="{% url 'user_profile' %}">
      {% csrf_token %}
      <div style="margin-bottom:12px;">
        <label style="display:block;font-size:12px;font-weight:500;color:#374151;margin-bottom:4px;">
          旧密码
        </label>
        <input type="password" name="old_password" required
               style="width:100%;box-sizing:border-box;padding:7px 10px;
                      border:1px solid #d1d5db;border-radius:6px;font-size:13px;">
      </div>
      <div style="margin-bottom:12px;">
        <label style="display:block;font-size:12px;font-weight:500;color:#374151;margin-bottom:4px;">
          新密码（至少 6 位）
        </label>
        <input type="password" name="new_password" required
               style="width:100%;box-sizing:border-box;padding:7px 10px;
                      border:1px solid #d1d5db;border-radius:6px;font-size:13px;">
      </div>
      <div style="margin-bottom:16px;">
        <label style="display:block;font-size:12px;font-weight:500;color:#374151;margin-bottom:4px;">
          确认新密码
        </label>
        <input type="password" name="confirm_password" required
               style="width:100%;box-sizing:border-box;padding:7px 10px;
                      border:1px solid #d1d5db;border-radius:6px;font-size:13px;">
      </div>
      <button type="submit"
              style="background:#1e40af;color:white;border:none;border-radius:6px;
                     padding:8px 20px;font-size:13px;font-weight:600;cursor:pointer;">
        修改密码
      </button>
    </form>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 6：运行全部测试，确认无回归**

```bash
python manage.py test app01 --verbosity=0 --keepdb
```

期望：`Ran 85 tests ... OK`（79 + 6 = 85）

- [ ] **Step 7：提交**

```bash
git add app01/tests.py app01/views.py templates/profile.html
git commit -m "feat: implement user_profile view with password change + 6 tests"
```

---

## Task 4：品牌重命名 + 侧边栏重构（base.html）

**Files:**
- Modify: `templates/base.html`

---

- [ ] **Step 1：修改 `<title>` 标签**

将：
```html
<title>SeqDB{% block page_title %}{% endblock %}</title>
```
改为：
```html
<title>BPRdb{% block page_title %}{% endblock %}</title>
```

- [ ] **Step 2：修改侧边栏 Logo 区域**

找到：
```html
<div class="ds-sidebar-logo">
  <div class="ds-logo-mark">S</div>
  <div>
    <div class="ds-logo-text">SeqDB</div>
    <div class="ds-logo-tagline">Sequence Database</div>
  </div>
</div>
```

替换为：
```html
<div class="ds-sidebar-logo">
  <div class="ds-logo-mark">B</div>
  <div>
    <div class="ds-logo-text">BPRdb</div>
    <div class="ds-logo-tagline">实验数据管理库</div>
  </div>
</div>
```

- [ ] **Step 3：替换整个侧边栏导航内容（`<nav class="ds-sidebar">` 内部）**

将 `<nav class="ds-sidebar">` 内的全部内容（Logo 区域之后、到 `</nav>` 之前）替换为：

```html
    {% if request.user.is_authenticated %}

    <div class="ds-nav-section">化合物数据</div>
    <a href="{% url 'compound_list' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'compound_list' or request.resolver_match.url_name == 'compound_detail' %}active{% endif %}">
      <i class="bi bi-table ds-nav-icon"></i> 化合物列表
    </a>

    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">数据录入</div>
    <a href="{% url 'upload' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'upload' or request.resolver_match.url_name == 'upload_confirm' or request.resolver_match.url_name == 'upload_success' %}active{% endif %}">
      <i class="bi bi-file-earmark-arrow-up ds-nav-icon"></i> 上传实验数据
    </a>

    {% if request.user.user_type == 'superadmin' or request.user.is_superuser %}
    <div class="ds-nav-divider"></div>
    <div class="ds-nav-section">系统</div>
    <a href="/admin/" class="ds-nav-item">
      <i class="bi bi-people ds-nav-icon"></i> 用户管理
    </a>
    {% endif %}

    <div class="ds-nav-divider"></div>
    <a href="{% url 'user_profile' %}" class="ds-nav-item {% if request.resolver_match.url_name == 'user_profile' %}active{% endif %}">
      <i class="bi bi-person-circle ds-nav-icon"></i> 我的资料
    </a>

    {% endif %}{# end is_authenticated #}

    <div class="ds-sidebar-footer">
      <div class="ds-user-card" style="justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:10px;">
          <div class="ds-user-avatar">{{ request.user.username|first|upper }}</div>
          <div>
            <div class="ds-user-name">{{ request.user.username }}</div>
            <div class="ds-user-role">
              <span class="ds-online-dot"></span>
              {{ request.user.user_type|default:"user" }}
            </div>
          </div>
        </div>
        {% if request.user.is_authenticated %}
        <form method="POST" action="{% url 'logout' %}" style="margin:0;">
          {% csrf_token %}
          <button type="submit" title="退出登录"
                  style="background:none;border:none;cursor:pointer;padding:4px 6px;
                         border-radius:6px;color:#94a3b8;display:flex;align-items:center;"
                  onmouseover="this.style.color='#ef4444';this.style.background='#fef2f2'"
                  onmouseout="this.style.color='#94a3b8';this.style.background='none'">
            <i class="bi bi-box-arrow-right" style="font-size:16px;"></i>
          </button>
        </form>
        {% endif %}
      </div>
    </div>
```

- [ ] **Step 4：删除 base.html 底部两行无用 JS**

找到并删除：
```html
<script src="/static/js/multi-blast-toolbar.js"></script>
<script src="/static/js/transcript-align-toolbar.js"></script>
```

- [ ] **Step 5：运行全部测试，确认无回归**

```bash
python manage.py test app01 --verbosity=0 --keepdb
```

期望：`Ran 85 tests ... OK`

- [ ] **Step 6：提交**

```bash
git add templates/base.html
git commit -m "feat: rebrand to BPRdb, rebuild sidebar with bprdb-only navigation"
```

---

## Task 5：登录页清理（login.html）

**Files:**
- Modify: `templates/login.html`

---

- [ ] **Step 1：修改 `<title>` 标签**

将：
```html
<title>SeqDB — 登录</title>
```
改为：
```html
<title>BPRdb — 登录</title>
```

- [ ] **Step 2：修改 Logo 色块字母**

将：
```html
<div class="ds-logo-mark">S</div>
```
改为：
```html
<div class="ds-logo-mark">B</div>
```

- [ ] **Step 3：修改 Logo 文字和副标题**

将：
```html
<div class="ds-logo-text">SeqDB</div>
<div class="ds-logo-tagline">Sequence Database</div>
```
改为：
```html
<div class="ds-logo-text">BPRdb</div>
<div class="ds-logo-tagline">实验数据管理库</div>
```

- [ ] **Step 4：修改登录页副标题**

将：
```html
<div class="ds-standalone-sub">RNA 序列管理系统 · 核酸药物研发数据平台</div>
```
改为：
```html
<div class="ds-standalone-sub">核酸实验数据管理库</div>
```

- [ ] **Step 5：删除"注册"链接**

找到并删除：
```html
<div style="text-align:center;margin-top:16px;font-size:13px;color:#64748b;">
  没有账户？<a href="/register" style="color:#2563eb;text-decoration:none;font-weight:500;">注册</a>
</div>
```

- [ ] **Step 6：运行全部测试，确认无回归**

```bash
python manage.py test app01 --verbosity=0 --keepdb
```

期望：`Ran 85 tests ... OK`

- [ ] **Step 7：提交**

```bash
git add templates/login.html
git commit -m "feat: rebrand login page to BPRdb, remove register link"
```

---

## Task 6：删除 legacy 模板

**Files:**
- Delete：35 个模板文件

---

- [ ] **Step 1：批量删除所有 legacy 模板**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb/templates

rm \
  seq_list.html \
  reg_seq_list.html \
  seq_edit.html \
  reg_seq_edit.html \
  register_seq.html \
  upload_delivery_info.html \
  upload_experiment.html \
  multi_blast.html \
  multi_blast_results.html \
  blast_results.html \
  blast_seq_blocks.html \
  module_list.html \
  seqmodule_list.html \
  linkermodule_list.html \
  edit_module.html \
  edit_seqmodule.html \
  edit_linkermodule.html \
  upload_seqmodules.html \
  upload_modules.html \
  upload_prism_preview.html \
  search_results.html \
  add_experiment.html \
  cor_seq.html \
  confirm_share.html \
  auth_edit.html \
  auth_list.html \
  author_add.html \
  transcript_align_prepare.html \
  transcript_align_results.html \
  register.html \
  change_password.html \
  clone_modal.html \
  _experiment_list_row.html \
  experiment_detail.html \
  experiment_detail_single.html \
  experiment_pivot_table.html
```

- [ ] **Step 2：确认 Django 系统检查无错误**

```bash
cd /Users/gutou/Projects/seq_web/seq_database_bprdb
python manage.py check
```

期望：`System check identified no issues (0 silenced).`

- [ ] **Step 3：运行全部测试，确认无回归**

```bash
python manage.py test app01 --verbosity=0 --keepdb
```

期望：`Ran 85 tests ... OK`

- [ ] **Step 4：确认剩余模板列表**

```bash
ls templates/
```

期望保留的文件：
```
_seq_group_row.html
base.html
char_block_AS.html
char_block_SS.html
compound_detail.html
compound_list.html
confirm_upload_preflight.html
index.html
login.html
profile.html
upload.html
upload_success.html
```

- [ ] **Step 5：提交**

```bash
git add -A templates/
git commit -m "chore: delete 35 legacy templates from seq_database_v2"
```
