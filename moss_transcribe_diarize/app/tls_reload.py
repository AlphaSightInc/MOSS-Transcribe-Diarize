"""Reload a prepared certificate on SIGHUP; established connections stay untouched."""
from __future__ import annotations

import asyncio
import logging
import signal
import ssl
from contextlib import contextmanager

from uvicorn.config import create_ssl_context

LOGGER = logging.getLogger("moss_transcribe_diarize.tls")


@contextmanager
def certificate_reload(config):
    """Install in the server event loop after Config.load(), before listening.

The listener retains its original context. Its handshake callback selects the
latest fully loaded context, so a bad key pair never mutates a working context.
Only the Unix service operator sends SIGHUP; no browser control surface exists.
"""
    current = config.ssl
    if not isinstance(current, ssl.SSLContext):
        raise ValueError("TLS must be configured before installing certificate reload")

    def select(connection, _name, _initial):
        connection.context = current

    def reload():
        nonlocal current
        try:
            prepared = create_ssl_context(
                config.ssl_certfile, config.ssl_keyfile, config.ssl_keyfile_password,
                config.ssl_version, config.ssl_cert_reqs, config.ssl_ca_certs, config.ssl_ciphers,
            )
        except (OSError, ssl.SSLError):
            LOGGER.error("tls_certificate_reload_rejected")
            return
        current = prepared
        LOGGER.info("tls_certificate_reloaded")

    current.set_servername_callback(select)
    loop = asyncio.get_running_loop()
    previous = signal.getsignal(signal.SIGHUP)
    loop.add_signal_handler(signal.SIGHUP, reload)
    try:
        yield
    finally:
        loop.remove_signal_handler(signal.SIGHUP)
        signal.signal(signal.SIGHUP, previous)


async def serve_with_certificate_reload(config):
    import uvicorn

    config.load()
    with certificate_reload(config):
        await uvicorn.Server(config).serve()
