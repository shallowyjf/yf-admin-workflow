from pathlib import Path

from scripts.check_sensitive_info import scan_repository, scan_text


def test_sensitive_scanner_detects_high_confidence_credentials() -> None:
    private_key = "-----BEGIN " + "PRIVATE KEY-----"
    github_token = "ghp_" + "a" * 24
    credentialed_url = "postgresql://" + "demo:unsafe@example.test/app"

    findings = scan_text(
        "fixture.txt",
        "\n".join((private_key, github_token, credentialed_url)),
    )

    assert {finding.reason for finding in findings} == {
        "PEM private key",
        "GitHub token",
        "credentialed URL",
    }


def test_repository_has_no_tracked_sensitive_information() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert scan_repository(repo_root) == []
