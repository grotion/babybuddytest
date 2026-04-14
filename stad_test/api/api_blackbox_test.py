from django.test import SimpleTestCase
from django.urls import resolve, reverse


class APIBlackBoxRouteTests(SimpleTestCase):
    """
    Black-box tests focused on public API surface:
    route existence, reverse names, and URL contract.
    These avoid database setup and migration-heavy paths.
    """

    def test_reverse_bmi_list_route(self):
        url = reverse("api:bmi-list")
        self.assertTrue(url.endswith("/api/bmi/"))

    def test_reverse_child_list_route(self):
        url = reverse("api:child-list")
        self.assertTrue(url.endswith("/api/children/"))

    def test_reverse_profile_route(self):
        url = reverse("api:profile")
        self.assertTrue(url.endswith("/api/profile"))

    def test_reverse_schema_route(self):
        url = reverse("api:openapi-schema")
        self.assertTrue(url.endswith("/api/schema"))

    def test_reverse_timer_restart_route(self):
        url = reverse("api:timer-restart", args=[123])
        self.assertTrue(url.endswith("/api/timers/123/restart/"))

    def test_profile_route_resolves(self):
        match = resolve("/api/profile")
        self.assertEqual(match.view_name, "api:profile")

    def test_schema_route_resolves(self):
        match = resolve("/api/schema")
        self.assertEqual(match.view_name, "api:openapi-schema")
