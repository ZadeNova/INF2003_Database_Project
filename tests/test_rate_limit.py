"""The sliding-window limiter and its use on sign-in and review saving, against a real Redis."""

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import redis
from bson import Decimal128
from checkout_helpers import customer, paid_order, product
from django.test import Client, RequestFactory

from accounts.models import User
from config import mongo, ratelimit, redis_store
from orders.models import OrderLine
from reviews.ratings import empty_summary

pytestmark = pytest.mark.django_db(transaction=True)
PASSWORD = "correct-horse-battery"
STATS = {"_id": "bayesian", "m": Decimal128("4"), "C": Decimal128("2")}


def account(name="alice"):
    return User.objects.create_user(username=name, password=PASSWORD)


def sign_in(client, username="alice", password="wrong-password"):
    return client.post("/login/", {"username": username, "password": password})


def limits(settings, **changes):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, **changes}


def keys():
    client = redis.Redis(
        host=redis_store.settings.REDIS_HOST,
        port=redis_store.settings.REDIS_PORT,
        db=redis_store.settings.REDIS_DB,
        username=redis_store.settings.REDIS_USER,
        password=redis_store.settings.REDIS_PASSWORD,
        decode_responses=True,
    )
    return client, sorted(client.scan_iter(match="*"))


# The window itself -----------------------------------------------------------------------------------------------


def age(name, subject, seconds):
    """Make every stored attempt of this counter `seconds` older, instead of sleeping.

    The Docker VM's wall clock steps back by about a second every 30 s, and Redis's TIME (which the window uses) moves with
    it, while time.sleep follows a different clock: a test that sleeps a few seconds against a window of a few seconds
    fails whenever a step lands inside it. Moving the recorded times keeps the same property with margins of many seconds.
    """
    client = keys()[0]
    key = redis_store.key(f"limit:{name}:{redis_store.digest(subject)}")
    for member, score in client.zrange(key, 0, -1, withscores=True):
        client.zadd(key, {member: score - seconds * 1000}, xx=True)


def test_a_window_blocks_after_the_limit_and_frees_one_slot_as_the_oldest_attempt_leaves():
    assert redis_store.window_hit("t", "s", 2, 60).allowed  # first attempt
    age("t", "s", 30)
    assert redis_store.window_hit("t", "s", 2, 60).allowed  # second attempt: the first is 30 s old
    blocked = redis_store.window_hit("t", "s", 2, 60)
    assert not blocked.allowed and blocked.count == 2
    age("t", "s", 35)  # the first attempt is now 65 s old and has left the window; the second is 35 s old and has not
    assert redis_store.window_hit("t", "s", 2, 60).allowed
    assert not redis_store.window_hit("t", "s", 2, 60).allowed  # the second attempt is still inside it


def test_blocked_attempts_are_not_recorded_so_a_block_ends_when_the_oldest_attempt_leaves():
    assert redis_store.window_hit("t", "s", 1, 60).allowed  # the only recorded attempt
    age("t", "s", 30)
    for _ in range(3):
        assert not redis_store.window_hit("t", "s", 1, 60).allowed  # blocked, so not recorded
    age("t", "s", 35)  # the recorded attempt is 65 s old; had the blocked ones been recorded they would be 35 s old
    assert redis_store.window_hit("t", "s", 1, 60).allowed


def test_checking_does_not_record_and_recording_ignores_the_limit():
    for _ in range(3):
        assert redis_store.window_check("t", "s", 1, 60).allowed
    assert redis_store.window_hit("t", "s", 1, 60).allowed
    assert not redis_store.window_check("t", "s", 1, 60).allowed
    for _ in range(3):
        redis_store.window_record("r", "s", 1, 60)
    assert redis_store.window_check("r", "s", 1, 60).count == 3


def test_retry_after_is_whole_seconds_between_one_and_the_window():
    redis_store.window_hit("t", "s", 1, 90)
    blocked = redis_store.window_hit("t", "s", 1, 90)
    assert not blocked.allowed and 88 <= blocked.retry_after <= 90
    assert isinstance(blocked.retry_after, int)


def test_parallel_attempts_cannot_overshoot_the_limit(mongo_db):
    def attempt(_):
        with mongo.using_database(mongo_db.name):
            return redis_store.window_hit("t", "s", 5, 60).allowed

    with ThreadPoolExecutor(20) as pool:
        results = list(pool.map(attempt, range(20)))
    assert results.count(True) == 5


def test_a_window_with_no_room_at_all_still_answers():
    assert not redis_store.window_hit("t", "s", 0, 60).allowed


# Sign-in ---------------------------------------------------------------------------------------------------------


def test_the_sixth_attempt_in_a_window_is_refused_with_429_even_with_the_right_password():
    account()
    client = Client()
    assert [sign_in(client).status_code for _ in range(5)] == [200] * 5
    blocked = sign_in(client)
    assert blocked.status_code == 429
    assert 1 <= int(blocked["Retry-After"]) <= 15 * 60 and "no-store" in blocked["Cache-Control"]
    assert b"Too many attempts" in blocked.content and b"wrong-password" not in blocked.content  # no form is echoed
    assert sign_in(client, password=PASSWORD).status_code == 429  # the block holds until the window passes


def test_another_username_and_another_address_are_not_blocked():
    account("alice")
    account("bob")
    client = Client()
    for _ in range(6):
        sign_in(client)
    assert sign_in(client, "alice").status_code == 429
    assert sign_in(client, "bob").status_code == 200  # a stranger cannot lock out other accounts from this address
    elsewhere = Client(REMOTE_ADDR="198.51.100.20")
    assert sign_in(elsewhere, "alice").status_code == 200  # nor lock alice out from her own address
    assert sign_in(elsewhere, "alice", PASSWORD).status_code == 302


def test_a_successful_sign_in_clears_that_usernames_counter(settings):
    limits(settings, login=(3, 60))
    account()
    for _ in range(2):
        assert sign_in(Client()).status_code == 200
    assert sign_in(Client(), password=PASSWORD).status_code == 302
    for _ in range(2):  # without the reset these would be the fourth and fifth attempts
        assert sign_in(Client()).status_code == 200
    assert sign_in(Client(), password=PASSWORD).status_code == 302


def test_failures_count_against_the_address_but_successes_never_do(settings):
    limits(settings, login_ip=(3, 60), login=(100, 60))
    for name in ("u1", "u2", "u3", "u4"):
        account(name)
    for _ in range(3):
        for name in ("u1", "u2", "u3", "u4"):
            assert sign_in(Client(), name, PASSWORD).status_code == 302
    assert redis_store.window_check("login_ip", "127.0.0.1", 3, 60).count == 0
    for name in ("u1", "u2", "u3"):
        assert sign_in(Client(), name).status_code == 200
    assert sign_in(Client(), "u4", PASSWORD).status_code == 429  # even a fresh username with the right password
    assert sign_in(Client(REMOTE_ADDR="198.51.100.21"), "u4", PASSWORD).status_code == 302


def test_usernames_are_trimmed_and_unicode_normalised_before_they_are_counted_but_case_is_kept(settings):
    limits(settings, login=(2, 60))
    account()
    assert sign_in(Client(), " alice").status_code == 200
    assert sign_in(Client(), "ａｌｉｃｅ").status_code == 200  # a full-width spelling is the same name
    assert sign_in(Client(), "alice").status_code == 429
    assert (
        sign_in(Client(), "ALICE").status_code == 200
    )  # Django matches names exactly: another account, another counter


def test_a_name_that_does_not_exist_is_counted_like_any_other(settings):
    limits(settings, login=(2, 60))
    assert [sign_in(Client(), "nobody").status_code for _ in range(3)] == [200, 200, 429]  # nothing reveals the account


def test_no_key_or_member_contains_the_username_or_the_address():
    account()
    client = Client(REMOTE_ADDR="203.0.113.9")
    sign_in(client)
    sign_in(client, "alice", PASSWORD)
    sign_in(Client(REMOTE_ADDR="203.0.113.9"))
    redis_client, found = keys()
    assert found
    for name in found:
        assert "alice" not in name and "203.0.113.9" not in name
        members = redis_client.zrange(name, 0, -1)  # every key here is a limiter sorted set
        assert members and all("alice" not in member and "203" not in member for member in members)


def test_the_429_page_is_rendered_without_touching_the_database(django_assert_num_queries):
    account()
    client = Client()
    for _ in range(5):
        sign_in(client)
    with django_assert_num_queries(0):
        response = sign_in(client)
    assert response.status_code == 429 and "Retry-After" in response


def test_nothing_is_limited_when_redis_is_disabled_or_unreachable(settings):
    account()
    settings.REDIS_ENABLED = False
    assert {sign_in(Client()).status_code for _ in range(8)} == {200}
    settings.REDIS_ENABLED = True
    settings.REDIS_PORT = 1
    redis_store.reset_for_tests()
    started = time.monotonic()
    assert {sign_in(Client()).status_code for _ in range(8)} == {200}  # fails open, and quickly
    assert time.monotonic() - started < 5
    assert sign_in(Client(), "alice", PASSWORD).status_code == 302


def test_addresses_in_one_ipv6_slash_64_share_a_counter_and_mapped_ipv4_is_unwrapped():
    factory = RequestFactory()

    def address(value):
        return ratelimit.client_address(factory.get("/", REMOTE_ADDR=value))

    assert address("2001:db8::1") == address("2001:db8::ffff") == "2001:db8::/64"
    assert address("2001:db8:0:1::1") != address("2001:db8::1")
    assert address("::ffff:192.0.2.5") == "192.0.2.5" and address("192.0.2.5") == "192.0.2.5"
    assert address("not an address") == "unknown" and address("") == "unknown"


def test_a_forwarded_header_cannot_change_the_address():
    account()
    for index in range(6):
        sign_in(Client(HTTP_X_FORWARDED_FOR=f"10.0.0.{index}"))
    assert sign_in(Client(HTTP_X_FORWARDED_FOR="10.9.9.9")).status_code == 429


# Reviews ---------------------------------------------------------------------------------------------------------


@pytest.fixture
def shop(mongo_db):
    buyer, item = customer(), product()
    mongo_db.platform_stats.insert_one(dict(STATS))
    mongo_db.product_specs.insert_one(
        {
            "_id": item.pk,
            "category_id": item.category_id,
            "description": "Example",
            "attributes": {},
            "photo_file_id": None,
            "rating_summary": empty_summary(STATS),
            "latest_reviews": [],
            "has_generated_content": False,
        }
    )
    return buyer, item


def delivered_line(buyer, item):
    _, order = paid_order(buyer, item, status="delivered")
    return OrderLine.objects.create(order=order, seller=item.seller, product=item, quantity=1, unit_price=10, freight=2)


def save_review(client, line, score="4", action="create"):
    return client.post(f"/reviews/line/{line.pk}/", {"action": action, "score": score, "title": "Fine", "text": "Good"})


def test_the_third_review_save_in_a_window_is_refused_and_deleting_is_not_limited(shop, settings):
    limits(settings, review=(2, 60))
    buyer, item = shop
    lines = [delivered_line(buyer, item) for _ in range(3)]
    client = Client()
    client.force_login(buyer)
    assert save_review(client, lines[0]).status_code == 302
    assert save_review(client, lines[1]).status_code == 302
    blocked = save_review(client, lines[2])
    assert blocked.status_code == 429 and 1 <= int(blocked["Retry-After"]) <= 60
    assert save_review(client, lines[0], action="delete").status_code == 302  # taking a review back is never limited
    assert save_review(client, lines[2]).status_code == 429  # deleting did not give the window back


def test_a_refused_save_does_not_use_up_the_allowance(shop, settings):
    limits(settings, review=(2, 60))
    buyer, item = shop
    lines = [delivered_line(buyer, item) for _ in range(2)]
    client = Client()
    client.force_login(buyer)
    assert save_review(client, lines[0], score="9").status_code == 400  # a validation error
    assert save_review(client, lines[0], score="9").status_code == 400
    assert save_review(client, lines[0]).status_code == 302
    assert save_review(client, lines[1]).status_code == 302  # both real saves fit: the errors were not counted


def test_review_saves_are_not_limited_when_redis_is_unreachable(shop, settings):
    limits(settings, review=(1, 60))
    settings.REDIS_PORT = 1
    redis_store.reset_for_tests()
    buyer, item = shop
    first, second = delivered_line(buyer, item), delivered_line(buyer, item)
    client = Client()
    client.force_login(buyer)
    assert save_review(client, first).status_code == 302
    assert (
        save_review(client, second).status_code == 302
    )  # a limit of one would have refused this, if it could be counted


def test_the_review_limit_is_per_customer(shop, settings):
    limits(settings, review=(1, 60))
    buyer, item = shop
    other = customer("other-buyer")
    first, second = delivered_line(buyer, item), delivered_line(other, item)
    one, two = Client(), Client()
    one.force_login(buyer)
    two.force_login(other)
    assert save_review(one, first).status_code == 302
    assert save_review(one, first, score="5", action="edit").status_code == 429
    assert save_review(two, second).status_code == 302


def test_retry_after_waits_for_enough_entries_to_leave_when_parallel_requests_overshot_the_limit():
    for _ in range(2):
        redis_store.window_record("t", "s", 2, 60)
    age("t", "s", 30)  # the first two entries are 30 s old
    for _ in range(2):
        redis_store.window_record("t", "s", 2, 60)  # four entries in a window that allows two
    blocked = redis_store.window_check("t", "s", 2, 60)
    # Two entries must leave before one more is allowed: the third in order, just recorded, leaves in about 60 s. The
    # oldest entry alone (the earlier logic) would say about 30.
    assert not blocked.allowed and blocked.count == 4 and 45 < blocked.retry_after <= 60


def test_signing_in_to_a_look_alike_name_does_not_touch_the_counter_of_the_account_it_resembles(settings):
    limits(settings, login=(5, 60))
    account("jessica")
    account("jeßica")  # case folding would turn this into "jessica"; the counters must stay separate
    for _ in range(4):
        assert sign_in(Client(), "jessica").status_code == 200
    assert sign_in(Client(), "jeßica", PASSWORD).status_code == 302  # a genuine sign-in, to another account
    assert sign_in(Client(), "jessica").status_code == 200  # the fifth attempt at jessica
    assert sign_in(Client(), "jessica").status_code == 429  # its counter was neither reset nor shared


def test_a_genuine_sign_in_still_clears_its_own_counter_when_typed_with_spaces_or_full_width_letters(settings):
    limits(settings, login=(3, 60))
    account("alice")
    for typed in (" alice ", "ａｌｉｃｅ"):
        for _ in range(2):
            assert sign_in(Client(), typed).status_code == 200
        assert sign_in(Client(), typed, PASSWORD).status_code == 302
    assert sign_in(Client(), "alice").status_code == 200 and sign_in(Client(), "alice").status_code == 200
