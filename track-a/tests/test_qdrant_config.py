"""Qdrant collection config tests (no live server required)."""

from qdrant_client import models

from app.config import get_settings
from app.core.qdrant import build_collection_config


def test_dense_vector_config():
    cfg = build_collection_config()
    dense = cfg["vectors_config"]["dense"]
    assert isinstance(dense, models.VectorParams)
    assert dense.size == get_settings().dense_vector_size == 384
    assert dense.distance == models.Distance.COSINE


def test_sparse_vector_config():
    cfg = build_collection_config()
    sparse = cfg["sparse_vectors_config"]["sparse"]
    assert isinstance(sparse, models.SparseVectorParams)
    assert sparse.modifier == models.Modifier.IDF
    assert sparse.index.on_disk is False


def test_build_collection_config_keys():
    cfg = build_collection_config()
    assert set(cfg.keys()) == {"vectors_config", "sparse_vectors_config"}
    assert set(cfg["vectors_config"].keys()) == {"dense"}
    assert set(cfg["sparse_vectors_config"].keys()) == {"sparse"}
