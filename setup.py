# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import re

from setuptools import setup

package = dict()

with open("README.md", "rb") as f:
    long_description = f.read().decode("utf-8")

with open("requirements.txt") as f:
    requirements = [l for l in f.read().splitlines() if l]

setup(
    name="django-cache-lock",
    version="0.2.2",
    author="Xavier-Lam",
    author_email="Lam.Xavier@hotmail.com",
    url="https://github.com/Xavier-Lam/django-cache-lock",
    py_modules=["django_lock"],
    keywords=["django", "cache", "lock"],
    description="A simple lock extension for django's cache.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=requirements,
    include_package_data=True,
    test_suite="runtests.main",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Web Environment",
        "Framework :: Django :: 1.11",
        "Framework :: Django :: 2.0",
        "Framework :: Django :: 2.1",
        "Framework :: Django :: 2.2",
        "Framework :: Django :: 3.0",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: MacOS",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities"
    ]
)
