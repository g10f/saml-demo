docker run \
  -p 8000:8000 \
  -v /home/gunnar/workspace/saml-demo/saml:/opt/g10f/saml-demo/saml \
  -e DATABASE_HOST=host.docker.internal \
  -e FORWARDED_ALLOW_IPS=* \
  -e HOST=localhost \
  g10f/saml-demo

