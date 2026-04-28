#####################################################
# Timer flow GUI tests                                #
#                                                     #
# Author: Samson Cournane                             #
#                                                     #
# Exercises the timer surface a caregiver actually    #
# uses: list page, add form, edit form, restart-via-  #
# POST, and delete.  The Timer model has a            #
# self-deleting `stop()` method, so what users call   #
# "stop" on the UI is in fact a delete.               #
#####################################################

from __future__ import annotations

import datetime

import pytest
from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC


def _seed_timer(child, user, name="Tracking Timer"):
    from core import models as core_models

    return core_models.Timer.objects.create(
        child=child,
        user=user,
        name=name,
        start=timezone.now() - datetime.timedelta(minutes=15),
    )


# ---------------------------------------------------------------------------
# A. Add form renders + valid timer save persists.
# ---------------------------------------------------------------------------


def test_timer_add_form_renders(admin_browser, live_server, wait, child):
    admin_browser.get(f"{live_server.url}/timers/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "name")))
    for fld in ("name", "start"):
        assert admin_browser.find_elements(
            By.NAME, fld
        ), f"Timer add form missing field {fld!r}"


def test_valid_timer_save_persists(
    admin_browser, live_server, wait, child, set_value, click_submit
):
    from core import models as core_models

    admin_browser.get(f"{live_server.url}/timers/add/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "name")))

    set_value(admin_browser, "name", "Nap timer")
    set_value(
        admin_browser,
        "start",
        (timezone.localtime() - datetime.timedelta(minutes=2)).strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
    )
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(lambda d: "/timers/add/" not in d.current_url)
    assert core_models.Timer.objects.filter(
        name="Nap timer"
    ).exists(), "Timer was not persisted after happy-path submit"


# ---------------------------------------------------------------------------
# B. Edit (update) form mutates the timer name.
# ---------------------------------------------------------------------------


def test_timer_edit_changes_name(
    admin_browser, live_server, wait, child, admin_user_gui, set_value, click_submit
):
    timer = _seed_timer(child, admin_user_gui, name="Old name")
    admin_browser.get(f"{live_server.url}/timers/{timer.pk}/edit/")
    wait(admin_browser).until(EC.presence_of_element_located((By.NAME, "name")))

    set_value(admin_browser, "name", "Renamed timer")
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/timers/{timer.pk}/edit/" not in d.current_url
    )
    timer.refresh_from_db()
    assert (
        timer.name == "Renamed timer"
    ), f"Timer name not updated; still {timer.name!r}"


# ---------------------------------------------------------------------------
# C. Restart: POST /timers/<pk>/restart/ resets `start` to now.
# ---------------------------------------------------------------------------


def test_timer_restart_resets_start(
    admin_browser, live_server, wait, child, admin_user_gui
):
    timer = _seed_timer(child, admin_user_gui)
    original_start = timer.start

    # The restart endpoint accepts POST.  Build a CSRF-aware in-page form
    # and submit it (the restart link in the UI does the same thing).
    admin_browser.get(f"{live_server.url}/timers/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    admin_browser.execute_script(
        """
        var token = document.querySelector("input[name='csrfmiddlewaretoken']");
        var f = document.createElement('form');
        f.method = 'POST';
        f.action = arguments[0];
        var t = document.createElement('input');
        t.name = 'csrfmiddlewaretoken';
        t.value = token ? token.value : '';
        f.appendChild(t);
        document.body.appendChild(f);
        f.submit();
        """,
        f"{live_server.url}/timers/{timer.pk}/restart/",
    )
    wait(admin_browser, timeout=15).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    timer.refresh_from_db()
    assert (
        timer.start > original_start
    ), f"Restart did not move start forward; original={original_start}, now={timer.start}"


# ---------------------------------------------------------------------------
# D. Stop (delete): POSTing to /timers/<pk>/delete/ removes the timer.
# ---------------------------------------------------------------------------


def test_timer_delete_removes_record(
    admin_browser, live_server, wait, child, admin_user_gui, click_submit
):
    from core import models as core_models

    timer = _seed_timer(child, admin_user_gui)
    admin_browser.get(f"{live_server.url}/timers/{timer.pk}/delete/")
    wait(admin_browser).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "form[method='post']"))
    )
    click_submit(admin_browser)
    wait(admin_browser, timeout=15).until(
        lambda d: f"/timers/{timer.pk}/delete/" not in d.current_url
    )
    assert not core_models.Timer.objects.filter(
        pk=timer.pk
    ).exists(), "Timer still exists after delete"


# ---------------------------------------------------------------------------
# E. Timer list renders the seeded timer's name.
# ---------------------------------------------------------------------------


def test_timer_list_renders_seeded_name(
    admin_browser, live_server, wait, child, admin_user_gui
):
    _seed_timer(child, admin_user_gui, name="Visible timer")
    admin_browser.get(f"{live_server.url}/timers/")
    wait(admin_browser).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    assert (
        "Visible timer" in admin_browser.page_source
    ), "Seeded timer name missing from /timers/ page"
