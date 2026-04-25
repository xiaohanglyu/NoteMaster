import pytest
from unittest.mock import MagicMock, patch
import numpy as np


def make_mock_model(dim=8):
    model = MagicMock()
    model.encode.side_effect = lambda text: np.array([0.1] * dim)
    return model


class TestEmbed:
    def test_returns_list_of_floats(self):
        from notemaster.embeddings import embed
        with patch("notemaster.embeddings._get_model", return_value=make_mock_model()):
            result = embed("granularity")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_non_empty(self):
        from notemaster.embeddings import embed
        with patch("notemaster.embeddings._get_model", return_value=make_mock_model()):
            result = embed("test")
        assert len(result) > 0

    def test_model_called_with_text(self):
        from notemaster.embeddings import embed
        mock = make_mock_model()
        with patch("notemaster.embeddings._get_model", return_value=mock):
            embed("hello world")
        mock.encode.assert_called_once_with("hello world")


class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        from notemaster.embeddings import cosine_similarity
        v = [1.0, 0.0, 0.0]
        assert cosine_similarity(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors_return_zero(self):
        from notemaster.embeddings import cosine_similarity
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_similar_vectors(self):
        from notemaster.embeddings import cosine_similarity
        a = [0.12, -0.34, 0.88]
        b = [0.11, -0.31, 0.85]
        assert cosine_similarity(a, b) > 0.99

    def test_zero_vector_returns_zero(self):
        from notemaster.embeddings import cosine_similarity
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0
