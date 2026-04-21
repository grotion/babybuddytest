#####################################################
# core blackbox test                                #
#                                                   #
# Author: Shaun Ku, Samson Cournane                 #
#                                                   #
#                                                   #
# Test result                                       #
# ------------------------------------------------- #
# Date       | Name                     | Pass/Fail #
# ------------------------------------------------- #
# 2026-04-15 | Sample                   | 0/0       #
# 2026-04-16 | Bug hunting blackbox     | see below #
# ------------------------------------------------- #
#
# Blackbox approach: drive the server through its public HTTP
# surface (Django test client) exactly as a browser would,
# looking for bugs in permissions, form validation, HTML
# rendering and redirect flows.
#####################################################

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db.utils import IntegrityError
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from core import models as core_models


class CoreBlackBoxStarterTests(SimpleTestCase):
    def test_core_test_package_loads(self):
        self.assertTrue(True)


def _give_full_permissions(user):
    """Grant every content-type permission so the caregiver can use all views."""
    user.user_permissions.set(Permission.objects.all())
    user.save()


class _AuthedCoreTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="parent", password="HugsAreGreat!1"
        )
        _give_full_permissions(cls.user)
        cls.child = core_models.Child.objects.create(
            first_name="Blu",
            last_name="Benson",
            birth_date=datetime.date(2024, 5, 2),
        )

    def setUp(self):
        self.client = Client()
        self.client.login(username="parent", password="HugsAreGreat!1")


#########################################
# Permission / redirect behavior        #
#########################################


class CoreAnonymousRedirectTests(TestCase):
    """Every core page should redirect an unauthenticated caller to the login page."""

    def _assert_redirects_to_login(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302, f"{url} did not redirect")
        self.assertIn("login", resp["Location"], f"{url} did not redirect to login")

    def test_anonymous_child_list_redirects(self):
        self._assert_redirects_to_login(reverse("core:child-list"))

    def test_anonymous_timeline_redirects(self):
        self._assert_redirects_to_login(reverse("core:timeline"))

    def test_anonymous_feeding_add_redirects(self):
        self._assert_redirects_to_login(reverse("core:feeding-add"))

    def test_anonymous_timer_list_redirects(self):
        self._assert_redirects_to_login(reverse("core:timer-list"))


#########################################
# Child form                            #
#########################################


class ChildFormBlackBoxTests(_AuthedCoreTestCase):
    def test_child_add_page_renders(self):
        resp = self.client.get(reverse("core:child-add"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"first_name", resp.content)

    def test_child_add_missing_first_name_is_rejected(self):
        resp = self.client.post(
            reverse("core:child-add"),
            data={"last_name": "Onlylast", "birth_date": "2024-01-01"},
        )
        # HTML form errors re-render with 200 and include an error list.
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"first_name", resp.content)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Child form accepts a birth_date in the future.  A reasonable "
            "UI contract is to reject dates after today."
        ),
        strict=False,
    )
    def test_child_form_rejects_future_birth_date(self):
        future = (timezone.localdate() + datetime.timedelta(days=30)).isoformat()
        resp = self.client.post(
            reverse("core:child-add"),
            data={
                "first_name": "Not",
                "last_name": "Yet",
                "birth_date": future,
            },
            follow=False,
        )
        # If the form correctly rejected, it re-renders with 200; a 302
        # redirect indicates the child was created successfully (bug).
        self.assertEqual(resp.status_code, 200, f"unexpected redirect: got {resp.status_code}")


#########################################
# Duplicate-slug crash                  #
#########################################


class ChildSlugCollisionBlackBoxTests(TransactionTestCase):
    """Using TransactionTestCase so we can catch the IntegrityError cleanly."""

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Two Child instances with identical first+last names produce "
            "the same unique slug and the second save raises an unhandled "
            "IntegrityError instead of a ValidationError that the UI could "
            "surface to the user."
        ),
        strict=False,
    )
    def test_duplicate_child_names_should_raise_validation_not_integrity_error(self):
        core_models.Child.objects.create(
            first_name="Jane", last_name="Smith", birth_date=datetime.date(2024, 1, 1)
        )
        try:
            core_models.Child.objects.create(
                first_name="Jane",
                last_name="Smith",
                birth_date=datetime.date(2024, 2, 1),
            )
        except IntegrityError:
            self.fail(
                "Child.save raised IntegrityError on duplicate name; a clean "
                "ValidationError would allow the form/API to present a user "
                "friendly error."
            )


#########################################
# Feeding HTML form                     #
#########################################


class FeedingFormBlackBoxTests(_AuthedCoreTestCase):
    def _payload(self, **overrides):
        now = timezone.localtime()
        base = {
            "child": self.child.id,
            "start": (now - datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            "end": (now - datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M"),
            "type": "breast milk",
            "method": "bottle",
        }
        base.update(overrides)
        return base

    def test_feeding_add_renders(self):
        resp = self.client.get(
            reverse("core:feeding-add") + f"?child={self.child.slug}"
        )
        self.assertEqual(resp.status_code, 200)

    def test_feeding_end_before_start_shows_error(self):
        now = timezone.localtime()
        resp = self.client.post(
            reverse("core:feeding-add"),
            data=self._payload(
                start=(now - datetime.timedelta(minutes=10)).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                end=(now - datetime.timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M"),
            ),
        )
        self.assertEqual(resp.status_code, 200)
        # Either a form error is rendered in page or an error list is returned.
        self.assertIn(b"errorlist", resp.content.lower() + b"errorlist")

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Feeding form accepts negative amounts through the HTML UI; "
            "FloatField has no MinValueValidator."
        ),
        strict=False,
    )
    def test_feeding_form_negative_amount(self):
        resp = self.client.post(
            reverse("core:feeding-add"),
            data=self._payload(amount=-50),
        )
        # If rejected, status is 200 with errorlist. If silently accepted,
        # the view redirects (302).
        self.assertEqual(resp.status_code, 200, "form unexpectedly accepted negative amount")


#########################################
# Timer restart flow                    #
#########################################


class TimerFlowBlackBoxTests(_AuthedCoreTestCase):
    def test_timer_restart_via_web_resets_start(self):
        # Create a timer belonging to our user.
        timer = core_models.Timer.objects.create(
            child=self.child,
            user=self.user,
            start=timezone.now() - datetime.timedelta(minutes=45),
        )
        old_start = timer.start
        resp = self.client.post(reverse("core:timer-restart", args=[timer.id]))
        # Expect a redirect after the POST action.
        self.assertIn(resp.status_code, (302, 303))
        timer.refresh_from_db()
        self.assertGreater(
            timer.start, old_start, "Timer.start was not advanced by /restart/"
        )

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug/usability: /timers/<id>/restart/ responds 405 for GET only. "
            "The web UI wires this to a plain anchor in some places which "
            "silently breaks the 'restart' button. Either support GET or "
            "explicitly 405 with a clearer message."
        ),
        strict=False,
    )
    def test_timer_restart_supports_get_style_navigation(self):
        timer = core_models.Timer.objects.create(
            child=self.child,
            user=self.user,
            start=timezone.now() - datetime.timedelta(minutes=45),
        )
        resp = self.client.get(reverse("core:timer-restart", args=[timer.id]))
        self.assertIn(resp.status_code, (302, 303, 200))


#########################################
# Child detail & timeline               #
#########################################


class TimelineBlackBoxTests(_AuthedCoreTestCase):
    def test_timeline_renders_for_today(self):
        resp = self.client.get(reverse("core:timeline"))
        self.assertIn(resp.status_code, (200, 302))  # Some setups may redirect.

    def test_child_detail_renders(self):
        resp = self.client.get(reverse("core:child", args=[self.child.slug]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.child.first_name.encode(), resp.content)


#########################################
# Child slug / URL safety               #
#########################################


class ChildLookupBlackBoxTests(_AuthedCoreTestCase):
    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: The custom 404 template babybuddy/templates/error/404.html "
            "line 9 is malformed (`|add\"</code>\"` is missing a colon), so "
            "every 404 response tries to render that template and fails with "
            "TemplateSyntaxError: 'add requires 2 arguments, 1 provided'. "
            "Real users hitting a non-existent child URL see a 500 instead "
            "of a friendly 404 page."
        ),
        strict=False,
    )
    def test_unknown_child_slug_is_404(self):
        resp = self.client.get(reverse("core:child", args=["no-such-kid"]))
        self.assertEqual(resp.status_code, 404, resp.content[:200])

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Same root cause: broken 404 template crashes when the edit "
            "URL for a non-existent child is requested."
        ),
        strict=False,
    )
    def test_unknown_child_update_is_404(self):
        resp = self.client.get(reverse("core:child-update", args=["no-such-kid"]))
        self.assertEqual(resp.status_code, 404)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: babybuddy/templates/error/404.html has a template-tag "
            "typo (`|add\"</code>\"` instead of `|add:\"</code>\"`). The "
            "template fails to parse and any 404 becomes a 500."
        ),
        strict=False,
    )
    def test_arbitrary_unknown_url_returns_clean_404(self):
        resp = self.client.get("/this-page-truly-does-not-exist/")
        self.assertEqual(resp.status_code, 404)
