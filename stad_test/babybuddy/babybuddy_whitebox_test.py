####################################################################################################################################
# babybuddy whitebox test                                                                                                          #
#                                                                                                                                  #
# Author: Shaun Ku, Samson Cournane                                                                                                #
#                                                                                                                                  #
#                                                                                                                                  #
# Test result                                                                                                                      #
# -------------------------------------------------------------------------------------------------------------------------------- #
# Date       | Name                     | BC   | Pass/Fail | Mutation                                                              #
# -------------------------------------------------------------------------------------------------------------------------------- #
# 2026-04-16 | Init test                | 95%  | 96/0      | 136/136   1029/1029  🎉 355 🫥 545  ⏰ 0  🤔 0  🙁 129  🔇 0  🧙 0  #
# -------------------------------------------------------------------------------------------------------------------------------- #
####################################################################################################################################

import copy
import os
import sys
import types
from unittest.mock import MagicMock, Mock, patch

import pytest


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

from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.http import HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.test.client import RequestFactory

import babybuddy.forms as babybuddy_forms
import babybuddy.middleware as babybuddy_middleware
import babybuddy.mixins as babybuddy_mixins
import babybuddy.models as babybuddy_models
import babybuddy.site_settings as babybuddy_site_settings
import babybuddy.templatetags.babybuddy as babybuddy_tags
import babybuddy.views as babybuddy_views
import babybuddy.widgets as babybuddy_widgets


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

