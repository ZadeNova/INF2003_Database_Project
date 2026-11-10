"""The audit label and tone tables behind every audit badge."""

import pytest

from accounts.audit import AUDIT_ACTIONS, AUDIT_LABELS, SELLER_ACTIONS


def test_every_seller_action_has_a_label_because_the_operator_page_indexes_it_directly():
    assert {f"seller.{action}" for action in SELLER_ACTIONS} <= AUDIT_LABELS.keys()


@pytest.mark.parametrize("code,entry", AUDIT_ACTIONS.items())
def test_each_audit_action_has_a_label_and_a_known_tone(code, entry):
    label, tone = entry
    assert label and tone in (None, "completed", "warning"), code
