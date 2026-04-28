"""Tests for shadow reading pronunciation scoring."""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Word-level diff
# ---------------------------------------------------------------------------

class TestScoreShadowReading:
    def test_perfect_match(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("hello world", "hello world")
        assert result.overall_score == 1.0
        assert all(w.status == "ok" for w in result.words)

    def test_substituted_word(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("eventual consistency", "eventual concurrency")
        statuses = [w.status for w in result.words]
        assert "substituted" in statuses

    def test_omitted_word(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("the quick brown fox", "the brown fox")
        statuses = [w.status for w in result.words]
        assert "omitted" in statuses

    def test_inserted_word(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("hello world", "hello beautiful world")
        statuses = [w.status for w in result.words]
        assert "inserted" in statuses

    def test_overall_score_between_0_and_1(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("idempotent throughput latency", "idempotent troughput latency")
        assert 0.0 <= result.overall_score <= 1.0

    def test_score_reflects_accuracy(self):
        from notemaster.pronunciation import score_shadow_reading
        perfect = score_shadow_reading("hello world", "hello world")
        bad = score_shadow_reading("hello world", "goodbye earth")
        assert perfect.overall_score > bad.overall_score

    def test_case_insensitive(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("Hello World", "hello world")
        assert result.overall_score == 1.0

    def test_punctuation_ignored(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("Hello, world!", "hello world")
        assert result.overall_score == 1.0

    def test_word_results_contain_reference_word(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("idempotent", "idempotent")
        assert result.words[0].reference == "idempotent"

    def test_substituted_word_has_heard(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("idempotent", "indeterminate")
        subst = [w for w in result.words if w.status == "substituted"]
        assert len(subst) == 1
        assert subst[0].heard == "indeterminate"

    def test_empty_transcript(self):
        from notemaster.pronunciation import score_shadow_reading
        result = score_shadow_reading("hello world", "")
        assert result.overall_score == 0.0


# ---------------------------------------------------------------------------
# LLM feedback generation
# ---------------------------------------------------------------------------

class TestGetPronunciationFeedback:
    def _make_mock_provider(self, response: str):
        p = MagicMock()
        p.complete.return_value = response
        return p

    def test_returns_string(self):
        from notemaster.pronunciation import get_pronunciation_feedback, WordResult
        words = [WordResult(reference="idempotent", heard="indeterminate", status="substituted")]
        provider = self._make_mock_provider("Try 'eye-DEM-poh-tent' — stress the second syllable.")
        feedback = get_pronunciation_feedback(words, provider=provider)
        assert isinstance(feedback, str)
        assert len(feedback) > 0

    def test_calls_provider_with_problem_words(self):
        from notemaster.pronunciation import get_pronunciation_feedback, WordResult
        words = [
            WordResult(reference="throughput", heard="troughput", status="substituted"),
            WordResult(reference="ok", heard="ok", status="ok"),
        ]
        provider = self._make_mock_provider("Watch 'throughput': THRU-put.")
        get_pronunciation_feedback(words, provider=provider)
        call_args = provider.complete.call_args
        assert "throughput" in str(call_args)

    def test_no_problem_words_returns_positive(self):
        from notemaster.pronunciation import get_pronunciation_feedback, WordResult
        words = [WordResult(reference="hello", heard="hello", status="ok")]
        provider = self._make_mock_provider("Perfect pronunciation!")
        feedback = get_pronunciation_feedback(words, provider=provider)
        assert isinstance(feedback, str)


# ---------------------------------------------------------------------------
# Full assess_shadow pipeline
# ---------------------------------------------------------------------------

class TestAssessShadow:
    def test_returns_shadow_result(self):
        from notemaster.pronunciation import assess_shadow, ShadowResult
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Good job overall."
        result = assess_shadow(
            reference="idempotent operations",
            transcript="idempotent operations",
            provider=mock_provider,
        )
        assert isinstance(result, ShadowResult)
        assert result.overall_score == 1.0
        assert isinstance(result.feedback, str)

    def test_identifies_problem_words(self):
        from notemaster.pronunciation import assess_shadow
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Watch throughput."
        result = assess_shadow(
            reference="throughput and latency",
            transcript="troughput and latency",
            provider=mock_provider,
        )
        problem = [w for w in result.words if w.status != "ok"]
        assert len(problem) >= 1

    def test_feedback_skipped_on_perfect_score(self):
        from notemaster.pronunciation import assess_shadow
        mock_provider = MagicMock()
        result = assess_shadow(
            reference="hello world",
            transcript="hello world",
            provider=mock_provider,
        )
        mock_provider.complete.assert_not_called()
        assert "perfect" in result.feedback.lower() or result.overall_score == 1.0
