#####################################################
# List filter UI GUI tests                            #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Baby Buddy wires every list page through            #
# django-filter (see core/filters.py).  These tests   #
# seed two distinguishable records, hit the list URL  #
# with a query string, and assert that only the       #
# matching record is rendered.  We drive everything   #
# through the real list templates so a regression in  #
# the FilterSet -> queryset wiring would surface here.#
#                                                     #
# Filter fields per resource (from core/filters.py):  #
#   FeedingFilter    : child, type, method            #
#   DiaperChangeFilter: child, wet, solid, color      #
#   SleepFilter      : child                          #
#   NoteFilter       : child                          #
#   WeightFilter     : child                          #
#####################################################

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# ---------------------------------------------------------------------------
# Seed helpers - all return objects so tests can assert on PKs / fields.
# ---------------------------------------------------------------------------


def _second_child(first_name="Otto", last_name="Octavius"):
    from core import models as core_models

    return core_models.Child.objects.create(
        first_name=first_name,
        last_name=last_name,
        birth_date=datetime.date(2023, 7, 1),
    )


def _seed_feeding(child, *, type_="breast milk", method="bottle", amount=120):
    from core import models as core_models

    now = timezone.now()
    return core_models.Feeding.objects.create(
        child=child,
        start=now - datetime.timedelta(hours=1),
        end=now - datetime.timedelta(minutes=30),
        type=type_,
        method=method,
        amount=amount,
    )


def _seed_diaper(child, *, wet=True, solid=False, color=""):
    from core import models as core_models

    return core_models.DiaperChange.objects.create(
        child=child,
        time=timezone.now() - datetime.timedelta(minutes=5),
        wet=wet,
        solid=solid,
        color=color,
    )


def _seed_sleep(child, *, minutes_ago=120):
    from core import models as core_models

    now = timezone.now()
    return core_models.Sleep.objects.create(
        child=child,
        start=now - datetime.timedelta(minutes=minutes_ago + 30),
        end=now - datetime.timedelta(minutes=minutes_ago),
        nap=True,
    )


def _seed_note(child, *, body="seeded note"):
    from core import models as core_models

    return core_models.Note.objects.create(
        child=child,
        note=body,
        time=timezone.now() - datetime.timedelta(minutes=2),
    )


# ---------------------------------------------------------------------------
# A. Feeding list filtered by `type` shows only matching feedings.
# ---------------------------------------------------------------------------


def test_feeding_list_filter_by_type(admin_browser, live_server, wait, child):
    breast = _seed_feeding(child, type_="breast milk", method="bottle", amount=110)
    formula = _seed_feeding(child, type_="formula", method="bottle", amount=200)

    # `type` is a CharField with choices; the filter lookup is case-sensitive
    # match on the raw stored value.
    admin_browser.get(f"{live_server.url}/feedings/?type=formula")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    # The list view renders an edit URL per row of the form /feedings/<pk>/.
    # We use that as a stable oracle: the formula feeding's edit URL must be
    # present, the breast-milk one must not.
    page = admin_browser.page_source
    assert (
        f"/feedings/{formula.pk}/" in page
    ), "Filtered list missing the formula feeding"
    assert (
        f"/feedings/{breast.pk}/" not in page
    ), "Filtered list leaked the breast-milk feeding (should be hidden)"


# ---------------------------------------------------------------------------
# B. Feeding list filtered by `method`.
# ---------------------------------------------------------------------------


def test_feeding_list_filter_by_method(admin_browser, live_server, wait, child):
    bottle = _seed_feeding(child, type_="breast milk", method="bottle", amount=100)
    left = _seed_feeding(child, type_="breast milk", method="left breast", amount=0)

    admin_browser.get(f"{live_server.url}/feedings/?method=left+breast")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = admin_browser.page_source
    assert (
        f"/feedings/{left.pk}/" in page
    ), "Filtered list missing the left-breast feeding"
    assert (
        f"/feedings/{bottle.pk}/" not in page
    ), "Filtered list leaked the bottle feeding (should be hidden)"


# ---------------------------------------------------------------------------
# C. DiaperChange list filtered by `wet=True`.
#
# `wet` is a BooleanField; django-filter accepts the standard
# {True, False, true, false, 1, 0} forms.  We use the canonical "True".
# ---------------------------------------------------------------------------


def test_diaper_list_filter_by_wet(admin_browser, live_server, wait, child):
    wet_change = _seed_diaper(child, wet=True, solid=False)
    dry_change = _seed_diaper(child, wet=False, solid=True, color="brown")

    admin_browser.get(f"{live_server.url}/changes/?wet=True")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = admin_browser.page_source
    assert (
        f"/changes/{wet_change.pk}/" in page
    ), "Filtered diaper list missing the wet change"
    assert (
        f"/changes/{dry_change.pk}/" not in page
    ), "Filtered diaper list leaked the dry change"


# ---------------------------------------------------------------------------
# D. List filtered by `child` shows only that child's records.
#
# Most filters expose only `child`, so this exercises the most common
# filtering pathway.  We use Sleep here because it has the simplest form.
# ---------------------------------------------------------------------------


def test_sleep_list_filter_by_child_isolates_records(
    admin_browser, live_server, wait, child
):
    other = _second_child()
    rosa_sleep = _seed_sleep(child)
    otto_sleep = _seed_sleep(other)

    admin_browser.get(f"{live_server.url}/sleep/?child={child.pk}")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = admin_browser.page_source
    assert (
        f"/sleep/{rosa_sleep.pk}/" in page
    ), "Sleep list filtered to Rosa's child is missing Rosa's sleep"
    assert (
        f"/sleep/{otto_sleep.pk}/" not in page
    ), "Sleep list filtered to Rosa leaked Otto's sleep"


# ---------------------------------------------------------------------------
# E. Note list filtered by `child` (sanity that the same wiring works on
#    a different model with the simplest possible filter).
# ---------------------------------------------------------------------------


def test_note_list_filter_by_child(admin_browser, live_server, wait, child):
    other = _second_child(first_name="Hank", last_name="Pym")
    rosa_note = _seed_note(child, body="rosa-only note text")
    hank_note = _seed_note(other, body="hank-only note text")

    admin_browser.get(f"{live_server.url}/notes/?child={child.pk}")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = admin_browser.page_source
    # The notes list renders the body text directly, so we can also assert on
    # the literal content (defense in depth against template path changes).
    assert "rosa-only note text" in page, "Filtered note list missing Rosa's note"
    assert (
        "hank-only note text" not in page
    ), "Filtered note list leaked Hank's note (should be hidden)"
    assert f"/notes/{rosa_note.pk}/" in page
    assert f"/notes/{hank_note.pk}/" not in page


# ---------------------------------------------------------------------------
# F. Filter that matches no records returns an empty list, not a 500.
#
# Note: django-filter's ChoiceFilter silently ignores values that aren't in
# the field's `choices=` list (so ``?type=does-not-exist`` actually returns
# *every* record).  To exercise the "filter narrows to zero" path we have to
# pass a valid choice that no seeded record matches.
# ---------------------------------------------------------------------------


def test_feeding_list_with_unmatched_filter_returns_empty(
    admin_browser, live_server, wait, child
):
    # Seed a breast-milk feeding; then filter for the (valid but unmatched)
    # `solid food` choice.
    feeding = _seed_feeding(child, type_="breast milk", method="bottle", amount=80)

    admin_browser.get(f"{live_server.url}/feedings/?type=solid+food")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = admin_browser.page_source
    assert "Server Error" not in page, "Unmatched filter triggered a 500"
    # The seeded breast-milk feeding must NOT appear under the solid-food
    # filter - the filter genuinely narrows the queryset to zero rows.
    assert (
        f"/feedings/{feeding.pk}/" not in page
    ), "type=solid+food filter unexpectedly returned the breast-milk feeding"


# ---------------------------------------------------------------------------
# G. xfail: the FeedingFilter does not declare a date-range filter, but the
#    list page advertises a `start` query param via its UI - documented bug.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: the feeding list UI shows a date-range filter widget but the "
        "underlying FeedingFilter only declares ['child', 'type', 'method']. "
        "Passing ?start_min=2024-01-01 silently ignores the bound and returns "
        "every feeding."
    ),
    strict=False,
)
def test_feeding_list_supports_date_range_filter(
    admin_browser, live_server, wait, child
):
    # Two feedings far apart in time.
    from core import models as core_models

    long_ago = timezone.now() - datetime.timedelta(days=400)
    recent = _seed_feeding(child, type_="formula", method="bottle", amount=150)
    # Reach past Feeding.save()'s duration computation by using update().
    old_feeding = _seed_feeding(child, type_="formula", method="bottle", amount=150)
    core_models.Feeding.objects.filter(pk=old_feeding.pk).update(
        start=long_ago, end=long_ago + datetime.timedelta(minutes=5)
    )

    admin_browser.get(
        f"{live_server.url}/feedings/?start_min={timezone.now().date().isoformat()}"
    )
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    page = admin_browser.page_source
    # Expected (if the filter were wired): the 400-day-old record is hidden.
    assert (
        f"/feedings/{old_feeding.pk}/" not in page
    ), "start_min did not exclude the 400-day-old feeding"
    assert f"/feedings/{recent.pk}/" in page
