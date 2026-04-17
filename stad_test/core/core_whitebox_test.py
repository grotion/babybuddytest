#########################################################################################################################
# core whitebox test                                                                                                    #
#                                                                                                                       #
# Author: Shaun Ku, Samson Cournane                                                                                     #
#                                                                                                                       #
#                                                                                                                       #
# Test result                                                                                                           #
# --------------------------------------------------------------------------------------------------------------------- #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                   #
# --------------------------------------------------------------------------------------------------------------------- #
# 2026-04-17 | Initial Test             | 76%  | 36/0      | 1806/1806  🎉 680 🫥 862  ⏰ 0  🤔 0  🙁 264  🔇 0  🧙 0 #
# --------------------------------------------------------------------------------------------------------------------- #
#########################################################################################################################

import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django import forms as django_forms
from django.core.exceptions import ValidationError

from core import fields as core_fields
from core import forms as core_forms
from core import timeline as core_timeline
from core import utils as core_utils
from core import views as core_views


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

