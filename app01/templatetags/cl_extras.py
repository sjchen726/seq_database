from django import template

register = template.Library()


@register.filter
def list_index(lst, idx):
    """Return lst[idx] or None."""
    try:
        return lst[int(idx)]
    except (IndexError, TypeError, ValueError):
        return None
