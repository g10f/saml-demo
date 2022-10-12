import base64

from django.conf import settings
from django.http import (HttpResponse, HttpResponseRedirect,
                         HttpResponseServerError)
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.settings import OneLogin_Saml2_Settings
from onelogin.saml2.utils import OneLogin_Saml2_Utils

import logging

logger = logging.getLogger(__name__)


def update_authn_context(saml_settings, comparison='minimum', loa=1):
    mapping = {
        1: ["urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"],
        2: ["urn:oasis:names:tc:SAML:2.0:ac:classes:TimeSyncToken"],
        3: ["urn:oasis:names:tc:SAML:2.0:ac:classes:X509"]
    }
    saml_settings._security['requestedAuthnContextComparison'] = comparison
    saml_settings._security['requestedAuthnContext'] = mapping[loa]
    return saml_settings


def init_saml_auth(req):
    saml_settings = OneLogin_Saml2_Settings(custom_base_path=settings.SAML_FOLDER)
    saml_settings = update_authn_context(saml_settings)
    auth = OneLogin_Saml2_Auth(req, old_settings=saml_settings)
    return auth


def prepare_django_request(request):
    # If server is behind proxys or balancers use the HTTP_X_FORWARDED fields
    result = {
        'https': 'on' if request.is_secure() else 'off',
        'http_host': request.META['HTTP_HOST'],
        'script_name': request.META['PATH_INFO'],
        'get_data': request.GET.copy(),
        'post_data': request.POST.copy()
    }
    if 'HTTP_X_FORWARDED_FOR' not in request.META:
        result['server_port'] = request.META['SERVER_PORT']
    return result


@csrf_exempt
def index(request):
    req = prepare_django_request(request)
    auth = init_saml_auth(req)
    errors = []
    not_auth_warn = False
    success_slo = False
    attributes = False
    paint_logout = False

    if 'sso' in req['get_data']:
        return HttpResponseRedirect(auth.login(force_authn=False))
    elif 'sso2' in req['get_data']:
        return_to = OneLogin_Saml2_Utils.get_self_url(req) + reverse('service_provider:attrs')
        return HttpResponseRedirect(auth.login(return_to))
    elif 'slo' in req['get_data']:
        name_id = None
        session_index = None
        if 'samlNameId' in request.session:
            name_id = request.session['samlNameId']
        if 'samlSessionIndex' in request.session:
            session_index = request.session['samlSessionIndex']

        return HttpResponseRedirect(auth.logout(name_id=name_id, session_index=session_index))
    elif 'acs' in req['get_data']:
        auth.process_response()
        errors = auth.get_errors()
        not_auth_warn = not auth.is_authenticated()
        if not errors:
            request.session['samlUserdata'] = auth.get_attributes()
            request.session['samlNameId'] = auth.get_nameid()
            request.session['samlSessionIndex'] = auth.get_session_index()
            logger.info(base64.b64decode(req['post_data']['SAMLResponse']))
            if 'RelayState' in req['post_data'] and \
                    OneLogin_Saml2_Utils.get_self_url(req) != req['post_data']['RelayState']:
                return HttpResponseRedirect(auth.redirect_to(req['post_data']['RelayState']))
    elif 'sls' in req['get_data']:
        url = auth.process_slo(delete_session_cb=lambda: request.session.flush())
        errors = auth.get_errors()
        if len(errors) == 0:
            if url is not None:
                return HttpResponseRedirect(url)
            else:
                success_slo = True

    if 'samlUserdata' in request.session:
        paint_logout = True
        if len(request.session['samlUserdata']) > 0:
            attributes = request.session['samlUserdata'].items()

    context = {
        'samlNameId': request.session.get('samlNameId'),
        'samlSessionIndex': request.session.get('samlSessionIndex'),
        'errors': errors,
        'not_auth_warn': not_auth_warn,
        'success_slo': success_slo,
        'attributes': attributes,
        'paint_logout': paint_logout}
    return render(request, 'index.html', context=context)


def attrs(request):
    paint_logout = False
    attributes = False

    if 'samlUserdata' in request.session:
        paint_logout = True
        if len(request.session['samlUserdata']) > 0:
            attributes = request.session['samlUserdata'].items()

    return render(request, 'attrs.html', {'paint_logout': paint_logout, 'attributes': attributes})


def metadata(request):
    # req = prepare_django_request(request)
    # auth = init_saml_auth(req)
    # saml_settings = auth.get_settings()
    saml_settings = OneLogin_Saml2_Settings(settings=None, custom_base_path=settings.SAML_FOLDER,
                                            sp_validation_only=True)
    sp_metadata = saml_settings.get_sp_metadata()
    errors = saml_settings.validate_metadata(sp_metadata)

    if len(errors) == 0:
        resp = HttpResponse(content=sp_metadata, content_type='text/xml')
    else:
        resp = HttpResponseServerError(content=', '.join(errors))
    return resp
