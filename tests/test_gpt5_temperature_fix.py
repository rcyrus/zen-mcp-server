"""Test GPT-5 temperature constraint fix."""

import unittest
from unittest.mock import Mock, patch

from providers.openai_provider import OpenAIModelProvider


class TestGPT5TemperatureFix(unittest.TestCase):
    """Test that GPT-5 models correctly handle temperature constraints."""

    def setUp(self):
        """Set up test provider."""
        self.provider = OpenAIModelProvider(api_key="test-key")

    def test_gpt5_temperature_constraint(self):
        """Test that GPT-5 only accepts temperature=1."""
        capabilities = self.provider.get_capabilities("gpt-5")

        # Check that temperature constraint is fixed
        self.assertTrue(capabilities.supports_temperature)

        # Test that any temperature gets corrected to 1.0
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(0.5), 1.0)
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(0.0), 1.0)
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(2.0), 1.0)
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(1.0), 1.0)

        # Validate should only return True for 1.0
        self.assertTrue(capabilities.temperature_constraint.validate(1.0))
        self.assertFalse(capabilities.temperature_constraint.validate(0.5))

    def test_gpt5_mini_temperature_constraint(self):
        """Test that GPT-5-mini only accepts temperature=1."""
        capabilities = self.provider.get_capabilities("gpt-5-mini")

        # Check that temperature constraint is fixed
        self.assertTrue(capabilities.supports_temperature)

        # Test that any temperature gets corrected to 1.0
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(0.5), 1.0)
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(1.0), 1.0)

    def test_gpt5_nano_temperature_constraint(self):
        """Test that GPT-5-nano only accepts temperature=1."""
        capabilities = self.provider.get_capabilities("gpt-5-nano")

        # Check that temperature constraint is fixed
        self.assertTrue(capabilities.supports_temperature)

        # Test that any temperature gets corrected to 1.0
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(0.7), 1.0)
        self.assertEqual(capabilities.temperature_constraint.get_corrected_value(1.0), 1.0)

    def test_effective_temperature_for_gpt5(self):
        """Test that get_effective_temperature returns 1.0 for GPT-5 models."""
        # Test GPT-5
        self.assertEqual(self.provider.get_effective_temperature("gpt-5", 0.5), 1.0)
        self.assertEqual(self.provider.get_effective_temperature("gpt-5", 0.0), 1.0)
        self.assertEqual(self.provider.get_effective_temperature("gpt-5", 2.0), 1.0)

        # Test GPT-5-mini
        self.assertEqual(self.provider.get_effective_temperature("gpt-5-mini", 0.5), 1.0)
        self.assertEqual(self.provider.get_effective_temperature("mini", 0.7), 1.0)  # Test alias

        # Test GPT-5-nano
        self.assertEqual(self.provider.get_effective_temperature("gpt-5-nano", 0.3), 1.0)
        self.assertEqual(self.provider.get_effective_temperature("gpt5nano", 0.9), 1.0)  # Test alias

    @patch("providers.openai_compatible.OpenAI")
    def test_api_call_with_corrected_temperature(self, mock_openai_class):
        """Test that API calls use temperature=1.0 for GPT-5."""
        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="test response"))]
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        mock_response.model = "gpt-5"
        mock_client.chat.completions.create.return_value = mock_response

        # Make a call with wrong temperature
        self.provider.generate_content(
            prompt="test",
            model_name="gpt-5",
            temperature=0.5,  # This should be corrected to 1.0
        )

        # Verify the API was called with temperature=1.0
        mock_client.chat.completions.create.assert_called_once()
        call_args = mock_client.chat.completions.create.call_args
        self.assertEqual(call_args.kwargs["temperature"], 1.0)


if __name__ == "__main__":
    unittest.main()
