"""Identifier bounds shared by routes, forms and services: PostgreSQL and MongoDB both store ids as 8-byte integers."""

BIGINT_MAX = 2**63 - 1


class BigIntConverter:
    """URL converter for ids; a value above the 8-byte limit does not match, so the route answers 404, not 500."""

    regex = "[0-9]{1,19}"

    def to_python(self, value):
        number = int(value)
        if number > BIGINT_MAX:
            raise ValueError(value)
        return number

    def to_url(self, value):
        return str(value)
