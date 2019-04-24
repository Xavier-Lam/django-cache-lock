from .locmem import *


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "test",
        "USER": "root",
        "PASSWORD": "",
        "HOST": "localhost",   # Or an IP Address that your DB is hosted on
        "PORT": "3306",
    }
}


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "cache_table",
    }
}
