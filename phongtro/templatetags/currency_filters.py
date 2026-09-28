from django import template

register = template.Library()


@register.filter
def comma_number(value):
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return value
