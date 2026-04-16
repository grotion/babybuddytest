from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from api import serializers as api_serializers
from core import models


class DummyModel:
    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)

    def clean(self):
        return None


class DummyCoreModelSerializer(api_serializers.CoreModelSerializer):
    class Meta:
        model = DummyModel


class DummyDurationSerializer(api_serializers.CoreModelWithDurationSerializer):
    class Meta(api_serializers.CoreModelWithDurationSerializer.Meta):
        model = DummyModel


class SerializersContractTests(SimpleTestCase):
    # Component: api/serializers.py
    # Intent: serializers should enforce public validation behavior and expose expected field contracts.

    def test_core_serializer_returns_validated_data_for_valid_input(self):
        serializer = DummyCoreModelSerializer()
        attrs = {"alpha": 1}
        self.assertEqual(serializer.validate(attrs), attrs)

    def test_core_serializer_partial_update_returns_only_changed_fields(self):
        serializer = DummyCoreModelSerializer(instance=DummyModel(alpha=1, beta=2), partial=True)
        result = serializer.validate({"beta": 99})
        self.assertEqual(result, {"beta": 99})

    def test_duration_serializer_requires_child_start_and_end_without_timer(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({})
        self.assertIn("child", exc.exception.detail)
        self.assertIn("start", exc.exception.detail)
        self.assertIn("end", exc.exception.detail)

    def test_duration_serializer_partial_update_does_not_require_all_fields(self):
        serializer = DummyDurationSerializer(instance=DummyModel(child="c", start="s", end="e"), partial=True)
        self.assertEqual(serializer.validate({}), {})

    def test_duration_serializer_uses_timer_to_supply_missing_fields(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child="timer-child", start="timer-start", stop=MagicMock())

        with patch.object(api_serializers.timezone, "now", return_value="now"):
            result = serializer.validate({"timer": timer})

        self.assertEqual(result["child"], "timer-child")
        self.assertEqual(result["start"], "timer-start")
        self.assertEqual(result["end"], "now")
        self.assertNotIn("timer", result)
        timer.stop.assert_called_once()

    def test_duration_serializer_with_timer_and_no_child_reports_child_required(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child=None, start="timer-start", stop=MagicMock())

        with patch.object(api_serializers.timezone, "now", return_value="now"):
            with self.assertRaises(ValidationError) as exc:
                serializer.validate({"timer": timer})

        self.assertIn("child", exc.exception.detail)
        self.assertNotIn("start", exc.exception.detail)
        self.assertNotIn("end", exc.exception.detail)
        timer.stop.assert_not_called()

    def test_duration_serializer_timer_values_override_manual_values(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child="timer-child", start="timer-start", stop=MagicMock())

        with patch.object(api_serializers.timezone, "now", return_value="now"):
            result = serializer.validate(
                {"timer": timer, "child": "manual-child", "start": "manual-start", "end": "manual-end"}
            )

        self.assertEqual(result["child"], "timer-child")
        self.assertEqual(result["start"], "timer-start")
        self.assertEqual(result["end"], "now")

    def test_taggable_serializer_tags_are_optional(self):
        self.assertFalse(api_serializers.TaggableSerializer().fields["tags"].required)

    def test_sleep_serializer_nap_field_is_optional_and_nullable(self):
        nap_field = api_serializers.SleepSerializer().fields["nap"]
        self.assertFalse(nap_field.required)
        self.assertTrue(nap_field.allow_null)
        self.assertIsNone(nap_field.default)

    def test_timer_serializer_child_and_user_are_optional_and_duration_is_read_only(self):
        serializer = api_serializers.TimerSerializer()
        self.assertFalse(serializer.fields["child"].required)
        self.assertTrue(serializer.fields["child"].allow_null)
        self.assertFalse(serializer.fields["user"].required)
        self.assertTrue(serializer.fields["user"].allow_null)
        self.assertTrue(serializer.fields["duration"].read_only)

    def test_timer_serializer_defaults_user_from_request_when_missing(self):
        serializer = api_serializers.TimerSerializer(context={"request": SimpleNamespace(user="request-user")})
        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={"name": "x"}):
            result = serializer.validate({"name": "x"})
        self.assertEqual(result["user"], "request-user")

    def test_timer_serializer_defaults_user_from_request_when_none(self):
        serializer = api_serializers.TimerSerializer(context={"request": SimpleNamespace(user="request-user")})
        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={"user": None}):
            result = serializer.validate({"user": None})
        self.assertEqual(result["user"], "request-user")

    def test_timer_serializer_preserves_explicit_user(self):
        serializer = api_serializers.TimerSerializer(context={"request": SimpleNamespace(user="request-user")})
        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={"user": "explicit-user"}):
            result = serializer.validate({"user": "explicit-user"})
        self.assertEqual(result["user"], "explicit-user")

    def test_profile_serializer_returns_api_key_string(self):
        serializer = api_serializers.ProfileSerializer()
        serializer.instance = SimpleNamespace(api_key=lambda: SimpleNamespace(key="secret-key"))
        self.assertEqual(serializer.get_api_key(None), "secret-key")

    def test_user_serializer_fields_are_read_only(self):
        for field in api_serializers.UserSerializer.Meta.fields:
            self.assertTrue(api_serializers.UserSerializer.Meta.extra_kwargs[field]["read_only"])

    def test_profile_serializer_fields_are_read_only(self):
        for field in api_serializers.ProfileSerializer.Meta.fields:
            self.assertTrue(api_serializers.ProfileSerializer.Meta.extra_kwargs[field]["read_only"])

    def test_representative_serializer_models_match_expected_models(self):
        self.assertIs(api_serializers.BMISerializer.Meta.model, models.BMI)
        self.assertIs(api_serializers.PumpingSerializer.Meta.model, models.Pumping)
        self.assertIs(api_serializers.ChildSerializer.Meta.model, models.Child)
        self.assertIs(api_serializers.DiaperChangeSerializer.Meta.model, models.DiaperChange)
        self.assertIs(api_serializers.FeedingSerializer.Meta.model, models.Feeding)
        self.assertIs(api_serializers.HeadCircumferenceSerializer.Meta.model, models.HeadCircumference)
        self.assertIs(api_serializers.HeightSerializer.Meta.model, models.Height)
        self.assertIs(api_serializers.NoteSerializer.Meta.model, models.Note)
        self.assertIs(api_serializers.SleepSerializer.Meta.model, models.Sleep)
        self.assertIs(api_serializers.TagSerializer.Meta.model, models.Tag)
        self.assertIs(api_serializers.TemperatureSerializer.Meta.model, models.Temperature)
        self.assertIs(api_serializers.TimerSerializer.Meta.model, models.Timer)
        self.assertIs(api_serializers.TummyTimeSerializer.Meta.model, models.TummyTime)
        self.assertIs(api_serializers.WeightSerializer.Meta.model, models.Weight)

    def test_child_serializer_uses_slug_lookup(self):
        self.assertEqual(api_serializers.ChildSerializer.Meta.lookup_field, "slug")

    def test_tag_serializer_slug_and_last_used_are_read_only(self):
        extra = api_serializers.TagSerializer.Meta.extra_kwargs
        self.assertTrue(extra["slug"]["read_only"])
        self.assertTrue(extra["last_used"]["read_only"])

    def test_bmi_serializer_uses_bmi_label_override(self):
        self.assertEqual(api_serializers.BMISerializer.Meta.extra_kwargs["core.BMI.bmi"]["label"], "BMI")
