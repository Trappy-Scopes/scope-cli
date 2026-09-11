#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Trappy-Scopes CLI entry point.

The experiment environment is built by the recipe named in the scope
configuration (`config.startup_recipie`) and returned as a namespace, which is
merged into this module's globals. Since `python -i main.py` runs this file as
`__main__`, those names -- `scope`, `exp`, and the user tools -- become the
top-level names of the interactive session.

See expenv/__init__.py for the available environments.
"""

from expenv import build

globals().update(build())
