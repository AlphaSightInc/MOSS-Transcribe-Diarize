"""Real TLS sockets exercise production rotation in an isolated process."""
import asyncio
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import tempfile
from pathlib import Path

import uvicorn
from moss_transcribe_diarize.app.tls_reload import certificate_reload


async def run(root):
    for serial in (1, 2):
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", f"/CN=localhost-{serial}", "-addext", "subjectAltName=DNS:localhost", "-set_serial", str(serial),
            "-keyout", str(root / f"{serial}.key"), "-out", str(root / f"{serial}.crt")], check=True, capture_output=True)
    def publish(serial):
        for suffix in ("crt", "key"): shutil.copyfile(root / f"{serial}.{suffix}", root / f"live.{suffix}")
    publish(1)
    trust = ssl.create_default_context(cadata=(root / "1.crt").read_text() + (root / "2.crt").read_text())
    held = asyncio.Event(); release = asyncio.Event()
    async def app(scope, receive, send):
        if scope["path"] == "/hold": held.set(); await release.wait()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-length", b"2")]})
        await send({"type": "http.response.body", "body": b"ok"})
    listener = socket.socket(); listener.bind(("127.0.0.1", 0))
    config = uvicorn.Config(app, lifespan="off", log_level="error", ssl_certfile=str(root / "live.crt"), ssl_keyfile=str(root / "live.key"))
    config.load(); reload_context = certificate_reload(config); reload_context.__enter__()
    server = uvicorn.Server(config); task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started: await asyncio.sleep(.01)
    async def connection():
        reader, writer = await asyncio.open_connection("127.0.0.1", listener.getsockname()[1], ssl=trust, server_hostname="localhost")
        return reader, writer, writer.get_extra_info("ssl_object").getpeercert()["serialNumber"]
    reader, writer, first = await connection()
    writer.write(b"GET /hold HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"); await writer.drain(); await held.wait()
    publish(2); os.kill(os.getpid(), signal.SIGHUP); await asyncio.sleep(.05)
    _, second_writer, second = await connection(); second_writer.close(); await second_writer.wait_closed()
    shutil.copyfile(root / "1.key", root / "live.key")
    os.kill(os.getpid(), signal.SIGHUP); await asyncio.sleep(.05)
    _, third_writer, third = await connection(); third_writer.close(); await third_writer.wait_closed()
    release.set(); response = await reader.read(); writer.close(); await writer.wait_closed()
    server.should_exit = True; await task
    reload_context.__exit__(None, None, None)
    result = {"pid": os.getpid(), "initial_serial": first, "renewed_serial": second, "after_invalid_serial": third,
              "held_request_survived": response.endswith(b"ok"), "same_listener": True}
    print(json.dumps(result)); assert (first, second, third) == ("01", "02", "02") and result["held_request_survived"]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-tls-probe-") as temporary:
        asyncio.run(run(Path(temporary)))
