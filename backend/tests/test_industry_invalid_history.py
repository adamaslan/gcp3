from unittest.mock import MagicMock, patch
import industry
import etf_store


def test_invalid_history_cannot_restore_cached_returns():
    cached = MagicMock()
    cached.id = 'Test'
    cached.to_dict.return_value = {'returns': {'1d': -73.9}, '52w_high': 999}
    db = MagicMock()
    db.collection.return_value.list_documents.return_value = []
    db.collection.return_value.stream.return_value = [cached]
    rows = {'Test': {'etf': 'TEST', 'returns': {'1d': 12}, '52w_high': 55}}
    # On the old implementation invalid histories return None, triggering fallback.
    failure = getattr(etf_store, 'InvalidHistory', None)
    with patch('firestore.db', return_value=db), patch.object(etf_store, 'compute_returns', side_effect=failure('bad history') if failure else None, return_value=None):
        industry._attach_stored_returns(rows)
    assert rows['Test']['returns'] == {}
    assert rows['Test']['52w_high'] is None
    assert rows['Test']['return_data_status'] == 'invalid_history'
    persisted = db.batch.return_value.set.call_args.args[1]
    assert persisted['returns'] == {}
    assert persisted['return_data_status'] == 'invalid_history'


def test_missing_history_preserves_legacy_cache_fallback():
    cached = MagicMock()
    cached.id = 'Test'
    cached.to_dict.return_value = {'returns': {'1d': 2.0}}
    db = MagicMock()
    db.collection.return_value.list_documents.return_value = []
    db.collection.return_value.stream.return_value = [cached]
    rows = {'Test': {'etf': 'TEST'}}
    with patch('firestore.db', return_value=db), patch.object(etf_store, 'compute_returns', return_value=None):
        industry._attach_stored_returns(rows)
    assert rows['Test']['returns'] == {'1d': 2.0}
