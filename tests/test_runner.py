"""Tests for TerraformRunner — all mocked, no real Terraform needed."""

import subprocess
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from terrygui.core.terraform_runner import TerraformRunner, CommandResult
from terrygui.security.sanitizer import SecurityError
from terrygui.security.secure_memory import OutputRedactor, SecureString


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tf_dir(tmp_path):
    """Create a temporary directory with a .tf file so path validation passes."""
    tf_file = tmp_path / "main.tf"
    tf_file.write_text('variable "example" {}')
    return str(tmp_path)


@pytest.fixture
def runner(tf_dir):
    """Return a TerraformRunner pointed at a valid temp project dir."""
    with patch("terrygui.core.terraform_runner.InputSanitizer.sanitize_path", return_value=tf_dir):
        return TerraformRunner(project_path=tf_dir)


# ---------------------------------------------------------------------------
# Command construction tests
# ---------------------------------------------------------------------------

class TestBuildBaseCommand:
    def test_build_base_command(self, runner, tf_dir):
        cmd = runner._build_base_command("init")
        assert cmd == ["terraform", f"-chdir={tf_dir}", "init"]

    def test_build_base_command_validate(self, runner, tf_dir):
        cmd = runner._build_base_command("validate")
        assert cmd[2] == "validate"

    def test_build_base_command_plan(self, runner, tf_dir):
        cmd = runner._build_base_command("plan")
        assert cmd[2] == "plan"


class TestAddVariables:
    def test_add_variables(self, runner):
        cmd = []
        runner._add_variables(cmd, {"region": "us-east-1"}, {})
        assert cmd == ["-var", "region=us-east-1"]

    def test_add_multiple_variables(self, runner):
        cmd = []
        runner._add_variables(cmd, {"a": "1", "b": "2"}, {})
        assert "-var" in cmd
        # Two variables → four elements
        assert len(cmd) == 4

    def test_add_variables_validates_names(self, runner):
        cmd = []
        with pytest.raises(SecurityError):
            runner._add_variables(cmd, {"bad name!": "value"}, {})

    def test_add_variables_validates_values(self, runner):
        cmd = []
        with pytest.raises(SecurityError):
            runner._add_variables(cmd, {"name": "val;ue"}, {})

    def test_add_variables_with_types(self, runner):
        cmd = []
        runner._add_variables(cmd, {"enabled": True}, {"enabled": "bool"})
        assert cmd == ["-var", "enabled=true"]


# ---------------------------------------------------------------------------
# Command-structure tests (init / validate / plan)
# ---------------------------------------------------------------------------

class TestInitCommand:
    def test_init_command_structure(self, runner, tf_dir):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "init")) as mock_exec:
            runner.init()
            cmd = mock_exec.call_args[0][0]
            assert cmd[0] == "terraform"
            assert f"-chdir={tf_dir}" in cmd
            assert "init" in cmd
            assert "-input=false" in cmd
            assert "-no-color" in cmd

    def test_init_with_backend_config(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "init")) as mock_exec:
            runner.init(backend_config={"key": "val"})
            cmd = mock_exec.call_args[0][0]
            assert "-backend-config=key=val" in cmd


class TestValidateCommand:
    def test_validate_command_structure(self, runner, tf_dir):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "validate")) as mock_exec:
            runner.validate()
            cmd = mock_exec.call_args[0][0]
            assert "validate" in cmd
            assert "-no-color" in cmd


class TestPlanCommand:
    def test_plan_command_structure(self, runner, tf_dir):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "plan")) as mock_exec:
            runner.plan(variables={"region": "us-east-1"})
            cmd = mock_exec.call_args[0][0]
            assert "plan" in cmd
            assert "-input=false" in cmd
            assert "-no-color" in cmd
            assert "-var" in cmd
            assert "region=us-east-1" in cmd

    def test_plan_with_out_file(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "plan")) as mock_exec:
            runner.plan(out_file="tfplan")
            cmd = mock_exec.call_args[0][0]
            assert "-out=tfplan" in cmd

    def test_plan_no_variables(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "plan")) as mock_exec:
            runner.plan()
            cmd = mock_exec.call_args[0][0]
            assert "-var" not in cmd


class TestApplyCommand:
    def test_apply_command_structure(self, runner, tf_dir):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "apply")) as mock_exec:
            runner.apply(variables={"region": "us-east-1"})
            cmd = mock_exec.call_args[0][0]
            assert "apply" in cmd
            assert "-input=false" in cmd
            assert "-no-color" in cmd
            assert "-var" in cmd
            assert "region=us-east-1" in cmd

    def test_apply_auto_approve(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "apply")) as mock_exec:
            runner.apply(auto_approve=True)
            cmd = mock_exec.call_args[0][0]
            assert "-auto-approve" in cmd

    def test_apply_no_auto_approve(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "apply")) as mock_exec:
            runner.apply()
            cmd = mock_exec.call_args[0][0]
            assert "-auto-approve" not in cmd


class TestDestroyCommand:
    def test_destroy_command_structure(self, runner, tf_dir):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "destroy")) as mock_exec:
            runner.destroy(variables={"region": "us-east-1"})
            cmd = mock_exec.call_args[0][0]
            assert "destroy" in cmd
            assert "-input=false" in cmd
            assert "-no-color" in cmd
            assert "-var" in cmd

    def test_destroy_auto_approve(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "destroy")) as mock_exec:
            runner.destroy(auto_approve=True)
            cmd = mock_exec.call_args[0][0]
            assert "-auto-approve" in cmd

    def test_destroy_no_variables(self, runner):
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "destroy")) as mock_exec:
            runner.destroy()
            cmd = mock_exec.call_args[0][0]
            assert "-var" not in cmd


# ---------------------------------------------------------------------------
# Execution tests (mocked subprocess)
# ---------------------------------------------------------------------------

def _make_mock_popen(stdout_lines, stderr_lines="", returncode=0):
    """Create a mock Popen that yields the given lines."""
    mock_proc = MagicMock()
    mock_proc.stdout = iter([line + "\n" for line in stdout_lines])
    mock_proc.stderr = iter([line + "\n" for line in stderr_lines] if isinstance(stderr_lines, list) else [])
    mock_proc.returncode = returncode
    mock_proc.wait = MagicMock(return_value=returncode)
    mock_proc.terminate = MagicMock()
    return mock_proc


class TestExecute:
    def test_execute_captures_output(self, runner):
        mock_proc = _make_mock_popen(["line1", "line2"])
        with patch("subprocess.Popen", return_value=mock_proc):
            result = runner._execute(["terraform", "init"], "init")
        assert result.success is True
        assert result.exit_code == 0
        assert "line1" in result.stdout
        assert "line2" in result.stdout
        assert result.command == "init"

    def test_execute_streams_output(self, runner):
        mock_proc = _make_mock_popen(["alpha", "beta"])
        callback_lines = []
        with patch("subprocess.Popen", return_value=mock_proc):
            runner._execute(["terraform", "init"], "init", output_callback=callback_lines.append)
        assert "alpha" in callback_lines
        assert "beta" in callback_lines

    def test_execute_redacts_sensitive(self, runner):
        redactor = OutputRedactor({"secret": SecureString("SUPERSECRET")})
        runner.set_redactor(redactor)
        mock_proc = _make_mock_popen(["token is SUPERSECRET here"])
        with patch("subprocess.Popen", return_value=mock_proc):
            result = runner._execute(["terraform", "init"], "init")
        assert "SUPERSECRET" not in result.stdout
        assert "[REDACTED]" in result.stdout

    def test_execute_failure_exit_code(self, runner):
        mock_proc = _make_mock_popen([], stderr_lines=["Error: something"], returncode=1)
        mock_proc.returncode = 1
        with patch("subprocess.Popen", return_value=mock_proc):
            result = runner._execute(["terraform", "plan"], "plan")
        assert result.success is False
        assert result.exit_code == 1

    def test_execute_timeout(self, runner):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.stderr = iter([])
        mock_proc.wait = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="tf", timeout=300))
        mock_proc.terminate = MagicMock()
        with patch("subprocess.Popen", return_value=mock_proc):
            result = runner._execute(["terraform", "init"], "init")
        assert result.success is False
        assert result.exit_code == -1
        assert "timed out" in result.stderr.lower()


class TestCancel:
    def test_cancel_terminates_process(self, runner):
        mock_proc = MagicMock()
        runner._process = mock_proc
        runner.cancel()
        mock_proc.terminate.assert_called_once()

    def test_cancel_no_process(self, runner):
        # Should not raise
        runner.cancel()


# ---------------------------------------------------------------------------
# Security validation tests
# ---------------------------------------------------------------------------

class TestSecurityValidation:
    def test_rejects_invalid_project_path(self, tmp_path):
        """sanitize_path raises SecurityError for non-existent paths."""
        with pytest.raises(SecurityError):
            TerraformRunner(project_path="/nonexistent/path/xyz")

    def test_rejects_unsafe_out_file(self, runner):
        bad_path = "\x00bad"
        with patch.object(runner, "_execute", return_value=CommandResult(0, "", "", True, "plan")):
            with pytest.raises(SecurityError):
                runner.plan(out_file=bad_path)
