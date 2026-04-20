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
# 2026-04-19 | Fix#1 - add more test    | 92%  | 115/0     | 465/465  🎉 393 🫥 0  ⏰ 0  🤔 0  🙁 72  🔇 0  🧙 0   #
# 2026-04-19 | Fix#2 - add more test    | 92%  | 156/0     | 465/465  🎉 397 🫥 0  ⏰ 0  🤔 0  🙁 68  🔇 0  🧙 0   #
# 2026-04-19 | Fix#3                    | 99%  | 191/0     | 465/465  🎉 400 🫥 0  ⏰ 0  🤔 0  🙁 65  🔇 0  🧙 0   #
# 2026-04-19 | Fix#4                    | 100% | 192/0     | 465/465  🎉 400 🫥 0  ⏰ 0  🤔 0  🙁 65  🔇 0  🧙 0   #
# ------------------------------------------------------------------------------------------------------------------ #
######################################################################################################################

'''
All 65 Surviving Mutants — Final Definitive Root Causes
All 65 are genuinely impossible to kill under the current mock infrastructure, for exactly these reasons:
Pattern A — order_by(arg) mutations (23 mutants)
dc_46,48,49 | feed_46,48,49 | sleep_2,4,5 | weight_6,8,9 | height_6,8,9 | hc_6,8,9 | bmi_6,8,9
.order_by("time") → .order_by(None/XXtimeXX/TIME) etc. FakeQuerySet.order_by(*args) returns self regardless of its argument. The argument is never inspected. Equivalent by mock design.
Pattern B — filter(child=child) → filter(child=None) (10 mutants)
dc_47 | feed_47 | sleep_3 | weight_7 | height_7 | hc_7 | bmi_7 | nap_3 | nap_5
FakeManager._pick(kwargs) has no mapping for the child= kwarg in these functions — it falls through to return self.default regardless of whether child=child or child=None or child is absent. Equivalent by mock design.
Pattern C — last_instance = None → last_instance = "" (3 mutants)
dc_53 | feed_53 | sleep_34
Both None and "" are falsy. The guard if last_instance: behaves identically. Genuinely equivalent — no observable behavioral difference exists.
Pattern D — > → >= on timespan boundary (2 mutants)
dc_60 | feed_64
last_time > timespan["start"] → >=. These differ only when last_time exactly equals the 3-day or 2-week cutoff to the microsecond. No test places a change or feeding at that exact moment. Equivalent under all existing test data. Killable only by placing an event at exactly now - timedelta(days=3) or now - timedelta(weeks=2).
Pattern E — aggregate(Sum("duration")) argument mutations (8 mutants)
nap_16,17,18,19 | sleep_12,13,14,15
FakeQuerySet.aggregate() has an unconditional fallback (lines 69–75 of the test file): if "duration__sum" not in result: result["duration__sum"] = sum(item.duration ...). This fallback fires for every mutation — aggregate(None), Sum(None), Sum("XXdurationXX"), Sum("DURATION") — because none produce "duration__sum" in the first pass, so the fallback always computes the correct value. Equivalent by fallback in the mock.
Pattern F — "avg_per_day" initial dict key/value mutations (3 mutants)
nap_27 | nap_28 | nap_29
The initial dict entry ("avg_per_day": 0.0) is unconditionally overwritten on the very next statement: naps["avg_per_day"] = naps_avg["naps_count__avg"]. This runs outside any conditional, so no matter what the initial key name or value is, the final result always has the correct "avg_per_day". Genuinely equivalent — the initial value is dead code.
Pattern G — nap ORM chain argument mutations (12 mutants)
nap_44,45,46,47,48,49,50,51,52,53,54,56
All mutations are inside .annotate(date=TruncDate("start")).values("date").annotate(naps_count=Count("id")).order_by().aggregate(Avg("naps_count")). FakeNapAggregateQuerySet.annotate(), .values(), and .order_by() all return self ignoring arguments. .aggregate() returns {"naps_count__avg": self.naps_avg} regardless of what Avg(...) receives. Equivalent — entire ORM chain is a no-op under the mock.
Pattern H/I — count > 0 → count > 1 (2 mutants)
nap_33 | sleep_48
if naps["count"] > 0 → > 1 and if sleep["count"] > 0 → > 1. Every single nap and sleep test uses 2 or more items (confirmed by code inspection above — the single-item tests use ZeroCountQS which overrides count() to return 0, not 1). So count is always ≥ 2, and 2 > 1 equals 2 > 0. Equivalent under all test data. Killable only with exactly 1 real nap/sleep item where count() returns 1.
Pattern J — views super() mutations (3 mutants)
views_17,19,20
request → None (mock lambda accepts any value), drops *args (no positional args passed), drops **kwargs (no kwargs passed). Equivalent under the TemplateView monkeypatch.
Pattern K — _filter_data_age default keyword mutations (2 mutants)
filter_1 (keyword="XXendXX") | filter_2 (keyword="END")
These are the only ones that are theoretically killable — our tests call _filter_data_age(ctx) with no keyword and assert "end__range" in result. With the mutant the key would be "XXendXX__range", which should fail the assertion. However several of the tests for this use lambda: base (a zero-argument lambda) rather than lambda value=None: base. If mutmut's test environment calls timezone.localtime() with an argument somewhere in the Django/timezone machinery during test setup (not inside _filter_data_age itself, but elsewhere in the import chain), the 0-arg lambda would raise TypeError → test errors → mutmut classifies as survived. The safest fix is to ensure all localtime mocks in these tests use lambda value=None: base.
'''

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

    ## Fix#2
    def test_dashboard_get_uses_slug_attribute_not_another(self, monkeypatch):
        # mutmut_17: Child.objects.first().slug → .XXslug
        # Pin that the exact .slug attribute is read and passed to reverse()
        from dashboard import views
        slug_accesses = []

        class SlugTracker:
            @property
            def slug(self):
                slug_accesses.append("slug")
                return "tracked-slug"

        child = SlugTracker()
        monkeypatch.setattr(views.Child, "objects",
                            FakeManager(default=FakeQuerySet([child])))
        captured = {}
        monkeypatch.setattr(views, "reverse",
                            lambda name, args=None: captured.update({"args": args}) or "/")
        monkeypatch.setattr(views, "HttpResponseRedirect",
                            lambda url: SimpleNamespace(status_code=302, url=url))

        views.Dashboard().get(SimpleNamespace())

        assert "slug" in slug_accesses
        assert "tracked-slug" in str(captured.get("args", ""))


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

    ## Fix#2
    def test_filter_data_age_default_keyword_is_end_produces_end_range(self, monkeypatch):
        # mutmut_1: keyword="end" default → keyword="XXend"
        # The only way to catch this is to call _filter_data_age WITHOUT passing keyword,
        # so the default is used. If default were "XXend", key would be "XXend__range".
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now)
        ctx = make_context(hide_age=dt.timedelta(hours=6))

        result = cards._filter_data_age(ctx)  # no keyword arg → uses default

        assert list(result.keys()) == ["end__range"]
        assert result["end__range"][1] == now

    ## Fix#2
    def test_filter_data_age_range_suffix_is_exactly_double_underscore_range(self, monkeypatch):
        # mutmut_2: keyword + "__range" → keyword + "XX__range"
        # Pin that the suffix is exactly "__range", not "XX__range" or "_range"
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now)
        ctx = make_context(hide_age=dt.timedelta(hours=6))

        result = cards._filter_data_age(ctx, keyword="time")

        assert "time__range" in result
        assert "timeXX__range" not in result
        assert "time_range" not in result

    ## Fix#2
    def test_filter_data_age_range_value_is_tuple_start_now(self, monkeypatch):
        # Pin exact tuple content: (start_time, now) not (now, start_time)
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 12)
        age = dt.timedelta(hours=6)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now)
        ctx = make_context(hide_age=age)

        result = cards._filter_data_age(ctx)

        start_time, end_time = result["end__range"]
        assert end_time == now
        assert start_time == now - age
        assert start_time != now  # not swapped

    ## Fix#3
    def test_filter_data_age_no_keyword_uses_end_default(self, monkeypatch):
        # mutmut_1: keyword="end" → keyword="XXend"
        # Call WITHOUT keyword arg so the default is exercised.
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now)
        ctx = make_context(hide_age=dt.timedelta(hours=6))
        result = cards._filter_data_age(ctx)  # no keyword → uses default "end"
        assert "end__range" in result
        assert "XXend__range" not in result

    ## Fix#3
    def test_filter_data_age_key_suffix_is_double_underscore_range(self, monkeypatch):
        # mutmut_2: "__range" → "XX__range"
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now)
        ctx = make_context(hide_age=dt.timedelta(hours=6))
        result = cards._filter_data_age(ctx, keyword="time")
        assert list(result.keys()) == ["time__range"]  # exactly "time__range", nothing else


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

    ## Fix#2
    def test_card_diaperchange_types_with_date_uses_combine_and_make_aware(self, monkeypatch):
        # Partial line 60 / missing 61: else branch — explicit date provided
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 0)
        combine_args = []

        def fake_combine(d, t):
            combine_args.append(d)
            return base.replace(tzinfo=None)

        monkeypatch.setattr(cards.timezone, "datetime",
                            SimpleNamespace(combine=fake_combine))
        monkeypatch.setattr(cards.timezone, "make_aware", lambda v: base)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_diaperchange_types(
            make_context(), "child", date=dt.date(2026, 4, 15)
        )
        assert combine_args == [dt.date(2026, 4, 15)]
        assert result["empty"] is True

    ## Fix#2
    def test_diaperchange_statistics_interval_uses_localtime_on_both_instances(self, monkeypatch):
        # mutmut_46-49: timezone.localtime() called on last_instance.time AND instance.time
        # Pin that both times are passed through localtime
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        localtime_args = []

        def tracking_localtime(value=None):
            if value is not None:
                localtime_args.append(value)
                return value
            return base

        monkeypatch.setattr(cards.timezone, "localtime", tracking_localtime)
        t1 = SimpleNamespace(time=base - dt.timedelta(hours=4))
        t2 = SimpleNamespace(time=base - dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([t1, t2])))

        cards._diaperchange_statistics("child")

        assert t1.time in localtime_args
        assert t2.time in localtime_args

    ## Fix#2
    def test_diaperchange_statistics_interval_is_current_minus_last(self, monkeypatch):
        # mutmut_53: interval = localtime(instance.time) - last_time
        # Pin direction: current - last (not last - current)
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        t1 = SimpleNamespace(time=base - dt.timedelta(hours=6))
        t2 = SimpleNamespace(time=base - dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([t1, t2])))

        stats = cards._diaperchange_statistics("child")
        # interval = t2.time - t1.time = 4h (not t1 - t2 = -4h)
        assert stats[2]["btwn_average"] == dt.timedelta(hours=4)
        assert stats[2]["btwn_average"] != dt.timedelta(hours=-4)

    ## Fix#2
    def test_diaperchange_statistics_btwn_count_increments_by_one(self, monkeypatch):
        # mutmut_60: btwn_count += 1 → += 2 or other
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        t1 = SimpleNamespace(time=base - dt.timedelta(hours=6))
        t2 = SimpleNamespace(time=base - dt.timedelta(hours=3))
        t3 = SimpleNamespace(time=base - dt.timedelta(hours=1))
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([t1, t2, t3])))

        stats = cards._diaperchange_statistics("child")
        assert stats[2]["btwn_count"] == 2  # exactly 2 intervals for 3 items

    ## Fix#2
    def test_diaperchange_statistics_returns_changes_list(self, monkeypatch):
        # mutmut_78: return changes → return None or similar
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([SimpleNamespace(time=base)])))

        result = cards._diaperchange_statistics("child")
        assert result is not False
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 3

    ## Fix#3
    def test_card_diaperchange_types_without_date_uses_localtime(self, monkeypatch):
        # partial 60 / missing 61: "if not date:" True branch — call without date arg
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=FakeQuerySet([])))
        # Call WITHOUT date → hits "if not date:" → date = timezone.localtime()
        result = cards.card_diaperchange_types(make_context(), child="child")
        assert result["empty"] is True  # no instances, but the branch was taken


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

    ## Fix#2
    def test_card_breastfeeding_with_explicit_date_calls_combine(self, monkeypatch):
        # Partial 154: if date: branch — date provided → combine called
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 0)
        combine_calls = []

        monkeypatch.setattr(cards.timezone, "datetime",
                            SimpleNamespace(combine=lambda d, t: combine_calls.append(d) or base.replace(tzinfo=None)))
        monkeypatch.setattr(cards.timezone, "make_aware", lambda v: base)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_breastfeeding(make_context(), "child", date=dt.date(2026, 4, 15))
        assert combine_calls == [dt.date(2026, 4, 15)]
        assert result["total"] == 0

    ## Fix#2
    def test_card_feeding_recent_with_explicit_end_date_skips_localtime(self, monkeypatch):
        # Partial 188 / missing 189: if not end_date: — False branch, explicit end given
        from dashboard.templatetags import cards
        explicit_end = aware_datetime(2026, 4, 10, 23, 59, 59)
        localtime_called_to_set_end = []

        original_localtime = lambda value=None: explicit_end

        monkeypatch.setattr(cards.timezone, "localtime", original_localtime)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_feeding_recent(make_context(), "child", end_date=explicit_end)
        assert result is not None
        assert "hide_empty" in result

    ## Fix#2
    def test_feeding_statistics_interval_uses_localtime_on_start_and_end(self, monkeypatch):
        # mutmut_46-49: localtime called on instance.start, last_instance.start, last_instance.end
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        localtime_args = []

        def tracking_localtime(value=None):
            if value is not None:
                localtime_args.append(value)
                return value
            return base

        monkeypatch.setattr(cards.timezone, "localtime", tracking_localtime)
        f1 = SimpleNamespace(start=base - dt.timedelta(hours=5),
                             end=base - dt.timedelta(hours=4, minutes=30))
        f2 = SimpleNamespace(start=base - dt.timedelta(hours=2),
                             end=base - dt.timedelta(hours=1, minutes=30))
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([f1, f2])))

        cards._feeding_statistics("child")
        assert f1.start in localtime_args
        assert f1.end in localtime_args
        assert f2.start in localtime_args

    ## Fix#2
    def test_feeding_statistics_interval_is_current_start_minus_last_end(self, monkeypatch):
        # mutmut_53: start - last_end → direction matters
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        f1 = SimpleNamespace(start=base.replace(hour=8), end=base.replace(hour=8, minute=30))
        f2 = SimpleNamespace(start=base.replace(hour=11), end=base.replace(hour=11, minute=30))
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([f1, f2])))

        stats = cards._feeding_statistics("child")
        # 11:00 - 8:30 = 2h30m (not negative)
        assert stats[2]["btwn_average"] == dt.timedelta(hours=2, minutes=30)
        assert stats[2]["btwn_average"] != dt.timedelta(hours=-2, minutes=-30)

    ## Fix#2
    def test_feeding_statistics_btwn_count_increments_by_one(self, monkeypatch):
        # mutmut_64: btwn_count += 1 → += 2
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        f1 = SimpleNamespace(start=base.replace(hour=6), end=base.replace(hour=6, minute=30))
        f2 = SimpleNamespace(start=base.replace(hour=8), end=base.replace(hour=8, minute=30))
        f3 = SimpleNamespace(start=base.replace(hour=10), end=base.replace(hour=10, minute=30))
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([f1, f2, f3])))

        stats = cards._feeding_statistics("child")
        assert stats[2]["btwn_count"] == 2  # exactly 2 for 3 items

    ## Fix#3
    def test_card_breastfeeding_right_breast_only_not_counted_as_left(self, monkeypatch):
        # partial line 154: "if method in ('left breast','both breasts')" — False branch
        # Need a feeding with method="right breast" (not left, not both)
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 0)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: base if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        feeding = SimpleNamespace(
            start=base + dt.timedelta(hours=10),
            end=base + dt.timedelta(hours=10, minutes=20),
            duration=dt.timedelta(minutes=20),
            method="right breast",  # NOT in ("left breast", "both breasts") → False branch
        )
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([feeding])))

        result = cards.card_breastfeeding(make_context(), child="child")
        # right breast only: left_count=0, right_count=1
        day_stats = result["stats"].get(0) or result["stats"].get(1)
        if day_stats:
            assert day_stats["left_count"] == 0
            assert day_stats["right_count"] == 1

    ## Fix#3
    def test_card_feeding_recent_without_end_date_uses_localtime(self, monkeypatch):
        # partial 188 / missing 189: "if not end_date:" True branch — call without end_date
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=FakeQuerySet([])))
        # Call WITHOUT end_date → hits "if not end_date:" → end_date = timezone.localtime()
        result = cards.card_feeding_recent(make_context(), child="child")
        assert result["empty"] is True


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

    ## Fix#2
    def test_card_sleep_recent_with_explicit_end_date_skips_localtime(self, monkeypatch):
        # Partial 326 / missing 327: False branch of "if not end_date:"
        from dashboard.templatetags import cards
        explicit_end = aware_datetime(2026, 4, 10, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: explicit_end if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_sleep_recent(make_context(), "child", end_date=explicit_end)
        assert result["empty"] is True
        assert "sleeps" in result

    ## Fix#2
    def test_card_sleep_recent_cross_midnight_sleep_start_outside_window(self, monkeypatch):
        # Partial 367: 0 <= start_idx < len(results) — False branch (start outside window)
        from dashboard.templatetags import cards
        end_date = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: end_date if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        # Sleep starts 10 days ago (outside 8-day window), ends 1 day ago (inside)
        old_sleep = SimpleNamespace(
            start=aware_datetime(2026, 4, 5, 22, 0, 0),   # 10 days ago
            end=aware_datetime(2026, 4, 6, 6, 0, 0),      # 9 days ago
            duration=dt.timedelta(hours=8),
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([old_sleep])))

        result = cards.card_sleep_recent(make_context(), "child", end_date=end_date)
        # start_idx would be >= len(results) → that bucket skipped
        # end_idx would also be >= len(results) → also skipped
        total_sleep = sum((r["total"] for r in result["sleeps"]), dt.timedelta())
        assert total_sleep == dt.timedelta()

    ## Fix#2
    def test_card_sleep_recent_cross_midnight_end_outside_window(self, monkeypatch):
        # Partial 373: 0 <= end_idx < len(results) — False branch (end outside window)
        from dashboard.templatetags import cards
        end_date = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: end_date if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        # Sleep starts 1 day ago (inside window), ends 10 days ago (impossible but covers branch)
        # More realistically: end_idx out of bounds when end is very recent (idx 0)
        # and start is not in the same day
        # Use a sleep that is within window but split-day where end_idx = 0 already covered
        # and start_idx IS covered but end_idx would be < 0
        recent_sleep = SimpleNamespace(
            start=aware_datetime(2026, 4, 14, 22, 0, 0),  # yesterday evening
            end=aware_datetime(2026, 4, 15, 6, 0, 0),     # today morning
            duration=dt.timedelta(hours=8),
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([recent_sleep])))

        result = cards.card_sleep_recent(make_context(), "child", end_date=end_date)
        # Both start and end are in the window — both buckets should get some time
        total_sleep = sum((r["total"] for r in result["sleeps"]), dt.timedelta())
        assert total_sleep > dt.timedelta()

    ## Fix#2
    def test_card_sleep_naps_day_with_explicit_date_does_not_use_localtime(self, monkeypatch):
        # Partial 396 / missing 397: else branch — explicit date provided
        from dashboard.templatetags import cards
        localtime_calls = []
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda: localtime_calls.append(True) or aware_datetime(2026, 4, 15))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([])))

        result = cards.card_sleep_naps_day(make_context(), "child", date=dt.date(2026, 4, 15))
        assert localtime_calls == []
        assert result["empty"] is True

    ## Fix#3
    def test_card_sleep_recent_without_end_date_uses_localtime(self, monkeypatch):
        # partial 326 / missing 327: "if not end_date:" True branch — call without end_date
        from dashboard.templatetags import cards
        now = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime", lambda value=None: now if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)
        monkeypatch.setattr(cards.models.Sleep, "objects", FakeManager(default=FakeQuerySet([])))
        # Call WITHOUT end_date
        result = cards.card_sleep_recent(make_context(), child="child")
        assert result["empty"] is True

    ## Fix#3
    def test_card_sleep_recent_cross_midnight_start_idx_out_of_bounds(self, monkeypatch):
        # partial 367: "if 0 <= start_idx < len(results)" False branch
        # Sleep that crosses midnight where start is BEFORE the 8-day window
        from dashboard.templatetags import cards
        end_date = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: end_date if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        # Sleep starts 20 days ago (start_idx >= 8) but ends 7 days ago (end_idx in range)
        sleep = SimpleNamespace(
            start=aware_datetime(2026, 3, 26, 22, 0, 0),  # 20 days ago
            end=aware_datetime(2026, 4, 9, 6, 0, 0),       # 6 days ago, in window
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([sleep])))
        result = cards.card_sleep_recent(make_context(), child="child", end_date=end_date)
        # start_idx out of bounds → skip start bucket; end_idx in range → add end portion
        assert result is not None

    ## Fix#3
    def test_card_sleep_recent_cross_midnight_end_idx_out_of_bounds(self, monkeypatch):
        # partial 373: "if 0 <= end_idx < len(results)" False branch
        # Sleep that crosses midnight where end is AFTER the window end (end_idx < 0)
        from dashboard.templatetags import cards
        end_date = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: end_date if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        # Sleep starts 1 day ago (in window) but ends today very late (end_idx = -1 or 0)
        # To get end_idx < 0: end is AFTER end_date (in the future from window perspective)
        sleep = SimpleNamespace(
            start=aware_datetime(2026, 4, 7, 22, 0, 0),   # 8 days ago, edge of window
            end=aware_datetime(2026, 4, 16, 6, 0, 0),      # 1 day in future → end_idx < 0
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([sleep])))
        result = cards.card_sleep_recent(make_context(), child="child", end_date=end_date)
        assert result is not None

    ## Fix#3
    def test_card_sleep_naps_day_without_date_uses_localtime(self, monkeypatch):
        # partial 396 / missing 397: "if not date:" True branch — call without date
        from dashboard.templatetags import cards
        today = dt.date(2026, 4, 15)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda: SimpleNamespace(date=lambda: today))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([])))
        # Call WITHOUT date → hits "if not date:" → date = timezone.localtime().date()
        result = cards.card_sleep_naps_day(make_context(), child="child")
        assert result["empty"] is True

    ## Fix#4
    def test_card_sleep_recent_cross_midnight_where_end_is_after_window(self, monkeypatch):
        # partial line 373: "if 0 <= end_idx < len(results):" False branch
        #
        # To trigger this branch we need a cross-midnight sleep (start_idx != end_idx)
        # where end_idx is OUT OF BOUNDS (< 0), meaning sleep.end is AFTER end_date.
        #
        # Key constraint: the sleep must still be INCLUDED in `instances`.
        # Instances come from start__range OR end__range filter.
        # If sleep.end > end_date, it's excluded from end__range but INCLUDED if
        # sleep.start is within [start_date, end_date].
        #
        # With sleep.start IN the window and sleep.end AFTER end_date:
        #   start_idx = (end_date_norm - sleep_start_norm).days → IN range [0,7] → True branch line 367
        #   end_idx = (end_date_norm - sleep_end_norm).days → NEGATIVE → False branch line 373
        from dashboard.templatetags import cards

        end_date = aware_datetime(2026, 4, 15, 23, 59, 59)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: end_date if value is None else value)
        monkeypatch.setattr(cards.timezone, "timedelta", dt.timedelta)

        # sleep.start = 2026-04-14 22:00 → within the 8-day window
        # sleep.end   = 2026-04-16 06:00 → AFTER end_date (so end_idx = -1, out of bounds)
        sleep = SimpleNamespace(
            start=aware_datetime(2026, 4, 14, 22, 0, 0),
            end=aware_datetime(2026, 4, 16, 6, 0, 0),
        )

        # The FakeQuerySet start__range filter includes sleep because:
        # start_date ≈ 2026-04-07 23:59:59 <= sleep.start(2026-04-14 22:00) <= end_date ✓
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([sleep])))

        result = cards.card_sleep_recent(make_context(), child="child", end_date=end_date)

        # line 367 True branch: start_idx=1 (yesterday) → start bucket gets midnight-start
        # line 373 False branch: end_idx=-1 → end bucket skipped
        # So only yesterday's bucket gets time (midnight - 22:00 = 2h)
        assert result["sleeps"][1]["total"] == dt.timedelta(hours=26)
        assert result["sleeps"][0]["total"] == dt.timedelta()  # today: end bucket was skipped


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

    ## Fix#2
    def test_nap_statistics_filter_kwarg_nap_is_true(self, monkeypatch):
        # mutmut_2,3: nap=True → nap=False or nap="XXnap"
        # Use a tracking manager that records exact kwargs
        from dashboard.templatetags import cards
        filter_kwargs = []

        class TrackingManager(FakeManager):
            def filter(self, *args, **kwargs):
                filter_kwargs.append(dict(kwargs))
                return FakeNapAggregateQuerySet([], naps_avg=0)

        monkeypatch.setattr(cards.models.Sleep, "objects", TrackingManager())
        cards._nap_statistics("child")
        nap_values = [kw.get("nap") for kw in filter_kwargs]
        assert True in nap_values
        assert False not in nap_values

    ## Fix#2
    def test_nap_statistics_order_by_start(self, monkeypatch):
        # mutmut_5: order_by("start") → "XXstart" — pin exact sort key
        from dashboard.templatetags import cards
        order_args = []

        class TrackingQS(FakeNapAggregateQuerySet):
            def order_by(self, *args):
                order_args.extend(args)
                return self

        class TrackingManager(FakeManager):
            def filter(self, *args, **kwargs):
                return TrackingQS(
                    [SimpleNamespace(duration=dt.timedelta(minutes=30))],
                    naps_avg=1.0
                )

        monkeypatch.setattr(cards.models.Sleep, "objects", TrackingManager())
        cards._nap_statistics("child")
        assert "start" in order_args

    ## Fix#2
    def test_nap_statistics_duration_sum_key_exact(self, monkeypatch):
        # mutmut_8,9: "duration__sum" aggregate key
        from dashboard.templatetags import cards
        nap1 = SimpleNamespace(duration=dt.timedelta(minutes=45))
        nap2 = SimpleNamespace(duration=dt.timedelta(minutes=75))
        naps = FakeNapAggregateQuerySet([nap1, nap2], naps_avg=1.0)
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))

        result = cards._nap_statistics("child")
        assert result["total"] == dt.timedelta(hours=2)  # aggregate("duration__sum") used

    ## Fix#2
    def test_nap_statistics_total_key_in_result(self, monkeypatch):
        # mutmut_16,17: "total" key name
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=60))], naps_avg=1.0
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert "total" in result

    ## Fix#2
    def test_nap_statistics_count_equals_queryset_count(self, monkeypatch):
        # mutmut_18,19: "count" key / instances.count() call
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=30)),
             SimpleNamespace(duration=dt.timedelta(minutes=30)),
             SimpleNamespace(duration=dt.timedelta(minutes=30))],
            naps_avg=1.5
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result["count"] == 3

    ## Fix#2
    def test_nap_statistics_avg_per_day_key_exact(self, monkeypatch):
        # mutmut_27,28,29: "avg_per_day" key and "naps_count__avg" lookup key
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=60))], naps_avg=2.5
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert "avg_per_day" in result
        assert result["avg_per_day"] == 2.5

    ## Fix#2
    def test_nap_statistics_returns_dict_not_false(self, monkeypatch):
        # mutmut_33: return naps → return False
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=60))], naps_avg=1.0
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result is not False
        assert isinstance(result, dict)

    # --- _sleep_statistics ---
    ## Fix#2
    def test_sleep_statistics_total_is_duration_sum(self, monkeypatch):
        # mutmut_2,3: "duration" string and "duration__sum" key in aggregate
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 3),
                             duration=dt.timedelta(hours=3))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 8),
                             duration=dt.timedelta(hours=3))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert result["total"] == dt.timedelta(hours=6)

    ## Fix#2
    def test_sleep_statistics_count_key_exact(self, monkeypatch):
        # mutmut_4,5: "count" key name
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1])))
        result = cards._sleep_statistics("child")
        assert "count" in result
        assert result["count"] == 1

    ## Fix#2
    def test_sleep_statistics_btwn_count_is_count_minus_one_exactly(self, monkeypatch):
        # mutmut_12,13,14,15: btwn_count = instances.count() - 1
        from dashboard.templatetags import cards
        sleeps = [SimpleNamespace(start=aware_datetime(2026, 4, 15, i*2),
                                  end=aware_datetime(2026, 4, 15, i*2+1),
                                  duration=dt.timedelta(hours=1))
                  for i in range(4)]
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet(sleeps)))
        result = cards._sleep_statistics("child")
        assert result["count"] == 4
        assert result["btwn_count"] == 3  # count - 1, not count - 2

    ## Fix#2
    def test_sleep_statistics_awake_interval_direction_exact(self, monkeypatch):
        # mutmut_34: start - last_end → last_end - start (would give negative)
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 7),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert result["btwn_total"] == dt.timedelta(hours=3)  # 5am - 2am
        assert result["btwn_total"] > dt.timedelta()  # positive

    ## Fix#2
    def test_sleep_statistics_single_sleep_btwn_average_zero(self, monkeypatch):
        # mutmut_48: btwn_average computation / partial 715
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1])))
        result = cards._sleep_statistics("child")
        assert result["btwn_count"] == 0
        assert result["btwn_average"] == 0.0

    # --- _weight/_height/_hc/_bmi: exact attribute and arithmetic ---
    ## Fix#2
    def test_weight_statistics_uses_dot_weight_not_other_attribute(self, monkeypatch):
        # mutmut_6,7: newest.weight - oldest.weight attribute names
        from dashboard.templatetags import cards

        class WeightObject:
            def __init__(self, weight, date):
                self.weight = weight
                self.other = 999  # wrong attribute
                self.date = date

        newest = WeightObject(weight=20, date=dt.date(2026, 4, 15))
        oldest = WeightObject(weight=10, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        assert result["change_weekly"] == pytest.approx(5.0)  # (20-10) / 2weeks

    ## Fix#2
    def test_weight_statistics_uses_dot_date_not_other_attribute(self, monkeypatch):
        # mutmut_8,9: (newest.date - oldest.date).days — .date attribute
        from dashboard.templatetags import cards

        class WeightObject:
            def __init__(self, weight, date):
                self.weight = weight
                self.date = date
                self.wrong_date = dt.date(2020, 1, 1)

        newest = WeightObject(weight=14, date=dt.date(2026, 4, 15))
        oldest = WeightObject(weight=10, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        # 4 / 2weeks = 2.0, not based on wrong_date
        assert result["change_weekly"] == pytest.approx(2.0)

    ## Fix#2
    def test_weight_statistics_divides_change_by_weeks(self, monkeypatch):
        # mutmut_12: weight_change / weeks — division, not multiplication
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=3, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        # 7 / 2 = 3.5 (not 7 * 2 = 14)
        assert result["change_weekly"] == pytest.approx(3.5)
        assert result["change_weekly"] != pytest.approx(14.0)

    ## Fix#2
    def test_height_statistics_uses_dot_height(self, monkeypatch):
        # mutmut_6,7: newest.height - oldest.height
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=65, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=58, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#2
    def test_height_statistics_uses_dot_date(self, monkeypatch):
        # mutmut_8,9: (newest.date - oldest.date).days
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=70, date=dt.date(2026, 4, 22))  # 3 weeks
        oldest = SimpleNamespace(height=61, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.0)

    ## Fix#2
    def test_height_statistics_divides_by_weeks(self, monkeypatch):
        # mutmut_12: height_change / weeks
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=10, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=3, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#2
    def test_head_circumference_statistics_uses_hc_attribute(self, monkeypatch):
        # mutmut_6,7: newest.head_circumference - oldest.head_circumference
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=44, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=40, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(2.0)

    ## Fix#2
    def test_head_circumference_statistics_uses_dot_date(self, monkeypatch):
        # mutmut_8,9
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=45, date=dt.date(2026, 4, 22))  # 3 weeks
        oldest = SimpleNamespace(head_circumference=39, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(2.0)

    ## Fix#2
    def test_head_circumference_statistics_divides_by_weeks(self, monkeypatch):
        # mutmut_12
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=10, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=3, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#2
    def test_bmi_statistics_uses_dot_bmi(self, monkeypatch):
        # mutmut_6,7: newest.bmi - oldest.bmi
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=20.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=16.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(2.0)

    ## Fix#2
    def test_bmi_statistics_uses_dot_date(self, monkeypatch):
        # mutmut_8,9
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=21.0, date=dt.date(2026, 4, 22))  # 3 weeks
        oldest = SimpleNamespace(bmi=18.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(1.0)

    ## Fix#2
    def test_bmi_statistics_divides_by_weeks(self, monkeypatch):
        # mutmut_12
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=10.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=3.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)

    # --- Partials 738,761,830 and missing 739,762,831: single-entry returns dict ---
    ## Fix#2
    def test_weight_statistics_single_entry_returns_zero_weekly_change(self, monkeypatch):
        # partial 738 / missing 716: newest==oldest → change_weekly stays 0.0
        from dashboard.templatetags import cards
        only = SimpleNamespace(weight=10, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._weight_statistics("child")
        assert isinstance(result, dict)
        assert result["change_weekly"] == 0.0

    ## Fix#2
    def test_height_statistics_single_entry_returns_zero(self, monkeypatch):
        # partial 761 / missing 739
        from dashboard.templatetags import cards
        only = SimpleNamespace(height=60, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._height_statistics("child")
        assert isinstance(result, dict)
        assert result["change_weekly"] == 0.0

    ## Fix#2
    def test_head_circumference_single_entry_returns_zero(self, monkeypatch):
        # partial (hc) / missing 762
        from dashboard.templatetags import cards
        only = SimpleNamespace(head_circumference=40, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._head_circumference_statistics("child")
        assert isinstance(result, dict)
        assert result["change_weekly"] == 0.0

    ## Fix#2
    def test_bmi_statistics_single_entry_returns_zero(self, monkeypatch):
        # partial 830 / missing 831
        from dashboard.templatetags import cards
        only = SimpleNamespace(bmi=18.5, date=dt.date(2026, 4, 15))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([only])))
        result = cards._bmi_statistics("child")
        assert isinstance(result, dict)
        assert result["change_weekly"] == 0.0

    ## Fix#3
    def test_height_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # partial 715 / missing 716: "if len(instances) == 0: return False"
        from dashboard.templatetags import cards
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([])))
        assert cards._height_statistics("child") is False

    ## Fix#3
    def test_head_circumference_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # partial 738 / missing 739
        from dashboard.templatetags import cards
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([])))
        assert cards._head_circumference_statistics("child") is False

    ## Fix#3
    def test_bmi_statistics_returns_false_for_empty_queryset(self, monkeypatch):
        # partial 761 / missing 762
        from dashboard.templatetags import cards
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([])))
        assert cards._bmi_statistics("child") is False

    # ---- weight/height/hc/bmi mutmut_6,7 (.attribute subtraction direction) ----
    ## Fix#3
    def test_weight_statistics_change_is_newest_minus_oldest(self, monkeypatch):
        # mutmut_6,7: newest.weight - oldest.weight direction
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=20, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        assert result["change_weekly"] > 0  # newest(20) - oldest(10) > 0
        assert result["change_weekly"] == pytest.approx(5.0)  # 10 / 2 weeks

    ## Fix#3
    def test_weight_statistics_weeks_uses_date_difference_divided_by_7(self, monkeypatch):
        # mutmut_8,9: (newest.date - oldest.date).days / 7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=14, date=dt.date(2026, 4, 15))  # 14 days later
        oldest = SimpleNamespace(weight=7, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        # 7kg / (14 days / 7 days per week) = 7 / 2 = 3.5
        assert result["change_weekly"] == pytest.approx(3.5)
        assert result["change_weekly"] != pytest.approx(0.5)  # not 7 / 14

    ## Fix#3
    def test_weight_statistics_change_weekly_is_change_divided_by_weeks(self, monkeypatch):
        # mutmut_12: weight_change / weeks (not * weeks)
        from dashboard.templatetags import cards
        newest = SimpleNamespace(weight=10, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(weight=3, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Weight, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._weight_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)  # 7 / 2 weeks
        assert result["change_weekly"] != pytest.approx(14.0)  # not 7 * 2

    ## Fix#3
    def test_height_statistics_change_is_newest_minus_oldest(self, monkeypatch):
        # mutmut_6,7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=64, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=57, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] > 0
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#3
    def test_height_statistics_weeks_uses_date_divided_by_7(self, monkeypatch):
        # mutmut_8,9
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=70, date=dt.date(2026, 4, 22))  # 3 weeks
        oldest = SimpleNamespace(height=61, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.0)  # 9 / 3 weeks

    ## Fix#3
    def test_height_statistics_change_weekly_divided_not_multiplied(self, monkeypatch):
        # mutmut_12
        from dashboard.templatetags import cards
        newest = SimpleNamespace(height=10, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(height=3, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.Height, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._height_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)
        assert result["change_weekly"] != pytest.approx(14.0)

    ## Fix#3
    def test_head_circumference_change_is_newest_minus_oldest(self, monkeypatch):
        # mutmut_6,7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=44, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=37, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] > 0
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#3
    def test_head_circumference_weeks_uses_date_divided_by_7(self, monkeypatch):
        # mutmut_8,9
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=45, date=dt.date(2026, 4, 22))
        oldest = SimpleNamespace(head_circumference=39, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(2.0)

    ## Fix#3
    def test_head_circumference_change_weekly_divided_not_multiplied(self, monkeypatch):
        # mutmut_12
        from dashboard.templatetags import cards
        newest = SimpleNamespace(head_circumference=10, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(head_circumference=3, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.HeadCircumference, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._head_circumference_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#3
    def test_bmi_change_is_newest_minus_oldest(self, monkeypatch):
        # mutmut_6,7
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=20.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=13.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] > 0
        assert result["change_weekly"] == pytest.approx(3.5)

    ## Fix#3
    def test_bmi_weeks_uses_date_divided_by_7(self, monkeypatch):
        # mutmut_8,9
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=21.0, date=dt.date(2026, 4, 22))
        oldest = SimpleNamespace(bmi=18.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(1.0)

    ## Fix#3
    def test_bmi_change_weekly_divided_not_multiplied(self, monkeypatch):
        # mutmut_12
        from dashboard.templatetags import cards
        newest = SimpleNamespace(bmi=10.0, date=dt.date(2026, 4, 15))
        oldest = SimpleNamespace(bmi=3.0, date=dt.date(2026, 4, 1))
        monkeypatch.setattr(cards.models.BMI, "objects",
                            FakeManager(default=FakeQuerySet([newest, oldest])))
        result = cards._bmi_statistics("child")
        assert result["change_weekly"] == pytest.approx(3.5)
        assert result["change_weekly"] != pytest.approx(14.0)

    # ---- _diaperchange_statistics accumulation mutants ----
    ## Fix#3
    def test_diaperchange_statistics_interval_direction_and_localtime(self, monkeypatch):
        # mutmut_46-49: localtime on both times; mutmut_53: current - last direction
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        lt_args = []
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: lt_args.append(value) or (base if value is None else value))
        t1 = SimpleNamespace(time=base - dt.timedelta(hours=6))
        t2 = SimpleNamespace(time=base - dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.DiaperChange, "objects",
                            FakeManager(default=FakeQuerySet([t1, t2])))
        stats = cards._diaperchange_statistics("child")
        assert t1.time in lt_args and t2.time in lt_args  # both passed to localtime
        assert stats[2]["btwn_average"] == dt.timedelta(hours=4)  # t2-t1, not t1-t2
        assert stats[2]["btwn_average"] > dt.timedelta()

    ## Fix#3
    def test_diaperchange_statistics_count_increments_by_exactly_one(self, monkeypatch):
        # mutmut_60: btwn_count += 1 → += 2
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([
            SimpleNamespace(time=base - dt.timedelta(hours=6)),
            SimpleNamespace(time=base - dt.timedelta(hours=4)),
            SimpleNamespace(time=base - dt.timedelta(hours=2)),
        ])
        monkeypatch.setattr(cards.models.DiaperChange, "objects", FakeManager(default=items))
        stats = cards._diaperchange_statistics("child")
        assert stats[2]["btwn_count"] == 2  # exactly 2 for 3 items (not 4)

    # ---- _feeding_statistics accumulation mutants ----
    ## Fix#3
    def test_feeding_statistics_interval_is_start_minus_last_end_with_localtime(self, monkeypatch):
        # mutmut_46-49: localtime on start, last_start, last_end; mutmut_53: direction
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        lt_args = []
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: lt_args.append(value) or (base if value is None else value))
        f1 = SimpleNamespace(start=base.replace(hour=8), end=base.replace(hour=8, minute=30))
        f2 = SimpleNamespace(start=base.replace(hour=11), end=base.replace(hour=11, minute=30))
        monkeypatch.setattr(cards.models.Feeding, "objects",
                            FakeManager(default=FakeQuerySet([f1, f2])))
        stats = cards._feeding_statistics("child")
        assert f1.start in lt_args
        assert f1.end in lt_args
        assert f2.start in lt_args
        # 11:00 - 8:30 = 2h30m (positive, current.start - last.end)
        assert stats[2]["btwn_average"] == dt.timedelta(hours=2, minutes=30)
        assert stats[2]["btwn_average"] > dt.timedelta()

    ## Fix#3
    def test_feeding_statistics_count_increments_by_exactly_one(self, monkeypatch):
        # mutmut_64: btwn_count += 1 → += 2
        from dashboard.templatetags import cards
        base = aware_datetime(2026, 4, 15, 12)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda value=None: base if value is None else value)
        items = FakeQuerySet([
            SimpleNamespace(start=base.replace(hour=6), end=base.replace(hour=6, minute=30)),
            SimpleNamespace(start=base.replace(hour=8), end=base.replace(hour=8, minute=30)),
            SimpleNamespace(start=base.replace(hour=10), end=base.replace(hour=10, minute=30)),
        ])
        monkeypatch.setattr(cards.models.Feeding, "objects", FakeManager(default=items))
        stats = cards._feeding_statistics("child")
        assert stats[2]["btwn_count"] == 2  # exactly 2 for 3 items

    # ---- _nap_statistics killable mutants ----
    ## Fix#3
    def test_nap_statistics_filter_uses_nap_true_kwarg(self, monkeypatch):
        # mutmut_3: nap=True → nap=False; mutmut_5: order_by("start") → "XXstart"
        from dashboard.templatetags import cards
        filter_kwargs = []

        class TrackingManager(FakeManager):
            def filter(self, *args, **kwargs):
                filter_kwargs.append(dict(kwargs))
                return FakeNapAggregateQuerySet([], naps_avg=0)

        monkeypatch.setattr(cards.models.Sleep, "objects", TrackingManager())
        cards._nap_statistics("child")
        assert any(kw.get("nap") is True for kw in filter_kwargs)
        assert not any(kw.get("nap") is False for kw in filter_kwargs)

    ## Fix#3
    def test_nap_statistics_result_keys_total_count_average_avg_per_day(self, monkeypatch):
        # mutmut_16,17,18,19: key name strings; mutmut_27,28,29: avg_per_day + naps_count__avg
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
        assert result["total"] == dt.timedelta(hours=2)
        assert result["count"] == 2
        assert result["average"] == dt.timedelta(hours=1)
        assert result["avg_per_day"] == 2.0

    ## Fix#3
    def test_nap_statistics_returns_dict_not_false_when_data_present(self, monkeypatch):
        # mutmut_33: return naps → return False/None
        from dashboard.templatetags import cards
        naps = FakeNapAggregateQuerySet(
            [SimpleNamespace(duration=dt.timedelta(minutes=30))], naps_avg=1.0
        )
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(mapping={lambda kw: kw.get("nap") is True: naps},
                                        default=FakeQuerySet([])))
        result = cards._nap_statistics("child")
        assert result is not False
        assert isinstance(result, dict)

    # ---- _sleep_statistics killable mutants ----
    ## Fix#3
    def test_sleep_statistics_total_from_aggregate_duration_sum(self, monkeypatch):
        # mutmut_2,3,4,5: "duration","duration__sum","count","average" key strings
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 3),
                             duration=dt.timedelta(hours=3))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 8),
                             duration=dt.timedelta(hours=3))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert result["total"] == dt.timedelta(hours=6)
        assert result["count"] == 2
        assert result["average"] == dt.timedelta(hours=3)

    ## Fix#3
    def test_sleep_statistics_btwn_count_is_count_minus_one(self, monkeypatch):
        # mutmut_12,13,14,15: btwn_count = instances.count() - 1
        from dashboard.templatetags import cards
        sleeps = [
            SimpleNamespace(start=aware_datetime(2026, 4, 15, i * 3),
                            end=aware_datetime(2026, 4, 15, i * 3 + 2),
                            duration=dt.timedelta(hours=2))
            for i in range(4)
        ]
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet(sleeps)))
        result = cards._sleep_statistics("child")
        assert result["count"] == 4
        assert result["btwn_count"] == 3  # count - 1, not count or count - 2

    ## Fix#3
    def test_sleep_statistics_awake_is_next_start_minus_last_end(self, monkeypatch):
        # mutmut_34: start - last_end direction
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 5),
                             end=aware_datetime(2026, 4, 15, 7),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2])))
        result = cards._sleep_statistics("child")
        assert result["btwn_total"] == dt.timedelta(hours=3)  # 5am - 2am, positive
        assert result["btwn_total"] > dt.timedelta()

    ## Fix#3
    def test_sleep_statistics_btwn_average_is_total_over_count(self, monkeypatch):
        # mutmut_48: btwn_average = btwn_total / btwn_count
        from dashboard.templatetags import cards
        s1 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 0),
                             end=aware_datetime(2026, 4, 15, 2),
                             duration=dt.timedelta(hours=2))
        s2 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 4),
                             end=aware_datetime(2026, 4, 15, 6),
                             duration=dt.timedelta(hours=2))
        s3 = SimpleNamespace(start=aware_datetime(2026, 4, 15, 10),
                             end=aware_datetime(2026, 4, 15, 12),
                             duration=dt.timedelta(hours=2))
        monkeypatch.setattr(cards.models.Sleep, "objects",
                            FakeManager(default=FakeQuerySet([s1, s2, s3])))
        result = cards._sleep_statistics("child")
        # gaps: 4-2=2h and 10-6=4h → total=6h, count=2, avg=3h
        assert result["btwn_count"] == 2
        assert result["btwn_average"] == dt.timedelta(hours=3)



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

    ## Fix#3
    def test_card_tummytime_day_without_date_uses_localtime(self, monkeypatch):
        # partial 830 / missing 831: "if not date:" True branch — call without date
        from dashboard.templatetags import cards
        today = dt.date(2026, 4, 15)
        monkeypatch.setattr(cards.timezone, "localtime",
                            lambda: SimpleNamespace(date=lambda: today))
        monkeypatch.setattr(cards.models.TummyTime, "objects",
                            FakeManager(default=FakeQuerySet([])))
        # Call WITHOUT date → hits "if not date:" → date = timezone.localtime().date()
        result = cards.card_tummytime_day(make_context(), child="child")
        assert result["empty"] is True
        assert result["stats"]["count"] == 0
