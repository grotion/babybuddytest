#####################################################
# Mobile / responsive viewport GUI tests              #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# The default driver fixture uses a 1280x900 desktop  #
# viewport.  Caregivers actually open Baby Buddy on   #
# their phones, so we drive the browser at an iPhone  #
# 13 viewport (390x844 CSS px) and assert that:       #
#   - the dashboard renders without horizontal scroll #
#   - the navbar collapses behind a hamburger toggle  #
#   - a real form (the child add page) is still       #
#     usable end-to-end                               #
#                                                     #
# We attach a per-test fixture that resizes the same  #
# browser used by admin_browser, then runs the test.  #
# The driver fixture itself is function-scoped so the #
# resize never leaks into a later test.               #
#####################################################

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

# Reasonably common phone CSS-pixel dimensions (iPhone 13 / Pixel 5).
MOBILE_W = 390
MOBILE_H = 844


@pytest.fixture
def mobile_admin_browser(admin_browser):
    """admin_browser pre-resized to a phone viewport.

    We resize *after* login so the login page still renders at desktop
    width (Baby Buddy's login template has its own quirks under narrow
    viewports that aren't the subject of these tests).
    """
    admin_browser.set_window_size(MOBILE_W, MOBILE_H)
    return admin_browser


# ---------------------------------------------------------------------------
# A. Dashboard renders without horizontal overflow at phone width.
#
# A common mobile-CSS regression is a fixed-width child element forcing the
# document into horizontal scroll.  We compare scrollWidth to clientWidth on
# the documentElement: if scrollWidth exceeds clientWidth by more than a
# couple of pixels (rounding fudge) the layout is overflowing.
# ---------------------------------------------------------------------------


def test_dashboard_no_horizontal_overflow_on_mobile(
    mobile_admin_browser, live_server, wait, child
):
    mobile_admin_browser.get(f"{live_server.url}/")
    wait(mobile_admin_browser).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    overflow_px = mobile_admin_browser.execute_script("""
        var de = document.documentElement;
        return de.scrollWidth - de.clientWidth;
        """)
    # Allow up to 4px of subpixel rounding noise; anything more is real
    # overflow.
    assert overflow_px <= 4, (
        f"Dashboard horizontally overflows the {MOBILE_W}px viewport by "
        f"{overflow_px}px (a fixed-width element is leaking out)"
    )


# ---------------------------------------------------------------------------
# B. The navbar collapses behind the hamburger toggle on mobile.
#
# Bootstrap renders <button class="navbar-toggler"> only when the navbar is
# in collapsed mode, i.e. screen < lg breakpoint.  At desktop widths the
# button is hidden via display:none; at mobile widths it must be visible.
# ---------------------------------------------------------------------------


def test_navbar_collapses_to_hamburger_on_mobile(
    mobile_admin_browser, live_server, wait, child
):
    mobile_admin_browser.get(f"{live_server.url}/")
    wait(mobile_admin_browser).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    togglers = mobile_admin_browser.find_elements(
        By.CSS_SELECTOR, "button.navbar-toggler"
    )
    assert togglers, "No <button class='navbar-toggler'> rendered at all"
    visible = [t for t in togglers if t.is_displayed()]
    assert visible, (
        "Hamburger toggler is present in the DOM but not displayed at "
        f"{MOBILE_W}x{MOBILE_H} - the navbar isn't collapsing on mobile"
    )


# ---------------------------------------------------------------------------
# C. Child add form is reachable and submittable at phone width.
#
# A regression where, say, a wide <table> inside the form pushes the submit
# button off-screen would cause click_submit's `.scrollIntoView()` to still
# work (we're calling it via JS) but the form layout itself would be busted.
# We assert two things at once: the input is laid out (visible) and the
# happy-path save still persists.
# ---------------------------------------------------------------------------


def test_child_add_form_works_on_mobile(
    mobile_admin_browser, live_server, wait, set_value, click_submit
):
    from core import models as core_models

    mobile_admin_browser.get(f"{live_server.url}/children/add/")
    wait(mobile_admin_browser).until(
        EC.presence_of_element_located((By.NAME, "first_name"))
    )

    # Fields must be in the visible viewport - not display:none, not
    # zero-height, and within the document body (catches off-canvas-only
    # widgets that never reach mobile users).
    for fld in ("first_name", "last_name", "birth_date"):
        el = mobile_admin_browser.find_element(By.NAME, fld)
        assert (
            el.is_displayed()
        ), f"Child add form field {fld!r} is hidden at {MOBILE_W}px width"

    set_value(mobile_admin_browser, "first_name", "Mobile")
    set_value(mobile_admin_browser, "last_name", "User")
    set_value(mobile_admin_browser, "birth_date", "2024-06-01")
    click_submit(mobile_admin_browser)
    wait(mobile_admin_browser, timeout=15).until(
        lambda d: "/children/add/" not in d.current_url
    )
    assert core_models.Child.objects.filter(
        first_name="Mobile", last_name="User"
    ).exists(), "Child add form failed to persist record at mobile width"


# ---------------------------------------------------------------------------
# D. xfail: clicking the hamburger should expand the nav menu.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: tapping the navbar-toggler does not toggle the aria-expanded "
        "attribute on headless Chrome under Bootstrap 5; the collapse menu "
        "stays hidden until a second tap.  Likely a bootstrap.bundle.js "
        "load-order race specific to the mobile breakpoint."
    ),
    strict=False,
)
def test_hamburger_click_expands_menu(mobile_admin_browser, live_server, wait, child):
    mobile_admin_browser.get(f"{live_server.url}/")
    wait(mobile_admin_browser).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "button.navbar-toggler"))
    )
    toggler = mobile_admin_browser.find_element(
        By.CSS_SELECTOR, "button.navbar-toggler"
    )
    toggler.click()
    # After a click, aria-expanded flips to "true".
    assert (
        toggler.get_attribute("aria-expanded") == "true"
    ), "Hamburger did not toggle aria-expanded -> menu cannot open on mobile"
