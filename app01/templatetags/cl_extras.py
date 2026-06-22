from django import template

register = template.Library()


@register.filter
def list_index(lst, idx):
    """Return lst[idx] or None."""
    try:
        return lst[int(idx)]
    except (IndexError, TypeError, ValueError):
        return None


@register.filter
def fmt_or_dash(val, decimals='1'):
    """Format a float to N decimal places, or '—' if None. Safe for zero values."""
    if val is None:
        return '—'
    try:
        return f'{float(val):.{int(decimals)}f}'
    except (TypeError, ValueError):
        return '—'


@register.filter
def ic50_class(ic50_nm):
    """CSS class for IC50 threshold: <1nM good, <10nM ok, else weak."""
    if ic50_nm is None:
        return ''
    if ic50_nm < 1:
        return 'cl-val-good'
    if ic50_nm < 10:
        return 'cl-val-ok'
    return 'cl-val-weak'


@register.filter
def kd_class(kd_pct):
    """CSS class for KD% threshold: ≥80% good, ≥50% ok, else weak."""
    if kd_pct is None:
        return ''
    if kd_pct >= 80:
        return 'cl-val-good'
    if kd_pct >= 50:
        return 'cl-val-ok'
    return 'cl-val-weak'


@register.filter
def vivo_kd_class(kd_pct):
    """CSS class for in-vivo peak KD%: ≥80% good, ≥50% ok, else weak."""
    if kd_pct is None:
        return ''
    if kd_pct >= 80:
        return 'cl-val-good'
    if kd_pct >= 50:
        return 'cl-val-ok'
    return 'cl-val-weak'


@register.filter
def bw_drop_class(pct):
    """CSS class for body weight % change from Day 0 baseline (negative = loss).
    Thresholds per IACUC/FDA rodent study guidelines:
      > -10%  : acceptable        -> cl-val-good   (green)
      > -20%  : significant loss  -> cl-val-ok     (orange)
      <= -20% : humane endpoint   -> cl-val-danger  (red)
    """
    if pct is None:
        return ''
    if pct > -10:
        return 'cl-val-good'
    if pct > -20:
        return 'cl-val-ok'
    return 'cl-val-danger'
