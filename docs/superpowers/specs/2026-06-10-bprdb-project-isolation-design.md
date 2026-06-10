# BPRdb 项目独立化 — 设计文档

**日期：** 2026-06-10
**范围：** 品牌重命名、环境清理、侧边栏重构、legacy 代码/模板删除、user_profile 最小实现
**前置上下文：** 项目从 seq_database_v2 fork 而来，子项目 A–D 已完成；现需将其彻底隔离为独立的"核酸实验数据管理库（BPRdb）"

---

## 一、品牌与标识

| 位置 | 现在 | 改后 |
|------|------|------|
| `<title>` 标签 | SeqDB | BPRdb |
| 侧边栏 Logo 文字 | SeqDB | BPRdb |
| 侧边栏 Logo 副标题 | Sequence Database | 实验数据管理库 |
| Logo 色块字母 | S | B |
| 登录页标题 | SeqDB | BPRdb |
| 登录页副标题 | RNA 序列管理系统 · 核酸药物研发数据平台 | 核酸实验数据管理库 |
| 登录页"注册"链接 | 存在（指向不存在路由） | 删除 |

---

## 二、设置与环境

| 项目 | 现在 | 改后 |
|------|------|------|
| `bprdb/settings.py` 顶部注释 | `Django settings for bms project` | `Django settings for bprdb` |
| Logger handler 文件名 | `edit_book.log` | `bprdb.log` |
| Logger 名称 | `edit_book_log` | `bprdb_log` |
| `ENTREZ_EMAIL` | `admin@seqdb.local` | `admin@bprdb.local` |
| `app01/views.py` logger 引用 | `getLogger("edit_book_log")` | `getLogger("bprdb_log")` |

---

## 三、侧边栏重构

删除节：序列数据、功能模块、BLAST、模块管理（共 10 个链接全部移除）

保留后的完整结构：

```
BPRdb / 实验数据管理库
─────────────────────
化合物数据
  ▪ 化合物列表  → /compounds/

数据录入
  ▪ 上传实验数据  → /upload/

─────────────────────
[仅 superadmin 可见]
系统
  ▪ 用户管理  → /admin/

─────────────────────
[全部登录用户]
  ▪ 我的资料  → /profile/

─────────────────────
[用户卡片 + 退出按钮]
```

active 判断规则（url_name）：

| 链接 | active 条件 |
|------|-------------|
| 化合物列表 | `compound_list` 或 `compound_detail` |
| 上传实验数据 | `upload` 或 `upload_confirm` 或 `upload_success` |
| 我的资料 | `user_profile` |

---

## 四、视图与路由清理

### 4.1 `bprdb/urls.py` — 删除路由

删除以下 10 条 path：

```python
path('seq/', ...),
path('reg-seq/', ...),
path('register/', ...),
path('delivery/', ...),
path('upload-experiment/', ...),
path('blast/', ...),
path('modules/', ...),
path('seqmodules/', ...),
path('linkermodules/', ...),
# authors/ 保留但改指向 admin
```

`authors/` 路由保留，视图改为 `redirect('/admin/')`。

保留的完整路由表：

```python
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
```

### 4.2 `app01/views.py` — 删除 stub 视图

删除以下 9 个函数（已无路由，也无实际逻辑）：

```
seq_list / reg_seq_list / register_seq / seq_delivery
upload_experiment / multi_blast / module_list / seqmodule_list / linkermodule_list
```

### 4.3 `author_list` — 改为 admin 重定向

```python
@login_required
def author_list(request):
    return redirect('/admin/')
```

### 4.4 注释清理

删除 `views.py` 中一行旧项目引用注释：
```
# ── Coloring utilities (verbatim from seq_database_v2/app01/views.py) ───────
```

### 4.5 `base.html` — 删除无用 JS 加载

删除以下两行：
```html
<script src="/static/js/multi-blast-toolbar.js"></script>
<script src="/static/js/transcript-align-toolbar.js"></script>
```

---

## 五、模板清理

### 5.1 删除（33 个）

以下模板不被任何活跃视图引用，全部删除：

```
seq_list.html
reg_seq_list.html
seq_edit.html
reg_seq_edit.html
register_seq.html
upload_delivery_info.html
upload_experiment.html
multi_blast.html
multi_blast_results.html
blast_results.html
blast_seq_blocks.html
module_list.html
seqmodule_list.html
linkermodule_list.html
edit_module.html
edit_seqmodule.html
edit_linkermodule.html
upload_seqmodules.html
upload_modules.html
upload_prism_preview.html
search_results.html
add_experiment.html
cor_seq.html
confirm_share.html
auth_edit.html
auth_list.html
author_add.html
transcript_align_prepare.html
transcript_align_results.html
register.html
change_password.html
clone_modal.html
_experiment_list_row.html
experiment_detail.html
experiment_detail_single.html
experiment_pivot_table.html
```

### 5.2 保留

```
base.html                        — 主布局
login.html                       — 登录页
index.html                       — 首页（改为重定向）
profile.html                     — 我的资料（复用或重写）
change_password.html             — 修改密码（user_profile 使用）
upload.html                      — 上传表单
confirm_upload_preflight.html    — 上传确认
upload_success.html              — 上传成功
compound_list.html               — 化合物列表
compound_detail.html             — 化合物详情
_seq_group_row.html              — 着色工具（静默保留）
char_block_SS.html               — 着色工具（静默保留）
char_block_AS.html               — 着色工具（静默保留）
```

---

## 六、user_profile 实现

### 视图（`app01/views.py`）

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
    return render(request, 'profile.html', {
        'msg': msg,
        'projects': projects,
    })
```

### 模板（`templates/profile.html`）

现有 `profile.html` 使用 `profile_user` 上下文变量和不存在的 `change_password` URL，**完整重写**。

展示内容：
- 用户名、角色（`user_type`）
- 所属项目权限（pills 形式展示，无项目则显示"全部"）
- 修改密码表单（旧密码 + 新密码 + 确认密码），POST 到 `/profile/` 自身

沿用 design-system.css 的卡片样式，风格与 compound_detail 一致。
`change_password.html` 不再需要，列入删除清单。

---

## 七、index.html / index 视图

`index` 视图改为直接重定向至 `/compounds/`：

```python
@login_required
def index(request):
    return redirect('compound_list')
```

`templates/index.html` 保留为空（重定向不需要模板，但不删除以避免迁移风险）。

---

## 八、文件变更清单

| 文件 | 操作 |
|------|------|
| `bprdb/settings.py` | 修改注释、logger 名称、文件名、ENTREZ_EMAIL |
| `app01/views.py` | 删除 9 个 stub 视图；改 `author_list`；改 `index`；改 logger 名；删旧项目注释；实现 `user_profile` |
| `bprdb/urls.py` | 删除 9 条 legacy 路由 |
| `templates/base.html` | 品牌重命名；侧边栏重构；删除 2 行 JS |
| `templates/login.html` | 品牌重命名；改副标题；删除注册链接 |
| `templates/profile.html` | 重写（或覆盖）为最小资料页 |
| `templates/index.html` | 保留文件，内容清空（视图已重定向，模板不再被渲染） |
| `templates/*.html`（33 个） | 删除 |

---

## 九、范围边界

- **着色工具函数**（`get_delivery_colored`、`get_modify_seq_colored` 等）和模型（`SeqModule`、`LinkerModule`、`DeliveryModule`）**保留但不挂路由**，不做任何改动
- `app01/transcript_align.py` 和 `app01/prism_upload.py` **保留**（可能被 upload pipeline 间接依赖，不动）
- 本次**不新增功能**，不改数据模型，不写迁移
- **不涉及**任何 upload 流程的逻辑改动
