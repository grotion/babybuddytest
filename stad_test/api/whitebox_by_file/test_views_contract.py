from unittest.mock import MagicMock, patch

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from api import filters
from api import serializers as api_serializers
from api import views
from babybuddy import models as babybuddy_models


class ViewsContractTests(SimpleTestCase):
    # Component: api/views.py
    # Intent: viewsets should expose expected serializers/filters, and custom methods should provide the right outcomes.

    def test_bmi_view_name_contains_bmi_and_optional_suffix(self):
        view = views.BMIViewSet()
        view.suffix = None
        self.assertIn("BMI", view.get_view_name())

        view.suffix = "List"
        name = view.get_view_name()
        self.assertIn("BMI", name)
        self.assertIn("List", name)

    def test_viewsets_use_expected_serializers_and_filters(self):
        self.assertIs(views.BMIViewSet.serializer_class, api_serializers.BMISerializer)
        self.assertIs(views.ChildViewSet.serializer_class, api_serializers.ChildSerializer)
        self.assertEqual(views.ChildViewSet.lookup_field, "slug")
        self.assertIs(views.DiaperChangeViewSet.serializer_class, api_serializers.DiaperChangeSerializer)
        self.assertIs(views.DiaperChangeViewSet.filterset_class, filters.DiaperChangeFilter)
        self.assertIs(views.FeedingViewSet.serializer_class, api_serializers.FeedingSerializer)
        self.assertIs(views.FeedingViewSet.filterset_class, filters.FeedingFilter)
        self.assertIs(views.HeadCircumferenceViewSet.serializer_class, api_serializers.HeadCircumferenceSerializer)
        self.assertIs(views.HeightViewSet.serializer_class, api_serializers.HeightSerializer)
        self.assertIs(views.NoteViewSet.serializer_class, api_serializers.NoteSerializer)
        self.assertIs(views.NoteViewSet.filterset_class, filters.NoteFilter)
        self.assertIs(views.PumpingViewSet.serializer_class, api_serializers.PumpingSerializer)
        self.assertIs(views.PumpingViewSet.filterset_class, filters.PumpingFilter)
        self.assertIs(views.SleepViewSet.serializer_class, api_serializers.SleepSerializer)
        self.assertIs(views.SleepViewSet.filterset_class, filters.SleepFilter)
        self.assertIs(views.TagViewSet.serializer_class, api_serializers.TagSerializer)
        self.assertEqual(views.TagViewSet.lookup_field, "slug")
        self.assertIs(views.TemperatureViewSet.serializer_class, api_serializers.TemperatureSerializer)
        self.assertIs(views.TemperatureViewSet.filterset_class, filters.TemperatureFilter)
        self.assertIs(views.TimerViewSet.serializer_class, api_serializers.TimerSerializer)
        self.assertIs(views.TimerViewSet.filterset_class, filters.TimerFilter)
        self.assertIs(views.TummyTimeViewSet.serializer_class, api_serializers.TummyTimeSerializer)
        self.assertIs(views.TummyTimeViewSet.filterset_class, filters.TummyTimeFilter)
        self.assertIs(views.WeightViewSet.serializer_class, api_serializers.WeightSerializer)

    def test_representative_ordering_contracts_are_exposed(self):
        self.assertEqual(views.BMIViewSet.ordering, "-date")
        self.assertEqual(views.ChildViewSet.ordering, ["-birth_date", "-birth_time"])
        self.assertEqual(views.FeedingViewSet.ordering, "-end")
        self.assertEqual(views.TimerViewSet.ordering, "-start")
        self.assertEqual(views.TagViewSet.ordering, "name")

    def test_timer_restart_invokes_timer_restart_and_returns_serialized_data(self):
        timer = MagicMock()
        timer.restart = MagicMock()

        class DummySerializer:
            def __init__(self, obj):
                self.data = {"id": 1, "name": "timer"}

        view = views.TimerViewSet()
        view.get_object = MagicMock(return_value=timer)
        view.serializer_class = DummySerializer

        response = view.restart(request=None, pk=1)
        timer.restart.assert_called_once()
        self.assertEqual(response.data, {"id": 1, "name": "timer"})

    def test_profile_view_exposes_expected_static_contract(self):
        self.assertEqual(views.ProfileView.action, "get")
        self.assertEqual(views.ProfileView.basename, "profile")
        self.assertIs(views.ProfileView.serializer_class, api_serializers.ProfileSerializer)

    def test_profile_view_returns_serialized_settings_for_current_user(self):
        request = RequestFactory().get("/api/profile/")
        request.user = "user-object"
        settings_obj = object()

        class DummySerializer:
            def __init__(self, obj):
                self.data = {"matched": obj is settings_obj}

        view = views.ProfileView()
        view.serializer_class = DummySerializer

        with patch.object(views, "get_object_or_404", return_value=settings_obj) as mock_get:
            response = view.get(request)

        mock_get.assert_called_once_with(babybuddy_models.Settings.objects, user="user-object")
        self.assertEqual(response.data, {"matched": True})

    def test_profile_view_raises_http404_when_settings_missing(self):
        request = RequestFactory().get("/api/profile/")
        request.user = "user-object"
        view = views.ProfileView()

        with patch.object(views, "get_object_or_404", side_effect=Http404):
            with self.assertRaises(Http404):
                view.get(request)
