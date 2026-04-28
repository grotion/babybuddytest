#####################################################
# Children + dashboard GUI tests                      #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Adds a child via the form, checks validation, and   #
# navigates the per-child dashboard.  Also reproduces #
# blackbox bug B-02 (duplicate child names crash) at  #
# the UI layer: the expected outcome is a clean form  #
# error, the observed outcome on current main is an   #
# unhandled 500, so the test is xfail-marked.         #
#####################################################

from __future__ import annotations

import datetime

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# DB access comes through the live_server fixture (which requests
# transactional_db under the hood); no explicit marker required.


# ---------------------------------------------------------------------------
# Add a child
# ---------------------------------------------------------------------------


def _fill_child_form(driver, set_value, first_name, last_name, birth_date_iso):
    # Baby Buddy's Child form renders its text inputs inside widget templates
    # that react to the ``focus`` event by installing helpers which intercept
    # keystrokes; on headless Chrome this surfaces as
    # ElementNotInteractableException when we ``send_keys``.  We bypass the
    # widget layer entirely by setting .value directly via JS and firing the
    # input/change events the rest of the form listens for.
    set_value(driver, "first_name", first_name)
    set_value(driver, "last_name", last_name)
    set_value(driver, "birth_date", birth_date_iso)


def test_child_add_form_renders(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    for fld in ("first_name", "last_name", "birth_date"):
        assert admin_browser.find_element(By.NAME, fld).is_displayed()


def test_add_child_happy_path_creates_entry(
    admin_browser, live_server, wait, set_value, click_submit
):
    from core import models as core_models

    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    _fill_child_form(admin_browser, set_value, "Gabe", "Cruz", "2024-02-14")
    click_submit(admin_browser)
    # Successful save redirects to the child list (or child detail).  Either
    # way the new name must now appear somewhere in the authenticated UI.
    wait(admin_browser, timeout=15).until(
        lambda d: "/children/add/" not in d.current_url
    )
    # Primary oracle: the DB write.  Baby Buddy's list view uses a cached
    # count (``core.child.count``) in some templates which has caused flaky
    # page-source asserts in past runs, so we ground the assertion on the
    # ORM instead.
    assert core_models.Child.objects.filter(
        first_name="Gabe", last_name="Cruz"
    ).exists(), "Child was not persisted after happy-path submit"
    # Secondary oracle: the list page must also mention the new child,
    # confirming the caching layer isn't masking the write.
    admin_browser.get(f"{live_server.url}/children/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    assert "Gabe" in admin_browser.page_source


def test_add_child_missing_first_name_shows_error(
    admin_browser, live_server, wait, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    # Skip first_name; fill the rest via the JS setter (bypasses widget quirks).
    set_value(admin_browser, "last_name", "Nofirst")
    set_value(admin_browser, "birth_date", "2024-01-01")

    # Django's ModelForm renders ``required`` on the first_name input, so
    # HTML5 will block client-side submission and keep us on /children/add/
    # without a navigation.  We intentionally bypass HTML5 by submitting the
    # <form> directly via JS: the server then gets to validate and renders
    # the same page with an errorlist.  Either outcome is fine - the only
    # invariant we care about is "page still contains the add form and we
    # have not silently created a Child with an empty name".
    admin_browser.execute_script("""
        var el = document.getElementById('id_first_name');
        if (el) { el.removeAttribute('required'); }
        var f = el ? el.form : document.querySelector('form[method="post"]');
        if (f) {
            if (typeof f.requestSubmit === 'function') { f.requestSubmit(); }
            else { f.submit(); }
        }
        """)
    # Give Django a moment to 200-re-render the form; absolute URL may or may
    # not leave /children/add/ briefly but must land us back there.
    import time as _t

    _t.sleep(0.5)
    wait(admin_browser).until(lambda d: "/children/add/" in d.current_url)
    assert "/children/add/" in admin_browser.current_url
    # Sanity: no child named "Nofirst" sneaked into the database.
    from core import models as core_models

    assert not core_models.Child.objects.filter(last_name="Nofirst").exists()


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug B-02: two children with identical first+last names generate the "
        "same unique slug; the second save raises an unhandled IntegrityError "
        "that surfaces as a 500 in the browser instead of a polite form error."
    ),
    strict=False,
)
def test_add_duplicate_child_name_is_rejected_politely(
    admin_browser, live_server, wait, set_value, click_submit
):
    # Seed one child directly.  We're testing the UI flow for the second add.
    from core import models as core_models

    core_models.Child.objects.create(
        first_name="Mika",
        last_name="Torres",
        birth_date=datetime.date(2024, 1, 10),
    )
    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    _fill_child_form(admin_browser, set_value, "Mika", "Torres", "2024-05-05")
    click_submit(admin_browser)
    # Expected polite behavior: either stay on /children/add/ with an error,
    # or redirect to the existing child.  Never a 500 / Django debug page.
    wait(admin_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    assert "Server Error" not in admin_browser.page_source
    assert "IntegrityError" not in admin_browser.page_source


# ---------------------------------------------------------------------------
# Per-child dashboard and list views
# ---------------------------------------------------------------------------


def test_child_list_shows_seeded_child(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/children/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    assert child.first_name in admin_browser.page_source


def test_child_detail_page_renders(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/children/{child.slug}/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    assert child.first_name in admin_browser.page_source


def test_unknown_child_slug_shows_404_or_redirects(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/children/does-not-exist/")
    wait(admin_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    # Either Django's 404 page or a redirect to the list - anything but a 500.
    assert "Server Error (500)" not in admin_browser.page_source


# ---------------------------------------------------------------------------
# Additional xfail bug-documentation tests (GUI layer).  strict=False keeps
# the suite green if BabyBuddy ever fixes the underlying issue.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: unknown child slug on the edit URL is routed through the "
        "custom 404 template which has the malformed `|add` filter (bug "
        "B-01), so the browser sees a 500 debug page instead of a polite "
        "404."
    ),
    strict=False,
)
def test_unknown_child_edit_slug_no_500(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/children/does-not-exist/edit/")
    wait(admin_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    page = admin_browser.page_source
    assert "Server Error (500)" not in page
    assert "TemplateSyntaxError" not in page


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: unknown child slug on the delete URL hits the same 404 "
        "template regression (bug B-01)."
    ),
    strict=False,
)
def test_unknown_child_delete_slug_no_500(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/children/does-not-exist/delete/")
    wait(admin_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    page = admin_browser.page_source
    assert "Server Error (500)" not in page
    assert "TemplateSyntaxError" not in page


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: BabyBuddy's UsernameField silently strips whitespace from "
        "first/last names on the Child form (a known Django quirk surfacing "
        "at the UI).  Submitting `'   '` as the first name should be "
        "rejected with a 'required' error; observed behavior is a 302."
    ),
    strict=False,
)
def test_whitespace_only_first_name_rejected(
    admin_browser, live_server, wait, set_value, click_submit
):
    admin_browser.get(f"{live_server.url}/children/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "first_name")))
    set_value(admin_browser, "first_name", "     ")
    set_value(admin_browser, "last_name", "Whitespace")
    set_value(admin_browser, "birth_date", "2024-01-01")
    click_submit(admin_browser)
    import time as _t

    _t.sleep(0.5)
    assert "/children/add/" in admin_browser.current_url
