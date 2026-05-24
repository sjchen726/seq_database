# 序列上传模板 — 设计文档 2026-05-24

## 背景与目标

为序列上传功能提供标准化的 CSV 模板文件，帮助用户正确填写上传数据。同时将双段序列的中间 linker 写法统一为 `[LK1-L96-LK1]` 括号格式，与首尾 delivery 括号风格保持一致，并在解析层自动标准化。

---

## 括号格式规范

所有 delivery 和 linker 模块统一用 `[...]` 括号表示，括号内以 `-` 为分隔符组合多个模块关键词。

| 位置 | 作用 | 示例 |
|------|------|------|
| 序列开头 | 5' delivery（`delivery5`） | `[invAb]`、`[Vp-invAb]` |
| 序列结尾 | 3' delivery（`delivery3`） | `[Vp]`、`[invAb]` |
| 序列中间 | 双段 linker 分隔符 | `[LK1-L96-LK1]` |

括号内容在上传时原样存入 `delivery5`/`delivery3` 字段；显示层 `get_delivery_colored()` 已有最长匹配 tokenize 逻辑，无需额外改造。

---

## 模板 CSV 文件

**位置**：`static/templates/upload_seq_template.csv`

**必填列**（顺序不限，但列名必须完全匹配）：

| 列名 | 类型 | 说明 |
|------|------|------|
| `Project` | 字符串 | 项目代码，如 `BPR-3T05` |
| `Target` | 字符串 | 靶点名，如 `TTR` |
| `Seq_type` | `SS` / `AS` | SS 行必须在前，AS 紧随其后 |
| `Modify_seq` | 字符串 | 修饰序列，`[xx]` 为 delivery/linker 模块 |
| `Strand_MWs` | 字符串（可空） | 分子量 |
| `Parents` | 字符串（可空） | 亲本序列编号 |
| `Remarks` | 字符串（可空） | 备注 |

**三类示例行**：

```
Project,Target,Seq_type,Modify_seq,Strand_MWs,Parents,Remarks
# === A类：首尾 delivery 括号（单段序列）===
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGmCmAmUm[Vp],,,
BPR-XXXX,GENE,AS,[Vp]AmGmCmAmUmGmAmCmGmUm[invAb],,,
# 复合 delivery（多模块用 - 连接）
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGmCmAmUm[Vp],,,
BPR-XXXX,GENE,AS,[Vp-invAb]AmGmCmAmUmGmAmCmGmUm[invAb],,,
# === B类：双段序列，中间 linker 括号 ===
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGm[LK1-L96-LK1]CmAmUmGmCmAmUm[Vp],,,
BPR-XXXX,GENE,AS,[Vp]GmAmUmGmCmAmUm[LK1-L96-LK1]CmGmAmUmGmCmAm[invAb],,,
# === C类：无 delivery 括号（裸序列）===
BPR-XXXX,GENE,SS,AmUmGmCmAmUmGmCmAmUm,,,
BPR-XXXX,GENE,AS,AmGmCmAmUmGmAmCmGmUm,,,
```

注：实际 CSV 文件不含 `#` 注释行（pandas 不支持），注释内容以空行或说明列替代。

---

## 下载入口

### 视图改动（`app01/views.py`）

在 `upload_delivery_info` 视图 GET 分支新增 `?download=template` 条件，与已有 `repeats`/`unregistered` 下载保持一致风格：

```python
elif request.GET.get('download') == 'template':
    template_path = os.path.join(settings.BASE_DIR, 'static', 'templates', 'upload_seq_template.csv')
    with open(template_path, 'rb') as f:
        response = HttpResponse(f.read(), content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="upload_seq_template.csv"'
        return response
```

### 模板页按钮（`templates/upload_delivery_info.html`）

在上传表单上方加下载入口：

```html
<a href="?download=template" class="ds-btn ds-btn-secondary" style="margin-bottom:12px;">
  ⬇ 下载上传模板
</a>
```

不新增 URL 路由，复用现有 `/upload_delivery_info/` 端点。

---

## 解析层标准化

### 改动位置

`app01/views.py`：新增 `normalize_middle_brackets()` 函数，在 `parse_uploaded_csv()` 返回 DataFrame 之后、`group_sequences()` 执行之前，对每行 `Modify_seq` 调用一次。

### 函数定义

```python
def normalize_middle_brackets(modify_seq: str) -> str:
    """将 Modify_seq 中间的 [linker] 括号块替换为 -linker- dash 格式。
    首位括号（delivery5）和末位括号（delivery3）保持不变，只处理中间块。
    例：[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]
     → [invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]
    """
    blocks = list(re.finditer(r'\[([^\[\]]+)\]', modify_seq))
    if len(blocks) <= 2:
        return modify_seq  # 无中间块，直接返回
    result = modify_seq
    # 从后往前替换，避免字符位移错位；跳过首块和末块
    for block in reversed(blocks[1:-1]):
        inner = block.group(1)
        result = result[:block.start()] + f'-{inner}-' + result[block.end():]
    return result
```

### 调用位置（`upload_delivery_info` 视图 POST 分支）

```python
df = parse_uploaded_csv(request)
# 新增：标准化中间 linker 括号
df['Modify_seq'] = df['Modify_seq'].apply(normalize_middle_brackets)
ss_groups, unpaired_ss_as = group_sequences(df)
```

### 处理结果

标准化后，`clean_seq`（去掉首尾括号）格式与旧 dash 格式完全一致：

```
[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]
  → clean_seq: AmUmGm-LK1-L96-LK1-CmAmUm
```

进入现有 `add_o_to_all_rules_safe()` 无需任何改动。

---

## 文件修改清单

| 文件 | 改动 | 规模 |
|------|------|------|
| `static/templates/upload_seq_template.csv` | 新建模板文件（含 A/B/C 三类示例） | 新建，小 |
| `app01/views.py` | 新增 `normalize_middle_brackets()`；在 POST 分支调用；在 GET 分支加 `?download=template` | 小 |
| `templates/upload_delivery_info.html` | 加「下载模板」按钮 | 小 |

---

## 不在本次范围内

- 旧 `-LK1-L96-LK1-` dash 格式的向后兼容（已明确不支持，旧 CSV 文件需用新格式重新准备）
- 数据库中已有记录不受影响（解析层只影响新上传数据）
- `static/templates/` 目录的 Django staticfiles 配置（开发环境无需额外配置，生产环境需确保该路径在 `STATICFILES_DIRS` 或 `BASE_DIR` 下可访问）
