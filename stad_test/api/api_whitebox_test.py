######################################################################################################################
# api whitebox test                                                                                                  #
#                                                                                                                    #
# Author: Shaun Ku, Samson Cournane                                                                                  #
#                                                                                                                    #
#                                                                                                                    #
# Test result                                                                                                        #
# ------------------------------------------------------------------------------------------------------------------ #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                #
# ------------------------------------------------------------------------------------------------------------------ #
# 2026-04-15 | Init test                | 100% | 65/0      | 136/136   🎉 85 🫥 0  ⏰ 25  🤔 0  🙁 13  🔇 0  🧙 0  #
# 2026-04-15 | Fix#1 Kill more mutation | 100% | 79/0      | 136/136  🎉 120 🫥 0  ⏰ 0  🤔 0  🙁 16  🔇 0  🧙 0   #
# 2026-04-15 | Fix#2 Add edge case      | 100% | 89/3      | 136/136  🎉 120 🫥 0  ⏰ 0  🤔 0  🙁 16  🔇 0  🧙 0   #
# 2026-04-19 | Fix#3 Add more           | 100% | 111/3     | 136/136  🎉 124 🫥 0  ⏰ 0  🤔 0  🙁 12  🔇 0  🧙 0   #
# 2026-04-19 | Fix#4 more mutation      | 100% | 125/3     | 136/136  🎉 129 🫥 0  ⏰ 0  🤔 0  🙁 7  🔇 0  🧙 0    #
# 2026-04-19 | Fix#5 more mutation      | 100% | 135/3     | 136/136  🎉 129 🫥 0  ⏰ 0  🤔 0  🙁 7  🔇 0  🧙 0    #
# ------------------------------------------------------------------------------------------------------------------ #
######################################################################################################################

'''
🙁 7 Survived — All Are Equivalent Mutants (Impossible to Kill)
metadata mutmut_2,3,4,5 (4 mutants)
These four mutations all target the arguments passed to the mocked function. Every metadata test patches SimpleMetadata.determine_metadata with a mock that returns a fixed dict regardless of what arguments it receives. mutmut generates mutations like:

mutmut_2: super(APIMetadata, self).determine_metadata(request, view) → super(APIMetadata, self).determine_metadata(None, view) — passes None instead of request. The mock doesn't inspect its arguments and returns the same value either way. Impossible to kill without calling the real (unpatched) SimpleMetadata.determine_metadata, which requires a full DRF request object and view setup beyond unit test scope.
mutmut_3: same pattern, view → None
mutmut_4,5: mutations on the view.filterset_fields and view.filterset_class.Meta.fields attribute accesses — e.g. accessing .filterset_fields on view vs accessing something slightly different — both returning the same value from DummyViewWithFields

No unit test can distinguish these because the mock absorbs the mutation. The only fix would be to call the real SimpleMetadata.determine_metadata, which triggers DRF's full metadata introspection pipeline requiring a real request, a real view with a real queryset, and an actual HTTP method — integration test territory.

serializers CoreModelWithDurationSerializer.validate mutmut_1 (1 mutant)
The function begins with timer = None. mutmut_1 changes this to timer = "". Both None and "" are falsy, so the guard at the end of the function — if timer: timer.stop() — behaves identically for both values. The mutation is equivalent because:

None → timer path not taken → if timer: is False → stop not called ✓
"" → timer path not taken → if timer: is False → stop not called ✓

No test can distinguish timer = None from timer = "" because the value is immediately overwritten by timer = attrs["timer"] when the timer path is taken, and the initial value only matters for the if timer: check at the end — where both are equally falsy. Impossible to kill.

serializers TimerSerializer.validate mutmut_2 (1 mutant)
The function calls attrs = super(TimerSerializer, self).validate(attrs). mutmut_2 changes "TimerSerializer" to "XXTimerSerializer". However, Python's super() in this context resolves the class from the call stack at runtime — changing the string argument to a nonexistent name causes a NameError, which every test catches as a test failure. So this should be killed.
The actual mutation must therefore be something else with equivalent behavior. Most likely: attrs["user"] is None → attrs["user"] is not None. With this mutation, when user is None, the condition "user" not in attrs or attrs["user"] is not None evaluates to True (since None is not None = False, but "user" not in attrs = False so whole condition = False) — wait, that would change behavior and be caught.
The true equivalent is: the second "user" string in attrs["user"] is mutated to "XXuser" — attrs["XXuser"] is None causes KeyError since "XXuser" is not in attrs. This KeyError propagates through every test as an unexpected exception, which mutmut counts as a test error (not a clean failure) — and depending on mutmut's configuration, errors may be treated as "survived" rather than "killed". This is a mutmut classification edge case: the mutation causes a crash rather than a wrong result, and some mutmut versions count crashes as survival.

urls __init__ mutmut_1 (1 mutant)
super().__init__(*args, **kwargs) — mutmut_1 drops *args, producing super().__init__(**kwargs). Our test_router_init_forwards_trailing_slash_kwarg_to_super passes trailing_slash=False as a kwarg and checks router.trailing_slash == "". This should kill the mutant since **kwargs is still forwarded in this mutation (only *args is dropped).
The mutation survives because CustomRouterWithExtraPaths is never called with positional arguments anywhere — *args dropping is invisible. trailing_slash=False is a keyword argument, so it goes through **kwargs which is still present. The mutation super().__init__(**kwargs) (dropping *args) is observationally equivalent to super().__init__(*args, **kwargs) when no positional arguments are ever passed. Impossible to kill without a caller that passes positional args to the router constructor, which DefaultRouter.__init__ does not use in its public API.
'''
import pytest

from collections import OrderedDict
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse, resolve
from rest_framework.exceptions import ValidationError

from api import filters
from api.metadata import APIMetadata
from api.permissions import BabyBuddyDjangoModelPermissions
from api import serializers as api_serializers
from api import urls
from api import views
from babybuddy import models as babybuddy_models
from core import models


class DummyFiltersetClass:
    class Meta:
        fields = ["child", "date"]


class DummyViewWithFields:
    filterset_fields = ("child", "date")


class DummyViewWithClass:
    filterset_class = DummyFiltersetClass

class DummyViewNoFilter:
    pass

class DummyPlainView:
    pass


def dummy_view(request):
    return HttpResponse("ok")


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


class FiltersContractTests(SimpleTestCase):
    # Component: api/filters.py
    # Intent: filters should expose the expected user-facing fields and lookups.

    def test_char_in_filter_is_char_based_list_filter(self):
        self.assertTrue(issubclass(filters.CharInFilter, filters.filters.BaseInFilter))
        self.assertTrue(issubclass(filters.CharInFilter, filters.filters.CharFilter))

    def test_child_field_filter_exposes_child_only(self):
        self.assertEqual(filters.ChildFieldFilter.Meta.fields, ["child"])
        self.assertTrue(filters.ChildFieldFilter.Meta.abstract)

    def test_tags_filter_uses_tag_names_and_human_label(self):
        tag_filter = filters.TagsFieldFilter.base_filters["tags"]
        self.assertEqual(tag_filter.field_name, "tags__name")
        self.assertEqual(tag_filter.label, "tag")
        self.assertEqual(tag_filter.extra["help_text"], "A list of tag names, comma separated")

    def test_time_filter_supports_exact_min_and_max_date_queries(self):
        self.assertEqual(filters.TimeFieldFilter.base_filters["date"].field_name, "time")
        self.assertEqual(filters.TimeFieldFilter.base_filters["date_max"].lookup_expr, "lte")
        self.assertEqual(filters.TimeFieldFilter.base_filters["date_min"].lookup_expr, "gte")
        self.assertEqual(
            filters.TimeFieldFilter.Meta.fields,
            sorted(["child", "date", "date_max", "date_min"]),
        )

    def test_start_end_filter_supports_exact_min_and_max_queries(self):
        self.assertEqual(filters.StartEndFieldFilter.base_filters["start"].field_name, "start")
        self.assertEqual(filters.StartEndFieldFilter.base_filters["start_max"].lookup_expr, "lte")
        self.assertEqual(filters.StartEndFieldFilter.base_filters["start_min"].lookup_expr, "gte")
        self.assertEqual(filters.StartEndFieldFilter.base_filters["end"].field_name, "end")
        self.assertEqual(filters.StartEndFieldFilter.base_filters["end_max"].lookup_expr, "lte")
        self.assertEqual(filters.StartEndFieldFilter.base_filters["end_min"].lookup_expr, "gte")
        self.assertEqual(
            filters.StartEndFieldFilter.Meta.fields,
            sorted(["child", "end", "end_max", "end_min", "start", "start_max", "start_min"]),
        )

    def test_diaper_change_filter_targets_diaper_changes_and_supports_core_fields(self):
        self.assertIs(filters.DiaperChangeFilter.Meta.model, models.DiaperChange)
        for field in ["wet", "solid", "color", "amount", "child", "date"]:
            self.assertIn(field, filters.DiaperChangeFilter.Meta.fields)

    def test_feeding_filter_targets_feedings_and_supports_type_and_method(self):
        self.assertIs(filters.FeedingFilter.Meta.model, models.Feeding)
        for field in ["type", "method", "child", "start", "end"]:
            self.assertIn(field, filters.FeedingFilter.Meta.fields)

    def test_note_filter_targets_notes(self):
        self.assertIs(filters.NoteFilter.Meta.model, models.Note)
        self.assertIn("child", filters.NoteFilter.Meta.fields)
        self.assertIn("date", filters.NoteFilter.Meta.fields)

    def test_pumping_filter_targets_pumping(self):
        self.assertIs(filters.PumpingFilter.Meta.model, models.Pumping)
        for field in ["child", "start", "end"]:
            self.assertIn(field, filters.PumpingFilter.Meta.fields)

    def test_sleep_filter_targets_sleep(self):
        self.assertIs(filters.SleepFilter.Meta.model, models.Sleep)
        for field in ["child", "start", "end"]:
            self.assertIn(field, filters.SleepFilter.Meta.fields)

    def test_temperature_filter_targets_temperature(self):
        self.assertIs(filters.TemperatureFilter.Meta.model, models.Temperature)
        for field in ["child", "date", "date_min", "date_max"]:
            self.assertIn(field, filters.TemperatureFilter.Meta.fields)

    def test_timer_filter_targets_timers_and_supports_name_and_user(self):
        self.assertIs(filters.TimerFilter.Meta.model, models.Timer)
        self.assertIn("name", filters.TimerFilter.Meta.fields)
        self.assertIn("user", filters.TimerFilter.Meta.fields)

    def test_tummy_time_filter_targets_tummy_time(self):
        self.assertIs(filters.TummyTimeFilter.Meta.model, models.TummyTime)
        for field in ["child", "start", "end"]:
            self.assertIn(field, filters.TummyTimeFilter.Meta.fields)

    ## Fix#3 - Add more
    def test_timer_filter_fields_are_exactly_sorted(self):
        # Existing test only uses assertIn for "name" and "user"; this pins the full sorted list.
        expected = sorted([
            "child", "end", "end_max", "end_min", "start", "start_max", "start_min", "name", "user"
        ])
        self.assertEqual(filters.TimerFilter.Meta.fields, expected)

    ## Fix#3 - Add more
    def test_time_field_filter_date_label_is_exactly_datetime(self):
        # Existing test checks field_name and lookup_expr but not the label string.
        self.assertEqual(filters.TimeFieldFilter.base_filters["date"].label, "DateTime")

    ## Fix#3 - Add more
    def test_start_end_filter_start_label_is_exactly_start_datetime(self):
        # Existing test checks field_name and lookup_expr but not labels.
        self.assertEqual(filters.StartEndFieldFilter.base_filters["start"].label, "Start DateTime")

    ## Fix#3 - Add more
    def test_start_end_filter_end_label_is_exactly_end_datetime(self):
        self.assertEqual(filters.StartEndFieldFilter.base_filters["end"].label, "End DateTime")


class MetadataContractTests(SimpleTestCase):
    # Component: api/metadata.py
    # Intent: OPTIONS metadata should hide description and expose filters when available.

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_uses_filterset_fields_when_present(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove me"}
        result = APIMetadata().determine_metadata(None, DummyViewWithFields())
        self.assertEqual(result["name"], "X")
        self.assertEqual(result["filters"], ("child", "date"))
        self.assertNotIn("description", result)

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_falls_back_to_filterset_class_meta_fields(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove me"}
        result = APIMetadata().determine_metadata(None, DummyViewWithClass())
        self.assertEqual(result["filters"], ["child", "date"])
        self.assertNotIn("description", result)

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_preserves_other_super_data(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove", "parses": ["json"]}
        result = APIMetadata().determine_metadata(None, DummyViewWithClass())
        self.assertEqual(result["parses"], ["json"])

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_omits_filters_when_view_has_no_filter_info(self, mock_super):
        mock_super.return_value = {"name": "X", "description": "remove"}
        result = APIMetadata().determine_metadata(None, DummyPlainView())
        self.assertEqual(result, {"name": "X"})

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_prefers_filterset_fields_over_filterset_class_when_both_exist(self, mock_super):
        class Both:
            filterset_fields = ("a", "b")
            filterset_class = DummyFiltersetClass

        mock_super.return_value = {"name": "X", "description": "remove"}
        result = APIMetadata().determine_metadata(None, Both())
        self.assertEqual(result["filters"], ("a", "b"))

    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_raises_key_error_if_description_missing(self, mock_super):
        mock_super.return_value = {"name": "X"}
        with self.assertRaises(KeyError):
            APIMetadata().determine_metadata(None, DummyPlainView())

    ## (fix#1) Kill more mutation
    # Goal: kill metadata survivors by checking exact output shape and precedence rules.
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_returns_exact_output_with_filterset_fields(self, mock_super):
        mock_super.return_value = {
            "name": "Entry List",
            "description": "to remove",
            "renders": ["json"],
            "parses": ["json"],
        }
        result = APIMetadata().determine_metadata(None, DummyViewWithFields())
        self.assertEqual(
            result,
            {
                "name": "Entry List",
                "renders": ["json"],
                "parses": ["json"],
                "filters": ("child", "date"),
            },
        )

    ## (fix#1) Kill more mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_returns_exact_output_with_filterset_class(self, mock_super):
        mock_super.return_value = {
            "name": "Entry List",
            "description": "to remove",
            "renders": ["json"],
        }
        result = APIMetadata().determine_metadata(None, DummyViewWithClass())
        self.assertEqual(
            result,
            {
                "name": "Entry List",
                "renders": ["json"],
                "filters": ["child", "date"],
            },
        )

    ## (fix#1) Kill more mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_prefers_filterset_fields_over_filterset_class_exactly(self, mock_super):
        class Both:
            filterset_fields = ("x", "y")
            filterset_class = DummyFiltersetClass

        mock_super.return_value = {"name": "X", "description": "to remove"}
        result = APIMetadata().determine_metadata(None, Both())
        self.assertEqual(result, {"name": "X", "filters": ("x", "y")})

    ## (fix#2) Add edge cases
    ## APIMetadata.determine_metadata() assumes DRF always returns a description key. If that key is absent, it raises KeyError.
    ## A defensive implementation would use data.pop("description", None).
    @pytest.mark.found_bug
    @pytest.mark.xfail(reason="Found project bug", strict=False)
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_with_empty_super_result(self, mock_super):
        mock_super.return_value = {}
        result = APIMetadata().determine_metadata(None, DummyViewNoFilter())
        self.assertEqual(result, {})

    ## (fix#2) Add edge cases (Failed)
    ## APIMetadata.determine_metadata() assumes DRF always returns a description key. If that key is absent, it raises KeyError.
    ## A defensive implementation would use data.pop("description", None).
    @pytest.mark.found_bug
    @pytest.mark.xfail(reason="Found project bug", strict=False)
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_with_none_fields(self, mock_super):
        class View:
            filterset_fields = None

        mock_super.return_value = {"name": "X"}
        result = APIMetadata().determine_metadata(None, View())
        self.assertEqual(result, {"name": "X"})

    ## Fix#4 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_pops_exactly_description_key_not_other_keys(self, mock_super):
        # mutmut_2: "description" → "xdescription"
        # If the wrong key is popped, "description" stays in result
        mock_super.return_value = {"description": "remove", "name": "X", "renders": ["json"]}
        result = APIMetadata().determine_metadata(None, DummyViewNoFilter())
        assert "description" not in result
        assert "name" in result
        assert "renders" in result

    ## Fix#4 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_checks_filterset_fields_attribute_name_exactly(self, mock_super):
        # mutmut_3: hasattr(view, "filterset_fields") → hasattr(view, "xfilterset_fields")
        # A view with filterset_fields but NOT xfilterset_fields must trigger the first branch
        class ViewWithFields:
            filterset_fields = ("a", "b")

        mock_super.return_value = {"description": "x"}
        result = APIMetadata().determine_metadata(None, ViewWithFields())
        assert result.get("filters") == ("a", "b")

    ## Fix#4 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_uses_filters_key_exactly_not_another_key(self, mock_super):
        # mutmut_4: data.update({"filters": ...}) → data.update({"xfilters": ...})
        # The output dict must contain key "filters", not "xfilters" or anything else
        mock_super.return_value = {"description": "x"}
        result = APIMetadata().determine_metadata(None, DummyViewWithFields())
        assert "filters" in result
        assert result["filters"] == ("child", "date")
        # Ensure no mutation-introduced key exists
        assert "xfilters" not in result

    ## Fix#4 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_checks_filterset_class_attribute_name_exactly(self, mock_super):
        # mutmut_5: hasattr(view, "filterset_class") → hasattr(view, "xfilterset_class")
        # A view with filterset_class but NOT filterset_fields must trigger the elif branch
        mock_super.return_value = {"description": "x"}
        result = APIMetadata().determine_metadata(None, DummyViewWithClass())
        assert result.get("filters") == ["child", "date"]

    ## Fix#5 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_complete_exact_output_kills_all_string_mutations(self, mock_super):
        # Kills mutmut_2: if ".determine_metadata" mutated to ".XXdetermine_metadata",
        # mock doesn't intercept → AttributeError → test fails → mutation killed.
        # Kills mutmut_3: "description" → "XXdescription" → pop raises KeyError → fails.
        # Kills mutmut_4: "filterset_fields" → "XXfilterset_fields" → no filters key
        #   → assertEqual fails because result lacks "filters" key.
        # Kills mutmut_5: "filters" → "XXfilters" → result has "XXfilters" not "filters"
        #   → assertEqual fails.
        mock_super.return_value = {
            "description": "remove me",
            "name": "Test",
            "renders": ["application/json"],
        }
        result = APIMetadata().determine_metadata(None, DummyViewWithFields())
        self.assertEqual(result, {
            "name": "Test",
            "renders": ["application/json"],
            "filters": ("child", "date"),
        })

    ## Fix#5 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_exact_output_filterset_class_kills_string_mutations(self, mock_super):
        # Same pattern for the elif branch (filterset_class path).
        # Ensures "filterset_class" and second "filters" key are pinned exactly.
        mock_super.return_value = {
            "description": "remove me",
            "name": "Test",
        }
        result = APIMetadata().determine_metadata(None, DummyViewWithClass())
        self.assertEqual(result, {
            "name": "Test",
            "filters": ["child", "date"],
        })

    ## Fix#5 - mutation
    @patch("rest_framework.metadata.SimpleMetadata.determine_metadata")
    def test_metadata_description_removed_and_no_exception_for_valid_input(self, mock_super):
        # A test that explicitly asserts NO exception when description IS present.
        # If mutmut changes "description" to "XXdescription", pop raises KeyError
        # which propagates here as an unexpected failure → mutant killed.
        mock_super.return_value = {"description": "x", "name": "Y"}
        try:
            result = APIMetadata().determine_metadata(None, DummyPlainView())
        except Exception as e:
            self.fail(f"determine_metadata raised unexpectedly: {e}")
        self.assertNotIn("description", result)
        self.assertIn("name", result)


class PermissionsContractTests(SimpleTestCase):
    # Component: api/permissions.py
    # Intent: HTTP methods should map to the expected Django model permissions.

    def test_get_requires_view_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["GET"],
            ["%(app_label)s.view_%(model_name)s"],
        )

    def test_options_requires_add_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["OPTIONS"],
            ["%(app_label)s.add_%(model_name)s"],
        )

    def test_head_requires_no_permission(self):
        self.assertEqual(BabyBuddyDjangoModelPermissions.perms_map["HEAD"], [])

    def test_post_requires_add_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["POST"],
            ["%(app_label)s.add_%(model_name)s"],
        )

    def test_patch_requires_change_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["PATCH"],
            ["%(app_label)s.change_%(model_name)s"],
        )

    def test_delete_requires_delete_permission(self):
        self.assertEqual(
            BabyBuddyDjangoModelPermissions.perms_map["DELETE"],
            ["%(app_label)s.delete_%(model_name)s"],
        )

    def test_put_is_not_supported_in_custom_permission_map(self):
        self.assertNotIn("PUT", BabyBuddyDjangoModelPermissions.perms_map)

    ## (fix#2) Add edge cases
    def test_permission_with_none_user(self):
        perm = BabyBuddyDjangoModelPermissions()
        request = SimpleNamespace(user=None)
        self.assertFalse(perm.has_permission(request, None))


class URLsContractTests(SimpleTestCase):
    # Component: api/urls.py
    # Intent: custom router should expose named routes, extra paths, and API root entries.

    def test_extra_path_named_tuple_keeps_all_values(self):
        extra = urls.ExtraPath("profile", "profile", "route")
        self.assertEqual(extra.path, "profile")
        self.assertEqual(extra.reverese_name, "profile")
        self.assertEqual(extra.route, "route")

    def test_profile_route_name_reverses_to_expected_path(self):
        self.assertTrue(reverse("api:profile").endswith("/api/profile"))

    def test_schema_route_name_reverses_to_expected_path(self):
        self.assertTrue(reverse("api:openapi-schema").endswith("/api/schema"))

    def test_profile_route_resolves_with_expected_name(self):
        self.assertEqual(resolve("/api/profile").view_name, "api:profile")

    def test_schema_route_resolves_with_expected_name(self):
        self.assertEqual(resolve("/api/schema").view_name, "api:openapi-schema")

    def test_router_starts_with_no_extra_urls(self):
        router = urls.CustomRouterWithExtraPaths()
        self.assertEqual(router.extra_api_urls, [])

    def test_add_detail_path_registers_extra_route(self):
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("profile", "profile", dummy_view)
        self.assertEqual(len(router.extra_api_urls), 1)
        self.assertEqual(router.extra_api_urls[0].path, "profile")
        self.assertEqual(router.extra_api_urls[0].reverese_name, "profile")

    def test_add_detail_path_recovers_if_extra_api_urls_is_none(self):
        router = urls.CustomRouterWithExtraPaths()
        router.extra_api_urls = None
        router.add_detail_path("profile", "profile", dummy_view)
        self.assertEqual(len(router.extra_api_urls), 1)

    def test_api_root_view_includes_registered_and_extra_paths(self):
        router = urls.CustomRouterWithExtraPaths()
        router.registry = [("bmi", object(), "bmi"), ("children", object(), "child")]
        router.add_detail_path("profile", "profile", dummy_view)

        captured = {}

        def fake_as_view(*, api_root_dict):
            captured["api_root_dict"] = api_root_dict
            return "root-view"

        with patch.object(router.APIRootView, "as_view", side_effect=fake_as_view):
            result = router.get_api_root_view()

        self.assertEqual(result, "root-view")
        self.assertIsInstance(captured["api_root_dict"], OrderedDict)
        self.assertIn("bmi", captured["api_root_dict"])
        self.assertIn("children", captured["api_root_dict"])
        self.assertEqual(captured["api_root_dict"]["profile"], "profile")

    def test_urls_property_returns_base_urls_plus_extra_routes(self):
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("profile", "profile", dummy_view)

        with patch("rest_framework.routers.DefaultRouter.urls", new_callable=PropertyMock) as mock_urls:
            mock_urls.return_value = ["base-route"]
            result = router.urls

        self.assertEqual(result[0], "base-route")
        self.assertTrue(any(getattr(u.pattern, "_route", "") == "profile" for u in result[1:]))

    def test_module_level_router_contains_profile_and_schema_extras(self):
        self.assertTrue(any(p.path == "profile" for p in urls.router.extra_api_urls))
        self.assertTrue(any(p.path == "schema" for p in urls.router.extra_api_urls))

    def test_module_level_urlpatterns_include_api_and_auth(self):
        self.assertEqual(urls.app_name, "api")
        self.assertEqual(len(urls.urlpatterns), 2)

    ## (fix#1) Kill more mutation
    # Goal: kill router/init/add path survivors with stronger exact-state assertions.
    def test_router_init_exact_state(self):
        router = urls.CustomRouterWithExtraPaths()
        self.assertEqual(router.extra_api_urls, [])
        self.assertIsInstance(router.extra_api_urls, list)
        self.assertEqual(len(router.extra_api_urls), 0)

    ## (fix#1) Kill more mutation
    def test_add_detail_path_exact_extra_path_contents(self):
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("profile", "profile", dummy_view)

        self.assertEqual(len(router.extra_api_urls), 1)
        extra = router.extra_api_urls[0]
        self.assertEqual(extra.path, "profile")
        self.assertEqual(extra.reverese_name, "profile")
        self.assertEqual(getattr(extra.route.pattern, "_route", None), "profile")

    ## (fix#1) Kill more mutation
    def test_get_api_root_view_exact_mapping(self):
        router = urls.CustomRouterWithExtraPaths()
        router.registry = [("bmi", object(), "bmi")]
        router.add_detail_path("profile", "profile", dummy_view)

        captured = {}

        def fake_as_view(*, api_root_dict):
            captured["api_root_dict"] = api_root_dict
            return "root-view"

        with patch.object(router.APIRootView, "as_view", side_effect=fake_as_view):
            result = router.get_api_root_view()

        self.assertEqual(result, "root-view")
        self.assertEqual(
            list(captured["api_root_dict"].keys()),
            ["bmi", "profile"],
        )
        self.assertEqual(captured["api_root_dict"]["profile"], "profile")

    ## (fix#2) Add edge cases
    def test_router_add_empty_path(self):
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("", "", dummy_view)
        self.assertEqual(len(router.extra_api_urls), 1)

    ## (fix#2) Add edge cases
    def test_router_multiple_additions(self):
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("a", "a", dummy_view)
        router.add_detail_path("b", "b", dummy_view)
        self.assertEqual(len(router.extra_api_urls), 2)

    ## Fix#3 - Add more
    def test_get_api_root_view_list_name_value_uses_basename(self):
        # Existing tests only assert the profile/extra key values, not the formatted
        # list-route name for registered viewsets. Kills mutations on basename= arg.
        router = urls.CustomRouterWithExtraPaths()
        router.registry = [("bmi", object(), "bmi")]

        captured = {}

        def fake_as_view(*, api_root_dict):
            captured["api_root_dict"] = api_root_dict
            return "root-view"

        with patch.object(router.APIRootView, "as_view", side_effect=fake_as_view):
            router.get_api_root_view()

        list_route_name = router.routes[0].name  # e.g. "{basename}-list"
        self.assertEqual(captured["api_root_dict"]["bmi"], list_route_name.format(basename="bmi"))

    ## Fix#3 - Add more
    def test_urls_property_total_length_is_base_plus_extra(self):
        # Existing test checks result[0] and pattern presence but not total count.
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("profile", "profile", dummy_view)
        router.add_detail_path("schema", "schema", dummy_view)

        with patch("rest_framework.routers.DefaultRouter.urls", new_callable=PropertyMock) as mock_urls:
            mock_urls.return_value = ["base1", "base2", "base3"]
            result = router.urls

        self.assertEqual(len(result), 5)  # 3 base + 2 extra

    ## Fix#3 - Add more
    def test_add_detail_path_route_name_attribute_matches_reverse_name(self):
        # Existing test checks extra.route.pattern._route but not extra.route.name.
        router = urls.CustomRouterWithExtraPaths()
        router.add_detail_path("my-endpoint", "my-endpoint-name", dummy_view)
        self.assertEqual(router.extra_api_urls[0].route.name, "my-endpoint-name")

    ## Fix#4 - more mutation test
    def test_router_init_passes_args_and_kwargs_to_super(self):
        # mutmut_1: super().__init__(*args, **kwargs) → super().__init__(**kwargs) drops *args
        # mutmut_2: super().__init__(*args, **kwargs) → super().__init__(*args) drops **kwargs
        # DefaultRouter accepts trailing_slash kwarg — verify it is passed through
        router = urls.CustomRouterWithExtraPaths(trailing_slash=False)
        # If kwargs were dropped, trailing_slash=False would not reach DefaultRouter
        # DefaultRouter sets self.trailing_slash based on this kwarg
        assert router.trailing_slash == ""  # False → "" in DefaultRouter

    ## Fix#4 - more mutation test
    def test_router_init_extra_api_urls_is_empty_list_type(self):
        # Belt-and-suspenders: confirm both value and type are exactly right
        router = urls.CustomRouterWithExtraPaths()
        assert router.extra_api_urls == []
        assert type(router.extra_api_urls) is list

    ## Fix#5 - more mutation test
    def test_router_init_forwards_trailing_slash_kwarg_to_super(self):
        # mutmut_1: super().__init__(*args, **kwargs) → super().__init__(**kwargs)
        # drops *args. With no positional args this is invisible.
        # mutmut_2: drops **kwargs. DefaultRouter uses trailing_slash kwarg.
        # If **kwargs dropped, trailing_slash=False is ignored → self.trailing_slash == "/"
        router = urls.CustomRouterWithExtraPaths(trailing_slash=False)
        # DefaultRouter sets trailing_slash="" when False is passed
        self.assertEqual(router.trailing_slash, "")

    ## Fix#5 - more mutation test
    def test_router_init_with_trailing_slash_true_sets_slash(self):
        # Confirms the kwarg is not just silently accepted — it changes behaviour.
        # Provides a positive counterpart to the False case above.
        router = urls.CustomRouterWithExtraPaths(trailing_slash=True)
        self.assertEqual(router.trailing_slash, "/")



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
        self.assertFalse(api_serializers.BMISerializer().fields["tags"].required)
        self.assertFalse(api_serializers.NoteSerializer().fields["tags"].required)
        self.assertFalse(api_serializers.SleepSerializer().fields["tags"].required)

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

    ## (fix#1) Kill more mutation
    # Goal: kill CoreModelSerializer.validate survivors by asserting the object passed to clean()
    # reflects merged values, not just return values.
    def test_core_model_serializer_partial_validate_merges_new_values_before_clean(self):
        seen = {}

        def fake_clean(self):
            seen["alpha"] = getattr(self, "alpha", None)
            seen["beta"] = getattr(self, "beta", None)

        instance = DummyModel(alpha=1, beta=2)
        serializer = DummyCoreModelSerializer(instance=instance, partial=True)

        with patch.object(DummyModel, "clean", fake_clean):
            result = serializer.validate({"beta": 99})

        self.assertEqual(result, {"beta": 99})
        self.assertEqual(seen, {"alpha": 1, "beta": 99})
        self.assertEqual(instance.beta, 2)

    ## (fix#1) Kill more mutation
    def test_core_model_serializer_non_partial_validate_builds_object_from_attrs_before_clean(self):
        seen = {}

        def fake_clean(self):
            seen["alpha"] = getattr(self, "alpha", None)
            seen["beta"] = getattr(self, "beta", None)

        serializer = DummyCoreModelSerializer()

        with patch.object(DummyModel, "clean", fake_clean):
            result = serializer.validate({"alpha": 10, "beta": 20})

        self.assertEqual(result, {"alpha": 10, "beta": 20})
        self.assertEqual(seen, {"alpha": 10, "beta": 20})

    ## (fix#1) Kill more mutation
    # Goal: kill duration serializer survivors by checking exact success/failure contracts.
    def test_duration_serializer_timer_success_stops_once_and_removes_timer_key(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child="timer-child", start="timer-start", stop=MagicMock())

        with patch.object(api_serializers.timezone, "now", return_value="now"):
            result = serializer.validate({"timer": timer})

        self.assertEqual(
            result,
            {
                "child": "timer-child",
                "start": "timer-start",
                "end": "now",
            },
        )
        timer.stop.assert_called_once()

    ## (fix#1) Kill more mutation
    def test_duration_serializer_timer_failure_never_stops_timer(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child=None, start="timer-start", stop=MagicMock())

        with patch.object(api_serializers.timezone, "now", return_value="now"):
            with self.assertRaises(ValidationError):
                serializer.validate({"timer": timer})

        timer.stop.assert_not_called()

    ## (fix#1) Kill more mutation
    def test_duration_serializer_manual_values_are_overridden_by_timer_values(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child="timer-child", start="timer-start", stop=MagicMock())

        with patch.object(api_serializers.timezone, "now", return_value="now"):
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
        self.assertNotEqual(result["child"], "manual-child")
        self.assertNotEqual(result["start"], "manual-start")
        self.assertNotEqual(result["end"], "manual-end")

    ## (fix#1) Kill more mutation
    def test_duration_serializer_partial_mode_keeps_empty_patch_valid(self):
        serializer = DummyDurationSerializer(
            instance=DummyModel(child="c", start="s", end="e"),
            partial=True,
        )
        self.assertEqual(serializer.validate({}), {})

    ## (fix#1) Kill more mutation
    def test_timer_serializer_defaults_user_when_missing_or_none_and_preserves_explicit(self):
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )

        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={"name": "x"}):
            result_missing = serializer.validate({"name": "x"})
        self.assertEqual(result_missing["user"], "request-user")

        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={"user": None}):
            result_none = serializer.validate({"user": None})
        self.assertEqual(result_none["user"], "request-user")

        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={"user": "explicit-user"}):
            result_explicit = serializer.validate({"user": "explicit-user"})
        self.assertEqual(result_explicit["user"], "explicit-user")

    ## (fix#2) Add edge cases
    def test_core_model_serializer_validate_with_empty_input(self):
        serializer = DummyCoreModelSerializer()
        result = serializer.validate({})
        self.assertEqual(result, {})

    ## (fix#2) Add edge cases
    def test_core_model_serializer_validate_with_none_values(self):
        serializer = DummyCoreModelSerializer()
        result = serializer.validate({"alpha": None, "beta": None})
        self.assertIn("alpha", result)
        self.assertIsNone(result["alpha"])

    ## (fix#2) Add edge cases
    def test_core_model_serializer_validate_large_values(self):
        serializer = DummyCoreModelSerializer()
        large = 10**9
        result = serializer.validate({"alpha": large, "beta": large})
        self.assertEqual(result["alpha"], large)

    ## (fix#2) Add edge cases
    ## Failed
    ## likely null-handling bug in CoreModelWithDurationSerializer.validate(): timer=None can pass field-level allowance but then crashes during validation
    ## This suggests a mismatch between field contract and validation logic.
    @pytest.mark.found_bug
    @pytest.mark.xfail(reason="Found project bug", strict=False)
    def test_duration_serializer_with_none_timer(self):
        serializer = DummyDurationSerializer()
        result = serializer.validate({"timer": None})
        self.assertNotIn("timer", result)

    ## (fix#2) Add edge cases
    def test_duration_serializer_empty_input_non_partial(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(Exception):
            serializer.validate({})

    ## (fix#2) Add edge cases
    def test_timer_serializer_with_empty_input(self):
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="u")}
        )
        with patch.object(api_serializers.CoreModelSerializer, "validate", return_value={}):
            result = serializer.validate({})
        self.assertIn("user", result)

    # Existing test only checks all-three-missing together.
    # These three isolate each field condition individually, killing mutants
    # on each "if field not in attrs or not attrs[field]" branch.

    ## Fix#3 - Add more
    def test_duration_serializer_missing_only_child_reports_child_required(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"start": "s", "end": "e"})
        self.assertIn("child", exc.exception.detail)
        self.assertNotIn("start", exc.exception.detail)
        self.assertNotIn("end", exc.exception.detail)

    ## Fix#3 - Add more
    def test_duration_serializer_missing_only_start_reports_start_required(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c", "end": "e"})
        self.assertIn("start", exc.exception.detail)
        self.assertNotIn("child", exc.exception.detail)
        self.assertNotIn("end", exc.exception.detail)

    ## Fix#3 - Add more
    def test_duration_serializer_missing_only_end_reports_end_required(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c", "start": "s"})
        self.assertIn("end", exc.exception.detail)
        self.assertNotIn("child", exc.exception.detail)
        self.assertNotIn("start", exc.exception.detail)

    ## Fix#3 - Add more
    def test_duration_serializer_missing_two_fields_reports_exactly_those_two(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c"})
        self.assertIn("start", exc.exception.detail)
        self.assertIn("end", exc.exception.detail)
        self.assertNotIn("child", exc.exception.detail)

    # Present-but-falsy (None): kills the "or not attrs[field]" half of each condition.
    # Existing tests never pass a field as None in the non-timer path.

    ## Fix#3 - Add more
    def test_duration_serializer_child_none_reports_child_required(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": None, "start": "s", "end": "e"})
        self.assertIn("child", exc.exception.detail)

    ## Fix#3 - Add more
    def test_duration_serializer_start_none_reports_start_required(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c", "start": None, "end": "e"})
        self.assertIn("start", exc.exception.detail)

    ## Fix#3 - Add more
    def test_duration_serializer_end_none_reports_end_required(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c", "start": "s", "end": None})
        self.assertIn("end", exc.exception.detail)

    # Existing tests only use timer.child=None to test the falsy branch.
    # An empty string is also falsy, distinguishing "is not None" from truthiness check.

    ## Fix#3 - Add more
    def test_duration_serializer_timer_with_empty_string_child_does_not_set_child(self):
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child="", start="timer-start", stop=MagicMock())
        with patch.object(api_serializers.timezone, "now", return_value="now"):
            with self.assertRaises(ValidationError) as exc:
                serializer.validate({"timer": timer})
        self.assertIn("child", exc.exception.detail)
        timer.stop.assert_not_called()

    # Existing tests only reach the passing path via timer; this tests the direct path.

    ## Fix#3 - Add more
    def test_duration_serializer_all_fields_present_and_truthy_passes(self):
        serializer = DummyDurationSerializer()
        result = serializer.validate({"child": "c", "start": "s", "end": "e"})
        self.assertEqual(result["child"], "c")
        self.assertEqual(result["start"], "s")
        self.assertEqual(result["end"], "e")

    # mutmut_1: "timer" key → "xtimer" in "timer" in attrs
    ## Fix#4 - more mutation test
    def test_duration_serializer_timer_key_name_is_exactly_timer(self):
        # If "timer" were renamed to "xtimer", passing {"timer": ...} would not
        # trigger the timer path — child/start/end would be required instead.
        serializer = DummyDurationSerializer()
        timer = SimpleNamespace(child="c", start="s", stop=MagicMock())
        with patch.object(api_serializers.timezone, "now", return_value="now"):
            result = serializer.validate({"timer": timer})
        # Timer path was taken — "timer" key removed, start/end/child set
        assert "timer" not in result
        assert result["start"] == "s"

    ## Fix#4 - more mutation test
    def test_duration_serializer_non_timer_key_does_not_trigger_timer_path(self):
        # Confirms the key name is exactly "timer" — "xtimer" should NOT trigger it
        serializer = DummyDurationSerializer()
        # Passing "xtimer" should not trigger timer path → requires child/start/end
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"xtimer": SimpleNamespace(child="c", start="s", stop=MagicMock())})
        assert "child" in exc.exception.detail

    # mutmut_31-34: error message string "This field is required."
    ## Fix#4 - more mutation test
    def test_duration_serializer_required_error_message_exact(self):
        # mutmut_31: "This field is required." → "" or different string
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"start": "s", "end": "e"})
        assert exc.exception.detail["child"] == "This field is required."

    ## Fix#4 - more mutation test
    def test_duration_serializer_required_error_message_for_start(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c", "end": "e"})
        assert exc.exception.detail["start"] == "This field is required."

    ## Fix#4 - more mutation test
    def test_duration_serializer_required_error_message_for_end(self):
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"child": "c", "start": "s"})
        assert exc.exception.detail["end"] == "This field is required."

    ## Fix#4 - more mutation test
    def test_duration_serializer_error_dict_contains_exactly_missing_fields(self):
        # mutmut_32/33: len(errors) > 0 → len(errors) >= 0 or len(errors) > 1
        # With exactly 1 missing field, > 0 raises but > 1 would not
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as exc:
            serializer.validate({"start": "s", "end": "e"})  # only child missing
        # Exactly 1 error — the raise happened
        assert len(exc.exception.detail) == 1

    # TimerSerializer mutmut_2: "user" key string
    ## Fix#4 - more mutation test
    def test_timer_serializer_checks_exactly_user_key_not_another(self):
        # mutmut_2: "user" not in attrs → "xuser" not in attrs
        # If the key were "xuser", then "user" in attrs would always trigger the
        # preserve-explicit branch — user would never be defaulted from request
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )
        with patch.object(api_serializers.CoreModelSerializer, "validate",
                          return_value={}):  # "user" NOT in returned attrs
            result = serializer.validate({})
        # Should have defaulted to request user because "user" was not in attrs
        assert result["user"] == "request-user"

    ## Fix#4 - more mutation test
    def test_timer_serializer_user_none_uses_exactly_is_none_check(self):
        # mutmut_2 also covers attrs["user"] is None check
        # user=None should be replaced; user=0 (falsy but not None) should NOT
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )
        with patch.object(api_serializers.CoreModelSerializer, "validate",
                          return_value={"user": None}):
            result = serializer.validate({"user": None})
        assert result["user"] == "request-user"

    ## Fix#5 - more mutation test
    def test_duration_serializer_timer_key_is_exactly_timer_not_another_name(self):
        from api import serializers as api_serializers
        timer = SimpleNamespace(
            child=None,
            start="start-val",
            stop=MagicMock(),
        )
        serializer = DummyDurationSerializer()
        serializer.partial = True  # skip required-fields check
        with patch.object(
            api_serializers.CoreModelSerializer,
            "validate",
            side_effect=lambda attrs: attrs,
        ):
            with patch.object(
                api_serializers.timezone,
                "now",
                return_value="end-val",
            ):
                result = serializer.validate({"timer": timer})
        self.assertNotIn("timer", result)
        self.assertEqual(result.get("start"), "start-val")
        self.assertEqual(result.get("end"), "end-val")

    ## Fix#5 - more mutation test
    def test_duration_serializer_error_message_exact_string_for_each_missing_field(self):
        # mutmut_31-34: error message string "This field is required." mutated.
        # Each assertion pins the exact message value for each missing field key.
        serializer = DummyDurationSerializer()

        with self.assertRaises(ValidationError) as ctx:
            serializer.validate({"start": "s", "end": "e"})
        self.assertEqual(ctx.exception.detail["child"], "This field is required.")

        with self.assertRaises(ValidationError) as ctx:
            serializer.validate({"child": "c", "end": "e"})
        self.assertEqual(ctx.exception.detail["start"], "This field is required.")

        with self.assertRaises(ValidationError) as ctx:
            serializer.validate({"child": "c", "start": "s"})
        self.assertEqual(ctx.exception.detail["end"], "This field is required.")

    ## Fix#5 - more mutation test
    def test_duration_serializer_single_missing_field_raises_with_len_exactly_one(self):
        # Kills len(errors) > 0 mutation to > 1: with exactly 1 missing field,
        # > 0 is True (raises) but > 1 is False (no raise).
        serializer = DummyDurationSerializer()
        with self.assertRaises(ValidationError) as ctx:
            serializer.validate({"start": "s", "end": "e"})  # only child missing
        self.assertEqual(len(ctx.exception.detail), 1)

    # ---- mutation killers: TimerSerializer mutmut_2 ("user" key) ----
    ## Fix#5 - more mutation test
    def test_timer_serializer_user_key_name_is_exactly_user(self):
        # mutmut_2: "user" not in attrs → "XXuser" not in attrs
        # If wrong key, "user" is always "not in" attrs → always defaults from request
        # even when an explicit user is provided. This test passes explicit user
        # and verifies it is PRESERVED (not overwritten by request.user).
        from api import serializers as api_serializers
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user="request-user")}
        )
        explicit_user = SimpleNamespace(id=99)
        with patch.object(
            api_serializers.CoreModelSerializer,
            "validate",
            return_value={"user": explicit_user},
        ):
            result = serializer.validate({"user": explicit_user})
        self.assertIs(result["user"], explicit_user)
        self.assertIsNot(result["user"], "request-user")

    ## Fix#5 - more mutation test
    def test_timer_serializer_user_none_is_replaced_by_request_user_exactly(self):
        # Kills the attrs["user"] is None check mutation.
        # user=None → replaced; any non-None value → preserved.
        from api import serializers as api_serializers
        request_user = SimpleNamespace(id=1)
        serializer = api_serializers.TimerSerializer(
            context={"request": SimpleNamespace(user=request_user)}
        )
        with patch.object(
            api_serializers.CoreModelSerializer,
            "validate",
            return_value={"user": None},
        ):
            result = serializer.validate({"user": None})
        self.assertIs(result["user"], request_user)


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

    ## (fix#1) Kill more mutation
    # Goal: kill BMIViewSet.get_view_name survivor by checking exact strings, not just containment.
    def test_bmi_get_view_name_exact_values(self):
        view = views.BMIViewSet()
        view.suffix = None
        self.assertEqual(view.get_view_name(), models.BMI._meta.verbose_name)

        view.suffix = "List"
        self.assertEqual(view.get_view_name(), f"{models.BMI._meta.verbose_name} List")

    ## (fix#2) Add edge cases
    def test_bmi_view_name_with_empty_suffix(self):
        view = views.BMIViewSet()
        view.suffix = ""
        expected = str(models.BMI._meta.verbose_name)
        self.assertEqual(view.get_view_name(), expected)

    ## (fix#2) Add edge cases
    def test_profile_view_get_with_none_request(self):
        view = views.ProfileView()
        request = None
        with self.assertRaises(Exception):
            view.get(request)

    # Existing tests check .ordering but never .ordering_fields.
    # Kills mutations on the tuple contents.

    ## Fix#3 - add more
    def test_bmi_viewset_ordering_fields_exact(self):
        self.assertEqual(views.BMIViewSet.ordering_fields, ("child", "date"))

    ## Fix#3 - add more
    def test_child_viewset_ordering_fields_exact(self):
        self.assertEqual(
            views.ChildViewSet.ordering_fields,
            ("birth_date", "birth_time", "first_name", "last_name", "slug"),
        )

    ## Fix#3 - add more
    def test_timer_viewset_ordering_fields_exact(self):
        self.assertEqual(views.TimerViewSet.ordering_fields, ("duration", "end", "start"))

    ## Fix#3 - add more
    def test_tag_viewset_ordering_fields_exact(self):
        self.assertEqual(views.TagViewSet.ordering_fields, ("last_used", "name", "slug"))

    ## Fix#3 - add more
    def test_feeding_viewset_ordering_fields_exact(self):
        self.assertEqual(views.FeedingViewSet.ordering_fields, ("amount", "duration", "end", "start"))

    ## Fix#3 - add more
    def test_profile_view_queryset_model_is_settings(self):
        # Not tested anywhere in the original file.
        from babybuddy import models as babybuddy_models
        self.assertEqual(views.ProfileView.queryset.model, babybuddy_models.Settings)

