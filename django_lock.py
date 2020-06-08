# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from functools import wraps
import time
import threading
import uuid
from warnings import warn

from django.conf import settings
from django.core.cache import cache, DefaultCacheProxy
from django.core.cache.backends.db import BaseDatabaseCache
from django.core.cache.backends.locmem import LocMemCache
from django.core.cache.backends.memcached import BaseMemcachedCache
from django.db.models import Model
from django.utils.module_loading import import_string
import six

redis_backends = ()
try:
    from django_redis.cache import RedisCache
    redis_backends = redis_backends + (RedisCache,)
except ImportError:
    RedisCache = ()
try:
    from redis_cache.backends.base import BaseRedisCache
    redis_backends = redis_backends + (BaseRedisCache,)
except ImportError:
    BaseRedisCache = ()


__all__ = ("DEFAULT_SETTINGS", "IncorrectLock", "lock", "lock_model", "Lock",
           "Locked", "LockError", "LocMemLock", "MemcachedLock", "RedisLock")


DEFAULT_SETTINGS = dict(
    PREFIX="lock:",
    SLEEP=0.1,
    RELEASEONDEL=True
)


def _backend_cls(client):
    backend_cls = type(client)
    if backend_cls is DefaultCacheProxy:
        cls = settings.CACHES["default"]["BACKEND"]
        backend_cls = import_string(cls)
    return backend_cls


def _get_setting(name):
    return getattr(settings, "DJANGOLOCK_" + name, DEFAULT_SETTINGS[name])


class LockWarning(RuntimeWarning):
    pass


class LockError(ValueError):
    pass


class Locked(LockError):
    pass


class IncorrectLock(LockError):
    pass


class Lock(object):
    """
    A lock class like `redis.lock.Lock`.
    """

    def __init__(self, name, client, timeout=None, blocking=True, sleep=None,
                 token_generator=None, release_on_del=None, thread_local=True,
                 extend_owned=False):
        self.client = client
        self.name = name

        self.blocking = blocking
        self.sleep = sleep or _get_setting("SLEEP")

        if timeout and self.sleep > timeout:
            warn("'sleep' should be less than 'timeout'", LockWarning)
        self.timeout = timeout or None

        local_cls = threading.local if thread_local else type(
            str("dummy"), (object,), dict())
        self.local = local_cls()

        self.token_generator = token_generator or uuid.uuid1
        if release_on_del is None:
            release_on_del = _get_setting("RELEASEONDEL")
        self.release_on_del = release_on_del
        self.extend_owned = extend_owned

    @property
    def key(self):
        """
        The lock's key stores in the cache
        """
        prefix = _get_setting("PREFIX")
        if not isinstance(self.name, six.string_types):
            raise IncorrectLock("lock's name must be str, got %s" % self.name)
        return prefix + self.name

    def acquire_raise(self, blocking=None, token=None):
        """
        Raise an `django_lock.Locked` error when acquire failed
        :raises: django_lock.Locked
        """
        if not self.acquire(blocking, token):
            raise Locked

    def acquire(self, blocking=None, token=None):
        """
        :param blocking: If blocking is False, always return immediately. If
                         blocking is True, the lock will trying to acquire
                         forever. If blocking is a digit, it indicates the
                         maximum amount of time in seconds to spend trying to
                         acquire the lock
        :type blocking: bool or float
        :type token: str
        """
        if self.extend_owned and self.owned and self.extend():
            return True

        if token is None:
            token = str(self.token_generator())
        if blocking is None:
            blocking = self.blocking
        try_started = time.time()
        while True:
            if self._acquire(token):
                return True
            if not blocking:
                return False
            if blocking is not True and time.time() - try_started > blocking:
                return False
            time.sleep(self.sleep)

    def _acquire(self, token):
        if self.client.add(self.key, token, self.timeout):
            self.local.token = token
            return True
        return False

    def release(self, force=False, warns=True):
        """
        Releases the already acquired lock
        :param force: Force to release lock without checking owned
        """
        token = getattr(self.local, "token", None)
        if not token and not force:
            warns and warn("Cannot release an unlocked lock", LockWarning)
            return

        self._release(token, force, warns)

    def _release(self, token, force=False, warns=True):
        # TODO: use cas to release a memcached lock
        setattr(self.local, "token", None)
        if force:
            self.client.delete(self.key)
        else:
            owned = self._release_owned(token)
            warns and not owned and warn(
                "Cannot release a lock that's no longer owned", LockWarning)

    def _release_owned(self, token):
        locked_token = self.client.get(self.key)
        owned = locked_token and locked_token == token
        owned and self.client.delete(self.key)
        return owned

    def extend_raise(self, additional_time=False):
        """
        Raise an `django_lock.IncorrectLock` error when extend failed
        :raises: django_lock.IncorrectLock
        """
        msg = self._extend_msg(additional_time)
        if msg:
            raise IncorrectLock(msg)

    def extend(self, additional_time=False):
        """
        Adds more time to an already acquired lock.
        """
        return not self._extend_msg(additional_time)

    def _extend_msg(self, additional_time=False):
        if additional_time is False:
            additional_time = self.timeout

        token = getattr(self.local, "token", None)
        if not token:
            return "Cannot extend an unlocked lock"

        if not self._extend(token, additional_time):
            return "Cannot extend a lock that's no longer owned"

    def _extend(self, token, additional_time):
        locked_token = self.client.get(self.key)
        owned = locked_token and locked_token == token
        if owned:
            self.client.set(self.key, locked_token, additional_time)
        else:
            self.local.token = None
        return owned

    @property
    def locked(self):
        """
        Returns True if this key is locked by any process, otherwise False.
        """
        return bool(self.client.get(self.key))

    @property
    def owned(self):
        """
        Returns True if this key is locked by this lock, otherwise False.
        """
        token = getattr(self.local, "token", None)
        return bool(token and token == self.client.get(self.key))

    def __enter__(self):
        self.acquire_raise()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def __del__(self):
        try:
            self.release_on_del and self.name and self.release(warns=False)
        except:
            pass

    @classmethod
    def _from_lock(cls, lock, **kwargs):
        """
        Create a lock from another
        :type lock: django_lock.lock
        """
        defaults = dict(name=lock.name, client=lock.client,
                        timeout=lock.timeout, blocking=lock.blocking,
                        sleep=lock.sleep,
                        token_generator=lock.token_generator,
                        release_on_del=lock.release_on_del,
                        thread_local=isinstance(lock.local, threading.local),
                        extend_owned=lock.extend_owned)
        defaults.update(kwargs)
        return cls(**defaults)


class LocMemLock(Lock):
    def __init__(self, *args, **kwargs):
        msg = ("DO NOT use locmem cache as lock's backend in a product "
               "environment")
        if not settings.DEBUG:
            raise RuntimeError(msg)
        else:
            warn(msg, LockWarning)

        super(LocMemLock, self).__init__(*args, **kwargs)


class RedisLock(Lock):
    LUA_RELEASE_SCRIPT = """
        local token = redis.call('get', KEYS[1])
        if not token or token ~= ARGV[1] then
            return 0
        end
        redis.call('del', KEYS[1])
        return 1
    """

    LUA_EXTEND_SCRIPT = """
        local token = redis.call('get', KEYS[1])
        if not token or token ~= ARGV[1] then
            return 0
        end

        local newttl = ARGV[2]
        if newttl then
            redis.call('pexpire', KEYS[1], newttl)
        else
            redis.call('persist', KEYS[1])
        end
        return 1
    """

    @property
    def _key(self):
        return self.client.make_key(self.key)

    @property
    def _redis(self):
        backend_cls = _backend_cls(self.client)
        if issubclass(backend_cls, RedisCache):
            return self.client.client.get_client()
        elif issubclass(backend_cls, BaseRedisCache):
            return self.client.get_master_client()
        else:
            raise NotImplementedError("Unknown redis backend")

    def _serialize(self, data):
        backend_cls = _backend_cls(self.client)
        if issubclass(backend_cls, RedisCache):
            return self.client.client.encode(data)
        elif issubclass(backend_cls, BaseRedisCache):
            return self.client.serialize(data)
        else:
            raise NotImplementedError("Unknown redis backend")

    def _eval(self, script, keys=None, args=None):
        keys = keys or tuple()
        args = args or tuple()
        numkeys = len(keys)
        return self._redis.eval(script, numkeys, *(keys + args))

    def _release_owned(self, token):
        token = self._serialize(token)
        return self._eval(self.LUA_RELEASE_SCRIPT,
                          keys=(self._key,), args=(token,))

    def _extend(self, token, additional_time):
        token = self._serialize(token)
        expires_in = int(1000*(additional_time or 0))
        return self._eval(self.LUA_EXTEND_SCRIPT,
                          keys=(self._key,), args=(token, expires_in))


class MemcachedLock(Lock):
    def __init__(self, name, client, timeout=None, *args, **kwargs):
        # memcached only support int timeout
        if timeout and not isinstance(timeout, int):
            warn("memcached only support int timeout, your time out will "
                 "be parsed to int, timeout less than one second will be "
                 "treated as lock forever", LockWarning)
            timeout = int(timeout)

        super(MemcachedLock, self).__init__(
            name, client, timeout, *args, **kwargs)


def get_lock_cls(client, *bases):
    backend_cls = _backend_cls(client)
    if issubclass(backend_cls, redis_backends):
        cls = RedisLock
    elif issubclass(backend_cls, LocMemCache):
        cls = LocMemLock
    elif issubclass(backend_cls, BaseMemcachedCache):
        cls = MemcachedLock
    elif issubclass(backend_cls, BaseDatabaseCache):
        raise NotImplementedError("We don't support database cache yet")
    else:
        cls = Lock
    return type(cls.__name__, bases + (cls,), {}) if bases else cls


class LockContext(object):
    name_generator = None

    def __init__(self, name, *args, **kwargs):
        if callable(name):
            self.name_generator = name
            name = None
        super(LockContext, self).__init__(name, *args, **kwargs)

    def __call__(self, func):
        @wraps(func)
        def inner(*args, **kwargs):
            if not self.name and self.name_generator:
                context = self._from_args(*args, **kwargs)
            else:
                context = self
            with context:
                return func(*args, **kwargs)
        return inner

    def _from_args(self, *args, **kwargs):
        name = self.name_generator(*args, **kwargs)
        return self._from_lock(self, name=name)


def lock(name, client=None, timeout=None, blocking=True, sleep=None,
         token_generator=None, release_on_del=None, thread_local=True,
         extend_owned=False, bases=None):
    """
    :param timeout: indicates a maximum life for the lock. By default,
                    it will remain locked until release() is called.
    :type timeout: float
    :param sleep: indicates the amount of time to sleep per loop iteration
                    when the lock is in blocking mode and another client is
                    currently holding the lock.
    :type sleep: float
    :type client: django.core.cache.BaseCache
    :type blocking: bool or float
    :param extend_owned: if extend_owned is True, it won't raise an `Locked`
                         exception if you already owned this lock, and it will
                         extend this lock automatically

        from django_lock import lock

        with lock("global"):
            pass

        @lock("global")
        def foo():
            pass
    """
    client = client or cache
    bases = bases or tuple()
    cls = get_lock_cls(client, *(bases + (LockContext,)))
    return cls(name, client, timeout, blocking=blocking, sleep=sleep,
               token_generator=token_generator, release_on_del=release_on_del,
               thread_local=thread_local, extend_owned=extend_owned)


def lock_model(model_or_func_or_arg=None, *keys, **kw):
    """
    A shortcut to lock a model instance

    :param refresh_from_db: reload model from database if locked success

    you can use this function as a decorator for a model's method

        from django.db import models
        from django_lock import lock_model

        class Foo(models.Model):
            first_name = models.CharField(max_length=32)
            last_name = models.CharField(max_length=32)

            @lock_model
            def bar(self, *args, **kwargs):
                pass

            @lock_model("first_name", "last_name", blocking=False)
            def bar(self, *args, **kwargs):
                pass

    or

        with lock_model(instance):
            pass
    """

    class ModelLockMixin(object):
        model = None

        def __init__(self, name, *args, **kwargs):
            if isinstance(name, Model):
                self.model = name
                name = self.name_generator(name)
            super(ModelLockMixin, self).__init__(name, *args, **kwargs)

        def name_generator(self, model, *args, **kwargs):
            values = [getattr(model, key) for key in keys]
            kvs = zip(keys, values)
            # TODO: max length of cache key
            prefix = self.lock_name or "{app_label}:{table}:".format(
                app_label=model._meta.app_label,
                table=model._meta.db_table
            )
            return prefix + ":".join(map(lambda o: ":".join(map(str, o)), kvs))

        def __enter__(self):
            super(ModelLockMixin, self).__enter__()
            self.refresh_from_db and self.model.refresh_from_db()
            return self

        def _from_args(self, model, *args, **kwargs):
            rv = super(ModelLockMixin, self)._from_args(model, *args, **kwargs)
            rv.model = model
            return rv

    ModelLockMixin.refresh_from_db = kw.pop("refresh_from_db", True)
    ModelLockMixin.lock_name = kw.pop("name", None)

    decorator = lock(None, bases=(ModelLockMixin,), **kw)

    arg = model_or_func_or_arg
    if arg and isinstance(arg, Model):
        keys = keys or ("pk",)
        return lock(arg, bases=(ModelLockMixin,), **kw)
    elif arg and callable(arg):
        keys = ("pk",)
        return decorator(arg)
    else:
        keys = ((arg,) + keys) if arg else ("pk",)

        return decorator
