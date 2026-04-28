#####################################################
# API token / device pairing GUI tests                #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Drives the /user/add-device/ page from a real       #
# browser - the entry point caregivers use to pair    #
# the mobile app with their account.  The page renders#
# the user's API key, a regenerate-key form, and a    #
# QR code containing a login URL.                     #
#####################################################

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


def test_add_device_page_renders_for_authed_user(user_browser, live_server, wait):
    """Logged-in users must be able to load the device pairing screen."""
    user_browser.get(f"{live_server.url}/user/add-device/")
    wait(user_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    page = user_browser.page_source
    # The page should expose the API key block and at least one form.
    assert user_browser.find_elements(
        By.CSS_SELECTOR, "form[method='post']"
    ), "/user/add-device/ rendered without any POST form"
    # And it must not 500.
    assert "Server Error" not in page, "/user/add-device/ surfaced a 500"


def test_add_device_anonymous_user_is_bounced(driver, live_server, wait):
    """Unauthenticated callers must be sent to login (the page leaks the
    user's API key, so it absolutely cannot be public)."""
    driver.get(f"{live_server.url}/user/add-device/")
    wait(driver, timeout=15).until(lambda d: "login" in d.current_url.lower())
    assert "login" in driver.current_url.lower()


def test_regenerate_api_key_rotates_token(
    user_browser, live_server, wait, normal_user, click_submit
):
    """Clicking Regenerate must actually mint a new key for the user."""
    # Seed the user's API key so we have a baseline to compare against.
    # Baby Buddy's Settings.api_key() lazily creates a DRF Token if none
    # exists; we reach in and grab the underlying token.key directly so
    # we can compare before and after the regenerate POST.
    from rest_framework.authtoken.models import Token

    token, _ = Token.objects.get_or_create(user=normal_user)
    original_key = token.key
    assert original_key, "User has no API key to start with"

    user_browser.get(f"{live_server.url}/user/add-device/")
    wait(user_browser).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[name='api_key_regenerate']")
        )
    )
    # The regenerate button is an ``<input type="submit">`` named
    # ``api_key_regenerate``; click_submit accepts an explicit selector.
    click_submit(user_browser, "input[name='api_key_regenerate']")
    wait(user_browser, timeout=15).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    # The original Token was deleted; a new one is created on the next
    # api_key() call, so we re-fetch from the DB.
    new_token = Token.objects.get(user=normal_user)
    assert new_token.key != original_key, "Regenerate did not rotate the API key"
