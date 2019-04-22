# django-cache-lock

[![PyPI](https://img.shields.io/pypi/v/django-cache-lock.svg)](https://pypi.org/project/django-cache-lock)
[![Build Status](https://travis-ci.org/Xavier-Lam/django-cache-lock.svg?branch=master)](https://travis-ci.org/Xavier-Lam/django-cache-lock)

A simple lock extension for django's cache.

## Installation
Install django-cache-lock by using pip

    pip install django-cache-lock

## Quick Start
You can work with django-cache-lock by using with-statement or decorator.

        from django_lock import lock

        with lock("global"):
            pass

        @lock
        def foo():
            pass

This is the simplest way to use django-cache-lock, for more usages, please read the [code](django_lock.py).