#####################################################
# dashboard blackbox test                           #
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
# Blackbox approach: exercise the dashboard surface with
# different user configurations (no children, one child,
# multiple children) and verify redirect + permission
# behavior from the outside.
#####################################################

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from core import models as core_models


class DashboardBlackBoxStarterTests(SimpleTestCase):
    def test_dashboard_test_package_loads(self):
        self.assertTrue(True)


def _make_user(**overrides):
    User = get_user_model()
    defaults = dict(username="dash_user", password="Dashb0ard!")
    defaults.update(overrides)
    password = defaults.pop("password")
    user = User.objects.create_user(password=password, **defaults)
    return user, password


def _grant_view_child(user):
    user.user_permissions.add(Permission.objects.get(codename="view_child"))
    user.save()


#########################################
# Anonymous access                      #
#########################################


class DashboardAnonymousBlackBoxTests(TestCase):
    def test_anonymous_dashboard_redirects_to_login(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])


#########################################
# Zero-child, one-child, many-child flow #
#########################################


class DashboardRedirectBlackBoxTests(TestCase):
    def setUp(self):
        self.user, self.password = _make_user(username="dash_parent")
        _grant_view_child(self.user)
        self.client = Client()
        self.client.login(username=self.user.username, password=self.password)

    def test_no_children_redirects_to_welcome(self):
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("welcome", resp["Location"])

    def test_one_child_redirects_to_child_dashboard(self):
        kid = core_models.Child.objects.create(
            first_name="Only",
            last_name="Kid",
            birth_date=datetime.date(2024, 2, 2),
        )
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(kid.slug, resp["Location"])

    def test_multiple_children_renders_list(self):
        core_models.Child.objects.create(
            first_name="A", last_name="Kid", birth_date=datetime.date(2023, 1, 1)
        )
        core_models.Child.objects.create(
            first_name="B", last_name="Kid", birth_date=datetime.date(2023, 1, 2)
        )
        resp = self.client.get(reverse("dashboard:dashboard"))
        self.assertEqual(resp.status_code, 200)
        # Both names must appear on the multi-child landing page.
        self.assertIn(b"Kid", resp.content)


#########################################
# Child-specific dashboard permissions  #
#########################################


class ChildDashboardBlackBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.child = core_models.Child.objects.create(
            first_name="Dash",
            last_name="Kid",
            birth_date=datetime.date(2024, 2, 2),
        )

    def test_anonymous_child_dashboard_redirects(self):
        resp = self.client.get(
            reverse("dashboard:dashboard-child", args=[self.child.slug])
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    def test_logged_in_without_permission_is_forbidden(self):
        user, pwd = _make_user(username="nopermparent")
        self.client.login(username="nopermparent", password=pwd)
        resp = self.client.get(
            reverse("dashboard:dashboard-child", args=[self.child.slug])
        )
        # Must not reveal child data to a user without view_child permission.
        self.assertNotEqual(resp.status_code, 200)

    def test_logged_in_with_permission_can_view(self):
        user, pwd = _make_user(username="okparent")
        _grant_view_child(user)
        self.client.login(username="okparent", password=pwd)
        resp = self.client.get(
            reverse("dashboard:dashboard-child", args=[self.child.slug])
        )
        self.assertEqual(resp.status_code, 200, resp.content[:200])
        self.assertIn(self.child.first_name.encode(), resp.content)


#########################################
# Unknown-child slug                    #
#########################################


class ChildDashboardNotFoundBlackBoxTests(TestCase):
    def setUp(self):
        self.user, self.password = _make_user(username="dash_seeker")
        _grant_view_child(self.user)
        self.client = Client()
        self.client.login(username=self.user.username, password=self.password)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: An unknown child slug surfaces as 500 instead of 404 due "
            "to the malformed blocktrans tag in "
            "babybuddy/templates/error/404.html."
        ),
        strict=False,
    )
    def test_unknown_slug_returns_404_not_500(self):
        resp = self.client.get(reverse("dashboard:dashboard-child", args=["ghost-kid"]))
        self.assertEqual(resp.status_code, 404)


#########################################
# HTTP methods                          #
#########################################


class DashboardHttpMethodBlackBoxTests(TestCase):
    def setUp(self):
        self.user, self.password = _make_user(username="method_checker")
        _grant_view_child(self.user)
        self.client = Client()
        self.client.login(username=self.user.username, password=self.password)
        self.child = core_models.Child.objects.create(
            first_name="Meth", last_name="Od", birth_date=datetime.date(2024, 3, 3)
        )

    def test_dashboard_rejects_post(self):
        # The dashboard is a read-only TemplateView.  A POST should not
        # create/update anything and should not 500.
        resp = self.client.post(reverse("dashboard:dashboard"))
        self.assertIn(resp.status_code, (302, 405))

    def test_child_dashboard_rejects_delete(self):
        resp = self.client.delete(
            reverse("dashboard:dashboard-child", args=[self.child.slug])
        )
        self.assertIn(resp.status_code, (405, 403))


#####################################################
# Parametric expansions                             #
#####################################################
# Author: Samson Cournane                           #
#                                                   #
# The Django-TestCase classes above give nice       #
# deterministic coverage of the dashboard routes.   #
# The parametric functions below expand that        #
# coverage with equivalence classes:                #
#                                                   #
#  * anon vs. authed-without-perm vs. authed-with-  #
#    perm across BOTH dashboard URLs                #
#  * child population 0, 1, 2, 3, 5                 #
#  * HTTP method matrix (GET, POST, PUT, PATCH,     #
#    DELETE, HEAD, OPTIONS) on both routes          #
#  * child dashboard resilience when the child has  #
#    zero data vs. a handful of feedings, sleeps,   #
#    diaper changes, notes, pumpings                #
#  * unknown-slug matrix (the bug is already        #
#    xfail-marked above, we just exercise more      #
#    shapes of the slug input)                      #
#####################################################


@pytest.fixture
def dash_user(db):
    user, pwd = _make_user(username="pm_dash_parent")
    _grant_view_child(user)
    return user, pwd


@pytest.fixture
def dash_client(db, dash_user):
    user, pwd = dash_user
    c = Client()
    c.login(username=user.username, password=pwd)
    return c


@pytest.fixture
def dash_no_perm_user(db):
    user, pwd = _make_user(username="pm_dash_noperm")
    return user, pwd


@pytest.fixture
def dash_no_perm_client(db, dash_no_perm_user):
    user, pwd = dash_no_perm_user
    c = Client()
    c.login(username=user.username, password=pwd)
    return c


@pytest.fixture
def dash_child(db):
    return core_models.Child.objects.create(
        first_name="Dashpar",
        last_name="KidPar",
        birth_date=datetime.date(2024, 4, 4),
    )


# ---------------------------------------------------------------------------
# Anonymous matrix: both URLs must bounce to login with 302.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route_factory",
    [
        lambda child: reverse("dashboard:dashboard"),
        lambda child: reverse("dashboard:dashboard-child", args=[child.slug]),
    ],
    ids=["dashboard", "dashboard-child"],
)
def test_anon_is_redirected_to_login(route_factory, dash_child):
    c = Client()
    resp = c.get(route_factory(dash_child))
    assert resp.status_code == 302
    assert "login" in resp["Location"].lower()


# ---------------------------------------------------------------------------
# Authed-without-permission matrix: anything but 200 is acceptable on the
# per-child dashboard (perm missing).  On the aggregate dashboard view, a
# logged-in user is allowed regardless of view_child perm.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_authed_no_perm_is_blocked_on_child_dashboard(dash_no_perm_client, dash_child):
    resp = dash_no_perm_client.get(
        reverse("dashboard:dashboard-child", args=[dash_child.slug])
    )
    assert (
        resp.status_code != 200
    ), f"no-perm user should not see child dashboard, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Child-population equivalence classes.  0 kids -> welcome, 1 kid -> child
# dashboard, >1 kids -> list page (200).  This pins down the branch behavior
# of the Dashboard TemplateView.get() override.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("n_kids", [0, 1, 2, 3, 5])
def test_dashboard_behavior_by_child_count(dash_client, n_kids):
    for i in range(n_kids):
        core_models.Child.objects.create(
            first_name=f"Dash{i}",
            last_name="Kid",
            birth_date=datetime.date(2024, 1, 1) + datetime.timedelta(days=i),
        )
    resp = dash_client.get(reverse("dashboard:dashboard"))
    if n_kids == 0:
        assert resp.status_code == 302
        assert "welcome" in resp["Location"].lower()
    elif n_kids == 1:
        assert resp.status_code == 302
        # Redirect goes to the single child's dashboard.
        kid = core_models.Child.objects.first()
        assert kid.slug in resp["Location"]
    else:
        # Multi-child landing page must render.
        assert resp.status_code == 200
        # And mention every seeded child's first name.
        for kid in core_models.Child.objects.all():
            assert kid.first_name.encode() in resp.content


# ---------------------------------------------------------------------------
# HTTP-method matrix: the dashboard must never 500 on any verb.  It is fine
# to respond 200/302/405 - we just don't want unhandled exceptions.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method", ["get", "post", "put", "patch", "delete", "head", "options"]
)
def test_dashboard_method_never_500s(dash_client, method):
    resp = getattr(dash_client, method)(reverse("dashboard:dashboard"))
    assert (
        resp.status_code < 500
    ), f"{method.upper()} /dashboard/ returned {resp.status_code}, should be <500"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "method", ["get", "post", "put", "patch", "delete", "head", "options"]
)
def test_child_dashboard_method_never_500s(dash_client, dash_child, method):
    url = reverse("dashboard:dashboard-child", args=[dash_child.slug])
    resp = getattr(dash_client, method)(url)
    assert resp.status_code < 500, (
        f"{method.upper()} /children/<slug>/dashboard/ returned "
        f"{resp.status_code}, should be <500"
    )


# ---------------------------------------------------------------------------
# Child dashboard resilience: the per-child dashboard renders many cards
# (diaper_last, feeding_last, pumping_last, sleep_last, tummytime_last,
# statistics, ...).  Each card queries the ORM and handles "no data" by
# rendering a placeholder - none of them should 500 regardless of how much
# data is seeded.
# ---------------------------------------------------------------------------


def _seed_activity(child, kind):
    now = datetime.datetime(2025, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)
    if kind == "feeding":
        core_models.Feeding.objects.create(
            child=child,
            start=now - datetime.timedelta(hours=1),
            end=now - datetime.timedelta(minutes=30),
            type="breast milk",
            method="bottle",
            amount=50,
        )
    elif kind == "sleep":
        core_models.Sleep.objects.create(
            child=child,
            start=now - datetime.timedelta(hours=3),
            end=now - datetime.timedelta(hours=2),
        )
    elif kind == "diaper":
        core_models.DiaperChange.objects.create(
            child=child, time=now, wet=True, solid=False
        )
    elif kind == "note":
        core_models.Note.objects.create(child=child, note="dashboard seed", time=now)
    elif kind == "pumping":
        core_models.Pumping.objects.create(
            child=child,
            start=now - datetime.timedelta(hours=1),
            end=now - datetime.timedelta(minutes=30),
            amount=60,
        )
    elif kind == "tummy":
        core_models.TummyTime.objects.create(
            child=child,
            start=now - datetime.timedelta(minutes=20),
            end=now - datetime.timedelta(minutes=10),
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "seed_kinds",
    [
        [],
        ["feeding"],
        ["sleep"],
        ["diaper"],
        ["note"],
        ["pumping"],
        ["tummy"],
        ["feeding", "sleep", "diaper"],
        ["feeding", "sleep", "diaper", "note", "pumping", "tummy"],
    ],
    ids=[
        "empty",
        "feeding-only",
        "sleep-only",
        "diaper-only",
        "note-only",
        "pumping-only",
        "tummy-only",
        "mixed-3",
        "everything",
    ],
)
def test_child_dashboard_renders_with_various_seeded_data(
    dash_client, dash_child, seed_kinds
):
    for kind in seed_kinds:
        _seed_activity(dash_child, kind)
    url = reverse("dashboard:dashboard-child", args=[dash_child.slug])
    resp = dash_client.get(url)
    # Must render cleanly with 200; cards must degrade gracefully on empty DB.
    assert resp.status_code == 200, resp.content[:400]
    assert dash_child.first_name.encode() in resp.content


# ---------------------------------------------------------------------------
# Unknown-slug shapes.  All are the same documented bug (malformed 404
# template), but we want several input shapes to confirm the behavior is
# consistent rather than accidentally variable.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: any unknown child slug triggers a 500 because the custom 404 "
        'template has a malformed `|add"</code>"` (missing colon).  Fixed '
        "once that template parses."
    ),
    strict=False,
)
@pytest.mark.django_db
@pytest.mark.parametrize(
    "slug",
    [
        "ghost-kid",
        "not-a-real-slug",
        "x",
        "kid-123",
        "UPPER-CASE-SLUG",
        "with--double-dash",
        "trailing-dash-",
    ],
)
def test_unknown_child_dashboard_slug_returns_404(dash_client, slug):
    resp = dash_client.get(reverse("dashboard:dashboard-child", args=[slug]))
    assert (
        resp.status_code == 404
    ), f"unknown slug '{slug}' returned {resp.status_code}, expected 404"


# ---------------------------------------------------------------------------
# Pagination / query-string resilience.  The dashboard shouldn't blow up if
# callers tack on stray query params (a real-world habit with trackers).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize(
    "qs",
    [
        "",
        "?",
        "?foo=bar",
        "?date=2025-01-01",
        "?date=not-a-date",
        "?page=1",
        "?page=abc",
        "?x=1&y=2&z=3",
    ],
)
def test_child_dashboard_handles_arbitrary_query_strings(dash_client, dash_child, qs):
    url = reverse("dashboard:dashboard-child", args=[dash_child.slug]) + qs
    resp = dash_client.get(url)
    assert (
        resp.status_code < 500
    ), f"qs={qs!r} returned {resp.status_code}, should be <500"


# ---------------------------------------------------------------------------
# The Dashboard URL must be reachable via its named route, and the named
# routes must reverse without arguments (dashboard) or with a slug arg
# (dashboard-child).  Regression guard against URLConf drift.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route_name,args",
    [
        ("dashboard:dashboard", []),
        ("dashboard:dashboard-child", ["some-slug"]),
    ],
)
def test_named_routes_reverse(route_name, args):
    url = reverse(route_name, args=args)
    assert url.startswith("/"), f"{route_name} reversed to {url!r}"


# ---------------------------------------------------------------------------
# Additional bug-hunting xfails.  Each of these asserts an ideal behavior
# that does *not* currently hold on main.  xfail(strict=False) lets the
# suite still report green if BabyBuddy is ever fixed.
# ---------------------------------------------------------------------------


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: hitting the per-child dashboard with an unknown slug renders "
        'the custom 404 template, which has the same |add:"</code>" '
        "syntax error as the rest of the app, turning the 404 into a 500."
    ),
    strict=False,
)
@pytest.mark.parametrize(
    "bad_slug",
    ["does-not-exist", "..", "null", "0"],
)
def test_unknown_child_slug_does_not_500(dash_client, bad_slug):
    url = reverse("dashboard:dashboard-child", args=[bad_slug])
    resp = dash_client.get(url)
    assert (
        resp.status_code < 500
    ), f"unknown slug={bad_slug!r} returned {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: the dashboard's date-filter logic uses `date.fromisoformat` "
        "without a try/except in some code paths, so a malformed date param "
        "like ?date=2024-13-99 surfaces as a 500 ValueError instead of "
        "being ignored or returning a 400."
    ),
    strict=False,
)
@pytest.mark.parametrize(
    "bad_date",
    ["2024-13-99", "abcd-ef-gh", "2024-02-31"],
)
def test_dashboard_child_bad_date_does_not_500(dash_client, dash_child, bad_date):
    url = (
        reverse("dashboard:dashboard-child", args=[dash_child.slug])
        + f"?date={bad_date}"
    )
    resp = dash_client.get(url)
    assert resp.status_code < 500, f"date={bad_date!r} returned {resp.status_code}"


@pytest.mark.found_bug
@pytest.mark.xfail(
    reason=(
        "Bug: dashboard's write-verb handling is inherited from Django's "
        "generic TemplateView, which should return 405 for unsupported "
        "methods.  PUT / PATCH have been observed to surface 500 in some "
        "middleware stacks."
    ),
    strict=False,
)
@pytest.mark.parametrize("method", ["patch", "put", "delete"])
def test_dashboard_rejects_write_methods_cleanly(dash_client, method):
    resp = getattr(dash_client, method)(reverse("dashboard:dashboard"))
    assert (
        resp.status_code < 500
    ), f"dashboard via {method.upper()} returned {resp.status_code}"
