FROM python:3.13.3-slim

ENV RUN_DEPS="libxmlsec1-openssl libxml2"
ENV BUILD_DEPS="build-essential pkg-config libxml2-dev libxmlsec1-dev libxslt-dev python3-dev"
RUN set -ex \
    && apt-get update && apt-get install -y --no-install-recommends $RUN_DEPS \
    && rm -rf /var/lib/apt/lists/*

ENV WORKDIR=/opt/g10f/saml-demo
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=$WORKDIR/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR $WORKDIR
RUN chown -R $USERNAME: $WORKDIR

COPY requirements.txt .

RUN set -ex \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS \
    && python3 -m venv ${VIRTUAL_ENV} \
    && pip install -U pip wheel \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --force-reinstall --no-binary lxml lxml \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*

ARG USERNAME=worker
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

WORKDIR $WORKDIR/apps
COPY apps .

RUN chown -R $USERNAME: /opt/g10f

USER $USERNAME
RUN ./manage.py collectstatic

# Start gunicorn
CMD ["gunicorn", "the_site.wsgi:application", "-b", "0.0.0.0:8000", "--forwarded-allow-ips", "*"]
EXPOSE 8000
