---
name: cross-project-sample-sharing
description: Design spec for cross-project sample sharing in seq_database — allow one Delivery record to belong to multiple projects while keeping all IDs unchanged
metadata:
  type: project
---

# 跨项目样品共享 — 设计规范

## 背景

当前 `Delivery` 模型的 `project` 是单值字段，一条样品记录只能归属于一个项目。但实际业务中，同一个样品（相同的 `linker_seq` + `delivery5` + `delivery3`）可能同时用于多个项目（如 3T03 和 350）。当前系统无法表达这种归属关系，用户需要重复上传同一条样品，导致数据冗余和 ID 不一致。

## 目标

让一条 `Delivery` 记录可以同时属于多个项目，满足以下约束：

- 所有核心 ID（`rm_code`、`duplex_id`、`delivery_id`）保持不变
- 在任一所属项目中均可查看
- 编辑时两边同步（共用同一条数据库记录）
- 编辑权限收紧：只有拥有所有相关项目权限的用户才能编辑
- 上传时检测重复并引导用户共享

## 判重规则

两条样品视为"相同"当且仅当以下三个字段完全一致：

- `linker_seq`（修饰序列）
- `delivery5`（5' ligand）
- `delivery3`（3' ligand）

## 数据库结构

### 新增模型：`DeliveryProject`

```python
class DeliveryProject(models.Model):
    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.CASCADE,
        related_name='project_links',
    )
    project_code = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('delivery', 'project_code')
        indexes = [
            models.Index(fields=['project_code']),
            models.Index(fields=['delivery']),
        ]
```

### `Delivery` 保持不变

`Delivery.project` 字段保留，语义变为**主项目**（首次注册的项目）。新增的 `DeliveryProject` 表承担所有项目归属查询。

### 数据迁移

- 为每条现有 `Delivery` 生成一条 `DeliveryProject(delivery=d, project_code=d.project)`
- 通过 Django 信号（`post_save`）确保新建 `Delivery` 时自动创建对应的 `DeliveryProject` 记录，保持 `Delivery.project` 和 `DeliveryProject` 的一致性

## 查重与提示流程

### 单条上传

1. 用户填写表单并提交
2. 后端查询：
   ```python
   existing = Delivery.objects.filter(
       linker_seq=form_data['linker_seq'],
       delivery5=form_data['delivery5'],
       delivery3=form_data['delivery3'],
   ).exclude(
       project_links__project_code=target_project,
   ).first()
   ```
3. 若命中 `existing`：
   - 返回 JSON `{"duplicate": true, "existing_projects": [...], "delivery_id": <id>, ...}`
   - 前端弹窗展示冲突项目 + 样品 ID + 序列信息 + 两个 ligand
   - 用户选"共享到当前项目" → 前端再次提交，带 `share_from_delivery=<id>` 参数
   - 后端创建 `DeliveryProject(delivery=<id>, project_code=target_project)`，不新建 Delivery
4. 未命中或用户选"取消" → 正常新建 Delivery + DeliveryProject

### 批量上传（CSV/Excel）

1. 后端解析文件所有行，对每行执行上述查重
2. 汇总所有重复项为列表：
   ```python
   duplicates = [
       {
           "row_index": 5,
           "target_project": "350",
           "existing_projects": ["3T03"],
           "delivery_id": 123,
           "sequence_info": "<上传文件中该行的原始序列信息>",
           "delivery5": "GalNAc",
           "delivery3": "Chol",
       },
       ...
   ]
   ```
3. 返回确认页面，展示表格：

   | 行号 | 目标项目 | 冲突项目 | 样品 ID | 序列信息 | 5' Ligand | 3' Ligand | 操作 |
   |------|----------|----------|---------|----------|-----------|-----------|------|

   序列信息列展示上传文件中的原始序列（不展示 `linker_seq`），以便用户对照源文件判断。

4. 表格底部提供 [全部共享] [全部跳过] [提交选择] 按钮
5. 用户提交后：
   - "共享"的行 → 创建 `DeliveryProject` 关联（不新建 Delivery）
   - "跳过"的行 → **不导入到目标项目**。用户需在上传文件中手动处理（删除或修改后重新上传）
6. 返回结果摘要："成功共享 N 条，跳过 M 条"

> **关于"作为新样品注册"选项：** 本设计**不支持**此选项。因为判重规则规定"`linker_seq` + `delivery5` + `delivery3` 三者完全一致的样品视为同一样品"，允许"作为新样品注册"会导致数据库中出现逻辑上相同但 ID 不同的重复记录，违反 uniqueness 原则。如用户确实需要以"新样品"身份录入，应修改 `linker_seq` 或任一 ligand 使其不重复。

## 权限控制

### 编辑权限规则

只有同时拥有某条 Delivery 所属**所有项目**权限的用户才能编辑它；单一项目权限的用户只能查看。

```python
def user_can_edit_delivery(user, delivery):
    if user.is_superuser or user.user_type in ['admin', 'superadmin']:
        return True
    delivery_projects = set(
        delivery.project_links.values_list('project_code', flat=True)
    )
    user_projects = set(
        (user.permissions_project or '').split(',')
    )
    user_projects.discard('')
    return delivery_projects.issubset(user_projects)
```

### 查询逻辑改动

所有涉及项目筛选的查询，从 `Delivery.project` 改为通过 `DeliveryProject` 查询：

```python
# 旧
Delivery.objects.filter(project='3T03')
# 新
Delivery.objects.filter(project_links__project_code='3T03').distinct()
```

### 视图层应用

- `seq_list`：用户能看到所有有权限的项目的样品（只要拥有任一相关项目权限即可看）
- `/edit_seq/`：提交时调用 `user_can_edit_delivery()`，无权限返回 403
- 编辑表单顶部展示当前样品所属的所有项目；若无编辑权限，所有输入框设为 `readonly` 并展示提示文字

## UI 改动

### 单条上传的弹窗

```
该样品已存在于项目 3T03

样品 ID: 3T03-001
序列信息: AmsCmsUm...（前 20 字符）
5' Ligand: GalNAc
3' Ligand: Chol

是否将该样品共享到当前项目 350？

[取消] [共享到 350]
```

### 批量上传的确认表

- 表格列：行号、目标项目、冲突项目、样品 ID、序列信息（来自上传文件）、5' Ligand、3' Ligand、操作
- 操作列为下拉选择：`共享 / 跳过`（默认 `共享`）
- 底部按钮：`[全部共享] [全部跳过] [提交选择]`
- 提交后显示结果摘要

### 编辑权限提示

- 有编辑权限：顶部显示"该样品属于项目：3T03, 350"
- 无编辑权限：顶部显示"该样品属于项目：3T03, 350（你只有部分项目权限，仅可查看）" + 所有输入框设为 `readonly`

## 边界情况

| 情况 | 处理方式 |
|------|---------|
| 新建 Delivery 时是否需要手动创建 DeliveryProject | 不需要，由 `post_save` 信号自动创建 |
| 同一 Delivery 重复共享到同一项目 | `unique_together` 约束拒绝插入，提示"已在该项目中" |
| 删除 Delivery | 级联删除所有 DeliveryProject（`on_delete=CASCADE`） |
| 取消共享（从某个项目移除） | **不支持**。一旦共享，无法单独从某项目移除，除非删除整条 Delivery |
| 修改主项目 | **不支持**。`Delivery.project` 字段一旦创建不可改 |
| 用户无任何相关项目权限 | `seq_list` 查询自动过滤，用户看不到该样品 |

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `app01/models.py` | 新增 `DeliveryProject` 模型；新增 `Delivery` `post_save` 信号处理器 |
| `app01/migrations/` | 新增迁移：建表 + 数据回填（为所有现有 Delivery 生成 DeliveryProject 记录） |
| `app01/views.py` | 改动所有 `Delivery.objects.filter(project=...)` 为 `project_links__project_code=...`；新增查重逻辑与共享接口；新增 `user_can_edit_delivery()` 辅助函数 |
| `templates/` | 新增单条上传查重弹窗、批量上传确认表；编辑表单顶部显示所属项目与权限提示 |
| `static/js/` | 新增查重弹窗交互逻辑 |

## 非目标

- 本次不实现实验数据录入（批次、细胞系、活性等），该功能作为独立 spec 后续设计
- 本次不改动 Duplex/Sequence 模型本身的归属关系，只改 Delivery 的项目归属
- 不实现跨项目样品的合并/拆分工具
