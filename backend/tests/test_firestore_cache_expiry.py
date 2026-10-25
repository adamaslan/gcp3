"""Memory caches retain store expiry without cloud access."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import firestore


@pytest.fixture
def cache(monkeypatch):
    clock = [0.0]
    wall = datetime(2026, 10, 12, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return wall + timedelta(seconds=clock[0])

    monkeypatch.setattr(firestore.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(firestore, 'datetime', Clock)
    monkeypatch.setattr(firestore, '_MEM_CACHE', {})
    store = MagicMock()
    monkeypatch.setattr(firestore, 'db', lambda: store)
    doc = store.collection.return_value.document.return_value
    return clock, wall, doc


def test_firestore_read_does_not_extend_near_expiry(cache):
    clock, wall, doc = cache
    doc.get.return_value.exists = True
    doc.get.return_value.to_dict.return_value = {
        'expires_at': wall + timedelta(seconds=600), 'value': {'error': 'cooldown'},
    }
    clock[0] = 599
    assert firestore.get_cache('failure') == {'error': 'cooldown'}
    assert firestore.get_cache('failure') == {'error': 'cooldown'}
    assert doc.get.call_count == 1
    clock[0] = 601
    assert firestore.get_cache('failure') is None
    assert doc.get.call_count == 2


def test_short_write_ttl_is_preserved_in_memory(cache):
    clock, _, _ = cache
    firestore.set_cache('short', {'value': 1}, ttl_seconds=5)
    assert firestore.mem_get('short') == {'value': 1}
    clock[0] = 6
    assert firestore.mem_get('short') is None


def test_delete_invalidates_memory_only_after_store_delete_succeeds(cache):
    _, _, doc = cache
    firestore.mem_set('summary', {'brief': 'cached'})
    doc.delete.side_effect = RuntimeError('unavailable')
    with pytest.raises(RuntimeError):
        firestore.delete_cache('summary')
    assert firestore.mem_get('summary') == {'brief': 'cached'}
    doc.delete.side_effect = None
    firestore.delete_cache('summary')
    assert firestore.mem_get('summary') is None
