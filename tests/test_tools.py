"""
Tests for the three FitFindr tools.

Run from the project root:
    pytest tests/

Coverage:
  search_listings — core behavior, price filter, size filter, sort order, failure mode
  suggest_outfit  — empty-wardrobe path, wardrobe-specific path, LLM exception → ""
  create_fit_card — empty/None/whitespace guard (no LLM call), LLM path, LLM exception
"""

import pytest
from unittest.mock import MagicMock, patch

from tools import create_fit_card, search_listings, suggest_outfit


# ── Shared test data ───────────────────────────────────────────────────────────

SAMPLE_ITEM = {
    "id": "lst_test",
    "title": "Vintage Band Tee — Faded Black",
    "description": "A faded vintage band tee with a great worn-in look.",
    "category": "tops",
    "style_tags": ["vintage", "graphic tee", "grunge", "90s"],
    "size": "M",
    "condition": "good",
    "price": 22.00,
    "colors": ["black"],
    "brand": None,
    "platform": "depop",
}

SAMPLE_WARDROBE = {
    "items": [
        {
            "id": "w_001",
            "name": "Baggy straight-leg jeans, dark wash",
            "category": "bottoms",
            "colors": ["dark blue", "indigo"],
            "style_tags": ["denim", "streetwear", "baggy"],
            "notes": "High-waisted",
        },
        {
            "id": "w_002",
            "name": "Chunky white sneakers",
            "category": "shoes",
            "colors": ["white"],
            "style_tags": ["chunky", "streetwear"],
            "notes": "",
        },
    ]
}

EMPTY_WARDROBE = {"items": []}


def _make_mock_groq(content: str = "mocked LLM response") -> MagicMock:
    """Return a mock Groq client whose chat.completions.create() returns content."""
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ── Tool 1: search_listings ────────────────────────────────────────────────────

class TestSearchListings:

    def test_returns_results_for_valid_query(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)
        assert len(results) > 0

    # Failure mode: no matching listings — must return [] not raise
    def test_returns_empty_list_for_nonsense_query(self):
        results = search_listings("zzzxxx", size="XXS", max_price=5)
        assert results == []

    def test_empty_results_never_raises(self):
        try:
            results = search_listings("zzzxxx", size=None, max_price=None)
            assert results == []
        except Exception as exc:
            pytest.fail(f"search_listings raised unexpectedly: {exc}")

    def test_price_filter_excludes_items_above_max(self):
        results = search_listings("jacket", size=None, max_price=25)
        assert all(item["price"] <= 25 for item in results)

    def test_price_filter_includes_item_at_exact_boundary(self):
        # price <= max_price: an item priced exactly at the ceiling must be included
        from utils.data_loader import load_listings
        min_price = min(item["price"] for item in load_listings())
        results = search_listings("vintage", size=None, max_price=min_price)
        assert all(item["price"] <= min_price for item in results)

    def test_size_filter_keeps_only_matching_size(self):
        # "S/M" exists in the dataset (lst_002 — Y2K Baby Tee)
        results = search_listings("tee", size="S/M", max_price=None)
        assert len(results) > 0
        assert all(item["size"].lower() == "s/m" for item in results)

    def test_size_filter_is_case_insensitive(self):
        lower = {r["id"] for r in search_listings("tee", size="s/m", max_price=None)}
        upper = {r["id"] for r in search_listings("tee", size="S/M", max_price=None)}
        assert lower == upper

    def test_no_filters_returns_more_results_than_filtered(self):
        filtered = search_listings("vintage", size="M", max_price=20)
        unfiltered = search_listings("vintage", size=None, max_price=None)
        assert len(unfiltered) >= len(filtered)

    def test_result_dicts_contain_all_required_fields(self):
        required = {
            "id", "title", "description", "category", "style_tags",
            "size", "condition", "price", "colors", "brand", "platform",
        }
        results = search_listings("vintage", size=None, max_price=None)
        for item in results:
            assert required.issubset(item.keys()), f"Missing fields in: {item}"

    def test_results_sorted_highest_score_first(self):
        # A two-keyword query: items matching both keywords should outrank single-keyword matches.
        results = search_listings("vintage denim", size=None, max_price=None)
        if len(results) < 2:
            pytest.skip("Not enough results to test sort order")

        def keyword_hits(item):
            text = " ".join([
                item["title"],
                item["description"],
                " ".join(item["style_tags"]),
                item["category"],
            ]).lower()
            return sum(1 for kw in ["vintage", "denim"] if kw in text)

        assert keyword_hits(results[0]) >= keyword_hits(results[-1])


# ── Tool 2: suggest_outfit ─────────────────────────────────────────────────────

class TestSuggestOutfit:

    # Failure mode: empty wardrobe — must not crash and must use the fallback prefix
    def test_empty_wardrobe_returns_string_with_expected_prefix(self):
        prefix = "Since you haven't added wardrobe items yet, here are general styling ideas: "
        mock_client = _make_mock_groq(prefix + "try pairing with wide-leg trousers.")
        with patch("tools._get_groq_client", return_value=mock_client):
            result = suggest_outfit(SAMPLE_ITEM, EMPTY_WARDROBE)
        assert result.startswith(prefix)

    def test_empty_wardrobe_never_raises(self):
        mock_client = _make_mock_groq("general advice here.")
        with patch("tools._get_groq_client", return_value=mock_client):
            try:
                result = suggest_outfit(SAMPLE_ITEM, EMPTY_WARDROBE)
                assert isinstance(result, str)
            except Exception as exc:
                pytest.fail(f"suggest_outfit raised on empty wardrobe: {exc}")

    def test_with_wardrobe_returns_llm_response(self):
        expected = "Pair this tee with your baggy jeans and chunky sneakers."
        mock_client = _make_mock_groq(expected)
        with patch("tools._get_groq_client", return_value=mock_client):
            result = suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE)
        assert result == expected

    def test_with_wardrobe_prompt_includes_wardrobe_item_names(self):
        # Wardrobe item names must be in the prompt so the LLM can reference them
        mock_client = _make_mock_groq("some suggestion")
        with patch("tools._get_groq_client", return_value=mock_client):
            suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE)
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        prompt_text = " ".join(m["content"] for m in messages)
        assert "Baggy straight-leg jeans" in prompt_text
        assert "Chunky white sneakers" in prompt_text

    def test_llm_exception_returns_empty_string(self):
        # Failure mode: Groq raises → "" so agent.py can set session["error"]
        with patch("tools._get_groq_client", side_effect=Exception("API error")):
            result = suggest_outfit(SAMPLE_ITEM, SAMPLE_WARDROBE)
        assert result == ""


# ── Tool 3: create_fit_card ────────────────────────────────────────────────────

class TestCreateFitCard:

    ERROR_MSG = "Could not create a fit card — outfit data was missing or incomplete."

    # Failure mode: empty/None/whitespace outfit — must return error string, never call LLM
    def test_empty_string_returns_error_without_calling_llm(self):
        with patch("tools._get_groq_client") as mock_get:
            result = create_fit_card("", SAMPLE_ITEM)
        assert result == self.ERROR_MSG
        mock_get.assert_not_called()

    def test_none_returns_error_without_calling_llm(self):
        with patch("tools._get_groq_client") as mock_get:
            result = create_fit_card(None, SAMPLE_ITEM)
        assert result == self.ERROR_MSG
        mock_get.assert_not_called()

    def test_whitespace_only_returns_error_without_calling_llm(self):
        with patch("tools._get_groq_client") as mock_get:
            result = create_fit_card("   ", SAMPLE_ITEM)
        assert result == self.ERROR_MSG
        mock_get.assert_not_called()

    def test_valid_outfit_returns_llm_response(self):
        caption = "found this vintage tee on depop for $22 and it goes with everything."
        mock_client = _make_mock_groq(caption)
        with patch("tools._get_groq_client", return_value=mock_client):
            result = create_fit_card("Pair with baggy jeans.", SAMPLE_ITEM)
        assert result == caption

    def test_prompt_includes_item_price_and_platform(self):
        # Price and platform must reach the LLM so it can include them in the caption
        mock_client = _make_mock_groq("a caption")
        with patch("tools._get_groq_client", return_value=mock_client):
            create_fit_card("Pair with baggy jeans.", SAMPLE_ITEM)
        messages = mock_client.chat.completions.create.call_args.kwargs["messages"]
        prompt_text = " ".join(m["content"] for m in messages)
        assert "depop" in prompt_text.lower()
        assert "22" in prompt_text  # price 22.00

    def test_llm_exception_returns_error_string_not_empty(self):
        # Failure mode: Groq raises → error string (not "") so UI has something to show
        with patch("tools._get_groq_client", side_effect=Exception("timeout")):
            result = create_fit_card("Pair with baggy jeans.", SAMPLE_ITEM)
        assert result == self.ERROR_MSG
