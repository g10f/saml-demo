import base64
import copy
import json
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from lxml import etree
from onelogin.saml2.utils import OneLogin_Saml2_Utils

SP_URL = 'http://testserver'
IDP_ENTITY_ID = 'https://idp.example.org/saml'


def create_key_pair(directory, name):
    """Create a throwaway RSA key and self-signed certificate with openssl, return both PEM bodies."""
    key_file = directory / f'{name}.key'
    cert_file = directory / f'{name}.crt'
    subprocess.run(
        ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', f'/CN={name}',
         '-keyout', str(key_file), '-out', str(cert_file)],
        check=True, capture_output=True)
    return key_file.read_text(), cert_file.read_text()


def saml_time(delta=timedelta()):
    return (datetime.now(timezone.utc) + delta).strftime('%Y-%m-%dT%H:%M:%SZ')


class ServiceProviderTests(SimpleTestCase):
    """Login against a fake IdP whose responses are signed with a key created for the test run."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_dir = tempfile.TemporaryDirectory()
        saml_folder = Path(cls.temp_dir.name)
        sp_key, sp_cert = create_key_pair(saml_folder, 'sp')
        cls.idp_key, cls.idp_cert = create_key_pair(saml_folder, 'idp')
        saml_settings = {
            'strict': True,
            'debug': False,
            'sp': {
                'entityId': f'{SP_URL}/metadata/',
                'assertionConsumerService': {
                    'url': f'{SP_URL}/?acs', 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST'},
                'singleLogoutService': {
                    'url': f'{SP_URL}/?sls', 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'},
                'NameIDFormat': 'urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified',
                'x509cert': sp_cert,
                'privateKey': sp_key,
            },
            'idp': {
                'entityId': IDP_ENTITY_ID,
                'singleSignOnService': {
                    'url': f'{IDP_ENTITY_ID}/sso', 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'},
                'singleLogoutService': {
                    'url': f'{IDP_ENTITY_ID}/slo', 'binding': 'urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect'},
                'x509cert': cls.idp_cert,
            },
        }
        # the same security settings as the deployed demo, except that the host name of the test client is allowed
        advanced_settings = {
            'security': {
                'allowSingleLabelDomains': True,
                'authnRequestsSigned': True,
                'logoutRequestSigned': True,
                'logoutResponseSigned': True,
                'wantMessagesSigned': True,
                'wantAssertionsSigned': False,
                'wantNameId': True,
                'signatureAlgorithm': 'http://www.w3.org/2001/04/xmldsig-more#rsa-sha256',
                'digestAlgorithm': 'http://www.w3.org/2001/04/xmlenc#sha256',
            },
        }
        (saml_folder / 'settings.json').write_text(json.dumps(saml_settings))
        (saml_folder / 'advanced_settings.json').write_text(json.dumps(advanced_settings))
        cls.saml_settings = saml_settings
        cls.advanced_settings = advanced_settings
        cls.settings_override = override_settings(SAML_FOLDER=str(saml_folder))
        cls.settings_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.settings_override.disable()
        cls.temp_dir.cleanup()
        super().tearDownClass()

    def start_login(self, client=None):
        """Start the login in the browser of the client and return the ID of the AuthnRequest."""
        client = client or self.client
        response = client.get('/?sso')
        self.assertEqual(response.status_code, 302)
        saml_request = parse_qs(urlparse(response['Location']).query)['SAMLRequest'][0]
        authn_request = OneLogin_Saml2_Utils.decode_base64_and_inflate(saml_request)
        return etree.fromstring(authn_request).get('ID')

    def make_response(self, in_response_to, name_id='alice', response_in_response_to=None, sign_assertion_only=False):
        """
        Return a SAML response of the IdP, signed and base64 encoded as the HTTP-POST binding sends it.

        in_response_to goes into the Response element and the SubjectConfirmationData of the assertion, unless
        response_in_response_to gives another value for the Response element.
        """
        in_response_to_attribute = f' InResponseTo="{in_response_to}"' if in_response_to else ''
        if response_in_response_to is None:
            response_in_response_to_attribute = in_response_to_attribute
        else:
            response_in_response_to_attribute = f' InResponseTo="{response_in_response_to}"'
        acs_url = f'{SP_URL}/?acs'
        xml = f"""<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_{uuid.uuid4().hex}" Version="2.0"
    IssueInstant="{saml_time()}" Destination="{acs_url}"{response_in_response_to_attribute}>
  <saml:Issuer>{IDP_ENTITY_ID}</saml:Issuer>
  <samlp:Status><samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>
  <saml:Assertion ID="_{uuid.uuid4().hex}" Version="2.0" IssueInstant="{saml_time()}">
    <saml:Issuer>{IDP_ENTITY_ID}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified">{name_id}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData NotOnOrAfter="{saml_time(timedelta(minutes=5))}"
            Recipient="{acs_url}"{in_response_to_attribute}/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="{saml_time(timedelta(minutes=-1))}"
        NotOnOrAfter="{saml_time(timedelta(minutes=5))}">
      <saml:AudienceRestriction><saml:Audience>{SP_URL}/metadata/</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="{saml_time()}" SessionIndex="_session">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
    <saml:AttributeStatement>
      <saml:Attribute Name="email"><saml:AttributeValue>{name_id}@example.org</saml:AttributeValue></saml:Attribute>
    </saml:AttributeStatement>
  </saml:Assertion>
</samlp:Response>"""
        if sign_assertion_only:
            # add_sign signs the parent of the first Issuer in the whole document, so the assertion is signed as
            # a document of its own and then put back into the response
            document = etree.fromstring(xml)
            assertion = document.find('{urn:oasis:names:tc:SAML:2.0:assertion}Assertion')
            signed_assertion = OneLogin_Saml2_Utils.add_sign(etree.tostring(assertion), self.idp_key, self.idp_cert)
            document.replace(assertion, etree.fromstring(signed_assertion))
            signed = etree.tostring(document)
        else:
            signed = OneLogin_Saml2_Utils.add_sign(xml, self.idp_key, self.idp_cert)
        return base64.b64encode(signed).decode()

    def post_response(self, saml_response, relay_state=None, client=None):
        client = client or self.client
        data = {'SAMLResponse': saml_response}
        if relay_state is not None:
            data['RelayState'] = relay_state
        return client.post('/?acs', data)

    def assertLoggedIn(self, client, name_id):
        self.assertEqual(client.session.get('samlNameId'), name_id)

    def assertNotLoggedIn(self, client):
        self.assertNotIn('samlNameId', client.session)

    def test_login(self):
        request_id = self.start_login()
        self.assertEqual(self.client.session['samlRequestId'], request_id)
        response = self.post_response(self.make_response(request_id))
        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertLoggedIn(self.client, 'alice')
        self.assertEqual(self.client.session['samlUserdata'], {'email': ['alice@example.org']})
        self.assertNotIn('samlRequestId', self.client.session)

    def test_response_cannot_be_used_twice_in_a_session(self):
        request_id = self.start_login()
        saml_response = self.make_response(request_id)
        self.post_response(saml_response)
        self.assertLoggedIn(self.client, 'alice')

        # the session cookie set by the first post no longer holds the request ID
        response = self.post_response(saml_response)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No login was started in this browser')

    def test_session_cookie_is_sent_on_the_post_of_the_idp(self):
        self.start_login()
        cookie = self.client.cookies['sessionid']
        self.assertEqual(cookie['samesite'], 'None')
        self.assertTrue(cookie['secure'])
        self.assertTrue(cookie['httponly'])

    def test_response_for_another_browser_is_rejected(self):
        # login CSRF: the attacker starts a login in their own browser and posts the response from the victim's browser
        attacker = self.client_class()
        attacker_request_id = self.start_login(attacker)
        attacker_response = self.make_response(attacker_request_id, name_id='mallory')

        # the victim has no login in progress
        response = self.post_response(attacker_response)
        self.assertEqual(response.status_code, 200)
        self.assertNotLoggedIn(self.client)

        # the victim has its own login in progress
        self.start_login()
        response = self.post_response(attacker_response)
        self.assertEqual(response.status_code, 200)
        self.assertNotLoggedIn(self.client)

    def test_changed_in_response_to_of_the_response_is_rejected(self):
        # The attacker changes the InResponseTo of the Response element to the victim's request ID. This only works
        # if the IdP signs the assertion alone, so such a response must be rejected.
        attacker_request_id = self.start_login(self.client_class())
        victim_request_id = self.start_login()
        for sign_assertion_only in [True, False]:
            with self.subTest(sign_assertion_only=sign_assertion_only):
                saml_response = self.make_response(attacker_request_id, response_in_response_to=victim_request_id,
                                                   sign_assertion_only=sign_assertion_only)
                response = self.post_response(saml_response)
                self.assertEqual(response.status_code, 200)
                self.assertNotLoggedIn(self.client)
                victim_request_id = self.start_login()

    def test_response_signed_only_in_the_assertion_is_rejected(self):
        request_id = self.start_login()
        response = self.post_response(self.make_response(request_id, sign_assertion_only=True))
        self.assertEqual(response.status_code, 200)
        self.assertNotLoggedIn(self.client)

    def test_unsigned_response_messages_are_a_configuration_error(self):
        advanced_settings = copy.deepcopy(self.advanced_settings)
        advanced_settings['security']['wantMessagesSigned'] = False
        advanced_settings['security']['wantAssertionsSigned'] = True
        with tempfile.TemporaryDirectory() as saml_folder:
            (Path(saml_folder) / 'settings.json').write_text(json.dumps(self.saml_settings))
            (Path(saml_folder) / 'advanced_settings.json').write_text(json.dumps(advanced_settings))
            # the configuration error must be loud: a 500, logged as error (which mails the admins)
            with (override_settings(SAML_FOLDER=saml_folder), self.assertRaises(ImproperlyConfigured),
                  self.assertLogs('django.request', 'ERROR')):
                self.client.get('/?sso')

    def test_unsolicited_response_is_rejected(self):
        self.start_login()
        response = self.post_response(self.make_response(in_response_to=None))
        self.assertEqual(response.status_code, 200)
        self.assertNotLoggedIn(self.client)

    def test_relay_state_to_this_site(self):
        request_id = self.start_login()
        response = self.post_response(self.make_response(request_id), relay_state=f'{SP_URL}/?page')
        self.assertRedirects(response, f'{SP_URL}/?page', fetch_redirect_response=False)

    def test_relay_state_to_another_site_is_ignored(self):
        for relay_state in ['https://evil.example.org/', '//evil.example.org/', '/\\evil.example.org/',
                            'http://testserver.evil.example.org/', 'http://testserver:8080/', 'javascript:alert(1)']:
            with self.subTest(relay_state=relay_state):
                request_id = self.start_login()
                response = self.post_response(self.make_response(request_id), relay_state=relay_state)
                self.assertRedirects(response, '/', fetch_redirect_response=False)
                self.assertLoggedIn(self.client, 'alice')

    def test_missing_or_invalid_messages_are_client_errors(self):
        # with a login in progress, so that the response is actually parsed
        for data in [None, {}, {'SAMLResponse': 'not base64 %%%'}, {'SAMLResponse': 'PGE='},
                     {'SAMLResponse': base64.b64encode(b'<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>').decode()}]:
            with self.subTest(data=data):
                self.start_login()
                if data is None:
                    response = self.client.get('/?acs')
                else:
                    response = self.client.post('/?acs', data)
                self.assertEqual(response.status_code, 200)
                self.assertNotLoggedIn(self.client)

        for query in ['?sls', '?sls&SAMLResponse=%25%25%25', '?sls&SAMLRequest=PGE%3D']:
            with self.subTest(query=query):
                response = self.client.get(f'/{query}')
                self.assertEqual(response.status_code, 200)
