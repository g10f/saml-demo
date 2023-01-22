#!/usr/bin/env bash
set -xef


if [ "$DJANGO_MIGRATE" = "on" ]; then
	./manage.py migrate --noinput
fi

if  [ "$DJANGO_CREATE_SUPERUSER" = "on" ]; then
  user_count=$(./manage.py user_count)

  if [[ $user_count -eq 0 ]]; then

    if  [ "$DJANGO_CREATE_SUPERUSER" = "on" ]; then
      ./manage.py createsuperuser --noinput
    fi

  fi
fi

# shellcheck disable=SC2068
exec $@
