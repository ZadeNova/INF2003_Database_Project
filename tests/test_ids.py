"""Ids above the 8-byte limit never reach a database: the route does not match, so the answer is 404, not 500."""

import re

import pytest
from django.test import Client
from django.urls import get_resolver

from config.ids import BIGINT_MAX, BigIntConverter

OVERSIZED = [str(BIGINT_MAX + 1), "99999999999999999999"]


def route_strings(patterns, prefix=""):
    for pattern in patterns:
        if hasattr(pattern, "url_patterns"):
            yield from route_strings(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern)


def id_routes():
    return [route for route in route_strings(get_resolver().url_patterns) if "<bigint:" in route]


def test_converter_accepts_the_largest_id_and_refuses_the_next():
    converter = BigIntConverter()
    assert converter.to_python(str(BIGINT_MAX)) == BIGINT_MAX
    with pytest.raises(ValueError):
        converter.to_python(str(BIGINT_MAX + 1))
    assert converter.to_url(7) == "7"


def test_every_id_route_uses_the_bigint_converter():
    routes = list(route_strings(get_resolver().url_patterns))
    assert not [route for route in routes if "<int:" in route]
    assert len(id_routes()) >= 20


@pytest.mark.django_db
@pytest.mark.parametrize("number", OVERSIZED)
def test_oversized_ids_are_404_on_every_id_route(number):
    client = Client()
    for route in id_routes():
        url = "/" + re.sub(r"<slug:\w+>", "approve", re.sub(r"<bigint:\w+>", number, route))
        assert client.get(url).status_code == 404, url
        assert client.post(url).status_code == 404, url
