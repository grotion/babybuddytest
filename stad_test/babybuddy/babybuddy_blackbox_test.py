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
            "with path=...|add\"</code>\"|safe` line is missing a colon "
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
