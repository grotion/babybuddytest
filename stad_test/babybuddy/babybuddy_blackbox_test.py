from django.test import SimpleTestCase
from django.urls import reverse


class BabyBuddyBlackBoxSmokeTests(SimpleTestCase):
    def test_api_profile_route_is_named(self):
        url = reverse("api:profile")
        self.assertTrue(url.endswith("/api/profile"))
