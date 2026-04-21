from .base import *

SECRET_KEY = "TESTS"

# Static files
# https://docs.djangoproject.com/en/5.0/howto/static-files/
#
# Override the manifest-strict WhiteNoise backend inherited from base so that
# test runs don't need a pre-built `static/` tree.  Plain StaticFilesStorage
# resolves `{% static %}` tags by string concatenation instead of looking the
# file up in `staticfiles.json`, which means tests that render templates like
# babybuddy/base.html (which references /static/babybuddy/root/apple-touch-icon.png
# etc.) no longer crash when `collectstatic`/`gulp build` hasn't been run.

STORAGES["staticfiles"][
    "BACKEND"
] = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Password hasher configuration
# See https://docs.djangoproject.com/en/5.0/ref/settings/#password-hashers
# See https://docs.djangoproject.com/en/5.0/topics/testing/overview/#password-hashing

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Email
# https://docs.djangoproject.com/en/5.0/topics/email/

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Axes configuration
# See https://django-axes.readthedocs.io/en/latest/4_configuration.html

AXES_ENABLED = False

# DBSettings configuration
# See https://github.com/zlorf/django-dbsettings#a-note-about-caching

DBSETTINGS_USE_CACHE = False

# We want to test the home assistant middleware

ENABLE_HOME_ASSISTANT_SUPPORT = True
