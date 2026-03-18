"""
core/templatetags/core_tags.py
Custom template filters used across all templates.
"""

from django import template

register = template.Library()


@register.filter
def split(value, delimiter="|"):
    """
    Splits a string by delimiter.
    Usage: {{ "a|b|c"|split:"|" }}
    """
    return value.split(delimiter)


@register.filter
def get_item(lst, index):
    """Gets item from list by index."""
    try:
        return lst[int(index)]
    except (IndexError, TypeError, ValueError):
        return ''
