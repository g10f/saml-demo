from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from jinja2 import Environment


def environment(**options):
    env = Environment(**options)
    env.globals.update({
        'static': static,
        'url': reverse,
        'enable_plausible': settings.ENABLE_PLAUSIBLE,
        'domain': settings.DOMAIN
    })
    return env
