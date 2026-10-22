from django import template

register = template.Library()


@register.filter
def option_label(value):
    return str(value).replace("_", " ").capitalize()


@register.filter
def option_value(value):
    return "Yes" if value is True else "No" if value is False else value
