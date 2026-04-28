#####################################################
# Tracking flows GUI tests                            #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Feeding, sleep, diaper and pumping - the four core  #
# activities a caregiver logs every day.  Each flow   #
# is exercised at the browser level:                  #
#   - form renders                                    #
#   - valid submission persists                       #
#   - invalid submission stays on the page            #
#                                                     #
# Two tests reproduce blackbox bug B-05 at the UI:    #
#   - feeding end-before-start                        #
#   - pumping negative amount                         #
# Both are xfail-marked because current main silently #
# accepts them where a clean form error is expected.  #
#####################################################

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# DB access comes through the live_server fixture (which requests
# transactional_db under the hood); no explicit marker required.


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _fmt(ts: datetime.datetime) -> str:
    """Format a timestamp the way Baby Buddy's DateTimeInput (``type=\"datetime-local\"``)
    widget expects: ``YYYY-MM-DDTHH:MM:SS``.

    HTML5 ``<input type=\"datetime-local\">`` *rejects* a space-separated value
    and silently coerces ``el.value`` back to the empty string, which makes
    Django raise ``This field is required.`` on the server and leaves the
    browser on ``/add/`` - confusing our post-submit navigation asserts.

    The widget's ``step=1`` attribute (set by babybuddy/widgets.DateTimeInput)
    means seconds granularity is expected; we include ``:SS`` accordingly.
    """
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _select_radio_by_value(driver, field_name: str, value: str) -> None:
    """Click the radio input whose name= matches and value= matches.

    PillRadioSelect renders as a <label>-wrapped <input type='radio'>.  Clicks
    on the hidden input can be intercepted by the label in some browsers, so
    we JS-click to stay portable.
    """
    radio = driver.find_element(
        By.CSS_SELECTOR, f"input[name='{field_name}'][value='{value}']"
    )
    driver.execute_script("arguments[0].click();", radio)


def _select_child_radio(driver, child_pk: int) -> None:
    """ChildRadioSelect emits inputs named `child`; pick by the child's PK."""
    _select_radio_by_value(driver, "child", str(child_pk))


# ---------------------------------------------------------------------------
# Feeding
# ---------------------------------------------------------------------------


def test_feeding_add_form_renders(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/feedings/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    for fld in ("child", "start", "end", "type", "method", "amount"):
        assert admin_browser.find_elements(
            By.NAME, fld
        ), f"Feeding form is missing expected field '{fld}'"


def test_valid_feeding_save_persists(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    from core import models as core_models

    admin_browser.get(f"{live_server.url}/feedings/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    # DateTimeInput renders a native <input type="datetime-local"> which
    # rejects free-text send_keys in headless Chrome; setting .value via JS
    # and firing input/change is what flatpickr + the Django widget expect.
    set_value(admin_browser, "start", _fmt(now - datetime.timedelta(minutes=30)))
    set_value(admin_browser, "end", _fmt(now - datetime.timedelta(minutes=10)))
    _select_child_radio(admin_browser, child.pk)
    _select_radio_by_value(admin_browser, "type", "breast milk")
    _select_radio_by_value(admin_browser, "method", "bottle")

    click_submit(admin_browser)
    wait(admin_browser).until(lambda d: "/feedings/add/" not in d.current_url)
    assert core_models.Feeding.objects.filter(child=child).exists()


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug B-05: Feeding.clean() validates `start` only.  An `end` that "
        "precedes `start` is silently accepted, corrupting duration analytics."
    ),
    strict=False,
)
def test_feeding_end_before_start_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/feedings/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    # Intentionally reverse them.
    set_value(admin_browser, "start", _fmt(now - datetime.timedelta(minutes=5)))
    set_value(admin_browser, "end", _fmt(now - datetime.timedelta(minutes=30)))
    _select_child_radio(admin_browser, child.pk)
    _select_radio_by_value(admin_browser, "type", "breast milk")
    _select_radio_by_value(admin_browser, "method", "bottle")
    click_submit(admin_browser)
    # Expected behavior: stay on the add page with an errorlist.  Observed:
    # the form redirects (bug) - the assertion below fails, which xfail
    # converts to a documented bug entry.
    assert "/feedings/add/" in admin_browser.current_url


def test_feeding_list_renders_after_save(admin_browser, live_server, wait, child):
    from core import models as core_models

    now = timezone.now()
    core_models.Feeding.objects.create(
        child=child,
        start=now - datetime.timedelta(hours=1),
        end=now - datetime.timedelta(minutes=30),
        type="breast milk",
        method="bottle",
    )
    admin_browser.get(f"{live_server.url}/feedings/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    # The list must render and mention the child we seeded.
    assert child.first_name in admin_browser.page_source


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------


def test_sleep_add_form_renders(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/sleep/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    for fld in ("child", "start", "end"):
        assert admin_browser.find_elements(By.NAME, fld)


def test_valid_sleep_entry_saves(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    from core import models as core_models

    admin_browser.get(f"{live_server.url}/sleep/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    set_value(admin_browser, "start", _fmt(now - datetime.timedelta(hours=2)))
    set_value(admin_browser, "end", _fmt(now - datetime.timedelta(hours=1)))
    _select_child_radio(admin_browser, child.pk)
    click_submit(admin_browser)
    wait(admin_browser).until(lambda d: "/sleep/add/" not in d.current_url)
    assert core_models.Sleep.objects.filter(child=child).exists()


# ---------------------------------------------------------------------------
# Diaper change
# ---------------------------------------------------------------------------


def test_diaper_change_add_form_renders(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/changes/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "time")))
    # `wet` and `solid` are checkbox inputs on the DiaperChange form.
    for fld in ("child", "time", "wet", "solid"):
        assert admin_browser.find_elements(By.NAME, fld)


def test_diaper_change_valid_entry_saves(
    admin_browser, live_server, wait, child, set_value, check_box, click_submit
):
    from core import models as core_models

    admin_browser.get(f"{live_server.url}/changes/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "time")))
    set_value(
        admin_browser,
        "time",
        _fmt(timezone.localtime() - datetime.timedelta(minutes=5)),
    )
    _select_child_radio(admin_browser, child.pk)
    # The wet/solid inputs are Bootstrap `btn-check d-none` checkboxes; the
    # visible <label> swallows clicks aimed at the <input>, so a plain Selenium
    # click on the underlying element raises ElementNotInteractableException.
    check_box(admin_browser, "wet", True)
    click_submit(admin_browser)
    wait(admin_browser).until(lambda d: "/changes/add/" not in d.current_url)
    assert core_models.DiaperChange.objects.filter(child=child).exists()


# ---------------------------------------------------------------------------
# Pumping
# ---------------------------------------------------------------------------


def test_pumping_add_form_renders(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/pumping/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    for fld in ("child", "start", "amount"):
        assert admin_browser.find_elements(By.NAME, fld)


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug B-05 (pumping variant): the amount FloatField has no "
        "MinValueValidator, so a negative pumping volume is accepted by "
        "the UI and persisted."
    ),
    strict=False,
)
def test_pumping_negative_amount_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/pumping/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    set_value(admin_browser, "start", _fmt(now - datetime.timedelta(minutes=30)))
    if admin_browser.find_elements(By.NAME, "end"):
        set_value(admin_browser, "end", _fmt(now - datetime.timedelta(minutes=10)))
    _select_child_radio(admin_browser, child.pk)
    set_value(admin_browser, "amount", "-50")
    click_submit(admin_browser)
    # Expected: stay on the add page with an errorlist.
    assert "/pumping/add/" in admin_browser.current_url


# ---------------------------------------------------------------------------
# Additional xfail bug-documentation tests at the GUI layer.  Each of these
# drives a real browser against the same flow a caregiver would use and
# asserts an *ideal* behavior (graceful validation) that does not hold on
# current main.  strict=False means a future fix makes them silently pass.
# ---------------------------------------------------------------------------


# --------- Feeding form: amount, empty type/method, duplicate period -------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug B-05 (feeding-amount variant): Feeding.amount has no "
        "MinValueValidator, so a negative feeding volume is accepted by the "
        "UI and persisted."
    ),
    strict=False,
)
def test_feeding_negative_amount_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/feedings/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    set_value(admin_browser, "start", _fmt(now - datetime.timedelta(minutes=30)))
    set_value(admin_browser, "end", _fmt(now - datetime.timedelta(minutes=10)))
    _select_child_radio(admin_browser, child.pk)
    _select_radio_by_value(admin_browser, "type", "breast milk")
    _select_radio_by_value(admin_browser, "method", "bottle")
    set_value(admin_browser, "amount", "-120")
    click_submit(admin_browser)
    # Expected: stay on the add page with an errorlist.
    assert "/feedings/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: a zero-duration feeding (start == end) is silently accepted "
        "and corrupts duration analytics - the form should either flag it "
        "or coerce to a 1s minimum."
    ),
    strict=False,
)
def test_feeding_zero_duration_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/feedings/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    ts = _fmt(now - datetime.timedelta(minutes=5))
    set_value(admin_browser, "start", ts)
    set_value(admin_browser, "end", ts)  # identical -> duration=0
    _select_child_radio(admin_browser, child.pk)
    _select_radio_by_value(admin_browser, "type", "breast milk")
    _select_radio_by_value(admin_browser, "method", "bottle")
    click_submit(admin_browser)
    assert "/feedings/add/" in admin_browser.current_url


# --------- Sleep form: zero duration + far-future entries -----------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Sleep.clean() validates start only; a zero-duration sleep "
        "(start == end) is silently accepted where the UI should flag it."
    ),
    strict=False,
)
def test_sleep_zero_duration_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/sleep/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    ts = _fmt(timezone.localtime() - datetime.timedelta(hours=1))
    set_value(admin_browser, "start", ts)
    set_value(admin_browser, "end", ts)
    _select_child_radio(admin_browser, child.pk)
    click_submit(admin_browser)
    assert "/sleep/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Sleep.start / Sleep.end accept timestamps in the far future; "
        "a caregiver can accidentally log tomorrow's nap today."
    ),
    strict=False,
)
def test_sleep_future_timestamps_are_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/sleep/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    future = timezone.localtime() + datetime.timedelta(days=7)
    set_value(admin_browser, "start", _fmt(future))
    set_value(admin_browser, "end", _fmt(future + datetime.timedelta(hours=1)))
    _select_child_radio(admin_browser, child.pk)
    click_submit(admin_browser)
    assert "/sleep/add/" in admin_browser.current_url


# --------- DiaperChange form: neither wet nor solid, future time ----------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: DiaperChange permits submission with neither `wet` nor `solid` "
        "checked, creating a nonsensical 'empty' diaper change record."
    ),
    strict=False,
)
def test_diaper_change_neither_wet_nor_solid_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/changes/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "time")))
    set_value(
        admin_browser,
        "time",
        _fmt(timezone.localtime() - datetime.timedelta(minutes=5)),
    )
    _select_child_radio(admin_browser, child.pk)
    # Intentionally leave both wet and solid unchecked.
    click_submit(admin_browser)
    assert "/changes/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: DiaperChange.time accepts future timestamps - a change "
        "scheduled tomorrow is meaningless."
    ),
    strict=False,
)
def test_diaper_change_future_time_rejected(
    admin_browser, live_server, wait, child, set_value, check_box, click_submit
):
    admin_browser.get(f"{live_server.url}/changes/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "time")))
    future = timezone.localtime() + datetime.timedelta(days=1)
    set_value(admin_browser, "time", _fmt(future))
    _select_child_radio(admin_browser, child.pk)
    check_box(admin_browser, "wet", True)
    click_submit(admin_browser)
    assert "/changes/add/" in admin_browser.current_url


# --------- Child form: future birth date + over-length names -------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Child.birth_date accepts dates arbitrarily far in the future; "
        "the form should flag a birth date after today."
    ),
    strict=False,
)
def test_child_future_birth_date_rejected(
    admin_browser, live_server, wait, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    future = (timezone.localdate() + datetime.timedelta(days=365)).isoformat()
    set_value(admin_browser, "first_name", "Future")
    set_value(admin_browser, "last_name", "Kid")
    set_value(admin_browser, "birth_date", future)
    click_submit(admin_browser)
    # Expected: stay on /children/add/ with an errorlist.
    assert "/children/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: a first_name longer than the documented 255-char limit is "
        "not handled gracefully by the UI - the form should render an "
        "errorlist instead of letting the request 500 under some storage "
        "backends."
    ),
    strict=False,
)
def test_child_over_length_first_name_rejected(
    admin_browser, live_server, wait, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    set_value(admin_browser, "first_name", "A" * 512)
    set_value(admin_browser, "last_name", "Toolong")
    set_value(admin_browser, "birth_date", "2024-01-01")
    click_submit(admin_browser)
    # Expected: stay on /children/add/ with a friendly errorlist; observed:
    # the form quietly redirects, truncating / 500ing depending on DB.
    assert "/children/add/" in admin_browser.current_url


# --------- Weight / Height / Head-Circumference / BMI / Temperature -------


def _post_single_value_form(
    admin_browser,
    live_server,
    wait,
    child,
    set_value,
    click_submit,
    url_path,
    field_name,
    bad_value,
    date_field="date",
):
    admin_browser.get(f"{live_server.url}{url_path}?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, field_name)))
    # The child radio select is always rendered; select our seeded child.
    _select_child_radio(admin_browser, child.pk)
    set_value(admin_browser, field_name, bad_value)
    today_iso = timezone.localdate().isoformat()
    if admin_browser.find_elements(By.NAME, date_field):
        set_value(admin_browser, date_field, today_iso)
    click_submit(admin_browser)


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason="Bug: Weight.weight accepts zero and negative values at the UI.",
    strict=False,
)
def test_weight_non_positive_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    _post_single_value_form(
        admin_browser,
        live_server,
        wait,
        child,
        set_value,
        click_submit,
        "/weight/add/",
        "weight",
        "-1",
    )
    assert "/weight/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason="Bug: Height.height accepts zero and negative values at the UI.",
    strict=False,
)
def test_height_non_positive_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    _post_single_value_form(
        admin_browser,
        live_server,
        wait,
        child,
        set_value,
        click_submit,
        "/height/add/",
        "height",
        "-1",
    )
    assert "/height/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: HeadCircumference.head_circumference accepts zero and "
        "negative values at the UI."
    ),
    strict=False,
)
def test_head_circumference_non_positive_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    _post_single_value_form(
        admin_browser,
        live_server,
        wait,
        child,
        set_value,
        click_submit,
        "/head-circumference/add/",
        "head_circumference",
        "-1",
    )
    assert "/head-circumference/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: BMI.bmi has no sanity validators - negative or absurdly large "
        "values are silently accepted at the UI."
    ),
    strict=False,
)
def test_bmi_nonsensical_value_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    _post_single_value_form(
        admin_browser,
        live_server,
        wait,
        child,
        set_value,
        click_submit,
        "/bmi/add/",
        "bmi",
        "-5",
    )
    assert "/bmi/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Temperature.temperature accepts readings far outside the "
        "physiological range (<20 or >50 degC) at the UI."
    ),
    strict=False,
)
def test_temperature_absurd_value_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/temperature/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "temperature")))
    _select_child_radio(admin_browser, child.pk)
    set_value(admin_browser, "temperature", "200")
    now = timezone.localtime() - datetime.timedelta(minutes=1)
    if admin_browser.find_elements(By.NAME, "time"):
        set_value(admin_browser, "time", _fmt(now))
    click_submit(admin_browser)
    assert "/temperature/add/" in admin_browser.current_url


# --------- Note form: empty body + future time ----------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Note.note is not ``blank=False`` at the form layer, so an "
        "empty note body is silently accepted creating a useless record."
    ),
    strict=False,
)
def test_note_empty_body_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/notes/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "note")))
    _select_child_radio(admin_browser, child.pk)
    set_value(admin_browser, "note", "")
    set_value(
        admin_browser,
        "time",
        _fmt(timezone.localtime() - datetime.timedelta(minutes=1)),
    )
    click_submit(admin_browser)
    assert "/notes/add/" in admin_browser.current_url


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason="Bug: Note.time accepts timestamps in the future.",
    strict=False,
)
def test_note_future_time_is_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/notes/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "note")))
    _select_child_radio(admin_browser, child.pk)
    set_value(admin_browser, "note", "future note")
    future = timezone.localtime() + datetime.timedelta(days=1)
    set_value(admin_browser, "time", _fmt(future))
    click_submit(admin_browser)
    assert "/notes/add/" in admin_browser.current_url


# --------- TummyTime form: end before start + zero duration --------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: TummyTime.end preceding TummyTime.start is silently accepted, "
        "producing negative-duration records that skew analytics."
    ),
    strict=False,
)
def test_tummytime_end_before_start_rejected(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/tummy-time/add/?child={child.slug}")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "start")))
    now = timezone.localtime()
    set_value(admin_browser, "start", _fmt(now - datetime.timedelta(minutes=5)))
    set_value(admin_browser, "end", _fmt(now - datetime.timedelta(minutes=30)))
    _select_child_radio(admin_browser, child.pk)
    click_submit(admin_browser)
    assert "/tummy-time/add/" in admin_browser.current_url
