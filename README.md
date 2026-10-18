Simple SAML2 demo app
=====================
Modified Django demo web app from python3-saml library without database.

The app is a SAML 2.0 service provider. It logs in at an identity provider and shows the
attributes, the NameID and the session index of the logged in user. It supports single logout.

Endpoints
---------

| URL           | Description                                                     |
|---------------|-----------------------------------------------------------------|
| `/`           | start page with login and logout                                |
| `/?sso`       | starts the login at the identity provider                       |
| `/?acs`       | assertion consumer service, receives the SAML response          |
| `/?slo`       | starts the single logout                                        |
| `/?sls`       | single logout service, receives the logout request or response  |
| `/metadata/`  | metadata of the service provider for the identity provider      |

The login requests the authentication context `PasswordProtectedTransport` with the comparison
`minimum`.

SAML configuration
------------------
The SAML settings are read from the directory `saml/` next to `apps/`. It is not part of the
repository, because it contains the private key of the service provider.

- `settings.json`: service provider (`sp`) and identity provider (`idp`)
- `advanced_settings.json`: security settings, contact person and organization

See the [python3-saml documentation](https://github.com/SAML-Toolkits/python3-saml#settings) for
the format.

Configuration
-------------
Environment variables:

| Variable                          | Default                    | Description                                   |
|-----------------------------------|----------------------------|-----------------------------------------------|
| `ALLOWED_HOSTS`                   | `saml2.g10f.de`            | comma separated list, localhost is always allowed |
| `SECRET_KEY`                      | random on every start      | Django secret key                             |
| `SESSION_COOKIE_AGE`              | `1800`                     | session lifetime in seconds                   |
| `SESSION_EXPIRE_AT_BROWSER_CLOSE` | `True`                     |                                               |
| `ENABLE_PLAUSIBLE`                | `False`                    | adds the Plausible analytics script           |
| `DOMAIN`                          | `localhost`                | domain for Plausible                          |
| `EMAIL_HOST`, `EMAIL_PORT`        | `localhost`, `25`          | mail server for error mails                   |
| `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` | `webmaster@g10f.de`     | sender of mails                               |
| `DJANGO_LOG_LEVEL`                | `INFO`                     |                                               |
| `VERSION`                         | `dev`                      | version shown in the footer, set by the CI    |

`DEBUG` is on only with `manage.py runserver`.

Development
-----------
With docker compose (the directory `saml/` is mounted into the container):

    docker compose up --build

The app runs on http://localhost:8000. Without docker:

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    cd apps
    ../.venv/bin/python manage.py runserver

`python3-saml` needs the development packages of libxml2 and xmlsec1, see the `Dockerfile`.

Release
-------
The version is the git tag. A release is a pushed tag `X.Y.Z`:

    git tag -a 1.6.6 -m "release 1.6.6"
    git push --follow-tags origin main

The CI builds the image `ghcr.io/g10f/saml-demo:X.Y.Z` (and `latest`) for amd64 and arm64 and
deploys it. A push without a tag does not start the CI.
