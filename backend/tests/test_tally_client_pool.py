import pytest

from app.tally.client import TallyClient


@pytest.mark.asyncio
async def test_shared_client_start_and_close():
    # Start from a clean state.
    await TallyClient.close_shared_client()

    assert TallyClient._shared_client is None

    await TallyClient.start_shared_client()

    client = TallyClient._shared_client

    assert client is not None
    assert client.is_closed is False

    await TallyClient.close_shared_client()

    assert TallyClient._shared_client is None
    assert client.is_closed is True


@pytest.mark.asyncio
async def test_shared_client_is_reused():
    await TallyClient.close_shared_client()

    await TallyClient.start_shared_client()

    first_client = TallyClient._shared_client

    # Calling startup again should not create
    # another HTTP client.
    await TallyClient.start_shared_client()

    second_client = TallyClient._shared_client

    assert first_client is second_client

    await TallyClient.close_shared_client()