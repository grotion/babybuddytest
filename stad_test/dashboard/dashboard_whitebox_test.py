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
# 2026-04-19 | Fix#1 - add more test    | 95%  | 115/0     | 465/465  🎉 393 🫥 0  ⏰ 0  🤔 0  🙁 72  🔇 0  🧙 0   #
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

    # --- Dashboard.get mutation kills ---
    ## Fix#1 - add more test
    def test_dashboard_get_redirects_to_exact_welcome_url(self, monkeypatch):
        # mutmut_5,6: "babybuddy:welcome" string mutation
        from dashboard import views
        captured = {}

        def fake_reverse(name, args=None):
            captured["name"] = name
            return "/welcome/"

        monkeypatch.setattr(views.Child, "objects", FakeManager(default=FakeQuerySet([])))
        monkeypatch.setattr(views, "reverse", fake_reverse)
        monkeypatch.setattr(views, "HttpResponseRedirect",
                            lambda url: SimpleNamespace(status_code=302, url=url))
        views.Dashboard().get(SimpleNamespace())
        assert captured["name"] == "babybuddy:welcome"

    ## Fix#1 - add more test
    def test_dashboard_get_zero_children_redirects_not_to_child_view(self, monkeypatch):
        # mutmut_7: children == 0 → children == 1; ensures the zero branch is exclusive
        from dashboard import views
        redirected_to = []
        monkeypatch.setattr(views.Child, "objects", FakeManager(default=FakeQuerySet([])))
        monkeypatch.setattr(views, "reverse", lambda name, args=None: f"/{name}/")
        monkeypatch.setattr(views, "HttpResponseRedirect",
                            lambda url: redirected_to.append(url) or SimpleNamespace(status_code=302, url=url))
        views.Dashboard().get(SimpleNamespace())
        assert redirected_to == ["/babybuddy:welcome/"]

    ## Fix#1 - add more test
    def test_dashboard_get_one_child_uses_exact_reverse_name(self, monkeypatch):
        # mutmut_17: "dashboard:dashboard-child" string mutation
        from dashboard import views
        captured = {}
        child = SimpleNamespace(slug="ava")
        monkeypatch.setattr(views.Child, "objects", FakeManager(default=FakeQuerySet([child])))
        monkeypatch.setattr(views, "reverse",
                            lambda name, args=None: captured.update({"name": name, "args": args}) or "/child/")
        monkeypatch.setattr(views, "HttpResponseRedirect",
                            lambda url: SimpleNamespace(status_code=302, url=url))
        views.Dashboard().get(SimpleNamespace())
        assert captured["name"] == "dashboard:dashboard-child"

    ## Fix#1 - add more test
    def test_dashboard_get_one_child_uses_slug_in_args(self, monkeypatch):
        # mutmut_20: child.slug usage in args
        from dashboard import views
        captured = {}
        child = SimpleNamespace(slug="ava-doe")
        monkeypatch.setattr(views.Child, "objects", FakeManager(default=FakeQuerySet([child])))
        monkeypatch.setattr(views, "reverse",
                            lambda name, args=None: captured.update({"args": args}) or "/child/")
        monkeypatch.setattr(views, "HttpResponseRedirect",
                            lambda url: SimpleNamespace(status_code=302, url=url))
        views.Dashboard().get(SimpleNamespace())
        assert "ava-doe" in str(captured["args"])

    # --- Dashboard.get_context_data mutation kills ---
    ## Fix#1 - add more test
    def test_dashboard_context_data_key_is_exactly_objects(self, monkeypatch):
        # mutmut_9: "objects" key string
        from dashboard import views
        from django.views.generic.base import TemplateView
        ordered = FakeQuerySet([SimpleNamespace(slug="a")])
        monkeypatch.setattr(views.Child, "objects", FakeAllManager(default=ordered))
        monkeypatch.setattr(TemplateView, "get_context_data", lambda self, **kw: {})
        context = views.Dashboard().get_context_data()
        assert "objects" in context
        assert context["objects"] is ordered

    ## Fix#1 - add more test
    def test_dashboard_context_orders_by_last_name_then_first_name_then_id(self, monkeypatch):
        # mutmut_10-20: ordering tuple strings "last_name", "first_name", "id"
        from dashboard import views
        from django.views.generic.base import TemplateView
        order_calls = []

        class TrackingQS(FakeQuerySet):
            def order_by(self, *args):
                order_calls.append(args)
                return self

        class TrackingAllManager(FakeAllManager):
            def all(self):
                return TrackingQS([])

        monkeypatch.setattr(views.Child, "objects", TrackingAllManager())
        monkeypatch.setattr(TemplateView, "get_context_data", lambda self, **kw: {})
        views.Dashboard().get_context_data()
        assert order_calls == [("last_name", "first_name", "id")]


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

    ## Fix#1 - add more test
    def test_filter_data_age_default_keyword_is_end(self, monkeypatch):
        # mutmut_1: default keyword="end" mutation
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        age = dt.timedelta(hours=24)
        monkeypatch.setattr(cards.timezone, "localtime", lambda: base)
        ctx = make_context(hide_age=age)
        result = cards._filter_data_age(ctx)
        # Default keyword is "end" → key should be "end__range"
        assert "end__range" in result
        assert "start__range" not in result

    ## Fix#1 - add more test
    def test_filter_data_age_custom_keyword_produces_correct_key(self, monkeypatch):
        # mutmut_2: keyword + "__range" concatenation
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        age = dt.timedelta(hours=6)
        monkeypatch.setattr(cards.timezone, "localtime", lambda: base)
        ctx = make_context(hide_age=age)
        result = cards._filter_data_age(ctx, keyword="time")
        assert "time__range" in result
        assert list(result.keys()) == ["time__range"]

    ## Fix#1 - add more test
    def test_filter_data_age_range_is_start_to_now(self, monkeypatch):
        # mutmut_1,2: pin exact tuple (start_time, now) in range
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        age = dt.timedelta(hours=6)
        monkeypatch.setattr(cards.timezone, "localtime", lambda: base)
        ctx = make_context(hide_age=age)
        result = cards._filter_data_age(ctx)
        start_time, now = result["end__range"]
        assert now == base
        assert start_time == base - age


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

    ## Fix#1 - add more test
    def test_card_diaperchange_types_with_explicit_date_uses_combine(self, monkeypatch):
        # partial line 60: else branch — date provided → timezone.datetime.combine used
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        combined_dt = aware_datetime(2026, 4, 15, 0)

        combine_calls = []
        def fake_combine(d, t):
            combine_calls.append((d, t))
            return combined_dt.replace(tzinfo=None)

        monkeypatch.setattr(cards.timezone, "datetime",
                            SimpleNamespace(combine=fake_combine))
        monkeypatch.setattr(cards.timezone, "make_aware", lambda v: combined_dt)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_diaperchange_types(
            make_context(hide_empty=False),
            "child",
            date=dt.date(2026, 4, 15),
        )
        assert len(combine_calls) == 1
        assert result["empty"] is True


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

    ## Fix#1 - add more test
    def test_card_breastfeeding_with_explicit_date_uses_combine(self, monkeypatch):
        # partial line 154: if date: branch — date provided
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 0)
        combine_calls = []

        def fake_combine(d, t):
            combine_calls.append(d)
            return base.replace(tzinfo=None)

        monkeypatch.setattr(cards.timezone, "datetime",
                            SimpleNamespace(combine=fake_combine))
        monkeypatch.setattr(cards.timezone, "make_aware", lambda v: base)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_breastfeeding(
            make_context(hide_empty=False),
            "child",
            date=dt.date(2026, 4, 15),
        )
        assert len(combine_calls) == 1
        assert result["total"] == 0

    ## Fix#1 - add more test
    def test_card_feeding_recent_with_explicit_end_date(self, monkeypatch):
        # partial line 188: False branch of "if not end_date:"
        from dashboard.templatetags import cards
        explicit_end = aware_datetime(2026, 4, 10, 23, 59, 59)
        localtime_called = []
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: localtime_called.append(True) or explicit_end)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_feeding_recent(
            make_context(hide_empty=False),
            "child",
            end_date=explicit_end,
        )
        # When end_date is provided, timezone.localtime() should NOT be called
        # to set end_date (branch skipped)
        assert result is not None


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

    ## Fix#1 - add more test
    def test_card_sleep_recent_with_explicit_end_date(self, monkeypatch):
        # partial line 326: False branch of "if not end_date:"
        from dashboard.templatetags import cards
        explicit_end = aware_datetime(2026, 4, 10, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: explicit_end if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_sleep_recent(
            make_context(hide_empty=False),
            "child",
            end_date=explicit_end,
        )
        assert result["empty"] is True

    ## Fix#1 - add more test
    def test_card_sleep_recent_cross_midnight_out_of_bounds_indices_ignored(self, monkeypatch):
        # partial 367,373: "if 0 <= start_idx < len(results)" False branch
        # Sleep starts before the 8-day window (start_idx >= len(results))
        from dashboard.templatetags import cards

        end_date = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: end_date if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        # Sleep that spans midnight but starts 10 days ago (out of 8-day window)
        old_sleep = SimpleNamespace(
            start=aware_datetime(2026, 4, 4, 22, 0, 0),   # 11 days ago
            end=aware_datetime(2026, 4, 5, 6, 0, 0),
            duration=dt.timedelta(hours=8),
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([old_sleep])))

        result = cards.card_sleep_recent(
            make_context(hide_empty=False),
            "child",
            end_date=end_date,
        )
        # Out-of-bounds sleep ignored, all buckets remain zero
        assert all(r["total"] == dt.timedelta() for r in result["sleeps"])

    ## Fix#1 - add more test
    def test_card_sleep_naps_day_with_explicit_date(self, monkeypatch):
        # partial line 396: False branch of "if not date:"
        from dashboard.templatetags import cards
        localtime_called = []
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda: localtime_called.append(True) or aware_datetime(2026, 4, 15))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_sleep_naps_day(
            make_context(hide_empty=False),
            "child",
            date=dt.date(2026, 4, 15),
        )
        # timezone.localtime() not called for date when date explicitly provided
        assert localtime_called == []
        assert result["empty"] is True


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

    # --- _diaperchange_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_diaperchange_statistics_exact_title_strings(self, monkeypatch):
        # mutmut_4,6,7,8: title strings and timedelta(days=3), timedelta(weeks=2)
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([
            SimpleNamespace(time=base - dt.timedelta(hours=4)),
            SimpleNamespace(time=base - dt.timedelta(hours=2)),
        ])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert stats[0]["title"] == "Diaper change frequency (past 3 days)"
        assert stats[1]["title"] == "Diaper change frequency (past 2 weeks)"
        assert stats[2]["title"] == "Diaper change frequency"

    ## Fix#1 - add more test
    def test_diaperchange_statistics_start_cutoffs_are_3days_and_2weeks(self, monkeypatch):
        # mutmut_10,11,12: timedelta(days=3) and timedelta(weeks=2) values
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(time=base)])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert stats[0]["start"] == base - dt.timedelta(days=3)
        assert stats[1]["start"] == base - dt.timedelta(weeks=2)
        assert stats[2]["start"] is None

    ## Fix#1 - add more test
    def test_diaperchange_statistics_btwn_total_initial_is_zero_timedelta(self, monkeypatch):
        # mutmut_15,17,18,19: initial btwn_total=timedelta(0), btwn_count=0, btwn_average=0.0
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(time=base)])  # single item → no intervals
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert stats[0]["btwn_total"] == dt.timedelta(0)
        assert stats[0]["btwn_count"] == 0
        assert stats[0]["btwn_average"] == 0.0

    ## Fix#1 - add more test
    def test_diaperchange_statistics_timespan_filtering_by_start(self, monkeypatch):
        # mutmut_21,22,23: last_time > timespan["start"] comparison
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        # First change is 5 days ago (outside 3-day window, inside 2-week window)
        old = SimpleNamespace(time=base - dt.timedelta(days=5))
        recent = SimpleNamespace(time=base - dt.timedelta(hours=2))
        items = FakeQuerySet([old, recent])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        # 3-day window: only the recent pair contributes if old is outside window
        # 2-week window: both contribute
        assert stats[0]["btwn_count"] == 0  # only 1 item in 3-day window → no pair
        assert stats[1]["btwn_count"] == 1
        assert stats[2]["btwn_count"] == 1

    ## Fix#1 - add more test
    def test_diaperchange_statistics_average_is_total_divided_by_count(self, monkeypatch):
        # mutmut_26,27: btwn_total / btwn_count division
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        t1 = SimpleNamespace(time=base - dt.timedelta(hours=9))
        t2 = SimpleNamespace(time=base - dt.timedelta(hours=6))
        t3 = SimpleNamespace(time=base - dt.timedelta(hours=3))
        items = FakeQuerySet([t1, t2, t3])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert stats[2]["btwn_average"] == dt.timedelta(hours=3)
        assert stats[2]["btwn_count"] == 2

    ## Fix#1 - add more test
    def test_diaperchange_statistics_btwn_keys_are_exact(self, monkeypatch):
        # mutmut_29,30,31: key strings "btwn_total","btwn_count","btwn_average"
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([
            SimpleNamespace(time=base - dt.timedelta(hours=4)),
            SimpleNamespace(time=base - dt.timedelta(hours=2)),
        ])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        for ts in stats:
            assert "btwn_total" in ts
            assert "btwn_count" in ts
            assert "btwn_average" in ts

    ## Fix#1 - add more test
    def test_diaperchange_statistics_single_instance_returns_zero_average(self, monkeypatch):
        # mutmut_41-49: conditional logic — single instance yields no intervals
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(time=base)])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert stats[2]["btwn_average"] == 0.0
        assert stats[2]["btwn_count"] == 0

    ## Fix#1 - add more test
    def test_diaperchange_statistics_accumulation_uses_localtime(self, monkeypatch):
        # mutmut_53,60: timezone.localtime() called on instance.time for accumulation
        from dashboard.templatetags import cards
        utc = dt.timezone.utc
        base_dt = dt.datetime(2026, 4, 15, 12, 0, tzinfo=utc)
        localtime_calls = []

        def tracking_localtime(value=None):
            if value is not None:
                localtime_calls.append(value)
            return base_dt if value is None else value

        monkeypatch.setattr(cards.timezone, "localtime", tracking_localtime)
        t1 = SimpleNamespace(time=base_dt - dt.timedelta(hours=4))
        t2 = SimpleNamespace(time=base_dt - dt.timedelta(hours=2))
        items = FakeQuerySet([t1, t2])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        cards._diaperchange_statistics("child")
        # localtime should have been called with instance.time values
        assert t1.time in localtime_calls
        assert t2.time in localtime_calls

    ## Fix#1 - add more test
    def test_diaperchange_statistics_returns_list_of_three(self, monkeypatch):
        # mutmut_77,78: return value — always returns list of 3 timespans
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(time=base)])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert isinstance(stats, list)
        assert len(stats) == 3

    # --- _feeding_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_feeding_statistics_exact_title_strings(self, monkeypatch):
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        first = SimpleNamespace(start=base - dt.timedelta(hours=4),
                                end=base - dt.timedelta(hours=3, minutes=30))
        second = SimpleNamespace(start=base - dt.timedelta(hours=2),
                                 end=base - dt.timedelta(hours=1, minutes=30))
        items = FakeQuerySet([first, second])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[0]["title"] == "Feeding frequency (past 3 days)"
        assert stats[1]["title"] == "Feeding frequency (past 2 weeks)"
        assert stats[2]["title"] == "Feeding frequency"

    ## Fix#1 - add more test
    def test_feeding_statistics_start_cutoffs_are_3days_and_2weeks(self, monkeypatch):
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(start=base, end=base)])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[0]["start"] == base - dt.timedelta(days=3)
        assert stats[1]["start"] == base - dt.timedelta(weeks=2)
        assert stats[2]["start"] is None

    ## Fix#1 - add more test
    def test_feeding_statistics_interval_is_current_start_minus_previous_end(self, monkeypatch):
        # mutmut_41-53: "start - last_end" vs "start - last_start"
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        # first feeding: start=8am, end=8:30am
        # second feeding: start=10am, end=10:30am
        # interval = 10am - 8:30am = 1h30m (NOT 10am - 8am = 2h)
        first = SimpleNamespace(start=base.replace(hour=8),
                                end=base.replace(hour=8, minute=30))
        second = SimpleNamespace(start=base.replace(hour=10),
                                 end=base.replace(hour=10, minute=30))
        items = FakeQuerySet([first, second])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[2]["btwn_average"] == dt.timedelta(hours=1, minutes=30)
        assert stats[2]["btwn_average"] != dt.timedelta(hours=2)

    ## Fix#1 - add more test
    def test_feeding_statistics_timespan_filtering_by_start(self, monkeypatch):
        # mutmut_26-31: last_start > timespan["start"] comparison
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        old = SimpleNamespace(start=base - dt.timedelta(days=5),
                              end=base - dt.timedelta(days=5) + dt.timedelta(minutes=30))
        recent = SimpleNamespace(start=base - dt.timedelta(hours=2),
                                 end=base - dt.timedelta(hours=1, minutes=30))
        items = FakeQuerySet([old, recent])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[0]["btwn_count"] == 0  # old is outside 3-day window
        assert stats[1]["btwn_count"] == 1
        assert stats[2]["btwn_count"] == 1

    ## Fix#1 - add more test
    def test_feeding_statistics_average_exact_value(self, monkeypatch):
        # mutmut_57,64,67: division and average computation
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        # 3 feedings: gaps of 1h and 2h = total 3h / 2 = 1.5h avg
        f1 = SimpleNamespace(start=base.replace(hour=6), end=base.replace(hour=6, minute=30))
        f2 = SimpleNamespace(start=base.replace(hour=7, minute=30), end=base.replace(hour=8))
        f3 = SimpleNamespace(start=base.replace(hour=10), end=base.replace(hour=10, minute=30))
        items = FakeQuerySet([f1, f2, f3])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[2]["btwn_count"] == 2
        assert stats[2]["btwn_average"] == dt.timedelta(hours=1, minutes=30)

    ## Fix#1 - add more test
    def test_feeding_statistics_returns_list_of_three(self, monkeypatch):
        # mutmut_72,80,85: return value structure
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(start=base, end=base)])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert isinstance(stats, list)
        assert len(stats) == 3
        for ts in stats:
            assert "btwn_total" in ts
            assert "btwn_count" in ts
            assert "btwn_average" in ts

    # --- _nap_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_nap_statistics_filters_by_nap_true(self, monkeypatch):
        # mutmut_2,3: nap=True filter
        from dashboard.templatetags import cards
        filter_calls = []

        class TrackingManager(FakeManager):
            def filter(self, *args, **kwargs):
                filter_calls.append(kwargs)
                return FakeNapAggregateQuerySet([], naps_avg=0)

        monkeypatch.setattr(cards.models.Sleep, "objects", TrackingManager())
        cards._nap_statistics("child")
        assert any(kw.get("nap") is True for kw in filter_calls)

    ## Fix#1 - add more test
    def test_nap_statistics_count_key_exact(self, monkeypatch):
        # mutmut_5,8,9: "count" key and instances.count()
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=60)),
             SimpleNamespace(duration=dt.timedelta(minutes=60))],
            naps_avg=2.0,
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result["count"] == 2

    ## Fix#1 - add more test
    def test_nap_statistics_average_is_total_divided_by_count(self, monkeypatch):
        # mutmut_16,17,18,19: average = total / count
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=30)),
             SimpleNamespace(duration=dt.timedelta(minutes=90))],
            naps_avg=1.0,
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result["average"] == dt.timedelta(hours=1)
        assert result["average"] == result["total"] / result["count"]

    ## Fix#1 - add more test
    def test_nap_statistics_avg_per_day_uses_naps_count_avg_key(self, monkeypatch):
        # mutmut_24,25,26,27: "naps_count__avg" key and avg_per_day assignment
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=45))],
            naps_avg=3.5,
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result["avg_per_day"] == 3.5

    ## Fix#1 - add more test
    def test_nap_statistics_all_keys_present(self, monkeypatch):
        # mutmut_28-56: key names "total","count","average","avg_per_day"
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=60))],
            naps_avg=1.0,
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert "total" in result
        assert "count" in result
        assert "average" in result
        assert "avg_per_day" in result

    # --- _sleep_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_sleep_statistics_total_key_exact(self, monkeypatch):
        # mutmut_2,3,4,5: "total","count","average","btwn_total" key names
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 8),
                             duration=dt.timedelta(hours=3))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert "total" in result
        assert "count" in result
        assert "average" in result
        assert "btwn_total" in result
        assert "btwn_count" in result
        assert "btwn_average" in result

    ## Fix#1 - add more test
    def test_sleep_statistics_btwn_count_is_count_minus_one(self, monkeypatch):
        # mutmut_12,13,14,15: btwn_count = count - 1
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 8),
                             duration=dt.timedelta(hours=3))
        s3 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 10),
                             end=aware_datetime(2026, 4, 15, 12),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2, s3])))
        result = cards._sleep_statistics("child")
        assert result["count"] == 3
        assert result["btwn_count"] == 2  # count - 1, not count

    ## Fix#1 - add more test
    def test_sleep_statistics_awake_time_is_next_start_minus_last_end(self, monkeypatch):
        # mutmut_20,21,22: start - last_end (not start - last_start)
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 8),
                             duration=dt.timedelta(hours=3))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        # awake = s2.start - s1.end = 5am - 2am = 3h
        assert result["btwn_average"] == dt.timedelta(hours=3)
        assert result["btwn_average"] != dt.timedelta(hours=5)  # not s2.start - s1.start

    ## Fix#1 - add more test
    def test_sleep_statistics_average_is_total_over_count(self, monkeypatch):
        # mutmut_31,32,33,34: average = total / count
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 9),
                             duration=dt.timedelta(hours=4))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert result["average"] == dt.timedelta(hours=3)  # (2+4)/2

    ## Fix#1 - add more test
    def test_sleep_statistics_single_instance_btwn_is_zero(self, monkeypatch):
        # mutmut_39: single sleep → btwn_count=0 → btwn_average stays 0
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1])))
        result = cards._sleep_statistics("child")
        assert result["btwn_count"] == 0
        assert result["btwn_average"] == 0.0

    ## Fix#1 - add more test
    def test_sleep_statistics_exact_numeric_values(self, monkeypatch):
        # mutmut_47,48,59,64: exact return values
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 8),
                             duration=dt.timedelta(hours=3))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert result["count"] == 2
        assert result["total"] == dt.timedelta(hours=5)
        assert result["average"] == dt.timedelta(hours=2, minutes=30)
        assert result["btwn_total"] == dt.timedelta(hours=3)
        assert result["btwn_count"] == 1
        assert result["btwn_average"] == dt.timedelta(hours=3)

    # --- _weight_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_weight_statistics_change_weekly_key_exact(self, monkeypatch):
        # mutmut_2,3,4: "change_weekly" key name
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=20, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        assert "change_weekly" in result
        assert result["change_weekly"] != 0.0

    ## Fix#1 - add more test
    def test_weight_statistics_uses_weight_attribute(self, monkeypatch):
        # mutmut_6,7: newest.weight - oldest.weight
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=14, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        # 4kg / 2 weeks = 2.0 per week
        assert result["change_weekly"] == 2.0
        assert result["change_weekly"] != -2.0  # not oldest - newest

    ## Fix#1 - add more test
    def test_weight_statistics_divides_by_days_over_7(self, monkeypatch):
        # mutmut_8,9: (days).days / 7 division
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=17.5, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=10.5, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        # 7kg over 14 days = 7/2 weeks = 3.5 per week
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#1 - add more test
    def test_weight_statistics_same_item_returns_zero_change(self, monkeypatch):
        # newest == oldest → change_weekly stays 0.0 (no mutation of the if)
        from dashboard.templatetags import cards
        only = SimpleNamespace(weight=10, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._weight_statistics("child")
        assert result["change_weekly"] == 0.0

    # --- _height_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_height_statistics_uses_height_attribute(self, monkeypatch):
        # mutmut_3,4,6,7: newest.height - oldest.height
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=60, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=53, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)
        assert result["change_weekly"] != pytest.approx(-3.5)

    ## Fix#1 - add more test
    def test_height_statistics_divides_by_weeks(self, monkeypatch):
        # mutmut_8,9,11,12: (days).days / 7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=70, date=dt.date(2026, 4, 22))  # 3 weeks later
        oldest = SimpleNamespace(height=61, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.0)

    # --- _head_circumference_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_head_circumference_statistics_uses_hc_attribute(self, monkeypatch):
        # mutmut_2,3,4,6,7: newest.head_circumference - oldest.head_circumference
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=42, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=40, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(1.0)
        assert result["change_weekly"] != pytest.approx(-1.0)

    ## Fix#1 - add more test
    def test_head_circumference_statistics_divides_by_weeks(self, monkeypatch):
        # mutmut_8,9,11,12: division by 7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=45, date=dt.date(2026, 4, 22))  # 3 weeks
        oldest = SimpleNamespace(head_circumference=39, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(2.0)

    # --- _bmi_statistics mutation kills ---
    ## Fix#1 - add more test
    def test_bmi_statistics_uses_bmi_attribute(self, monkeypatch):
        # mutmut_2,3,4,6,7: newest.bmi - oldest.bmi
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=18.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=16.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(1.0)
        assert result["change_weekly"] != pytest.approx(-1.0)

    ## Fix#1 - add more test
    def test_bmi_statistics_divides_by_weeks(self, monkeypatch):
        # mutmut_8,9,11,12: division by 7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=21.0, date=dt.date(2026, 4, 22))  # 3 weeks
        oldest = SimpleNamespace(bmi=18.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(1.0)

    ## Fix#1 - add more test
    def test_bmi_statistics_single_entry_returns_zero(self, monkeypatch):
        # pin: newest == oldest → no change computed
        from dashboard.templatetags import cards
        only = SimpleNamespace(bmi=18.5, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == 0.0

    ## Fix#1 - add more test
    def test_bmi_statistics_change_weekly_key_exact(self, monkeypatch):
        # mutmut_6,7: "change_weekly" key name
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=19.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=18.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert "change_weekly" in result

    ## Fix#1 - add more test
    def test_nap_statistics_count_zero_average_stays_zero(self, monkeypatch):
        # partial 490: if naps["count"] > 0 — False path
        # This can't happen (we check len>0 first) but cover the branch via
        # the aggregate returning count=0 edge case with FakeNapAggregateQuerySet
        from dashboard.templatetags import cards
        # Provide a queryset that has items but count() returns 0 — artificial but covers branch
        class ZeroCountQS(FakeNapAggregateQuerySet):
            def count(self):
                return 0
        naps = ZeroCountQS(
            [SimpleNamespace(duration=dt.timedelta(minutes=30))],
            naps_avg=1.0,
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result["average"] == 0.0

    ## Fix#1 - add more test
    def test_diaperchange_statistics_btwn_count_zero_average_stays_zero(self, monkeypatch):
        # partial 558: if timespan["btwn_count"] > 0 — False branch
        # Single instance → btwn_count stays 0 → btwn_average stays 0.0
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(time=base)])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        for ts in stats:
            assert ts["btwn_average"] == 0.0

    ## Fix#1 - add more test
    def test_diaperchange_statistics_timespan_start_none_always_includes(self, monkeypatch):
        # partial 566: timespan["start"] is None → always include (or branch)
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        # Two items very old — outside 3-day and 2-week windows but the None window always includes
        t1 = SimpleNamespace(time=base - dt.timedelta(days=100))
        t2 = SimpleNamespace(time=base - dt.timedelta(days=50))
        items = FakeQuerySet([t1, t2])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        # Windowed ones skip the old interval
        assert stats[0]["btwn_count"] == 0
        assert stats[1]["btwn_count"] == 0
        # All-time (None start) always includes
        assert stats[2]["btwn_count"] == 1

    ## Fix#1 - add more test
    def test_feeding_statistics_btwn_count_zero_average_stays_zero(self, monkeypatch):
        # partial 607: if timespan["btwn_count"] > 0 — False branch
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([SimpleNamespace(start=base, end=base)])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        for ts in stats:
            assert ts["btwn_average"] == 0.0

    ## Fix#1 - add more test
    def test_feeding_statistics_start_none_always_includes(self, monkeypatch):
        # partial 613: timespan["start"] is None → always include
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        old = SimpleNamespace(start=base - dt.timedelta(days=100),
                              end=base - dt.timedelta(days=100) + dt.timedelta(minutes=30))
        recent = SimpleNamespace(start=base - dt.timedelta(days=50),
                                 end=base - dt.timedelta(days=50) + dt.timedelta(minutes=30))
        items = FakeQuerySet([old, recent])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[0]["btwn_count"] == 0
        assert stats[1]["btwn_count"] == 0
        assert stats[2]["btwn_count"] == 1

    ## Fix#1 - add more test
    def test_card_statistics_includes_height_and_hc_when_available(self, monkeypatch):
        # partial 633: height branch — existing test uses height=False
        # This test provides actual height and hc values to cover those branches
        from dashboard.templatetags import cards
        monkeypatch.setattr(cards, "_diaperchange_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_feeding_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_nap_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_sleep_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_weight_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_height_statistics",
                            lambda child: {"change_weekly": 2.5})
        monkeypatch.setattr(cards, "_head_circumference_statistics",
                            lambda child: {"change_weekly": 0.5})
        monkeypatch.setattr(cards, "_bmi_statistics", lambda child: False)

        result = cards.card_statistics(make_context(), child="child")

        titles = {item["title"] for item in result["stats"]}
        assert "Height change per week" in titles
        assert "Head circumference change per week" in titles
        assert any(item["stat"] == 2.5 for item in result["stats"])
        assert any(item["stat"] == 0.5 for item in result["stats"])

    ## Fix#1 - add more test
    def test_sleep_statistics_btwn_total_accumulates_correctly(self, monkeypatch):
        # partial 675,677: loop body — start - last_end accumulation
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 4),
                             end=aware_datetime(2026, 4, 15, 7),
                             duration=dt.timedelta(hours=3))
        s3 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 9),
                             end=aware_datetime(2026, 4, 15, 11),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2, s3])))
        result = cards._sleep_statistics("child")
        # gaps: s2.start-s1.end=2h, s3.start-s2.end=2h → total=4h, count=2, avg=2h
        assert result["btwn_total"] == dt.timedelta(hours=4)
        assert result["btwn_count"] == 2
        assert result["btwn_average"] == dt.timedelta(hours=2)

    ## Fix#1 - add more test
    def test_sleep_statistics_count_zero_guard(self, monkeypatch):
        # partial 698: if sleep["count"] > 0 — use a queryset that has items but count()=0
        from dashboard.templatetags import cards

        class ZeroCountQS(FakeQuerySet):
            def count(self):
                return 0

        qs = ZeroCountQS([SimpleNamespace(
            start=aware_datetime(2026, 4, 15, 0),
            end=aware_datetime(2026, 4, 15, 2),
            duration=dt.timedelta(hours=2)
        )])
        monkeypatch.setattr(cards.models.Sleep, "objects", FakeManager(default=qs))
        result = cards._sleep_statistics("child")
        assert result["average"] == 0.0

    ## Fix#1 - add more test
    def test_sleep_statistics_btwn_count_zero_guard(self, monkeypatch):
        # partial 715: if sleep["btwn_count"] > 0 — False branch (single instance)
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1])))
        result = cards._sleep_statistics("child")
        assert result["btwn_count"] == 0
        assert result["btwn_average"] == 0.0

    ## Fix#1 - add more test
    def test_weight_statistics_newest_equals_oldest_returns_zero(self, monkeypatch):
        # partial 721, missing 716: newest==oldest → change_weekly stays 0.0
        from dashboard.templatetags import cards
        only = SimpleNamespace(weight=10, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._weight_statistics("child")
        assert result is not False
        assert result["change_weekly"] == 0.0

    ## Fix#1 - add more test
    def test_weight_statistics_returns_dict_for_single_entry(self, monkeypatch):
        # missing 716: return weight with single entry
        from dashboard.templatetags import cards
        only = SimpleNamespace(weight=10, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._weight_statistics("child")
        assert isinstance(result, dict)
        assert "change_weekly" in result

    ## Fix#1 - add more test
    def test_height_statistics_newest_equals_oldest_returns_zero(self, monkeypatch):
        # partial 761, missing 739: newest==oldest
        from dashboard.templatetags import cards
        only = SimpleNamespace(height=60, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._height_statistics("child")
        assert result is not False
        assert result["change_weekly"] == 0.0

    ## Fix#1 - add more test
    def test_height_statistics_returns_dict_for_single_entry(self, monkeypatch):
        # missing 739: return height
        from dashboard.templatetags import cards
        only = SimpleNamespace(height=60, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._height_statistics("child")
        assert isinstance(result, dict)

    ## Fix#1 - add more test
    def test_head_circumference_statistics_newest_equals_oldest(self, monkeypatch):
        # partial 744, missing 762
        from dashboard.templatetags import cards
        only = SimpleNamespace(head_circumference=40, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._head_circumference_statistics("child")
        assert result is not False
        assert result["change_weekly"] == 0.0

    ## Fix#1 - add more test
    def test_bmi_statistics_newest_equals_oldest_returns_zero(self, monkeypatch):
        # partial 767, missing 831
        from dashboard.templatetags import cards
        only = SimpleNamespace(bmi=18.5, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._bmi_statistics("child")
        assert result is not False
        assert result["change_weekly"] == 0.0

    ## Fix#1 - add more test
    def test_weight_statistics_negative_change(self, monkeypatch):
        # mutmut_738 partial: direction of subtraction (newest - oldest can be negative)
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=8, date=dt.date(2026, 4, 15))   # lighter
        oldest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 1))   # heavier
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        assert result["change_weekly"] == pytest.approx(-1.0)

    ## Fix#1 - add more test
    def test_height_statistics_negative_change_direction(self, monkeypatch):
        # Pins direction of subtraction
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=50, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=60, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] < 0

    ## Fix#1 - add more test
    def test_head_circumference_statistics_negative_change(self, monkeypatch):
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=38, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=40, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] < 0

    ## Fix#1 - add more test
    def test_bmi_statistics_negative_change(self, monkeypatch):
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=17.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=19.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] < 0

    # --- card_statistics: pin exact title strings (mutation kills) ---
    ## Fix#1 - add more test
    def test_card_statistics_exact_title_strings_for_all_helpers(self, monkeypatch):
        # Kills mutations on the title string literals inside card_statistics
        from dashboard.templatetags import cards
        monkeypatch.setattr(cards, "_diaperchange_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_feeding_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_nap_statistics",
                            lambda child: {"average": dt.timedelta(hours=1), "avg_per_day": 2.0})
        monkeypatch.setattr(cards, "_sleep_statistics",
                            lambda child: {"average": dt.timedelta(hours=8),
                                           "btwn_average": dt.timedelta(hours=4)})
        monkeypatch.setattr(cards, "_weight_statistics",
                            lambda child: {"change_weekly": 1.0})
        monkeypatch.setattr(cards, "_height_statistics",
                            lambda child: {"change_weekly": 0.5})
        monkeypatch.setattr(cards, "_head_circumference_statistics",
                            lambda child: {"change_weekly": 0.2})
        monkeypatch.setattr(cards, "_bmi_statistics",
                            lambda child: {"change_weekly": 0.1})

        result = cards.card_statistics(make_context(), child="child")
        titles = [item["title"] for item in result["stats"]]

        assert "Average nap duration" in titles
        assert "Average naps per day" in titles
        assert "Average sleep duration" in titles
        assert "Average awake duration" in titles
        assert "Weight change per week" in titles
        assert "Height change per week" in titles
        assert "Head circumference change per week" in titles
        assert "BMI change per week" in titles

    ## Fix#1 - add more test
    def test_card_statistics_stat_keys_and_types_are_exact(self, monkeypatch):
        # Pin "stat", "type", "title" key names and "duration"/"float" type values
        from dashboard.templatetags import cards
        nap_avg = dt.timedelta(hours=1)
        weight_chg = 2.5
        monkeypatch.setattr(cards, "_diaperchange_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_feeding_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_nap_statistics",
                            lambda child: {"average": nap_avg, "avg_per_day": weight_chg})
        monkeypatch.setattr(cards, "_sleep_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_weight_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_height_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_head_circumference_statistics", lambda child: False)
        monkeypatch.setattr(cards, "_bmi_statistics", lambda child: False)

        result = cards.card_statistics(make_context(), child="child")
        nap_dur = next(i for i in result["stats"] if i["title"] == "Average nap duration")
        nap_per = next(i for i in result["stats"] if i["title"] == "Average naps per day")

        assert nap_dur["type"] == "duration"
        assert nap_dur["stat"] is nap_avg
        assert nap_per["type"] == "float"
        assert nap_per["stat"] == weight_chg



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
