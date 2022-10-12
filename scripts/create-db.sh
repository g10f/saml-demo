#!/bin/bash
sudo -u postgres psql -c "CREATE USER saml_demo CREATEDB PASSWORD 'saml_demo'"
sudo -u postgres psql -c 'DROP DATABASE IF EXISTS saml_demo'
sudo -u postgres psql -c 'CREATE DATABASE saml_demo OWNER saml_demo'
