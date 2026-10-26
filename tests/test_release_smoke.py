from app.demo.release_smoke import run_release_smoke


def test_empty_database_configures_iam_and_closes_dma(tmp_path) -> None:
    database_path = tmp_path / "release.db"

    result = run_release_smoke(f"sqlite:///{database_path.as_posix()}")

    assert result.migration_revision == "head"
    assert result.table_count == 41
    assert result.configured_username == "release.smoke"
    assert result.configured_permission == "acceptance:view"
    assert result.authorization_effective is True
    assert result.audited_entities == ("PERMISSION", "ROLE", "USER")
    assert result.lifeline_systems == 6
    assert result.data_spaces == 6
    assert result.data_resources == 10
    assert result.gis_fields == 15
    assert result.gis_features == 9
    assert result.lifeline_projects == 6
    assert result.dma_final_status == "CLOSED"
    assert result.dma_timeline == (
        "CREATE",
        "SUBMIT",
        "DISPATCH",
        "CLAIM",
        "SUBMIT_RESULT",
        "APPROVE",
        "CLOSE",
    )
