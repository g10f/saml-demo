#!/bin/bash
VERSION=1.6.2
APP=the_site

sed -i "s/__version__ =.*/__version__ = '${VERSION}'/" apps/${APP}/__init__.py
sed -i "s/^  tag:.*/  tag: ${VERSION}/" ../dwbn-demos/helmfile/saml2/values.yaml
