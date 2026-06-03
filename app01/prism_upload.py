import csv
import io


def parse_prism_file(file_obj, filename):
    """Parse a Prism-exported CSV (.csv) or TXT (.txt) wide-format file.

    Returns dict:
      matched    — {duplex_id: {'rows': [{'x', 'replicates', 'excluded'}]}}
      x_values   — ordered list of x-axis float values (first column)
      skipped_cols — sorted list of unrecognised column header strings
      warnings   — list of human-readable warning strings
    """
    fname = filename.lower()
    if fname.endswith('.csv'):
        sep = ','
    elif fname.endswith('.txt'):
        sep = '\t'
    else:
        raise ValueError(f"不支持的文件格式：{filename}，请使用 .csv 或 .txt")

    raw = file_obj.read()
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8-sig')

    lines = [ln for ln in raw.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("文件为空")

    def split_row(line):
        return next(csv.reader(io.StringIO(line), delimiter=sep))

    # ── Header row ──────────────────────────────────────────────────────────────
    header = split_row(lines[0])
    col_names = [c.strip() for c in header[1:]]  # first cell = x-axis label, skip it

    unique_names = {n for n in col_names if n}
    from .models import Delivery
    existing_ids = set(
        Delivery.objects.filter(duplex_id__in=unique_names)
        .values_list('duplex_id', flat=True)
        .distinct()
    )

    # Build col_mapping: (duplex_id, rep_index, is_matched) per data column
    rep_counter = {}
    col_mapping = []
    for n in col_names:
        rep_idx = rep_counter.get(n, 0)
        rep_counter[n] = rep_idx + 1
        col_mapping.append((n, rep_idx, n in existing_ids))

    skipped_cols = sorted({n for n, _, m in col_mapping if n and not m})

    # ── Data rows ────────────────────────────────────────────────────────────────
    # raw_rows: {duplex_id: {x_float: {'replicates': {rep_idx: val}, 'excluded': {rep_idx: bool}}}}
    raw_rows = {}
    x_values = []
    seen_x = set()
    warnings = []

    for line_no, line in enumerate(lines[1:], start=2):
        row = split_row(line)
        if not row:
            continue
        x_raw = row[0].strip()
        try:
            x = float(x_raw)
        except ValueError:
            warnings.append(f"第 {line_no} 行：X 轴值 {x_raw!r} 无法解析，已跳过")
            continue

        if x not in seen_x:
            seen_x.add(x)
            x_values.append(x)

        data_cols = row[1:]
        for col_idx, (duplex_id, rep_idx, matched) in enumerate(col_mapping):
            if not matched or not duplex_id:
                continue
            raw_rows.setdefault(duplex_id, {}).setdefault(
                x, {'replicates': {}, 'excluded': {}}
            )
            cell = data_cols[col_idx].strip() if col_idx < len(data_cols) else ''
            if not cell:
                continue
            excluded = cell.endswith('*')
            if excluded:
                cell = cell[:-1].strip()
            try:
                val = float(cell)
                raw_rows[duplex_id][x]['replicates'][rep_idx] = val
                raw_rows[duplex_id][x]['excluded'][rep_idx] = excluded
            except ValueError:
                warnings.append(
                    f"第 {line_no} 行，列 {col_idx + 2}：值 {cell!r} 无法解析，已跳过"
                )

    # ── Assemble final structure ─────────────────────────────────────────────────
    rep_counts = {}
    for n, rep_idx, matched in col_mapping:
        if matched and n:
            rep_counts[n] = max(rep_counts.get(n, 0), rep_idx + 1)

    matched = {}
    for duplex_id, x_data in raw_rows.items():
        n_reps = rep_counts.get(duplex_id, 3)
        rows = [
            {
                'x': x,
                'replicates': [x_data[x]['replicates'].get(i) for i in range(n_reps)],
                'excluded': [x_data[x]['excluded'].get(i, False) for i in range(n_reps)],
            }
            for x in x_values
            if x in x_data
        ]
        matched[duplex_id] = {'rows': rows}

    return {
        'matched': matched,
        'x_values': x_values,
        'skipped_cols': skipped_cols,
        'warnings': warnings,
    }
