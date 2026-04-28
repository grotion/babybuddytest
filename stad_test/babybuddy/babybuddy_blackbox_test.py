#####################################################
# babybuddy blackbox test                           #
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
# Blackbox approach: exercise the authentication + settings
# surface through the ordinary HTTP client with no knowledge of
# internal controllers, looking for 500s, information leaks and
# unexpected responses.
#####################################################

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token


class BabyBuddyBlackBoxSmokeTests(SimpleTestCase):
    def test_api_profile_route_is_named(self):
        url = reverse("api:profile")
        self.assertTrue(url.endswith("/api/profile"))


#############################################
# Login / Logout / Password reset           #
#############################################


class LoginViewBlackBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="caregiver", password="Wr4pUpW@rmly"
        )

    def test_login_page_renders(self):
        resp = self.client.get(reverse("babybuddy:login"))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"username", resp.content.lower())

    def test_login_with_valid_credentials(self):
        resp = self.client.post(
            reverse("babybuddy:login"),
            data={"username": "caregiver", "password": "Wr4pUpW@rmly"},
        )
        # Successful login redirects to LOGIN_REDIRECT_URL.
        self.assertEqual(resp.status_code, 302)

    def test_login_with_wrong_password_stays_on_form(self):
        resp = self.client.post(
            reverse("babybuddy:login"),
            data={"username": "caregiver", "password": "NotMyPassword"},
        )
        self.assertEqual(resp.status_code, 200)
        # The form should re-render with an error - do not redirect.

    def test_login_with_unknown_user_does_not_leak(self):
        # Security: wrong-user and wrong-password should look identical.
        wrong_user = self.client.post(
            reverse("babybuddy:login"),
            data={"username": "ghost", "password": "nope"},
        )
        wrong_pw = self.client.post(
            reverse("babybuddy:login"),
            data={"username": "caregiver", "password": "nope"},
        )
        self.assertEqual(wrong_user.status_code, wrong_pw.status_code)

    def test_logout_redirects(self):
        self.client.login(username="caregiver", password="Wr4pUpW@rmly")
        resp = self.client.post(reverse("babybuddy:logout"))
        # Django LogoutView typically returns 302 to LOGOUT_REDIRECT_URL.
        self.assertIn(resp.status_code, (200, 302))

    def test_password_reset_page_renders(self):
        resp = self.client.get(reverse("babybuddy:password_reset"))
        self.assertEqual(resp.status_code, 200)


#############################################
# Root router & welcome                     #
#############################################


class RootRouterBlackBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="carer", password="Rhumba-32!", is_staff=True, is_superuser=True
        )

    def test_anonymous_at_root_is_redirected_to_login(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    def test_authenticated_root_redirects_to_dashboard(self):
        # Black-box contract: logged-in users visiting "/" should land on
        # the dashboard.  This also indirectly exercises RootRouter which
        # has a suspicious `super().get_redirect_url(self, ...)` call.
        self.client.login(username="carer", password="Rhumba-32!")
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("dashboard", resp["Location"])


#############################################
# API Profile endpoint                      #
#############################################


class ProfileEndpointBlackBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.regular = User.objects.create_user(
            username="profilegal", password="Boop!-99", is_staff=True
        )
        cls.regular_token = Token.objects.create(user=cls.regular)

        cls.admin = User.objects.create_user(
            username="profileadmin",
            password="Admin-99!",
            is_staff=True,
            is_superuser=True,
        )
        cls.admin_token = Token.objects.create(user=cls.admin)

    def test_profile_requires_authentication(self):
        resp = self.client.get(reverse("api:profile"))
        self.assertIn(resp.status_code, (401, 403))

    def test_profile_returns_user_info_for_superuser(self):
        resp = self.client.get(
            reverse("api:profile"),
            HTTP_AUTHORIZATION=f"Token {self.admin_token.key}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertEqual(body["user"]["username"], "profileadmin")
        self.assertIn("api_key", body)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: /api/profile is guarded by BabyBuddyDjangoModelPermissions, "
            "which requires the `view_settings` model permission.  A regular "
            "authenticated user therefore cannot read their own profile "
            "(HTTP 403) even though the view is intended to return the "
            "caller's own user settings."
        ),
        strict=False,
    )
    def test_profile_returns_user_info_for_regular_user(self):
        resp = self.client.get(
            reverse("api:profile"),
            HTTP_AUTHORIZATION=f"Token {self.regular_token.key}",
        )
        self.assertEqual(resp.status_code, 200, resp.content)


#############################################
# User settings / password change           #
#############################################


class UserSettingsBlackBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="settings_user", password="S3ttings_OK"
        )

    def test_settings_page_requires_login(self):
        resp = self.client.get(reverse("babybuddy:user-settings"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("login", resp["Location"])

    def test_settings_page_renders_for_logged_in_user(self):
        self.client.login(username="settings_user", password="S3ttings_OK")
        resp = self.client.get(reverse("babybuddy:user-settings"))
        self.assertEqual(resp.status_code, 200)


#############################################
# Admin-only pages                          #
#############################################


class StaffOnlyBlackBoxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.normal = User.objects.create_user(
            username="regular", password="RegularPwd1!", is_staff=False
        )
        cls.admin = User.objects.create_user(
            username="bossmom",
            password="Bosssy-99",
            is_staff=True,
            is_superuser=True,
        )

    def test_normal_user_cannot_list_users(self):
        self.client.login(username="regular", password="RegularPwd1!")
        resp = self.client.get(reverse("babybuddy:user-list"))
        # Must not return 200 with user data to a non-staff user.
        self.assertNotEqual(resp.status_code, 200)

    def test_admin_can_list_users(self):
        self.client.login(username="bossmom", password="Bosssy-99")
        resp = self.client.get(reverse("babybuddy:user-list"))
        self.assertEqual(resp.status_code, 200)


#############################################
# Custom 404 / 500 HTML response            #
#############################################


class CustomErrorTemplateBlackBoxTests(TestCase):
    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Unknown URLs cause a TemplateSyntaxError in "
            "babybuddy/templates/error/404.html (the `blocktrans trimmed "
            'with path=...|add"</code>"|safe` line is missing a colon '
            "after the second `add` filter).  Because the 404 handler "
            "tries to render this broken template, the real HTTP status "
            "a visitor sees is a 500 instead of a 404."
        ),
        strict=False,
    )
    def test_unknown_page_returns_clean_404(self):
        resp = self.client.get("/this/path/really/does/not/exist/")
        self.assertEqual(resp.status_code, 404)


#############################################
# Locale / i18n endpoint                    #
#############################################


class LocaleBlackBoxTests(TestCase):
    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Related to the 404-template bug: a GET on the i18n language "
            "endpoint path that does not exist triggers the broken 404 "
            "template and surfaces as a 500."
        ),
        strict=False,
    )
    def test_set_language_get_does_not_500(self):
        # Django's default set_language is POST-only; a GET shouldn't 500.
        resp = self.client.get("/user/lang/setlang/")
        self.assertIn(resp.status_code, (302, 405, 404))


#####################################################################
# Parametric blackbox expansions                                     #
#                                                                    #
# Author: Samson Cournane                                            #
#                                                                    #
# The class-based tests above prove a representative case for each   #
# rule.  The pytest-style functions below use parametrize to drive   #
# the same rules across whole equivalence classes: multiple invalid  #
# credentials, multiple gated pages, multiple HTTP methods, etc.     #
#####################################################################


@pytest.fixture
def regular_user(db):
    User = get_user_model()
    user = User.objects.create_user(username="pm_regular", password="Regular-Pwd-1!")
    return user


@pytest.fixture
def staff_user(db):
    User = get_user_model()
    user = User.objects.create_user(
        username="pm_staff",
        password="Staff-Pwd-1!",
        is_staff=True,
        is_superuser=True,
    )
    return user


# ---------------------------------------------------------------------------
# A. Login form rejects a matrix of bad credentials with the same visible
#    outcome (200 re-render, never a redirect or a 500).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "username,password",
    [
        ("pm_regular", ""),  # empty password
        ("", "Regular-Pwd-1!"),  # empty username
        ("", ""),  # both empty
        ("pm_regular", "wrong"),  # wrong password
        ("ghost", "anything"),  # unknown user
        ("PM_REGULAR", "Regular-Pwd-1!"),  # wrong case username
        ("pm_regular", "Regular-Pwd-1! "),  # trailing space on pw
        ("pm_regular", " Regular-Pwd-1!"),  # leading space on pw
    ],
)
def test_login_rejects_bad_credentials(regular_user, username, password):
    client = Client()
    resp = client.post(
        reverse("babybuddy:login"),
        data={"username": username, "password": password},
    )
    # A failed login must re-render the form (200), never 302 redirect to
    # the authenticated area and never 5xx.
    assert resp.status_code == 200, (
        f"login with {username!r}/{password!r} returned {resp.status_code}, "
        "expected 200 form-rerender"
    )


# ---------------------------------------------------------------------------
# B. Anonymous GET on login-gated pages redirects to login with a next= param.
# ---------------------------------------------------------------------------


GATED_PAGE_ROUTES = [
    "babybuddy:user-settings",
    "babybuddy:user-list",
    "core:child-list",
    "core:child-add",
    "core:feeding-list",
    "core:feeding-add",
    "core:sleep-list",
    "core:sleep-add",
    "core:diaperchange-list",
    "core:pumping-list",
    "core:note-list",
    "core:timer-list",
]


@pytest.mark.parametrize("route_name", GATED_PAGE_ROUTES)
def test_anonymous_gated_page_redirects_to_login(db, route_name):
    client = Client()
    resp = client.get(reverse(route_name))
    assert (
        resp.status_code == 302
    ), f"{route_name} should redirect for anon, got {resp.status_code}"
    assert (
        "login" in resp["Location"].lower()
    ), f"{route_name} redirected to {resp['Location']!r}, expected a login URL"


# ---------------------------------------------------------------------------
# C. Every gated page renders 200 for a staff user.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_name", GATED_PAGE_ROUTES)
def test_staff_can_render_gated_page(staff_user, route_name):
    client = Client()
    client.login(username="pm_staff", password="Staff-Pwd-1!")
    resp = client.get(reverse(route_name))
    # 200 if the page exists for this resource, or 302 onto a default child
    # filter - both acceptable; the failure mode we are guarding against is
    # a 403 or a 500.
    assert resp.status_code in (
        200,
        302,
    ), f"{route_name} responded {resp.status_code} for staff, expected 200/302"


# ---------------------------------------------------------------------------
# D. Non-staff user cannot reach admin surfaces.
# ---------------------------------------------------------------------------


STAFF_ONLY_ROUTES = [
    "babybuddy:user-list",
    "babybuddy:user-add",
]


@pytest.mark.parametrize("route_name", STAFF_ONLY_ROUTES)
def test_non_staff_cannot_reach_staff_route(regular_user, route_name):
    client = Client()
    client.login(username="pm_regular", password="Regular-Pwd-1!")
    resp = client.get(reverse(route_name))
    # Non-staff must NOT see a rendered admin page.  Acceptable answers are
    # redirect-to-login (302), Forbidden (403), or Not Found (404).
    assert (
        resp.status_code != 200
    ), f"{route_name} rendered 200 for a non-staff user - permission leak"


# ---------------------------------------------------------------------------
# E. Logout flow - every acceptable method is 2xx/3xx, never 5xx.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "get"])
def test_logout_never_crashes(regular_user, method):
    client = Client()
    client.login(username="pm_regular", password="Regular-Pwd-1!")
    resp = getattr(client, method)(reverse("babybuddy:logout"))
    # Even on GET (which Django 5 rejects with 405), we must not 500.
    assert (
        resp.status_code < 500
    ), f"{method.upper()} /logout/ produced {resp.status_code}"


# ---------------------------------------------------------------------------
# F. Password reset flow - GET on every page in the flow renders.
# ---------------------------------------------------------------------------


PASSWORD_RESET_ROUTES = [
    "babybuddy:password_reset",
    "babybuddy:password_reset_done",
    "babybuddy:password_reset_complete",
]


@pytest.mark.parametrize("route_name", PASSWORD_RESET_ROUTES)
def test_password_reset_stage_renders(db, route_name):
    client = Client()
    resp = client.get(reverse(route_name))
    assert resp.status_code == 200, f"{route_name} returned {resp.status_code}"


# ---------------------------------------------------------------------------
# G. /api/profile - token variants.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header_value",
    [
        "",  # empty
        "Token",  # missing key
        "Token invalidtoken",  # bad key
        "Bearer something",  # wrong scheme
    ],
)
def test_profile_rejects_bad_token(db, header_value):
    client = Client()
    resp = client.get(
        reverse("api:profile"),
        HTTP_AUTHORIZATION=header_value,
    )
    assert resp.status_code in (
        401,
        403,
    ), f"bad auth {header_value!r} got {resp.status_code}"


# ---------------------------------------------------------------------------
# H. Reverse routing - every named URL must resolve without exception.
# ---------------------------------------------------------------------------


NAMED_ROUTES_WITHOUT_ARGS = [
    "babybuddy:login",
    "babybuddy:logout",
    "babybuddy:password_reset",
    "babybuddy:user-settings",
    "babybuddy:user-list",
    "api:profile",
    "api:openapi-schema",
]


@pytest.mark.parametrize("route_name", NAMED_ROUTES_WITHOUT_ARGS)
def test_named_route_reverse_resolves(route_name):
    # Pure routing check: if the name is missing, reverse() raises.
    url = reverse(route_name)
    assert url.startswith("/"), f"reverse({route_name!r}) returned {url!r}"
