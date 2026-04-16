from unittest.mock import patch

from django.test import SimpleTestCase

from api.metadata import APIMetadata


class DummyFiltersetClass:
    class Meta:
        fields = ["child", "date"]


class DummyViewWithFields:
    filterset_fields = ("child", "date")


class DummyViewWithClass:
    filterset_class = DummyFiltersetClass


class DummyPlainView:
    pass


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
