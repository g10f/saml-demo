#!/bin/bash
VERSION=1.3.5
APP=the_site

sed -i "s/__version__ =.*/__version__ = '${VERSION}'/" apps/${APP}/__init__.py
