from collections import OrderedDict
from unittest.mock import PropertyMock, patch

from django.http import HttpResponse
from django.test import SimpleTestCase
from django.urls import reverse, resolve

from api import urls


def dummy_view(request):
    return HttpResponse("ok")


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
