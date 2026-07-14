"""Tests for Git reference parsing, models, and credential resolution."""

from pathlib import Path

import pytest

from skills_mcp.infrastructure.persistence.git_models import (
    DEFAULT_GIT_USERNAME,
    GitAuthConfig,
    GitRepositoryConfig,
    GitSkillReference,
    resolve_git_credentials,
)


class TestGitSkillReferenceParsingHappyPaths:
    """Valid ``git://`` reference strings parse into the right components."""

    def test_bare_reference(self) -> None:
        """A bare host/owner/repo has no ref or subdir."""
        ref = GitSkillReference.from_string("git://github.com/stacklok/skills")
        assert ref.host == "github.com"
        assert ref.owner == "stacklok"
        assert ref.repo == "skills"
        assert ref.ref is None
        assert ref.subdir is None
        assert ref.url_override is None

    def test_branch_ref(self) -> None:
        """An @branch is captured as the ref."""
        ref = GitSkillReference.from_string("git://github.com/stacklok/skills@main")
        assert ref.ref == "main"
        assert ref.ref_kind == "branch"

    def test_tag_ref(self) -> None:
        """A version-shaped @tag classifies as a tag advisorily."""
        ref = GitSkillReference.from_string("git://github.com/stacklok/skills@v1.2.3")
        assert ref.ref == "v1.2.3"
        assert ref.ref_kind == "tag"

    def test_commit_sha_ref(self) -> None:
        """A 40-hex @sha classifies as a commit and exposes pinned_sha."""
        sha = "a" * 40
        ref = GitSkillReference.from_string(f"git://github.com/stacklok/skills@{sha}")
        assert ref.ref == sha
        assert ref.ref_kind == "commit"
        assert ref.pinned_sha == sha

    def test_commit_sha_is_lowercased_in_pin(self) -> None:
        """pinned_sha lowercases a mixed-case SHA."""
        sha = "ABCDEF0123456789" + "0" * 24
        ref = GitSkillReference.from_string(f"git://github.com/o/r@{sha}")
        assert ref.pinned_sha == sha.lower()

    def test_subdir(self) -> None:
        """A #subdir is captured and normalized."""
        ref = GitSkillReference.from_string(
            "git://github.com/stacklok/skills#skills/analysis"
        )
        assert ref.subdir == "skills/analysis"
        assert ref.ref is None

    def test_ref_and_subdir(self) -> None:
        """@ref#subdir captures both."""
        ref = GitSkillReference.from_string(
            "git://github.com/stacklok/skills@main#analysis"
        )
        assert ref.ref == "main"
        assert ref.subdir == "analysis"

    def test_host_with_port(self) -> None:
        """A host:port authority is preserved."""
        ref = GitSkillReference.from_string("git://git.example.com:8443/team/repo")
        assert ref.host == "git.example.com:8443"
        assert ref.owner == "team"
        assert ref.repo == "repo"

    def test_nested_owner_path(self) -> None:
        """A nested owner path is joined into owner."""
        ref = GitSkillReference.from_string("git://gitlab.com/group/subgroup/repo@v1.0")
        assert ref.owner == "group/subgroup"
        assert ref.repo == "repo"

    def test_git_suffix_stripped(self) -> None:
        """A trailing .git on the repo is stripped."""
        ref = GitSkillReference.from_string("git://github.com/stacklok/skills.git")
        assert ref.repo == "skills"

    def test_https_url(self) -> None:
        """https_url embeds no credentials."""
        ref = GitSkillReference.from_string("git://github.com/stacklok/skills@v1")
        assert ref.https_url == "https://github.com/stacklok/skills.git"

    def test_full_ref_roundtrip(self) -> None:
        """full_ref reconstructs the canonical string."""
        ref = GitSkillReference.from_string(
            "git://github.com/stacklok/skills@main#analysis"
        )
        assert ref.full_ref == "git://github.com/stacklok/skills@main#analysis"

    def test_default_ref_kind(self) -> None:
        """No ref classifies as default."""
        ref = GitSkillReference.from_string("git://github.com/o/r")
        assert ref.ref_kind == "default"
        assert ref.pinned_sha is None


class TestGitSkillReferenceAdversarial:
    """Malformed and hostile references are rejected at parse time."""

    def test_empty(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            GitSkillReference.from_string("")

    def test_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            GitSkillReference.from_string("   ")

    def test_missing_owner_repo(self) -> None:
        with pytest.raises(ValueError, match="owner and repo"):
            GitSkillReference.from_string("git://github.com/onlyrepo")

    def test_missing_repo_only_host(self) -> None:
        with pytest.raises(ValueError, match="owner and repo"):
            GitSkillReference.from_string("git://github.com")

    def test_empty_path_segment(self) -> None:
        with pytest.raises(ValueError, match="empty path segment"):
            GitSkillReference.from_string("git://github.com/owner//repo")

    @pytest.mark.parametrize(
        "scheme_ref",
        [
            "https://github.com/o/r",
            "http://github.com/o/r",
            "file:///etc/passwd",
            "ssh://git@github.com/o/r",
            "git@github.com:o/r",
            "/etc/passwd",
        ],
    )
    def test_non_git_scheme(self, scheme_ref: str) -> None:
        with pytest.raises(ValueError, match="scheme"):
            GitSkillReference.from_string(scheme_ref)

    def test_userinfo_rejected(self) -> None:
        with pytest.raises(ValueError, match="userinfo"):
            GitSkillReference.from_string("git://user@github.com/o/r")

    def test_userinfo_with_password_rejected(self) -> None:
        with pytest.raises(ValueError, match="userinfo"):
            GitSkillReference.from_string("git://user:pass@github.com/o/r")

    @pytest.mark.parametrize(
        "bad_subdir",
        [
            "git://github.com/o/r#/absolute",
            "git://github.com/o/r#../escape",
            "git://github.com/o/r#a/../../b",
            r"git://github.com/o/r#a\b",
        ],
    )
    def test_bad_subdir(self, bad_subdir: str) -> None:
        with pytest.raises(ValueError):
            GitSkillReference.from_string(bad_subdir)

    @pytest.mark.parametrize(
        "bad_ref",
        [
            "git://github.com/o/r@-badstart",
            "git://github.com/o/r@bad..dots",
            "git://github.com/o/r@bad.lock",
            "git://github.com/o/r@bad;rm",
            "git://github.com/o/r@$(whoami)",
            "git://github.com/o/r@a|b",
            "git://github.com/o/r@a`b`",
            "git://github.com/o/r@a b",
        ],
    )
    def test_bad_ref(self, bad_ref: str) -> None:
        with pytest.raises(ValueError):
            GitSkillReference.from_string(bad_ref)

    @pytest.mark.parametrize(
        "ip_host",
        [
            "git://127.0.0.1/o/r",
            "git://10.0.0.1/o/r",
            "git://169.254.1.1/o/r",
            "git://192.168.1.1/o/r",
            "git://0.0.0.0/o/r",
            "git://[::1]/o/r",
            "git://[fe80::1]/o/r",
            "git://127.0.0.1:8080/o/r",
        ],
    )
    def test_private_ip_hosts_rejected(self, ip_host: str) -> None:
        with pytest.raises(ValueError, match="disallowed IP"):
            GitSkillReference.from_string(ip_host)

    def test_public_ip_host_allowed(self) -> None:
        """A public IP literal parses (DNS-less); repo-level checks still apply."""
        ref = GitSkillReference.from_string("git://8.8.8.8/o/r")
        assert ref.host == "8.8.8.8"


class TestRefKindClassification:
    """ref_kind is advisory only."""

    def test_short_hex_is_branch_not_commit(self) -> None:
        """A hex string shorter than 40 chars is not a commit pin."""
        ref = GitSkillReference.from_string("git://github.com/o/r@abc123")
        assert ref.ref_kind == "branch"
        assert ref.pinned_sha is None


class TestGitAuthConfig:
    """GitAuthConfig anonymity."""

    def test_anonymous_when_empty(self) -> None:
        assert GitAuthConfig(host="github.com").is_anonymous is True

    def test_not_anonymous_with_password(self) -> None:
        cfg = GitAuthConfig(host="github.com", password="tok")  # noqa: S106
        assert cfg.is_anonymous is False


class TestGitRepositoryConfig:
    """GitRepositoryConfig defaults."""

    def test_defaults(self) -> None:
        cfg = GitRepositoryConfig()
        assert cfg.skills == []
        assert cfg.auth == {}
        assert cfg.cache_dir is None
        assert cfg.allow_private_hosts is False
        assert cfg.clone_timeout == 120

    def test_default_cache_dir(self) -> None:
        assert GitRepositoryConfig.default_cache_dir() == (
            Path.home() / ".cache" / "skills-mcp" / "git"
        )


class TestResolveGitCredentials:
    """Credential precedence matrix (config beats env; token scoping)."""

    def test_none_when_no_config_and_no_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("GITHUB_TOKEN", "GITLAB_TOKEN", "GIT_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        assert resolve_git_credentials("github.com", {}) is None

    def test_config_beats_github_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        auth = {"github.com": GitAuthConfig(host="github.com", password="cfg-token")}  # noqa: S106
        creds = resolve_git_credentials("github.com", auth)
        assert creds == (DEFAULT_GIT_USERNAME, "cfg-token")

    def test_config_username_preserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("GITHUB_TOKEN", "GITLAB_TOKEN", "GIT_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        auth = {
            "github.com": GitAuthConfig(
                host="github.com",
                username="alice",
                password="cfg-token",  # noqa: S106
            )
        }
        creds = resolve_git_credentials("github.com", auth)
        assert creds == ("alice", "cfg-token")

    def test_github_token_only_github(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("GITLAB_TOKEN", "GIT_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "gh")
        assert resolve_git_credentials("github.com", {}) == (DEFAULT_GIT_USERNAME, "gh")
        # Does not apply to other hosts.
        assert resolve_git_credentials("example.com", {}) is None

    def test_gitlab_token_only_gitlab(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("GITHUB_TOKEN", "GIT_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("GITLAB_TOKEN", "gl")
        assert resolve_git_credentials("gitlab.com", {}) == (DEFAULT_GIT_USERNAME, "gl")
        assert resolve_git_credentials("github.com", {}) is None

    def test_git_token_any_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for var in ("GITHUB_TOKEN", "GITLAB_TOKEN"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("GIT_TOKEN", "any")
        assert resolve_git_credentials("example.com", {}) == (
            DEFAULT_GIT_USERNAME,
            "any",
        )
        # And also covers github when GITHUB_TOKEN is unset.
        assert resolve_git_credentials("github.com", {}) == (
            DEFAULT_GIT_USERNAME,
            "any",
        )

    def test_github_token_preferred_over_git_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "gh")
        monkeypatch.setenv("GIT_TOKEN", "any")
        assert resolve_git_credentials("github.com", {}) == (DEFAULT_GIT_USERNAME, "gh")
