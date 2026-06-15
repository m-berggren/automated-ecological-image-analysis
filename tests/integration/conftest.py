"""Shared fixtures for the API integration suite.

`api` is an unauthenticated DRF client; `auth_client` is force-authenticated as
`user`. Tests here are auto-marked `integration` (see tests/conftest.py) and run
against the in-memory sqlite test DB.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username='tester', password='pw12345', email='t@example.com'
    )


@pytest.fixture
def auth_client(db, user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client
