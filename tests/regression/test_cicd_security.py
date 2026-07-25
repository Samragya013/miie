"""
Regression tests for CI/CD security hardening.

Verifies GitHub Actions workflows are free from:
- Workflow injection via context interpolation
- pull_request_target misuse
- Unpinned actions (tag instead of SHA)
- Overly broad permissions
- Secret leakage in run blocks
- Self-hosted runner usage
- Unused OIDC permissions
- Artifact downloads without integrity checks
"""
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"


def _load_workflow(name):
    path = WORKFLOWS_DIR / name
    if not path.exists():
        pytest.skip(f"Workflow {name} not found")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CI Workflow Security
# ---------------------------------------------------------------------------
class TestCIWorkflowSecurity:
    """Verify ci.yml has no CI/CD security issues."""

    def test_no_pull_request_target(self):
        content = _load_workflow("ci.yml")
        assert "pull_request_target" not in content

    def test_no_self_hosted_runners(self):
        content = _load_workflow("ci.yml")
        assert "self-hosted" not in content

    def test_explicit_permissions_block(self):
        content = _load_workflow("ci.yml")
        assert "permissions:" in content, "ci.yml must have explicit permissions block"

    def test_permissions_are_read_only(self):
        content = _load_workflow("ci.yml")
        # Find permissions block
        m = re.search(r"permissions:(.*?)(?=\n\S|\Z)", content, re.DOTALL)
        assert m, "No permissions block found"
        perms = m.group(1)
        assert "contents: read" in perms or "contents: write" not in perms
        # Should NOT have write permissions
        assert "write" not in perms, f"ci.yml has write permissions: {perms}"

    def test_all_actions_sha_pinned(self):
        content = _load_workflow("ci.yml")
        for i, line in enumerate(content.split("\n"), 1):
            m = re.search(r"uses:\s+(\S+)@(\S+)", line)
            if m:
                action, ref = m.groups()
                # SHA is 40 hex chars
                assert re.match(r"^[a-f0-9]{40}$", ref), \
                    f"Unpinned action at line {i}: {action}@{ref}"

    def test_no_workflow_injection(self):
        """Context variables should not appear in run: blocks."""
        content = _load_workflow("ci.yml")
        lines = content.split("\n")
        in_run = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("run:"):
                in_run = True
            elif in_run and stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                in_run = False
            if in_run:
                assert "github.event." not in stripped, \
                    f"Workflow injection risk at line {i}: {stripped}"
                assert "github.head_ref" not in stripped, \
                    f"Workflow injection risk at line {i}: {stripped}"

    def test_no_secrets_in_run_blocks(self):
        """Secrets should not be echoed or printed in run blocks."""
        content = _load_workflow("ci.yml")
        lines = content.split("\n")
        in_run = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("run:"):
                in_run = True
            elif in_run and stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                in_run = False
            if in_run:
                if "secrets." in stripped:
                    assert "echo" not in stripped and "print" not in stripped, \
                        f"Secret potentially logged at line {i}: {stripped}"

    def test_no_oidc_permission(self):
        content = _load_workflow("ci.yml")
        assert "id-token: write" not in content

    def test_no_workflow_dispatch(self):
        """CI workflow should not have workflow_dispatch (manual trigger risk)."""
        content = _load_workflow("ci.yml")
        assert "workflow_dispatch" not in content


# ---------------------------------------------------------------------------
# Release Workflow Security
# ---------------------------------------------------------------------------
class TestReleaseWorkflowSecurity:
    """Verify release.yml has no CI/CD security issues."""

    def test_no_pull_request_target(self):
        content = _load_workflow("release.yml")
        assert "pull_request_target" not in content

    def test_no_self_hosted_runners(self):
        content = _load_workflow("release.yml")
        assert "self-hosted" not in content

    def test_explicit_permissions_block(self):
        content = _load_workflow("release.yml")
        assert "permissions:" in content

    def test_no_unused_oidc_permission(self):
        """id-token: write should only be present if OIDC is configured."""
        content = _load_workflow("release.yml")
        has_oidc_provider = (
            "configure-aws-credentials" in content or
            "google-github-actions" in content or
            "azure/login" in content
        )
        if "id-token: write" in content:
            assert has_oidc_provider, \
                "id-token: write declared but no OIDC provider configured"

    def test_all_actions_sha_pinned(self):
        content = _load_workflow("release.yml")
        for i, line in enumerate(content.split("\n"), 1):
            m = re.search(r"uses:\s+(\S+)@(\S+)", line)
            if m:
                action, ref = m.groups()
                assert re.match(r"^[a-f0-9]{40}$", ref), \
                    f"Unpinned action at line {i}: {action}@{ref}"

    def test_no_workflow_injection(self):
        content = _load_workflow("release.yml")
        lines = content.split("\n")
        in_run = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("run:"):
                in_run = True
            elif in_run and stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                in_run = False
            if in_run:
                assert "github.event." not in stripped, \
                    f"Workflow injection risk at line {i}: {stripped}"
                assert "github.head_ref" not in stripped, \
                    f"Workflow injection risk at line {i}: {stripped}"

    def test_secret_only_in_env_not_logged(self):
        """Secrets should be passed as env/parameters, not echoed."""
        content = _load_workflow("release.yml")
        lines = content.split("\n")
        in_run = False
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("run:"):
                in_run = True
            elif in_run and stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                in_run = False
            if in_run and "secrets." in stripped:
                assert "echo" not in stripped and "print" not in stripped, \
                    f"Secret potentially logged at line {i}: {stripped}"

    def test_artifact_integrity_check(self):
        """Artifact downloads should have integrity verification."""
        content = _load_workflow("release.yml")
        if "download-artifact" in content:
            # Should have sha256sum or similar verification after download
            assert "sha256" in content.lower() or "checksum" in content.lower() or "verify" in content.lower(), \
                "Artifact download without integrity check"

    def test_no_workflow_dispatch(self):
        content = _load_workflow("release.yml")
        assert "workflow_dispatch" not in content

    def test_release_trigger_is_tag_only(self):
        """Release should only trigger on version tags, not PRs."""
        content = _load_workflow("release.yml")
        assert "pull_request" not in content
        assert "push:" in content
        assert "tags:" in content


# ---------------------------------------------------------------------------
# Cross-workflow checks
# ---------------------------------------------------------------------------
class TestCrossWorkflowSecurity:
    """Verify security properties across all workflows."""

    def test_no_workflow_uses_both_pr_and_self_hosted(self):
        """No workflow should combine PR triggers with self-hosted runners."""
        for wf_file in WORKFLOWS_DIR.glob("*.yml"):
            content = wf_file.read_text(encoding="utf-8")
            if "pull_request" in content:
                assert "self-hosted" not in content, \
                    f"{wf_file.name}: combines pull_request with self-hosted runner"

    def test_all_workflows_have_permissions(self):
        """Every workflow should have an explicit permissions block."""
        for wf_file in WORKFLOWS_DIR.glob("*.yml"):
            content = wf_file.read_text(encoding="utf-8")
            assert "permissions:" in content, \
                f"{wf_file.name}: missing explicit permissions block"

    def test_no_eval_in_run_blocks(self):
        """No workflow should use eval in run blocks."""
        for wf_file in WORKFLOWS_DIR.glob("*.yml"):
            content = wf_file.read_text(encoding="utf-8")
            lines = content.split("\n")
            in_run = False
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("run:"):
                    in_run = True
                elif in_run and stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                    in_run = False
                if in_run and "eval " in stripped:
                    pytest.fail(f"{wf_file.name}:{i}: eval in run block: {stripped}")

    def test_no_curl_pipe_to_shell(self):
        """No workflow should pipe curl output to shell."""
        for wf_file in WORKFLOWS_DIR.glob("*.yml"):
            content = wf_file.read_text(encoding="utf-8")
            assert "curl | bash" not in content and "curl | sh" not in content, \
                f"{wf_file.name}: curl piped to shell"
