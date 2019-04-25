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

    @lock("global")
    def foo():
        pass

A shortcut to lock model instance

    from django.db import models
    from django_lock import model_lock

    class Foo(models.Model):
        bar = models.CharField(max_length=8)

        @lock_model
        def lock_pk(self):
            pass

        @lock_model("bar", blocking=False)
        def lock_bar(self):
            pass

## Configurations
| key | default | desc |
| --- | --- | --- |
| DJANGOLOCK_PREFIX | "lock:" | lock's key prefix stored in cache |
| DJANGOLOCK_SLEEP | 0.1 | default interval time to acquire a lock if a lock is holded by others |
| DJANGOLOCK_RELEASEONDEL | True | release lock when `__del__` is called if True |

## Advanced usage
For more usages, please read the [code](django_lock.py).

## ATTENTIONS
### memcached backend
* Memcached does not support milliseconds expire time, and its' expire time is not very exact. So memcached lock's timeout time is not as exact as other backends.

## TODOS:
* use lua script and memcached's cas to release lock
* reacquire and extend lock
* database backend cache support