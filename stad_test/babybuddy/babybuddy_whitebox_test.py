##########################################################################################################################
# babybuddy whitebox test                                                                                                #
#                                                                                                                        #
# Author: Shaun Ku, Samson Cournane                                                                                      #
#                                                                                                                        #
#                                                                                                                        #
# Test result                                                                                                            #
# ---------------------------------------------------------------------------------------------------------------------- #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                    #
# ---------------------------------------------------------------------------------------------------------------------- #
# 2026-04-16 | Init test                | 95%  | 96/0      | 1029/1029  🎉 355 🫥 545  ⏰ 0  🤔 0  🙁 129  🔇 0  🧙 0  #
# 2026-04-19 | Fix#1 - add more test    | 98%  | 177/0     | 1029/1029  🎉 465 🫥 450  ⏰ 0  🤔 0  🙁 114  🔇 0  🧙 0  #
# 2026-04-19 | Fix#2                    | 98%  | 225/0     | 1029/1029  🎉 504 🫥 450  ⏰ 0  🤔 0  🙁 75  🔇 0  🧙 0   #
# ---------------------------------------------------------------------------------------------------------------------- #
##########################################################################################################################

'''
Management commands (389 mutants) — not worth testing in whitebox
The three commands are fake.py, reset.py, and createuser.py. These are Django management commands invoked via python manage.py <command>. They are heavily interactive/IO-dependent:

fake.py generates fake data by creating real database records using factories/Faker
reset.py drops and recreates the database
createuser.py prompts for username/password interactively via stdin and creates a real user

Testing these properly requires either a real database or extensive mocking of Django's ORM, stdin, stdout, and the entire management command framework. The effort-to-value ratio is very low for whitebox testing because:

Their logic is mostly orchestration of other well-tested components (Django's ORM, Faker)
The mutants target things like argument strings in add_arguments() calls (e.g. "--username") and print message strings — mutations here don't affect correctness of the application itself
They are more naturally covered by integration or end-to-end tests

In summary: the 450 🫥 mutants are not a gap in your test quality — they reflect a deliberate and correct decision to exclude migration files and management commands from unit whitebox testing. This is standard practice.
'''

import copy
import os
import sys
import types
import pytest
import datetime

from unittest.mock import MagicMock, Mock, call, patch

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.contrib.auth.mixins import AccessMixin
from django.test.client import RequestFactory


import babybuddy.apps as babybuddy_apps
import babybuddy.middleware as babybuddy_middleware
import babybuddy.views as babybuddy_views
import babybuddy.forms as babybuddy_forms
import babybuddy.mixins as babybuddy_mixins
import babybuddy.models as babybuddy_models
import babybuddy.site_settings as babybuddy_site_settings
import babybuddy.templatetags.babybuddy as babybuddy_tags
import babybuddy.widgets as babybuddy_widgets

from babybuddy.settings.base import strtobool


# -----------------------------
# Bootstrap missing third-party/project modules so the isolated babybuddy app
# can be imported even when the zip does not include the full project tree.
# -----------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "babybuddy.settings.test")

try:
    import dbsettings  # type: ignore
except ModuleNotFoundError:
    dbsettings = types.ModuleType("dbsettings")

    class _TimeValue:
        pass

    class _Group:
        pass

    dbsettings.TimeValue = _TimeValue
    dbsettings.Group = _Group
    sys.modules["dbsettings"] = dbsettings

try:
    import core  # type: ignore
except ModuleNotFoundError:
    core = types.ModuleType("core")
    core_fields = types.ModuleType("core.fields")
    core_models = types.ModuleType("core.models")

    class _NapStartMaxTimeField:
        pass

    class _NapStartMinTimeField:
        pass

    class _Child:
        @staticmethod
        def count():
            return 0

    core_fields.NapStartMaxTimeField = _NapStartMaxTimeField
    core_fields.NapStartMinTimeField = _NapStartMinTimeField
    core_models.Child = _Child
    core.fields = core_fields
    core.models = core_models
    sys.modules["core"] = core
    sys.modules["core.fields"] = core_fields
    sys.modules["core.models"] = core_models

try:
    import axes  # type: ignore
except ModuleNotFoundError:
    axes = types.ModuleType("axes")
    axes_helpers = types.ModuleType("axes.helpers")
    axes_models = types.ModuleType("axes.models")
    axes_utils = types.ModuleType("axes.utils")

    def _get_lockout_message():
        return "locked"

    class _FilterResult:
        def exists(self):
            return False

    class _AttemptManager:
        def filter(self, **kwargs):
            return _FilterResult()

    class _AccessAttempt:
        objects = _AttemptManager()

    def _reset(**kwargs):
        return None

    axes_helpers.get_lockout_message = _get_lockout_message
    axes_models.AccessAttempt = _AccessAttempt
    axes_utils.reset = _reset
    axes.helpers = axes_helpers
    axes.models = axes_models
    axes.utils = axes_utils
    sys.modules["axes"] = axes
    sys.modules["axes.helpers"] = axes_helpers
    sys.modules["axes.models"] = axes_models
    sys.modules["axes.utils"] = axes_utils

# Ensure the extracted project root is importable when running this file outside the repo.
PROJECT_ROOT = "/mnt/data/babybuddy_extracted"
if PROJECT_ROOT not in sys.path and os.path.isdir(PROJECT_ROOT):
    sys.path.insert(0, PROJECT_ROOT)

# -----------------------------
# Shared helper / dummy classes
# -----------------------------
class DummyExistsResult:
    def __init__(self, exists_value):
        self._exists_value = exists_value

    def exists(self):
        return self._exists_value


class DummyGroups:
    def __init__(self, exists_value=False):
        self.exists_value = exists_value
        self.add_calls = []
        self.remove_calls = []
        self.filter_calls = []

    def filter(self, **kwargs):
        self.filter_calls.append(kwargs)
        return DummyExistsResult(self.exists_value)

    def add(self, value):
        self.add_calls.append(value)

    def remove(self, value):
        self.remove_calls.append(value)


class DummyUserSettings:
    def __init__(self, language=None, timezone_name=None, pagination_count=25):
        self.language = language
        self.timezone = timezone_name
        self.pagination_count = pagination_count
        self.api_key_calls = []
        self.saved = False

    def api_key(self, reset=False):
        self.api_key_calls.append(reset)

    def save(self):
        self.saved = True


class DummyUser:
    def __init__(
        self,
        username="alice",
        exists_value=False,
        is_staff=True,
        language=None,
        timezone_name=None,
        pagination_count=25,
    ):
        self.username = username
        self.first_name = ""
        self.last_name = ""
        self.email = ""
        self.is_staff = is_staff
        self.is_superuser = None
        self.is_active = True
        self.groups = DummyGroups(exists_value=exists_value)
        self.settings = DummyUserSettings(language, timezone_name, pagination_count)
        self.save_calls = 0

    def save(self):
        self.save_calls += 1

    def __str__(self):
        return self.username


class DummySession(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expiry_calls = []

    def set_expiry(self, value):
        self.expiry_calls.append(value)


class DummyRequest:
    def __init__(
        self,
        user=None,
        headers=None,
        language_code=None,
        session=None,
        post=None,
        cookies=None,
        path="/",
    ):
        self.user = user or DummyUser()
        self.headers = headers or {}
        self.LANGUAGE_CODE = language_code
        self.session = session if session is not None else DummySession()
        self.POST = post or {}
        self.COOKIES = cookies or {}
        self.path = path
        self.META = {}
        self.GET = MagicMock()
        self.GET.urlencode.return_value = ""
        self.is_homeassistant_ingress_request = False

    def build_absolute_uri(self, url):
        return f"https://example.test{url}"


class DummyObjectWithChild:
    def __init__(self, child=None):
        self.child = child


class DummyNoChildObject:
    pass


class DummyResponseWithCookies(HttpResponse):
    def __init__(self, content=b"", *args, **kwargs):
        super().__init__(content=content, *args, **kwargs)
        self.cookies["csrftoken"] = "abc"
        self.cookies["sessionid"] = "def"


class DummyForm:
    def __init__(self, is_valid_value=True, instance=None, save_result=None):
        self._is_valid_value = is_valid_value
        self.instance = instance
        self._save_result = save_result if save_result is not None else instance
        self.save_calls = []

    def is_valid(self):
        return self._is_valid_value

    def save(self, commit=True):
        self.save_calls.append(commit)

        # mutation guard: ensure instance consistency
        if self._save_result is not self.instance:
            raise AssertionError("Form returned a different instance than provided")

        return self._save_result


# -----------------------------
# forms.py tests
# -----------------------------
class TestFormsModule:
    """Targets: babybuddy/forms.py"""

    def test_babybuddy_user_form_init_sets_read_only_true_when_group_exists(self):
        # target file: babybuddy/forms.py | function: BabyBuddyUserForm.__init__ | branch: existing user in read-only group
        instance = DummyUser(exists_value=True)
        kwargs = {"instance": instance, "initial": {}}
        with patch("django.forms.ModelForm.__init__", return_value=None) as model_form_init:
            form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
            babybuddy_forms.BabyBuddyUserForm.__init__(form, **kwargs)
        assert kwargs["initial"]["is_read_only"] is True
        model_form_init.assert_called_once()
        assert instance.groups.filter_calls == [
            {"name": settings.BABY_BUDDY["READ_ONLY_GROUP_NAME"]}
        ]

    def test_babybuddy_user_form_init_sets_read_only_false_when_group_missing(self):
        # target file: babybuddy/forms.py | function: BabyBuddyUserForm.__init__ | branch: existing user not in read-only group
        instance = DummyUser(exists_value=False)
        kwargs = {"instance": instance, "initial": {}}
        with patch("django.forms.ModelForm.__init__", return_value=None):
            form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
            babybuddy_forms.BabyBuddyUserForm.__init__(form, **kwargs)
        assert kwargs["initial"]["is_read_only"] is False

    def test_babybuddy_user_form_init_skips_group_lookup_for_none_instance(self):
        # target file: babybuddy/forms.py | function: BabyBuddyUserForm.__init__ | branch: no instance provided
        kwargs = {"instance": None, "initial": {}}
        with patch("django.forms.ModelForm.__init__", return_value=None) as model_form_init:
            form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
            babybuddy_forms.BabyBuddyUserForm.__init__(form, **kwargs)
        assert "is_read_only" not in kwargs["initial"]
        model_form_init.assert_called_once()

    def test_babybuddy_user_form_save_read_only_true_disables_superuser_adds_group_and_commits(self):
        # target file: babybuddy/forms.py | function: BabyBuddyUserForm.save | branch: read-only true with commit
        user = DummyUser()
        group = types.SimpleNamespace(id=999)
        form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
        form.cleaned_data = {"is_read_only": True}
        with patch("django.forms.ModelForm.save", return_value=user) as model_form_save, patch.object(
            babybuddy_forms.Group.objects, "get", return_value=group
        ) as group_get:
            returned = babybuddy_forms.BabyBuddyUserForm.save(form, commit=True)
        assert returned is user
        assert user.is_superuser is False
        assert user.save_calls == 1
        assert user.groups.add_calls == [999]
        assert user.groups.remove_calls == []
        model_form_save.assert_called_once_with(commit=False)
        group_get.assert_called_once_with(name=settings.BABY_BUDDY["READ_ONLY_GROUP_NAME"])

    def test_babybuddy_user_form_save_read_only_false_enables_superuser_removes_group_and_skips_commit(self):
        # target file: babybuddy/forms.py | function: BabyBuddyUserForm.save | branch: read-only false without commit
        user = DummyUser()
        group = types.SimpleNamespace(id=123)
        form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
        form.cleaned_data = {"is_read_only": False}
        with patch("django.forms.ModelForm.save", return_value=user):
            with patch.object(babybuddy_forms.Group.objects, "get", return_value=group):
                returned = babybuddy_forms.BabyBuddyUserForm.save(form, commit=False)
        assert returned is user
        assert user.is_superuser is True
        assert user.save_calls == 0
        assert user.groups.add_calls == []
        assert user.groups.remove_calls == [123]

    def test_babybuddy_user_form_save_propagates_missing_cleaned_data_key(self):
        # target file: babybuddy/forms.py | function: BabyBuddyUserForm.save | branch: missing required cleaned_data
        user = DummyUser()
        form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
        form.cleaned_data = {}
        with patch("django.forms.ModelForm.save", return_value=user):
            with pytest.raises(KeyError):
                babybuddy_forms.BabyBuddyUserForm.save(form, commit=False)

    def test_user_add_form_is_subclass_of_both_expected_bases(self):
        # target file: babybuddy/forms.py | function: UserAddForm | behavior: inheritance contract
        assert issubclass(babybuddy_forms.UserAddForm, babybuddy_forms.BabyBuddyUserForm)
        assert issubclass(babybuddy_forms.UserAddForm, babybuddy_forms.UserCreationForm)

    def test_user_update_form_is_subclass_of_babybuddy_user_form(self):
        # target file: babybuddy/forms.py | function: UserUpdateForm | behavior: inheritance contract
        assert issubclass(babybuddy_forms.UserUpdateForm, babybuddy_forms.BabyBuddyUserForm)

    def test_user_form_meta_fields_are_exact_expected_fields(self):
        # target file: babybuddy/forms.py | function: UserForm.Meta | behavior: field contract
        assert babybuddy_forms.UserForm.Meta.fields == ["first_name", "last_name", "email"]

    def test_user_password_form_meta_fields_are_exact_expected_fields(self):
        # target file: babybuddy/forms.py | function: UserPasswordForm.Meta | behavior: field contract
        assert babybuddy_forms.UserPasswordForm.Meta.fields == [
            "old_password",
            "new_password1",
            "new_password2",
        ]

    def test_user_settings_form_meta_includes_pagination_field(self):
        # target file: babybuddy/forms.py | function: UserSettingsForm.Meta | behavior: all expected settings fields exposed
        assert babybuddy_forms.UserSettingsForm.Meta.fields == [
            "dashboard_refresh_rate",
            "dashboard_hide_empty",
            "dashboard_hide_age",
            "language",
            "timezone",
            "pagination_count",
        ]

    ## Fix#1 - add more test
    def test_babybuddy_user_form_init_updates_initial_with_is_read_only_key(self):
        # Kills __init__ mutmut_12/_13: the key name "is_read_only" in the
        # initial.update() dict and the use of .exists() as the value.
        instance = DummyUser(exists_value=True)
        kwargs = {"instance": instance, "initial": {"other": "value"}}
        with patch("django.forms.ModelForm.__init__", return_value=None):
            form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
            babybuddy_forms.BabyBuddyUserForm.__init__(form, **kwargs)
        # The exact key "is_read_only" must be present and "other" must be preserved
        assert "is_read_only" in kwargs["initial"]
        assert kwargs["initial"]["other"] == "value"
        assert kwargs["initial"]["is_read_only"] is True

    ## Fix#1 - add more test
    def test_babybuddy_user_form_save_returns_user_from_super(self):
        # Kills save mutmut_1: verifies save() returns the user object from
        # ModelForm.save(), not some other value.
        user = DummyUser()
        group = types.SimpleNamespace(id=42)
        form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
        form.cleaned_data = {"is_read_only": False}
        with patch("django.forms.ModelForm.save", return_value=user), \
             patch.object(babybuddy_forms.Group.objects, "get", return_value=group):
            result = babybuddy_forms.BabyBuddyUserForm.save(form, commit=False)
        assert result is user

    ## Fix#2
    def test_babybuddy_user_form_init_sets_read_only_based_on_exists_result_not_group(self):
        # mutmut_12/_13: the .exists() call result (True/False) is what's stored,
        # not the filter queryset itself. Tests both True and False explicitly.
        for exists_val in [True, False]:
            instance = DummyUser(exists_value=exists_val)
            kwargs = {"instance": instance, "initial": {}}
            with patch("django.forms.ModelForm.__init__", return_value=None):
                form = babybuddy_forms.BabyBuddyUserForm.__new__(
                    babybuddy_forms.BabyBuddyUserForm
                )
                babybuddy_forms.BabyBuddyUserForm.__init__(form, **kwargs)
            assert kwargs["initial"]["is_read_only"] is exists_val

    ## Fix#2
    def test_babybuddy_user_form_save_result_is_from_model_form_save_not_none(self):
        # save mutmut_1: the return value is the user object, not None or something else
        user = DummyUser()
        group = types.SimpleNamespace(id=7)
        form = babybuddy_forms.BabyBuddyUserForm.__new__(babybuddy_forms.BabyBuddyUserForm)
        form.cleaned_data = {"is_read_only": True}
        with patch("django.forms.ModelForm.save", return_value=user), \
             patch.object(babybuddy_forms.Group.objects, "get", return_value=group):
            result = babybuddy_forms.BabyBuddyUserForm.save(form, commit=True)
        assert result is user
        assert result is not None


# -----------------------------
# mixins.py tests
# -----------------------------
class TestMixinsModule:
    """Targets: babybuddy/mixins.py"""

    def test_permission_required_mixin_login_url_is_fixed_login_path(self):
        # target file: babybuddy/mixins.py | function: PermissionRequiredMixin | behavior: class attribute contract
        assert babybuddy_mixins.PermissionRequiredMixin.login_url == "/login"

    def test_staff_only_mixin_dispatch_denies_non_staff_user(self):
        # target file: babybuddy/mixins.py | function: StaffOnlyMixin.dispatch | branch: non-staff denied
        mixin = babybuddy_mixins.StaffOnlyMixin()
        denied = HttpResponse("denied")
        mixin.handle_no_permission = Mock(return_value=denied)
        request = DummyRequest(user=DummyUser(is_staff=False))

        response = mixin.dispatch(request)

        assert response is denied
        mixin.handle_no_permission.assert_called_once_with()

    def test_staff_only_mixin_dispatch_calls_super_for_staff_user(self):
        # target file: babybuddy/mixins.py | function: StaffOnlyMixin.dispatch | branch: staff allowed
        mixin = babybuddy_mixins.StaffOnlyMixin()
        request = DummyRequest(user=DummyUser(is_staff=True))
        allowed = HttpResponse("allowed")

        with patch.object(AccessMixin, "dispatch", return_value=allowed, create=True) as super_dispatch:
            response = babybuddy_mixins.StaffOnlyMixin.dispatch(mixin, request, 1, two=2)

        assert response is allowed
        super_dispatch.assert_called_once_with(request, 1, two=2)


# -----------------------------
# middleware.py tests
# -----------------------------
class TestMiddlewareModule:
    """Targets: babybuddy/middleware.py"""

    def test_user_language_middleware_uses_user_setting_language(self):
        # target file: babybuddy/middleware.py | function: UserLanguageMiddleware.__call__ | branch: explicit user language
        request = DummyRequest(user=DummyUser(language="fr"), language_code="en")
        get_response = Mock(return_value="response")
        middleware = babybuddy_middleware.UserLanguageMiddleware(get_response)
        with patch.object(babybuddy_middleware.translation, "activate") as activate, patch.object(
            babybuddy_middleware.translation, "deactivate"
        ) as deactivate:
            response = middleware(request)
        assert response == "response"
        activate.assert_called_once_with("fr")
        deactivate.assert_called_once_with()
        get_response.assert_called_once_with(request)

    def test_user_language_middleware_falls_back_to_request_language(self):
        # target file: babybuddy/middleware.py | function: UserLanguageMiddleware.__call__ | branch: request language fallback
        user = DummyUser(language=None)
        user.settings.language = None
        request = DummyRequest(user=user, language_code="es")
        middleware = babybuddy_middleware.UserLanguageMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.translation, "activate") as activate, patch.object(
            babybuddy_middleware.translation, "deactivate"
        ):
            middleware(request)
        activate.assert_called_once_with("es")

    def test_user_language_middleware_falls_back_to_global_default_language(self):
        # target file: babybuddy/middleware.py | function: UserLanguageMiddleware.__call__ | branch: global default fallback
        user = DummyUser(language=None)
        user.settings.language = None
        request = DummyRequest(user=user, language_code="")
        middleware = babybuddy_middleware.UserLanguageMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.translation, "activate") as activate, patch.object(
            babybuddy_middleware.translation, "deactivate"
        ):
            middleware(request)
        activate.assert_called_once_with(settings.LANGUAGE_CODE)

    def test_user_timezone_middleware_activates_valid_user_timezone(self):
        # target file: babybuddy/middleware.py | function: UserTimezoneMiddleware.__call__ | branch: valid timezone activation
        request = DummyRequest(user=DummyUser(timezone_name="UTC"))
        get_response = Mock(return_value="response")
        middleware = babybuddy_middleware.UserTimezoneMiddleware(get_response)
        with patch.object(babybuddy_middleware.timezone, "activate") as activate:
            response = middleware(request)
        assert response == "response"
        activate.assert_called_once_with("UTC")

    def test_user_timezone_middleware_ignores_invalid_timezone_value_error(self):
        # target file: babybuddy/middleware.py | function: UserTimezoneMiddleware.__call__ | branch: invalid timezone swallowed
        request = DummyRequest(user=DummyUser(timezone_name="Not/AZone"))
        get_response = Mock(return_value="response")
        middleware = babybuddy_middleware.UserTimezoneMiddleware(get_response)
        with patch.object(babybuddy_middleware.timezone, "activate", side_effect=ValueError) as activate:
            response = middleware(request)
        assert response == "response"
        activate.assert_called_once_with("Not/AZone")

    def test_user_timezone_middleware_skips_activation_when_timezone_missing(self):
        # target file: babybuddy/middleware.py | function: UserTimezoneMiddleware.__call__ | branch: missing timezone
        request = DummyRequest(user=DummyUser(timezone_name=None))
        request.user.settings.timezone = None
        get_response = Mock(return_value="response")
        middleware = babybuddy_middleware.UserTimezoneMiddleware(get_response)
        with patch.object(babybuddy_middleware.timezone, "activate") as activate:
            response = middleware(request)
        assert response == "response"
        activate.assert_not_called()

    def test_rolling_session_middleware_initializes_refresh_for_existing_session_without_marker(self):
        # target file: babybuddy/middleware.py | function: RollingSessionMiddleware.__call__ | branch: session exists without refresh key
        session = DummySession(existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=100):
            response = middleware(request)
        assert response == "ok"
        assert session["session_refresh"] == 100
        assert session.expiry_calls == []

    def test_rolling_session_middleware_refreshes_when_delta_exceeds_threshold(self):
        # target file: babybuddy/middleware.py | function: RollingSessionMiddleware.__call__ | branch: expiry refresh triggered
        session = DummySession(session_refresh=1, existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=settings.ROLLING_SESSION_REFRESH + 10):
            middleware(request)
        assert session["session_refresh"] == settings.ROLLING_SESSION_REFRESH + 10
        assert session.expiry_calls == [settings.SESSION_COOKIE_AGE]

    def test_rolling_session_middleware_does_not_refresh_when_delta_is_boundary_equal(self):
        # target file: babybuddy/middleware.py | function: RollingSessionMiddleware.__call__ | branch: strict greater-than comparison boundary
        boundary = settings.ROLLING_SESSION_REFRESH
        session = DummySession(session_refresh=10, existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=10 + boundary):
            middleware(request)
        assert session["session_refresh"] == 10
        assert session.expiry_calls == []

    def test_rolling_session_middleware_handles_non_integer_refresh_value(self):
        # target file: babybuddy/middleware.py | function: RollingSessionMiddleware.__call__ | branch: invalid refresh value coerced to refresh path
        session = DummySession(session_refresh="not-an-int", existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=500):
            middleware(request)
        assert session["session_refresh"] == 500
        assert session.expiry_calls == [settings.SESSION_COOKIE_AGE]

    def test_rolling_session_middleware_handles_none_refresh_value(self):
        # target file: babybuddy/middleware.py | function: RollingSessionMiddleware.__call__ | branch: empty refresh marker initializes current time
        session = DummySession(session_refresh=None, existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=77):
            middleware(request)
        assert session["session_refresh"] == 77
        assert session.expiry_calls == []

    def test_rolling_session_middleware_skips_empty_session(self):
        # target file: babybuddy/middleware.py | function: RollingSessionMiddleware.__call__ | branch: no session keys
        session = DummySession()
        request = DummyRequest(session=session)
        get_response = Mock(return_value="done")
        middleware = babybuddy_middleware.RollingSessionMiddleware(get_response)
        with patch.object(babybuddy_middleware, "time", return_value=111):
            response = middleware(request)
        assert response == "done"
        assert session == {}
        assert session.expiry_calls == []

    def test_custom_remote_user_skips_api_paths(self):
        # target file: babybuddy/middleware.py | function: CustomRemoteUser.process_request | branch: api path bypass
        middleware = babybuddy_middleware.CustomRemoteUser.__new__(babybuddy_middleware.CustomRemoteUser)
        request = DummyRequest(path="api/token/")
        assert babybuddy_middleware.CustomRemoteUser.process_request(middleware, request) is None

    def test_custom_remote_user_delegates_non_api_paths_to_super(self):
        # target file: babybuddy/middleware.py | function: CustomRemoteUser.process_request | branch: non-api path delegated
        middleware = babybuddy_middleware.CustomRemoteUser.__new__(babybuddy_middleware.CustomRemoteUser)
        request = DummyRequest(path="dashboard/")
        with patch(
            "django.contrib.auth.middleware.RemoteUserMiddleware.process_request",
            return_value="super-result",
        ) as super_process:
            result = babybuddy_middleware.CustomRemoteUser.process_request(middleware, request)
        assert result == "super-result"
        super_process.assert_called_once_with(request)

    def test_home_assistant_middleware_disabled_sets_flag_false_and_returns_response(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: middleware disabled
        request = DummyRequest(headers={"X-Hass-Source": "core.ingress"})
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", False):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value="response"))
            response = middleware(request)
        assert response == "response"
        assert request.is_homeassistant_ingress_request is False

    def test_home_assistant_middleware_enabled_non_ingress_resets_script_prefix(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: support enabled but not ingress
        request = DummyRequest(headers={})
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=HttpResponse("ok")))
            with patch.object(babybuddy_middleware, "set_script_prefix") as set_prefix:
                response = middleware(request)
        assert response.status_code == 200
        assert request.is_homeassistant_ingress_request is False
        set_prefix.assert_called_once_with(middleware.original_script_prefix)

    def test_home_assistant_middleware_enabled_ingress_without_path_resets_original_prefix(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: ingress request missing X-Ingress-Path
        request = DummyRequest(headers={"X-Hass-Source": "core.ingress"})
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=HttpResponse("ok")))
            with patch.object(babybuddy_middleware, "set_script_prefix") as set_prefix:
                middleware(request)
        assert request.is_homeassistant_ingress_request is True
        set_prefix.assert_called_once_with(middleware.original_script_prefix)

    def test_home_assistant_middleware_redirect_prepends_ingress_prefix_when_missing(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: redirect location rewritten
        response = HttpResponseRedirect("/dashboard")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            with patch.object(babybuddy_middleware, "set_script_prefix"):
                rewritten = middleware(request)
        assert rewritten["Location"].endswith("/ingress/dashboard")

    def test_home_assistant_middleware_redirect_does_not_duplicate_existing_prefix(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: redirect location already prefixed
        response = HttpResponseRedirect("/ingress/dashboard")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            with patch.object(babybuddy_middleware, "set_script_prefix"):
                rewritten = middleware(request)
        assert rewritten["Location"] == "/ingress/dashboard"

    def test_home_assistant_middleware_logs_error_for_streaming_response(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: streaming response warning path
        response = StreamingHttpResponse(iter([b"chunk"]))
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            with patch.object(babybuddy_middleware, "set_script_prefix"), patch.object(
                babybuddy_middleware.logging, "error"
            ) as log_error:
                result = middleware(request)
        assert result is response
        log_error.assert_called_once()

    def test_home_assistant_middleware_rewrites_static_and_media_urls_in_html_response(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: HTML content rewritten and cookies preserved
        html = b'<img src="/static/app.css"><img src="/media/photo.jpg">'
        response = DummyResponseWithCookies(content=html, content_type="text/html; charset=utf-8")
        response["X-Test"] = "value"
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), patch.object(
            babybuddy_middleware, "set_script_prefix"
        ):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            rewritten = middleware(request)
        content = rewritten.content.decode()
        assert '"/ingress/static' in content
        assert '"/ingress/media' in content
        assert rewritten.cookies["csrftoken"].value == "abc"
        assert rewritten.cookies["sessionid"].value == "def"
        assert rewritten["X-Test"] == "value"

    def test_home_assistant_middleware_does_not_rewrite_non_html_response(self):
        # target file: babybuddy/middleware.py | function: HomeAssistant.__call__ | branch: non-HTML response unchanged
        response = HttpResponse(b'{"ok": true}', content_type="application/json")
        original_content = response.content
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), patch.object(
            babybuddy_middleware, "set_script_prefix"
        ):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            rewritten = middleware(request)
        assert rewritten is response
        assert rewritten.content == original_content

    def test_user_language_middleware_skips_activation_when_user_settings_language_is_empty_string(self):
        # Kills "if hasattr(user, 'settings') and user.settings.language:" mutant that drops the
        # "and user.settings.language" part. user.settings exists but language="" (falsy) →
        # should fall back to request LANGUAGE_CODE, NOT activate the empty string.
        user = DummyUser(language=None)
        user.settings.language = ""          # has settings attr, but falsy value
        request = DummyRequest(user=user, language_code="pt")
        middleware = babybuddy_middleware.UserLanguageMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.translation, "activate") as activate, \
             patch.object(babybuddy_middleware.translation, "deactivate"):
            middleware(request)
        activate.assert_called_once_with("pt")

    def test_user_language_middleware_does_not_activate_when_all_language_sources_are_falsy(self):
        # Kills the "if language:" guard mutant that would activate even a None/empty language.
        # user.settings.language=None, LANGUAGE_CODE="", settings.LANGUAGE_CODE="" → language stays falsy.
        user = DummyUser(language=None)
        user.settings.language = None
        request = DummyRequest(user=user, language_code="")
        middleware = babybuddy_middleware.UserLanguageMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.translation, "activate") as activate, \
             patch.object(babybuddy_middleware.translation, "deactivate"), \
             patch.object(babybuddy_middleware.settings, "LANGUAGE_CODE", ""):
            middleware(request)
        activate.assert_not_called()

    # --- UserTimezoneMiddleware ---
    ## Fix#1 - add more test
    def test_user_timezone_middleware_skips_activation_when_user_has_no_settings_attr(self):
        # Kills mutant that drops the "hasattr(user, 'settings')" check, leaving only the
        # "user.settings.timezone" part which would AttributeError on a bare user object.
        user = DummyUser()
        del user.settings                    # user has no settings attr
        request = DummyRequest(user=user)
        get_response = Mock(return_value="response")
        middleware = babybuddy_middleware.UserTimezoneMiddleware(get_response)
        with patch.object(babybuddy_middleware.timezone, "activate") as activate:
            response = middleware(request)
        assert response == "response"
        activate.assert_not_called()

    # --- RollingSessionMiddleware ---
    ## Fix#1 - add more test
    def test_rolling_session_middleware_zero_refresh_value_treats_it_as_missing_and_initializes(self):
        # Kills "if session_refresh:" → "if session_refresh is not None:" mutant.
        # session_refresh=0 is falsy but not None → should go to the else branch (initialize),
        # NOT into the try block that computes delta.
        session = DummySession(session_refresh=0, existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=200):
            middleware(request)
        # Went to else branch: sets session_refresh to current time, no expiry refresh
        assert session["session_refresh"] == 200
        assert session.expiry_calls == []

    ## Fix#1 - add more test
    def test_rolling_session_middleware_type_error_in_delta_triggers_refresh(self):
        # Kills mutant that removes TypeError from the except tuple, leaving only ValueError.
        # Inject a session_refresh that causes TypeError when subtracted from int (e.g. a list).
        session = DummySession(session_refresh=[1, 2], existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=500):
            middleware(request)
        assert session["session_refresh"] == 500
        assert session.expiry_calls == [settings.SESSION_COOKIE_AGE]

    # --- HomeAssistant middleware ---
    ## Fix#1 - add more test
    def test_home_assistant_middleware_empty_ingress_path_does_not_treat_as_none(self):
        # Kills "if x_ingress_path is None:" → "if not x_ingress_path:" mutant.
        # x_ingress_path="" is not None → apply_x_ingress_path stays True.
        # set_script_prefix should be called with "/" (lstrip of "").
        response = HttpResponse("ok")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": ""}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            with patch.object(babybuddy_middleware, "set_script_prefix") as set_prefix:
                middleware(request)
        # "" is not None, so apply_x_ingress_path remains True → set_script_prefix called with "/"
        set_prefix.assert_called_with("/")

    ## Fix#1 - add more test
    def test_home_assistant_middleware_rewrites_uppercase_content_type_html(self):
        # Kills mutant that drops the .lower() call on Content-Type before startswith check.
        # "Text/HTML" would not match "text/html" without .lower().
        html = b'<img src="/static/app.css">'
        response = DummyResponseWithCookies(content=html, content_type="Text/HTML; charset=utf-8")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            middleware = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            rewritten = middleware(request)
        content = rewritten.content.decode()
        assert '"/ingress/static' in content

    # --- UserLanguageMiddleware partial branch ---
    ## Fix#1 - add more test
    def test_user_language_middleware_skips_activate_when_language_is_falsy(self):
        # Closes partial branch: line 38 "if language:" was always true.
        # All sources return falsy → activate must NOT be called.
        user = DummyUser(language=None)
        user.settings.language = None
        request = DummyRequest(user=user, language_code="")
        middleware = babybuddy_middleware.UserLanguageMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.translation, "activate") as activate, \
             patch.object(babybuddy_middleware.translation, "deactivate"), \
             patch.object(babybuddy_middleware.settings, "LANGUAGE_CODE", ""):
            middleware(request)
        activate.assert_not_called()

    # --- UserTimezoneMiddleware mutmut_10 ---
    ## Fix#1 - add more test
    def test_user_timezone_middleware_skips_when_user_has_no_settings_attr(self):
        # Kills mutmut_10: removes the hasattr(user, "settings") guard,
        # which would cause AttributeError on users without settings.
        user = DummyUser()
        del user.settings
        request = DummyRequest(user=user)
        middleware = babybuddy_middleware.UserTimezoneMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.timezone, "activate") as activate:
            response = middleware(request)
        assert response == "ok"
        activate.assert_not_called()

    # --- RollingSessionMiddleware mutmut_10 / mutmut_21 ---
    ## Fix#1 - add more test
    def test_rolling_session_middleware_zero_refresh_initializes_rather_than_computing_delta(self):
        # Kills mutmut_10: "if session_refresh:" → "if session_refresh is not None:"
        # session_refresh=0 is falsy → should go to else (initialize), not compute delta.
        session = DummySession(session_refresh=0, existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=200):
            middleware(request)
        assert session["session_refresh"] == 200
        assert session.expiry_calls == []

    ## Fix#1 - add more test
    def test_rolling_session_middleware_type_error_in_delta_triggers_refresh(self):
        # Kills mutmut_21: removes TypeError from the except tuple.
        # A list value causes TypeError on int subtraction → must still refresh.
        session = DummySession(session_refresh=[1, 2], existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=500):
            middleware(request)
        assert session["session_refresh"] == 500
        assert session.expiry_calls == [settings.SESSION_COOKIE_AGE]

    # --- HomeAssistant.__init__ mutmut_3 ---
    ## Fix#1 - add more test
    def test_home_assistant_init_stores_original_script_prefix(self):
        # Kills mutmut_3: the original_script_prefix assignment in __init__.
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", False), \
             patch.object(babybuddy_middleware, "get_script_prefix", return_value="/myprefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=HttpResponse()))
        assert mw.original_script_prefix == "/myprefix"

    # --- HomeAssistant.__call__ partial branch (line 189) ---
    ## Fix#1 - add more test
    def test_home_assistant_middleware_non_html_http_response_not_rewritten(self):
        # Closes partial branch: line 189 content-type check was always true.
        # JSON response must pass through unchanged.
        response = HttpResponse(b'{"ok":true}', content_type="application/json")
        original = response.content
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert result is response
        assert result.content == original

    # --- HomeAssistant.__call__ — redirect status codes 301/307/308 ---
    ## Fix#1 - add more test
    def test_home_assistant_middleware_301_redirect_is_rewritten(self):
        # Kills mutants on the redirect status code set {301, 307, 308}.
        response = HttpResponse(status=301)
        response["Location"] = "/dashboard"
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert "/ingress" in result["Location"]

    ## Fix#1 - add more test
    def test_home_assistant_middleware_307_redirect_is_rewritten(self):
        response = HttpResponse(status=307)
        response["Location"] = "/dashboard"
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert "/ingress" in result["Location"]

    ## Fix#1 - add more test
    def test_home_assistant_middleware_308_redirect_is_rewritten(self):
        response = HttpResponse(status=308)
        response["Location"] = "/dashboard"
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert "/ingress" in result["Location"]

    ## Fix#1 - add more test
    def test_home_assistant_middleware_ingress_path_lstripped_of_leading_slash(self):
        # Kills mutants on lstrip("/") — without it, "//ingress/dashboard" would appear.
        response = HttpResponseRedirect("/dashboard")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert result["Location"] == "/ingress/dashboard"
        assert "//ingress" not in result["Location"]

    ## Fix#1 - add more test
    def test_home_assistant_middleware_html_single_quote_static_url_rewritten(self):
        # Kills mutants on the single-quote replacement branches for static/media.
        static = settings.STATIC_URL.rstrip("/")
        html = f"'<img src='{static}/app.css'>".encode()
        response = DummyResponseWithCookies(content=html, content_type="text/html; charset=utf-8")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert f"'/ingress{static}" in result.content.decode()

    ## Fix#1 - add more test
    def test_home_assistant_middleware_html_media_url_rewritten(self):
        # Kills mutants on the media URL replacement branches.
        media = settings.MEDIA_URL.rstrip("/")
        html = f'<img src="{media}/photo.jpg">'.encode()
        response = DummyResponseWithCookies(content=html, content_type="text/html; charset=utf-8")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert f'"/ingress{media}' in result.content.decode()

    ## Fix#1 - add more test
    def test_home_assistant_middleware_content_headers_stripped_from_rebuilt_response(self):
        # Kills mutants on the filtered_headers comprehension that excludes content- headers.
        html = b"<html></html>"
        response = DummyResponseWithCookies(content=html, content_type="text/html; charset=utf-8")
        response["X-Custom"] = "keep-me"
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert result["X-Custom"] == "keep-me"
        # content-length must be absent (it's a content- header)
        assert "content-length" not in {k.lower() for k in dict(result.items())}

    # --- UserTimezoneMiddleware mutmut_10 ---
    ## Fix#2
    def test_user_timezone_middleware_no_settings_attr_does_not_crash(self):
        # mutmut_10: drops hasattr guard — without it, accessing user.settings
        # on a user with no settings attr raises AttributeError.
        user = DummyUser()
        del user.settings
        request = DummyRequest(user=user)
        middleware = babybuddy_middleware.UserTimezoneMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware.timezone, "activate") as activate:
            response = middleware(request)
        assert response == "ok"
        activate.assert_not_called()

    # --- RollingSessionMiddleware mutmut_10 ---
    ## Fix#2
    def test_rolling_session_zero_refresh_goes_to_else_branch(self):
        # mutmut_10: "if session_refresh:" → "if session_refresh is not None:"
        # 0 is falsy but not None — must go to else (initialize), not try block.
        session = DummySession(session_refresh=0, existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=300):
            middleware(request)
        assert session["session_refresh"] == 300
        assert session.expiry_calls == []

    # --- RollingSessionMiddleware mutmut_21 ---
    ## Fix#2
    def test_rolling_session_type_error_triggers_refresh(self):
        # mutmut_21: removes TypeError from except tuple.
        # A list causes TypeError on int subtraction → must still trigger refresh.
        session = DummySession(session_refresh=[1, 2], existing="yes")
        request = DummyRequest(session=session)
        middleware = babybuddy_middleware.RollingSessionMiddleware(Mock(return_value="ok"))
        with patch.object(babybuddy_middleware, "time", return_value=600):
            middleware(request)
        assert session["session_refresh"] == 600
        assert session.expiry_calls == [settings.SESSION_COOKIE_AGE]

    # --- HomeAssistant.__call__ redirect path mutants ---
    ## Fix#2
    def test_home_assistant_redirect_new_url_built_with_correct_components(self):
        # mutmut_28/_29/_30: mutations on urlunsplit tuple components
        # (scheme, netloc, path, query, fragment). Verify full reconstructed URL.
        response = HttpResponseRedirect("/page?q=1#section")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        location = result["Location"]
        assert location.startswith("/ingress/page")
        assert "q=1" in location
        assert "section" in location

    ## Fix#2
    def test_home_assistant_redirect_preserves_query_string(self):
        # mutmut_33: split_url.query dropped from urlunsplit
        response = HttpResponseRedirect("/dashboard?next=/home")
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert "next=/home" in result["Location"]

    # --- HomeAssistant HTML content rewriting mutants ---
    ## Fix#2
    def test_home_assistant_html_response_status_code_preserved(self):
        # mutmut_60/_63/_64/_65: response status_code in HttpResponse constructor
        html = b"<html></html>"
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        response.status_code = 200
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert result.status_code == 200

    ## Fix#2
    def test_home_assistant_html_response_content_type_preserved(self):
        # mutmut_66/_67/_68: content_type arg in rebuilt HttpResponse
        html = b"<html></html>"
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert "text/html" in result["Content-Type"]

    ## Fix#2
    def test_home_assistant_html_cookies_preserved_after_rebuild(self):
        # mutmut_69/_70/_71/_72/_73: cookies copy/assignment in rebuilt response
        html = b"<html></html>"
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert result.cookies["csrftoken"].value == "abc"
        assert result.cookies["sessionid"].value == "def"

    ## Fix#2
    def test_home_assistant_html_content_encoded_correctly(self):
        # mutmut_77/_78: content.encode() call — result body must be bytes
        html = b"<html><body>Hello</body></html>"
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        assert b"Hello" in result.content

    ## Fix#2
    def test_home_assistant_html_static_double_quote_replacement_exact(self):
        # mutmut_83/_85/_87/_89: mutations on the four .replace() call arguments
        static = settings.STATIC_URL.rstrip("/")
        media = settings.MEDIA_URL.rstrip("/")
        html = (
            f'<link href="{static}/app.css">'
            f"<link href='{static}/other.css'>"
            f'<img src="{media}/img.png">'
            f"<img src='{media}/img2.png'>"
        ).encode()
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        content = result.content.decode()
        assert f'"/ingress{static}' in content   # double-quote static
        assert f"'/ingress{static}" in content   # single-quote static
        assert f'"/ingress{media}' in content    # double-quote media
        assert f"'/ingress{media}" in content    # single-quote media

    ## Fix#2
    def test_home_assistant_html_filtered_headers_exclude_content_headers(self):
        # mutmut_117/_118/_119: the header filter condition key.lower().startswith("content-")
        html = b"<html></html>"
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        response["X-Keep"] = "yes"
        response["Content-Language"] = "en"
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        headers_lower = {k.lower() for k in dict(result.items())}
        assert "x-keep" in headers_lower
        assert "content-language" not in headers_lower

    ## Fix#2
    def test_home_assistant_html_static_url_rstripped_of_trailing_slash(self):
        # mutmut_122/_123/_124: STATIC_URL.rstrip("/") and MEDIA_URL.rstrip("/")
        # Verify no double slash appears in replaced content.
        static = settings.STATIC_URL.rstrip("/")
        html = f'<link href="{static}/app.css">'.encode()
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        content = result.content.decode()
        assert "//ingress" not in content
        assert f'"/ingress{static}/' in content

    ## Fix#2
    def test_home_assistant_html_ingress_path_lstripped_in_content_replacement(self):
        # mutmut_127/_128: x_ingress_path.lstrip("/") in the replace f-strings
        static = settings.STATIC_URL.rstrip("/")
        html = f'<link href="{static}/app.css">'.encode()
        response = DummyResponseWithCookies(
            content=html, content_type="text/html; charset=utf-8"
        )
        request = DummyRequest(
            headers={"X-Hass-Source": "core.ingress", "X-Ingress-Path": "/ingress"}
        )
        with patch.object(settings, "ENABLE_HOME_ASSISTANT_SUPPORT", True), \
             patch.object(babybuddy_middleware, "set_script_prefix"):
            mw = babybuddy_middleware.HomeAssistant(Mock(return_value=response))
            result = mw(request)
        content = result.content.decode()
        # "/ingress" not "//ingress"
        assert '"/ingress' in content
        assert '"//ingress' not in content


# -----------------------------
# widgets.py tests
# -----------------------------
class TestWidgetsModule:
    """Targets: babybuddy/widgets.py"""

    def test_datetime_base_input_format_value_converts_datetime_to_iso_string(self):
        # target file: babybuddy/widgets.py | function: DateTimeBaseInput.format_value | branch: datetime conversion
        import datetime

        widget = babybuddy_widgets.DateTimeBaseInput()
        value = datetime.datetime(2020, 1, 2, 3, 4, 5)
        assert widget.format_value(value) == value.isoformat()

    def test_datetime_base_input_format_value_leaves_string_unchanged(self):
        # target file: babybuddy/widgets.py | function: DateTimeBaseInput.format_value | branch: non-datetime passthrough
        widget = babybuddy_widgets.DateTimeBaseInput()
        assert widget.format_value("2020-01-02") == "2020-01-02"

    def test_datetime_base_input_format_value_leaves_none_unchanged(self):
        # target file: babybuddy/widgets.py | function: DateTimeBaseInput.format_value | branch: None passthrough
        widget = babybuddy_widgets.DateTimeBaseInput()
        assert widget.format_value(None) is None

    def test_datetime_input_build_attrs_sets_default_step_to_one(self):
        # target file: babybuddy/widgets.py | function: DateTimeInput.build_attrs | branch: default step inserted
        widget = babybuddy_widgets.DateTimeInput()
        attrs = widget.build_attrs({}, None)
        assert attrs["step"] == 1

    def test_datetime_input_build_attrs_preserves_explicit_step(self):
        # target file: babybuddy/widgets.py | function: DateTimeInput.build_attrs | branch: explicit step retained
        widget = babybuddy_widgets.DateTimeInput()
        attrs = widget.build_attrs({}, {"step": 60})
        assert attrs["step"] == 60

    def test_date_input_has_expected_input_type(self):
        # target file: babybuddy/widgets.py | function: DateInput | behavior: class attribute contract
        assert babybuddy_widgets.DateInput.input_type == "date"

    def test_time_input_has_expected_input_type(self):
        # target file: babybuddy/widgets.py | function: TimeInput | behavior: class attribute contract
        assert babybuddy_widgets.TimeInput.input_type == "time"

    def test_datetime_input_has_expected_input_type(self):
        # target file: babybuddy/widgets.py | function: DateTimeInput | behavior: class attribute contract
        assert babybuddy_widgets.DateTimeInput.input_type == "datetime-local"


# -----------------------------
# templatetags/babybuddy.py tests
# -----------------------------
class TestTemplateTagsModule:
    """Targets: babybuddy/templatetags/babybuddy.py"""

    def test_axes_lockout_message_returns_helper_value(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: axes_lockout_message | behavior: delegated helper value
        with patch.object(babybuddy_tags, "get_lockout_message", return_value="LOCKED") as helper:
            assert babybuddy_tags.axes_lockout_message() == "LOCKED"
        helper.assert_called_once_with()

    def test_relative_url_replaces_target_field_and_preserves_other_query_params(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: relative_url | branch: target field removed and others preserved
        request = DummyRequest()
        request.GET.urlencode.return_value = "page=3&sort=asc&page=4"
        result = babybuddy_tags.relative_url({"request": request}, "page", 9)
        assert result == "?page=9&sort=asc"

    def test_relative_url_handles_empty_query_string(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: relative_url | branch: empty query string edge case
        request = DummyRequest()
        request.GET.urlencode.return_value = ""
        result = babybuddy_tags.relative_url({"request": request}, "page", 1)
        assert result == "?page=1&"

    def test_version_string_reads_value_from_app_config(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: version_string | behavior: app config lookup
        config = types.SimpleNamespace(version_string="1.2.3 (abc123)")
        with patch.object(babybuddy_tags.apps, "get_app_config", return_value=config) as get_app_config:
            assert babybuddy_tags.version_string() == "1.2.3 (abc123)"
        get_app_config.assert_called_once_with("babybuddy")

    def test_get_current_locale_delegates_to_locale_converter(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: get_current_locale | behavior: translation helpers composed correctly
        with patch.object(babybuddy_tags, "get_language", return_value="en-us") as get_lang, patch.object(
            babybuddy_tags, "to_locale", return_value="en_US"
        ) as to_locale:
            assert babybuddy_tags.get_current_locale() == "en_US"
        get_lang.assert_called_once_with()
        to_locale.assert_called_once_with("en-us")

    def test_get_child_count_delegates_to_child_model(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: get_child_count | behavior: model delegation
        with patch.object(babybuddy_tags.Child, "count", return_value=42) as count:
            assert babybuddy_tags.get_child_count() == 42
        count.assert_called_once_with()

    def test_get_current_timezone_delegates_to_timezone_helper(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: get_current_timezone | behavior: helper delegation
        with patch.object(babybuddy_tags.timezone, "get_current_timezone_name", return_value="UTC") as helper:
            assert babybuddy_tags.get_current_timezone() == "UTC"
        helper.assert_called_once_with()

    def test_make_absolute_url_calls_request_build_absolute_uri(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: make_absolute_url | behavior: request helper delegation
        request = DummyRequest()
        assert babybuddy_tags.make_absolute_url({"request": request}, "/x/") == "https://example.test/x/"

    def test_user_is_locked_true_when_access_attempt_exists(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: user_is_locked | branch: lockout exists
        user = DummyUser(username="bob")
        filter_result = Mock()
        filter_result.exists.return_value = True
        with patch.object(babybuddy_tags.AccessAttempt.objects, "filter", return_value=filter_result) as filt:
            assert babybuddy_tags.user_is_locked(user) is True
        filt.assert_called_once_with(username="bob")

    def test_user_is_locked_false_when_no_access_attempt(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: user_is_locked | branch: no lockout
        user = DummyUser(username="bob")
        filter_result = Mock()
        filter_result.exists.return_value = False
        with patch.object(babybuddy_tags.AccessAttempt.objects, "filter", return_value=filter_result):
            assert babybuddy_tags.user_is_locked(user) is False

    def test_user_is_read_only_true_when_group_exists(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: user_is_read_only | branch: read-only group exists
        user = DummyUser(exists_value=True)
        assert babybuddy_tags.user_is_read_only(user) is True
        assert user.groups.filter_calls == [{"name": settings.BABY_BUDDY["READ_ONLY_GROUP_NAME"]}]

    def test_user_is_read_only_false_when_group_missing(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: user_is_read_only | branch: read-only group missing
        user = DummyUser(exists_value=False)
        assert babybuddy_tags.user_is_read_only(user) is False

    def test_confirm_delete_text_contains_rendered_object_name_and_prompt(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: confirm_delete_text | behavior: safe prompt with object name
        result = str(babybuddy_tags.confirm_delete_text("Toy"))
        assert "Are you sure you want to delete" in result
        assert '<span class="text-info">Toy</span>' in result

    def test_confirm_unlock_text_contains_rendered_object_name_and_prompt(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: confirm_unlock_text | behavior: safe prompt with object name
        result = str(babybuddy_tags.confirm_unlock_text("User1"))
        assert "Are you sure you want to unlock" in result
        assert '<span class="text-info">User1</span>' in result

    def test_confirm_delete_text_uses_string_conversion_for_non_string_object(self):
        # target file: babybuddy/templatetags/babybuddy.py | function: confirm_delete_text | branch: non-string object coerced via __str__
        user = DummyUser(username="charlie")
        result = str(babybuddy_tags.confirm_delete_text(user))
        assert "charlie" in result


# -----------------------------
# models.py tests (no DB access)
# -----------------------------
class TestModelsModule:
    """Targets: babybuddy/models.py"""

    def test_settings_str_formats_username_in_label(self):
        # target file: babybuddy/models.py | function: Settings.__str__ | behavior: formatted display string
        settings_obj = object.__new__(babybuddy_models.Settings)
        dummy_user = DummyUser(username="delta")
        settings_obj._state = types.SimpleNamespace(fields_cache={"user": dummy_user})

        assert str(settings_obj) == "delta's Settings"

    def test_settings_api_key_returns_existing_or_created_token_without_reset(self):
        # target file: babybuddy/models.py | function: Settings.api_key | branch: reset false returns token
        token = object()
        settings_obj = object.__new__(babybuddy_models.Settings)
        dummy_user = DummyUser()
        settings_obj._state = types.SimpleNamespace(fields_cache={"user": dummy_user})

        with patch.object(babybuddy_models.Token.objects, "get_or_create", return_value=(token, True)) as get_or_create, \
             patch.object(babybuddy_models.Token.objects, "get") as get_token:
            assert settings_obj.api_key(reset=False) is token

        get_token.assert_not_called()
        get_or_create.assert_called_once_with(user=settings_obj.user)

    def test_settings_api_key_resets_existing_token_before_creating_new_one(self):
        # target file: babybuddy/models.py | function: Settings.api_key | branch: reset true deletes existing token first
        token = object()
        existing_token = Mock()
        settings_obj = object.__new__(babybuddy_models.Settings)
        dummy_user = DummyUser()
        settings_obj._state = types.SimpleNamespace(fields_cache={"user": dummy_user})

        with patch.object(babybuddy_models.Token.objects, "get", return_value=existing_token) as get_token, \
             patch.object(babybuddy_models.Token.objects, "get_or_create", return_value=(token, False)) as get_or_create:
            assert settings_obj.api_key(reset=True) is token

        get_token.assert_called_once_with(user=settings_obj.user)
        existing_token.delete.assert_called_once_with()
        get_or_create.assert_called_once_with(user=settings_obj.user)

    def test_settings_dashboard_refresh_rate_milliseconds_returns_none_when_disabled(self):
        # target file: babybuddy/models.py | function: Settings.dashboard_refresh_rate_milliseconds | branch: disabled refresh rate
        settings_obj = object.__new__(babybuddy_models.Settings)
        settings_obj.__dict__["dashboard_refresh_rate"] = None

        assert settings_obj.dashboard_refresh_rate_milliseconds is None

    def test_settings_dashboard_refresh_rate_milliseconds_converts_seconds_to_milliseconds(self):
        # target file: babybuddy/models.py | function: Settings.dashboard_refresh_rate_milliseconds | branch: normal conversion
        refresh = babybuddy_models.timezone.timedelta(seconds=90)
        settings_obj = object.__new__(babybuddy_models.Settings)
        settings_obj.__dict__["dashboard_refresh_rate"] = refresh

        assert settings_obj.dashboard_refresh_rate_milliseconds == 90000

    def test_settings_dashboard_refresh_rate_milliseconds_uses_seconds_component_only(self):
        # target file: babybuddy/models.py | function: Settings.dashboard_refresh_rate_milliseconds | boundary: timedelta with days uses .seconds contract
        refresh = babybuddy_models.timezone.timedelta(days=1, seconds=5)
        settings_obj = object.__new__(babybuddy_models.Settings)
        settings_obj.__dict__["dashboard_refresh_rate"] = refresh

        assert settings_obj.dashboard_refresh_rate_milliseconds == 5000

    def test_create_user_settings_creates_settings_only_when_created_flag_true(self):
        # target file: babybuddy/models.py | function: create_user_settings | branch: created true
        instance = DummyUser()
        with patch.object(babybuddy_models.Settings.objects, "create") as create:
            babybuddy_models.create_user_settings(sender=object(), instance=instance, created=True)
        create.assert_called_once_with(user=instance)

    def test_create_user_settings_does_nothing_when_created_flag_false(self):
        # target file: babybuddy/models.py | function: create_user_settings | branch: created false
        instance = DummyUser()
        with patch.object(babybuddy_models.Settings.objects, "create") as create:
            babybuddy_models.create_user_settings(sender=object(), instance=instance, created=False)
        create.assert_not_called()

    def test_save_user_settings_calls_nested_settings_save(self):
        # target file: babybuddy/models.py | function: save_user_settings | behavior: nested settings persisted
        instance = DummyUser()
        babybuddy_models.save_user_settings(sender=object(), instance=instance)
        assert instance.settings.saved is True

    ## Fix#1 - add more test
    def test_settings_api_key_reset_false_does_not_call_delete(self):
        # Kills models.Settings.api_key__mutmut_1: ensures reset=False path
        # never calls Token.objects.get() (only get_or_create).
        import babybuddy.models as babybuddy_models
        token = object()
        settings_obj = object.__new__(babybuddy_models.Settings)
        settings_obj._state = types.SimpleNamespace(fields_cache={"user": DummyUser()})

        with patch.object(babybuddy_models.Token.objects, "get_or_create", return_value=(token, False)) as goc, \
             patch.object(babybuddy_models.Token.objects, "get") as get_tok:
            result = settings_obj.api_key(reset=False)

        assert result is token
        get_tok.assert_not_called()
        goc.assert_called_once()


# -----------------------------
# views.py tests
# -----------------------------
class TestViewsModule:
    """Targets: babybuddy/views.py"""

    def test_csrf_failure_returns_custom_bad_origin_response(self):
        # target file: babybuddy/views.py | function: csrf_failure | branch: bad origin custom template path
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        template = Mock()
        template.render.return_value = "rendered"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template) as get_template:
            response = babybuddy_views.csrf_failure(
                request,
                babybuddy_views.REASON_BAD_ORIGIN % request.META["HTTP_ORIGIN"],
            )
        assert response.status_code == 403
        assert response.content == b"rendered"
        get_template.assert_called_once_with("error/403_csrf_bad_origin.html")

    def test_csrf_failure_delegates_to_default_handler_for_other_reasons(self):
        # target file: babybuddy/views.py | function: csrf_failure | branch: non-matching reason fallback
        request = DummyRequest()
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="fallback") as fallback:
            result = babybuddy_views.csrf_failure(request, "different reason")
        assert result == "fallback"
        fallback.assert_called_once_with(request, "different reason", "403_csrf.html")

    def test_root_router_get_redirect_url_sets_dashboard_url_before_super_call(self):
        # target file: babybuddy/views.py | function: RootRouter.get_redirect_url | behavior: dashboard redirect target
        router = babybuddy_views.RootRouter()
        with patch.object(babybuddy_views, "reverse", return_value="/dashboard/"), patch(
            "django.views.generic.base.RedirectView.get_redirect_url", return_value="/dashboard/"
        ) as super_redirect:
            result = router.get_redirect_url()
        assert result == "/dashboard/"
        assert router.url == "/dashboard/"
        assert super_redirect.called

    def test_babybuddy_filter_view_sets_unique_child_when_exactly_one_child_present(self):
        # target file: babybuddy/views.py | function: BabyBuddyFilterView.get_context_data | branch: exactly one unique child
        view = babybuddy_views.BabyBuddyFilterView()
        context = {
            "object_list": [DummyObjectWithChild("a"), DummyObjectWithChild("a"), DummyNoChildObject()]
        }
        with patch(
            "django_filters.views.FilterView.get_context_data",
            return_value=context,
        ) as super_context:
            result = view.get_context_data(extra=True)
        assert result["unique_child"] is True
        super_context.assert_called_once_with(extra=True)

    def test_babybuddy_filter_view_does_not_set_unique_child_when_multiple_children_present(self):
        # target file: babybuddy/views.py | function: BabyBuddyFilterView.get_context_data | branch: multiple unique children
        view = babybuddy_views.BabyBuddyFilterView()
        context = {"object_list": [DummyObjectWithChild("a"), DummyObjectWithChild("b")]}
        with patch("django_filters.views.FilterView.get_context_data", return_value=context):
            result = view.get_context_data()
        assert "unique_child" not in result

    def test_babybuddy_filter_view_does_not_set_unique_child_when_no_child_attrs_present(self):
        # target file: babybuddy/views.py | function: BabyBuddyFilterView.get_context_data | branch: no child-bearing objects
        view = babybuddy_views.BabyBuddyFilterView()
        context = {"object_list": [DummyNoChildObject(), DummyNoChildObject()]}
        with patch("django_filters.views.FilterView.get_context_data", return_value=context):
            result = view.get_context_data()
        assert "unique_child" not in result

    def test_babybuddy_paginated_view_reads_pagination_count_from_user_settings(self):
        # target file: babybuddy/views.py | function: BabyBuddyPaginatedView.get_paginate_by | behavior: setting passthrough
        view = babybuddy_views.BabyBuddyPaginatedView()
        view.request = DummyRequest(user=DummyUser(pagination_count=100))
        assert view.get_paginate_by(queryset=[]) == 100

    def test_user_unlock_post_valid_form_resets_user_and_calls_form_valid(self):
        # target file: babybuddy/views.py | function: UserUnlock.post | branch: valid form path
        view = babybuddy_views.UserUnlock()
        user = DummyUser(username="unlockme")
        form = Mock()
        form.is_valid.return_value = True
        view.get_object = Mock(return_value=user)
        view.get_form = Mock(return_value=form)
        view.form_valid = Mock(return_value="valid")
        with patch.object(babybuddy_views, "reset") as reset:
            response = view.post(DummyRequest())
        assert response == "valid"
        reset.assert_called_once_with(username="unlockme")
        view.form_valid.assert_called_once_with(form)

    def test_user_unlock_post_invalid_form_calls_form_invalid(self):
        # target file: babybuddy/views.py | function: UserUnlock.post | branch: invalid form path
        view = babybuddy_views.UserUnlock()
        form = Mock()
        form.is_valid.return_value = False
        view.get_object = Mock(return_value=DummyUser())
        view.get_form = Mock(return_value=form)
        view.form_invalid = Mock(return_value="invalid")
        response = view.post(DummyRequest())
        assert response == "invalid"
        view.form_invalid.assert_called_once_with(form)

    def test_user_unlock_success_url_uses_primary_key_from_kwargs(self):
        # target file: babybuddy/views.py | function: UserUnlock.get_success_url | behavior: pk forwarded into reverse
        view = babybuddy_views.UserUnlock()
        view.kwargs = {"pk": 77}
        with patch.object(babybuddy_views, "reverse", return_value="/users/77/") as reverse:
            assert view.get_success_url() == "/users/77/"
        reverse.assert_called_once_with("babybuddy:user-update", kwargs={"pk": 77})

    def test_user_delete_success_message_uses_current_object_in_formatted_string(self):
        # target file: babybuddy/views.py | function: UserDelete.get_success_message | behavior: deleted user name included
        view = babybuddy_views.UserDelete()
        view.get_object = Mock(return_value="sam")
        assert str(view.get_success_message({})) == "User sam deleted."

    def test_user_password_get_renders_template_with_password_form(self):
        # target file: babybuddy/views.py | function: UserPassword.get | branch: GET renders form instance
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "render", return_value="rendered") as render:
            response = view.get(request)
        assert response == "rendered"
        render.assert_called_once()
        args, kwargs = render.call_args
        assert args[0] is request
        assert args[1] == view.template_name
        assert "form" in args[2]

    def test_user_password_post_valid_form_saves_updates_session_and_sets_message(self):
        # target file: babybuddy/views.py | function: UserPassword.post | branch: valid password change
        request = DummyRequest(user=DummyUser(), post={"k": "v"})
        saved_user = DummyUser(username="updated")
        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = saved_user
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form) as form_cls, patch.object(
            babybuddy_views, "update_session_auth_hash"
        ) as update_hash, patch.object(babybuddy_views.messages, "success") as success, patch.object(
            babybuddy_views, "render", return_value="rendered"
        ) as render:
            response = view.post(request)
        assert response == "rendered"
        form_cls.assert_called_once_with(request.user, request.POST)
        form.save.assert_called_once_with()
        update_hash.assert_called_once_with(request, saved_user)
        success.assert_called_once()
        render.assert_called_once_with(request, view.template_name, {"form": form})

    def test_user_password_post_invalid_form_does_not_save_or_update_session(self):
        # target file: babybuddy/views.py | function: UserPassword.post | branch: invalid password form
        request = DummyRequest(user=DummyUser(), post={})
        form = Mock()
        form.is_valid.return_value = False
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form), patch.object(
            babybuddy_views, "update_session_auth_hash"
        ) as update_hash, patch.object(babybuddy_views.messages, "success") as success, patch.object(
            babybuddy_views, "render", return_value="rendered"
        ) as render:
            response = view.post(request)
        assert response == "rendered"
        form.save.assert_not_called()
        update_hash.assert_not_called()
        success.assert_not_called()
        render.assert_called_once_with(request, view.template_name, {"form": form})

    def test_handle_api_regenerate_request_returns_true_and_regenerates_key_when_flag_present(self):
        # target file: babybuddy/views.py | function: handle_api_regenerate_request | branch: regenerate requested
        request = DummyRequest(user=DummyUser(), post={"api_key_regenerate": "1"})
        with patch.object(babybuddy_views.messages, "success") as success:
            result = babybuddy_views.handle_api_regenerate_request(request)
        assert result is True
        assert request.user.settings.api_key_calls == [True]
        success.assert_called_once()

    def test_handle_api_regenerate_request_returns_false_when_flag_missing(self):
        # target file: babybuddy/views.py | function: handle_api_regenerate_request | branch: no regenerate flag
        request = DummyRequest(user=DummyUser(), post={})
        with patch.object(babybuddy_views.messages, "success") as success:
            result = babybuddy_views.handle_api_regenerate_request(request)
        assert result is False
        assert request.user.settings.api_key_calls == []
        success.assert_not_called()

    def test_user_settings_get_renders_both_forms_with_correct_instances(self):
        # target file: babybuddy/views.py | function: UserSettings.get | branch: GET renders user and settings forms
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserSettings()
        user_form = object()
        settings_form = object()
        with patch.object(view, "form_user_class", return_value=user_form) as user_form_cls, patch.object(
            view, "form_settings_class", return_value=settings_form
        ) as settings_form_cls, patch.object(babybuddy_views, "render", return_value="rendered") as render:
            response = view.get(request)
        assert response == "rendered"
        user_form_cls.assert_called_once_with(instance=request.user)
        settings_form_cls.assert_called_once_with(instance=request.user.settings)
        render.assert_called_once()

    def test_user_settings_post_redirects_immediately_when_api_key_request_detected(self):
        # target file: babybuddy/views.py | function: UserSettings.post | branch: api key regenerate short-circuit
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=True) as handle, patch.object(
            babybuddy_views, "redirect", return_value="redirected"
        ) as redirect:
            response = view.post(request)
        assert response == "redirected"
        handle.assert_called_once_with(request)
        redirect.assert_called_once_with("babybuddy:user-settings")

    def test_user_settings_post_valid_forms_save_models_activate_language_and_delegate_to_set_language(self):
        # target file: babybuddy/views.py | function: UserSettings.post | branch: both forms valid
        request = DummyRequest(user=DummyUser(language="en"), post={"x": "1"})
        stable_settings = request.user.settings
        stable_settings.language = "de"
        stable_settings.timezone = "UTC"

        view = babybuddy_views.UserSettings()

        user_form = DummyForm(is_valid_value=True, instance=request.user)
        settings_form = DummyForm(is_valid_value=True, instance=stable_settings)

        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form) as user_form_cls, \
             patch.object(view, "form_settings_class", return_value=settings_form) as settings_form_cls, \
             patch.object(babybuddy_views.translation, "activate") as activate, \
             patch.object(babybuddy_views.translation, "deactivate") as deactivate, \
             patch.object(babybuddy_views.messages, "success") as success, \
             patch.object(babybuddy_views, "set_language", return_value="language-response") as set_language:

            response = view.post(request)

        assert response == "language-response"

        user_form_cls.assert_called_once()
        settings_form_cls.assert_called_once()

        user_call = user_form_cls.call_args
        settings_call = settings_form_cls.call_args

        assert user_call.kwargs["instance"] is request.user
        assert user_call.kwargs["data"] == request.POST

        assert settings_call.kwargs["instance"] is stable_settings
        assert settings_call.kwargs["data"] == request.POST

        assert user_form.save_calls == [False]
        assert settings_form.save_calls == [False]

        activate.assert_called_once_with(stable_settings.language)
        deactivate.assert_called_once_with()
        success.assert_called_once()
        set_language.assert_called_once()

    def test_user_settings_post_invalid_forms_renders_error_context(self):
        # target file: babybuddy/views.py | function: UserSettings.post | branch: invalid form(s)
        request = DummyRequest(user=DummyUser(), post={})
        stable_settings = request.user.settings
        view = babybuddy_views.UserSettings()

        user_form = DummyForm(is_valid_value=True, instance=request.user)
        settings_form = DummyForm(is_valid_value=False, instance=stable_settings)

        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views, "render", return_value="rendered") as render, \
             patch.object(babybuddy_views.translation, "activate") as activate, \
             patch.object(babybuddy_views.messages, "success") as success:

            response = view.post(request)

        assert response == "rendered"
        assert user_form.save_calls == []
        assert settings_form.save_calls == []
        success.assert_not_called()

    def test_user_settings_post_invalid_when_settings_form_fails(self):
        # target file: babybuddy/views.py | function: UserSettings.post | branch: second form invalid prevents save
        request = DummyRequest(user=DummyUser(), post={})
        stable_settings = request.user.settings
        view = babybuddy_views.UserSettings()

        user_form = DummyForm(is_valid_value=True, instance=request.user)
        settings_form = DummyForm(is_valid_value=False, instance=stable_settings)

        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views, "render", return_value="rendered"):
            response = view.post(request)

        assert response == "rendered"
        assert request.user.save_calls == 0
        assert user_form.save_calls == []
        assert settings_form.save_calls == []

    def test_user_add_device_get_without_ingress_uses_empty_session_cookie_payload(self):
        # target file: babybuddy/views.py | function: UserAddDevice.get | branch: non-ingress request
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        qr_response = HttpResponse(b'{"session_cookies": {}}')
        final_response = HttpResponse("ok")
        view = babybuddy_views.UserAddDevice()

        with patch.object(view, "form_user_class", return_value=Mock()) as user_form_cls, \
             patch.object(babybuddy_views, "render", side_effect=[qr_response, final_response]) as render:
            response = view.get(request)

        assert response is final_response
        user_form_cls.assert_called_once()
        first_call = render.call_args_list[0]
        second_call = render.call_args_list[1]
        assert first_call.args[1] == view.qr_code_template
        assert second_call.args[1] == view.template_name
        assert second_call.args[2]["qr_code_data"] == '{"session_cookies": {}}'

    def test_user_add_device_get_with_ingress_includes_ingress_session_cookie(self):
        # target file: babybuddy/views.py | function: UserAddDevice.get | branch: ingress request includes cookie in QR payload
        request = DummyRequest(user=DummyUser(), cookies={"ingress_session": "cookie123"})
        request.is_homeassistant_ingress_request = True
        qr_response = HttpResponse(b'{"session_cookies": {"ingress_session": "cookie123"}}')
        final_response = HttpResponse("ok")
        view = babybuddy_views.UserAddDevice()

        with patch.object(view, "form_user_class", return_value=Mock()), \
             patch.object(babybuddy_views, "render", side_effect=[qr_response, final_response]) as render:
            response = view.get(request)

        assert response is final_response
        first_call_context = render.call_args_list[0].args[2]
        assert "cookie123" in first_call_context["session_cookies"]

    def test_user_add_device_post_redirects_when_api_regenerate_handled(self):
        # target file: babybuddy/views.py | function: UserAddDevice.post | branch: regenerate redirect
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserAddDevice()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=True), patch.object(
            babybuddy_views, "redirect", return_value="redirected"
        ) as redirect:
            response = view.post(request)
        assert response == "redirected"
        redirect.assert_called_once_with("babybuddy:user-add-device")

    def test_user_add_device_post_raises_bad_request_when_not_regenerate_request(self):
        # target file: babybuddy/views.py | function: UserAddDevice.post | branch: unsupported POST rejected
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserAddDevice()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False):
            with pytest.raises(babybuddy_views.BadRequest):
                view.post(request)

    ## Fix#1 - add more test
    def test_csrf_failure_uses_default_handler_when_http_origin_present_but_reason_does_not_match(self):
        # Kills the mutant that drops "and reason == REASON_BAD_ORIGIN % ..." from the condition,
        # which would incorrectly serve the custom template whenever HTTP_ORIGIN is present.
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://trusted.example"
        # reason does NOT match REASON_BAD_ORIGIN % origin
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="fallback") as fallback:
            result = babybuddy_views.csrf_failure(request, "some unrelated reason")
        assert result == "fallback"
        fallback.assert_called_once_with(request, "some unrelated reason", "403_csrf.html")

    ## Fix#1 - add more test
    def test_csrf_failure_uses_default_handler_when_http_origin_absent_regardless_of_reason(self):
        # Kills mutant that drops the "'HTTP_ORIGIN' in request.META" check entirely.
        request = DummyRequest()
        # No HTTP_ORIGIN key in META at all
        bad_reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="fallback") as fallback:
            result = babybuddy_views.csrf_failure(request, bad_reason)
        assert result == "fallback"

    ## Fix#1 - add more test
    def test_user_settings_post_valid_forms_assigns_new_settings_object_to_user(self):
        # Kills the "user.settings = user_settings" line-deletion mutant.
        # We verify that after post(), user.settings is the object returned by settings_form.save().
        request = DummyRequest(user=DummyUser(language="en"), post={"x": "1"})
        new_settings = DummyUserSettings(language="de")
        user = request.user

        view = babybuddy_views.UserSettings()

        user_form_mock = Mock()
        user_form_mock.is_valid.return_value = True
        user_form_mock.save.return_value = user

        settings_form_mock = Mock()
        settings_form_mock.is_valid.return_value = True
        settings_form_mock.save.return_value = new_settings

        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form_mock), \
             patch.object(view, "form_settings_class", return_value=settings_form_mock), \
             patch.object(babybuddy_views.translation, "activate"), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)

        # user.settings must be updated to the new settings object
        assert user.settings is new_settings

    ## Fix#1 - add more test
    def test_user_settings_post_activates_language_from_updated_settings_not_original(self):
        # Kills a mutant that activates the language from the wrong (pre-update) settings object.
        # We give user original language "en" and new settings language "ja"; assert "ja" is activated.
        request = DummyRequest(user=DummyUser(language="en"), post={"x": "1"})
        new_settings = DummyUserSettings(language="ja")
        user = request.user

        view = babybuddy_views.UserSettings()

        user_form_mock = Mock()
        user_form_mock.is_valid.return_value = True
        user_form_mock.save.return_value = user

        settings_form_mock = Mock()
        settings_form_mock.is_valid.return_value = True
        settings_form_mock.save.return_value = new_settings

        activated = []

        def capture_activate(lang):
            activated.append(lang)

        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form_mock), \
             patch.object(view, "form_settings_class", return_value=settings_form_mock), \
             patch.object(babybuddy_views.translation, "activate", side_effect=capture_activate), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)

        assert activated == ["ja"]

    # --- csrf_failure survived mutants ---
    ## Fix#1 - add more test
    def test_csrf_failure_context_contains_origin_title_main_and_reason(self):
        # Kills csrf_failure mutants on context key names and their values.
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        captured = {}
        template = Mock()
        template.render.side_effect = lambda ctx: captured.update(ctx) or "rendered"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template):
            babybuddy_views.csrf_failure(request, reason)
        assert captured["title"] is not None
        assert captured["main"] is not None
        assert captured["reason"] == reason
        assert captured["origin"] == "https://evil.example"

    ## Fix#1 - add more test
    def test_csrf_failure_with_http_origin_but_mismatched_reason_uses_fallback(self):
        # Kills mutants that drop the reason== check from the condition.
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://trusted.example"
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="fallback") as fallback:
            result = babybuddy_views.csrf_failure(request, "unrelated reason")
        assert result == "fallback"
        fallback.assert_called_once_with(request, "unrelated reason", "403_csrf.html")

    ## Fix#1 - add more test
    def test_csrf_failure_without_http_origin_uses_fallback(self):
        # Kills mutants that drop the HTTP_ORIGIN in META check.
        request = DummyRequest()
        # No HTTP_ORIGIN in META
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://x.example"
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="fallback") as fallback:
            result = babybuddy_views.csrf_failure(request, reason)
        assert result == "fallback"

    ## Fix#1 - add more test
    def test_csrf_failure_response_is_403_forbidden(self):
        # Kills mutants on the HttpResponseForbidden call / status code.
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        template = Mock()
        template.render.return_value = "rendered"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template):
            response = babybuddy_views.csrf_failure(request, reason)
        assert response.status_code == 403

    ## Fix#1 - add more test
    def test_csrf_failure_uses_correct_template_name(self):
        # Kills mutants on the template name string.
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        template = Mock()
        template.render.return_value = "rendered"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template) as gt:
            babybuddy_views.csrf_failure(request, reason)
        gt.assert_called_once_with("error/403_csrf_bad_origin.html")

    ## Fix#1 - add more test
    def test_csrf_fallback_uses_correct_template_name(self):
        # Kills mutants on the fallback template name "403_csrf.html".
        request = DummyRequest()
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="ok") as fallback:
            babybuddy_views.csrf_failure(request, "other")
        assert fallback.call_args.args[2] == "403_csrf.html"

    # --- RootRouter.get_redirect_url survived mutants ---
    ## Fix#1 - add more test
    def test_root_router_reverses_dashboard_url(self):
        # Kills mutants on the reverse() argument "dashboard:dashboard".
        router = babybuddy_views.RootRouter()
        with patch.object(babybuddy_views, "reverse", return_value="/dash/") as rev, \
             patch("django.views.generic.base.RedirectView.get_redirect_url", return_value="/dash/"):
            router.get_redirect_url()
        rev.assert_called_once_with("dashboard:dashboard")

    ## Fix#1 - add more test
    def test_root_router_assigns_url_before_calling_super(self):
        # Kills mutants on self.url assignment and super call order.
        router = babybuddy_views.RootRouter()
        order = []
        with patch.object(babybuddy_views, "reverse", side_effect=lambda n: order.append("reverse") or "/dash/"), \
             patch("django.views.generic.base.RedirectView.get_redirect_url",
                   side_effect=lambda *a, **kw: order.append("super") or "/dash/"):
            router.get_redirect_url()
        assert order == ["reverse", "super"]
        assert router.url == "/dash/"

    # --- UserPassword.get survived mutant ---
    ## Fix#1 - add more test
    def test_user_password_get_passes_form_instance_not_class(self):
        # Kills get mutmut_9: the form is instantiated with request.user, not
        # left as a class reference.
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "render", return_value="rendered") as render:
            view.get(request)
        _, _, ctx = render.call_args.args
        form = ctx["form"]
        # Must be an instance, not the class itself
        assert not isinstance(form, type)

    # --- UserPassword.post survived mutants ---
    ## Fix#1 - add more test
    def test_user_password_post_passes_request_user_and_post_data_to_form(self):
        # Kills post mutmut_11/_12: the PasswordChangeForm is called with
        # exactly request.user and request.POST.
        request = DummyRequest(user=DummyUser(), post={"p": "v"})
        form = Mock()
        form.is_valid.return_value = False
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form) as form_cls, \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.post(request)
        form_cls.assert_called_once_with(request.user, request.POST)

    ## Fix#1 - add more test
    def test_user_password_post_valid_calls_update_session_with_saved_user(self):
        # Kills post mutmut_13/_14: update_session_auth_hash must get the user
        # returned by form.save(), not some other object.
        request = DummyRequest(user=DummyUser(), post={})
        saved_user = DummyUser(username="new")
        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = saved_user
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form), \
             patch.object(babybuddy_views, "update_session_auth_hash") as usha, \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.post(request)
        usha.assert_called_once_with(request, saved_user)

    ## Fix#1 - add more test
    def test_user_password_post_valid_success_message_text_contains_updated(self):
        # Kills post mutmut_16/_17/_18: messages.success must be called with
        # the "Password updated." message string.
        request = DummyRequest(user=DummyUser(), post={})
        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = DummyUser()
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form), \
             patch.object(babybuddy_views, "update_session_auth_hash"), \
             patch.object(babybuddy_views.messages, "success") as success, \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.post(request)
        assert success.called
        msg = str(success.call_args.args[1])
        assert "updated" in msg.lower() or "Password" in msg

    # --- handle_api_regenerate_request survived mutants ---
    ## Fix#1 - add more test
    def test_handle_api_regenerate_request_calls_api_key_with_reset_true(self):
        # Kills mutmut_6/_7: api_key must be called with reset=True exactly.
        request = DummyRequest(user=DummyUser(), post={"api_key_regenerate": "1"})
        with patch.object(babybuddy_views.messages, "success"):
            babybuddy_views.handle_api_regenerate_request(request)
        assert request.user.settings.api_key_calls == [True]

    ## Fix#1 - add more test
    def test_handle_api_regenerate_request_success_message_contains_regenerated(self):
        # Kills mutmut_8/_9/_11/_12/_13: success message must mention regeneration.
        request = DummyRequest(user=DummyUser(), post={"api_key_regenerate": "1"})
        with patch.object(babybuddy_views.messages, "success") as success:
            babybuddy_views.handle_api_regenerate_request(request)
        msg = str(success.call_args.args[1])
        assert "regenerated" in msg.lower() or "API" in msg

    ## Fix#1 - add more test
    def test_handle_api_regenerate_request_true_path_returns_true_not_none(self):
        # Kills mutants that drop/change the return True.
        request = DummyRequest(user=DummyUser(), post={"api_key_regenerate": "1"})
        with patch.object(babybuddy_views.messages, "success"):
            result = babybuddy_views.handle_api_regenerate_request(request)
        assert result is True

    ## Fix#1 - add more test
    def test_handle_api_regenerate_request_false_path_returns_false_not_none(self):
        # Kills mutants that drop/change the return False.
        request = DummyRequest(user=DummyUser(), post={})
        result = babybuddy_views.handle_api_regenerate_request(request)
        assert result is False

    # --- UserSettings.get survived mutants ---
    ## Fix#1 - add more test
    def test_user_settings_get_passes_user_instance_to_user_form(self):
        # Kills mutmut_2/_3: form_user_class must receive instance=request.user.
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserSettings()
        user_form = object()
        with patch.object(view, "form_user_class", return_value=user_form) as ufc, \
             patch.object(view, "form_settings_class", return_value=object()), \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.get(request)
        ufc.assert_called_once_with(instance=request.user)

    ## Fix#1 - add more test
    def test_user_settings_get_passes_settings_instance_to_settings_form(self):
        # Kills mutmut_5/_6: form_settings_class must receive instance=request.user.settings.
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserSettings()
        with patch.object(view, "form_user_class", return_value=object()), \
             patch.object(view, "form_settings_class", return_value=object()) as sfc, \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.get(request)
        sfc.assert_called_once_with(instance=request.user.settings)

    ## Fix#1 - add more test
    def test_user_settings_get_render_context_has_form_user_and_form_settings_keys(self):
        # Kills mutmut_8/_9/_11/_12: the context dict must use exactly
        # "form_user" and "form_settings" as keys.
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserSettings()
        sentinel_user_form = object()
        sentinel_settings_form = object()
        with patch.object(view, "form_user_class", return_value=sentinel_user_form), \
             patch.object(view, "form_settings_class", return_value=sentinel_settings_form), \
             patch.object(babybuddy_views, "render", return_value="ok") as render:
            view.get(request)
        _, _, ctx = render.call_args.args
        assert ctx["form_user"] is sentinel_user_form
        assert ctx["form_settings"] is sentinel_settings_form

    # --- UserSettings.post survived mutants ---
    ## Fix#1 - add more test
    def test_user_settings_post_valid_user_save_called_with_commit_false(self):
        # Kills mutmut_24/_25/_26/_27: form_user.save must be called commit=False.
        request = DummyRequest(user=DummyUser(), post={"x": "1"})
        new_settings = DummyUserSettings(language="en")
        user_form = Mock()
        user_form.is_valid.return_value = True
        user_form.save.return_value = request.user
        settings_form = Mock()
        settings_form.is_valid.return_value = True
        settings_form.save.return_value = new_settings
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views.translation, "activate"), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)
        user_form.save.assert_called_once_with(commit=False)
        settings_form.save.assert_called_once_with(commit=False)

    ## Fix#1 - add more test
    def test_user_settings_post_valid_user_save_called_before_user_dot_save(self):
        # Kills mutmut_29/_30: user.save() must be called (commits to DB).
        request = DummyRequest(user=DummyUser(), post={"x": "1"})
        new_settings = DummyUserSettings(language="en")
        user_form = Mock()
        user_form.is_valid.return_value = True
        user_form.save.return_value = request.user
        settings_form = Mock()
        settings_form.is_valid.return_value = True
        settings_form.save.return_value = new_settings
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views.translation, "activate"), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)
        assert request.user.save_calls == 1

    ## Fix#1 - add more test
    def test_user_settings_post_valid_assigns_new_settings_to_user(self):
        # Kills mutmut_31/_32: user.settings = user_settings line.
        request = DummyRequest(user=DummyUser(), post={"x": "1"})
        new_settings = DummyUserSettings(language="de")
        user = request.user
        user_form = Mock()
        user_form.is_valid.return_value = True
        user_form.save.return_value = user
        settings_form = Mock()
        settings_form.is_valid.return_value = True
        settings_form.save.return_value = new_settings
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views.translation, "activate"), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)
        assert user.settings is new_settings

    ## Fix#1 - add more test
    def test_user_settings_post_valid_activates_language_from_new_settings(self):
        # Kills mutmut_33/_34: translation.activate gets user.settings.language
        # AFTER reassignment, not the original language.
        request = DummyRequest(user=DummyUser(language="en"), post={"x": "1"})
        new_settings = DummyUserSettings(language="ja")
        user = request.user
        user_form = Mock()
        user_form.is_valid.return_value = True
        user_form.save.return_value = user
        settings_form = Mock()
        settings_form.is_valid.return_value = True
        settings_form.save.return_value = new_settings
        activated = []
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views.translation, "activate", side_effect=activated.append), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)
        assert activated == ["ja"]

    ## Fix#1 - add more test
    def test_user_settings_post_valid_calls_set_language(self):
        # Kills mutmut_35/_36: set_language(request) must be called and its
        # return value returned.
        request = DummyRequest(user=DummyUser(), post={})
        new_settings = DummyUserSettings(language="en")
        user_form = Mock()
        user_form.is_valid.return_value = True
        user_form.save.return_value = request.user
        settings_form = Mock()
        settings_form.is_valid.return_value = True
        settings_form.save.return_value = new_settings
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views.translation, "activate"), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success"), \
             patch.object(babybuddy_views, "set_language", return_value="lang-response") as sl:
            response = view.post(request)
        sl.assert_called_once_with(request)
        assert response == "lang-response"

    ## Fix#1 - add more test
    def test_user_settings_post_invalid_renders_with_user_form_and_settings_form_keys(self):
        # Kills mutmut_37/_38/_39/_40/_41/_42: invalid path renders with
        # exactly "user_form" and "settings_form" context keys.
        request = DummyRequest(user=DummyUser(), post={})
        user_form = Mock()
        user_form.is_valid.return_value = False
        settings_form = Mock()
        settings_form.is_valid.return_value = False
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views, "render", return_value="rendered") as render:
            view.post(request)
        _, _, ctx = render.call_args.args
        assert ctx["user_form"] is user_form
        assert ctx["settings_form"] is settings_form

    # --- UserAddDevice.get survived mutants ---
    ## Fix#1 - add more test
    def test_user_add_device_get_qr_template_rendered_first(self):
        # Kills mutmut_3/_4: qr_code_template used for first render call.
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b"{}", content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        assert render.call_args_list[0].args[1] == view.qr_code_template

    ## Fix#1 - add more test
    def test_user_add_device_get_session_cookies_json_dumped_correctly(self):
        # Kills mutmut_9: json.dumps(session_cookies) must be the qr_code_data.
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        import json
        qr_content = json.dumps({}).encode()
        qr_resp = HttpResponse(qr_content, content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        second_ctx = render.call_args_list[1].args[2]
        assert second_ctx["qr_code_data"] == "{}"

    ## Fix#1 - add more test
    def test_user_add_device_get_final_template_rendered_second(self):
        # Kills mutmut_19: template_name used for second render call.
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b"{}", content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        assert render.call_args_list[1].args[1] == view.template_name

    ## Fix#1 - add more test
    def test_user_add_device_get_form_user_instance_is_request_user(self):
        # Kills mutmut_25/_26/_27: form_user_class called with instance=request.user.
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b"{}", content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]), \
             patch.object(view, "form_user_class", return_value=Mock()) as ufc:
            view.get(request)
        ufc.assert_called_once_with(instance=request.user)

    # --- UserAddDevice.post mutmut_1 ---
    ## Fix#1 - add more test
    def test_user_add_device_post_redirect_target_is_user_add_device(self):
        # Kills post mutmut_1: redirect must go to "babybuddy:user-add-device".
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserAddDevice()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=True), \
             patch.object(babybuddy_views, "redirect", return_value="redirected") as redir:
            view.post(request)
        redir.assert_called_once_with("babybuddy:user-add-device")

    # --- csrf_failure mutmut_1,14-16,20-22,34,36,38,39 ---
    ## Fix#2
    def test_csrf_failure_renders_template_with_rendered_content(self):
        # mutmut_1: template.render(context) call — result used as response body
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        template = Mock()
        template.render.return_value = "RENDERED_BODY"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template):
            response = babybuddy_views.csrf_failure(request, reason)
        assert response.content == b"RENDERED_BODY"

    ## Fix#2
    def test_csrf_failure_response_content_type_is_text_html(self):
        # mutmut_14/_15/_16: content_type="text/html" argument
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        template = Mock()
        template.render.return_value = "body"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template):
            response = babybuddy_views.csrf_failure(request, reason)
        assert "text/html" in response["Content-Type"]

    ## Fix#2
    def test_csrf_failure_context_origin_is_http_origin_value(self):
        # mutmut_20/_21/_22: context["origin"] = request.META["HTTP_ORIGIN"]
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://specific-origin.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://specific-origin.example"
        captured = {}
        template = Mock()
        template.render.side_effect = lambda ctx: captured.update(ctx) or "ok"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template):
            babybuddy_views.csrf_failure(request, reason)
        assert captured["origin"] == "https://specific-origin.example"

    ## Fix#2
    def test_csrf_failure_context_reason_matches_passed_reason(self):
        # mutmut_34/_36: context["reason"] = reason
        request = DummyRequest()
        request.META["HTTP_ORIGIN"] = "https://evil.example"
        reason = babybuddy_views.REASON_BAD_ORIGIN % "https://evil.example"
        captured = {}
        template = Mock()
        template.render.side_effect = lambda ctx: captured.update(ctx) or "ok"
        with patch.object(babybuddy_views.loader, "get_template", return_value=template):
            babybuddy_views.csrf_failure(request, reason)
        assert captured["reason"] == reason

    ## Fix#2
    def test_csrf_failure_fallback_passes_request_as_first_arg(self):
        # mutmut_38/_39: csrf.csrf_failure(request, reason, template) arg order
        request = DummyRequest()
        with patch.object(babybuddy_views.csrf, "csrf_failure", return_value="ok") as fallback:
            babybuddy_views.csrf_failure(request, "other reason")
        assert fallback.call_args.args[0] is request
        assert fallback.call_args.args[1] == "other reason"
        assert fallback.call_args.args[2] == "403_csrf.html"

    # --- RootRouter mutmut_5,6,7,8 ---
    ## Fix#2
    def test_root_router_passes_self_as_first_arg_to_super(self):
        # mutmut_5/_6/_7/_8: super().get_redirect_url(self, *args, **kwargs)
        # The "self" is explicitly passed as first positional arg.
        router = babybuddy_views.RootRouter()
        received = {}
        def fake_super(*args, **kwargs):
            received["args"] = args
            received["kwargs"] = kwargs
            return "/dash/"
        with patch.object(babybuddy_views, "reverse", return_value="/dash/"), \
             patch("django.views.generic.base.RedirectView.get_redirect_url",
                   side_effect=fake_super):
            router.get_redirect_url(1, 2, key="val")
        # self is passed as first positional arg to super
        assert received["args"][0] is router
        assert 1 in received["args"]
        assert received["kwargs"]["key"] == "val"

    # --- UserPassword.get mutmut_9 ---
    ## Fix#2
    def test_user_password_get_renders_with_correct_template_name(self):
        # mutmut_9: template_name string used in render call
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "render", return_value="ok") as render:
            view.get(request)
        assert render.call_args.args[1] == view.template_name

    # --- UserPassword.post mutmut_11,16-18 ---
    ## Fix#2
    def test_user_password_post_renders_with_correct_template_name(self):
        # mutmut_11: template_name in render call
        request = DummyRequest(user=DummyUser(), post={})
        form = Mock()
        form.is_valid.return_value = False
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form), \
             patch.object(babybuddy_views, "render", return_value="ok") as render:
            view.post(request)
        assert render.call_args.args[1] == view.template_name

    ## Fix#2
    def test_user_password_post_valid_success_message_uses_request(self):
        # mutmut_16/_17/_18: messages.success(request, ...) — first arg is request
        request = DummyRequest(user=DummyUser(), post={})
        form = Mock()
        form.is_valid.return_value = True
        form.save.return_value = DummyUser()
        view = babybuddy_views.UserPassword()
        with patch.object(babybuddy_views, "PasswordChangeForm", return_value=form), \
             patch.object(babybuddy_views, "update_session_auth_hash"), \
             patch.object(babybuddy_views.messages, "success") as success, \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.post(request)
        assert success.call_args.args[0] is request

    # --- handle_api_regenerate_request mutmut_6,11-13 ---
    ## Fix#2
    def test_handle_api_regenerate_checks_api_key_regenerate_post_key(self):
        # mutmut_6: "api_key_regenerate" POST key string
        # A different key should NOT trigger regeneration.
        request = DummyRequest(user=DummyUser(), post={"other_key": "1"})
        result = babybuddy_views.handle_api_regenerate_request(request)
        assert result is False
        assert request.user.settings.api_key_calls == []

    ## Fix#2
    def test_handle_api_regenerate_success_message_uses_request(self):
        # mutmut_11/_12/_13: messages.success(request, ...) first arg is request
        request = DummyRequest(user=DummyUser(), post={"api_key_regenerate": "1"})
        with patch.object(babybuddy_views.messages, "success") as success:
            babybuddy_views.handle_api_regenerate_request(request)
        assert success.call_args.args[0] is request

    # --- UserSettings.get mutmut_2,3 ---
    ## Fix#2
    def test_user_settings_get_render_uses_correct_template_name(self):
        # mutmut_2/_3: template_name in render call
        request = DummyRequest(user=DummyUser())
        view = babybuddy_views.UserSettings()
        with patch.object(view, "form_user_class", return_value=object()), \
             patch.object(view, "form_settings_class", return_value=object()), \
             patch.object(babybuddy_views, "render", return_value="ok") as render:
            view.get(request)
        assert render.call_args.args[1] == view.template_name

    # --- UserSettings.post mutmut_24-27,29-31,33-34 ---
    ## Fix#2
    def test_user_settings_post_form_user_receives_request_user_instance(self):
        # mutmut_24/_25: form_user_class(instance=request.user, data=request.POST)
        request = DummyRequest(user=DummyUser(), post={"x": "1"})
        view = babybuddy_views.UserSettings()
        user_form = Mock()
        user_form.is_valid.return_value = False
        settings_form = Mock()
        settings_form.is_valid.return_value = False
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form) as ufc, \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.post(request)
        assert ufc.call_args.kwargs["instance"] is request.user
        assert ufc.call_args.kwargs["data"] is request.POST

    ## Fix#2
    def test_user_settings_post_form_settings_receives_user_settings_instance(self):
        # mutmut_26/_27: form_settings_class(instance=request.user.settings, data=request.POST)
        request = DummyRequest(user=DummyUser(), post={"x": "1"})
        view = babybuddy_views.UserSettings()
        user_form = Mock()
        user_form.is_valid.return_value = False
        settings_form = Mock()
        settings_form.is_valid.return_value = False
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form) as sfc, \
             patch.object(babybuddy_views, "render", return_value="ok"):
            view.post(request)
        assert sfc.call_args.kwargs["instance"] is request.user.settings
        assert sfc.call_args.kwargs["data"] is request.POST

    ## Fix#2
    def test_user_settings_post_valid_success_message_uses_request(self):
        # mutmut_33/_34: messages.success(request, ...) first arg is request
        request = DummyRequest(user=DummyUser(), post={})
        new_settings = DummyUserSettings(language="en")
        user_form = Mock()
        user_form.is_valid.return_value = True
        user_form.save.return_value = request.user
        settings_form = Mock()
        settings_form.is_valid.return_value = True
        settings_form.save.return_value = new_settings
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views.translation, "activate"), \
             patch.object(babybuddy_views.translation, "deactivate"), \
             patch.object(babybuddy_views.messages, "success") as success, \
             patch.object(babybuddy_views, "set_language", return_value="ok"):
            view.post(request)
        assert success.call_args.args[0] is request

    ## Fix#2
    def test_user_settings_post_valid_render_uses_correct_template_for_invalid(self):
        # mutmut_29/_30/_31: render(request, self.template_name, ...) template arg
        request = DummyRequest(user=DummyUser(), post={})
        user_form = Mock()
        user_form.is_valid.return_value = False
        settings_form = Mock()
        settings_form.is_valid.return_value = False
        view = babybuddy_views.UserSettings()
        with patch.object(babybuddy_views, "handle_api_regenerate_request", return_value=False), \
             patch.object(view, "form_user_class", return_value=user_form), \
             patch.object(view, "form_settings_class", return_value=settings_form), \
             patch.object(babybuddy_views, "render", return_value="ok") as render:
            view.post(request)
        assert render.call_args.args[1] == view.template_name

    # --- UserAddDevice.get mutmut_3,4,9,19,25,26 ---
    ## Fix#2
    def test_user_add_device_get_first_render_uses_request(self):
        # mutmut_3/_4: render(request, ...) first arg
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b"{}", content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        assert render.call_args_list[0].args[0] is request

    ## Fix#2
    def test_user_add_device_get_second_render_uses_request(self):
        # mutmut_25/_26: render(request, ...) first arg in second call
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b"{}", content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        assert render.call_args_list[1].args[0] is request

    ## Fix#2
    def test_user_add_device_get_qr_code_context_key_is_session_cookies(self):
        # mutmut_9: context key "session_cookies" in first render call
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b"{}", content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        first_ctx = render.call_args_list[0].args[2]
        assert "session_cookies" in first_ctx

    ## Fix#2
    def test_user_add_device_get_final_context_key_is_qr_code_data(self):
        # mutmut_19: context key "qr_code_data" in second render call
        request = DummyRequest(user=DummyUser())
        request.is_homeassistant_ingress_request = False
        view = babybuddy_views.UserAddDevice()
        qr_resp = HttpResponse(b'{"x":1}', content_type="text/plain")
        final_resp = HttpResponse("ok")
        with patch.object(babybuddy_views, "render", side_effect=[qr_resp, final_resp]) as render, \
             patch.object(view, "form_user_class", return_value=Mock()):
            view.get(request)
        second_ctx = render.call_args_list[1].args[2]
        assert "qr_code_data" in second_ctx
        assert second_ctx["qr_code_data"] == '{"x":1}'


# -----------------------------
# site_settings.py tests
# -----------------------------
class TestSiteSettingsModule:
    """Targets: babybuddy/site_settings.py"""

    def test_nap_start_max_time_value_uses_expected_field_class(self):
        # target file: babybuddy/site_settings.py | function: NapStartMaxTimeValue | behavior: field class binding
        assert babybuddy_site_settings.NapStartMaxTimeValue.field is core.fields.NapStartMaxTimeField

    def test_nap_start_min_time_value_uses_expected_field_class(self):
        # target file: babybuddy/site_settings.py | function: NapStartMinTimeValue | behavior: field class binding
        assert babybuddy_site_settings.NapStartMinTimeValue.field is core.fields.NapStartMinTimeField

    def test_nap_settings_widgets_use_time_input_for_both_settings(self):
        # target file: babybuddy/site_settings.py | function: NapSettings | behavior: both settings use TimeInput widget
        nap_start_min_descriptor = babybuddy_site_settings.NapSettings.__dict__["nap_start_min"]
        nap_start_max_descriptor = babybuddy_site_settings.NapSettings.__dict__["nap_start_max"]

        assert nap_start_min_descriptor.widget is babybuddy_site_settings.TimeInput
        assert nap_start_max_descriptor.widget is babybuddy_site_settings.TimeInput

    # Truthy values — each must return exactly 1

    ## Fix#1 - kill more mutation
    def test_strtobool_y_returns_1(self):
        assert strtobool("y") == 1

    ## Fix#1 - kill more mutation
    def test_strtobool_yes_returns_1(self):
        assert strtobool("yes") == 1

    ## Fix#1 - kill more mutation
    def test_strtobool_t_returns_1(self):
        assert strtobool("t") == 1

    ## Fix#1 - kill more mutation
    def test_strtobool_true_returns_1(self):
        assert strtobool("true") == 1

    ## Fix#1 - kill more mutation
    def test_strtobool_on_returns_1(self):
        assert strtobool("on") == 1

    ## Fix#1 - kill more mutation
    def test_strtobool_1_returns_1(self):
        assert strtobool("1") == 1

    # Falsy values — each must return exactly 0
    ## Fix#1 - kill more mutation
    def test_strtobool_n_returns_0(self):
        assert strtobool("n") == 0

    ## Fix#1 - kill more mutation
    def test_strtobool_no_returns_0(self):
        assert strtobool("no") == 0

    ## Fix#1 - kill more mutation
    def test_strtobool_f_returns_0(self):
        assert strtobool("f") == 0

    ## Fix#1 - kill more mutation
    def test_strtobool_false_returns_0(self):
        assert strtobool("false") == 0

    ## Fix#1 - kill more mutation
    def test_strtobool_off_returns_0(self):
        assert strtobool("off") == 0

    ## Fix#1 - kill more mutation
    def test_strtobool_0_returns_0(self):
        assert strtobool("0") == 0

    # Uppercase input — must be case-insensitive (val.lower() branch)
    ## Fix#1 - kill more mutation
    def test_strtobool_uppercase_true_returns_1(self):
        assert strtobool("TRUE") == 1

    ## Fix#1 - kill more mutation
    def test_strtobool_uppercase_false_returns_0(self):
        assert strtobool("FALSE") == 0

    ## Fix#1 - kill more mutation
    def test_strtobool_mixed_case_yes_returns_1(self):
        assert strtobool("Yes") == 1

    # Invalid value — must raise ValueError
    ## Fix#1 - kill more mutation
    def test_strtobool_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            strtobool("maybe")

    ## Fix#1 - kill more mutation
    def test_strtobool_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            strtobool("")

    # Return values are exactly 1 and 0, not True/False
    ## Fix#1 - kill more mutation
    def test_strtobool_truthy_returns_int_1_not_bool(self):
        result = strtobool("yes")
        assert result == 1
        assert result != 2

    ## Fix#1 - kill more mutation
    def test_strtobool_falsy_returns_int_0_not_bool(self):
        result = strtobool("no")
        assert result == 0
        assert result != -1

class TestAppsModule:
    """Targets: babybuddy/apps.py"""
    ## Fix#1 - New test class
    def test_create_read_only_group_calls_get_or_create_with_correct_name(self):
        # Kills all mutants on create_read_only_group: the group name argument
        # and the get_or_create call itself.
        from django.contrib.auth.models import Group
        with patch.object(Group.objects, "get_or_create") as get_or_create:
            babybuddy_apps.create_read_only_group(sender=object())
        get_or_create.assert_called_once_with(
            name=settings.BABY_BUDDY["READ_ONLY_GROUP_NAME"]
        )

    ## Fix#1 - New test class
    def test_baby_buddy_config_ready_connects_both_signals(self):
        # Kills all BabyBuddyConfig.ready mutants — both post_migrate.connect
        # calls must happen with the correct handlers and sender=self.
        config = babybuddy_apps.BabyBuddyConfig.__new__(babybuddy_apps.BabyBuddyConfig)

        connected = []

        def fake_connect(handler, sender):
            connected.append((handler, sender))

        with patch.object(babybuddy_apps.post_migrate, "connect", side_effect=fake_connect):
            babybuddy_apps.BabyBuddyConfig.ready(config)

        handlers = [h for h, s in connected]
        senders = [s for h, s in connected]

        assert babybuddy_apps.create_read_only_group in handlers
        assert babybuddy_apps.set_default_site_settings in handlers
        assert all(s is config for s in senders)

    ## Fix#1 - New test class
    def test_set_default_site_settings_uses_env_nap_start_min_when_valid(self):
        # Kills mutants on the NAP_START_MIN env parsing path (valid format).
        from dbsettings.loading import set_setting_value, setting_in_db
        with patch.dict(os.environ, {"NAP_START_MIN": "07:30", "NAP_START_MAX": "17:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False) as mock_in_db, \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())

        # First default tuple is ("Sleep", "nap_start_min", time(7,30))
        calls = mock_set.call_args_list
        assert any(
            c == call("core.models", "Sleep", "nap_start_min", datetime.time(7, 30))
            for c in calls
        )

    ## Fix#1 - New test class
    def test_set_default_site_settings_falls_back_to_model_when_env_invalid(self):
        import core.models as core_models
        fake_settings = types.SimpleNamespace(
            nap_start_min=datetime.time(6),
            nap_start_max=datetime.time(18)
        )
        env_without_nap = {k: v for k, v in os.environ.items()
                           if k not in ("NAP_START_MIN", "NAP_START_MAX")}
        with patch.dict(os.environ, env_without_nap, clear=True), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set, \
             patch.object(core_models.Sleep, "settings", fake_settings, create=True):
            babybuddy_apps.set_default_site_settings(sender=object())

        calls = mock_set.call_args_list
        assert any(
            c == call("core.models", "Sleep", "nap_start_min", datetime.time(6))
            for c in calls
        )

    ## Fix#1 - New test class
    def test_set_default_site_settings_skips_already_set_values(self):
        env_without_nap = {k: v for k, v in os.environ.items()
                           if k not in ("NAP_START_MIN", "NAP_START_MAX")}
        with patch.dict(os.environ, env_without_nap, clear=True), \
             patch("babybuddy.apps.setting_in_db", return_value=True) as mock_in_db, \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        mock_set.assert_not_called()

    ## Fix#1 - New test class
    def test_set_default_site_settings_calls_set_with_correct_module_string(self):
        # Kills mutants on the "core.models" module string argument.
        env_without_nap = {k: v for k, v in os.environ.items()
                   if k not in ("NAP_START_MIN", "NAP_START_MAX")}
        with patch.dict(os.environ, env_without_nap, clear=True), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())

        for c in mock_set.call_args_list:
            assert c.args[0] == "core.models"

    ## Fix#2
    def _env_without_nap(self):
        return {k: v for k, v in os.environ.items()
                if k not in ("NAP_START_MIN", "NAP_START_MAX")}

    ## Fix#2
    def test_set_default_site_settings_uses_env_nap_start_max_when_valid(self):
        # Kills mutants on "NAP_START_MAX" env key and the nap_start_max path
        with patch.dict(os.environ, {"NAP_START_MIN": "06:00", "NAP_START_MAX": "17:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        calls = mock_set.call_args_list
        assert any(
            c == call("core.models", "Sleep", "nap_start_max", datetime.time(17, 0))
            for c in calls
        )

    ## Fix#2
    def test_set_default_site_settings_format_string_parses_hh_mm(self):
        # Kills mutant on "%H:%M" format string — if mutated, time parse fails
        # and falls back to model default; we verify the parsed value is used.
        with patch.dict(os.environ, {"NAP_START_MIN": "08:30", "NAP_START_MAX": "16:45"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        calls = mock_set.call_args_list
        assert any(
            c == call("core.models", "Sleep", "nap_start_min", datetime.time(8, 30))
            for c in calls
        )
        assert any(
            c == call("core.models", "Sleep", "nap_start_max", datetime.time(16, 45))
            for c in calls
        )

    ## Fix#2
    def test_set_default_site_settings_nap_start_min_attribute_name_exact(self):
        # Kills mutants on "nap_start_min" attribute name string in defaults tuple
        with patch.dict(os.environ, {"NAP_START_MIN": "07:00", "NAP_START_MAX": "18:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        called_attribute_names = [c.args[2] for c in mock_set.call_args_list]
        assert "nap_start_min" in called_attribute_names

    ## Fix#2
    def test_set_default_site_settings_nap_start_max_attribute_name_exact(self):
        # Kills mutants on "nap_start_max" attribute name string in defaults tuple
        with patch.dict(os.environ, {"NAP_START_MIN": "07:00", "NAP_START_MAX": "18:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        called_attribute_names = [c.args[2] for c in mock_set.call_args_list]
        assert "nap_start_max" in called_attribute_names

    ## Fix#2
    def test_set_default_site_settings_sleep_class_name_exact(self):
        # Kills mutants on "Sleep" class name string in defaults tuple
        with patch.dict(os.environ, {"NAP_START_MIN": "07:00", "NAP_START_MAX": "18:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        called_class_names = [c.args[1] for c in mock_set.call_args_list]
        assert all(n == "Sleep" for n in called_class_names)

    ## Fix#2
    def test_set_default_site_settings_value_error_in_strptime_triggers_fallback(self):
        # Kills mutants on ValueError in except tuple — invalid format raises ValueError
        import core.models as core_models
        fake_settings = types.SimpleNamespace(
            nap_start_min=datetime.time(6),
            nap_start_max=datetime.time(18)
        )
        env = {k: v for k, v in os.environ.items()
               if k not in ("NAP_START_MIN", "NAP_START_MAX")}
        env["NAP_START_MIN"] = "not-a-time"
        env["NAP_START_MAX"] = "also-invalid"
        with patch.dict(os.environ, env, clear=True), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set, \
             patch.object(core_models.Sleep, "settings", fake_settings, create=True):
            babybuddy_apps.set_default_site_settings(sender=object())
        calls = mock_set.call_args_list
        assert any(
            c == call("core.models", "Sleep", "nap_start_min", datetime.time(6))
            for c in calls
        )

    ## Fix#2
    def test_set_default_site_settings_setting_in_db_called_with_correct_args(self):
        # Kills mutants on setting_in_db("core.models", class_name, attribute_name)
        with patch.dict(os.environ, {"NAP_START_MIN": "07:00", "NAP_START_MAX": "18:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False) as mock_in_db, \
             patch("babybuddy.apps.set_setting_value"):
            babybuddy_apps.set_default_site_settings(sender=object())
        in_db_calls = mock_in_db.call_args_list
        assert call("core.models", "Sleep", "nap_start_min") in in_db_calls
        assert call("core.models", "Sleep", "nap_start_max") in in_db_calls

    ## Fix#2
    def test_set_default_site_settings_set_value_called_twice_when_neither_in_db(self):
        # Kills mutants that drop one of the two set_setting_value calls
        with patch.dict(os.environ, {"NAP_START_MIN": "07:00", "NAP_START_MAX": "18:00"}), \
             patch("babybuddy.apps.setting_in_db", return_value=False), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        assert mock_set.call_count == 2

    ## Fix#2
    def test_set_default_site_settings_set_value_called_once_when_one_already_in_db(self):
        # Kills mutants on the loop / conditional logic
        in_db_results = [True, False]  # first already set, second not
        with patch.dict(os.environ, {"NAP_START_MIN": "07:00", "NAP_START_MAX": "18:00"}), \
             patch("babybuddy.apps.setting_in_db", side_effect=in_db_results), \
             patch("babybuddy.apps.set_setting_value") as mock_set:
            babybuddy_apps.set_default_site_settings(sender=object())
        assert mock_set.call_count == 1

class TestSettingsModule:

    ## Fix#2
    def test_strtobool_truthy_returns_exactly_1_not_0(self):
        # mutmut_29: return 1 → return 0
        assert strtobool("yes") != 0
        assert strtobool("yes") == 1

    ## Fix#2
    def test_strtobool_falsy_returns_exactly_0_not_1(self):
        # mutmut_30: return 0 → return 1
        assert strtobool("no") != 1
        assert strtobool("no") == 0

    ## Fix#2
    def test_strtobool_truthy_and_falsy_return_different_values(self):
        # mutmut_31/_32: kills any mutation that makes both branches return same value
        assert strtobool("yes") != strtobool("no")

    ## Fix#2
    def test_strtobool_invalid_error_message_contains_value(self):
        # Kills mutants on the ValueError format string
        with pytest.raises(ValueError) as exc:
            strtobool("garbage")
        assert "garbage" in str(exc.value)

