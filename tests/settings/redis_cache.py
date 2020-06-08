from .locmem import *


UNIT_TIME = 1

CACHES = {
    "default": {
        "BACKEND": "redis_cache.RedisCache",
        "LOCATION": ["127.0.0.1:6379"],
    }
}
