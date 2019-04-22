# django-cache-lock

[![PyPI](https://img.shields.io/pypi/v/django-cache-lock.svg)](https://pypi.org/project/django-cache-lock)
[![Build Status](https://travis-ci.org/Xavier-Lam/django-cache-lock.svg?branch=master)](https://travis-ci.org/Xavier-Lam/django-cache-lock)

A simple lock extension for django's cache.

## Installation
Install django-cache-lock by using pip

    pip install django-cache-lock

then patch the django's default cache in wherever you like.

    class AppConfig(AppConfig):
        def ready(self):
            import django_lock
            django_lock.patch_lock()

> ATTENTION: this will replace all your caches' lock method defined in your `settings.CACHE`, include builtin locks like django-redis's lock.

## Quick Start
You can work with django-cache-lock by using with-statement or decorator.

        from django.core.cache import cache

        with cache.lock("global"):
            pass

        @cache.lock
        def foo():
            pass

This is the simplest way to use django-cache-lock, for more usages, please read the [code](django_lock.py).