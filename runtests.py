# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

import django
from django.conf import settings
from django.core.management import call_command
from django.test.utils import get_runner


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings.locmem")
    django.setup()

    if settings.CACHES["default"]["BACKEND"] == "django.core.cache.backends.db.DatabaseCache":
        call_command("createcachetable")

    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(["tests"])
    sys.exit(bool(failures))


if __name__ == "__main__":
    main()
