from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase
from rest_framework.exceptions import ValidationError

import api.filters as api_filters
import api.metadata as api_metadata
import api.permissions as api_permissions
import api.serializers as api_serializers
import api.urls as api_urls
import api.views as api_views


class DummyFiltersetClass:
    class Meta:
        fields = ["child", "date"]


class DummyViewWithFields:
    filterset_fields = ("child", "date")


class DummyViewWithClass:
    filterset_class = DummyFiltersetClass


class DummyPlainView:
    pass


def dummy_view(request):
    return HttpResponse("ok")


class DummyModel:
    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)

    def clean(self):
        return None


class DummyCoreSerializer(api_serializers.CoreModelSerializer):
    class Meta:
        model = DummyModel


class DummyDurationSerializer(api_serializers.CoreModelWithDurationSerializer):
    class Meta(api_serializers.CoreModelWithDurationSerializer.Meta):
        model = DummyModel


class APIMetadataWhiteBoxTests(SimpleTestCase):
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_determine_metadata_uses_filterset_fields_branch(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove"}
        result = api_metadata.APIMetadata().determine_metadata(
            None, DummyViewWithFields()
        )
        self.assertNotIn("description", result)
        self.assertEqual(result["filters"], ("child", "date"))

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_determine_metadata_uses_filterset_class_branch(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove"}
        result = api_metadata.APIMetadata().determine_metadata(
            None, DummyViewWithClass()
        )
        self.assertNotIn("description", result)
        self.assertEqual(result["filters"], ["child", "date"])

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_determine_metadata_without_filter_data_branch(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove"}
        result = api_metadata.APIMetadata().determine_metadata(None, DummyPlainView())
        self.assertNotIn("description", result)
        self.assertNotIn("filters", result)


class APIPermissionsWhiteBoxTests(SimpleTestCase):
    def test_custom_permission_map_matches_expected_contract(self):
        perms = api_permissions.BabyBuddyDjangoModelPermissions.perms_map
        self.assertEqual(perms["GET"], ["%(app_label)s.view_%(model_name)s"])
        self.assertEqual(perms["OPTIONS"], ["%(app_label)s.add_%(model_name)s"])
        self.assertEqual(perms["HEAD"], [])
        self.assertEqual(perms["POST"], ["%(app_label)s.add_%(model_name)s"])
        self.assertEqual(perms["PATCH"], ["%(app_label)s.change_%(model_name)s"])
        self.assertEqual(perms["DELETE"], ["%(app_label)s.delete_%(model_name)s"])
        self.assertNotIn("PUT", perms)


class APIFiltersWhiteBoxTests(SimpleTestCase):
    def test_tags_filter_field_name(self):
        self.assertEqual(
            api_filters.DiaperChangeFilter.base_filters["tags"].field_name,
            "tags__name",
        )

    def test_time_filter_fields(self):
        fields = api_filters.TimeFieldFilter.Meta.fields
        for name in ["child", "date", "date_max", "date_min"]:
            self.assertIn(name, fields)

    def test_start_end_filter_fields(self):
        fields = api_filters.StartEndFieldFilter.Meta.fields
        for name in [
            "child",
            "start",
            "start_max",
            "start_min",
            "end",
            "end_max",
            "end_min",
        ]:
            self.assertIn(name, fields)

    def test_timer_filter_fields_include_name_and_user(self):
        fields = api_filters.TimerFilter.Meta.fields
        self.assertIn("name", fields)
        self.assertIn("user", fields)


class APIRouterWhiteBoxTests(SimpleTestCase):
    def test_router_init_sets_empty_extra_urls(self):
        router = api_urls.CustomRouterWithExtraPaths()
        self.assertEqual(router.extra_api_urls, [])

    def test_add_detail_path_appends_extra_route(self):
        router = api_urls.CustomRouterWithExtraPaths()
        router.add_detail_path("profile", "profile", dummy_view)
        self.assertEqual(len(router.extra_api_urls), 1)
        self.assertEqual(router.extra_api_urls[0].path, "profile")
        self.assertEqual(router.extra_api_urls[0].reverese_name, "profile")

    def test_get_api_root_view_includes_registry_and_extra_paths(self):
        router = api_urls.CustomRouterWithExtraPaths()
        router.registry = [("bmi", object(), "bmi")]
        router.add_detail_path("profile", "profile", dummy_view)

        captured = {}

        def fake_as_view(*, api_root_dict):
            captured["api_root_dict"] = api_root_dict
            return "root-view"

        with patch.object(router.APIRootView, "as_view", side_effect=fake_as_view):
            result = router.get_api_root_view()

        self.assertEqual(result, "root-view")
        self.assertIn("bmi", captured["api_root_dict"])
        self.assertEqual(captured["api_root_dict"]["profile"], "profile")

    def test_urls_property_returns_base_urls_plus_extra_routes(self):
        router = api_urls.CustomRouterWithExtraPaths()
        router.add_detail_path("profile", "profile", dummy_view)
        urls = router.urls
        self.assertTrue(
            any(getattr(u.pattern, "_route", "") == "profile" for u in urls)
        )


class APISerializerWhiteBoxTests(SimpleTestCase):
    def test_core_model_serializer_validate_non_partial_branch(self):
        serializer = DummyCoreSerializer()
        with patch.object(DummyModel, "clean", autospec=True) as mock_clean:
            attrs = {"field_a": 1}
            result = serializer.validate(attrs)
        self.assertEqual(result, attrs)
        mock_clean.assert_called_once()

    def test_core_model_serializer_validate_partial_branch(self):
        instance = DummyModel(field_a=1, field_b=2)
        serializer = DummyCoreSerializer(instance=instance, partial=True)

        with patch.object(DummyModel, "clean", autospec=True) as mock_clean:
            result = serializer.validate({"field_b": 99})

        self.assertEqual(result, {"field_b": 99})
        mock_clean.assert_called_once()
        # original instance is unchanged because validate uses a deepcopy
        self.assertEqual(instance.field_b, 2)

    def test_duration_serializer_missing_required_fields_raises(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({})
        self.assertIn("child", exc.exception.detail)
        self.assertIn("start", exc.exception.detail)
        self.assertIn("end", exc.exception.detail)

    def test_duration_serializer_partial_skips_required_field_check(self):
        instance = DummyModel(child="c", start="s", end="e")
        serializer = DummyDurationSerializer(instance=instance, partial=True)
        with patch.object(DummyModel, "clean", autospec=True) as mock_clean:
            result = serializer.validate({})
        self.assertEqual(result, {})
        mock_clean.assert_called_once()

    def test_duration_serializer_timer_without_child_keeps_error_and_does_not_stop(
        self,
    ):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child=None, start="timer-start", stop=MagicMock())
        with patch.object(api_serializers.timezone, "now", return_value="now"):
            with self.assertRaises(ValidationError) as exc:
                serializer.validate({"timer": timer})
        self.assertIn("child", exc.exception.detail)
        timer.stop.assert_not_called()

    def test_duration_serializer_timer_with_child_sets_fields_and_stops_timer(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(
            child="timer-child", start="timer-start", stop=MagicMock()
        )
        with patch.object(api_serializers.timezone, "now", return_value="now"):
            with patch.object(DummyModel, "clean", autospec=True) as mock_clean:
                result = serializer.validate({"timer": timer})

        self.assertEqual(result["child"], "timer-child")
        self.assertEqual(result["start"], "timer-start")
        self.assertEqual(result["end"], "now")
        self.assertNotIn("timer", result)
        timer.stop.assert_called_once()
        mock_clean.assert_called_once()

    def test_duration_serializer_timer_overwrites_direct_values(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(
            child="timer-child", start="timer-start", stop=MagicMock()
        )
        with patch.object(api_serializers.timezone, "now", return_value="now"):
            with patch.object(DummyModel, "clean", autospec=True):
                result = serializer.validate(
                    {
                        "timer": timer,
                        "child": "manual-child",
                        "start": "manual-start",
                        "end": "manual-end",
                    }
                )
        self.assertEqual(result["child"], "timer-child")
        self.assertEqual(result["start"], "timer-start")
        self.assertEqual(result["end"], "now")

    def test_timer_serializer_defaults_user_from_request_when_missing(self):
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )
        with patch.object(
            api_serializers.CoreModelSerializer, "validate", return_value={"name": "x"}
        ):
            result = serializer.validate({"name": "x"})
        self.assertEqual(result["user"], "request-user")

    def test_timer_serializer_defaults_user_from_request_when_none(self):
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )
        with patch.object(
            api_serializers.CoreModelSerializer, "validate", return_value={"user": None}
        ):
            result = serializer.validate({"user": None})
        self.assertEqual(result["user"], "request-user")

    def test_timer_serializer_preserves_explicit_user(self):
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )
        with patch.object(
            api_serializers.CoreModelSerializer,
            "validate",
            return_value={"user": "explicit-user"},
        ):
            result = serializer.validate({"user": "explicit-user"})
        self.assertEqual(result["user"], "explicit-user")

    def test_profile_serializer_get_api_key(self):
        serializer = api_serializers.ProfileSerializer()
        serializer.instance = SimpleNamespace(
            api_key=lambda: SimpleNamespace(key="abc123")
        )
        self.assertEqual(serializer.get_api_key(None), "abc123")


class APIViewsWhiteBoxTests(SimpleTestCase):
    def test_bmi_get_view_name_without_suffix(self):
        view = api_views.BMIViewSet()
        view.suffix = None
        name = view.get_view_name()
        self.assertIn("BMI", name)

    def test_bmi_get_view_name_with_suffix(self):
        view = api_views.BMIViewSet()
        view.suffix = "List"
        name = view.get_view_name()
        self.assertIn("BMI", name)
        self.assertIn("List", name)

    def test_timer_restart_calls_restart_and_returns_serialized_data(self):
        timer = MagicMock()
        timer.restart = MagicMock()

        class DummySerializer:
            def __init__(self, obj):
                self.data = {"id": 1, "name": "timer"}

        view = api_views.TimerViewSet()
        view.get_object = MagicMock(return_value=timer)
        view.serializer_class = DummySerializer

        response = view.restart(request=None, pk=1)
        timer.restart.assert_called_once()
        self.assertEqual(response.data, {"id": 1, "name": "timer"})

    def test_profile_view_get_success(self):
        request = RequestFactory().get("/api/profile/")
        request.user = "user-object"
        settings_obj = object()

        class DummySerializer:
            def __init__(self, obj):
                self.data = {"ok": True, "obj": obj is settings_obj}

        view = api_views.ProfileView()
        view.serializer_class = DummySerializer

        with patch.object(
            api_views, "get_object_or_404", return_value=settings_obj
        ) as mock_get:
            response = view.get(request)

        mock_get.assert_called_once()
        self.assertEqual(response.data, {"ok": True, "obj": True})

    def test_profile_view_get_not_found_branch(self):
        request = RequestFactory().get("/api/profile/")
        request.user = "user-object"
        view = api_views.ProfileView()

        with patch.object(api_views, "get_object_or_404", side_effect=Http404):
            with self.assertRaises(Http404):
                view.get(request)
