"""
Error classification for Tally connectivity vs business/parser errors.
Only genuine infrastructure and network failures are eligible for stale cache fallback.
"""

import asyncio
import socket
import httpx


def is_tally_connectivity_error(exc: BaseException) -> bool:
    """
    Determine if an exception is a genuine Tally connectivity/infrastructure failure
    (connection refused, timeout, network failure, host unreachable).

    Business errors (e.g. LINEERROR, STATUS 0), parser errors (ValueError, ParseError),
    task cancellation, and HTTP protocol errors are NOT connectivity errors.
    """
    # Cancellation must NEVER be suppressed or treated as connectivity error
    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
        return False

    # HTTPX network and timeout exceptions
    if isinstance(exc, (
        httpx.ConnectError,
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    )):
        return True

    # Standard library socket/connection errors
    if isinstance(exc, (
        ConnectionRefusedError,
        ConnectionResetError,
        ConnectionAbortedError,
        TimeoutError,
        socket.timeout,
        socket.gaierror,
    )):
        return True

    # Generic OSError with network failure codes (e.g. Windows Winsock errors)
    if isinstance(exc, OSError) and not isinstance(exc, (FileNotFoundError, PermissionError)):
        # WinError 10061 (WSAECONNREFUSED), 10060 (WSAETIMEDOUT), 10065 (WSAEHOSTUNREACH), 10051 (WSAENETUNREACH)
        winerror = getattr(exc, "winerror", None)
        if winerror in (10060, 10061, 10064, 10065, 10051, 10053, 10054):
            return True
        # Generic message check for socket/connection failure
        err_msg = str(exc).lower()
        if any(term in err_msg for term in (
            "actively refused",
            "timed out",
            "failed to establish a new connection",
            "network is unreachable",
            "host is unreachable",
        )):
            return True

    return False
