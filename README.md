# django-cache-lock

[![PyPI](https://img.shields.io/pypi/v/django-cache-lock.svg)](https://pypi.org/project/django-cache-lock)
[![Build Status](https://travis-ci.org/Xavier-Lam/django-cache-lock.svg?branch=master)](https://travis-ci.org/Xavier-Lam/django-cache-lock)
[![Donate with Bitcoin](https://en.cryptobadges.io/badge/micro/1BdJG31zinrMFWxRt2utGBU2jdpv8xSgju)](https://en.cryptobadges.io/donate/1BdJG31zinrMFWxRt2utGBU2jdpv8xSgju)

A simple lock extension for django's cache to prevent concurrent editing.

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

        def nolock(self):
            pass

    foo = Foo()
    with lock_model(foo, blocking=False):
        nolock()

## Configurations
| key | default | desc |
| --- | --- | --- |
| DJANGOLOCK_PREFIX | "lock:" | lock's key prefix stored in cache |
| DJANGOLOCK_SLEEP | 0.1 | default interval time to acquire a lock if a lock is holded by others |
| DJANGOLOCK_RELEASEONDEL | True | release lock when `__del__` is called if True |

## Advanced usage
For more usages, please read the [code](django_lock.py).

## Supported backends
* django.core.cache.backends.db
* django.core.cache.backends.file
* django.core.cache.backends.locmem
* django.core.cache.backends.memcached
* [django-redis](https://github.com/niwinz/django-redis)
* [django-redis-cache](https://github.com/sebleier/django-redis-cache)

## ATTENTIONS
### locmem backend
* DO NOT USE locmem backend in a product environment.

### memcached backend
* Memcached does not support milliseconds expire time, and its' expire time is not very exact. So memcached lock's timeout time is not as exact as other backends.

### redis backend
* We didn't test distributed redis lock.

## TODOS:
* use memcached's cas to release lock
* reacquire and extend lock
* database backend cache support