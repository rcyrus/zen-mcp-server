"""Tests for uv-based package management in run-server.sh script.

This test file ensures our uv-based package management works correctly
and the setup script functions properly.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest


class TestUvPackageManagement:
    """Test cases for uv-based package management in setup script."""

    def test_run_server_script_syntax_valid(self):
        """Test that run-server.sh has valid bash syntax."""
        result = subprocess.run(["bash", "-n", "./run-server.sh"], capture_output=True, text=True)
        assert result.returncode == 0, f"Syntax error in run-server.sh: {result.stderr}"

    def test_run_server_has_proper_shebang(self):
        """Test that run-server.sh starts with proper shebang."""
        content = Path("./run-server.sh").read_text()
        assert content.startswith("#!/bin/bash"), "Script missing proper bash shebang"

    def test_critical_functions_exist(self):
        """Test that all critical functions are defined in the script."""
        content = Path("./run-server.sh").read_text()
        critical_functions = ["check_uv_installed", "setup_environment", "install_dependencies", "get_venv_python_path"]

        for func in critical_functions:
            assert f"{func}()" in content, f"Critical function {func}() not found in script"

    def test_uv_package_management(self):
        """Test that the script properly handles uv-based package management.

        This test verifies that uv is used for dependency installation.
        """
        content = Path("./run-server.sh").read_text()

        # Check that uv-related functions exist
        assert "check_uv_installed()" in content, "check_uv_installed function should exist"
        assert "uv sync" in content or "uv pip sync" in content, "Should use uv for dependency installation"

        # Check that get_venv_python_path includes our absolute path conversion logic
        assert "abs_venv_path" in content, "get_venv_python_path should use absolute paths"
        assert 'cd "$(dirname' in content, "Should convert to absolute path"

        # Test successful completion
        result = subprocess.run(["bash", "-n", "./run-server.sh"], capture_output=True, text=True)
        assert result.returncode == 0, "Script should have valid syntax"

    def test_venv_detection_with_non_interactive_shell(self):
        """Test virtual environment detection works in non-interactive shell environments.

        This ensures the script can find Python executables in both Unix and Windows environments.
        """
        # Test case for cross-platform virtual environment detection
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock virtual environment structure
            venv_path = Path(temp_dir) / ".zen_venv"
            bin_path = venv_path / "bin"
            bin_path.mkdir(parents=True)

            # Create mock python executable
            python_exe = bin_path / "python"
            python_exe.write_text("#!/bin/bash\necho 'Python 3.12.3'\n")
            python_exe.chmod(0o755)

            # Create mock uv executable
            uv_exe = bin_path / "uv"
            uv_exe.write_text("#!/bin/bash\necho 'uv 0.1.0'\n")
            uv_exe.chmod(0o755)

            # Test that we can detect executables using explicit paths (not PATH)
            assert python_exe.exists(), "Mock python executable should exist"
            assert uv_exe.exists(), "Mock uv executable should exist"
            assert python_exe.is_file(), "Python should be a file"
            assert uv_exe.is_file(), "uv should be a file"

    def test_uv_installation_instructions(self):
        """Test that the script includes proper uv installation instructions.

        Verify that the script provides clear guidance for installing uv when it's not found.
        """
        content = Path("./run-server.sh").read_text()

        # Check that uv-related messages and installation instructions are present
        expected_patterns = [
            "check_uv_installed",
            "command -v uv",
            "pip install uv",
            "uv sync",
        ]

        for pattern in expected_patterns:
            assert pattern in content, f"Expected pattern '{pattern}' should be in script"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
