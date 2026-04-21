#####################################################
# api blackbox test                                 #
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
# Blackbox approach:
#   The API is exercised purely through its HTTP surface using
#   rest_framework.test.APIClient. Tests were designed from the
#   caregiver-facing contract (valid inputs accepted, invalid
#   inputs rejected with 4xx) without relying on internal
#   implementation details. Tests that expose real behavioral
#   bugs are marked @pytest.mark.found_bug plus @pytest.mark.xfail
#   so they turn green in the suite while still documenting the
#   defect; remove the xfail marker once the bug is fixed and the
#   test should XPASS on a corrected implementation.
#####################################################

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from django.test import SimpleTestCase

from core import models as core_models


#############################################
# Original URL-contract tests (kept intact) #
#############################################


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


#############################################
# Shared base: authenticated API client.    #
#############################################


class _AuthedAPITestCase(APITestCase):
    """
    Spin up a superuser + a Child so we can exercise all POST/PATCH
    routes through the HTTP surface.  We use a token so the caller
    looks the same as a real API consumer.
    """

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="caregiver",
            password="Sup3r-Safe-Pwd!",
            is_superuser=True,
            is_staff=True,
        )
        cls.token = Token.objects.create(user=cls.user)
        cls.child = core_models.Child.objects.create(
            first_name="Testy",
            last_name="McBaby",
            birth_date=datetime.date(2024, 1, 1),
        )

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    # Small helpers keeping tests concise.
    def _iso(self, dt):
        return dt.isoformat()

    def _now(self):
        return timezone.localtime()


#############################################
# Authentication / authorization (blackbox) #
#############################################


class APIAuthBlackBoxTests(APITestCase):
    """Hit the REST surface as an anonymous or bad-token client."""

    def test_anonymous_cannot_list_children(self):
        # Caller without credentials should not be able to enumerate data.
        resp = self.client.get(reverse("api:child-list"))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_anonymous_cannot_read_profile(self):
        resp = self.client.get(reverse("api:profile"))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        resp = self.client.get(reverse("api:child-list"))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_malformed_auth_header_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="NotToken nonsense")
        resp = self.client.get(reverse("api:child-list"))
        self.assertIn(resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


#############################################
# Child endpoint                            #
#############################################


class APIChildBlackBoxTests(_AuthedAPITestCase):
    def test_create_child_happy_path(self):
        resp = self.client.post(
            reverse("api:child-list"),
            data={
                "first_name": "Happy",
                "last_name": "Baby",
                "birth_date": "2024-06-15",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_create_child_missing_first_name_is_rejected(self):
        resp = self.client.post(
            reverse("api:child-list"),
            data={"last_name": "Alone", "birth_date": "2024-01-01"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("first_name", resp.json())

    def test_create_child_missing_birth_date_is_rejected(self):
        resp = self.client.post(
            reverse("api:child-list"),
            data={"first_name": "NoDob"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("birth_date", resp.json())

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: ChildSerializer does not reject birth_date in the future. "
            "A date a year from now should be invalid."
        ),
        strict=False,
    )
    def test_create_child_birth_date_in_future_should_be_rejected(self):
        future = (timezone.localdate() + datetime.timedelta(days=365)).isoformat()
        resp = self.client.post(
            reverse("api:child-list"),
            data={"first_name": "Futura", "last_name": "Prime", "birth_date": future},
            format="json",
        )
        # Caregiver-facing contract: no baby can be born in the future.
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Creating two children with identical first/last names "
            "generates identical slugs, causing an unhandled IntegrityError "
            "(HTTP 500) rather than a clean 400 validation error."
        ),
        strict=False,
    )
    def test_duplicate_names_should_not_500(self):
        payload = {
            "first_name": "John",
            "last_name": "Doe",
            "birth_date": "2024-01-02",
        }
        first = self.client.post(reverse("api:child-list"), data=payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)
        second = self.client.post(reverse("api:child-list"), data=payload, format="json")
        # A duplicate should be a validation problem, not a server error.
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)


#############################################
# Feeding endpoint                          #
#############################################


class APIFeedingBlackBoxTests(_AuthedAPITestCase):
    def _payload(self, **overrides):
        now = self._now()
        base = {
            "child": self.child.id,
            "start": self._iso(now - datetime.timedelta(minutes=30)),
            "end": self._iso(now - datetime.timedelta(minutes=10)),
            "type": "breast milk",
            "method": "bottle",
        }
        base.update(overrides)
        return base

    def test_create_feeding_happy_path(self):
        resp = self.client.post(
            reverse("api:feeding-list"), data=self._payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_feeding_end_before_start_is_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(minutes=10)),
                end=self._iso(now - datetime.timedelta(minutes=30)),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_feeding_invalid_type_is_rejected(self):
        resp = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(type="unicorn milk"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_feeding_invalid_method_is_rejected(self):
        resp = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(method="hyperdrive"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_feeding_duration_just_over_24h_is_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(hours=24, minutes=1)),
                end=self._iso(now),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_feeding_overlapping_time_period_is_rejected(self):
        now = self._now()
        first = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(hours=2)),
                end=self._iso(now - datetime.timedelta(hours=1)),
            ),
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)
        second = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(hours=1, minutes=30)),
                end=self._iso(now - datetime.timedelta(minutes=30)),
            ),
            format="json",
        )
        # Feedings for the same child cannot overlap in time.
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST, second.content)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Feeding.clean() only validates that `start` is not in the "
            "future, so a caregiver can log a feeding whose `end` time is in "
            "the future (asymmetric with Sleep/TummyTime which check both)."
        ),
        strict=False,
    )
    def test_feeding_end_in_future_should_be_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(minutes=10)),
                end=self._iso(now + datetime.timedelta(hours=2)),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Feeding.amount is a FloatField with no range validator; "
            "negative amounts (e.g. -100 ml) are silently accepted."
        ),
        strict=False,
    )
    def test_feeding_negative_amount_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:feeding-list"),
            data=self._payload(amount=-100.0),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)


#############################################
# Pumping endpoint                          #
#############################################


class APIPumpingBlackBoxTests(_AuthedAPITestCase):
    def _payload(self, **overrides):
        now = self._now()
        base = {
            "child": self.child.id,
            "amount": 120,
            "start": self._iso(now - datetime.timedelta(minutes=20)),
            "end": self._iso(now - datetime.timedelta(minutes=5)),
        }
        base.update(overrides)
        return base

    def test_create_pumping_happy_path(self):
        resp = self.client.post(
            reverse("api:pumping-list"), data=self._payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_pumping_end_before_start_is_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:pumping-list"),
            data=self._payload(
                start=self._iso(now),
                end=self._iso(now - datetime.timedelta(hours=1)),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Pumping.clean() only validates that `start` is not in the "
            "future; end-in-future pumpings are silently accepted."
        ),
        strict=False,
    )
    def test_pumping_end_in_future_should_be_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:pumping-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(minutes=5)),
                end=self._iso(now + datetime.timedelta(hours=1)),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Pumping.amount has no non-negative validator, so nonsensical "
            "negative amounts are accepted."
        ),
        strict=False,
    )
    def test_pumping_negative_amount_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:pumping-list"),
            data=self._payload(amount=-50),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


#############################################
# Sleep endpoint                            #
#############################################


class APISleepBlackBoxTests(_AuthedAPITestCase):
    def _payload(self, **overrides):
        now = self._now()
        base = {
            "child": self.child.id,
            "start": self._iso(now - datetime.timedelta(hours=2)),
            "end": self._iso(now - datetime.timedelta(hours=1)),
        }
        base.update(overrides)
        return base

    def test_create_sleep_happy_path(self):
        resp = self.client.post(
            reverse("api:sleep-list"), data=self._payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_sleep_end_in_future_is_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:sleep-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(minutes=30)),
                end=self._iso(now + datetime.timedelta(hours=2)),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sleep_duration_over_24h_is_rejected(self):
        now = self._now()
        resp = self.client.post(
            reverse("api:sleep-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(hours=25)),
                end=self._iso(now),
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sleep_overlap_same_child_is_rejected(self):
        now = self._now()
        first = self.client.post(
            reverse("api:sleep-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(hours=3)),
                end=self._iso(now - datetime.timedelta(hours=2)),
            ),
            format="json",
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.content)
        second = self.client.post(
            reverse("api:sleep-list"),
            data=self._payload(
                start=self._iso(now - datetime.timedelta(hours=2, minutes=30)),
                end=self._iso(now - datetime.timedelta(hours=1, minutes=30)),
            ),
            format="json",
        )
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST, second.content)


#############################################
# DiaperChange endpoint                     #
#############################################


class APIDiaperChangeBlackBoxTests(_AuthedAPITestCase):
    def _payload(self, **overrides):
        base = {
            "child": self.child.id,
            "time": self._iso(self._now() - datetime.timedelta(minutes=5)),
            "wet": True,
            "solid": False,
        }
        base.update(overrides)
        return base

    def test_create_happy_path(self):
        resp = self.client.post(
            reverse("api:diaperchange-list"), data=self._payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_diaperchange_time_in_future_is_rejected(self):
        resp = self.client.post(
            reverse("api:diaperchange-list"),
            data=self._payload(
                time=self._iso(self._now() + datetime.timedelta(hours=1))
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_diaperchange_invalid_color_is_rejected(self):
        resp = self.client.post(
            reverse("api:diaperchange-list"),
            data=self._payload(color="rainbow"),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: A DiaperChange with wet=False, solid=False and no color/amount "
            "is nonsensical (nothing actually changed) but the API accepts it."
        ),
        strict=False,
    )
    def test_empty_diaper_change_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:diaperchange-list"),
            data=self._payload(wet=False, solid=False),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


#############################################
# Note endpoint                             #
#############################################


class APINoteBlackBoxTests(_AuthedAPITestCase):
    def _payload(self, **overrides):
        base = {
            "child": self.child.id,
            "note": "baby smiled",
            "time": self._iso(self._now() - datetime.timedelta(minutes=1)),
        }
        base.update(overrides)
        return base

    def test_create_happy_path(self):
        resp = self.client.post(
            reverse("api:note-list"), data=self._payload(), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Note has no clean() validation on `time`, so notes can be "
            "logged with time in the future.  All other timestamped core "
            "models reject future times."
        ),
        strict=False,
    )
    def test_note_time_in_future_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:note-list"),
            data=self._payload(
                time=self._iso(self._now() + datetime.timedelta(days=2))
            ),
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


#############################################
# Temperature / Weight / BMI / Height /     #
# HeadCircumference measurement endpoints   #
#############################################


class APIMeasurementsBlackBoxTests(_AuthedAPITestCase):
    # These models share the same pattern: a positive real-world measurement
    # with an optional date.  They all lack a non-negative / range validator.

    def test_temperature_invalid_time_future_is_rejected(self):
        resp = self.client.post(
            reverse("api:temperature-list"),
            data={
                "child": self.child.id,
                "temperature": 37.2,
                "time": self._iso(self._now() + datetime.timedelta(hours=1)),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_temperature_happy_path(self):
        resp = self.client.post(
            reverse("api:temperature-list"),
            data={
                "child": self.child.id,
                "temperature": 37.2,
                "time": self._iso(self._now() - datetime.timedelta(minutes=1)),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Temperature has no sane-range validator so absurd values "
            "(e.g. 9999°C) are silently accepted."
        ),
        strict=False,
    )
    def test_temperature_absurd_value_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:temperature-list"),
            data={
                "child": self.child.id,
                "temperature": 9999,
                "time": self._iso(self._now() - datetime.timedelta(minutes=1)),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weight_happy_path(self):
        resp = self.client.post(
            reverse("api:weight-list"),
            data={
                "child": self.child.id,
                "weight": 4.2,
                "date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_weight_future_date_is_rejected(self):
        future = (timezone.localdate() + datetime.timedelta(days=3)).isoformat()
        resp = self.client.post(
            reverse("api:weight-list"),
            data={"child": self.child.id, "weight": 4.2, "date": future},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Weight has no positive-value validator, so zero and "
            "negative weights are silently accepted."
        ),
        strict=False,
    )
    def test_weight_zero_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:weight-list"),
            data={
                "child": self.child.id,
                "weight": 0,
                "date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: BMI has no positive-value validator; a negative BMI is "
            "physically impossible but silently stored."
        ),
        strict=False,
    )
    def test_bmi_negative_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:bmi-list"),
            data={
                "child": self.child.id,
                "bmi": -5,
                "date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: Height has no positive-value validator; a zero/negative "
            "height is silently stored."
        ),
        strict=False,
    )
    def test_height_zero_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:height-list"),
            data={
                "child": self.child.id,
                "height": 0,
                "date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: HeadCircumference has no positive-value validator."
        ),
        strict=False,
    )
    def test_head_circumference_negative_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:headcircumference-list"),
            data={
                "child": self.child.id,
                "head_circumference": -3.0,
                "date": timezone.localdate().isoformat(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


#############################################
# Tag endpoint                              #
#############################################


class APITagBlackBoxTests(_AuthedAPITestCase):
    def test_tag_happy_path(self):
        resp = self.client.post(
            reverse("api:tag-list"),
            data={"name": "morning", "color": "#abcdef"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_tag_missing_hash_in_color_is_rejected(self):
        resp = self.client.post(
            reverse("api:tag-list"),
            data={"name": "nohash", "color": "FF0000"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_tag_non_hex_color_is_rejected(self):
        resp = self.client.post(
            reverse("api:tag-list"),
            data={"name": "nothex", "color": "#GGGGGG"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    def test_tag_8char_color_with_alpha_is_rejected(self):
        # regex only allows 6 hex digits, alpha channel must be rejected.
        resp = self.client.post(
            reverse("api:tag-list"),
            data={"name": "alpha", "color": "#FF000080"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)


#############################################
# Timer endpoint + restart action           #
#############################################


class APITimerBlackBoxTests(_AuthedAPITestCase):
    def test_create_timer_happy_path(self):
        resp = self.client.post(
            reverse("api:timer-list"),
            data={
                "child": self.child.id,
                "name": "bath",
                "start": self._iso(self._now() - datetime.timedelta(minutes=10)),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)

    def test_timer_restart_resets_start_to_now(self):
        create = self.client.post(
            reverse("api:timer-list"),
            data={
                "child": self.child.id,
                "start": self._iso(self._now() - datetime.timedelta(minutes=30)),
            },
            format="json",
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.content)
        pk = create.json()["id"]
        before_restart = self._now()
        resp = self.client.patch(reverse("api:timer-restart", args=[pk]))
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.content)
        new_start = datetime.datetime.fromisoformat(
            resp.json()["start"].replace("Z", "+00:00")
        )
        # After restart, start must be >= the moment we fired the restart call.
        self.assertGreaterEqual(
            new_start.timestamp(),
            (before_restart - datetime.timedelta(seconds=1)).timestamp(),
        )

    def test_timer_start_in_future_should_be_rejected(self):
        resp = self.client.post(
            reverse("api:timer-list"),
            data={
                "child": self.child.id,
                "start": self._iso(self._now() + datetime.timedelta(hours=1)),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)

    @pytest.mark.found_bug
    @pytest.mark.xfail(
        reason=(
            "Bug: CoreModelWithDurationSerializer silently overrides any "
            "caller-supplied `start` and `end` when a `timer` id is also "
            "provided, instead of rejecting the conflicting payload."
        ),
        strict=False,
    )
    def test_feeding_with_timer_and_explicit_start_end_should_not_silently_override(self):
        # Create a timer owned by our user.
        t_resp = self.client.post(
            reverse("api:timer-list"),
            data={
                "child": self.child.id,
                "start": self._iso(self._now() - datetime.timedelta(minutes=20)),
            },
            format="json",
        )
        self.assertEqual(t_resp.status_code, status.HTTP_201_CREATED, t_resp.content)
        timer_id = t_resp.json()["id"]

        my_start = self._now() - datetime.timedelta(minutes=10)
        my_end = self._now() - datetime.timedelta(minutes=1)
        resp = self.client.post(
            reverse("api:feeding-list"),
            data={
                "child": self.child.id,
                "start": self._iso(my_start),
                "end": self._iso(my_end),
                "type": "formula",
                "method": "bottle",
                "timer": timer_id,
            },
            format="json",
        )
        # The contract a caller would expect: either reject the conflicting
        # input (400) or honor the explicit start/end.  Currently the server
        # accepts the request (201) AND silently throws away the caller's
        # start/end values, which is the worst of both options.
        if resp.status_code == status.HTTP_201_CREATED:
            body = resp.json()
            saved_start = datetime.datetime.fromisoformat(
                body["start"].replace("Z", "+00:00")
            )
            # If the server accepted us, it must have honored our start.
            self.assertAlmostEqual(
                saved_start.timestamp(), my_start.timestamp(), delta=2
            )
        else:
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
