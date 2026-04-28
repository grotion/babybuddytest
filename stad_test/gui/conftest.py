#####################################################
# GUI test fixtures                                   #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Selenium + pytest-django live_server harness.       #
# The conftest provides:                              #
#   - a --headed CLI flag so the demo can be watched  #
#   - a Chrome WebDriver fixture (function scoped)    #
#   - seed data fixtures: admin_user, normal_user,    #
#     child                                           #
#   - login helpers (login_as) and a ready-made       #
#     admin_browser fixture                           #
#                                                     #
# No imports from core.views / api.views / babybuddy  #
# .views or dashboard.views - we drive the real       #
# running server exactly as a human user would.       #
#####################################################

from __future__ import annotations

import datetime
import os
from typing import Callable

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    # webdriver-manager transparently downloads a ChromeDriver that matches the
    # user's installed Chrome.  Falling back to the default Service() path lets
    # us run on CI boxes where the driver is already on PATH.
    from webdriver_manager.chrome import ChromeDriverManager

    _HAS_WDM = True
except ImportError:  # pragma: no cover - only hit if dev didn't install deps
    _HAS_WDM = False


# ---------------------------------------------------------------------------
# WebDriver
#
# Note: the --headed and --slow-gui CLI flags are registered in
# stad_test/conftest.py (pytest requires pytest_addoption to live at or
# above the rootdir).  We just read them here via request.config.getoption.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def chrome_options(request):
    opts = Options()
    if not request.config.getoption("--headed"):
        # --headless=new is the modern flag.  The old "--headless" still works
        # but emits a deprecation warning on Chrome >= 109.
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    # Suppress the DevTools listening log line on Windows.
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    return opts


@pytest.fixture
def driver(chrome_options, request):
    """A fresh Chrome WebDriver per test.  Function-scoped so state never
    leaks between tests (cookies, localStorage, etc.)."""
    if _HAS_WDM:
        service = Service(ChromeDriverManager().install())
    else:
        service = Service()  # relies on chromedriver being on PATH

    drv = webdriver.Chrome(service=service, options=chrome_options)
    drv.set_page_load_timeout(30)
    drv.implicitly_wait(0)  # we use explicit waits everywhere

    # Slow-demo mode: after every .get(), pause briefly.
    if request.config.getoption("--slow-gui"):
        original_get = drv.get

        def slow_get(url):
            original_get(url)
            import time

            time.sleep(0.5)

        drv.get = slow_get  # type: ignore[assignment]

    yield drv

    drv.quit()


# ---------------------------------------------------------------------------
# Users + seed data (pytest-django database fixtures)
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_user_gui(transactional_db, django_user_model):
    """A superuser.  Named *_gui to avoid shadowing pytest-django's own
    admin_user fixture, which uses a different default password.

    We depend on ``transactional_db`` rather than ``db`` so the live_server
    thread sees our writes without transaction isolation games."""
    return django_user_model.objects.create_superuser(
        username="gui_admin",
        email="gui_admin@example.com",
        password="AdminPass123!",
    )


@pytest.fixture
def normal_user(transactional_db, django_user_model):
    """A regular authenticated user with no special permissions."""
    return django_user_model.objects.create_user(
        username="gui_parent",
        email="gui_parent@example.com",
        password="ParentPass123!",
    )


@pytest.fixture
def second_user(transactional_db, django_user_model):
    """A second, unrelated user - for cross-user permission tests."""
    return django_user_model.objects.create_user(
        username="gui_stranger",
        email="gui_stranger@example.com",
        password="StrangerPass123!",
    )


@pytest.fixture
def child(transactional_db, admin_user_gui):
    """A single Child in the DB, visible to the browser-authenticated user."""
    from core import models as core_models

    return core_models.Child.objects.create(
        first_name="Rosa",
        last_name="Diaz",
        birth_date=datetime.date(2024, 3, 15),
    )


# ---------------------------------------------------------------------------
# Login helpers
# ---------------------------------------------------------------------------


def _login_via_form(driver, live_server_url: str, username: str, password: str) -> None:
    driver.get(f"{live_server_url}/login/")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.NAME, "username"))
    )
    driver.find_element(By.NAME, "username").send_keys(username)
    driver.find_element(By.NAME, "password").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    # The login view redirects (302) to LOGIN_REDIRECT_URL.  Wait until we've
    # definitely left the login form.
    WebDriverWait(driver, 10).until(lambda d: "/login/" not in d.current_url)


@pytest.fixture
def login_as(driver, live_server) -> Callable[[str, str], None]:
    """Callable that logs `driver` in with the given credentials."""

    def _do(username: str, password: str) -> None:
        _login_via_form(driver, live_server.url, username, password)

    return _do


@pytest.fixture
def admin_browser(driver, live_server, admin_user_gui):
    """A driver already logged in as the superuser `gui_admin`."""
    _login_via_form(driver, live_server.url, "gui_admin", "AdminPass123!")
    return driver


@pytest.fixture
def user_browser(driver, live_server, normal_user):
    """A driver already logged in as the regular user `gui_parent`."""
    _login_via_form(driver, live_server.url, "gui_parent", "ParentPass123!")
    return driver


# ---------------------------------------------------------------------------
# Small helpers exported for use in tests
# ---------------------------------------------------------------------------


@pytest.fixture
def wait():
    """Return a factory that builds a WebDriverWait for the given driver."""

    def _wait(drv, timeout: int = 10) -> WebDriverWait:
        return WebDriverWait(drv, timeout)

    return _wait


@pytest.fixture
def set_value():
    """Robust replacement for ``element.send_keys`` that handles inputs hidden
    behind custom widgets (DateTimeInput flatpickr, PillRadioSelect, etc.).

    Finds the element by its Django-generated id (``id_<field_name>``), scrolls
    it into view, focuses it, sets ``.value`` directly, then dispatches both
    ``input`` and ``change`` events so any listener-driven validation runs.
    """

    def _set(driver, field_name: str, value: str) -> None:
        driver.execute_script(
            """
            var el = document.getElementById('id_' + arguments[0])
                  || document.querySelector('[name="' + arguments[0] + '"]');
            if (!el) { throw new Error('No form field named ' + arguments[0]); }
            el.scrollIntoView({block: 'center'});
            el.focus();
            el.value = arguments[1];
            el.dispatchEvent(new Event('input',  {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            field_name,
            value,
        )

    return _set


@pytest.fixture
def check_box():
    """Tick a Bootstrap ``btn-check d-none`` checkbox via JS.  The visible
    surface is a ``<label>``; the underlying ``<input>`` has ``d-none`` so a
    plain Selenium click goes to the label instead and ``send_keys`` blows up
    with ``ElementNotInteractableException``.
    """

    def _check(driver, field_name: str, checked: bool = True) -> None:
        driver.execute_script(
            """
            var el = document.getElementById('id_' + arguments[0])
                  || document.querySelector('[name="' + arguments[0] + '"]');
            if (!el) { throw new Error('No checkbox named ' + arguments[0]); }
            if (el.checked !== arguments[1]) {
                el.checked = arguments[1];
                el.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            field_name,
            checked,
        )

    return _check


@pytest.fixture
def click_submit():
    """Robust replacement for ``find_element(..., "button[type='submit']").click()``.

    Baby Buddy's ``form.html`` renders ``{{ field.widget }}`` debris alongside
    every field, which inflates page height and regularly pushes the primary
    submit button below the viewport.  Selenium's standard ``.click()`` then
    raises ``ElementNotInteractableException`` on headless Chrome.

    In addition to the viewport issue, the authenticated navbar contains its
    own ``<form>`` (the Logout dropdown button) whose ``<button>`` tag is
    rendered BEFORE the content form.  A plain ``document.querySelector``
    would pick that navbar button first and log the test user out instead of
    submitting the content form.  To avoid both problems we:

    1. Prefer the ``.submit-primary`` class that ``babybuddy/form.html`` puts
       on the main Submit button.
    2. Fall back to the **last** ``button[type='submit']`` in the DOM, which
       is empirically the content form's button (navbar dropdowns come first).
    3. Finally, if we still can't find it, use ``HTMLFormElement.requestSubmit``
       on the closest ``<form>`` element that wraps any of the named fields.
    """

    def _click(driver, selector: str = ".submit-primary") -> None:
        driver.execute_script(
            """
            var selector = arguments[0];
            var btn = document.querySelector(selector);
            if (!btn) {
                // Fall back: last submit button on the page (content form).
                var all = document.querySelectorAll("button[type='submit'], input[type='submit']");
                if (all.length > 0) { btn = all[all.length - 1]; }
            }
            if (!btn) {
                // Ultimate fallback: submit the first non-navbar <form> directly.
                var forms = document.querySelectorAll("form");
                for (var i = 0; i < forms.length; i++) {
                    var f = forms[i];
                    // Skip the tiny logout form (only has csrf + a bare button).
                    if (f.querySelector("input[name='first_name'], input[name='start'], input[name='time'], input[name='name'], input[name='weight'], input[name='height'], input[name='temperature'], input[name='bmi'], input[name='head_circumference'], input[name='amount'], textarea, select")) {
                        if (typeof f.requestSubmit === 'function') { f.requestSubmit(); }
                        else { f.submit(); }
                        return;
                    }
                }
                throw new Error('No submit button matching ' + selector + ' and no suitable form found');
            }
            btn.scrollIntoView({block: 'center'});
            btn.click();
            """,
            selector,
        )

    return _click


@pytest.fixture
def logout_via_post():
    """Django 5's ``LogoutView`` requires POST.  Build a CSRF-aware POST form
    in-page and submit it so the server actually logs the browser out.  Block
    until the navigation away from the current page completes - the POST is
    asynchronous, so a test that immediately asserts on ``current_url`` would
    otherwise race the server's 302."""

    def _logout(driver, logout_url: str) -> None:
        before = driver.current_url
        # Preferred path: the authenticated nav-dropdown already contains a
        # <form method="post" action="/logout/"> with a {% csrf_token %}
        # hidden input.  Submitting *that* form delegates CSRF extraction to
        # Django's own template layer and avoids the JS-vs-cookie flakiness we
        # hit on headless Chrome, where the csrftoken cookie is occasionally
        # still marked "pending" when we try to read it.
        clicked = driver.execute_script("""
            var forms = document.querySelectorAll("form[action$='/logout/']");
            for (var i = 0; i < forms.length; i++) {
                var tok = forms[i].querySelector("input[name='csrfmiddlewaretoken']");
                if (tok && tok.value) {
                    if (typeof forms[i].requestSubmit === 'function') {
                        forms[i].requestSubmit();
                    } else {
                        forms[i].submit();
                    }
                    return true;
                }
            }
            return false;
            """)
        if not clicked:
            # Fall back: read CSRF from *any* rendered form on the page
            # (DRF's browsable API and every Baby Buddy form embed one),
            # then build & submit a synthetic POST form.
            driver.execute_script(
                """
                var tok = document.querySelector("input[name='csrfmiddlewaretoken']");
                var token = tok ? tok.value : '';
                if (!token) {
                    var csrfCookie = document.cookie.split('; ').find(
                        function (c) { return c.startsWith('csrftoken='); }
                    );
                    token = csrfCookie ? csrfCookie.split('=')[1] : '';
                }
                var f = document.createElement('form');
                f.method = 'POST';
                f.action = arguments[0];
                var t = document.createElement('input');
                t.name = 'csrfmiddlewaretoken';
                t.value = token;
                f.appendChild(t);
                document.body.appendChild(f);
                f.submit();
                """,
                logout_url,
            )
        # Block briefly until the browser has navigated off the pre-POST URL.
        WebDriverWait(driver, 10).until(lambda d: d.current_url != before)

    return _logout
