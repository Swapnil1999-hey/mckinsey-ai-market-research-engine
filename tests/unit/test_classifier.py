"""
Unit tests for backend/services/irrelevant_question.py
"""

import sys
import os

# Make the services directory importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend/services"))

from irrelevant_question import classify_query, irrelevant_answer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _verdict(query: str) -> str:
    """Return just the verdict string for a query."""
    verdict, _cat, _reason = classify_query(query)
    return verdict


def _category(query: str) -> str:
    """Return just the category string for a query."""
    _verdict, category, _reason = classify_query(query)
    return category


# ---------------------------------------------------------------------------
# Irrelevant-query detection tests
# ---------------------------------------------------------------------------

class TestIrrelevantDetection:

    def test_weather_detected(self):
        verdict, category, _ = classify_query("What is the weather today?")
        assert verdict == "irrelevant"
        assert category == "weather"

    def test_date_time_detected(self):
        verdict, category, _ = classify_query("What is today date?")
        assert verdict == "irrelevant"
        assert category == "date_time"

    def test_what_time_is_it(self):
        verdict, category, _ = classify_query("what time is it?")
        assert verdict == "irrelevant"
        assert category == "date_time"

    def test_sports_detected(self):
        verdict, category, _ = classify_query("Who won the IPL match yesterday?")
        assert verdict == "irrelevant"
        assert category == "sports"

    def test_cooking_detected(self):
        verdict, category, _ = classify_query("Give me a recipe for biryani")
        assert verdict == "irrelevant"
        assert category == "cooking_recipes"

    def test_crypto_detected(self):
        verdict, category, _ = classify_query("What is the Bitcoin price today?")
        assert verdict == "irrelevant"
        assert category == "crypto_stock_trading"

    def test_travel_detected(self):
        verdict, category, _ = classify_query("How do I book a flight ticket to Mumbai?")
        assert verdict == "irrelevant"
        assert category == "travel_booking"

    def test_health_detected(self):
        verdict, category, _ = classify_query("What are the symptoms of dengue?")
        assert verdict == "irrelevant"
        assert category == "health_medical"


# ---------------------------------------------------------------------------
# Relevant (pass-through) tests
# ---------------------------------------------------------------------------

class TestRelevantPassthrough:

    def test_market_research_passthrough(self):
        verdict = _verdict("What are the growth opportunities in Indian digital healthcare market?")
        assert verdict == "relevant"

    def test_competitor_analysis_passthrough(self):
        verdict = _verdict("Competitor analysis of fintech startups in India")
        assert verdict == "relevant"

    def test_ev_market_passthrough(self):
        verdict = _verdict("Market forecast for EV sector in India 2025")
        assert verdict == "relevant"

    def test_strategy_passthrough(self):
        verdict = _verdict("Market entry strategy for Southeast Asia")
        assert verdict == "relevant"


# ---------------------------------------------------------------------------
# irrelevant_answer() tests
# ---------------------------------------------------------------------------

class TestIrrelevantAnswer:

    def test_irrelevant_answer_weather(self):
        result = irrelevant_answer("weather today", "weather")
        assert result["is_irrelevant"] is True
        assert "weather" in result["answer"].lower() or "today" in result["answer"].lower()
        assert result["category"] == "weather"

    def test_irrelevant_answer_datetime(self):
        result = irrelevant_answer("what day is it", "date_time")
        assert "is_irrelevant" in result
        assert result["is_irrelevant"] is True

    def test_irrelevant_answer_has_redirect(self):
        result = irrelevant_answer("who won the match", "sports")
        assert len(result["redirect"]) > 10

    def test_irrelevant_answer_keys_complete(self):
        """Every irrelevant_answer call must include all expected keys."""
        result = irrelevant_answer("book a flight", "travel_booking")
        for key in ("is_irrelevant", "category", "query", "answer", "redirect", "timestamp"):
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_empty_query_safe(self):
        """An empty query must not raise and should default to 'relevant'."""
        try:
            verdict, category, _ = classify_query("")
        except Exception as exc:
            raise AssertionError(f"classify_query('') raised unexpectedly: {exc}")
        assert verdict == "relevant"

    def test_mixed_market_weather(self):
        """'market weather conditions in India' — 'market' keyword should fast-pass as relevant."""
        verdict = _verdict("market weather conditions in India")
        assert verdict == "relevant"
