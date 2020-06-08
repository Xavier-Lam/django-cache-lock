# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEBUG = True

SECRET_KEY = "fake-key"

UNIT_TIME = 0.2


INSTALLED_APPS = [
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {
            "NAME": ":memory:"
        }
    }
}
