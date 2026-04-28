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
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_anonymous_cannot_read_profile(self):
        resp = self.client.get(reverse("api:profile"))
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_invalid_token_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token not-a-real-token")
        resp = self.client.get(reverse("api:child-list"))
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )

    def test_malformed_auth_header_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="NotToken nonsense")
        resp = self.client.get(reverse("api:child-list"))
        self.assertIn(
            resp.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
        )


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
        second = self.client.post(
            reverse("api:child-list"), data=payload, format="json"
        )
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
        self.assertEqual(
            second.status_code, status.HTTP_400_BAD_REQUEST, second.content
        )

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
        self.assertEqual(
            second.status_code, status.HTTP_400_BAD_REQUEST, second.content
        )


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
        reason=("Bug: HeadCircumference has no positive-value validator."),
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
    def test_feeding_with_timer_and_explicit_start_end_should_not_silently_override(
        self,
    ):
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


#####################################################################
# Parametric blackbox expansions                                     #
#                                                                    #
# Author: Samson Cournane                                            #
#                                                                    #
# The class-based tests above cover one concrete case per scenario.  #
# The pytest-style functions below enumerate whole equivalence       #
# classes using @pytest.mark.parametrize so each rejection /         #
# acceptance rule is proven against every member of the class, not   #
# just a single representative value.  This is the blackbox analogue #
# of boundary-value + partition testing: one rule -> many inputs.    #
#####################################################################


@pytest.fixture
def api_child(db):
    """A Child row usable as `child=<id>` in POST payloads."""
    return core_models.Child.objects.create(
        first_name="Parametric",
        last_name="Kid",
        birth_date=datetime.date(2024, 1, 1),
    )


@pytest.fixture
def authed_client(db):
    """Token-authed APIClient for a superuser."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="parametric_caregiver",
        defaults={"is_staff": True, "is_superuser": True},
    )
    user.set_password("Sup3r-Safe-Pwd!")
    user.save()
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _now_iso(offset_seconds: int = 0) -> str:
    return (
        timezone.localtime() + datetime.timedelta(seconds=offset_seconds)
    ).isoformat()


# ---------------------------------------------------------------------------
# A. Anonymous access to list endpoints - every route should reject anon.
# ---------------------------------------------------------------------------


ANON_GATED_ENDPOINTS = [
    "api:child-list",
    "api:feeding-list",
    "api:sleep-list",
    "api:pumping-list",
    "api:diaperchange-list",
    "api:note-list",
    "api:temperature-list",
    "api:weight-list",
    "api:bmi-list",
    "api:height-list",
    "api:headcircumference-list",
    "api:tag-list",
    "api:timer-list",
    "api:tummytime-list",
]


@pytest.mark.parametrize("route_name", ANON_GATED_ENDPOINTS)
def test_anonymous_cannot_list_endpoint(route_name, db):
    client = APIClient()  # no credentials
    resp = client.get(reverse(route_name))
    assert resp.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ), f"{route_name} should gate anonymous GET, got {resp.status_code}"


# ---------------------------------------------------------------------------
# B. Bad / malformed auth headers across endpoints.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_header",
    [
        "Token ",  # empty token
        "Token not-a-real-token",  # garbage
        "Bearer something",  # wrong scheme
        "NotToken xyz",  # unknown scheme
        "token lowercase-scheme",  # case-sensitivity sanity
        " Token extra-leading-space",  # malformed
    ],
)
def test_malformed_auth_headers_are_rejected(bad_header, db):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=bad_header)
    resp = client.get(reverse("api:child-list"))
    assert resp.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ), f"auth header {bad_header!r} should be rejected, got {resp.status_code}"


# ---------------------------------------------------------------------------
# C. Child create - invalid birth_date partitions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_birth_date",
    [
        "",  # empty
        "not-a-date",  # not ISO
        "2024/01/01",  # wrong separator
        "2024-13-01",  # invalid month
        "2024-02-30",  # invalid day
        "abcd-ef-gh",  # total garbage
    ],
)
def test_child_rejects_malformed_birth_date(authed_client, bad_birth_date):
    resp = authed_client.post(
        reverse("api:child-list"),
        data={"first_name": "Bad", "last_name": "Date", "birth_date": bad_birth_date},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# D. Child create - invalid first_name partitions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_first_name",
    [
        "",  # empty
        "   ",  # whitespace only (blank after strip)
        None,  # null
        "x" * 500,  # exceeds max_length=255
    ],
)
def test_child_rejects_bad_first_name(authed_client, bad_first_name):
    resp = authed_client.post(
        reverse("api:child-list"),
        data={
            "first_name": bad_first_name,
            "last_name": "Ok",
            "birth_date": "2024-01-01",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# E. Feeding - every valid (type, method) combination is accepted.
# ---------------------------------------------------------------------------


VALID_FEEDING_TYPES = [
    "breast milk",
    "formula",
    "fortified breast milk",
    "solid food",
]
VALID_FEEDING_METHODS = [
    "bottle",
    "left breast",
    "right breast",
    "both breasts",
    "parent fed",
    "self fed",
]


@pytest.mark.parametrize("feeding_type", VALID_FEEDING_TYPES)
def test_feeding_accepts_every_valid_type(authed_client, api_child, feeding_type):
    now = timezone.localtime()
    resp = authed_client.post(
        reverse("api:feeding-list"),
        data={
            "child": api_child.id,
            "start": (now - datetime.timedelta(minutes=30)).isoformat(),
            "end": (now - datetime.timedelta(minutes=10)).isoformat(),
            "type": feeding_type,
            "method": "bottle",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.content


@pytest.mark.parametrize("feeding_method", VALID_FEEDING_METHODS)
def test_feeding_accepts_every_valid_method(authed_client, api_child, feeding_method):
    now = timezone.localtime()
    resp = authed_client.post(
        reverse("api:feeding-list"),
        data={
            "child": api_child.id,
            "start": (now - datetime.timedelta(minutes=30)).isoformat(),
            "end": (now - datetime.timedelta(minutes=10)).isoformat(),
            "type": "breast milk",
            "method": feeding_method,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.content


@pytest.mark.parametrize(
    "bad_type",
    ["unicorn milk", "", "BREAST MILK", "breast_milk", "soda"],
)
def test_feeding_rejects_invalid_type(authed_client, api_child, bad_type):
    now = timezone.localtime()
    resp = authed_client.post(
        reverse("api:feeding-list"),
        data={
            "child": api_child.id,
            "start": (now - datetime.timedelta(minutes=30)).isoformat(),
            "end": (now - datetime.timedelta(minutes=10)).isoformat(),
            "type": bad_type,
            "method": "bottle",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


@pytest.mark.parametrize(
    "bad_method",
    ["hyperdrive", "", "BOTTLE", "syringe", "iv drip"],
)
def test_feeding_rejects_invalid_method(authed_client, api_child, bad_method):
    now = timezone.localtime()
    resp = authed_client.post(
        reverse("api:feeding-list"),
        data={
            "child": api_child.id,
            "start": (now - datetime.timedelta(minutes=30)).isoformat(),
            "end": (now - datetime.timedelta(minutes=10)).isoformat(),
            "type": "breast milk",
            "method": bad_method,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# F. DiaperChange colors - the canonical four are accepted; others are not.
# ---------------------------------------------------------------------------


VALID_DIAPER_COLORS = ["black", "brown", "green", "yellow"]


@pytest.mark.parametrize("color", VALID_DIAPER_COLORS)
def test_diaper_accepts_every_valid_color(authed_client, api_child, color):
    resp = authed_client.post(
        reverse("api:diaperchange-list"),
        data={
            "child": api_child.id,
            "time": (timezone.localtime() - datetime.timedelta(minutes=5)).isoformat(),
            "wet": False,
            "solid": True,
            "color": color,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.content


@pytest.mark.parametrize(
    "bad_color",
    ["rainbow", "BLACK", "#000000", "red", "grey", "purple"],
)
def test_diaper_rejects_invalid_color(authed_client, api_child, bad_color):
    resp = authed_client.post(
        reverse("api:diaperchange-list"),
        data={
            "child": api_child.id,
            "time": (timezone.localtime() - datetime.timedelta(minutes=5)).isoformat(),
            "wet": False,
            "solid": True,
            "color": bad_color,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# G. Measurements - every measurement endpoint must reject a future date.
# ---------------------------------------------------------------------------


MEASUREMENT_DATE_ENDPOINTS = [
    ("api:weight-list", "weight", 4.2),
    ("api:height-list", "height", 55.0),
    ("api:bmi-list", "bmi", 15.0),
    ("api:headcircumference-list", "head_circumference", 36.0),
]


@pytest.mark.parametrize("route,field,value", MEASUREMENT_DATE_ENDPOINTS)
def test_measurement_rejects_future_date(authed_client, api_child, route, field, value):
    future = (timezone.localdate() + datetime.timedelta(days=3)).isoformat()
    resp = authed_client.post(
        reverse(route),
        data={"child": api_child.id, field: value, "date": future},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


@pytest.mark.parametrize("route,field,value", MEASUREMENT_DATE_ENDPOINTS)
def test_measurement_accepts_today(authed_client, api_child, route, field, value):
    today = timezone.localdate().isoformat()
    resp = authed_client.post(
        reverse(route),
        data={"child": api_child.id, field: value, "date": today},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.content


@pytest.mark.parametrize(
    "route,field,value",
    MEASUREMENT_DATE_ENDPOINTS + [("api:temperature-list", "temperature", 37.2)],
)
def test_measurement_missing_child_is_rejected(authed_client, route, field, value):
    today = timezone.localdate().isoformat()
    resp = authed_client.post(
        reverse(route),
        data={field: value, "date": today},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# H. Tag colors - a real hex regex is the spec; exercise both sides.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "color",
    ["#000000", "#ffffff", "#AaBbCc", "#123abc"],
)
def test_tag_accepts_valid_hex_color(authed_client, color):
    resp = authed_client.post(
        reverse("api:tag-list"),
        data={"name": f"ok-{color.strip('#')}", "color": color},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.content


@pytest.mark.parametrize(
    "bad_color",
    [
        "FFFFFF",  # missing #
        "#FFF",  # 3-digit shorthand (spec requires 6)
        "#GGGGGG",  # non-hex characters
        "#1234567",  # 7 chars (should be 6)
        "#FF000080",  # 8 chars with alpha
        "red",  # not hex at all
        "",  # empty
    ],
)
def test_tag_rejects_bad_hex_color(authed_client, bad_color):
    resp = authed_client.post(
        reverse("api:tag-list"),
        data={"name": "bad", "color": bad_color},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# I. Required-field matrix: each POST endpoint rejects requests with only
# a single required field supplied.  Surfaces inconsistent error surfaces.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "route,sole_field,value",
    [
        ("api:feeding-list", "type", "breast milk"),
        ("api:sleep-list", "child", 1),
        ("api:pumping-list", "amount", 120),
        ("api:diaperchange-list", "wet", True),
        ("api:note-list", "note", "partial"),
        ("api:weight-list", "weight", 4.2),
        ("api:bmi-list", "bmi", 15),
        ("api:height-list", "height", 55),
        ("api:headcircumference-list", "head_circumference", 35),
        ("api:temperature-list", "temperature", 37),
    ],
)
def test_endpoint_rejects_partial_payload(
    authed_client, api_child, route, sole_field, value
):
    resp = authed_client.post(
        reverse(route),
        data={sole_field: value},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.content


# ---------------------------------------------------------------------------
# J. Timer restart rejects non-PATCH methods.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "put", "delete", "post"])
def test_timer_restart_rejects_wrong_method(authed_client, api_child, method):
    created = authed_client.post(
        reverse("api:timer-list"),
        data={
            "child": api_child.id,
            "start": (timezone.localtime() - datetime.timedelta(minutes=5)).isoformat(),
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    timer_id = created.json()["id"]
    resp = getattr(authed_client, method)(reverse("api:timer-restart", args=[timer_id]))
    # restart is PATCH-only in the API contract.
    assert resp.status_code in (
        status.HTTP_405_METHOD_NOT_ALLOWED,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_400_BAD_REQUEST,
    ), f"method {method!r} should not be accepted, got {resp.status_code}"


# ---------------------------------------------------------------------------
# K. GET on list endpoints returns a paginated envelope for every resource.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route_name", ANON_GATED_ENDPOINTS)
def test_authed_list_returns_envelope(authed_client, route_name):
    resp = authed_client.get(reverse(route_name))
    assert resp.status_code == status.HTTP_200_OK, resp.content
    body = resp.json()
    # DRF default pagination envelope.
    for key in ("count", "results"):
        assert key in body, (
            f"list envelope from {route_name} is missing `{key}` "
            f"(body keys: {list(body.keys())})"
        )


# ---------------------------------------------------------------------------
# L. Note length - contract is 255-char max.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("length", [1, 50, 254, 255])
def test_note_accepts_length_up_to_limit(authed_client, api_child, length):
    resp = authed_client.post(
        reverse("api:note-list"),
        data={
            "child": api_child.id,
            "note": "x" * length,
            "time": (timezone.localtime() - datetime.timedelta(minutes=1)).isoformat(),
        },
        format="json",
    )
    # A clean-contract response is 201.  Some legacy deployments allow longer
    # notes via an open TextField - in that case 201 is still expected, which
    # is why we constrain the upper bound to 255 above.
    assert resp.status_code == status.HTTP_201_CREATED, resp.content
