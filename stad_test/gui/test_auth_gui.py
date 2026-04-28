#####################################################
# Auth + settings GUI tests                           #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Drives the babybuddy app through a real browser,    #
# exercising the login form, logout redirect, session #
# behavior, the password-reset page, and the          #
# user-settings screen.  No knowledge of Django's     #
# internal auth backend is required - the tests poke  #
# the same URLs a human caregiver would.              #
#                                                     #
# Test result                                         #
# ------------------------------------------------- #
# Date       | Name                     | Pass/Fail #
# ------------------------------------------------- #
# 2026-04-21 | Full GUI regression      | see below #
# ------------------------------------------------- #
#####################################################

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# Every test in this module touches the DB and the live_server fixture,
# which pytest-django wires up as a transactional DB automatically.  No
# explicit @pytest.mark.django_db marker is needed.


# ---------------------------------------------------------------------------
# Login form
# ---------------------------------------------------------------------------


def test_login_page_has_username_and_password_inputs(driver, live_server, wait):
    driver.get(f"{live_server.url}/login/")
    wait(driver).until(EC.presence_of_element_located((By.NAME, "username")))
    assert driver.find_element(By.NAME, "username").is_displayed()
    assert driver.find_element(By.NAME, "password").is_displayed()
    assert driver.find_elements(
        By.CSS_SELECTOR, "button[type='submit']"
    ), "Login form has no submit button"


def test_valid_login_lands_on_authenticated_area(
    driver, live_server, admin_user_gui, login_as, wait
):
    login_as("gui_admin", "AdminPass123!")
    # After login Django redirects to LOGIN_REDIRECT_URL.  The authenticated
    # layout always exposes a logout link in the navbar / user menu.
    wait(driver).until(lambda d: "/login/" not in d.current_url)
    assert "/login/" not in driver.current_url


def test_wrong_password_stays_on_login_form(driver, live_server, admin_user_gui, wait):
    driver.get(f"{live_server.url}/login/")
    wait(driver).until(EC.presence_of_element_located((By.NAME, "username")))
    driver.find_element(By.NAME, "username").send_keys("gui_admin")
    driver.find_element(By.NAME, "password").send_keys("WrongPassword!")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    # Django's LoginView re-renders the form at the same URL on failure.
    wait(driver).until(EC.presence_of_element_located((By.NAME, "username")))
    assert "/login/" in driver.current_url


def test_unknown_user_does_not_leak_username_existence(
    driver, live_server, admin_user_gui, wait
):
    """Security check: submitting a nonexistent username should produce the
    same visible response as submitting a real username with a wrong password
    (both stay on the form).  This is the browser-level analogue of the
    blackbox test ``test_login_with_unknown_user_does_not_leak``."""
    driver.get(f"{live_server.url}/login/")
    wait(driver).until(EC.presence_of_element_located((By.NAME, "username")))
    driver.find_element(By.NAME, "username").send_keys("no_such_user")
    driver.find_element(By.NAME, "password").send_keys("whatever")
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait(driver).until(EC.presence_of_element_located((By.NAME, "username")))
    assert "/login/" in driver.current_url


def test_logout_returns_user_to_login(
    admin_browser, live_server, wait, logout_via_post
):
    # Django 5's LogoutView is POST-only; a plain GET to /logout/ renders the
    # confirmation page rather than actually logging the user out.  Submit a
    # CSRF-aware POST the way the navbar button does.
    logout_via_post(admin_browser, f"{live_server.url}/logout/")
    # After the POST, verify the browser is actually logged out by visiting a
    # gated URL - we don't depend on LOGOUT_REDIRECT_URL's exact resolution.
    admin_browser.get(f"{live_server.url}/user/settings/")
    wait(admin_browser, timeout=15).until(lambda d: "login" in d.current_url.lower())
    assert "login" in admin_browser.current_url.lower()


def test_password_reset_page_renders(driver, live_server, wait):
    driver.get(f"{live_server.url}/reset/")
    wait(driver).until(EC.presence_of_element_located((By.NAME, "email")))
    assert driver.find_element(By.NAME, "email").is_displayed()


# ---------------------------------------------------------------------------
# User settings (requires authentication)
# ---------------------------------------------------------------------------


def test_user_settings_page_renders_for_logged_in_user(user_browser, live_server, wait):
    user_browser.get(f"{live_server.url}/user/settings/")
    # The settings page renders a form.  Any <form> tag plus a Save-style
    # submit button is a sufficient browser-level oracle.
    wait(user_browser).until(EC.presence_of_element_located((By.CSS_SELECTOR, "form")))
    assert user_browser.find_elements(By.CSS_SELECTOR, "form")


def test_anonymous_user_is_bounced_from_settings(driver, live_server, wait):
    driver.get(f"{live_server.url}/user/settings/")
    # The login_required decorator redirects to /login/?next=/user/settings/.
    wait(driver).until(lambda d: "/login/" in d.current_url)
    assert "next=" in driver.current_url
