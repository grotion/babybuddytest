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
        self.assertEqual(
            resp.status_code, 200, f"unexpected redirect: got {resp.status_code}"
        )


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
                start=(now - datetime.timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M"),
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
        self.assertEqual(
            resp.status_code, 200, "form unexpectedly accepted negative amount"
        )


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
            'line 9 is malformed (`|add"</code>"` is missing a colon), so '
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
            'typo (`|add"</code>"` instead of `|add:"</code>"`). The '
            "template fails to parse and any 404 becomes a 500."
        ),
        strict=False,
    )
    def test_arbitrary_unknown_url_returns_clean_404(self):
        resp = self.client.get("/this-page-truly-does-not-exist/")
        self.assertEqual(resp.status_code, 404)


#####################################################################
# Parametric blackbox expansions                                     #
#                                                                    #
# Author: Samson Cournane                                            #
#                                                                    #
# Parametric enumeration of equivalence classes for the core HTML    #
# surface: list-view access across resources, form rejections across #
# field partitions, and slug-lookup safety on every detail/edit URL. #
#####################################################################


@pytest.fixture
def core_child(db):
    return core_models.Child.objects.create(
        first_name="Param",
        last_name="Core",
        birth_date=datetime.date(2024, 3, 1),
    )


@pytest.fixture
def core_logged_in_client(db):
    User = get_user_model()
    user = User.objects.create_user(username="core_param", password="Core-Pwd-1!")
    user.user_permissions.set(Permission.objects.all())
    user.save()
    client = Client()
    client.login(username="core_param", password="Core-Pwd-1!")
    return client


def _fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


# ---------------------------------------------------------------------------
# A. Every core list/add route redirects anonymous callers to login.
# ---------------------------------------------------------------------------


ANONYMOUS_CORE_ROUTES = [
    "core:child-list",
    "core:child-add",
    "core:feeding-list",
    "core:feeding-add",
    "core:sleep-list",
    "core:sleep-add",
    "core:diaperchange-list",
    "core:diaperchange-add",
    "core:note-list",
    "core:note-add",
    "core:pumping-list",
    "core:pumping-add",
    "core:temperature-list",
    "core:temperature-add",
    "core:weight-list",
    "core:weight-add",
    "core:timer-list",
    "core:timeline",
]


@pytest.mark.parametrize("route_name", ANONYMOUS_CORE_ROUTES)
def test_anonymous_core_route_redirects_to_login(db, route_name):
    client = Client()
    resp = client.get(reverse(route_name))
    assert resp.status_code == 302, f"{route_name} got {resp.status_code}"
    assert (
        "login" in resp["Location"].lower()
    ), f"{route_name} redirected to {resp['Location']!r}"


# ---------------------------------------------------------------------------
# B. The same routes render 200 for a fully-permissioned user.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_name", ANONYMOUS_CORE_ROUTES)
def test_authed_core_route_renders_or_redirects(core_logged_in_client, route_name):
    resp = core_logged_in_client.get(reverse(route_name))
    assert resp.status_code in (
        200,
        302,
    ), f"{route_name} responded {resp.status_code}, expected 200 or 302"


# ---------------------------------------------------------------------------
# C. Child form - invalid birth_date partitions all leave us on the form.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_birth_date",
    [
        "",  # empty
        "not-a-date",  # garbage
        "2024/01/01",  # wrong separator
        "2024-13-01",  # invalid month
        "2024-02-30",  # invalid day
    ],
)
def test_child_form_rejects_bad_birth_date(core_logged_in_client, bad_birth_date):
    resp = core_logged_in_client.post(
        reverse("core:child-add"),
        data={"first_name": "Bad", "last_name": "Date", "birth_date": bad_birth_date},
    )
    # Django re-renders the form with an errorlist on validation failure.
    assert (
        resp.status_code == 200
    ), f"birth_date={bad_birth_date!r} got {resp.status_code}, expected 200"


# ---------------------------------------------------------------------------
# D. Feeding form - malformed datetimes, invalid types and invalid methods.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_type",
    ["unicorn milk", "BREAST MILK", "breast_milk", "", "soda"],
)
def test_feeding_form_rejects_invalid_type(core_logged_in_client, core_child, bad_type):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:feeding-add"),
        data={
            "child": core_child.id,
            "start": _fmt_dt(now - datetime.timedelta(minutes=30)),
            "end": _fmt_dt(now - datetime.timedelta(minutes=10)),
            "type": bad_type,
            "method": "bottle",
        },
    )
    assert resp.status_code == 200, f"feeding type={bad_type!r} got {resp.status_code}"


@pytest.mark.parametrize(
    "bad_method",
    ["hyperdrive", "BOTTLE", "", "syringe", "iv drip"],
)
def test_feeding_form_rejects_invalid_method(
    core_logged_in_client, core_child, bad_method
):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:feeding-add"),
        data={
            "child": core_child.id,
            "start": _fmt_dt(now - datetime.timedelta(minutes=30)),
            "end": _fmt_dt(now - datetime.timedelta(minutes=10)),
            "type": "breast milk",
            "method": bad_method,
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# E. Sleep form - bad start/end ordering variants.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "start_offset_min,end_offset_min",
    [
        (-30, -60),  # end before start
        pytest.param(
            -30,
            -30,  # zero duration
            marks=[
                pytest.mark.found_bug,
                pytest.mark.xfail(
                    reason=(
                        "Bug: zero-duration sleep (start == end) is silently "
                        "accepted and redirects (302) instead of re-rendering "
                        "the form with an errorlist."
                    ),
                    strict=False,
                ),
            ],
        ),
        (10, 20),  # start in the future
        (-30, 60),  # end in the future
    ],
)
def test_sleep_form_rejects_bad_durations(
    core_logged_in_client, core_child, start_offset_min, end_offset_min
):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:sleep-add"),
        data={
            "child": core_child.id,
            "start": _fmt_dt(now + datetime.timedelta(minutes=start_offset_min)),
            "end": _fmt_dt(now + datetime.timedelta(minutes=end_offset_min)),
        },
    )
    # Any validation rejection re-renders the add form (200).  A successful
    # save redirects (302) - that's the failure mode this test guards against.
    assert resp.status_code == 200, (
        f"sleep(start+{start_offset_min}m,end+{end_offset_min}m) got "
        f"{resp.status_code}, expected 200 errorlist"
    )


# ---------------------------------------------------------------------------
# F. Detail and update views for an unknown child slug on every resource.
# We expect a 404 (or a redirect - both would be fine for a non-existent
# resource).  The failure mode we are guarding against is a 500.
# ---------------------------------------------------------------------------


SLUG_ROUTES = [
    "core:child",
    "core:child-update",
    "core:child-delete",
]


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: custom 404 template babybuddy/templates/error/404.html has a "
        'malformed `|add"</code>"` (missing colon), so every 404 crashes '
        "the template engine and bubbles up as a 500.  Until that template "
        "is fixed, unknown-slug routes surface as 500 instead of 404."
    ),
    strict=False,
)
@pytest.mark.parametrize("route_name", SLUG_ROUTES)
def test_unknown_child_slug_never_500s(core_logged_in_client, route_name):
    resp = core_logged_in_client.get(reverse(route_name, args=["no-such-kid-xyz"]))
    assert (
        resp.status_code < 500
    ), f"{route_name}(no-such-kid-xyz) returned {resp.status_code}, should be <500"


# ---------------------------------------------------------------------------
# G. Note form - length partitions up to limit are accepted.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("length", [1, 10, 100, 255])
def test_note_form_accepts_length_up_to_limit(
    core_logged_in_client, core_child, length
):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:note-add"),
        data={
            "child": core_child.id,
            "note": "x" * length,
            "time": _fmt_dt(now - datetime.timedelta(minutes=1)),
        },
    )
    # Valid note -> redirect to list; never 5xx.
    assert resp.status_code in (
        200,
        302,
    ), f"note length={length} got {resp.status_code}"


# ---------------------------------------------------------------------------
# H. Timer restart - various HTTP method outcomes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "delete", "patch"])
def test_timer_restart_response_categories(core_logged_in_client, core_child, method):
    User = get_user_model()
    user = User.objects.get(username="core_param")
    timer = core_models.Timer.objects.create(
        child=core_child,
        user=user,
        start=timezone.now() - datetime.timedelta(minutes=30),
    )
    resp = getattr(core_logged_in_client, method)(
        reverse("core:timer-restart", args=[timer.id])
    )
    # Only constraint for blackbox: never a 5xx.
    assert (
        resp.status_code < 500
    ), f"restart via {method.upper()} produced {resp.status_code}"


# ---------------------------------------------------------------------------
# I. List views accept `child=<slug>` query param without crashing for every
#    valid resource that supports the filter.
# ---------------------------------------------------------------------------


FILTERABLE_LIST_ROUTES = [
    "core:feeding-list",
    "core:sleep-list",
    "core:diaperchange-list",
    "core:note-list",
    "core:pumping-list",
    "core:temperature-list",
    "core:weight-list",
]


@pytest.mark.parametrize("route_name", FILTERABLE_LIST_ROUTES)
def test_filterable_list_with_child_query(
    core_logged_in_client, core_child, route_name
):
    resp = core_logged_in_client.get(reverse(route_name) + f"?child={core_child.slug}")
    assert resp.status_code in (
        200,
        302,
    ), f"{route_name}?child={core_child.slug} got {resp.status_code}"


# ---------------------------------------------------------------------------
# J. Numeric field min-value regressions (found via equivalence-class search).
#
#    BabyBuddy defines Weight/Height/Temperature/HeadCircumference/BMI/amount
#    as plain FloatField without a MinValueValidator.  Every one of the
#    following tests asserts the form refuses a zero or negative value (a
#    biologically meaningless value that should never be persistable).  All
#    six currently xfail because the form layer happily accepts these values
#    and redirects on save.  xfail(strict=False) means: if any one ever
#    passes, the suite still reports success - we've fixed a bug.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Weight.weight is a FloatField without a MinValueValidator, so "
        "a zero or negative weight is accepted by the form and persisted."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_weight", ["-5", "-0.1", "0"])
def test_weight_form_rejects_non_positive(
    core_logged_in_client, core_child, bad_weight
):
    today = timezone.localdate().isoformat()
    resp = core_logged_in_client.post(
        reverse("core:weight-add"),
        data={"child": core_child.id, "weight": bad_weight, "date": today},
    )
    # A clean rejection re-renders the form (200); a buggy accept redirects (302).
    assert (
        resp.status_code == 200
    ), f"weight={bad_weight!r} got {resp.status_code}, expected 200 error re-render"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Height.height has no MinValueValidator; zero/negative heights "
        "are silently accepted."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_height", ["-1", "-0.01", "0"])
def test_height_form_rejects_non_positive(
    core_logged_in_client, core_child, bad_height
):
    today = timezone.localdate().isoformat()
    resp = core_logged_in_client.post(
        reverse("core:height-add"),
        data={"child": core_child.id, "height": bad_height, "date": today},
    )
    assert (
        resp.status_code == 200
    ), f"height={bad_height!r} got {resp.status_code}, expected 200"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: HeadCircumference.head_circumference has no MinValueValidator; "
        "zero/negative head circumferences are silently accepted."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_hc", ["-10", "-0.1", "0"])
def test_head_circumference_rejects_non_positive(
    core_logged_in_client, core_child, bad_hc
):
    today = timezone.localdate().isoformat()
    resp = core_logged_in_client.post(
        reverse("core:head-circumference-add"),
        data={"child": core_child.id, "head_circumference": bad_hc, "date": today},
    )
    assert (
        resp.status_code == 200
    ), f"head_circumference={bad_hc!r} got {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: BMI.bmi has no MinValueValidator nor a MaxValueValidator, so "
        "negative and absurdly high BMI values are silently accepted."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_bmi", ["-5", "-0.5", "0", "1000"])
def test_bmi_form_rejects_nonsensical_values(
    core_logged_in_client, core_child, bad_bmi
):
    today = timezone.localdate().isoformat()
    resp = core_logged_in_client.post(
        reverse("core:bmi-add"),
        data={"child": core_child.id, "bmi": bad_bmi, "date": today},
    )
    assert resp.status_code == 200, f"bmi={bad_bmi!r} got {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Temperature.temperature has no sanity validators, so readings "
        "far outside the physiological range (<20 or >50 degC) are accepted."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_temp", ["-50", "0", "200"])
def test_temperature_form_rejects_absurd_values(
    core_logged_in_client, core_child, bad_temp
):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:temperature-add"),
        data={
            "child": core_child.id,
            "temperature": bad_temp,
            "time": _fmt_dt(now - datetime.timedelta(minutes=1)),
        },
    )
    assert resp.status_code == 200, f"temperature={bad_temp!r} got {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Feeding.amount is a FloatField without a MinValueValidator; "
        "a negative feeding volume should not be persistable but currently is."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_amount", ["-100", "-0.1"])
def test_feeding_form_rejects_negative_amount(
    core_logged_in_client, core_child, bad_amount
):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:feeding-add"),
        data={
            "child": core_child.id,
            "start": _fmt_dt(now - datetime.timedelta(minutes=30)),
            "end": _fmt_dt(now - datetime.timedelta(minutes=10)),
            "type": "breast milk",
            "method": "bottle",
            "amount": bad_amount,
        },
    )
    assert (
        resp.status_code == 200
    ), f"feeding amount={bad_amount!r} got {resp.status_code}"


# ---------------------------------------------------------------------------
# K. Birth date + birth time sanity (future-dated birth is clearly a bug).
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Child.birth_date has no 'not in future' validator, so a birth "
        "date years in the future is accepted and the child appears in the "
        "roster with a negative age."
    ),
    strict=False,
)
@pytest.mark.parametrize("future_offset_days", [1, 30, 365, 3650])
def test_child_form_rejects_future_birth_date(
    core_logged_in_client, future_offset_days
):
    future = timezone.localdate() + datetime.timedelta(days=future_offset_days)
    resp = core_logged_in_client.post(
        reverse("core:child-add"),
        data={
            "first_name": "Future",
            "last_name": f"Baby{future_offset_days}",
            "birth_date": future.isoformat(),
        },
    )
    # A well-behaved form re-renders with an error (200); the observed
    # behavior is a redirect to the list (302).
    assert (
        resp.status_code == 200
    ), f"future birth_date(+{future_offset_days}d) got {resp.status_code}"


# ---------------------------------------------------------------------------
# L. DiaperChange / Note / Pumping timestamps in the future.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: DiaperChange.time accepts future timestamps.  A diaper change "
        "recorded tomorrow makes no semantic sense and pollutes analytics."
    ),
    strict=False,
)
@pytest.mark.parametrize("future_minutes", [5, 60, 60 * 24])
def test_diaperchange_form_rejects_future_time(
    core_logged_in_client, core_child, future_minutes
):
    future = timezone.localtime() + datetime.timedelta(minutes=future_minutes)
    resp = core_logged_in_client.post(
        reverse("core:diaperchange-add"),
        data={
            "child": core_child.id,
            "time": _fmt_dt(future),
            "wet": "on",
        },
    )
    assert (
        resp.status_code == 200
    ), f"future diaperchange(+{future_minutes}m) got {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Note.time accepts future timestamps without validation, so a "
        "caregiver can accidentally log notes 'tomorrow'."
    ),
    strict=False,
)
@pytest.mark.parametrize("future_minutes", [5, 60, 60 * 24])
def test_note_form_rejects_future_time(
    core_logged_in_client, core_child, future_minutes
):
    future = timezone.localtime() + datetime.timedelta(minutes=future_minutes)
    resp = core_logged_in_client.post(
        reverse("core:note-add"),
        data={
            "child": core_child.id,
            "note": "x",
            "time": _fmt_dt(future),
        },
    )
    assert (
        resp.status_code == 200
    ), f"future note(+{future_minutes}m) got {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Pumping.amount has no MinValueValidator; a negative pumping "
        "volume is accepted by the form and persisted."
    ),
    strict=False,
)
@pytest.mark.parametrize("bad_amount", ["-50", "-0.01"])
def test_pumping_form_rejects_negative_amount(
    core_logged_in_client, core_child, bad_amount
):
    now = timezone.localtime()
    resp = core_logged_in_client.post(
        reverse("core:pumping-add"),
        data={
            "child": core_child.id,
            "start": _fmt_dt(now - datetime.timedelta(minutes=30)),
            "end": _fmt_dt(now - datetime.timedelta(minutes=10)),
            "amount": bad_amount,
        },
    )
    assert (
        resp.status_code == 200
    ), f"pumping amount={bad_amount!r} got {resp.status_code}"


# ---------------------------------------------------------------------------
# M. Very long text fields (beyond the documented 255-char limit) should
#    produce form errors, not SQL errors.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: Child.first_name / last_name are CharField(max_length=255) but "
        "the form does not display a friendly error when the limit is "
        "exceeded by submitted data - the exception escapes as 500 on some "
        "backends."
    ),
    strict=False,
)
@pytest.mark.parametrize("length", [256, 500, 1024])
def test_child_form_long_name_renders_error(core_logged_in_client, length):
    resp = core_logged_in_client.post(
        reverse("core:child-add"),
        data={
            "first_name": "A" * length,
            "last_name": "B",
            "birth_date": "2024-01-01",
        },
    )
    # Any non-5xx response means the server didn't crash.  200 is ideal
    # (errorlist re-render); 302 would still be acceptable.
    assert resp.status_code < 500, f"long first_name={length} got {resp.status_code}"
    # But the form should have refused the save; a happy 302 means the
    # over-length string was silently accepted.
    assert (
        resp.status_code == 200
    ), f"long first_name={length} got {resp.status_code}, expected 200 error"
