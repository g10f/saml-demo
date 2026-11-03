# Build stage: compiles the Python packages into /venv. lxml and xmlsec are built from source against the
# libxml2 of the system, because xmlsec refuses to work with an lxml that uses another libxml2 version (the
# wheels of both bundle their own).
FROM python:3.14.9-slim AS build

RUN set -ex \
    && apt-get update && apt-get install -y --no-install-recommends \
       build-essential pkg-config libxml2-dev libxmlsec1-dev libxslt1-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt /requirements.txt
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir --no-binary lxml,xmlsec -r /requirements.txt


FROM python:3.14.9-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Runtime libraries of lxml and xmlsec
RUN set -ex \
    && apt-get update && apt-get install -y --no-install-recommends libxml2 libxslt1.1 libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /venv /venv

ARG USERNAME=worker
ARG PROJ_NAME=saml-demo
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user. The uid must stay 1000: the SAML settings mounted from the host are readable only by it.
RUN groupadd --gid $USER_GID $USERNAME && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

# The venv and the code belong to root. The user only writes the static files with collectstatic.
# The SAML settings are mounted at /opt/g10f/saml-demo/saml.
RUN mkdir -p /opt/g10f/$PROJ_NAME/htdocs/static \
    && chown $USERNAME:$USERNAME /opt/g10f/$PROJ_NAME/htdocs/static

WORKDIR /opt/g10f/$PROJ_NAME/apps
COPY apps .

USER $USERNAME
RUN ./manage.py collectstatic --noinput

# Start gunicorn
CMD ["gunicorn", "the_site.wsgi:application", "-b", "0.0.0.0:8000", "--forwarded-allow-ips", "*"]
EXPOSE 8000
