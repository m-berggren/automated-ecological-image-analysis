"""Integration tests for the auth endpoints (register / login / refresh) and
the global IsAuthenticated default.
"""

import pytest
from django.contrib.auth.models import User

pytestmark = pytest.mark.django_db

REGISTER = '/api/auth/register/'
LOGIN = '/api/auth/login/'
REFRESH = '/api/auth/refresh/'
PROTECTED = '/api/analysis/models/'


class TestRegister:
    def test_success_returns_token_pair(self, api):
        resp = api.post(
            REGISTER,
            {'username': 'alice', 'password': 'pw12345', 'email': 'a@example.com'},
            format='json',
        )
        assert resp.status_code == 200
        assert 'access' in resp.data and 'refresh' in resp.data
        assert User.objects.filter(username='alice').exists()

    def test_missing_password_rejected(self, api):
        resp = api.post(REGISTER, {'username': 'alice'}, format='json')
        assert resp.status_code == 400

    def test_missing_email_rejected(self, api):
        resp = api.post(
            REGISTER, {'username': 'alice', 'password': 'pw12345'}, format='json'
        )
        assert resp.status_code == 400

    def test_duplicate_username_rejected(self, api, user):
        resp = api.post(
            REGISTER,
            {'username': 'tester', 'password': 'pw12345', 'email': 'new@example.com'},
            format='json',
        )
        assert resp.status_code == 400

    def test_duplicate_email_rejected(self, api, user):
        resp = api.post(
            REGISTER,
            {'username': 'newname', 'password': 'pw12345', 'email': 't@example.com'},
            format='json',
        )
        assert resp.status_code == 400


class TestLogin:
    def test_valid_credentials_return_tokens(self, api, user):
        resp = api.post(
            LOGIN, {'username': 'tester', 'password': 'pw12345'}, format='json'
        )
        assert resp.status_code == 200
        assert 'access' in resp.data and 'refresh' in resp.data

    def test_bad_credentials_rejected(self, api, user):
        resp = api.post(
            LOGIN, {'username': 'tester', 'password': 'wrong'}, format='json'
        )
        assert resp.status_code == 401


class TestRefresh:
    def test_refresh_returns_new_access(self, api, user):
        login = api.post(
            LOGIN, {'username': 'tester', 'password': 'pw12345'}, format='json'
        )
        resp = api.post(REFRESH, {'refresh': login.data['refresh']}, format='json')
        assert resp.status_code == 200
        assert 'access' in resp.data

    def test_garbage_refresh_rejected(self, api):
        resp = api.post(REFRESH, {'refresh': 'not-a-token'}, format='json')
        assert resp.status_code == 401


class TestAuthGate:
    def test_protected_endpoint_requires_auth(self, api):
        assert api.get(PROTECTED).status_code == 401

    def test_protected_endpoint_ok_when_authenticated(self, auth_client):
        assert auth_client.get(PROTECTED).status_code == 200
