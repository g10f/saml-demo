#!/bin/bash

tag=$(python apps/version.py)
app=saml-demo
export DOCKER_BUILDKIT=1
docker buildx build --platform linux/amd64 -t ghcr.io/g10f/$app:$tag -t ghcr.io/g10f/$app:latest --load .
