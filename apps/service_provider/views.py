import base64

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import (HttpResponse, HttpResponseRedirect, HttpResponseServerError)
from django.shortcuts import render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from lxml import etree
from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.errors import OneLogin_Saml2_Error
from onelogin.saml2.settings import OneLogin_Saml2_Settings

import logging

logger = logging.getLogger(__name__)

# Session key for the ID of the AuthnRequest that this browser sent to the IdP
REQUEST_ID_SESSION_KEY = 'samlRequestId'

# Exceptions python3-saml raises for a missing or malformed SAML message. They are client errors and must not end
# in a 500 (which also mails the admins): OneLogin_Saml2_Error for a missing message, lxml errors for invalid XML,
# ValueError for forbidden DTDs and invalid base64.
INVALID_MESSAGE_ERRORS = (OneLogin_Saml2_Error, etree.LxmlError, ValueError)


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
    # The binding of the response to the browser (process_acs_response) compares the InResponseTo of the Response
    # element. That value is only protected if the IdP signs the whole Response, not just the assertion.
    if not saml_settings.get_security_data()['wantMessagesSigned']:
        raise ImproperlyConfigured('The SAML setting security.wantMessagesSigned must be true, otherwise the '
                                   'InResponseTo of a response could be changed and the login bound to another browser.')
    saml_settings = update_authn_context(saml_settings)
    auth = OneLogin_Saml2_Auth(req, old_settings=saml_settings)
    return auth


def prepare_django_request(request):
    # If server is behind proxys or balancers use the HTTP_X_FORWARDED fields
    result = {
        'https': 'on' if request.is_secure() else 'off',
        # get_host() is checked against ALLOWED_HOSTS, and HTTP_HOST is missing in requests without Host header
        'http_host': request.get_host(),
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
    success_slo = False
    attributes = False
    paint_logout = False

    match req['get_data']:
        case {'sso': _}:
            url = auth.login(force_authn=False)
            # Remember the ID of the request in this browser. The ACS accepts only the response to exactly this
            # request, see process_acs_response.
            request.session[REQUEST_ID_SESSION_KEY] = auth.get_last_request_id()
            return HttpResponseRedirect(url)
        case {'slo': _}:
            name_id = None
            session_index = None
            if 'samlNameId' in request.session:
                name_id = request.session['samlNameId']
            if 'samlSessionIndex' in request.session:
                session_index = request.session['samlSessionIndex']
            return HttpResponseRedirect(auth.logout(name_id=name_id, session_index=session_index))
        case {'acs': _}:
            errors = process_acs_response(request, auth)
            if not errors:
                request.session['samlUserdata'] = auth.get_attributes()
                request.session['samlNameId'] = auth.get_nameid()
                request.session['samlSessionIndex'] = auth.get_session_index()
                logger.debug(base64.b64decode(req['post_data']['SAMLResponse']))
                # The RelayState comes back from the IdP unprotected and could point anywhere. Only follow it to
                # this site, otherwise the ACS would be an open redirector (SAML Bindings 3.4.3, RFC 9700 4.11).
                relay_state = req['post_data'].get('RelayState')
                if relay_state and url_has_allowed_host_and_scheme(
                        relay_state, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    return HttpResponseRedirect(relay_state)
                return HttpResponseRedirect(reverse('service_provider:index'))
        case {'sls': _}:
            try:
                url = auth.process_slo(delete_session_cb=lambda: request.session.flush())
                errors = auth.get_errors()
            except INVALID_MESSAGE_ERRORS as e:
                logger.warning('Invalid SAML logout message: %r', e)
                errors = ['The logout message is missing or invalid.']
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
        'success_slo': success_slo,
        'attributes': attributes,
        'paint_logout': paint_logout}
    return render(request, 'index.html', context=context)


def process_acs_response(request, auth):
    """
    Validate the SAML response posted to the ACS and return a list of errors, empty if the login is valid.

    The response must answer the AuthnRequest that was sent from this browser. Without this check anybody who has a
    valid response for their own account could post it to the ACS from another browser and log that browser in with
    their account (login CSRF). IdP-initiated logins are therefore not supported.

    The details of a rejection are only logged: they can contain values from the unsigned parts of the response.
    They are logged with %r, so that line breaks in these values cannot fake log lines.
    """
    # The ID is removed from the session in any case, so that the same session can use a response only once
    # (SAML Profiles 4.1.4.5). With cookie based sessions a copy of the old cookie still holds the ID, so a replay
    # with it remains possible until the response expires (NotOnOrAfter, a few minutes).
    request_id = request.session.pop(REQUEST_ID_SESSION_KEY, None)
    if request_id is None:
        logger.warning('SAML response without a login started in this browser')
        return ['No login was started in this browser, or its response was already used. Please log in again. '
                'If this keeps happening, the browser does not send the session cookie back: it needs cookies '
                'enabled and the site opened with https or on http://localhost.']

    try:
        auth.process_response(request_id=request_id)
    except INVALID_MESSAGE_ERRORS as e:
        logger.warning('Invalid SAML response: %r', e)
        return ['The SAML response is missing or invalid.']

    if auth.get_errors():
        logger.warning('SAML response rejected: %r %r', auth.get_errors(), auth.get_last_error_reason())
        return ['The SAML response is not valid.']

    # python3-saml compares InResponseTo with the request ID only if the response contains InResponseTo, so an
    # unsolicited response would pass. It must be present and match.
    if auth.get_last_response_in_response_to() != request_id:
        logger.warning('SAML response does not answer the request %r of this browser', request_id)
        return ['The SAML response does not answer the login started in this browser.']

    return []


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
