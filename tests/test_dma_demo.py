from app.demo.dma_workflow_demo import run_dma_demo


def test_executable_dma_demo_completes_standard_closed_loop(db_session) -> None:
    result = run_dma_demo(db_session)

    assert result.status_path == (
        "DRAFT",
        "PENDING_DISPATCH",
        "PENDING_CLAIM",
        "PROCESSING",
        "PENDING_REVIEW",
        "COMPLETED",
        "CLOSED",
    )
    assert result.candidate_usernames == ("lisi", "zhaoliu")
    assert result.claimed_by == "lisi"
    assert result.second_claim_conflict is True
    assert result.timeline_actions == (
        "CREATE",
        "SUBMIT",
        "DISPATCH",
        "CLAIM",
        "SUBMIT_RESULT",
        "APPROVE",
        "CLOSE",
    )
    assert result.final_status == "CLOSED"
