######################################################################################################################
# dashboard whitebox test                                                                                            #
#                                                                                                                    #
# Author: Shaun Ku, Samson Cournane                                                                                  #
#                                                                                                                    #
#                                                                                                                    #
# Test result                                                                                                        #
# ------------------------------------------------------------------------------------------------------------------ #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                #
# ------------------------------------------------------------------------------------------------------------------ #
# 2026-04-17 | Initial Test             | 92%  | 41/0      | 465/465  🎉 297 🫥 0  ⏰ 0  🤔 0  🙁 168  🔇 0  🧙 0  #
# ------------------------------------------------------------------------------------------------------------------ #
######################################################################################################################

import datetime as dt
from types import SimpleNamespace

import pytest


class FakeQuerySet:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *args, **kwargs):
        filtered = self.items

        for key, value in kwargs.items():
            if key == "child":
                filtered = [i for i in filtered if getattr(i, "child", None) == value]

            elif key == "start__range":
                start, end = value
                filtered = [i for i in filtered if start <= i.start <= end]

            elif key == "end__range":
                start, end = value
                filtered = [i for i in filtered if start <= i.end <= end]

        return FakeQuerySet(filtered)

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self.items[0] if self.items else None

    def last(self):
        return self.items[-1] if self.items else None

    def count(self):
        return len(self.items)

    def aggregate(self, *args, **kwargs):
        result = {}
        for arg in args:
            text = str(arg)
            if "duration" in text:
                result["duration__sum"] = sum(
                    (getattr(item, "duration", dt.timedelta()) for item in self.items),
                    dt.timedelta(),
                )
            if "naps_count" in text:
                result["naps_count__avg"] = None
        if "duration__sum" not in result:
            result["duration__sum"] = sum(
                (getattr(item, "duration", dt.timedelta()) for item in self.items),
                dt.timedelta(),
            )
        if "naps_count__avg" not in result:
            result["naps_count__avg"] = None
        return result

    def annotate(self, *args, **kwargs):
        return self

    def values(self, *args, **kwargs):
        return self

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def __getitem__(self, item):
        if isinstance(item, slice):
            return self.items[item]
        return self.items[item]

    def __or__(self, other):
        combined = []
        seen = set()
        for obj in list(self.items) + list(other.items):
            marker = id(obj)
            if marker not in seen:
                seen.add(marker)
                combined.append(obj)
        return FakeQuerySet(combined)


class FakeNapAggregateQuerySet(FakeQuerySet):
    def __init__(self, items, naps_avg):
        super().__init__(items)
        self.naps_avg = naps_avg

    def aggregate(self, *args, **kwargs):
        wants_avg = any("naps_count" in str(arg) for arg in args)
        if wants_avg:
            return {"naps_count__avg": self.naps_avg}
        return {
            "duration__sum": sum(
                (getattr(item, "duration", dt.timedelta()) for item in self.items),
                dt.timedelta(),
            )
        }


class FakeManager:
    def __init__(self, mapping=None, default=None):
        self.mapping = mapping or {}
        self.default = default if default is not None else FakeQuerySet([])

    def _pick(self, kwargs):
        for matcher, value in self.mapping.items():
            if matcher(kwargs):
                return value
        return self.default

    def filter(self, *args, **kwargs):
        return self._pick(kwargs)

    def order_by(self, *args, **kwargs):
        return self.default

    def count(self):
        return len(self.default)

    def first(self):
        return self.default.first()

    def all(self):
        return self.default


class FakeAllManager(FakeManager):
    def all(self):
        return self.default



def make_context(*, hide_empty=False, hide_age=None):
    settings = SimpleNamespace(
        dashboard_hide_empty=hide_empty,
        dashboard_hide_age=hide_age,
    )
    user = SimpleNamespace(settings=settings)
    request = SimpleNamespace(user=user)
    return {"request": request}



def aware_datetime(year, month, day, hour=0, minute=0, second=0):
    return dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.timezone.utc)


class TestDashboardViews:
    def test_dashboard_redirects_to_welcome_when_no_children(self, monkeypatch):
        # target file: dashboard/views.py
        # function/method: Dashboard.get
        # branch or behavior tested: child count == 0 redirects to welcome
        from dashboard import views

        monkeypatch.setattr(views.Child, "objects", FakeManager(default=FakeQuerySet([])))
        monkeypatch.setattr(views, "reverse", lambda name, args=None: "/welcome/")
        monkeypatch.setattr(
            views,
            "HttpResponseRedirect",
            lambda url: SimpleNamespace(status_code=302, url=url),
        )

        response = views.Dashboard().get(SimpleNamespace())

        assert response.status_code == 302
        assert response.url == "/welcome/"

    def test_dashboard_redirects_to_child_when_one_child(self, monkeypatch):
        # target file: dashboard/views.py
        # function/method: Dashboard.get
        # branch or behavior tested: child count == 1 redirects using child slug
        from dashboard import views

        child = SimpleNamespace(slug="kid-1")
        monkeypatch.setattr(views.Child, "objects", FakeManager(default=FakeQuerySet([child])))

        captured = {}

        def fake_reverse(name, args=None):
            captured["name"] = name
            captured["args"] = args
            return "/child/"

        monkeypatch.setattr(views, "reverse", fake_reverse)
        monkeypatch.setattr(
            views,
            "HttpResponseRedirect",
            lambda url: SimpleNamespace(status_code=302, url=url),
        )

        response = views.Dashboard().get(SimpleNamespace())

        assert response.status_code == 302
        assert response.url == "/child/"
        assert captured["name"] == "dashboard:dashboard-child"
        assert captured["args"] == {child.slug}

    def test_dashboard_uses_parent_get_when_multiple_children(self, monkeypatch):
        # target file: dashboard/views.py
        # function/method: Dashboard.get
        # branch or behavior tested: child count > 1 falls through to parent get
        from dashboard import views
        from django.views.generic.base import TemplateView

        monkeypatch.setattr(
            views.Child,
            "objects",
            FakeManager(default=FakeQuerySet([SimpleNamespace(), SimpleNamespace()])),
        )

        sentinel = object()
        monkeypatch.setattr(TemplateView, "get", lambda self, request, *args, **kwargs: sentinel)

        result = views.Dashboard().get(SimpleNamespace())

        assert result is sentinel

    def test_dashboard_context_orders_all_children(self, monkeypatch):
        # target file: dashboard/views.py
        # function/method: Dashboard.get_context_data
        # branch or behavior tested: objects added to context from ordered Child queryset
        from dashboard import views
        from django.views.generic.base import TemplateView

        ordered_children = FakeQuerySet([SimpleNamespace(slug="a"), SimpleNamespace(slug="b")])
        monkeypatch.setattr(views.Child, "objects", FakeAllManager(default=ordered_children))
        monkeypatch.setattr(TemplateView, "get_context_data", lambda self, **kwargs: {"base": True})

        context = views.Dashboard().get_context_data()

        assert context["base"] is True
        assert context["objects"] is ordered_children


class TestCardsUtilities:
    def test_hide_empty_reads_user_setting(self):
        # target file: dashboard/templatetags/cards.py
        # function/method: _hide_empty
        # branch or behavior tested: returns dashboard_hide_empty flag directly
        from dashboard.templatetags import cards

        assert cards._hide_empty(make_context(hide_empty=True)) is True
        assert cards._hide_empty(make_context(hide_empty=False)) is False

    def test_filter_data_age_returns_empty_filter_when_setting_disabled(self):
        # target file: dashboard/templatetags/cards.py
        # function/method: _filter_data_age
        # branch or behavior tested: no age filter when dashboard_hide_age is falsy
        from dashboard.templatetags import cards

        result = cards._filter_data_age(make_context(hide_age=None), "time")

        assert result == {}

    def test_filter_data_age_builds_range_when_setting_enabled(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _filter_data_age
        # branch or behavior tested: constructs keyword__range using configured timedelta
        from dashboard.templatetags import cards

        now = aware_datetime(2026, 4, 15, 12, 0, 0)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now)

        result = cards._filter_data_age(make_context(hide_age=dt.timedelta(days=2)), "end")

        assert result == {"end__range": (now - dt.timedelta(days=2), now)}


class TestCardDiaperChangeComponents:
    def test_card_diaperchange_last_returns_empty_when_no_instance(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_diaperchange_last
        # branch or behavior tested: empty result when queryset first() is None
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=FakeQuerySet([])))

        result = cards.card_diaperchange_last(make_context(hide_empty=True), child="child")

        assert result["type"] == "diaperchange"
        assert result["change"] is None
        assert result["empty"] is True
        assert result["hide_empty"] is True

    def test_card_diaperchange_last_returns_instance(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_diaperchange_last
        # branch or behavior tested: populated result when recent change exists
        from dashboard.templatetags import cards

        instance = SimpleNamespace(time=aware_datetime(2026, 4, 15, 8))
        monkeypatch.setattr(
            cards.models.DiaperChange,
            "objects",
            FakeManager(default=FakeQuerySet([instance])),
        )

        result = cards.card_diaperchange_last(make_context(), child="child")

        assert result["change"] is instance
        assert result["empty"] is False

    def test_card_diaperchange_types_counts_wet_solid_and_empty(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_diaperchange_types
        # branch or behavior tested: wet/solid/empty tallies and percentages by day
        from dashboard.templatetags import cards

        max_date = aware_datetime(2026, 4, 16, 0, 0, 0)
        one_day_ago = aware_datetime(2026, 4, 15, 9, 0, 0)
        two_days_ago = aware_datetime(2026, 4, 14, 10, 0, 0)

        items = FakeQuerySet(
            [
                SimpleNamespace(time=one_day_ago, wet=True, solid=False),
                SimpleNamespace(time=one_day_ago, wet=False, solid=True),
                SimpleNamespace(time=two_days_ago, wet=False, solid=False),
            ]
        )

        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: max_date if value is None else value)
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))

        result = cards.card_diaperchange_types(make_context(), child="child", date=dt.date(2026, 4, 15))
        day_0 = result["stats"][0]
        day_1 = result["stats"][1]

        assert day_0["changes"] == 2.0
        assert day_0["wet"] == 1.0
        assert day_0["solid"] == 1.0
        assert day_0["wet_pct"] == 50.0
        assert day_0["solid_pct"] == 50.0

        assert day_1["changes"] == 1.0
        assert day_1["empty"] == 1.0
        assert day_1["empty_pct"] == 100.0

    def test_diaperchange_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _diaperchange_statistics
        # branch or behavior tested: empty queryset returns False
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=FakeQuerySet([])))

        assert cards._diaperchange_statistics("child") is False

    def test_diaperchange_statistics_computes_average_intervals(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _diaperchange_statistics
        # branch or behavior tested: interval accumulation across consecutive changes
        from dashboard.templatetags import cards

        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: base if value is None else value)

        items = FakeQuerySet(
            [
                SimpleNamespace(time=base - dt.timedelta(hours=6)),
                SimpleNamespace(time=base - dt.timedelta(hours=4)),
                SimpleNamespace(time=base - dt.timedelta(hours=1)),
            ]
        )
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))

        stats = cards._diaperchange_statistics("child")

        assert stats is not False
        assert stats[2]["btwn_count"] == 2
        assert stats[2]["btwn_average"] == dt.timedelta(hours=2, minutes=30)


class TestCardBreastfeedingAndFeedingComponents:
    def test_card_breastfeeding_returns_empty_structure_when_no_items(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_breastfeeding
        # branch or behavior tested: empty queryset still returns 7-day stats shell
        from dashboard.templatetags import cards

        now = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now if value is None else value)
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=FakeQuerySet([])))

        result = cards.card_breastfeeding(make_context(), child="child")

        assert result["type"] == "feeding"
        assert result["empty"] is True
        assert result["total"] == 0
        assert len(result["stats"]) == 7

    def test_card_breastfeeding_counts_left_right_and_duration(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_breastfeeding
        # branch or behavior tested: both-breasts increments both sides and percentages
        from dashboard.templatetags import cards

        max_date = aware_datetime(2026, 4, 16, 0, 0, 0)
        start = aware_datetime(2026, 4, 15, 9, 0, 0)
        items = FakeQuerySet(
            [
                SimpleNamespace(
                    start=start,
                    method="left breast",
                    duration=dt.timedelta(minutes=10),
                ),
                SimpleNamespace(
                    start=start,
                    method="both breasts",
                    duration=dt.timedelta(minutes=20),
                ),
            ]
        )

        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: max_date if value is None else value)
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))

        result = cards.card_breastfeeding(make_context(), child="child", date=dt.date(2026, 4, 15))
        day_0 = result["stats"][0]

        assert result["empty"] is False
        assert result["total"] == 2
        assert day_0["count"] == 2
        assert day_0["duration"] == dt.timedelta(minutes=30)
        assert day_0["left_count"] == 2
        assert day_0["right_count"] == 1
        assert day_0["left_pct"] == 66
        assert day_0["right_pct"] == 33

    def test_card_feeding_recent_groups_amounts_by_day_and_handles_none_amount(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_feeding_recent
        # branch or behavior tested: None amount contributes zero and counts still increase
        from dashboard.templatetags import cards

        end_of_day = aware_datetime(2026, 4, 15, 23, 59, 59)
        today_end = aware_datetime(2026, 4, 15, 10)
        yesterday_end = aware_datetime(2026, 4, 14, 11)

        items = FakeQuerySet(
            [
                SimpleNamespace(start=today_end, end=today_end, amount=120),
                SimpleNamespace(start=today_end, end=today_end, amount=None),
                SimpleNamespace(start=yesterday_end, end=yesterday_end, amount=80),
            ]
        )
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: end_of_day if value is None else value)
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))

        result = cards.card_feeding_recent(make_context(), child="child", end_date=end_of_day)

        assert result["empty"] is False
        assert len(result["feedings"]) == 8
        assert result["feedings"][0]["count"] == 2
        assert result["feedings"][0]["total"] == 120
        assert result["feedings"][1]["count"] == 1
        assert result["feedings"][1]["total"] == 80

    def test_card_feeding_last_returns_empty_when_no_recent_instance(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_feeding_last
        # branch or behavior tested: empty result when queryset first() is None
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=FakeQuerySet([])))

        result = cards.card_feeding_last(make_context(), child="child")

        assert result["feeding"] is None
        assert result["empty"] is True

    def test_card_feeding_last_method_marks_empty_when_methods_not_unique(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_feeding_last_method
        # branch or behavior tested: empty when three recent feedings collapse to one unique method
        from dashboard.templatetags import cards

        items = FakeQuerySet(
            [
                SimpleNamespace(method="bottle"),
                SimpleNamespace(method="bottle"),
                SimpleNamespace(method="bottle"),
            ]
        )
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))

        result = cards.card_feeding_last_method(make_context(), child="child")

        assert result["empty"] is True
        assert [feeding.method for feeding in result["feedings"]] == ["bottle", "bottle", "bottle"]

    def test_card_feeding_last_method_reverses_recent_instances(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_feeding_last_method
        # branch or behavior tested: returned order is reversed for carousel behavior
        from dashboard.templatetags import cards

        first = SimpleNamespace(method="left")
        second = SimpleNamespace(method="right")
        third = SimpleNamespace(method="bottle")
        items = FakeQuerySet([first, second, third])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))

        result = cards.card_feeding_last_method(make_context(), child="child")

        assert result["empty"] is False
        assert result["feedings"] == [third, second, first]

    def test_feeding_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _feeding_statistics
        # branch or behavior tested: empty queryset returns False
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=FakeQuerySet([])))

        assert cards._feeding_statistics("child") is False

    def test_feeding_statistics_uses_previous_end_not_previous_start(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _feeding_statistics
        # branch or behavior tested: awake interval is current.start - previous.end
        from dashboard.templatetags import cards

        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: base if value is None else value)

        first = SimpleNamespace(
            start=base - dt.timedelta(hours=5),
            end=base - dt.timedelta(hours=4, minutes=30),
        )
        second = SimpleNamespace(
            start=base - dt.timedelta(hours=2),
            end=base - dt.timedelta(hours=1, minutes=45),
        )
        items = FakeQuerySet([first, second])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))

        stats = cards._feeding_statistics("child")

        assert stats[2]["btwn_count"] == 1
        assert stats[2]["btwn_average"] == dt.timedelta(hours=2, minutes=30)


class TestCardPumpingAndSleepComponents:
    def test_card_pumping_last_returns_empty_when_no_recent_instance(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_pumping_last
        # branch or behavior tested: empty result when queryset first() is None
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.Pumping, "objects", FakeManager(default=FakeQuerySet([])))

        result = cards.card_pumping_last(make_context(), child="child")

        assert result["pumping"] is None
        assert result["empty"] is True

    def test_card_sleep_last_returns_empty_when_no_recent_instance(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_sleep_last
        # branch or behavior tested: empty result when queryset first() is None
        from dashboard.templatetags import cards

        monkeypatch.setattr(
            cards.models.Sleep,
            "objects",
            FakeManager(default=FakeQuerySet([])),
        )

        result = cards.card_sleep_last(make_context(), child="child")

        assert result["type"] == "sleep"
        assert result["sleep"] is None
        assert result["empty"] is True

    def test_card_sleep_recent_splits_cross_midnight_sleep(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_sleep_recent
        # branch or behavior tested: sleep spanning midnight is split across two daily buckets
        from dashboard.templatetags import cards

        end_of_day = aware_datetime(2026, 4, 15, 23, 59, 59)
        start = aware_datetime(2026, 4, 14, 22, 0, 0)
        end = aware_datetime(2026, 4, 15, 6, 0, 0)

        sleep = SimpleNamespace(
            start=start,
            end=end,
            child="child",
        )

        monkeypatch.setattr(
            cards.models.Sleep,
            "objects",
            FakeManager(default=FakeQuerySet([sleep])),
        )
        monkeypatch.setattr(
            cards.timezone,
            "localtime",
            lambda value=None: end_of_day if value is None else value,
        )

        result = cards.card_sleep_recent(make_context(), child="child", end_date=end_of_day)

        assert result["empty"] is False
        assert result["sleeps"][0]["total"] == dt.timedelta(hours=6)
        assert result["sleeps"][0]["count"] == 1
        assert result["sleeps"][1]["total"] == dt.timedelta(hours=2)
        assert result["sleeps"][1]["count"] == 1

    def test_card_sleep_recent_same_day_sleep_stays_in_one_bucket(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_sleep_recent
        # branch or behavior tested: same-day sleep adds full duration to one day only
        from dashboard.templatetags import cards

        end_of_day = aware_datetime(2026, 4, 15, 23, 59, 59)
        sleep = SimpleNamespace(
            start=aware_datetime(2026, 4, 15, 1, 0, 0),
            end=aware_datetime(2026, 4, 15, 3, 30, 0),
            child="child",
        )

        monkeypatch.setattr(
            cards.models.Sleep,
            "objects",
            FakeManager(default=FakeQuerySet([sleep])),
        )
        monkeypatch.setattr(
            cards.timezone,
            "localtime",
            lambda value=None: end_of_day if value is None else value,
        )

        result = cards.card_sleep_recent(make_context(), child="child", end_date=end_of_day)

        assert result["empty"] is False
        assert result["sleeps"][0]["total"] == dt.timedelta(hours=2, minutes=30)
        assert result["sleeps"][0]["count"] == 1

    def test_card_sleep_naps_day_aggregates_duration_and_count(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_sleep_naps_day
        # branch or behavior tested: nap totals come from aggregate and count from queryset length
        from dashboard.templatetags import cards

        nap1 = SimpleNamespace(duration=dt.timedelta(minutes=40))
        nap2 = SimpleNamespace(duration=dt.timedelta(minutes=20))
        naps = FakeQuerySet([nap1, nap2])
        manager = FakeManager(
            mapping={
                lambda kwargs: kwargs.get("nap") is True: naps,
            },
            default=FakeQuerySet([]),
        )
        monkeypatch.setattr(cards.models.Sleep, "objects", manager)

        result = cards.card_sleep_naps_day(make_context(), child="child", date=dt.date(2026, 4, 15))

        assert result["type"] == "sleep"
        assert result["total"] == dt.timedelta(minutes=60)
        assert result["count"] == 2
        assert result["empty"] is False

    def test_sleep_statistics_computes_average_sleep_and_awake_time(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _sleep_statistics
        # branch or behavior tested: total average and between-sleep average are computed separately
        from dashboard.templatetags import cards

        s1 = SimpleNamespace(
            start=aware_datetime(2026, 4, 15, 0, 0, 0),
            end=aware_datetime(2026, 4, 15, 2, 0, 0),
            duration=dt.timedelta(hours=2),
        )
        s2 = SimpleNamespace(
            start=aware_datetime(2026, 4, 15, 5, 0, 0),
            end=aware_datetime(2026, 4, 15, 8, 0, 0),
            duration=dt.timedelta(hours=3),
        )
        sleeps = FakeQuerySet([s1, s2])
        monkeypatch.setattr(cards.models.Sleep, "objects", FakeManager(default=sleeps))

        result = cards._sleep_statistics("child")

        assert result["count"] == 2
        assert result["average"] == dt.timedelta(hours=2, minutes=30)
        assert result["btwn_count"] == 1
        assert result["btwn_average"] == dt.timedelta(hours=3)

    def test_sleep_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _sleep_statistics
        # branch or behavior tested: empty queryset returns False
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.Sleep, "objects", FakeManager(default=FakeQuerySet([])))

        assert cards._sleep_statistics("child") is False


class TestCardStatisticsHelpers:
    def test_nap_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _nap_statistics
        # branch or behavior tested: empty queryset returns False
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.Sleep, "objects", FakeManager(default=FakeQuerySet([])))

        assert cards._nap_statistics("child") is False

    def test_nap_statistics_computes_average_and_average_per_day(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _nap_statistics
        # branch or behavior tested: average duration and aggregated avg_per_day both returned
        from dashboard.templatetags import cards

        naps = FakeNapAggregateQuerySet(
            [
                SimpleNamespace(duration=dt.timedelta(minutes=30)),
                SimpleNamespace(duration=dt.timedelta(minutes=90)),
            ],
            naps_avg=1.5,
        )
        manager = FakeManager(
            mapping={
                lambda kwargs: kwargs.get("nap") is True: naps,
            },
            default=FakeQuerySet([]),
        )
        monkeypatch.setattr(cards.models.Sleep, "objects", manager)

        result = cards._nap_statistics("child")

        assert result["count"] == 2
        assert result["total"] == dt.timedelta(hours=2)
        assert result["average"] == dt.timedelta(hours=1)
        assert result["avg_per_day"] == 1.5

    def test_weight_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _weight_statistics
        # branch or behavior tested: empty queryset returns False
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.Weight, "objects", FakeManager(default=FakeQuerySet([])))

        assert cards._weight_statistics("child") is False

    def test_weight_statistics_computes_weekly_change(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _weight_statistics
        # branch or behavior tested: weekly delta uses newest and oldest entries
        from dashboard.templatetags import cards

        newest = SimpleNamespace(weight=14, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(
            cards.models.Weight,
            "objects",
            FakeManager(default=FakeQuerySet([newest, oldest])),
        )

        result = cards._weight_statistics("child")

        assert result["change_weekly"] == 2.0

    def test_height_statistics_computes_weekly_change(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _height_statistics
        # branch or behavior tested: weekly delta uses newest and oldest entries
        from dashboard.templatetags import cards

        newest = SimpleNamespace(height=60, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=50, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(
            cards.models.Height,
            "objects",
            FakeManager(default=FakeQuerySet([newest, oldest])),
        )

        result = cards._height_statistics("child")

        assert result["change_weekly"] == 5.0

    def test_head_circumference_statistics_computes_weekly_change(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _head_circumference_statistics
        # branch or behavior tested: weekly delta uses newest and oldest entries
        from dashboard.templatetags import cards

        newest = SimpleNamespace(head_circumference=42, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=40, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(
            cards.models.HeadCircumference,
            "objects",
            FakeManager(default=FakeQuerySet([newest, oldest])),
        )

        result = cards._head_circumference_statistics("child")

        assert result["change_weekly"] == 1.0

    def test_bmi_statistics_computes_weekly_change(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: _bmi_statistics
        # branch or behavior tested: weekly delta uses newest and oldest entries
        from dashboard.templatetags import cards

        newest = SimpleNamespace(bmi=18.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=17.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(
            cards.models.BMI,
            "objects",
            FakeManager(default=FakeQuerySet([newest, oldest])),
        )

        result = cards._bmi_statistics("child")

        assert result["change_weekly"] == 0.5

    def test_card_statistics_collects_only_available_stats(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_statistics
        # branch or behavior tested: aggregates helper outputs and skips false helpers
        from dashboard.templatetags import cards

        monkeypatch.setattr(
            cards,
            "_diaperchange_statistics",
            lambda child: [{"btwn_average": dt.timedelta(hours=2), "title": "A"}],
        )
        monkeypatch.setattr(
            cards,
            "_feeding_statistics",
            lambda child: [{"btwn_average": dt.timedelta(hours=3), "title": "B"}],
        )
        monkeypatch.setattr(
            cards,
            "_nap_statistics",
            lambda child: {"average": dt.timedelta(hours=1), "avg_per_day": 2.5},
        )
        monkeypatch.setattr(
            cards,
            "_sleep_statistics",
            lambda child: {"average": dt.timedelta(hours=8), "btwn_average": dt.timedelta(hours=4)},
        )
        monkeypatch.setattr(cards, "_weight_statistics", lambda child: {"change_weekly": 1.2})
        monkeypatch.setattr(cards, "_height_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_head_circumference_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_bmi_statistics", lambda child: {"change_weekly": -0.3})

        result = cards.card_statistics(make_context(hide_empty=True), child="child")

        assert result["empty"] is False
        assert result["hide_empty"] is True
        assert len(result["stats"]) == 8
        titles = {item["title"] for item in result["stats"]}
        assert "A" in titles
        assert "B" in titles
        assert "Average nap duration" in titles
        assert "Average naps per day" in titles
        assert "Average sleep duration" in titles
        assert "Average awake duration" in titles
        assert "Weight change per week" in titles
        assert "BMI change per week" in titles
        assert any(item["stat"] == dt.timedelta(hours=2) for item in result["stats"])
        assert any(item["stat"] == 2.5 for item in result["stats"])
        assert any(item["stat"] == -0.3 for item in result["stats"])

    def test_card_statistics_marks_empty_when_all_helpers_return_false(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_statistics
        # branch or behavior tested: empty when every helper returns False
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards, "_diaperchange_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_feeding_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_nap_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_sleep_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_weight_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_height_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_head_circumference_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_bmi_statistics", lambda child: False)

        result = cards.card_statistics(make_context(), child="child")

        assert result["stats"] == []
        assert result["empty"] is True


class TestTimerAndTummyTimeComponents:
    def test_card_timer_list_without_child_uses_global_ordered_instances(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_timer_list
        # branch or behavior tested: child=None returns all ordered timers
        from dashboard.templatetags import cards

        timer_a = SimpleNamespace(name="a")
        timer_b = SimpleNamespace(name="b")
        monkeypatch.setattr(
            cards.models.Timer,
            "objects",
            FakeManager(default=FakeQuerySet([timer_a, timer_b])),
        )

        result = cards.card_timer_list(make_context(), child=None)

        assert result["type"] == "timer"
        assert result["instances"] == [timer_a, timer_b]
        assert result["empty"] is False

    def test_card_timer_list_with_child_uses_filtered_instances(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_timer_list
        # branch or behavior tested: child-specific branch uses filtered queryset path
        from dashboard.templatetags import cards

        timer = SimpleNamespace(name="filtered")
        manager = FakeManager(default=FakeQuerySet([timer]))
        monkeypatch.setattr(cards.models.Timer, "objects", manager)

        result = cards.card_timer_list(make_context(), child="child")

        assert result["instances"] == [timer]
        assert result["empty"] is False

    def test_card_tummytime_last_returns_empty_when_missing(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_tummytime_last
        # branch or behavior tested: empty result when no tummy-time entry exists
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.TummyTime, "objects", FakeManager(default=FakeQuerySet([])))

        result = cards.card_tummytime_last(make_context(), child="child")

        assert result["tummytime"] is None
        assert result["empty"] is True

    def test_card_tummytime_day_accumulates_seconds_and_returns_last(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_tummytime_day
        # branch or behavior tested: sums duration.seconds and exposes first ordered instance as last
        from dashboard.templatetags import cards

        first = SimpleNamespace(duration=dt.timedelta(seconds=30))
        second = SimpleNamespace(duration=dt.timedelta(minutes=2))
        items = FakeQuerySet([first, second])
        monkeypatch.setattr(cards.models.TummyTime, "objects", FakeManager(default=items))

        result = cards.card_tummytime_day(make_context(), child="child", date=dt.date(2026, 4, 15))

        assert result["empty"] is False
        assert result["stats"]["count"] == 2
        assert result["stats"]["total"] == dt.timedelta(seconds=150)
        assert result["instances"] is items
        assert result["last"] is first

    def test_card_tummytime_day_empty_queryset_returns_zero_total(self, monkeypatch):
        # target file: dashboard/templatetags/cards.py
        # function/method: card_tummytime_day
        # branch or behavior tested: empty day returns zero totals and no last item
        from dashboard.templatetags import cards

        monkeypatch.setattr(cards.models.TummyTime, "objects", FakeManager(default=FakeQuerySet([])))

        result = cards.card_tummytime_day(make_context(), child="child", date=dt.date(2026, 4, 15))

        assert result["empty"] is True
        assert result["stats"]["count"] == 0
        assert result["stats"]["total"] == dt.timedelta(0)
        assert result["last"] is None
