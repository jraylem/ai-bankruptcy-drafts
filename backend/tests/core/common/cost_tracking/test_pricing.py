"""Pricing math + model-name normalization."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.core.common.cost_tracking.pricing import (
    compute_cost_usd,
    normalize_model_name,
    web_search_fee_usd,
)


@pytest.mark.unit
class TestNormalizeModelName:
    def test_strips_trailing_date_suffix(self):
        assert normalize_model_name("claude-haiku-4-5-20251001") == "claude-haiku-4-5"

    def test_strips_bracket_variant_suffix(self):
        assert normalize_model_name("claude-opus-4-7[1m]") == "claude-opus-4-7"

    def test_lowercases_and_trims(self):
        assert normalize_model_name(" Claude-Sonnet-4-6 ") == "claude-sonnet-4-6"

    def test_empty_returns_empty(self):
        assert normalize_model_name("") == ""


@pytest.mark.unit
class TestComputeCostUsd:
    def test_haiku_input_output(self):
        # 1k input @ $1/1M + 1k output @ $5/1M = $0.006
        cost = compute_cost_usd(
            model="claude-haiku-4-5",
            input_tokens=1000, output_tokens=1000,
        )
        assert cost == Decimal("0.006")

    def test_sonnet_input_output(self):
        # 1k in @ $3/1M + 1k out @ $15/1M = $0.018
        cost = compute_cost_usd(
            model="claude-sonnet-4-6",
            input_tokens=1000, output_tokens=1000,
        )
        assert cost == Decimal("0.018")

    def test_opus_input_output(self):
        # 1k in @ $5/1M + 1k out @ $25/1M = $0.030
        cost = compute_cost_usd(
            model="claude-opus-4-7",
            input_tokens=1000, output_tokens=1000,
        )
        assert cost == Decimal("0.030")

    def test_cache_discount_haiku(self):
        # cache_read @ 0.1× input rate (= $0.10/1M) — 10k reads = $0.001
        cost = compute_cost_usd(
            model="claude-haiku-4-5",
            cache_read_tokens=10000,
        )
        assert cost == Decimal("0.001")

    def test_dated_model_name_normalizes(self):
        cost = compute_cost_usd(
            model="claude-haiku-4-5-20251001",
            input_tokens=1000,
        )
        assert cost == Decimal("0.001")

    def test_embeddings(self):
        # 1M tokens @ $0.13 = $0.13
        cost = compute_cost_usd(
            model="text-embedding-3-large",
            input_tokens=1_000_000,
        )
        assert cost == Decimal("0.130000")

    def test_unknown_model_returns_zero(self):
        cost = compute_cost_usd(
            model="claude-bogus-99",
            input_tokens=1_000_000, output_tokens=1_000_000,
        )
        assert cost == Decimal("0")

    def test_negative_tokens_clamped(self):
        cost = compute_cost_usd(
            model="claude-haiku-4-5",
            input_tokens=-100, output_tokens=-100,
        )
        assert cost == Decimal("0")


@pytest.mark.unit
class TestWebSearchFee:
    def test_per_use_flat_fee(self):
        # 1 search = $0.01
        assert web_search_fee_usd(1) == Decimal("0.010000")

    def test_three_searches(self):
        assert web_search_fee_usd(3) == Decimal("0.030000")

    def test_zero_searches(self):
        assert web_search_fee_usd(0) == Decimal("0")

    def test_negative_clamps_to_zero(self):
        assert web_search_fee_usd(-2) == Decimal("0")
