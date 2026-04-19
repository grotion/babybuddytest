###########################################################################################################################
# core whitebox test                                                                                                      #
#                                                                                                                         #
# Author: Shaun Ku, Samson Cournane                                                                                       #
#                                                                                                                         #
#                                                                                                                         #
# Test result                                                                                                             #
# ----------------------------------------------------------------------------------------------------------------------- #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                     #
# ----------------------------------------------------------------------------------------------------------------------- #
# 2026-04-17 | Initial Test             | 76%  | 36/0      | 1806/1806  🎉 680 🫥 862  ⏰ 0  🤔 0  🙁 264  🔇 0  🧙 0   #
# 2026-04-19 | Fix#1                    | 89%  | 128/0     | 1806/1806  🎉 675 🫥 707  ⏰ 154  🤔 0  🙁 270  🔇 0  🧙 0 #
# 2026-04-19 | Fix#2                    | 94%  | 169/0     | 1806/1806  🎉 897 🫥 534  ⏰ 0  🤔 0  🙁 375  🔇 0  🧙 0   #
# 2026-04-19 | Fix#3                    | 94%  | 175/0     | 1806/1806  🎉 898 🫥 534  ⏰ 0  🤔 0  🙁 374  🔇 0  🧙 0   #
# ----------------------------------------------------------------------------------------------------------------------- #
###########################################################################################################################

'''
core/models.py — 43 missing
All require calling Django's ORM (super().save(), super().delete(), .filter(), .count()):

Lines 151-153: Tagged.save_base — calls self.tag.save() and super().save_base(), both hit the DB
Line 184: Child.delete — calls super().delete() then cache.set(Child.objects.count())
Lines 218, 221-227: Child.count classmethod and the Child.__str__ — cache.get_or_set(Child.objects.count) hits DB
Line 246: DiaperChange.clean — calls validate_time which is covered, but this line is the validate_time call inside clean, which Django only invokes through form validation with a real model instance
Lines 299, 360-367, 399, 429, 524-531, 579-582, 673-685, 725-733: All the save() and clean() methods on Feeding, HeadCircumference, Height, Note, Pumping, Sleep, TummyTime, Weight — all call super().save() (DB) or validate_unique_period(ModelClass.objects.filter(...), self) (DB query)
Line 614: Timer.restart/stop — calls self.save() / self.delete() → DB
Line 763: WeightPercentile.__str__ — this one is actually testable but trivial

core/forms.py — 3 missing
Lines 95-97: CoreModelForm.__init__ body — the super(CoreModelForm, self).__init__(*args, **kwargs) call requires real Django form binding machinery with a real model.
core/views.py — 26 missing

Lines 123-126: ChildDetail.get_context_data — calls super().get_context_data() which requires a real Django DetailView dispatch with a database-backed object
Lines 366-392: TagList.get_queryset and TagAdminDetail.get_queryset — both call super().get_queryset().annotate(Count(...)) which requires DB
Lines 415-416: TagAdminDelete.get_queryset — same, qs.annotate(Count(...))

core/widgets.py — 15 missing
Lines 67-84: TagsEditor.get_context — first line calls models.Tag.objects.order_by("-last_used").all()[:256] which is a DB query. Everything after depends on that result.
core/templatetags/timers.py — 28 missing (entire file)
timer_nav, quick_timer_nav, instance_add_url — all call Timer.objects.filter() and Child.objects.all() immediately. No logic can be isolated without DB access.
core/templatetags/breadcrumb.py — 11 missing (entire file)
child_quick_switch — first line calls Child.objects.exclude(slug=...). No unit-testable logic.
core/urls.py — counted here but shown as 4 missing in the image (the coverage report counts path() calls) — pure routing declarations, no executable logic.

Summary: The 94% total coverage ceiling you're hitting is the natural limit for whitebox unit testing of this Django project. The remaining 6% (96 statements) all require either a real database connection or full Django HTTP request dispatch to execute — they are integration test territory, not unit test territory.
'''

import datetime
from types import SimpleNamespace
from unittest.mock import Mock, MagicMock, patch, call

import pytest
from django import forms as django_forms
from django.core.exceptions import ValidationError

from core import fields as core_fields
from core import forms as core_forms
from core import timeline as core_timeline
from core import utils as core_utils
from core import views as core_views
from core import models as core_models
from core.widgets import TagsEditor, ChildRadioSelect, PillRadioSelect
from core.templatetags import duration as duration_tags
from core.templatetags import misc as misc_tags
from core.templatetags import bootstrap as bootstrap_tags
from core.templatetags import datetime as datetime_tags


class FakeQuerySet:
    def __init__(self, items):
        self.items = list(items)
        self.filter_calls = []
        self.order_by_calls = []

    def filter(self, **kwargs):
        self.filter_calls.append(kwargs)
        filtered = self.items
        for key, value in kwargs.items():
            if key.endswith("__range"):
                attr = key[:-7]
                start, end = value
                filtered = [
                    item for item in filtered if start <= getattr(item, attr) <= end
                ]
            else:
                filtered = [item for item in filtered if getattr(item, key) == value]
        new_qs = FakeQuerySet(filtered)
        new_qs.filter_calls = list(self.filter_calls)
        new_qs.order_by_calls = list(self.order_by_calls)
        return new_qs

    def order_by(self, *fields):
        self.order_by_calls.append(fields)
        items = list(self.items)
        for field in reversed(fields):
            reverse = field.startswith("-")
            attr = field[1:] if reverse else field
            items.sort(key=lambda item: getattr(item, attr), reverse=reverse)
        new_qs = FakeQuerySet(items)
        new_qs.filter_calls = list(self.filter_calls)
        new_qs.order_by_calls = list(self.order_by_calls)
        return new_qs

    def first(self):
        return self.items[0] if self.items else None

    def last(self):
        return self.items[-1] if self.items else None

    def count(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)


class DummyBoundField:
    def __init__(self, name):
        self.name = name


class TestCoreUtilsModule:
    def test_duration_parts_returns_hours_minutes_seconds_for_large_duration(self):
        # target file: core/utils.py
        # function/method: duration_parts
        # branch or behavior tested: multi-day duration is normalized into total hours
        duration = datetime.timedelta(days=2, hours=3, minutes=4, seconds=5)
        assert core_utils.duration_parts(duration) == (51, 4, 5)

    def test_duration_parts_rejects_none(self):
        # target file: core/utils.py
        # function/method: duration_parts
        # branch or behavior tested: invalid non-timedelta input raises TypeError
        with pytest.raises(TypeError):
            core_utils.duration_parts(None)

    @pytest.mark.parametrize(
        ("duration", "precision", "expected"),
        [
            (datetime.timedelta(hours=2, minutes=5, seconds=6), "s", "2 hours, 5 minutes, 6 seconds"),
            (datetime.timedelta(hours=2, minutes=5, seconds=6), "m", "2 hours, 5 minutes"),
            (datetime.timedelta(hours=2, minutes=5, seconds=6), "h", "2 hours"),
            (datetime.timedelta(minutes=0), "s", "0 minutes"),
        ],
    )
    def test_duration_string_formats_precisely(self, duration, precision, expected):
        # target file: core/utils.py
        # function/method: duration_string
        # branch or behavior tested: precision gates hour/minute/second rendering
        assert core_utils.duration_string(duration, precision=precision) == expected

    def test_random_color_uses_palette_boundaries(self, monkeypatch):
        # target file: core/utils.py
        # function/method: random_color
        # branch or behavior tested: random index covers full configured palette bounds
        calls = []

        def fake_randrange(start, stop):
            calls.append((start, stop))
            return stop - 1

        monkeypatch.setattr(core_utils.random, "randrange", fake_randrange)
        result = core_utils.random_color()

        assert calls == [(0, len(core_utils.COLORS))]
        assert result == core_utils.COLORS[-1]

    def test_timezone_aware_duration_accounts_for_timezone_conversion(self):
        # target file: core/utils.py
        # function/method: timezone_aware_duration
        # branch or behavior tested: aware datetimes are converted to UTC before subtraction
        eastern = datetime.timezone(datetime.timedelta(hours=-5))
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=eastern)
        end = datetime.datetime(2026, 1, 1, 16, 30, tzinfo=utc)

        assert core_utils.timezone_aware_duration(start, end) == datetime.timedelta(hours=1, minutes=30)

    ## Fix#1
    def test_duration_string_zero_hours_omits_hours(self):
        # h > 0 branch: when h == 0, hours not included
        d = datetime.timedelta(minutes=5, seconds=3)
        result = core_utils.duration_string(d)
        assert "hour" not in result
        assert "5 minutes" in result

    ## Fix#1
    def test_duration_string_with_hours_and_no_seconds_at_m_precision(self):
        # precision="m" gates seconds
        d = datetime.timedelta(hours=1, minutes=30, seconds=45)
        result = core_utils.duration_string(d, precision="m")
        assert "second" not in result
        assert "1 hour" in result
        assert "30 minutes" in result

    ## Fix#1
    def test_duration_string_zero_seconds_omits_seconds(self):
        # s > 0 branch: zero seconds not shown
        d = datetime.timedelta(hours=1, minutes=5)
        result = core_utils.duration_string(d)
        assert "second" not in result

    ## Fix#1
    def test_duration_string_partial_branch_minutes_always_shown(self):
        # "if m >= 0 and precision != 'h':" — m=0, precision='s' → show "0 minutes"
        d = datetime.timedelta(hours=2)
        result = core_utils.duration_string(d, precision="s")
        assert "0 minutes" in result

    ## Fix#1
    def test_duration_parts_zero_duration(self):
        d = datetime.timedelta(0)
        assert core_utils.duration_parts(d) == (0, 0, 0)

    ## Fix#1
    def test_duration_parts_exactly_one_hour(self):
        d = datetime.timedelta(hours=1)
        assert core_utils.duration_parts(d) == (1, 0, 0)

    ## Fix#1
    def test_timezone_aware_duration_returns_timedelta(self):
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 1, 1, 10, 0, tzinfo=utc)
        end = datetime.datetime(2026, 1, 1, 11, 30, tzinfo=utc)
        result = core_utils.timezone_aware_duration(start, end)
        assert result == datetime.timedelta(hours=1, minutes=30)

    ## Fix#2
    def test_duration_string_seconds_with_comma_separator(self):
        # partial branch line 49: "if duration != ''" before adding seconds
        # need a duration that has hours/minutes already in string
        d = datetime.timedelta(hours=1, minutes=2, seconds=3)
        result = core_utils.duration_string(d, precision="s")
        assert ", 3 seconds" in result

    ## Fix#2
    def test_duration_string_only_seconds_no_comma(self):
        # s > 0 but duration == "" (no hours, no minutes shown at h precision)
        # Actually with precision="s" and 0h 0m: "0 minutes, X seconds"
        # Test: only seconds, no preceding comma from hours
        d = datetime.timedelta(seconds=5)
        result = core_utils.duration_string(d, precision="s")
        assert "5 seconds" in result
        assert "0 minutes, 5 seconds" == result

    ## Fix#3
    def test_duration_string_zero_seconds_not_shown_at_s_precision(self):
        # s == 0 → False branch of "if s > 0 and precision != 'h' and precision != 'm'"
        d = datetime.timedelta(hours=1, minutes=5, seconds=0)
        result = core_utils.duration_string(d, precision="s")
        assert "second" not in result
        assert "1 hour" in result
        assert "5 minutes" in result


class TestCoreFieldsModule:
    def test_nap_start_max_time_field_rejects_value_below_minimum(self, monkeypatch):
        # target file: core/fields.py
        # function/method: NapStartMaxTimeField.validate
        # branch or behavior tested: invalid maximum earlier than configured minimum raises ValidationError
        fake_sleep = SimpleNamespace(settings=SimpleNamespace(nap_start_min=datetime.time(9, 0)))
        monkeypatch.setattr("core.models.Sleep", fake_sleep, raising=False)
        field = core_fields.NapStartMaxTimeField()

        with pytest.raises(django_forms.ValidationError) as exc_info:
            field.validate(datetime.time(8, 59))

        assert exc_info.value.code == "invalid_nap_start_max"

    def test_nap_start_min_time_field_rejects_value_above_maximum(self, monkeypatch):
        # target file: core/fields.py
        # function/method: NapStartMinTimeField.validate
        # branch or behavior tested: invalid minimum later than configured maximum raises ValidationError
        fake_sleep = SimpleNamespace(settings=SimpleNamespace(nap_start_max=datetime.time(17, 0)))
        monkeypatch.setattr("core.models.Sleep", fake_sleep, raising=False)
        field = core_fields.NapStartMinTimeField()

        with pytest.raises(django_forms.ValidationError) as exc_info:
            field.validate(datetime.time(17, 1))

        assert exc_info.value.code == "invalid_nap_start_min"

    def test_nap_time_fields_accept_boundary_values(self, monkeypatch):
        # target file: core/fields.py
        # function/method: NapStartMaxTimeField.validate / NapStartMinTimeField.validate
        # branch or behavior tested: exact configured boundaries are accepted
        fake_sleep = SimpleNamespace(
            settings=SimpleNamespace(
                nap_start_min=datetime.time(9, 0),
                nap_start_max=datetime.time(17, 0),
            )
        )
        monkeypatch.setattr("core.models.Sleep", fake_sleep, raising=False)

        core_fields.NapStartMaxTimeField().validate(datetime.time(9, 0))
        core_fields.NapStartMinTimeField().validate(datetime.time(17, 0))


class TestCoreFormsModule:
    def test_set_initial_values_returns_existing_instance_kwargs_unchanged(self):
        # target file: core/forms.py
        # function/method: set_initial_values
        # branch or behavior tested: existing instance short-circuits all initial-value mutation
        instance = object()
        kwargs = {"instance": instance, "child": "slug", "timer": 1}

        result = core_forms.set_initial_values(kwargs, core_forms.SleepForm)

        assert result is kwargs
        assert result["instance"] is instance
        assert result["child"] == "slug"
        assert result["timer"] == 1

    def test_set_initial_values_prefills_child_timer_feeding_and_sleep(self, monkeypatch):
        # target file: core/forms.py
        # function/method: set_initial_values
        # branch or behavior tested: child lookup, timer lookup, feeding defaults, sleep nap inference, and custom kwarg cleanup
        fixed_now = datetime.datetime(2026, 4, 1, 12, 0, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(slug="kid-a")
        timer = SimpleNamespace(id=9, start=datetime.datetime(2026, 4, 1, 9, 30, tzinfo=datetime.timezone.utc))
        last_feeding = SimpleNamespace(
            child=child,
            type="formula",
            method="bottle",
            end=datetime.datetime(2026, 4, 1, 11, 0, tzinfo=datetime.timezone.utc),
        )

        child_qs = FakeQuerySet([child])
        feeding_qs = FakeQuerySet([last_feeding])

        fake_models = SimpleNamespace(
            Child=SimpleNamespace(
                objects=SimpleNamespace(
                    filter=lambda **kwargs: child_qs.filter(**kwargs),
                    first=lambda: child,
                ),
                count=lambda: 2,
            ),
            Timer=SimpleNamespace(
                objects=SimpleNamespace(get=lambda id: timer),
                DoesNotExist=LookupError,
            ),
            Feeding=SimpleNamespace(
                objects=SimpleNamespace(
                    filter=lambda **kwargs: feeding_qs.filter(**kwargs)
                )
            ),
            Sleep=SimpleNamespace(
                settings=SimpleNamespace(
                    nap_start_min=datetime.time(9, 0),
                    nap_start_max=datetime.time(17, 0),
                )
            ),
        )
        monkeypatch.setattr(core_forms, "models", fake_models)
        monkeypatch.setattr(core_forms, "Timer", fake_models.Timer)
        monkeypatch.setattr(core_forms.timezone, "now", lambda: fixed_now)
        monkeypatch.setattr(core_forms.timezone, "localtime", lambda value=None: value or fixed_now)

        kwargs = {"child": "kid-a", "timer": 9}
        result = core_forms.set_initial_values(kwargs, core_forms.FeedingForm)

        assert result["initial"]["child"] is child
        assert result["initial"]["timer"] is timer
        assert result["initial"]["start"] == timer.start
        assert result["initial"]["end"] == fixed_now
        assert result["initial"]["type"] == "formula"
        assert result["initial"]["method"] == "bottle"
        assert "child" not in result
        assert "timer" not in result
        assert child_qs.filter_calls == [{"slug": "kid-a"}]
        assert feeding_qs.filter_calls == [{"child": child}]

        sleep_kwargs = {"initial": {"start": fixed_now.replace(hour=10)}}
        sleep_result = core_forms.set_initial_values(sleep_kwargs, core_forms.SleepForm)
        assert sleep_result["initial"]["nap"] is True

    def test_set_initial_values_uses_only_child_without_method_for_breastfeeding(self, monkeypatch):
        # target file: core/forms.py
        # function/method: set_initial_values
        # branch or behavior tested: left/right breast feeding carries type only, not bottle method
        child = SimpleNamespace(slug="kid-a")
        last_feeding = SimpleNamespace(
            child=child,
            type="breast milk",
            method="left breast",
            end=datetime.datetime(2026, 4, 1, 7, 45, tzinfo=datetime.timezone.utc),
        )

        feeding_qs = FakeQuerySet([last_feeding])

        fake_models = SimpleNamespace(
            Child=SimpleNamespace(
                objects=SimpleNamespace(first=lambda: child),
                count=lambda: 1,
            ),
            Timer=SimpleNamespace(
                objects=SimpleNamespace(get=lambda id: None),
                DoesNotExist=LookupError,
            ),
            Feeding=SimpleNamespace(
                objects=SimpleNamespace(
                    filter=lambda **kwargs: feeding_qs.filter(**kwargs)
                )
            ),
            Sleep=SimpleNamespace(
                settings=SimpleNamespace(
                    nap_start_min=datetime.time(9, 0),
                    nap_start_max=datetime.time(17, 0),
                )
            ),
        )
        monkeypatch.setattr(core_forms, "models", fake_models)
        monkeypatch.setattr(core_forms, "Timer", fake_models.Timer)
        monkeypatch.setattr(
            core_forms.timezone,
            "localtime",
            lambda value=None: value or datetime.datetime(2026, 4, 1, 8, 0, tzinfo=datetime.timezone.utc),
        )

        result = core_forms.set_initial_values({}, core_forms.FeedingForm)

        assert result["initial"]["child"] is child
        assert result["initial"]["type"] == "breast milk"
        assert "method" not in result["initial"]
        assert feeding_qs.filter_calls == [{"child": child}]

    def test_set_initial_values_ignores_missing_timer_and_marks_non_nap_by_default(self, monkeypatch):
        # target file: core/forms.py
        # function/method: set_initial_values
        # branch or behavior tested: missing timer is ignored and sleep nap defaults false outside configured window
        class FakeDoesNotExist(Exception):
            pass

        timer_get = Mock(side_effect=FakeDoesNotExist)

        fake_models = SimpleNamespace(
            Child=SimpleNamespace(objects=SimpleNamespace(first=lambda: None), count=lambda: 0),
            Timer=SimpleNamespace(
                objects=SimpleNamespace(get=timer_get),
                DoesNotExist=FakeDoesNotExist,
            ),
            Feeding=SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([]))),
            Sleep=SimpleNamespace(
                settings=SimpleNamespace(
                    nap_start_min=datetime.time(9, 0),
                    nap_start_max=datetime.time(17, 0),
                )
            ),
        )
        monkeypatch.setattr(core_forms, "models", fake_models)
        monkeypatch.setattr(core_forms, "Timer", fake_models.Timer)
        monkeypatch.setattr(
            core_forms.timezone,
            "localtime",
            lambda value=None: value or datetime.datetime(2026, 4, 1, 6, 30, tzinfo=datetime.timezone.utc),
        )

        result = core_forms.set_initial_values({"timer": 404}, core_forms.SleepForm)

        assert result["initial"]["nap"] is False
        assert "timer" not in result
        assert "start" not in result["initial"]
        timer_get.assert_called_once_with(id=404)

    def test_core_model_form_save_stops_timer_and_respects_commit_flag(self, monkeypatch):
        # target file: core/forms.py
        # function/method: CoreModelForm.save
        # branch or behavior tested: timer stop is invoked and save/save_m2m are gated by commit
        saved_instances = []
        timer = SimpleNamespace(stop=Mock())
        instance = SimpleNamespace(save=lambda: saved_instances.append("saved"))

        def fake_super_save(self, commit=False):
            assert commit is False
            return instance

        monkeypatch.setattr(django_forms.ModelForm, "save", fake_super_save)
        monkeypatch.setattr(core_forms.models.Timer.objects, "get", lambda id: timer)

        form = object.__new__(core_forms.CoreModelForm)
        form.timer_id = 99
        form.save_m2m = Mock()

        result = core_forms.CoreModelForm.save(form, commit=False)

        assert result is instance
        timer.stop.assert_called_once_with()
        assert saved_instances == []
        form.save_m2m.assert_not_called()

        timer.stop.reset_mock()
        result = core_forms.CoreModelForm.save(form, commit=True)
        assert result is instance
        timer.stop.assert_called_once_with()
        assert saved_instances == ["saved"]
        form.save_m2m.assert_called_once_with()

    def test_hydrated_fieldsets_preserves_layouts_and_returns_bound_fields(self):
        # target file: core/forms.py
        # function/method: CoreModelForm.hydrated_fielsets
        # branch or behavior tested: fieldset metadata and field ordering are preserved for rendering
        class DemoForm(core_forms.CoreModelForm):
            fieldsets = [
                {"fields": ["alpha", "beta"], "layout": "required", "layout_attrs": {"label": "Main"}},
                {"fields": ["gamma"]},
            ]

            def __iter__(self):
                return iter([DummyBoundField("alpha"), DummyBoundField("beta"), DummyBoundField("gamma")])

        form = object.__new__(DemoForm)
        hydrated = DemoForm.hydrated_fielsets.__get__(form, DemoForm)

        assert [fieldset["layout"] for fieldset in hydrated] == ["required", "default"]
        assert hydrated[0]["layout_attrs"] == {"label": "Main"}
        assert [field.name for field in hydrated[0]["fields"]] == ["alpha", "beta"]
        assert [field.name for field in hydrated[1]["fields"]] == ["gamma"]

    def test_bottle_feeding_form_clean_sets_end_from_start_only_when_present(self, monkeypatch):
        # target file: core/forms.py
        # function/method: BottleFeedingForm.clean
        # branch or behavior tested: start value is copied into instance.end only when available
        start = datetime.datetime(2026, 4, 1, 8, 0, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(django_forms.ModelForm, "clean", lambda self: {"start": start})
        form = object.__new__(core_forms.BottleFeedingForm)
        form.instance = SimpleNamespace(end=None)

        cleaned = core_forms.BottleFeedingForm.clean(form)

        assert cleaned["start"] == start
        assert form.instance.end == start

        monkeypatch.setattr(django_forms.ModelForm, "clean", lambda self: {})
        form.instance.end = "unchanged"
        cleaned = core_forms.BottleFeedingForm.clean(form)
        assert cleaned == {}
        assert form.instance.end == "unchanged"

    def test_bottle_feeding_form_save_forces_bottle_method_and_same_end(self, monkeypatch):
        # target file: core/forms.py
        # function/method: BottleFeedingForm.save
        # branch or behavior tested: bottle feed save overwrites method/end and respects commit flag
        start = datetime.datetime(2026, 4, 1, 8, 0, tzinfo=datetime.timezone.utc)
        instance = SimpleNamespace(start=start, method=None, end=None, save=Mock())
        monkeypatch.setattr(core_forms.CoreModelForm, "save", lambda self, commit=False: instance)

        form = object.__new__(core_forms.BottleFeedingForm)
        form.save_m2m = Mock()

        result = core_forms.BottleFeedingForm.save(form, commit=False)
        assert result is instance
        assert instance.method == "bottle"
        assert instance.end == start
        instance.save.assert_not_called()
        form.save_m2m.assert_not_called()

        result = core_forms.BottleFeedingForm.save(form, commit=True)
        assert result is instance
        instance.save.assert_called_once_with()
        form.save_m2m.assert_called_once_with()

    def test_child_delete_form_clean_confirm_name_validates_exact_match(self):
        # target file: core/forms.py
        # function/method: ChildDeleteForm.clean_confirm_name
        # branch or behavior tested: mismatched confirmation raises ValidationError and exact match passes
        class ChildInstance:
            def __str__(self):
                return "Alice Doe"

        form = object.__new__(core_forms.ChildDeleteForm)
        form.instance = ChildInstance()
        form.cleaned_data = {"confirm_name": "Alice Doe"}

        assert core_forms.ChildDeleteForm.clean_confirm_name(form) == "Alice Doe"

        form.cleaned_data = {"confirm_name": "Wrong Name"}
        with pytest.raises(django_forms.ValidationError) as exc_info:
            core_forms.ChildDeleteForm.clean_confirm_name(form)
        assert exc_info.value.code == "confirm_mismatch"

    def test_child_delete_form_save_deletes_instance_and_returns_original(self):
        # target file: core/forms.py
        # function/method: ChildDeleteForm.save
        # branch or behavior tested: delete side effect occurs and original instance is returned
        instance = SimpleNamespace(delete=Mock())
        form = object.__new__(core_forms.ChildDeleteForm)
        form.instance = instance

        result = core_forms.ChildDeleteForm.save(form)

        assert result is instance
        instance.delete.assert_called_once_with()

    def test_timer_form_requires_user_kwarg_and_assigns_user_on_save(self, monkeypatch):
        # target file: core/forms.py
        # function/method: TimerForm.__init__ / TimerForm.save
        # branch or behavior tested: user kwarg is consumed during init and assigned before save
        captured = {}

        def fake_core_init(self, *args, **kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(core_forms.CoreModelForm, "__init__", fake_core_init)
        user = SimpleNamespace(username="tester")
        form = core_forms.TimerForm(user=user, timer="ignored")
        assert form.user is user
        assert "user" not in captured
        assert captured["timer"] == "ignored"

        instance = SimpleNamespace(user=None, save=Mock())
        monkeypatch.setattr(core_forms.CoreModelForm, "save", lambda self, commit=False: instance)
        result = core_forms.TimerForm.save(form)
        assert result is instance
        assert instance.user is user
        instance.save.assert_called_once_with()

    ## Fix#1
    def test_set_initial_values_no_child_count_zero_does_not_set_child(self, monkeypatch):
        # elif models.Child.count() == 1 branch: count=0 → no child set
        fake_models = SimpleNamespace(
            Child=SimpleNamespace(objects=SimpleNamespace(first=lambda: None), count=lambda: 0),
            Timer=SimpleNamespace(objects=SimpleNamespace(get=lambda id: None), DoesNotExist=LookupError),
            Feeding=SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([]))),
            Sleep=SimpleNamespace(settings=SimpleNamespace(nap_start_min=datetime.time(9), nap_start_max=datetime.time(17))),
        )
        monkeypatch.setattr(core_forms, "models", fake_models)
        monkeypatch.setattr(core_forms, "Timer", fake_models.Timer)
        monkeypatch.setattr(core_forms.timezone, "localtime",
                            lambda v=None: v or datetime.datetime(2026, 4, 1, 8, 0, tzinfo=datetime.timezone.utc))

        result = core_forms.set_initial_values({}, core_forms.FeedingForm)
        assert "child" not in result.get("initial", {})

    ## Fix#1
    def test_set_initial_values_sleep_nap_false_outside_window(self, monkeypatch):
        # SleepForm branch: time outside nap window → nap=False
        fake_models = SimpleNamespace(
            Child=SimpleNamespace(objects=SimpleNamespace(first=lambda: None), count=lambda: 0),
            Timer=SimpleNamespace(objects=SimpleNamespace(get=lambda id: None), DoesNotExist=LookupError),
            Feeding=SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([]))),
            Sleep=SimpleNamespace(settings=SimpleNamespace(nap_start_min=datetime.time(9), nap_start_max=datetime.time(17))),
        )
        monkeypatch.setattr(core_forms, "models", fake_models)
        monkeypatch.setattr(core_forms, "Timer", fake_models.Timer)
        # 6am is outside the 9am-5pm nap window
        monkeypatch.setattr(core_forms.timezone, "localtime",
                            lambda v=None: v or datetime.datetime(2026, 4, 1, 6, 0, tzinfo=datetime.timezone.utc))

        result = core_forms.set_initial_values({}, core_forms.SleepForm)
        assert result["initial"]["nap"] is False

    ## Fix#1
    def test_set_initial_values_no_feeding_last_does_not_set_type(self, monkeypatch):
        # if last_feeding: branch — no last feeding → no type/method set
        child = SimpleNamespace(slug="kid")
        fake_models = SimpleNamespace(
            Child=SimpleNamespace(objects=SimpleNamespace(
                filter=lambda **kwargs: FakeQuerySet([child]),
                first=lambda: child,
            ), count=lambda: 1),
            Timer=SimpleNamespace(objects=SimpleNamespace(get=lambda id: None), DoesNotExist=LookupError),
            Feeding=SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([]))),
            Sleep=SimpleNamespace(settings=SimpleNamespace(nap_start_min=datetime.time(9), nap_start_max=datetime.time(17))),
        )
        monkeypatch.setattr(core_forms, "models", fake_models)
        monkeypatch.setattr(core_forms, "Timer", fake_models.Timer)
        monkeypatch.setattr(core_forms.timezone, "localtime",
                            lambda v=None: v or datetime.datetime(2026, 4, 1, 8, 0, tzinfo=datetime.timezone.utc))

        result = core_forms.set_initial_values({}, core_forms.FeedingForm)
        assert "type" not in result.get("initial", {})
        assert "method" not in result.get("initial", {})

    ## Fix#1
    def test_core_model_form_save_no_timer_does_not_call_get(self, monkeypatch):
        # if self.timer_id: branch — no timer_id → Timer.objects.get not called
        get_mock = Mock()
        instance = SimpleNamespace(save=Mock())
        monkeypatch.setattr(core_forms.models.Timer.objects, "get", get_mock)
        monkeypatch.setattr(core_forms.CoreModelForm.__bases__[0], "save", lambda self, commit=False: instance)

        form = object.__new__(core_forms.CoreModelForm)
        form.timer_id = None
        form.save_m2m = Mock()

        core_forms.CoreModelForm.save(form, commit=False)
        get_mock.assert_not_called()


class TestCoreViewsModule:
    def test_prepare_timeline_context_data_sets_previous_and_optional_next_dates(self, monkeypatch):
        # target file: core/views.py
        # function/method: _prepare_timeline_context_data
        # branch or behavior tested: parsed date populates timeline data and only past dates get a next-date link
        captured = []
        fake_date = datetime.datetime(2026, 4, 15, 0, 0, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(
            core_views.timezone,
            "datetime",
            SimpleNamespace(strptime=lambda value, fmt: datetime.datetime(2026, 4, 15, 0, 0)),
        )
        monkeypatch.setattr(core_views.timezone, "make_aware", lambda value: fake_date)
        monkeypatch.setattr(core_views.timezone, "localtime", lambda value: value)
        monkeypatch.setattr(core_views.timezone, "localdate", lambda: datetime.date(2026, 4, 17))
        monkeypatch.setattr(core_views.timeline, "get_objects", lambda date, child=None: captured.append((date, child)) or ["evt"])

        context = {}
        core_views._prepare_timeline_context_data(context, "2026-04-15", child="kid")

        assert context["timeline_objects"] == ["evt"]
        assert context["date"] == fake_date
        assert context["date_previous"] == fake_date - datetime.timedelta(days=1)
        assert context["date_next"] == fake_date + datetime.timedelta(days=1)
        assert captured == [(fake_date, "kid")]

        monkeypatch.setattr(core_views.timezone, "localdate", lambda: datetime.date(2026, 4, 15))
        today_context = {}
        core_views._prepare_timeline_context_data(today_context, "2026-04-15")
        assert "date_next" not in today_context

    def test_core_add_view_get_success_message_switches_on_child_presence(self):
        # target file: core/views.py
        # function/method: CoreAddView.get_success_message
        # branch or behavior tested: child-aware and generic success messages differ correctly
        class DemoView(core_views.CoreAddView):
            model = SimpleNamespace(_meta=SimpleNamespace(verbose_name="timer"))

        view = DemoView()
        with_child = view.get_success_message({"child": "Ava"})
        without_child = view.get_success_message({})

        assert with_child == "Timer entry for Ava added!"
        assert without_child == "Timer entry added!"

    def test_core_add_view_get_form_kwargs_includes_only_truthy_query_params(self, monkeypatch):
        # target file: core/views.py
        # function/method: CoreAddView.get_form_kwargs
        # branch or behavior tested: child/timer query params are forwarded only when supplied
        monkeypatch.setattr(core_views.CreateView, "get_form_kwargs", lambda self: {"base": True})

        class DemoView(core_views.CoreAddView):
            pass

        view = DemoView()
        view.request = SimpleNamespace(GET={"child": "kid-a", "timer": "8", "ignored": "x"})
        assert view.get_form_kwargs() == {"base": True, "child": "kid-a", "timer": "8"}

        view.request = SimpleNamespace(GET={"child": "", "timer": None})
        assert view.get_form_kwargs() == {"base": True}

    def test_core_update_and_delete_success_messages_are_specific(self):
        # target file: core/views.py
        # function/method: CoreUpdateView.get_success_message / CoreDeleteView.get_success_message / ChildDelete.get_success_message
        # branch or behavior tested: update and delete messages include the correct wording and model name
        class DemoUpdate(core_views.CoreUpdateView):
            model = SimpleNamespace(_meta=SimpleNamespace(verbose_name="temperature"))

        class DemoDelete(core_views.CoreDeleteView):
            model = SimpleNamespace(_meta=SimpleNamespace(verbose_name="temperature"))

        update_view = DemoUpdate()
        delete_view = DemoDelete()
        child_delete_view = core_views.ChildDelete()
        child_delete_view.model = SimpleNamespace(_meta=SimpleNamespace(verbose_name="child"))

        assert update_view.get_success_message({"child": "Ava"}) == "Temperature entry for Ava updated."
        assert update_view.get_success_message({}) == "Temperature entry updated."
        assert delete_view.get_success_message({}) == "Temperature entry deleted."
        assert child_delete_view.get_success_message({}) == "Child entry deleted."

    def test_timer_add_and_update_form_kwargs_include_request_user(self, monkeypatch):
        # target file: core/views.py
        # function/method: TimerAdd.get_form_kwargs / TimerUpdate.get_form_kwargs
        # branch or behavior tested: authenticated user is always injected into timer forms
        monkeypatch.setattr(core_views.CreateView, "get_form_kwargs", lambda self: {"base": 1})
        monkeypatch.setattr(core_views.UpdateView, "get_form_kwargs", lambda self: {"base": 2})
        user = SimpleNamespace(username="tester")

        add_view = core_views.TimerAdd()
        add_view.request = SimpleNamespace(user=user)
        assert add_view.get_form_kwargs() == {"base": 1, "user": user}

        update_view = core_views.TimerUpdate()
        update_view.request = SimpleNamespace(user=user)
        assert update_view.get_form_kwargs() == {"base": 2, "user": user}

    def test_timer_add_and_update_success_urls_target_detail_view(self, monkeypatch):
        # target file: core/views.py
        # function/method: TimerAdd.get_success_url / TimerUpdate.get_success_url
        # branch or behavior tested: timer detail redirect uses object primary key
        monkeypatch.setattr(core_views, "reverse", lambda name, kwargs=None, args=None: f"{name}:{kwargs['pk']}")

        add_view = core_views.TimerAdd()
        add_view.object = SimpleNamespace(pk=123)
        assert add_view.get_success_url() == "core:timer-detail:123"

        update_view = core_views.TimerUpdate()
        update_view.get_object = lambda: SimpleNamespace(pk=456)
        assert update_view.get_success_url() == "core:timer-detail:456"

    def test_timer_add_quick_sets_child_from_post_then_falls_back_to_single_child(self, monkeypatch):
        # target file: core/views.py
        # function/method: TimerAddQuick.post
        # branch or behavior tested: explicit child POST wins, otherwise single-child fallback is used, then redirect URL is resolved
        created = []
        explicit_child = SimpleNamespace(pk="7")
        fallback_child = SimpleNamespace(pk="1")

        class DummyTimer:
            def __init__(self, user):
                self.user = user
                self.child = None
                self.id = 55
                self.save = Mock()

        def create_timer(user):
            timer = DummyTimer(user)
            created.append(timer)
            return timer

        monkeypatch.setattr(core_views.models.Timer.objects, "create", create_timer)
        monkeypatch.setattr(core_views.models.Child.objects, "get", lambda pk: explicit_child)
        monkeypatch.setattr(core_views.models.Child, "count", lambda: 1)
        monkeypatch.setattr(core_views.models.Child.objects, "first", lambda: fallback_child)
        monkeypatch.setattr(core_views, "reverse", lambda name, args=None, kwargs=None: f"{name}:{next(iter(args))}")
        monkeypatch.setattr(core_views.RedirectView, "get", lambda self, request, *args, **kwargs: self.url)

        view = core_views.TimerAddQuick()
        request = SimpleNamespace(user="user-1", POST={"child": "7"}, GET={"next": "/done"})
        assert view.post(request) == "/done"
        assert created[-1].child is explicit_child
        created[-1].save.assert_called_once_with()

        view = core_views.TimerAddQuick()
        request = SimpleNamespace(user="user-2", POST={}, GET={})
        result = view.post(request)
        assert created[-1].child is fallback_child
        assert result == "core:timer-detail:55"

    def test_timer_restart_restarts_timer_pushes_message_and_redirects(self, monkeypatch):
        # target file: core/views.py
        # function/method: TimerRestart.post / TimerRestart.get_redirect_url
        # branch or behavior tested: timer restart side effect occurs before redirect generation
        class RestartableTimer:
            def restart(self):
                return self._restart()

            def __str__(self):
                return "Nap timer"

        timer = RestartableTimer()
        timer._restart = Mock()
        monkeypatch.setattr(core_views.models.Timer.objects, "get", lambda id: timer)
        success_messages = []
        monkeypatch.setattr(core_views.messages, "success", lambda request, message: success_messages.append((request, message)))
        monkeypatch.setattr(core_views.RedirectView, "get", lambda self, request, *args, **kwargs: "redirected")
        monkeypatch.setattr(core_views, "reverse", lambda name, kwargs=None, args=None: f"{name}:{kwargs['pk']}")

        view = core_views.TimerRestart()
        request = SimpleNamespace()
        assert view.post(request, pk=33) == "redirected"
        timer._restart.assert_called_once_with()
        assert success_messages == [(request, "Nap timer restarted.")]
        assert view.get_redirect_url(pk=33) == "core:timer-detail:33"

    ## Fix#1
    def test_prepare_timeline_context_no_next_date_when_today(self, monkeypatch):
        # Already tested — kept to confirm partial branch closed
        fake_date = datetime.datetime(2026, 4, 15, 0, 0, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(core_views.timezone, "datetime",
                            SimpleNamespace(strptime=lambda v, f: datetime.datetime(2026, 4, 15, 0, 0)))
        monkeypatch.setattr(core_views.timezone, "make_aware", lambda v: fake_date)
        monkeypatch.setattr(core_views.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_views.timezone, "localdate", lambda: datetime.date(2026, 4, 15))
        monkeypatch.setattr(core_views.timeline, "get_objects", lambda date, child=None: [])

        context = {}
        core_views._prepare_timeline_context_data(context, "2026-04-15")
        assert "date_next" not in context

    ## Fix#1
    def test_timeline_view_redirects_when_single_child(self, monkeypatch):
        # Timeline.get: children==1 → redirect to child detail
        monkeypatch.setattr(core_views.models.Child.objects, "count", lambda: 1)
        monkeypatch.setattr(core_views.models.Child.objects, "first",
                            lambda: SimpleNamespace(slug="ava"))
        monkeypatch.setattr(core_views, "reverse",
                            lambda name, args=None, kwargs=None: f"/core/children/ava/")

        view = core_views.Timeline()
        request = SimpleNamespace(GET={})
        view.request = request

        response = view.get(request)
        assert response.status_code == 302

    ## Fix#1
    def test_timeline_view_no_redirect_for_multiple_children(self, monkeypatch):
        # Timeline.get: children!=1 → calls super().get
        monkeypatch.setattr(core_views.models.Child.objects, "count", lambda: 2)

        class FakeSuperResponse:
            status_code = 200

        import django.views.generic.base as base_views
        monkeypatch.setattr(base_views.TemplateView, "get",
                            lambda self, request, *a, **kw: FakeSuperResponse())
        monkeypatch.setattr(core_views.timeline, "get_objects", lambda date, child=None: [])
        monkeypatch.setattr(core_views.timezone, "localdate", lambda: datetime.date(2026, 4, 15))
        monkeypatch.setattr(core_views.timezone, "datetime",
                            SimpleNamespace(strptime=lambda v, f: datetime.datetime(2026, 4, 15, 0, 0)))
        monkeypatch.setattr(core_views.timezone, "make_aware",
                            lambda v: datetime.datetime(2026, 4, 15, 0, 0, tzinfo=datetime.timezone.utc))
        monkeypatch.setattr(core_views.timezone, "localtime",
                            lambda v: datetime.datetime(2026, 4, 15, 0, 0, tzinfo=datetime.timezone.utc))

        view = core_views.Timeline()
        view.request = SimpleNamespace(GET={})
        view.kwargs = {}
        response = view.get(view.request)
        assert response.status_code == 200

    ## Fix#2
    def test_timeline_get_context_data_multiple_children(self, monkeypatch):
        # Timeline.get_context_data: calls _prepare_timeline_context_data
        fake_date = datetime.datetime(2026, 4, 15, 0, 0, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(core_views.timezone, "localdate",
                            lambda: datetime.date(2026, 4, 17))
        monkeypatch.setattr(core_views.timezone, "datetime",
                            SimpleNamespace(strptime=lambda v, f: datetime.datetime(2026, 4, 15, 0, 0)))
        monkeypatch.setattr(core_views.timezone, "make_aware", lambda v: fake_date)
        monkeypatch.setattr(core_views.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_views.timeline, "get_objects", lambda date, child=None: [])

        import django.views.generic.base as base_views
        monkeypatch.setattr(base_views.TemplateView, "get_context_data",
                            lambda self, **kw: {"object_list": []})

        view = core_views.Timeline()
        view.request = SimpleNamespace(GET={"date": "2026-04-15"})
        view.kwargs = {}
        view.object_list = []

        context = view.get_context_data()
        assert "timeline_objects" in context
        assert "date" in context


class TestCoreTimelineModule:
    def test_add_feedings_creates_start_and_end_events_for_duration_and_tracks_previous_feed(self, monkeypatch):
        # target file: core/timeline.py
        # function/method: _add_feedings
        # branch or behavior tested: prior-day feeding seeds time_since_prev and positive duration creates paired events
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")

        previous = SimpleNamespace(
            id=1,
            child=child,
            start=min_date - datetime.timedelta(hours=2),
            end=min_date - datetime.timedelta(hours=1, minutes=30),
            duration=datetime.timedelta(minutes=30),
            notes="night feed",
            amount=None,
            model_name="feeding",
            tags=SimpleNamespace(all=lambda: ["prev"]),
        )
        current = SimpleNamespace(
            id=2,
            child=child,
            start=min_date + datetime.timedelta(hours=3),
            end=min_date + datetime.timedelta(hours=3, minutes=20),
            duration=datetime.timedelta(minutes=20),
            notes="morning",
            amount=120,
            model_name="feeding",
            tags=SimpleNamespace(all=lambda: ["today"]),
        )

        manager_qs = FakeQuerySet([previous, current])
        monkeypatch.setattr(
            core_timeline,
            "Feeding",
            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: manager_qs.filter(**kwargs))),
        )
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda value: value)
        monkeypatch.setattr(core_timeline.timesince, "timesince", lambda start, now=None: "5 hours")
        monkeypatch.setattr(core_timeline, "duration_string", lambda value: "20 minutes")

        events = []
        core_timeline._add_feedings(min_date, max_date, events, child=child)

        assert len(events) == 2

        start_event, end_event = events

        assert start_event["type"] == "start"
        assert start_event["time_since_prev"] == "5 hours"
        assert "morning" in start_event["details"]
        assert "Amount: 120" in start_event["details"]
        assert start_event["edit_link"] == "core:feeding-update:2"

        assert end_event["type"] == "end"
        assert end_event["duration"] == "20 minutes"
        assert end_event["edit_link"] == "core:feeding-update:2"

    def test_add_feedings_uses_single_event_for_zero_duration_and_handles_empty_notes(self, monkeypatch):
        # target file: core/timeline.py
        # function/method: _add_feedings
        # branch or behavior tested: zero-duration feed emits one event without duration field
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        current = SimpleNamespace(
            id=3,
            child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=1),
            duration=datetime.timedelta(0),
            notes="",
            amount=None,
            model_name="feeding",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Feeding", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([current]))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda value: value)
        monkeypatch.setattr(core_timeline.timesince, "timesince", lambda start, now=None: "unused")

        events = []
        core_timeline._add_feedings(min_date, max_date, events)

        assert len(events) == 1
        event = events[0]
        assert event["event"] == "Ava had a feeding."
        assert "duration" not in event
        assert event["details"] == []

    def test_add_diaper_changes_encodes_contents_icons(self, monkeypatch):
        # target file: core/timeline.py
        # function/method: _add_diaper_changes
        # branch or behavior tested: wet and solid flags contribute expected emoji sequence
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        change = SimpleNamespace(
            id=8,
            child=child,
            time=min_date + datetime.timedelta(hours=1),
            wet=True,
            solid=True,
            model_name="diaperchange",
            tags=SimpleNamespace(all=lambda: ["tag"]),
        )
        monkeypatch.setattr(core_timeline, "DiaperChange", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([change]))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda value: value)

        events = []
        core_timeline._add_diaper_changes(min_date, max_date, events, child=child)

        assert events == [
            {
                "time": change.time,
                "event": "Ava had a 💧💩 diaper change.",
                "edit_link": "core:diaperchange-update:8",
                "model_name": "diaperchange",
                "tags": ["tag"],
            }
        ]

    def test_add_sleeps_and_tummy_times_include_duration_only_when_positive(self, monkeypatch):
        # target file: core/timeline.py
        # function/method: _add_sleeps / _add_tummy_times
        # branch or behavior tested: start/end events are emitted and duration is omitted for zero-length records
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        sleep = SimpleNamespace(
            id=4,
            child=child,
            start=min_date + datetime.timedelta(hours=2),
            end=min_date + datetime.timedelta(hours=3),
            duration=datetime.timedelta(hours=1),
            notes="slept well",
            model_name="sleep",
            tags=SimpleNamespace(all=lambda: []),
        )
        tummy = SimpleNamespace(
            id=5,
            child=child,
            start=min_date + datetime.timedelta(hours=4),
            end=min_date + datetime.timedelta(hours=4),
            duration=datetime.timedelta(0),
            milestone="rolled over",
            model_name="tummytime",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Sleep", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([sleep]))))
        monkeypatch.setattr(core_timeline, "TummyTime", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([tummy]))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda value: value)
        monkeypatch.setattr(core_timeline, "duration_string", lambda value: "1 hour")

        sleep_events = []
        core_timeline._add_sleeps(min_date, max_date, sleep_events)
        assert len(sleep_events) == 2
        assert sleep_events[1]["duration"] == "1 hour"
        assert sleep_events[0]["details"] == ["slept well"]

        tummy_events = []
        core_timeline._add_tummy_times(min_date, max_date, tummy_events)
        assert len(tummy_events) == 2
        assert tummy_events[0]["details"] == ["rolled over"]
        assert "duration" not in tummy_events[1]

    def test_add_notes_and_temperature_measurements_include_details_conditionally(self, monkeypatch):
        # target file: core/timeline.py
        # function/method: _add_notes / _add_temperature_measurements
        # branch or behavior tested: notes always populate details while temperature details depend on notes/value presence
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        note = SimpleNamespace(
            id=6,
            child=child,
            time=min_date + datetime.timedelta(hours=5),
            note="observed rash",
            model_name="note",
            tags=SimpleNamespace(all=lambda: ["important"]),
        )
        temp = SimpleNamespace(
            id=7,
            child=child,
            time=min_date + datetime.timedelta(hours=6),
            notes="after nap",
            temperature=101.5,
            model_name="temperature",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Note", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([note]))))
        monkeypatch.setattr(core_timeline, "Temperature", SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([temp]))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda value: value)

        note_events = []
        core_timeline._add_notes(min_date, max_date, note_events, child=child)
        assert note_events[0]["details"] == ["observed rash"]
        assert note_events[0]["tags"] == ["important"]

        temp_events = []
        core_timeline._add_temperature_measurements(min_date, max_date, temp_events, child=child)
        assert temp_events[0]["details"] == ["after nap", "Temperature: 101.5"]
        assert temp_events[0]["event"] == "Ava had a temperature measurement."

    def test_get_objects_calls_all_collectors_and_sorts_descending(self, monkeypatch):
        # target file: core/timeline.py
        # function/method: get_objects
        # branch or behavior tested: all collector functions run and final events are sorted in reverse chronological order
        call_order = []

        def add_named(name, when, event_type=None):
            def inner(min_date, max_date, events, child=None):
                call_order.append((name, min_date, max_date, child))
                payload = {"time": when, "event": name}
                if event_type is not None:
                    payload["type"] = event_type
                events.append(payload)
            return inner

        base = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(core_timeline, "_add_diaper_changes", add_named("diaper", base + datetime.timedelta(hours=1)))
        monkeypatch.setattr(core_timeline, "_add_feedings", add_named("feeding-start", base + datetime.timedelta(hours=2), "start"))
        monkeypatch.setattr(core_timeline, "_add_sleeps", add_named("sleep-end", base + datetime.timedelta(hours=2), "end"))
        monkeypatch.setattr(core_timeline, "_add_tummy_times", add_named("tummy", base + datetime.timedelta(hours=3)))
        monkeypatch.setattr(core_timeline, "_add_notes", add_named("note", base + datetime.timedelta(hours=4)))
        monkeypatch.setattr(core_timeline, "_add_temperature_measurements", add_named("temp", base + datetime.timedelta(hours=5)))

        events = core_timeline.get_objects(base, child="kid")

        assert [item[0] for item in call_order] == [
            "diaper",
            "feeding-start",
            "sleep-end",
            "tummy",
            "note",
            "temp",
        ]
        assert all(item[3] == "kid" for item in call_order)
        assert [event["event"] for event in events] == ["temp", "note", "tummy", "sleep-end", "feeding-start", "diaper"]

    ## Fix#1
    def test_add_feedings_no_child_filter_includes_all_children(self, monkeypatch):
        # child=None branch: no filter applied
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child_a = SimpleNamespace(first_name="Ava")
        child_b = SimpleNamespace(first_name="Ben")
        feeding = SimpleNamespace(
            id=1, child=child_a,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=1),
            duration=datetime.timedelta(0),
            notes="", amount=None, model_name="feeding",
            tags=SimpleNamespace(all=lambda: []),
        )
        qs = FakeQuerySet([feeding])
        monkeypatch.setattr(core_timeline, "Feeding",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: qs.filter(**kwargs))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline.timesince, "timesince", lambda s, now=None: "")

        events = []
        core_timeline._add_feedings(min_date, max_date, events, child=None)
        # No child filter applied — feeding should be included
        assert len(events) == 1

    ## Fix#1
    def test_add_sleeps_no_child_filter(self, monkeypatch):
        # child=None path for _add_sleeps
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        sleep = SimpleNamespace(
            id=1, child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=2),
            duration=datetime.timedelta(hours=1),
            notes="", model_name="sleep",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Sleep",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([sleep]).filter(**kwargs))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline, "duration_string", lambda v: "1 hour")

        events = []
        core_timeline._add_sleeps(min_date, max_date, events, child=None)
        assert len(events) == 2

    ## Fix#1
    def test_add_tummy_times_no_milestone(self, monkeypatch):
        # if instance.milestone: branch — no milestone → details empty
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        tummy = SimpleNamespace(
            id=1, child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=1, minutes=5),
            duration=datetime.timedelta(minutes=5),
            milestone="", model_name="tummytime",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "TummyTime",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([tummy]).filter(**kwargs))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline, "duration_string", lambda v: "5 minutes")

        events = []
        core_timeline._add_tummy_times(min_date, max_date, events)
        start_event = events[0]
        assert start_event["details"] == []

    ## Fix#1
    def test_add_sleeps_no_notes(self, monkeypatch):
        # if instance.notes: branch — empty notes → empty details
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        sleep = SimpleNamespace(
            id=2, child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=2),
            duration=datetime.timedelta(hours=1),
            notes="", model_name="sleep",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Sleep",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([sleep]).filter(**kwargs))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline, "duration_string", lambda v: "1 hour")

        events = []
        core_timeline._add_sleeps(min_date, max_date, events)
        assert events[0]["details"] == []

    ## Fix#1
    def test_add_temperature_no_notes_no_temperature(self, monkeypatch):
        # both "if instance.notes" and "if instance.temperature" false → empty details
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        temp = SimpleNamespace(
            id=1, child=child,
            time=min_date + datetime.timedelta(hours=1),
            notes="", temperature=None,
            model_name="temperature",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Temperature",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([temp]).filter(**kwargs))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_temperature_measurements(min_date, max_date, events, child=child)
        assert events[0]["details"] == []

    ## Fix#1
    def test_add_diaper_change_wet_only(self, monkeypatch):
        # wet=True, solid=False → only 💧
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        change = SimpleNamespace(
            id=1, child=child,
            time=min_date + datetime.timedelta(hours=1),
            wet=True, solid=False,
            model_name="diaperchange",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "DiaperChange",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kwargs: FakeQuerySet([change]).filter(**kwargs))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_diaper_changes(min_date, max_date, events, child=child)
        assert "💧" in events[0]["event"]
        assert "💩" not in events[0]["event"]

    ## Fix#1
    def test_get_objects_max_date_replaces_time_correctly(self, monkeypatch):
        # max_date = date.replace(hour=23, minute=59, second=59)
        base = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        captured = {}

        def fake_add(min_date, max_date, events, child=None):
            captured["max"] = max_date

        for attr in ["_add_diaper_changes", "_add_feedings", "_add_sleeps",
                     "_add_tummy_times", "_add_notes", "_add_temperature_measurements"]:
            monkeypatch.setattr(core_timeline, attr, fake_add)

        core_timeline.get_objects(base)
        assert captured["max"].hour == 23
        assert captured["max"].minute == 59
        assert captured["max"].second == 59

    ## Fix#2
    def test_add_tummy_times_child_filter_applied_when_child_given(self, monkeypatch):
        # partial branch: child given → instances.filter(child=child) called
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        tummy = SimpleNamespace(
            id=1, child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=1, minutes=5),
            duration=datetime.timedelta(minutes=5),
            milestone="rolled over", model_name="tummytime",
            tags=SimpleNamespace(all=lambda: []),
        )
        qs = FakeQuerySet([tummy])
        filter_calls = []
        orig_filter = qs.filter

        def tracking_filter(**kwargs):
            filter_calls.append(kwargs)
            return orig_filter(**kwargs)
        qs.filter = tracking_filter

        monkeypatch.setattr(core_timeline, "TummyTime",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: qs.filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline, "duration_string", lambda v: "5 minutes")

        events = []
        core_timeline._add_tummy_times(min_date, max_date, events, child=child)
        assert len(events) == 2

    ## Fix#2
    def test_add_diaper_changes_no_child_includes_all(self, monkeypatch):
        # partial branch: child=None → no filter
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        change = SimpleNamespace(
            id=1, child=child,
            time=min_date + datetime.timedelta(hours=1),
            wet=True, solid=False, model_name="diaperchange",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "DiaperChange",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: FakeQuerySet([change]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_diaper_changes(min_date, max_date, events, child=None)
        assert len(events) == 1

    ## Fix#2
    def test_add_notes_no_child_includes_all(self, monkeypatch):
        # partial branch: child=None → no filter
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        note = SimpleNamespace(
            id=1, child=child,
            time=min_date + datetime.timedelta(hours=1),
            note="test note", model_name="note",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Note",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: FakeQuerySet([note]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_notes(min_date, max_date, events, child=None)
        assert len(events) == 1

    ## Fix#2
    def test_add_temperature_no_child_includes_all(self, monkeypatch):
        # partial branch: child=None → no filter
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        temp = SimpleNamespace(
            id=1, child=child,
            time=min_date + datetime.timedelta(hours=1),
            notes="", temperature=98.6, model_name="temperature",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Temperature",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: FakeQuerySet([temp]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_temperature_measurements(min_date, max_date, events, child=None)
        assert len(events) == 1

    ## Fix#2
    def test_add_feedings_child_filter_skipped_when_no_child(self, monkeypatch):
        # partial branch: child=None path for feedings
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        feeding = SimpleNamespace(
            id=1, child=child,
            start=min_date + datetime.timedelta(hours=2),
            end=min_date + datetime.timedelta(hours=2),
            duration=datetime.timedelta(0),
            notes="", amount=None, model_name="feeding",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Feeding",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: FakeQuerySet([feeding]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline.timesince, "timesince", lambda s, now=None: "")

        events = []
        core_timeline._add_feedings(min_date, max_date, events, child=None)
        assert len(events) == 1

    ## Fix#2
    def test_add_sleeps_with_child_filter(self, monkeypatch):
        # partial branch: child given → filter applied
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        sleep = SimpleNamespace(
            id=1, child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=2),
            duration=datetime.timedelta(hours=1),
            notes="deep sleep", model_name="sleep",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "Sleep",
                            SimpleNamespace(objects=SimpleNamespace(filter=lambda **kw: FakeQuerySet([sleep]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)
        monkeypatch.setattr(core_timeline, "duration_string", lambda v: "1 hour")

        events = []
        core_timeline._add_sleeps(min_date, max_date, events, child=child)
        assert len(events) == 2
        assert events[0]["details"] == ["deep sleep"]

    ## Fix#3
    def test_add_tummy_times_zero_duration_omits_duration_key(self, monkeypatch):
        # partial line 115: "if instance.duration > timedelta(seconds=0)" — False branch
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        tummy = SimpleNamespace(
            id=1, child=child,
            start=min_date + datetime.timedelta(hours=1),
            end=min_date + datetime.timedelta(hours=1),  # same start/end → zero duration
            duration=datetime.timedelta(0),
            milestone="", model_name="tummytime",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "TummyTime",
                            SimpleNamespace(objects=SimpleNamespace(
                                filter=lambda **kw: FakeQuerySet([tummy]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_tummy_times(min_date, max_date, events, child=child)
        end_event = events[1]
        assert "duration" not in end_event

    ## Fix#3
    def test_add_diaper_changes_solid_false_omits_poo_icon(self, monkeypatch):
        # partial line 189: "if instance.solid" — False branch (solid=False)
        min_date = datetime.datetime(2026, 4, 10, 0, 0, tzinfo=datetime.timezone.utc)
        max_date = datetime.datetime(2026, 4, 10, 23, 59, tzinfo=datetime.timezone.utc)
        child = SimpleNamespace(first_name="Ava")
        change = SimpleNamespace(
            id=1, child=child,
            time=min_date + datetime.timedelta(hours=1),
            wet=False, solid=False,  # both False → empty contents
            model_name="diaperchange",
            tags=SimpleNamespace(all=lambda: []),
        )
        monkeypatch.setattr(core_timeline, "DiaperChange",
                            SimpleNamespace(objects=SimpleNamespace(
                                filter=lambda **kw: FakeQuerySet([change]).filter(**kw))))
        monkeypatch.setattr(core_timeline, "reverse", lambda name, args=None: f"{name}:{args[0]}")
        monkeypatch.setattr(core_timeline.timezone, "localtime", lambda v: v)

        events = []
        core_timeline._add_diaper_changes(min_date, max_date, events, child=child)
        assert "💩" not in events[0]["event"]
        assert "💧" not in events[0]["event"]

class TestCoreModelsModule:
    """Targets: core/models.py"""

    # --- validate_date ---
    ## Fix#1
    def test_validate_date_future_date_raises(self, monkeypatch):
        from core.models import validate_date
        monkeypatch.setattr("core.models.timezone.localdate", lambda: datetime.date(2026, 4, 15))
        with pytest.raises(ValidationError) as exc:
            validate_date(datetime.date(2026, 4, 16), "date")
        assert "date" in exc.value.message_dict

    ## Fix#1
    def test_validate_date_past_date_passes(self, monkeypatch):
        from core.models import validate_date
        monkeypatch.setattr("core.models.timezone.localdate",
                            lambda: datetime.date(2026, 4, 15))
        validate_date(datetime.date(2026, 4, 14), "date")  # no exception

    ## Fix#1
    def test_validate_date_none_passes(self, monkeypatch):
        from core.models import validate_date
        monkeypatch.setattr("core.models.timezone.localdate",
                            lambda: datetime.date(2026, 4, 15))
        validate_date(None, "date")  # no exception

    ## Fix#1
    def test_validate_date_today_passes(self, monkeypatch):
        from core.models import validate_date
        today = datetime.date(2026, 4, 15)
        monkeypatch.setattr("core.models.timezone.localdate", lambda: today)
        validate_date(today, "date")  # today is not in the future

    ## Fix#1
    def test_validate_date_error_uses_field_name_as_key(self, monkeypatch):
        from core.models import validate_date
        monkeypatch.setattr("core.models.timezone.localdate", lambda: datetime.date(2026, 4, 15))
        with pytest.raises(ValidationError) as exc:
            validate_date(datetime.date(2026, 4, 16), "my_field")
        assert "my_field" in exc.value.message_dict

    # --- validate_time ---
    ## Fix#1
    def test_validate_time_future_time_raises(self, monkeypatch):
        from core.models import validate_time
        utc = datetime.timezone.utc
        now = datetime.datetime(2026, 4, 15, 10, 0, tzinfo=utc)
        future = datetime.datetime(2026, 4, 15, 11, 0, tzinfo=utc)
        monkeypatch.setattr("core.models.timezone.localtime", lambda: now)
        with pytest.raises(ValidationError) as exc:
            validate_time(future, "time")
        assert "time" in exc.value.message_dict

    ## Fix#1
    def test_validate_time_past_time_passes(self, monkeypatch):
        from core.models import validate_time
        utc = datetime.timezone.utc
        now = datetime.datetime(2026, 4, 15, 10, 0, tzinfo=utc)
        past = datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc)
        monkeypatch.setattr("core.models.timezone.localtime", lambda: now)
        validate_time(past, "time")  # no exception

    ## Fix#1
    def test_validate_time_none_passes(self, monkeypatch):
        from core.models import validate_time
        validate_time(None, "time")  # no exception

    ## Fix#1
    def test_validate_time_error_uses_field_name(self, monkeypatch):
        from core.models import validate_time
        utc = datetime.timezone.utc
        now = datetime.datetime(2026, 4, 15, 10, 0, tzinfo=utc)
        future = datetime.datetime(2026, 4, 15, 11, 0, tzinfo=utc)
        monkeypatch.setattr("core.models.timezone.localtime", lambda: now)
        with pytest.raises(ValidationError) as exc:
            validate_time(future, "start")
        assert "start" in exc.value.message_dict

    # --- validate_duration ---
    ## Fix#1
    def test_validate_duration_end_before_start_raises(self):
        from core.models import validate_duration
        utc = datetime.timezone.utc
        model = SimpleNamespace(
            start=datetime.datetime(2026, 4, 15, 10, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        with pytest.raises(ValidationError) as exc:
            validate_duration(model)
        assert exc.value.code == "end_before_start"

    ## Fix#1
    def test_validate_duration_exceeds_max_raises(self):
        from core.models import validate_duration
        utc = datetime.timezone.utc
        model = SimpleNamespace(
            start=datetime.datetime(2026, 4, 15, 0, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 16, 1, 0, tzinfo=utc),  # 25 hours later
        )
        with pytest.raises(ValidationError) as exc:
            validate_duration(model)
        assert exc.value.code == "max_duration"

    ## Fix#1
    def test_validate_duration_valid_passes(self):
        from core.models import validate_duration
        utc = datetime.timezone.utc
        model = SimpleNamespace(
            start=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        validate_duration(model)  # no exception

    ## Fix#1
    def test_validate_duration_none_start_skips(self):
        from core.models import validate_duration
        model = SimpleNamespace(start=None, end=datetime.datetime(2026, 4, 15, 9, 0))
        validate_duration(model)  # no exception

    ## Fix#1
    def test_validate_duration_custom_max(self):
        from core.models import validate_duration
        utc = datetime.timezone.utc
        model = SimpleNamespace(
            start=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        # 1 hour exceeds 30 minute max
        with pytest.raises(ValidationError) as exc:
            validate_duration(model, max_duration=datetime.timedelta(minutes=30))
        assert exc.value.code == "max_duration"

    # --- validate_unique_period ---
    ## Fix#1
    def test_validate_unique_period_no_conflict_passes(self, monkeypatch):
        from core.models import validate_unique_period
        utc = datetime.timezone.utc
        model = SimpleNamespace(
            id=None,
            start=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        qs = FakeQuerySet([])
        validate_unique_period(qs, model)  # no exception

    ## Fix#1
    def test_validate_unique_period_with_conflict_raises(self, monkeypatch):
        from core.models import validate_unique_period, _format_dt
        utc = datetime.timezone.utc
        conflicting = SimpleNamespace(
            id=99,
            model_name="sleep",
            start=datetime.datetime(2026, 4, 15, 8, 30, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 30, tzinfo=utc),
        )

        class ConflictingQS:
            def exclude(self, **kwargs):
                return self
            def filter(self, **kwargs):
                return self
            def first(self):
                return conflicting

        model = SimpleNamespace(
            id=1,
            start=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        monkeypatch.setattr("core.models.reverse",
                            lambda name, args=None: f"/core/sleep/{args[0]}/edit/")
        monkeypatch.setattr("core.models.formats.date_format",
                            lambda v, format: "formatted")
        monkeypatch.setattr("core.models.timezone.localtime", lambda v: v)

        with pytest.raises(ValidationError) as exc:
            validate_unique_period(ConflictingQS(), model)
        assert exc.value.code == "period_intersection"

    ## Fix#1
    def test_validate_unique_period_excludes_self_when_id_set(self, monkeypatch):
        from core.models import validate_unique_period
        utc = datetime.timezone.utc
        excluded = []

        class TrackingQS:
            def exclude(self, **kwargs):
                excluded.append(kwargs)
                return FakeQuerySet([])
            def filter(self, **kwargs):
                return FakeQuerySet([])

        model = SimpleNamespace(
            id=42,
            start=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        validate_unique_period(TrackingQS(), model)
        assert excluded == [{"id": 42}]

    ## Fix#1
    def test_validate_unique_period_no_id_does_not_exclude(self, monkeypatch):
        from core.models import validate_unique_period
        utc = datetime.timezone.utc
        excluded = []

        class TrackingQS:
            def exclude(self, **kwargs):
                excluded.append(kwargs)
                return FakeQuerySet([])
            def filter(self, **kwargs):
                return FakeQuerySet([])

        model = SimpleNamespace(
            id=None,
            start=datetime.datetime(2026, 4, 15, 8, 0, tzinfo=utc),
            end=datetime.datetime(2026, 4, 15, 9, 0, tzinfo=utc),
        )
        validate_unique_period(TrackingQS(), model)
        assert excluded == []

    # --- Tag.complementary_color ---
    ## Fix#1
    def test_tag_complementary_color_light_color_returns_dark(self, monkeypatch):
        from core.models import Tag
        tag = object.__new__(Tag)
        tag.__dict__["color"] = "#FFFFFF"  # white → YIQ high → DARK
        assert tag.complementary_color == Tag.DARK_COLOR

    ## Fix#1
    def test_tag_complementary_color_dark_color_returns_light(self, monkeypatch):
        from core.models import Tag
        tag = object.__new__(Tag)
        tag.__dict__["color"] = "#000000"  # black → YIQ low → LIGHT
        assert tag.complementary_color == Tag.LIGHT_COLOR

    ## Fix#1
    def test_tag_complementary_color_no_color_returns_dark(self, monkeypatch):
        from core.models import Tag
        tag = object.__new__(Tag)
        tag.__dict__["color"] = ""
        assert tag.complementary_color == Tag.DARK_COLOR

    ## Fix#1
    def test_tag_complementary_color_yiq_boundary_128_returns_dark(self):
        from core.models import Tag
        # Craft a color where YIQ == 128 → DARK_COLOR
        # YIQ = (r*299 + g*587 + b*114) // 1000 = 128
        # Use r=0, g=0, b=1122 (not valid)... use approximate: #808080 gray
        # For #808080: r=g=b=128 → (128*299 + 128*587 + 128*114)//1000 = (38272+75136+14592)//1000 = 128000//1000 = 128
        tag = object.__new__(Tag)
        tag.__dict__["color"] = "#808080"
        assert tag.complementary_color == Tag.DARK_COLOR

    # --- Child.name ---
    ## Fix#1
    def test_child_name_no_last_name_returns_first_only(self):
        from core.models import Child
        child = object.__new__(Child)
        child.__dict__.update({"first_name": "Alice", "last_name": ""})
        assert child.name() == "Alice"

    ## Fix#1
    def test_child_name_with_last_name_returns_full_name(self):
        from core.models import Child
        child = object.__new__(Child)
        child.__dict__.update({"first_name": "Alice", "last_name": "Doe"})
        assert child.name() == "Alice Doe"

    ## Fix#1
    def test_child_name_reverse_true_returns_last_first(self):
        from core.models import Child
        child = object.__new__(Child)
        child.__dict__.update({"first_name": "Alice", "last_name": "Doe"})
        assert child.name(reverse=True) == "Doe, Alice"

    # --- Child.birth_datetime ---
    ## Fix#1
    def test_child_birth_datetime_with_time(self, monkeypatch):
        from core.models import Child
        child = object.__new__(Child)
        child.__dict__.update({
            "birth_date": datetime.date(2020, 1, 1),
            "birth_time": datetime.time(8, 30),
        })
        aware = datetime.datetime(2020, 1, 1, 8, 30, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr("core.models.timezone.make_aware", lambda v: aware)
        assert child.birth_datetime() == aware

    ## Fix#1
    def test_child_birth_datetime_without_time_returns_date(self):
        from core.models import Child
        child = object.__new__(Child)
        child.__dict__.update({
            "birth_date": datetime.date(2020, 1, 1),
            "birth_time": None,
        })
        assert child.birth_datetime() == datetime.date(2020, 1, 1)

    # --- Timer.__str__ ---
    ## Fix#1
    def test_timer_str_with_name(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer.__dict__["name"] = "Nap Timer"
        timer.__dict__["id"] = 1
        assert str(timer) == "Nap Timer"

    ## Fix#1
    def test_timer_str_without_name_uses_id(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer.__dict__["name"] = None
        timer.__dict__["id"] = 7
        result = str(timer)
        assert "7" in result

    # --- Timer.title_with_child ---
    ## Fix#1
    def test_timer_title_with_child_multiple_children(self, monkeypatch):
        from core.models import Timer, Child

        class FakeChild:
            def __str__(self):
                return "Ava"

        timer = object.__new__(Timer)
        timer._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        timer.__dict__["name"] = "Feeding"
        timer.__dict__["id"] = 1
        monkeypatch.setattr(Timer, "child", property(lambda self: FakeChild()))
        monkeypatch.setattr(Child, "count", classmethod(lambda cls: 2))
        result = str(timer.title_with_child)
        assert "Feeding" in result
        assert "Ava" in result

    ## Fix#1
    def test_timer_title_with_child_single_child_no_append(self, monkeypatch):
        from core.models import Timer, Child
        timer = object.__new__(Timer)
        timer._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        timer.__dict__["name"] = "Feeding"
        timer.__dict__["id"] = 1
        child = SimpleNamespace(__str__=lambda self: "Ava")
        monkeypatch.setattr(Timer, "child", property(lambda self: child))
        monkeypatch.setattr(Child, "count", classmethod(lambda cls: 1))
        result = str(timer.title_with_child)
        assert result == "Feeding"

    ## Fix#1
    def test_timer_title_no_child(self, monkeypatch):
        from core.models import Timer, Child
        timer = object.__new__(Timer)
        timer._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        timer.__dict__["name"] = "Feeding"
        timer.__dict__["id"] = 1
        monkeypatch.setattr(Timer, "child", property(lambda self: None))
        monkeypatch.setattr(Child, "count", classmethod(lambda cls: 2))
        result = str(timer.title_with_child)
        assert result == "Feeding"

    # --- Timer.user_username ---
    ## Fix#1
    def test_timer_user_username_prefers_full_name(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        user = SimpleNamespace(get_full_name=lambda: "Alice Doe", get_username=lambda: "alice")
        monkeypatch.setattr(Timer, "user", property(lambda self: user))
        assert timer.user_username == "Alice Doe"

    ## Fix#1
    def test_timer_user_username_falls_back_to_username(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        user = SimpleNamespace(get_full_name=lambda: "", get_username=lambda: "alice")
        monkeypatch.setattr(Timer, "user", property(lambda self: user))
        assert timer.user_username == "alice"

    # --- Timer.save (name=None coercion) ---
    ## Fix#1
    def test_timer_save_empty_name_coerced_to_none(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer.__dict__["name"] = ""
        saved = []
        import django.db.models as djmodels
        monkeypatch.setattr(djmodels.Model, "save", lambda self, *a, **kw: saved.append(True))
        Timer.save(timer)
        assert timer.name is None

    ## Fix#1
    def test_timer_save_existing_name_preserved(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer.__dict__["name"] = "My Timer"
        import django.db.models as djmodels
        monkeypatch.setattr(djmodels.Model, "save", lambda self, *a, **kw: None)
        Timer.save(timer)
        assert timer.name == "My Timer"

    # --- WeightPercentile.__str__ ---
    ## Fix#1
    def test_weight_percentile_str_contains_all_fields(self):
        from core.models import WeightPercentile
        wp = object.__new__(WeightPercentile)
        wp.__dict__.update({
            "sex": "girl",
            "age_in_days": datetime.timedelta(days=100),
            "p3_weight": 3.5,
            "p15_weight": 4.0,
            "p50_weight": 5.0,
            "p85_weight": 6.0,
            "p97_weight": 7.0,
        })
        result = str(wp)
        assert "girl" in result
        assert "3.5" in result
        assert "5.0" in result

    # --- __str__ methods for all uncovered models ---
    ## Fix#2
    def test_bmi_str(self):
        from core.models import BMI
        obj = object.__new__(BMI)
        assert "BMI" in str(obj)

    ## Fix#2
    def test_diaper_change_str(self):
        from core.models import DiaperChange
        obj = object.__new__(DiaperChange)
        assert "Diaper" in str(obj)

    ## Fix#2
    def test_feeding_str(self):
        from core.models import Feeding
        obj = object.__new__(Feeding)
        assert "Feeding" in str(obj)

    ## Fix#2
    def test_head_circumference_str(self):
        from core.models import HeadCircumference
        obj = object.__new__(HeadCircumference)
        assert "Head" in str(obj)

    ## Fix#2
    def test_height_str(self):
        from core.models import Height
        obj = object.__new__(Height)
        assert "Height" in str(obj)

    ## Fix#2
    def test_note_str(self):
        from core.models import Note
        obj = object.__new__(Note)
        assert "Note" in str(obj)

    ## Fix#2
    def test_pumping_str(self):
        from core.models import Pumping
        obj = object.__new__(Pumping)
        assert "Pumping" in str(obj)

    ## Fix#2
    def test_sleep_str(self):
        from core.models import Sleep
        obj = object.__new__(Sleep)
        assert "Sleep" in str(obj)

    ## Fix#2
    def test_temperature_str(self):
        from core.models import Temperature
        obj = object.__new__(Temperature)
        assert "Temperature" in str(obj)

    ## Fix#2
    def test_tummy_time_str(self):
        from core.models import TummyTime
        obj = object.__new__(TummyTime)
        assert "Tummy" in str(obj)

    ## Fix#2
    def test_weight_str(self):
        from core.models import Weight
        obj = object.__new__(Weight)
        assert "Weight" in str(obj)

    # --- DiaperChange.attributes ---
    ## Fix#2
    def test_diaper_change_attributes_wet_solid_and_color(self, monkeypatch):
        from core.models import DiaperChange
        obj = object.__new__(DiaperChange)
        obj._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        obj.__dict__.update({"wet": True, "solid": True, "color": "yellow"})

        wet_field = SimpleNamespace(verbose_name="Wet")
        solid_field = SimpleNamespace(verbose_name="Solid")
        monkeypatch.setattr(DiaperChange, "_meta",
                            SimpleNamespace(get_field=lambda name: wet_field if name == "wet" else solid_field))
        monkeypatch.setattr(DiaperChange, "get_color_display", lambda self: "Yellow")

        result = obj.attributes()
        assert "Wet" in result
        assert "Solid" in result
        assert "Yellow" in result

    ## Fix#2
    def test_diaper_change_attributes_empty(self, monkeypatch):
        from core.models import DiaperChange
        obj = object.__new__(DiaperChange)
        obj._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        obj.__dict__.update({"wet": False, "solid": False, "color": ""})
        monkeypatch.setattr(DiaperChange, "_meta", SimpleNamespace(get_field=lambda name: None))
        result = obj.attributes()
        assert result == []

    # --- Timer.duration ---
    ## Fix#2
    def test_timer_duration_returns_elapsed_time(self, monkeypatch):
        from core.models import Timer
        timer = object.__new__(Timer)
        timer._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 4, 15, 10, 0, tzinfo=utc)
        now = datetime.datetime(2026, 4, 15, 11, 30, tzinfo=utc)
        timer.__dict__["start"] = start
        monkeypatch.setattr("core.models.timezone.now", lambda: now)
        result = timer.duration()
        assert result == datetime.timedelta(hours=1, minutes=30)

    # --- Sleep.save nap inference ---
    ## Fix#2
    def test_sleep_save_infers_nap_true_when_within_window(self, monkeypatch):
        from core.models import Sleep
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 4, 15, 12, 0, tzinfo=utc)  # noon — within 9-17 window

        sleep = object.__new__(Sleep)
        sleep._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        sleep.__dict__.update({"nap": None, "start": start, "end": start})

        monkeypatch.setattr("core.models.Sleep.settings",
                            SimpleNamespace(nap_start_min=datetime.time(9), nap_start_max=datetime.time(17)))
        monkeypatch.setattr("core.models.timezone.localtime", lambda v: v)
        monkeypatch.setattr("core.models.timezone_aware_duration", lambda s, e: datetime.timedelta(0))
        import django.db.models as djmodels
        monkeypatch.setattr(djmodels.Model, "save", lambda self, *a, **kw: None)

        Sleep.save(sleep)
        assert sleep.nap is True

    ## Fix#2
    def test_sleep_save_infers_nap_false_when_outside_window(self, monkeypatch):
        from core.models import Sleep
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 4, 15, 6, 0, tzinfo=utc)  # 6am — before 9am window

        sleep = object.__new__(Sleep)
        sleep._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        sleep.__dict__.update({"nap": None, "start": start, "end": start})

        monkeypatch.setattr("core.models.Sleep.settings",
                            SimpleNamespace(nap_start_min=datetime.time(9), nap_start_max=datetime.time(17)))
        monkeypatch.setattr("core.models.timezone.localtime", lambda v: v)
        monkeypatch.setattr("core.models.timezone_aware_duration", lambda s, e: datetime.timedelta(0))
        import django.db.models as djmodels
        monkeypatch.setattr(djmodels.Model, "save", lambda self, *a, **kw: None)

        Sleep.save(sleep)
        assert sleep.nap is False

    ## Fix#2
    def test_sleep_save_preserves_explicit_nap_value(self, monkeypatch):
        from core.models import Sleep
        utc = datetime.timezone.utc
        start = datetime.datetime(2026, 4, 15, 12, 0, tzinfo=utc)

        sleep = object.__new__(Sleep)
        sleep._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        sleep.__dict__.update({"nap": False, "start": start, "end": start})  # explicit False

        monkeypatch.setattr("core.models.timezone_aware_duration", lambda s, e: datetime.timedelta(0))
        import django.db.models as djmodels
        monkeypatch.setattr(djmodels.Model, "save", lambda self, *a, **kw: None)

        Sleep.save(sleep)
        assert sleep.nap is False  # not overridden

    ## Fix#3
    def test_validate_unique_period_skips_filter_when_start_is_none(self):
        # partial line 68: model.start is None → False branch → no filter call
        from core.models import validate_unique_period

        class TrackingQS:
            def exclude(self, **kwargs):
                return self
            def filter(self, **kwargs):
                raise AssertionError("filter should not be called")

        model = SimpleNamespace(id=None, start=None, end=datetime.datetime(2026, 4, 15, 9, 0))
        validate_unique_period(TrackingQS(), model)  # no exception, no filter call

    ## Fix#3
    def test_validate_unique_period_skips_filter_when_end_is_none(self):
        # model.end is None → False branch
        from core.models import validate_unique_period

        class TrackingQS:
            def exclude(self, **kwargs):
                return self
            def filter(self, **kwargs):
                raise AssertionError("filter should not be called")

        model = SimpleNamespace(id=None,
                                start=datetime.datetime(2026, 4, 15, 8, 0),
                                end=None)
        validate_unique_period(TrackingQS(), model)  # no exception

    ## Fix#3
    def test_sleep_save_skips_duration_when_start_is_none(self, monkeypatch):
        # partial line 574: "if self.start and self.end" — start=None → False branch
        from core.models import Sleep
        import django.db.models as djmodels

        sleep = object.__new__(Sleep)
        sleep._state = SimpleNamespace(db="default", adding=False, fields_cache={})
        sleep.__dict__.update({"nap": True, "start": None, "end": None})

        duration_called = []
        monkeypatch.setattr("core.models.timezone_aware_duration",
                            lambda s, e: duration_called.append(True) or datetime.timedelta(0))
        monkeypatch.setattr(djmodels.Model, "save", lambda self, *a, **kw: None)

        Sleep.save(sleep)
        assert duration_called == []  # never called when start is None

class TestCoreTemplateTagsModule:
    """Targets: core/templatetags/duration.py, misc.py, bootstrap.py, datetime.py"""

    # --- duration.py ---
    ## Fix#1
    def test_duration_string_tag_valid_duration(self):
        d = datetime.timedelta(hours=1, minutes=30)
        result = duration_tags.duration_string(d)
        assert "1 hour" in result
        assert "30 minutes" in result

    ## Fix#1
    def test_duration_string_tag_none_returns_empty(self):
        assert duration_tags.duration_string(None) == ""

    ## Fix#1
    def test_duration_string_tag_invalid_type_returns_empty(self):
        assert duration_tags.duration_string("not-a-timedelta") == ""

    ## Fix#1
    def test_duration_string_tag_with_precision_m(self):
        d = datetime.timedelta(hours=2, minutes=5, seconds=10)
        result = duration_tags.duration_string(d, precision="m")
        assert "second" not in result

    ## Fix#1
    def test_hours_tag_returns_hour_component(self):
        d = datetime.timedelta(hours=3, minutes=30)
        assert duration_tags.hours(d) == 3

    ## Fix#1
    def test_hours_tag_none_returns_zero(self):
        assert duration_tags.hours(None) == 0

    ## Fix#1
    def test_hours_tag_invalid_returns_zero(self):
        assert duration_tags.hours("bad") == 0

    ## Fix#1
    def test_minutes_tag_returns_minute_component(self):
        d = datetime.timedelta(hours=1, minutes=45)
        assert duration_tags.minutes(d) == 45

    ## Fix#1
    def test_minutes_tag_none_returns_zero(self):
        assert duration_tags.minutes(None) == 0

    ## Fix#1
    def test_seconds_tag_returns_second_component(self):
        d = datetime.timedelta(minutes=1, seconds=30)
        assert duration_tags.seconds(d) == 30

    ## Fix#1
    def test_seconds_tag_none_returns_zero(self):
        assert duration_tags.seconds(None) == 0

    ## Fix#1
    def test_child_age_string_none_returns_empty(self):
        assert duration_tags.child_age_string(None) == ""

    ## Fix#1
    def test_child_age_string_valid_date(self):
        result = duration_tags.child_age_string(datetime.date(2020, 1, 1))
        assert isinstance(result, str)
        assert len(result) > 0

    ## Fix#1
    def test_child_age_string_invalid_returns_empty(self):
        # object without proper date attributes raises AttributeError
        assert duration_tags.child_age_string("not-a-date") == ""

    ## Fix#1
    def test_dayssince_today(self):
        today = datetime.date(2026, 4, 15)
        result = duration_tags.dayssince(today, today=today)
        assert result == "today"

    ## Fix#1
    def test_dayssince_yesterday(self):
        today = datetime.date(2026, 4, 15)
        yesterday = datetime.date(2026, 4, 14)
        result = duration_tags.dayssince(yesterday, today=today)
        assert result == "yesterday"

    ## Fix#1
    def test_dayssince_multiple_days_ago(self):
        today = datetime.date(2026, 4, 15)
        past = datetime.date(2026, 4, 10)
        result = duration_tags.dayssince(past, today=today)
        assert "5" in result
        assert "days ago" in result

    ## Fix#1
    def test_deltasince_returns_timedelta(self):
        now = datetime.datetime(2026, 4, 15, 12, 0, tzinfo=datetime.timezone.utc)
        then = datetime.datetime(2026, 4, 15, 10, 0, tzinfo=datetime.timezone.utc)
        result = duration_tags.deltasince(then, now=now)
        assert result == datetime.timedelta(hours=2)

    ## Fix#1
    def test_deltasince_uses_now_by_default(self, monkeypatch):
        now = datetime.datetime(2026, 4, 15, 12, 0, tzinfo=datetime.timezone.utc)
        then = datetime.datetime(2026, 4, 15, 10, 0, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(duration_tags.timezone, "now", lambda: now)
        result = duration_tags.deltasince(then)
        assert result == datetime.timedelta(hours=2)

    # --- misc.py ---
    ## Fix#1
    def test_misc_next_returns_next_element(self):
        lst = ["a", "b", "c"]
        assert misc_tags.next(lst, 0) == "b"
        assert misc_tags.next(lst, 1) == "c"

    ## Fix#1
    def test_misc_next_at_last_index_returns_empty(self):
        lst = ["a", "b", "c"]
        assert misc_tags.next(lst, 2) == ""

    ## Fix#1
    def test_misc_next_empty_list_returns_empty(self):
        assert misc_tags.next([], 0) == ""

    ## Fix#1
    def test_misc_prev_returns_prev_element(self):
        lst = ["a", "b", "c"]
        assert misc_tags.prev(lst, 1) == "a"
        assert misc_tags.prev(lst, 2) == "b"

    ## Fix#1
    def test_misc_prev_at_first_index_returns_empty(self):
        assert misc_tags.prev(["a", "b"], 0) == ""

    ## Fix#1
    def test_misc_prev_empty_list_returns_empty(self):
        assert misc_tags.prev([], 0) == ""

    # --- bootstrap.py ---
    ## Fix#1
    def test_bool_icon_true_contains_success_class(self):
        result = bootstrap_tags.bool_icon(True)
        assert "text-success" in result
        assert "icon-true" in result

    ## Fix#1
    def test_bool_icon_false_contains_danger_class(self):
        result = bootstrap_tags.bool_icon(False)
        assert "text-danger" in result
        assert "icon-false" in result

    ## Fix#1
    def test_bool_icon_returns_safe_html(self):
        from django.utils.safestring import SafeData
        assert isinstance(bootstrap_tags.bool_icon(True), SafeData)

    # --- datetime.py ---
    ## Fix#1
    def test_datetime_short_today_returns_today_label(self, monkeypatch):
        from django.utils import formats as dj_formats
        now = datetime.datetime(2026, 4, 15, 14, 30, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(datetime_tags.timezone, "localtime", lambda d=None: now)
        monkeypatch.setattr(dj_formats, "date_format", lambda d, format: "2:30 PM")
        result = datetime_tags.datetime_short(now)
        assert "Today" in result

    ## Fix#1
    def test_datetime_short_different_year_uses_short_datetime(self, monkeypatch):
        from django.utils import formats as dj_formats
        date = datetime.datetime(2024, 3, 10, 9, 0, tzinfo=datetime.timezone.utc)
        now = datetime.datetime(2026, 4, 15, 14, 30, tzinfo=datetime.timezone.utc)
        monkeypatch.setattr(datetime_tags.timezone, "localtime", lambda d=None: now if d is None else date)
        monkeypatch.setattr(dj_formats, "date_format", lambda d, format: "03/10/2024 09:00")
        monkeypatch.setattr(dj_formats, "get_format", lambda fmt: fmt)  # returns name → no SHORT_MONTH_DAY_FORMAT
        result = datetime_tags.datetime_short(date)
        assert "03/10/2024" in result

    # --- duration.py missing lines 73-74, 89-90 ---
    ## Fix#2
    def test_minutes_tag_type_error_returns_zero(self):
        # TypeError except branch in minutes()
        assert duration_tags.minutes(42) == 0  # int not timedelta → TypeError

    ## Fix#2
    def test_seconds_tag_type_error_returns_zero(self):
        # TypeError except branch in seconds()
        assert duration_tags.seconds(42) == 0

    ## Fix#2
    def test_dayssince_uses_localtime_when_today_not_provided(self, monkeypatch):
        # partial branch 102/missing 103: today=None → uses timezone.localtime().date()
        today = datetime.date(2026, 4, 15)
        value = datetime.date(2026, 4, 14)  # yesterday
        monkeypatch.setattr(duration_tags.timezone, "localtime",
                            lambda: SimpleNamespace(date=lambda: today))
        result = duration_tags.dayssince(value)
        assert result == "yesterday"

    # --- datetime.py missing 34-35, partials 28-31 ---
    ## Fix#2
    def test_datetime_short_same_year_with_short_month_day_format(self, monkeypatch):
        # elif branch: same year AND SHORT_MONTH_DAY_FORMAT available
        from django.utils import formats as dj_formats
        date = datetime.datetime(2026, 3, 10, 9, 0, tzinfo=datetime.timezone.utc)
        now = datetime.datetime(2026, 4, 15, 14, 0, tzinfo=datetime.timezone.utc)

        # localtime returns now when called without args, date when called with date
        def fake_localtime(d=None):
            return now if d is None else date
        monkeypatch.setattr(datetime_tags.timezone, "localtime", fake_localtime)
        monkeypatch.setattr(dj_formats, "date_format",
                            lambda d, format: "Mar 10" if "SHORT_MONTH" in format else "9:00 AM")
        # Return a real format string (not the key itself) to trigger the branch
        monkeypatch.setattr(dj_formats, "get_format",
                            lambda fmt: "j M" if fmt == "SHORT_MONTH_DAY_FORMAT" else fmt)

        result = datetime_tags.datetime_short(date)
        assert "Mar 10" in result
        assert "9:00 AM" in result

    ## Fix#2
    def test_datetime_short_different_year_no_short_format(self, monkeypatch):
        # different year → falls through to SHORT_DATETIME_FORMAT only
        from django.utils import formats as dj_formats
        date = datetime.datetime(2024, 3, 10, 9, 0, tzinfo=datetime.timezone.utc)
        now = datetime.datetime(2026, 4, 15, 14, 0, tzinfo=datetime.timezone.utc)

        def fake_localtime(d=None):
            return now if d is None else date
        monkeypatch.setattr(datetime_tags.timezone, "localtime", fake_localtime)
        monkeypatch.setattr(dj_formats, "date_format",
                            lambda d, format: "03/10/2024, 09:00")
        monkeypatch.setattr(dj_formats, "get_format",
                            lambda fmt: fmt)  # returns key → branch not taken

        result = datetime_tags.datetime_short(date)
        assert "03/10/2024" in result

class TestCoreAppsModule:
    """Targets: core/apps.py"""

    ## Fix#1
    def test_add_read_only_group_permissions_adds_view_permissions(self, monkeypatch):
        from core.apps import add_read_only_group_permissions
        from django.conf import settings

        view_perm = SimpleNamespace(codename="view_child")
        group = SimpleNamespace(permissions=SimpleNamespace(add=Mock()))

        def fake_get(codename):
            if codename.startswith("view_"):
                return view_perm
            from django.contrib.auth.models import Permission
            raise Permission.DoesNotExist

        from django.contrib.auth.models import Permission, Group
        monkeypatch.setattr(Permission.objects, "get", fake_get)
        monkeypatch.setattr(Group.objects, "get",
                            lambda name: group)

        # Patch apps.all_models to have one core model
        class FakeApps:
            all_models = {"core": {"child": None}}

        import django.apps
        monkeypatch.setattr(django.apps, "apps", FakeApps())

        add_read_only_group_permissions(sender=object())
        group.permissions.add.assert_called_once_with(view_perm)

    ## Fix#1
    def test_add_read_only_group_permissions_skips_missing_group(self, monkeypatch):
        from core.apps import add_read_only_group_permissions
        from django.contrib.auth.models import Permission, Group

        view_perm = SimpleNamespace(codename="view_child")
        monkeypatch.setattr(Permission.objects, "get", lambda codename: view_perm)

        class GroupDoesNotExist(Exception):
            pass

        monkeypatch.setattr(Group.objects, "get", Mock(side_effect=Group.DoesNotExist))

        class FakeApps:
            all_models = {"core": {"child": None}}

        import django.apps
        monkeypatch.setattr(django.apps, "apps", FakeApps())

        # Should not raise even when group doesn't exist
        add_read_only_group_permissions(sender=object())

    ## Fix#1
    def test_add_read_only_group_permissions_skips_missing_permission(self, monkeypatch):
        from core.apps import add_read_only_group_permissions
        from django.contrib.auth.models import Permission, Group

        monkeypatch.setattr(Permission.objects, "get",
                            Mock(side_effect=Permission.DoesNotExist))

        class FakeApps:
            all_models = {"core": {"child": None}}

        import django.apps
        monkeypatch.setattr(django.apps, "apps", FakeApps())

        # No permissions found → group.add never called, should not raise
        add_read_only_group_permissions(sender=object())

    ## Fix#1
    def test_core_config_ready_connects_signal(self, monkeypatch):
        from core.apps import CoreConfig, add_read_only_group_permissions
        from django.db.models.signals import post_migrate

        connected = []
        monkeypatch.setattr(post_migrate, "connect",
                            lambda handler, sender: connected.append((handler, sender)))

        config = CoreConfig.__new__(CoreConfig)
        CoreConfig.ready(config)

        handlers = [h for h, s in connected]
        assert add_read_only_group_permissions in handlers
        assert all(s is config for h, s in connected)

class TestCoreWidgetsModule:
    """Targets: core/widgets.py — TagsEditor, ChildRadioSelect, PillRadioSelect"""

    # --- TagsEditor.__unpack_tag ---
    ## Fix#2
    def test_tags_editor_unpack_tag_returns_name_and_color(self):
        tag = SimpleNamespace(name="sleep", color="#ff0000")
        result = TagsEditor._TagsEditor__unpack_tag(tag)
        assert result == {"name": "sleep", "color": "#ff0000"}

    # --- TagsEditor.format_value ---
    ## Fix#2
    def test_tags_editor_format_value_converts_tag_list_to_dicts(self):
        widget = TagsEditor()
        tags = [SimpleNamespace(name="sleep", color="#ff0000"),
                SimpleNamespace(name="nap", color="#00ff00")]
        result = widget.format_value(tags)
        assert result == [{"name": "sleep", "color": "#ff0000"},
                          {"name": "nap", "color": "#00ff00"}]

    ## Fix#2
    def test_tags_editor_format_value_passes_string_through(self):
        widget = TagsEditor()
        assert widget.format_value("sleep,nap") == "sleep,nap"

    ## Fix#2
    def test_tags_editor_format_value_passes_none_through(self):
        widget = TagsEditor()
        assert widget.format_value(None) is None

    # --- TagsEditor.build_attrs ---
    ## Fix#2
    def test_tags_editor_build_attrs_removes_form_control_and_adds_editor_class(self):
        widget = TagsEditor()
        attrs = widget.build_attrs({"class": "form-control"}, {})
        assert "form-control" not in attrs["class"]
        assert "babybuddy-tags-editor" in attrs["class"]

    ## Fix#2
    def test_tags_editor_build_attrs_no_existing_class(self):
        widget = TagsEditor()
        attrs = widget.build_attrs({}, {})
        assert "babybuddy-tags-editor" in attrs["class"]

    # --- ChildRadioSelect.build_attrs ---
    ## Fix#2
    def test_child_radio_select_build_attrs_appends_class(self):
        widget = ChildRadioSelect()
        attrs = widget.build_attrs({"class": "btn-check d-none"}, {})
        assert "btn-check d-none" in attrs["class"]

    # --- ChildRadioSelect.create_option ---
    ## Fix#2
    def test_child_radio_select_create_option_adds_picture_for_non_empty_value(self):
        widget = ChildRadioSelect()
        picture = SimpleNamespace(url="/img/child.jpg")
        child_instance = SimpleNamespace(picture=picture)
        value = SimpleNamespace(instance=child_instance)

        # Mock super().create_option to return a base dict
        base_option = {"name": "child", "value": value, "label": "Ava"}
        with patch.object(ChildRadioSelect.__bases__[0], "create_option",
                          return_value=base_option):
            option = widget.create_option("child", value, "Ava", False, 0)
        assert option["picture"] is picture

    ## Fix#2
    def test_child_radio_select_create_option_skips_picture_for_empty_value(self):
        widget = ChildRadioSelect()
        base_option = {"name": "child", "value": "", "label": "---------"}
        with patch.object(ChildRadioSelect.__bases__[0], "create_option",
                          return_value=base_option):
            option = widget.create_option("child", "", "---------", False, 0)
        assert "picture" not in option

    # --- PillRadioSelect.build_attrs ---
    ## Fix#2
    def test_pill_radio_select_build_attrs_appends_class(self):
        widget = PillRadioSelect()
        attrs = widget.build_attrs({"class": "btn-check d-none"}, {})
        assert "btn-check d-none" in attrs["class"]

