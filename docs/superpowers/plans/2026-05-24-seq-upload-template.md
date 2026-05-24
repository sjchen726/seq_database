# 序列上传模板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供标准化的序列上传 CSV 模板文件，并更新解析层支持中间括号 `[LK1-L96-LK1]` linker 写法。

**Architecture:** 三部分：① 新建 `static/templates/upload_seq_template.csv` 静态模板文件；② 在 `app01/views.py` 添加 `normalize_middle_brackets()` 预处理函数并在 POST 分支调用、在 GET 分支加 `?download=template` 下载处理；③ 更新 `templates/upload_delivery_info.html` 替换旧示例模板下载链接。

**Tech Stack:** Django 5.1, Python 3.10, pandas, re（标准库）

---

## 文件修改清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `static/templates/upload_seq_template.csv` | 新建 | A/B/C 三类示例行模板 |
| `app01/views.py` | 修改 | 新增函数 + GET/POST 两处改动 |
| `app01/tests.py` | 修改 | `normalize_middle_brackets` 单元测试 |
| `templates/upload_delivery_info.html` | 修改 | 替换旧示例下载链接为新模板链接 |

---

### Task 1: 创建静态模板 CSV 文件

**Files:**
- Create: `static/templates/upload_seq_template.csv`

- [ ] **Step 1: 创建目录并写入模板文件**

```bash
mkdir -p /path/to/project/static/templates
```

文件内容（7 列，SS 行紧跟 AS 行为一对，Remarks 字段供备注用）：

```
Project,Target,Seq_type,Modify_seq,Strand_MWs,Parents,Remarks
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGmCmAmUm[Vp],,,A类-单段-单delivery
BPR-XXXX,GENE,AS,[Vp]AmGmCmAmUmGmAmCmGmUm[invAb],,,A类-单段-单delivery
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGmCmAmUm[Vp-invAb],,,A类-单段-复合delivery
BPR-XXXX,GENE,AS,[Vp-invAb]AmGmCmAmUmGmAmCmGmUm[invAb],,,A类-单段-复合delivery
BPR-XXXX,GENE,SS,[invAb]AmUmGmCmAmUmGm[LK1-L96-LK1]CmAmUmGmCmAmUm[Vp],,,B类-双段-linker括号
BPR-XXXX,GENE,AS,[Vp]GmAmUmGmCmAmUm[LK1-L96-LK1]CmGmAmUmGmCmAm[invAb],,,B类-双段-linker括号
BPR-XXXX,GENE,SS,AmUmGmCmAmUmGmCmAmUm,,,C类-无delivery括号
BPR-XXXX,GENE,AS,AmGmCmAmUmGmAmCmGmUm,,,C类-无delivery括号
```

注意事项（写进 Remarks 列，不用 # 注释，pandas 无法解析注释行）：
- `Project`：项目代码，如 `BPR-3T05`
- `Seq_type`：只能是 `SS` 或 `AS`；SS 必须在前，AS 紧随其后
- `Modify_seq`：`[模块名]` 括号中为 delivery/linker，多模块用 `-` 间隔，如 `[Vp-invAb]`
- `Strand_MWs`、`Parents`、`Remarks` 可留空

- [ ] **Step 2: 确认文件存在且内容正确**

```bash
cat static/templates/upload_seq_template.csv
```

预期：8 行数据行 + 1 行表头，共 9 行。

- [ ] **Step 3: Commit**

```bash
git add static/templates/upload_seq_template.csv
git commit -m "feat: add upload_seq_template.csv with A/B/C sequence format examples"
```

---

### Task 2: 新增 normalize_middle_brackets() 函数及单元测试

**Files:**
- Modify: `app01/views.py`（在 `parse_uploaded_csv` 前插入，约第 1222 行）
- Modify: `app01/tests.py`

- [ ] **Step 1: 在 app01/tests.py 写失败测试**

打开 `app01/tests.py`，替换全部内容为：

```python
from django.test import TestCase
from app01.views import normalize_middle_brackets


class NormalizeMiddleBracketsTests(TestCase):

    def test_no_brackets_unchanged(self):
        seq = "AmUmGmCmAmUmGm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_only_delivery5_unchanged(self):
        seq = "[invAb]AmUmGmCmAmUmGm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_only_delivery3_unchanged(self):
        seq = "AmUmGmCmAmUmGm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_delivery5_and_3_unchanged(self):
        seq = "[invAb]AmUmGmCmAmUmGm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_middle_bracket_normalized(self):
        seq = "[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]"
        expected = "[invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), expected)

    def test_middle_bracket_no_delivery(self):
        # 无首尾括号，只有一个括号 → 只有1个块，<= 2，不处理
        seq = "AmUmGm[LK1-L96-LK1]CmAmUm"
        # 只有1个括号块，不满足>2条件，原样返回
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_delivery5_and_middle_bracket(self):
        # 首括号 + 中间括号，共2个，不足3个，不处理中间
        seq = "[invAb]AmUmGm[LK1-L96-LK1]CmAmUm"
        self.assertEqual(normalize_middle_brackets(seq), seq)

    def test_three_brackets_middle_normalized(self):
        # 3个括号：首 + 中 + 尾 → 中间被替换
        seq = "[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]"
        expected = "[invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]"
        self.assertEqual(normalize_middle_brackets(seq), expected)

    def test_compound_delivery_preserved(self):
        # 首尾为复合 delivery，中间 linker 被替换
        seq = "[Vp-invAb]AmUmGm[LK1-L96-LK1]CmAmUm[invAb]"
        expected = "[Vp-invAb]AmUmGm-LK1-L96-LK1-CmAmUm[invAb]"
        self.assertEqual(normalize_middle_brackets(seq), expected)

    def test_empty_string(self):
        self.assertEqual(normalize_middle_brackets(""), "")

    def test_multiple_middle_brackets(self):
        # 4个括号：首 + 中1 + 中2 + 尾 → 中1和中2都被替换
        seq = "[d5]AAA[LK1]BBB[LK2]CCC[d3]"
        expected = "[d5]AAA-LK1-BBB-LK2-CCC[d3]"
        self.assertEqual(normalize_middle_brackets(seq), expected)
```

- [ ] **Step 2: 运行测试，确认全部失败（函数未定义）**

```bash
source venv/bin/activate
python manage.py test app01.tests.NormalizeMiddleBracketsTests -v 2
```

预期：`ImportError: cannot import name 'normalize_middle_brackets' from 'app01.views'`

- [ ] **Step 3: 在 views.py 中添加函数（parse_uploaded_csv 之前）**

打开 `app01/views.py`，找到 `# 上传递送信息 （分块函数)` 注释行（约第 1222 行），在该注释行之前插入：

```python
def normalize_middle_brackets(modify_seq: str) -> str:
    """将 Modify_seq 中间的 [linker] 括号块替换为 -linker- dash 格式。
    首位括号（delivery5）和末位括号（delivery3）保持不变，只处理中间块。

    例：[invAb]AmUmGm[LK1-L96-LK1]CmAmUm[Vp]
     → [invAb]AmUmGm-LK1-L96-LK1-CmAmUm[Vp]
    """
    if not modify_seq:
        return modify_seq
    blocks = list(re.finditer(r'\[([^\[\]]+)\]', modify_seq))
    if len(blocks) <= 2:
        return modify_seq  # 无中间块，直接返回
    result = modify_seq
    # 从后往前替换，避免字符位移错位；跳过首块（index 0）和末块（index -1）
    for block in reversed(blocks[1:-1]):
        inner = block.group(1)
        result = result[:block.start()] + f'-{inner}-' + result[block.end():]
    return result


```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
python manage.py test app01.tests.NormalizeMiddleBracketsTests -v 2
```

预期输出（共 11 项）：
```
test_compound_delivery_preserved ... ok
test_delivery5_and_3_unchanged ... ok
test_delivery5_and_middle_bracket ... ok
test_empty_string ... ok
test_middle_bracket_no_delivery ... ok
test_middle_bracket_normalized ... ok
test_multiple_middle_brackets ... ok
test_no_brackets_unchanged ... ok
test_only_delivery3_unchanged ... ok
test_only_delivery5_unchanged ... ok
test_three_brackets_middle_normalized ... ok
OK
```

- [ ] **Step 5: Commit**

```bash
git add app01/views.py app01/tests.py
git commit -m "feat: add normalize_middle_brackets() to support [LK1-L96-LK1] mid-sequence bracket notation"
```

---

### Task 3: 更新 upload_delivery_info 视图（GET 下载 + POST 预处理）

**Files:**
- Modify: `app01/views.py`（`upload_delivery_info` 函数，约第 1665 行）

- [ ] **Step 1: 在 GET 分支末尾添加 `?download=template` 处理**

在 `upload_delivery_info` 视图中，找到：

```python
        elif request.GET.get('download') == 'unpaired_ss_as':
            unpaired_ss_as_path = request.session.get('unpaired_ss_as_path')
            if unpaired_ss_as_path and os.path.exists(unpaired_ss_as_path):
                with open(unpaired_ss_as_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv')
                    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(unpaired_ss_as_path)}"'
                    return response
```

在其正下方（仍在 GET 分支内，`if request.method == 'POST':` 之前）追加：

```python
        elif request.GET.get('download') == 'template':
            template_path = os.path.join(settings.BASE_DIR, 'static', 'templates', 'upload_seq_template.csv')
            if os.path.exists(template_path):
                with open(template_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='text/csv; charset=utf-8-sig')
                    response['Content-Disposition'] = 'attachment; filename="upload_seq_template.csv"'
                    return response
```

确认 `settings` 已在文件顶部导入（搜索 `from django.conf import settings`，正常情况下 Django 项目已导入）。

- [ ] **Step 2: 在 POST 分支中，parse_uploaded_csv 调用之后加预处理**

找到：

```python
            df = parse_uploaded_csv(request)
            ss_groups, unpaired_ss_as = group_sequences(df)
```

替换为：

```python
            df = parse_uploaded_csv(request)
            # 标准化 Modify_seq 中的中间 linker 括号：[LK1-L96-LK1] → -LK1-L96-LK1-
            df['Modify_seq'] = df['Modify_seq'].apply(normalize_middle_brackets)
            ss_groups, unpaired_ss_as = group_sequences(df)
```

- [ ] **Step 3: 手动验证 settings 导入存在**

```bash
grep -n "from django.conf import settings" app01/views.py
```

预期：有一行输出，如 `5:from django.conf import settings`。若无，在文件顶部 import 区加入该行。

- [ ] **Step 4: 启动开发服务器，访问上传页面确认不报错**

```bash
python manage.py runserver
```

浏览器访问 `http://127.0.0.1:8000/upload_delivery_info/`，页面正常加载。

- [ ] **Step 5: Commit**

```bash
git add app01/views.py
git commit -m "feat: add ?download=template endpoint and normalize_middle_brackets call in upload pipeline"
```

---

### Task 4: 更新上传页面模板，替换旧示例下载链接

**Files:**
- Modify: `templates/upload_delivery_info.html`（约第 64 行）

- [ ] **Step 1: 替换旧示例模板链接**

找到：

```html
        <a href="/static/example/2_info.csv" download class="ds-btn ds-btn-ghost" style="margin-bottom:12px;font-size:12.5px;">
          <i class="bi bi-download"></i> 下载 CSV 示例模板
        </a>
```

替换为：

```html
        <a href="?download=template" class="ds-btn ds-btn-ghost" style="margin-bottom:12px;font-size:12.5px;">
          <i class="bi bi-download"></i> 下载上传模板 CSV
        </a>
```

- [ ] **Step 2: 浏览器验证下载按钮**

访问 `http://127.0.0.1:8000/upload_delivery_info/`，点击「下载上传模板 CSV」按钮，确认：
- 浏览器弹出下载对话框，文件名为 `upload_seq_template.csv`
- 打开文件，包含 8 行数据行（A/B/C 三类示例）

- [ ] **Step 3: 验证 B 类双段序列上传正确解析**

使用以下内容创建测试文件 `/tmp/test_bracket.csv`：

```
Project,Target,Seq_type,Modify_seq,Strand_MWs,Parents,Remarks
TEST-0001,GENE,SS,[invAb]AmUmGmCmAmUmGm[LK1-L96-LK1]CmAmUmGmCmAmUm[Vp],,,
TEST-0001,GENE,AS,[Vp]GmAmUmGmCmAmUm[LK1-L96-LK1]CmGmAmUmGmCmAm[invAb],,,
```

在上传页面上传该文件，确认：
- 没有报错
- 数据库中生成对应的 Delivery 记录，`delivery5`=`invAb`，`delivery3`=`Vp`
- `linker_seq` 中包含 `-LK1-L96-LK1-` 段

验证方法（Django shell）：

```bash
python manage.py shell -c "
from app01.models import Delivery
d = Delivery.objects.filter(duplex_id__isnull=False).order_by('-id').first()
print('delivery5:', d.delivery5)
print('delivery3:', d.delivery3)
print('linker_seq:', d.linker_seq[:60])
"
```

预期输出包含 `delivery5: invAb`、`delivery3: Vp`、`linker_seq:` 中含有 `LK1` 或 `L96`。

- [ ] **Step 4: Commit**

```bash
git add templates/upload_delivery_info.html
git commit -m "feat: replace old example CSV link with new upload template download button"
```

---

## 验收标准

1. `static/templates/upload_seq_template.csv` 存在，含 8 行示例（A/B/C 三类）
2. 上传页面「下载上传模板 CSV」按钮可下载该文件
3. `python manage.py test app01.tests.NormalizeMiddleBracketsTests` 全部通过（11/11）
4. 上传含 `[LK1-L96-LK1]` 中间括号的 CSV，数据库 `delivery5`/`delivery3`/`linker_seq` 正确写入
