docker run \
  -p 8000:8000 \
  -v /home/gunnar/workspace/saml-demo/saml:/opt/g10f/saml-demo/saml \
  -e DATABASE_URL=postgres://saml_demo:saml_demo@host.docker.internal:5432/saml_demo \
  -e FORWARDED_ALLOW_IPS=* \
  -e DJANGO_MIGRATE=on \
  -e DJANGO_CREATE_SUPERUSER=on \
  -e DJANGO_SUPERUSER_UNIQUE_NAME=admin \
  -e DJANGO_SUPERUSER_UUID=3f7409f9-3b81-4d84-a7c5-668bc6e58c5c \
  -e DJANGO_SUPERUSER_EMAIL=mail@g10f.de \
  ghcr.io/g10f/saml-demo
