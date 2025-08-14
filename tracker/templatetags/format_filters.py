from django import template
import builtins

print("Loading format_filters.py")

register = template.Library()

@register.filter
def format_number(value):
    try:
        num = float(value)
        if num >= 1_000_000_000_000:
            return f"{num / 1_000_000_000_000:.2f}T"
        elif num >= 1_000_000_000:
            return f"{num / 1_000_000_000:.2f}B"
        elif num >= 1_000_000:
            return f"{num / 1_000_000:.2f}M"
        elif num >= 1_000:
            return f"{num / 1_000:.2f}K"
        else:
            return f"{num:.2f}"
    except (ValueError, TypeError):
        return "0.00"

@register.filter
def format_currency(value):
    try:
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "$0.00"

@register.filter
def abs_value(value):
    try:
        return builtins.abs(float(value))
    except (ValueError, TypeError):
        return 0.0

@register.filter
def lookup(dictionary, key):
    try:
        return dictionary.get(key, {})
    except (AttributeError, TypeError):
        return {}

@register.filter
def capitalize_value(value):
    try:
        return ' '.join(word.capitalize() for word in str(value).replace('_', ' ').split())
    except (ValueError, TypeError):
        return ''