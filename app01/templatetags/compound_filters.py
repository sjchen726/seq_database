from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def index(lst, i):
    try:
        return lst[i]
    except (IndexError, TypeError):
        return None


@register.filter
def all_days(invivo_batches):
    days = set()
    for batch in invivo_batches:
        for tp in batch.get('timepoints', []):
            days.add(tp['day'])
    return sorted(days)


@register.filter
def as_day_map(timepoints):
    if not timepoints:
        return {}
    return {tp['day']: tp['kd_pct'] for tp in timepoints}
