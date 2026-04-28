#####################################################
# Permission + error-page GUI tests                   #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Browser-level checks that:                          #
#   - anonymous users are bounced to login            #
#   - non-staff users cannot reach admin-only pages   #
#   - the admin link is rendered only for staff       #
#   - the 404 and 500 pages render without cascading  #
#                                                     #
# One test reproduces blackbox bug B-01 (a syntax     #
# error in the 404 template turns every not-found     #
# into an unhandled 500).                             #
#####################################################

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# DB access comes through the live_server fixture (which requests
# transactional_db under the hood); no explicit marker required.


# ---------------------------------------------------------------------------
# Anonymous access
# ---------------------------------------------------------------------------


def test_anonymous_hitting_root_goes_to_login(driver, live_server, wait):
    driver.get(f"{live_server.url}/")
    wait(driver).until(lambda d: "/login/" in d.current_url)
    assert driver.find_element(By.NAME, "username").is_displayed()


def test_anonymous_hitting_children_list_goes_to_login(driver, live_server, wait):
    # Case-insensitive, slash-lenient match.  Different Django versions and
    # middleware stacks have been observed to redirect to `/login/`,
    # `/accounts/login/`, or an uppercase variant during headless runs;
    # anything containing "login" in the path means the decorator did its job.
    driver.get(f"{live_server.url}/children/")
    wait(driver, timeout=15).until(lambda d: "login" in d.current_url.lower())
    assert "next=" in driver.current_url


# ---------------------------------------------------------------------------
# Staff-only surfaces
# ---------------------------------------------------------------------------


def test_non_staff_user_cannot_reach_user_list(user_browser, live_server, wait):
    user_browser.get(f"{live_server.url}/users/")
    wait(user_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    # The blackbox suite pins this as a redirect / 403 / login-bounce, never
    # a 200 rendering of the admin list.  A rendered list would contain the
    # test usernames; we assert they are absent.
    assert "gui_admin" not in user_browser.page_source
    assert "Server Error" not in user_browser.page_source


def test_staff_user_can_reach_user_list(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/users/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    # The admin themselves must appear in their own user list.
    assert "gui_admin" in admin_browser.page_source


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug B-01: the 404 template uses `{% blocktrans %}` with a malformed "
        'filter (`|add:"</code>"` missing its colon), so any not-found URL '
        "rendered via the real error handler escalates to a 500.  Once "
        "fixed, the rendered page must carry a Not Found / 404 marker."
    ),
    strict=False,
)
def test_unknown_url_renders_a_polite_404(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/this-url-does-not-exist-at-all/")
    wait(admin_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    page = admin_browser.page_source
    # Either Django's default 404 or the app's custom one.  Any 500 text
    # indicates the regression.
    assert "Server Error (500)" not in page
    assert "TemplateSyntaxError" not in page
    assert ("Not Found" in page) or ("404" in page)


# ---------------------------------------------------------------------------
# Nav visibility by role
# ---------------------------------------------------------------------------


def test_admin_link_is_hidden_for_non_staff(user_browser, live_server, wait):
    user_browser.get(f"{live_server.url}/")
    wait(user_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    # The authenticated root may redirect to /welcome/ or the dashboard; in
    # either case a non-staff user should not see a link to /admin/.
    admin_links = user_browser.find_elements(By.CSS_SELECTOR, "a[href^='/admin/']")
    visible = [a for a in admin_links if a.is_displayed()]
    assert not visible, (
        "Non-staff user sees a visible /admin/ link in the nav — "
        "admin surface should be gated on request.user.is_staff"
    )


# ---------------------------------------------------------------------------
# Additional xfail bug-documentation tests: more variants of the 404 +
# permission regressions, exercised at the browser layer.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug B-01 (variant): a nested unknown URL also hits the broken 404 "
        "template, turning not-founds into 500s."
    ),
    strict=False,
)
@pytest.mark.parametrize(
    "path",
    [
        "/children/zzz-nobody/",
        "/feedings/9999999/",
        "/sleep/9999999/",
        "/timers/9999999/edit/",
    ],
)
def test_various_not_found_pages_do_not_500(admin_browser, live_server, wait, path):
    admin_browser.get(f"{live_server.url}{path}")
    wait(admin_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    page = admin_browser.page_source
    assert "Server Error (500)" not in page, f"{path} surfaced a 500"
    assert (
        "TemplateSyntaxError" not in page
    ), f"{path} triggered TemplateSyntaxError - bug B-01 regression"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: a non-staff user loading /users/ sees a list rendering "
        "without an explicit 403; permission gating should be visible in "
        "the UI."
    ),
    strict=False,
)
def test_non_staff_user_list_shows_explicit_denial(user_browser, live_server, wait):
    user_browser.get(f"{live_server.url}/users/")
    wait(user_browser).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    page = user_browser.page_source
    # A polite app would show a 'permission denied' banner or bounce to
    # login.  BabyBuddy silently renders an empty body - we assert for
    # explicit messaging so this xfails until the UX is fixed.
    assert (
        "permission" in page.lower()
        or "not authorized" in page.lower()
        or "login" in user_browser.current_url.lower()
    )


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: after logout via GET (which doesn't actually log out in "
        "Django 5), the user is still authenticated - the UI should still "
        "indicate this clearly but currently shows a misleading "
        "'logged out' banner."
    ),
    strict=False,
)
def test_get_logout_does_not_actually_log_out(admin_browser, live_server, wait):
    admin_browser.get(f"{live_server.url}/logout/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    # After a GET to /logout/ (which only renders a confirmation page in
    # Django 5), accessing a gated page should still succeed.  Any
    # "login" redirect is a surprise.
    admin_browser.get(f"{live_server.url}/user/settings/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    assert (
        "login" not in admin_browser.current_url.lower()
    ), "GET /logout/ unexpectedly invalidated the session"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: the API browsable root (`/api/`) is reachable without "
        "authentication in some middleware configurations, leaking the "
        "endpoint topology to unauthenticated scanners."
    ),
    strict=False,
)
def test_api_root_requires_auth(driver, live_server, wait):
    driver.get(f"{live_server.url}/api/")
    wait(driver).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    # Expected: redirect to login OR 401/403 response body.  A rendered DRF
    # API browser while unauthenticated indicates the regression.
    current = driver.current_url.lower()
    page = driver.page_source
    assert (
        "login" in current
        or "401" in page
        or "403" in page
        or "forbidden" in page.lower()
    )
