"""The trending panel's ranking is cached for a minute; visibility and photos are always read live."""

import json
from datetime import timedelta

import pytest
from checkout_helpers import product
from django.test import Client
from django.utils import timezone

import activity.services as activity_services
from catalogue.models import Product
from config import redis_keys, redis_store

pytestmark = pytest.mark.django_db(transaction=True)


def event(item, when, *, generated=False):
    meta = {"type": "view", "product_id": item.pk, "category": item.category_id, "session_key": "synthetic-test"}
    return {"ts": when, "meta": meta, "is_generated": generated}


def add_views(mongo_db, items, counts, hours_ago=1):
    when = timezone.now() - timedelta(hours=hours_ago)
    for item, count in zip(items, counts):
        mongo_db.events.insert_many([event(item, when) for _ in range(count)])


def ranked(response):
    return [p.pk for p in response.context["trending_products"]]


def forget_trending():
    redis_store.call(lambda client: client.delete(redis_store.key("trending")))


def test_the_ranking_is_cached_but_a_takedown_applies_at_once(mongo_db):
    items = [product(f"trend{n}") for n in range(3)]
    add_views(mongo_db, items, [5, 3, 1])
    client = Client()
    assert ranked(client.get("/products/")) == [items[0].pk, items[1].pk, items[2].pk]
    add_views(mongo_db, [items[2]], [10], hours_ago=0)
    assert ranked(client.get("/products/")) == [items[0].pk, items[1].pk, items[2].pk]  # the cached ranking
    Product.objects.filter(pk=items[0].pk).update(taken_down=True)
    assert ranked(client.get("/products/")) == [items[1].pk, items[2].pk]  # visibility is live
    forget_trending()
    assert ranked(client.get("/products/")) == [items[2].pk, items[1].pk]  # a fresh ranking sees the new views


def test_the_panel_is_the_same_cold_warm_and_with_redis_off(mongo_db, settings):
    items = [product(f"same{n}") for n in range(4)]
    add_views(mongo_db, items, [6, 6, 2, 1])

    def panel():
        shown = Client().get("/products/").context["trending_products"]
        return [(p.pk, p.event_views, p.event_rank, p.generated_views) for p in shown]

    cold, warm = panel(), panel()
    settings.REDIS_ENABLED = False
    assert cold == warm == panel() and len(cold) == 4


def test_when_almost_every_cached_row_is_withdrawn_the_live_ranking_fills_the_panel(mongo_db, monkeypatch):
    monkeypatch.setattr(activity_services, "TRENDING_CACHE_ROWS", 3)
    monkeypatch.setattr(activity_services, "TRENDING_PANEL_SIZE", 2)
    items = [product(f"slack{n}") for n in range(4)]
    add_views(mongo_db, items, [9, 8, 7, 1])
    client = Client()
    assert ranked(client.get("/products/")) == [items[0].pk, items[1].pk]  # the cache now holds the top three
    Product.objects.filter(pk__in=[items[0].pk, items[1].pk]).update(taken_down=True)
    assert ranked(client.get("/products/")) == [items[2].pk, items[3].pk]  # one cached row was left, so it went live


def test_the_category_ranking_is_not_cached(mongo_db):
    items = [product(f"cat{n}") for n in range(2)]
    add_views(mongo_db, items, [3, 2])
    response = Client().get("/products/category/example/")
    assert {p.pk for p in response.context["trending_products"]} == {i.pk for i in items}
    assert redis_store.call(lambda client: list(client.scan_iter(match=redis_store.key("*")))) == []


def test_the_cached_rows_hold_ranking_data_only_never_price_or_stock(mongo_db):
    items = [product(f"rows{n}") for n in range(2)]
    add_views(mongo_db, items, [3, 2])
    Client().get("/products/")
    text = redis_store.call(lambda client: client.get(redis_store.key("trending")))
    rows = redis_store.loads(text)["value"]
    assert rows and all(set(row) <= {"_id", "views", "generated_views", "rank"} for row in rows)
    assert not any(word in json.dumps(rows) for word in ("price", "stock"))  # AGENTS.md rule 2
    assert (
        0
        < redis_store.call(lambda client: client.pttl(redis_store.key("trending")))
        <= (redis_keys.TRENDING_TTL_SECONDS * 1000)
    )


def test_the_panel_still_renders_when_redis_is_unreachable(mongo_db, settings):
    items = [product(f"down{n}") for n in range(2)]
    add_views(mongo_db, items, [4, 2])
    settings.REDIS_PORT = 1
    redis_store.reset_for_tests()
    response = Client().get("/products/")
    assert response.status_code == 200 and ranked(response) == [items[0].pk, items[1].pk]


def test_cached_rows_in_an_older_shape_are_recomputed_not_a_server_error(mongo_db):
    items = [product(f"shape{n}") for n in range(2)]
    add_views(mongo_db, items, [4, 2])
    envelope = redis_store.dumps(
        {"shape": activity_services.TRENDING_SHAPE, "value": [{"views": 3}], "computed_at": timezone.now()}
    )  # no "_id"
    redis_store.call(lambda client: client.set(redis_store.key("trending"), envelope, ex=60))
    response = Client().get("/products/")
    assert response.status_code == 200 and ranked(response) == [items[0].pk, items[1].pk]


def test_cached_rows_written_with_another_shape_number_are_recomputed(mongo_db):
    items = [product(f"stale{n}") for n in range(2)]
    add_views(mongo_db, items, [5, 1])
    rows = [{"_id": items[1].pk, "views": 99, "generated_views": 0, "rank": 1}]  # looks right, but is an older shape
    envelope = redis_store.dumps(
        {"shape": activity_services.TRENDING_SHAPE + 1, "value": rows, "computed_at": timezone.now()}
    )
    redis_store.call(lambda client: client.set(redis_store.key("trending"), envelope, ex=60))
    assert ranked(Client().get("/products/")) == [items[0].pk, items[1].pk]  # the live ranking, not the stale entry
