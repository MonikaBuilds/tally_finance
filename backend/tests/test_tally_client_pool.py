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

@pytest.mark.asyncio
async def test_read_only_export_retries_one_dropped_connection(monkeypatch):
    import httpx
    from unittest.mock import AsyncMock
    from app.tally.xml_builders import build_company_request
    response=httpx.Response(200, text="<ENVELOPE/>", request=httpx.Request("POST","http://tally"))
    shared=AsyncMock()
    shared.post.side_effect=[httpx.RemoteProtocolError("Server disconnected without sending a response."),response]
    monkeypatch.setattr(TallyClient,"_shared_client",shared)
    monkeypatch.setattr(TallyClient,"_unavailable_until",0)
    monkeypatch.setattr(TallyClient,"_mark_available",staticmethod(lambda: None))
    assert await TallyClient().send_xml(build_company_request()) == "<ENVELOPE/>"
    assert shared.post.await_count == 2


@pytest.mark.parametrize("request_type,expected_attempts", [("Export",2),("Import",1)])
@pytest.mark.asyncio
async def test_protocol_retry_is_bounded_and_never_retries_import(monkeypatch,request_type,expected_attempts):
    import httpx
    from unittest.mock import AsyncMock
    shared=AsyncMock()
    shared.post.side_effect=httpx.RemoteProtocolError("Server disconnected without sending a response.")
    monkeypatch.setattr(TallyClient,"_shared_client",shared)
    monkeypatch.setattr(TallyClient,"_unavailable_until",0)
    monkeypatch.setattr(TallyClient,"_mark_unavailable",staticmethod(lambda: None))
    with pytest.raises(httpx.RemoteProtocolError):
        await TallyClient().send_xml(f"<ENVELOPE><HEADER><TALLYREQUEST>{request_type}</TALLYREQUEST></HEADER></ENVELOPE>")
    assert shared.post.await_count == expected_attempts
