"""Integration test for GET /api/pollinator/training/pool/.

Verifies the eligibility-count endpoint responds with the documented shape on
an empty database (no detections -> nothing available or consumed).
"""

import pytest

pytestmark = pytest.mark.django_db

POOL = '/api/pollinator/training/pool/'


def test_pool_empty_counts(auth_client):
    resp = auth_client.get(POOL, {'track': 'detector'})
    assert resp.status_code == 200
    assert resp.data['available'] == 0
    assert resp.data['consumed'] == 0
