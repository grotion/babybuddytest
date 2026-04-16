from django.test import SimpleTestCase

from api import filters
from core import models


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
