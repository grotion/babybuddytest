#####################################################
# Update view GUI tests                               #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Every Baby Buddy CRUD resource exposes an "edit"    #
# URL of the form `/<resource>/<pk>/`.  These tests   #
# seed an instance, drive the browser to the edit     #
# page, mutate one field, submit, and assert the      #
# database round-trip succeeded.                      #
#                                                     #
# Test result                                         #
# ------------------------------------------------- #
# Date       | Name                     | Pass/Fail #
# ------------------------------------------------- #
# 2026-04-27 | Update flow regression   | see below #
# ------------------------------------------------- #
#####################################################

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# DB access flows in via the live_server fixture (transactional_db).


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _fmt_dt(ts: datetime.datetime) -> str:
    """ISO format expected by ``<input type="datetime-local">`` (with seconds)."""
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _seed_feeding(child):
    from core import models as core_models

    now = timezone.now()
    return core_models.Feeding.objects.create(
        child=child,
        start=now - datetime.timedelta(hours=1),
        end=now - datetime.timedelta(minutes=30),
        type="breast milk",
        method="bottle",
        amount=120,
    )


def _seed_sleep(child):
    from core import models as core_models

    now = timezone.now()
    return core_models.Sleep.objects.create(
        child=child,
        start=now - datetime.timedelta(hours=2),
        end=now - datetime.timedelta(hours=1),
        nap=True,
    )


def _seed_diaper(child):
    from core import models as core_models

    # DiaperChange.solid is a BooleanField with no default - omit it and
    # SQLite raises a NOT NULL IntegrityError on insert.  Pass both flags
    # explicitly.
    return core_models.DiaperChange.objects.create(
        child=child,
        time=timezone.now() - datetime.timedelta(minutes=5),
        wet=True,
        solid=False,
    )


def _seed_pumping(child):
    from core import models as core_models

    now = timezone.now()
    return core_models.Pumping.objects.create(
        child=child,
        start=now - datetime.timedelta(minutes=30),
        end=now - datetime.timedelta(minutes=10),
        amount=60,
    )


def _seed_note(child):
    from core import models as core_models

    return core_models.Note.objects.create(
        child=child,
        note="original",
        time=timezone.now() - datetime.timedelta(minutes=5),
    )


def _seed_temperature(child):
    from core import models as core_models

    return core_models.Temperature.objects.create(
        child=child,
        temperature=37.0,
        time=timezone.now() - datetime.timedelta(minutes=5),
    )


def _seed_weight(child):
    from core import models as core_models

    return core_models.Weight.objects.create(
        child=child,
        weight=8.5,
        date=timezone.localdate(),
    )


def _seed_height(child):
    from core import models as core_models

    return core_models.Height.objects.create(
        child=child,
        height=68.0,
        date=timezone.localdate(),
    )


# ---------------------------------------------------------------------------
# A. Note: simplest possible update flow - text in a textarea.
# ---------------------------------------------------------------------------


def test_note_update_changes_body(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    from core import models as core_models

    note = _seed_note(child)
    admin_browser.get(f"{live_server.url}/notes/{note.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "note")))

    # Mutate the body and submit.
    set_value(admin_browser, "note", "edited body")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/notes/{note.pk}/" not in d.current_url
        or "edited body" in d.page_source
    )
    note.refresh_from_db()
    assert (
        note.note == "edited body"
    ), f"Note was not updated; still reads {note.note!r}"


# ---------------------------------------------------------------------------
# B. Weight / Height / Temperature: scalar field updates.
# ---------------------------------------------------------------------------


def test_weight_update_changes_value(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    weight = _seed_weight(child)
    admin_browser.get(f"{live_server.url}/weight/{weight.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "weight")))

    set_value(admin_browser, "weight", "9.25")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/weight/{weight.pk}/" not in d.current_url
    )
    weight.refresh_from_db()
    assert float(weight.weight) == pytest.approx(
        9.25
    ), f"Weight not updated; still {weight.weight}"


def test_height_update_changes_value(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    height = _seed_height(child)
    admin_browser.get(f"{live_server.url}/height/{height.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "height")))

    set_value(admin_browser, "height", "70.5")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/height/{height.pk}/" not in d.current_url
    )
    height.refresh_from_db()
    assert float(height.height) == pytest.approx(
        70.5
    ), f"Height not updated; still {height.height}"


def test_temperature_update_changes_value(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    temp = _seed_temperature(child)
    admin_browser.get(f"{live_server.url}/temperature/{temp.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "temperature")))

    set_value(admin_browser, "temperature", "38.4")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/temperature/{temp.pk}/" not in d.current_url
    )
    temp.refresh_from_db()
    assert float(temp.temperature) == pytest.approx(
        38.4
    ), f"Temperature not updated; still {temp.temperature}"


# ---------------------------------------------------------------------------
# C. Feeding: amount mutation on a multi-field form.
# ---------------------------------------------------------------------------


def test_feeding_update_changes_amount(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    feeding = _seed_feeding(child)
    admin_browser.get(f"{live_server.url}/feedings/{feeding.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))

    set_value(admin_browser, "amount", "175")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/feedings/{feeding.pk}/" not in d.current_url
    )
    feeding.refresh_from_db()
    assert float(feeding.amount) == pytest.approx(
        175
    ), f"Feeding amount not updated; still {feeding.amount}"


# ---------------------------------------------------------------------------
# D. Sleep: end-time mutation extends the duration.
# ---------------------------------------------------------------------------


def test_sleep_update_extends_end_time(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    sleep = _seed_sleep(child)
    new_end = sleep.end + datetime.timedelta(minutes=15)
    admin_browser.get(f"{live_server.url}/sleep/{sleep.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))

    set_value(admin_browser, "end", _fmt_dt(timezone.localtime(new_end)))
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/sleep/{sleep.pk}/" not in d.current_url
    )
    sleep.refresh_from_db()
    # 15 minutes added (allow 1 minute slack for second-rounding).
    delta = sleep.end - (new_end - datetime.timedelta(minutes=15))
    assert (
        datetime.timedelta(minutes=14) <= delta <= datetime.timedelta(minutes=16)
    ), f"Sleep end was not extended; got delta={delta}"


# ---------------------------------------------------------------------------
# E. DiaperChange: toggling a checkbox.
# ---------------------------------------------------------------------------


def test_diaper_update_toggles_solid(
    admin_browser, live_server, wait, child, check_box, click_submit
):
    change = _seed_diaper(child)
    assert change.solid is False
    admin_browser.get(f"{live_server.url}/changes/{change.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "time")))

    check_box(admin_browser, "solid", True)
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/changes/{change.pk}/" not in d.current_url
    )
    change.refresh_from_db()
    assert change.solid is True, "DiaperChange.solid did not flip to True"


# ---------------------------------------------------------------------------
# F. Pumping: amount mutation.
# ---------------------------------------------------------------------------


def test_pumping_update_changes_amount(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    pumping = _seed_pumping(child)
    admin_browser.get(f"{live_server.url}/pumping/{pumping.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))

    set_value(admin_browser, "amount", "85")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/pumping/{pumping.pk}/" not in d.current_url
    )
    pumping.refresh_from_db()
    assert float(pumping.amount) == pytest.approx(
        85
    ), f"Pumping amount not updated; still {pumping.amount}"


# ---------------------------------------------------------------------------
# G. Update form rejects nonsensical mutations (should re-render with error).
#    xfail because the same min-value gaps that exist on add/ also exist on
#    the update view - documented as a single bug.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: the WeightForm has no MinValueValidator on weight, so updating "
        "an existing weight to a negative number is silently accepted."
    ),
    strict=False,
)
def test_weight_update_rejects_negative(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    weight = _seed_weight(child)
    admin_browser.get(f"{live_server.url}/weight/{weight.pk}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "weight")))

    set_value(admin_browser, "weight", "-2")
    click_submit(admin_browser)
    # Expected: form re-renders at /weight/<pk>/ with errorlist.
    assert f"/weight/{weight.pk}/" in admin_browser.current_url


# ---------------------------------------------------------------------------
# H. Update view renders for every resource (regression guard for URLConf
#    + template includes).  Parametrized.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "seed,url_template,first_field",
    [
        (_seed_feeding, "/feedings/{pk}/", "start"),
        (_seed_sleep, "/sleep/{pk}/", "start"),
        (_seed_diaper, "/changes/{pk}/", "time"),
        (_seed_pumping, "/pumping/{pk}/", "start"),
        (_seed_note, "/notes/{pk}/", "note"),
        (_seed_temperature, "/temperature/{pk}/", "temperature"),
        (_seed_weight, "/weight/{pk}/", "weight"),
        (_seed_height, "/height/{pk}/", "height"),
    ],
)
def test_update_form_renders_for_every_resource(
    admin_browser, live_server, wait, child, seed, url_template, first_field
):
    obj = seed(child)
    admin_browser.get(f"{live_server.url}{url_template.format(pk=obj.pk)}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, first_field)))
    # Submit button must be reachable; the body must render the form tag.
    assert admin_browser.find_elements(
        By.CSS_SELECTOR, "form[method='post']"
    ), f"{url_template} did not render a POST form"
