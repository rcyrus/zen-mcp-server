"""Tests for Perplexity provider implementation."""

import os
from unittest.mock import patch

import pytest

from providers.base import ProviderType
from providers.perplexity_provider import PerplexityProvider


class TestPerplexityProvider:
    """Test Perplexity provider functionality."""

    def setup_method(self):
        """Set up clean state before each test."""
        # Clear restriction service cache before each test
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    def teardown_method(self):
        """Clean up after each test to avoid singleton issues."""
        # Clear restriction service cache after each test
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    @patch.dict(os.environ, {"PERPLEXITY_API_KEY": "test-key"})
    def test_initialization(self):
        """Test provider initialization."""
        provider = PerplexityProvider("test-key")
        assert provider.api_key == "test-key"
        assert provider.get_provider_type() == ProviderType.PERPLEXITY
        expected_url = "https://api.perplexity.ai/chat/completions"
        assert provider.base_url == expected_url

    def test_initialization_with_api_key(self):
        """Test provider initialization with API key."""
        provider = PerplexityProvider("pplx-test-key-123")
        assert provider.api_key == "pplx-test-key-123"
        assert provider.get_provider_type() == ProviderType.PERPLEXITY

    def test_provider_type(self):
        """Test provider type is correct."""
        provider = PerplexityProvider("test-key")
        assert provider.get_provider_type() == ProviderType.PERPLEXITY

    def test_base_url_correct(self):
        """Test that base URL is set correctly for Perplexity API."""
        provider = PerplexityProvider("test-key")
        expected_url = "https://api.perplexity.ai/chat/completions"
        assert provider.base_url == expected_url

    def test_friendly_name(self):
        """Test provider friendly name."""
        provider = PerplexityProvider("test-key")
        assert provider.FRIENDLY_NAME == "Perplexity"

    def test_model_validation_implemented(self):
        """Test that model validation is now implemented."""
        provider = PerplexityProvider("test-key")

        # Should return True for valid models
        assert provider.validate_model_name("sonar") is True
        assert provider.validate_model_name("sonar-pro") is True
        assert provider.validate_model_name("sonar-reasoning") is True
        assert provider.validate_model_name("r1-1776") is True

        # Should work with aliases
        assert provider.validate_model_name("perplexity") is True
        assert provider.validate_model_name("pplx") is True

        # Should return False for invalid models
        assert provider.validate_model_name("invalid-model") is False
        assert provider.validate_model_name("gpt-4") is False

    def test_get_capabilities_implemented(self):
        """Test that get_capabilities is now implemented."""
        provider = PerplexityProvider("test-key")

        # Should work for valid models
        caps = provider.get_capabilities("sonar")
        assert caps.model_name == "sonar"
        assert caps.provider == ProviderType.PERPLEXITY
        assert caps.supports_streaming is True
        assert caps.supports_function_calling is True

        # Should work with aliases
        caps_alias = provider.get_capabilities("perplexity")
        assert caps_alias.model_name == "sonar"

        # Should raise ValueError for invalid models
        with pytest.raises(ValueError):
            provider.get_capabilities("invalid-model")

    def test_supports_thinking_mode_implemented(self):
        """Test that supports_thinking_mode is now implemented."""
        provider = PerplexityProvider("test-key")

        # Reasoning models should support thinking
        assert provider.supports_thinking_mode("sonar-reasoning") is True
        assert provider.supports_thinking_mode("sonar-reasoning-pro") is True
        assert provider.supports_thinking_mode("sonar-deep-research") is True
        assert provider.supports_thinking_mode("r1-1776") is True

        # Regular models should not support thinking
        assert provider.supports_thinking_mode("sonar") is False
        assert provider.supports_thinking_mode("sonar-pro") is False

        # Invalid models should return False
        assert provider.supports_thinking_mode("invalid-model") is False


class TestPerplexityExtensions:
    """Test Perplexity-specific extensions and parameters."""

    @pytest.fixture
    def provider(self):
        """Create a test PerplexityProvider instance."""
        return PerplexityProvider(api_key="test-key")

    def test_extract_perplexity_params_max_tokens(self, provider):
        """Test PPLX-031: max_tokens parameter extraction."""
        kwargs = {"max_tokens": 500}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "max_tokens" in params
        assert params["max_tokens"] == 500

    def test_extract_perplexity_params_reasoning_effort_valid(self, provider):
        """Test PPLX-024: reasoning_effort for reasoning models."""
        kwargs = {"reasoning_effort": "medium"}
        params = provider._extract_perplexity_params("sonar-reasoning", kwargs)

        assert "reasoning_effort" in params
        assert params["reasoning_effort"] == "medium"

    def test_extract_perplexity_params_reasoning_effort_ignored(self, provider):
        """Test PPLX-024: reasoning_effort ignored for non-reasoning models."""
        kwargs = {"reasoning_effort": "medium"}
        with patch("providers.perplexity_provider.logger") as mock_logger:
            params = provider._extract_perplexity_params("sonar", kwargs)

        assert "reasoning_effort" not in params
        mock_logger.warning.assert_called_once()

    def test_extract_perplexity_params_search_domain_filter(self, provider):
        """Test PPLX-022: search_domain_filter parameter."""
        kwargs = {"search_domain_filter": ["wikipedia.org", "-reddit.com"]}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "search_domain_filter" in params
        assert params["search_domain_filter"] == ["wikipedia.org", "-reddit.com"]

    def test_extract_perplexity_params_search_recency_filter(self, provider):
        """Test PPLX-023: search_recency_filter parameter."""
        kwargs = {"search_recency_filter": "week"}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "search_recency_filter" in params
        assert params["search_recency_filter"] == "week"

    def test_extract_perplexity_params_search_mode(self, provider):
        """Test PPLX-032: search_mode parameter."""
        kwargs = {"search_mode": "high"}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "search_mode" in params
        assert params["search_mode"] == "high"

    def test_extract_perplexity_params_date_filters(self, provider):
        """Test PPLX-033: date filter parameters."""
        kwargs = {"search_after_date_filter": "2025-01-01", "search_before_date_filter": "2025-12-31"}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "search_after_date_filter" in params
        assert "search_before_date_filter" in params
        assert params["search_after_date_filter"] == "2025-01-01"
        assert params["search_before_date_filter"] == "2025-12-31"

    def test_extract_perplexity_params_image_params(self, provider):
        """Test PPLX-034: image parameter handling."""
        kwargs = {"return_images": True, "image_domain_filter": ["unsplash.com"], "image_format_filter": ["jpg", "png"]}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "return_images" in params
        assert "image_domain_filter" in params
        assert "image_format_filter" in params
        assert params["return_images"] is True

    def test_extract_perplexity_params_related_questions(self, provider):
        """Test PPLX-035: related questions parameter."""
        kwargs = {"return_related_questions": True}
        params = provider._extract_perplexity_params("sonar", kwargs)

        assert "return_related_questions" in params
        assert params["return_related_questions"] is True

    def test_validate_reasoning_effort_valid(self, provider):
        """Test reasoning effort validation with valid values."""
        valid_efforts = ["low", "medium", "high"]
        for effort in valid_efforts:
            provider._validate_reasoning_effort(effort)  # Should not raise

    def test_validate_reasoning_effort_invalid(self, provider):
        """Test reasoning effort validation with invalid values."""
        with pytest.raises(ValueError, match="reasoning_effort must be one of"):
            provider._validate_reasoning_effort("invalid")

    def test_validate_search_domain_filter_valid(self, provider):
        """Test search domain filter validation with valid domains."""
        valid_domains = ["wikipedia.org", "-reddit.com", "github.com"]
        provider._validate_search_domain_filter(valid_domains)  # Should not raise

    def test_validate_search_domain_filter_invalid(self, provider):
        """Test search domain filter validation with invalid inputs."""
        with pytest.raises(ValueError, match="must be a list"):
            provider._validate_search_domain_filter("not_a_list")

        with pytest.raises(ValueError, match="items must be strings"):
            provider._validate_search_domain_filter([123])

        with pytest.raises(ValueError, match="Invalid domain format"):
            provider._validate_search_domain_filter(["invalid_domain"])

    def test_validate_search_recency_filter_valid(self, provider):
        """Test search recency filter validation with valid values."""
        valid_recencies = ["hour", "day", "week", "month", "year"]
        for recency in valid_recencies:
            provider._validate_search_recency_filter(recency)  # Should not raise

    def test_validate_search_recency_filter_invalid(self, provider):
        """Test search recency filter validation with invalid values."""
        with pytest.raises(ValueError, match="search_recency_filter must be one of"):
            provider._validate_search_recency_filter("invalid")

    def test_validate_search_mode_valid(self, provider):
        """Test search mode validation with valid values."""
        valid_modes = ["web", "high", "medium", "low"]
        for mode in valid_modes:
            provider._validate_search_mode(mode)  # Should not raise

    def test_validate_search_mode_invalid(self, provider):
        """Test search mode validation with invalid values."""
        with pytest.raises(ValueError, match="search_mode must be one of"):
            provider._validate_search_mode("invalid")

    def test_validate_date_filter_valid(self, provider):
        """Test date filter validation with valid dates."""
        valid_dates = ["2025-01-01", "2025-12-31", "2024-02-29"]  # Leap year
        for date in valid_dates:
            provider._validate_date_filter(date)  # Should not raise

    def test_validate_date_filter_invalid_format(self, provider):
        """Test date filter validation with invalid formats."""
        invalid_formats = ["2025-1-1", "25-01-01", "2025/01/01", "invalid"]
        for invalid_date in invalid_formats:
            with pytest.raises(ValueError, match="Date filter must be in YYYY-MM-DD format"):
                provider._validate_date_filter(invalid_date)

    def test_validate_date_filter_invalid_date(self, provider):
        """Test date filter validation with invalid dates."""
        invalid_dates = ["2025-13-01", "2025-02-30", "2023-02-29"]  # Not leap year
        for invalid_date in invalid_dates:
            with pytest.raises(ValueError, match="Invalid date"):
                provider._validate_date_filter(invalid_date)

    def test_resolve_model_name_aliases(self, provider):
        """Test model name alias resolution."""
        alias_tests = [
            ("perplexity", "sonar"),
            ("perplexity-pro", "sonar-pro"),
            ("perplexity-reasoning", "sonar-reasoning"),
            ("perplexity-reasoning-pro", "sonar-reasoning-pro"),
            ("deep-research", "sonar-deep-research"),
            ("r1", "r1-1776"),
        ]

        for alias, expected in alias_tests:
            assert provider._resolve_model_name(alias) == expected

    def test_calculate_perplexity_cost(self, provider):
        """Test cost calculation with official Perplexity pricing."""
        usage_data = {"prompt_tokens": 1000, "completion_tokens": 500, "citation_tokens": 100, "reasoning_tokens": 200}

        # Test sonar model cost
        cost = provider._calculate_perplexity_cost(usage_data, "sonar")
        assert cost["currency"] == "USD"
        assert cost["prompt_cost"] == 0.001  # 1000 tokens * $0.001/1M
        assert cost["completion_cost"] == 0.0005  # 500 tokens * $0.001/1M
        assert cost["citation_cost"] == 0.0  # Not charged for sonar
        assert cost["reasoning_cost"] == 0.0  # Not charged for sonar

        # Test sonar-deep-research model cost (has citation/reasoning charges)
        cost_deep = provider._calculate_perplexity_cost(usage_data, "sonar-deep-research")
        assert cost_deep["citation_cost"] == 0.0002  # 100 tokens * $0.002/1M
        assert cost_deep["reasoning_cost"] == 0.0006  # 200 tokens * $0.003/1M
