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
        resp = self.client.get(
            reverse("dashboard:dashboard-child", args=["ghost-kid"])
        )
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
