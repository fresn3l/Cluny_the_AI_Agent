"""Tests for cross-encoder rerank model caching."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from cluny.query import RetrievedChunk, _cross_rerank, _get_cross_encoder


def test_cross_encoder_cached():
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.5, 0.9]
    fake_st = MagicMock()
    fake_st.CrossEncoder.return_value = mock_model

    import cluny.query as query_mod

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        query_mod._CROSS_ENCODER = None
        chunks = [
            RetrievedChunk("a", "l1", None, 0, 1.0, "d1"),
            RetrievedChunk("b", "l2", None, 1, 0.9, "d2"),
        ]
        _cross_rerank(chunks, "question", k=1)
        _cross_rerank(chunks, "question", k=1)
        assert fake_st.CrossEncoder.call_count == 1


def test_get_cross_encoder_returns_same_instance():
    mock_model = MagicMock()
    fake_st = MagicMock()
    fake_st.CrossEncoder.return_value = mock_model

    import cluny.query as query_mod

    with patch.dict(sys.modules, {"sentence_transformers": fake_st}):
        query_mod._CROSS_ENCODER = None
        a = _get_cross_encoder()
        b = _get_cross_encoder()
        assert a is b
        assert fake_st.CrossEncoder.call_count == 1
