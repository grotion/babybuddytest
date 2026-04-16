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
# ------------------------------------------------- #
#####################################################

from django.test import SimpleTestCase
from django.urls import reverse


class BabyBuddyBlackBoxSmokeTests(SimpleTestCase):
    def test_api_profile_route_is_named(self):
        url = reverse("api:profile")
        self.assertTrue(url.endswith("/api/profile"))
