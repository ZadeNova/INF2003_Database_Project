from django import template

register = template.Library()


@register.filter
def decimal_value(value):
    return value.to_decimal() if hasattr(value, "to_decimal") else value


@register.filter
def option_label(value):
    return str(value).replace("_", " ").capitalize()


@register.filter
def option_value(value):
    return "Yes" if value is True else "No" if value is False else value
