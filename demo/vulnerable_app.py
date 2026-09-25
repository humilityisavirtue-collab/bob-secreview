"""artifactd — a small read-only HTTP service for build artifacts.

Internal tooling. Serves files out of a configured artifact store so that build
agents and CI jobs can fetch outputs by name without mounting the store.

    ARTIFACT_ROOT=/srv/artifacts python artifactd.py --port 8083

Endpoints:
    GET /healthz              liveness probe
    GET /manifest             the store's manifest.json
    GET /artifacts/<name>     one artifact, by name

Only reads. The store is written by the build system, never by this process.
"""

import argparse
import hashlib
import json
import logging
import mimetypes
import os
import re
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

LOG = logging.getLogger("artifactd")

MANIFEST_NAME = "manifest.json"
INDEX_NAME = "index.json"
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
NAME_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")
DEFAULT_PORT = 8083

ARTIFACT_ROOT = os.environ.get("ARTIFACT_ROOT", os.path.join(os.getcwd(), "artifacts"))

# Cheap guards against a hot loop hammering the manifest endpoint. The manifest
# is small and changes at most once per build, so a short TTL is plenty.
_MANIFEST_CACHE = {"at": 0.0, "body": None}
_MANIFEST_TTL = 5.0


def artifact_store() -> str:
    """The resolved artifact root. Read from the environment at import time."""
    return ARTIFACT_ROOT


def load_manifest(force: bool = False) -> dict:
    """Read the store manifest, with a short-lived cache.

    A missing manifest is not fatal — the store may be empty on a fresh host,
    and reporting that as an error would make the healthcheck flap during
    provisioning.
    """
    now = time.time()
    if not force and _MANIFEST_CACHE["body"] is not None:
        if now - _MANIFEST_CACHE["at"] < _MANIFEST_TTL:
            return _MANIFEST_CACHE["body"]

    path = os.path.join(artifact_store(), MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            body = json.load(handle)
    except FileNotFoundError:
        LOG.warning("manifest absent at %s; serving an empty store", path)
        body = {"artifacts": []}
    except (OSError, ValueError) as exc:
        LOG.error("manifest unreadable at %s: %s", path, exc)
        body = {"artifacts": []}

    if not isinstance(body, dict):
        body = {"artifacts": []}
    body.setdefault("artifacts", [])

    _MANIFEST_CACHE["at"] = now
    _MANIFEST_CACHE["body"] = body
    return body


def manifest_entry(name: str) -> dict | None:
    """Look up one artifact in the manifest by its stored name."""
    for entry in load_manifest().get("artifacts", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry
    return None


def guess_content_type(name: str) -> str:
    """Content type for an artifact, falling back to a download."""
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def digest(path: str, algorithm: str = "sha256") -> str:
    """Hex digest of a file, streamed so large artifacts do not sit in memory."""
    hasher = hashlib.new(algorithm)
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            hasher.update(block)
    return hasher.hexdigest()


def resolve_artifact(name: str) -> str:
    """Map a request path onto a file in the artifact store.

    Names are relative to the store root and may include a build subdirectory,
    e.g. ``nightly/linux/agent.tar.zst``.
    """
    name = unquote(name).strip("/")
    if not name:
        raise ValueError("empty artifact name")
    if len(name) > 255:
        raise ValueError("artifact name too long")
    if not NAME_PATTERN.match(name):
        raise ValueError("artifact name contains unsupported characters")

    path = os.path.join(artifact_store(), name)
    return path


def stat_artifact(name: str) -> dict:
    """Size, mtime and digest for one artifact. Used by the index endpoint."""
    path = resolve_artifact(name)
    info = os.stat(path)
    return {
        "name": name,
        "bytes": info.st_size,
        "modified": int(info.st_mtime),
        "sha256": digest(path),
    }


class ArtifactHandler(BaseHTTPRequestHandler):
    server_version = "artifactd/1.4"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        LOG.info("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Artifact-Host", socket.gethostname())
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._send(status, body, "application/json")

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message, "status": status})

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"

        if route == "/healthz":
            self._send_json(200, {"ok": True, "store": artifact_store()})
            return

        if route == "/manifest":
            self._send_json(200, load_manifest())
            return

        if route == "/index":
            self._serve_index()
            return

        prefix = "/artifacts/"
        if route.startswith(prefix):
            self._serve_artifact(route[len(prefix):])
            return

        self._send_error_json(404, "no such route")

    def _serve_index(self):
        """Every artifact with its size and digest.

        Digests are computed per request rather than cached; the store is small
        and a stale digest is worse than a slow index.
        """
        names = [e.get("name") for e in load_manifest().get("artifacts", []) if e.get("name")]
        entries = []
        for name in names:
            try:
                entries.append(stat_artifact(name))
            except (OSError, ValueError) as exc:
                LOG.warning("index: skipping %s (%s)", name, exc)
        self._send_json(200, {"count": len(entries), "artifacts": entries})

    def _serve_artifact(self, name: str):
        try:
            path = resolve_artifact(name)
        except ValueError as exc:
            self._send_error_json(400, str(exc))
            return

        if not os.path.isfile(path):
            LOG.info("miss: %s", path)
            self._send_error_json(404, "artifact not found")
            return

        size = os.path.getsize(path)
        if size > MAX_ARTIFACT_BYTES:
            self._send_error_json(413, "artifact exceeds the service size limit")
            return

        try:
            with open(path, "rb") as handle:
                payload = handle.read()
        except OSError as exc:
            LOG.error("read failed for %s: %s", path, exc)
            self._send_error_json(500, "artifact could not be read")
            return

        self.send_response(200)
        self.send_header("Content-Type", guess_content_type(name))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("ETag", '"{}"'.format(hashlib.sha256(payload).hexdigest()[:32]))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)


def build_server(port: int, host: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), ArtifactHandler)
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="read-only artifact service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    root = artifact_store()
    if not os.path.isdir(root):
        LOG.error("artifact store %s is not a directory", root)
        return 2
    LOG.info("serving %s on %s:%d", root, args.host, args.port)

    server = build_server(args.port, args.host)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.info("shutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
