import asyncio

import pytest

from app.chatbot import executor


@pytest.mark.asyncio
async def test_tool_concurrency_is_bounded(
    monkeypatch,
):
    active_calls = 0
    maximum_active_calls = 0

    async def fake_tool():
        nonlocal active_calls
        nonlocal maximum_active_calls

        active_calls += 1

        maximum_active_calls = max(
            maximum_active_calls,
            active_calls,
        )

        await asyncio.sleep(0.05)

        active_calls -= 1

        return {
            "success": True,
            "source": "test",
            "message": "ok",
            "data": {},
        }

    monkeypatch.setitem(
        executor.TOOL_FUNCTIONS,
        "test_concurrent_tool",
        fake_tool,
    )

    # This test verifies concurrency only.
    # Permission behavior is tested separately.
    monkeypatch.setattr(
        executor,
        "can_execute_tool",
        lambda user_id, tool_name: True,
    )

    # Use a small limit so the test is easy
    # and fast to verify.
    test_limit = 2

    monkeypatch.setattr(
        executor,
        "_tool_semaphore",
        asyncio.Semaphore(test_limit),
    )

    results = await asyncio.gather(
        *[
            executor.execute_tool(
                "test_concurrent_tool",
                user_id="test-user",
            )
            for _ in range(6)
        ]
    )

    assert all(
        result["success"]
        for result in results
    )

    assert maximum_active_calls <= test_limit