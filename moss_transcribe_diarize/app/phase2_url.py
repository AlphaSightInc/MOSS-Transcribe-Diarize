"""Bounded HTTP(S) media acquisition for owner-bound File Meetings."""

from __future__ import annotations

import asyncio
import mimetypes
import os
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


MAX_URL_BYTES = 2 * 1024 * 1024 * 1024
URL_ACQUISITION_TIMEOUT_SECONDS = 3_900.0
URL_NETWORK_TIMEOUT_SECONDS = 30.0
URL_MAX_REDIRECTS = 5
YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"})
HTTP_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class UrlAcquisitionRejected(ValueError):
    """A content-free rejection safe to translate into a failed Meeting."""


def validate_http_url(source_url: str) -> str:
    value = source_url.strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UrlAcquisitionRejected("Only HTTP(S) media URLs are accepted.")
    return value


class UrlMediaAcquirer:
    """Acquire one bounded media source without creating any durable authority."""

    def __init__(
        self,
        *,
        max_bytes: int = MAX_URL_BYTES,
        total_timeout_seconds: float = URL_ACQUISITION_TIMEOUT_SECONDS,
        network_timeout_seconds: float = URL_NETWORK_TIMEOUT_SECONDS,
        max_redirects: int = URL_MAX_REDIRECTS,
        http_transport: Any | None = None,
        yt_dlp_command: Sequence[str] | None = None,
    ) -> None:
        if max_bytes <= 0 or total_timeout_seconds <= 0 or network_timeout_seconds <= 0:
            raise ValueError("URL acquisition bounds must be positive.")
        if max_redirects < 0:
            raise ValueError("URL redirect bound must be non-negative.")
        self._max_bytes = max_bytes
        self._total_timeout_seconds = total_timeout_seconds
        self._network_timeout_seconds = network_timeout_seconds
        self._max_redirects = max_redirects
        self._http_transport = http_transport
        self._yt_dlp_command = tuple(yt_dlp_command or (sys.executable, "-m", "yt_dlp"))

    async def acquire(self, source_url: str, directory: Path) -> Path:
        source_url = validate_http_url(source_url)
        directory.mkdir(parents=True, exist_ok=True)
        host = (urlsplit(source_url).hostname or "").lower()
        if host in YOUTUBE_HOSTS:
            return await self._acquire_youtube(source_url, directory)
        return await self._acquire_http(source_url, directory)

    async def _acquire_http(self, source_url: str, directory: Path) -> Path:
        try:
            return await asyncio.wait_for(
                self._stream_http(source_url, directory),
                timeout=self._total_timeout_seconds,
            )
        except UrlAcquisitionRejected:
            raise
        except asyncio.TimeoutError as exc:
            raise UrlAcquisitionRejected("URL acquisition timed out.") from exc
        except httpx.HTTPError as exc:
            raise UrlAcquisitionRejected("URL media could not be acquired.") from exc

    async def _stream_http(self, source_url: str, directory: Path) -> Path:
        timeout = httpx.Timeout(self._network_timeout_seconds)
        destination: Path | None = None
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=timeout,
                transport=self._http_transport,
            ) as client:
                current_url = source_url
                redirects_followed = 0
                while True:
                    async with client.stream("GET", current_url) as response:
                        if response.status_code in HTTP_REDIRECT_STATUSES:
                            if redirects_followed >= self._max_redirects:
                                raise UrlAcquisitionRejected("URL media could not be acquired.")
                            location = response.headers.get("location")
                            if location is None:
                                raise UrlAcquisitionRejected("URL media could not be acquired.")
                            try:
                                current_url = validate_http_url(str(response.url.join(location)))
                            except (ValueError, httpx.InvalidURL) as exc:
                                raise UrlAcquisitionRejected(
                                    "URL redirected outside HTTP(S)."
                                ) from exc
                            redirects_followed += 1
                            continue

                        response.raise_for_status()
                        media_type = (
                            response.headers.get("content-type", "").split(";", 1)[0].lower()
                        )
                        if media_type in {"text/html", "application/xhtml+xml"}:
                            raise UrlAcquisitionRejected(
                                "The URL returned a web page instead of direct media."
                            )
                        declared_size = self._declared_size(
                            response.headers.get("content-length")
                        )
                        if declared_size is not None and declared_size > self._max_bytes:
                            raise UrlAcquisitionRejected(
                                "URL media exceeds the acquisition size limit."
                            )

                        destination = directory / (
                            f"input{self._suffix(response.url.path, media_type)}"
                        )
                        received = 0
                        with destination.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                received += len(chunk)
                                if received > self._max_bytes:
                                    raise UrlAcquisitionRejected(
                                        "URL media exceeds the acquisition size limit."
                                    )
                                output.write(chunk)
                        if received == 0:
                            raise UrlAcquisitionRejected("URL media was empty.")
                        return destination
        except BaseException:
            self._remove_partial(destination)
            raise

    async def _acquire_youtube(self, source_url: str, directory: Path) -> Path:
        destination = directory / "input.media"
        arguments = (
            *self._yt_dlp_command,
            "--ignore-config",
            "--no-playlist",
            "--max-filesize",
            str(self._max_bytes),
            "--socket-timeout",
            str(self._network_timeout_seconds),
            "--no-update",
            "--quiet",
            "--no-warnings",
            "--no-progress",
            "-f",
            "bestaudio/best",
            "-o",
            "-",
            source_url,
        )
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            return_code = await asyncio.wait_for(
                self._drain_youtube(process, destination),
                timeout=self._total_timeout_seconds,
            )
        except UrlAcquisitionRejected:
            if await self._quiesce_youtube(process, destination):
                raise asyncio.CancelledError
            raise
        except asyncio.TimeoutError as exc:
            if await self._quiesce_youtube(process, destination):
                raise asyncio.CancelledError from exc
            raise UrlAcquisitionRejected("URL acquisition timed out.") from exc
        except asyncio.CancelledError:
            await self._quiesce_youtube(process, destination)
            raise
        if return_code != 0:
            if await self._quiesce_youtube(process, destination):
                raise asyncio.CancelledError
            raise UrlAcquisitionRejected("URL media could not be acquired.")
        if destination.stat().st_size == 0:
            self._remove_partial(destination)
            raise UrlAcquisitionRejected("URL media could not be acquired.")
        return destination

    async def _drain_youtube(
        self,
        process: asyncio.subprocess.Process,
        destination: Path,
    ) -> int:
        received = 0
        assert process.stdout is not None
        with destination.open("wb") as output:
            while chunk := await process.stdout.read(64 * 1024):
                received += len(chunk)
                if received > self._max_bytes:
                    raise UrlAcquisitionRejected(
                        "URL media exceeds the acquisition size limit."
                    )
                output.write(chunk)
        return await process.wait()

    async def _quiesce_youtube(
        self,
        process: asyncio.subprocess.Process,
        destination: Path,
    ) -> bool:
        try:
            return await self._stop_process_group_quiescent(process)
        finally:
            self._remove_partial(destination)

    async def _stop_process_group_quiescent(
        self,
        process: asyncio.subprocess.Process,
    ) -> bool:
        cleanup_task = asyncio.create_task(self._stop_process_group(process))
        cancelled_during_cleanup = False
        while True:
            try:
                await asyncio.shield(cleanup_task)
                return cancelled_during_cleanup
            except asyncio.CancelledError:
                cancelled_during_cleanup = True

    @staticmethod
    async def _stop_process_group(process: asyncio.subprocess.Process) -> None:
        wait_task = asyncio.create_task(process.wait())
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(asyncio.shield(wait_task), timeout=0.25)
        except asyncio.TimeoutError:
            pass
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await wait_task

    @staticmethod
    def _remove_partial(path: Path | None) -> None:
        if path is not None:
            path.unlink(missing_ok=True)

    @staticmethod
    def _declared_size(value: str | None) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _suffix(path: str, media_type: str) -> str:
        suffix = Path(path).suffix.lower()
        if suffix and len(suffix) <= 10 and suffix[1:].isalnum():
            return suffix
        guessed = mimetypes.guess_extension(media_type, strict=False) if media_type else None
        return guessed or ".media"
