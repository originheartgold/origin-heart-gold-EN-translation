"""Persistent, bounded JSON-lines transport to the shared TypeScript save core.

Build the core explicitly before running a harness. This adapter never installs
packages or builds code, and contains no binary save/Pokémon implementation.
"""
from __future__ import annotations

import atexit
import base64
import copy
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import threading
import time

VERSION = 1
MAX_MESSAGE = 2_000_000
WORKER = Path(__file__).resolve().parents[1] / "save-core" / "cli" / "worker.mjs"


class CoreError(ValueError):
    def __init__(self, message, code="CORE_ERROR", operation_index=None):
        super().__init__(message)
        self.code = code
        self.operation_index = operation_index


class WorkerError(RuntimeError):
    pass


class Worker:
    """One request at a time, one deadline for writing and reading, lazy restart.

    A failed request is never replayed. The next independent request starts a new
    worker. stderr is inherited rather than piped, so diagnostics cannot deadlock.
    Production workers verify the sealed build at startup and complete an identity
    handshake before receiving data. A running worker keeps that verified version;
    close/restart it after rebuilding. Explicit command injection is for transport
    tests; expected_build additionally enables handshake tests for such commands.
    """
    def __init__(self, command=None, timeout=15, expected_build=None):
        self.command = command
        self.timeout = timeout
        self.expected_build = expected_build
        self._proc = None
        self._owner = os.getpid()
        self._id = 0
        self._lock = threading.Lock()

    def _start(self):
        if self._owner != os.getpid():
            # Never kill the parent's worker after fork.
            if self._proc:
                self._proc.stdin.close()
                self._proc.stdout.close()
                # The inherited Popen does not own a child in this process.
                self._proc.returncode = 0
            self._proc = None
            self._owner = os.getpid()
        if self._proc is not None and self._proc.poll() is None:
            return
        self._close()
        command = self.command
        expected_build = self.expected_build
        if command is None:
            node = shutil.which("node")
            if not node:
                raise WorkerError("Node.js is required by the save core; install it explicitly before running the harness")
            if not WORKER.is_file() or not (WORKER.parent.parent / "dist" / "fixture.js").is_file():
                raise WorkerError("Shared save core is not built. Run npm run build in work/save-editor first; no runtime build is attempted")
            try:
                manifest = json.loads((WORKER.parent.parent / "dist" / "build-identity.json").read_text())
                expected_build = manifest["buildId"]
                if (type(manifest.get("schema")) is not int or manifest["schema"] != 1
                        or type(manifest.get("protocol")) is not int or manifest["protocol"] != VERSION
                        or type(expected_build) is not str or len(expected_build) != 64
                        or any(c not in "0123456789abcdef" for c in expected_build)):
                    raise ValueError("invalid build identity")
            except (OSError, ValueError, KeyError, TypeError) as e:
                raise WorkerError("Shared save core build identity is missing or incompatible. Run npm run build in work/save-editor first; no runtime build is attempted") from e
            command = [node, str(WORKER)]
        try:
            self._proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=None, bufsize=0, shell=False, close_fds=True)
        except OSError as e:
            raise WorkerError(f"Cannot start shared save core: {e}") from e
        os.set_blocking(self._proc.stdin.fileno(), False)
        os.set_blocking(self._proc.stdout.fileno(), False)
        if expected_build is not None:
            try:
                identity = self._exchange("handshake", b"", {})
                if (type(identity) is not dict or type(identity.get("schema")) is not int or identity["schema"] != 1
                        or type(identity.get("protocol")) is not int or identity["protocol"] != VERSION
                        or identity.get("buildId") != expected_build):
                    raise WorkerError("save core build identity/protocol handshake mismatch")
            except (CoreError, WorkerError) as e:
                self._close()
                raise WorkerError(f"Shared save core startup failed: {e}. The build may be stale; run npm run build in work/save-editor") from e

    def _close(self):
        p, self._proc = self._proc, None
        if p is None:
            return
        if self._owner == os.getpid() and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=1)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=1)
        if self._owner != os.getpid():
            p.returncode = 0
        p.stdin.close()
        p.stdout.close()

    def close(self):
        if self._owner != os.getpid():
            self._lock = threading.Lock()
        with self._lock:
            self._close()

    def request(self, op, raw=b"", **args):
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise TypeError("save core input must be bytes")
        size = raw.nbytes if isinstance(raw, memoryview) else len(raw)
        if size > 750_000:
            raise ValueError("save core input is too large")
        raw = bytes(raw)  # own the snapshot; normalize cast/noncontiguous views
        if self._owner != os.getpid():
            self._lock = threading.Lock()
        with self._lock:
            self._start()
            return self._exchange(op, raw, args)

    def _exchange(self, op, raw, args):
        """Caller owns the lock; shared bounded transport for startup and operations."""
        self._id += 1
        request_id = self._id
        packet = json.dumps({"version": VERSION, "id": request_id, "op": op,
                             "bytes": base64.b64encode(raw).decode("ascii"), "args": args},
                            allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(packet) > MAX_MESSAGE:
            raise ValueError("save core request is too large")
        packet_view = memoryview(packet)
        deadline = time.monotonic() + self.timeout
        received, sent = bytearray(), 0
        try:
            with selectors.DefaultSelector() as poll:
                poll.register(self._proc.stdin, selectors.EVENT_WRITE)
                poll.register(self._proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WorkerError("save core request timed out")
                    for key, _ in poll.select(remaining):
                        if key.fileobj is self._proc.stdin:
                            sent += os.write(key.fd, packet_view[sent:])
                            if sent == len(packet):
                                poll.unregister(self._proc.stdin)
                        else:
                            chunk = os.read(key.fd, 65536)
                            if not chunk:
                                raise WorkerError("save core exited before responding")
                            received.extend(chunk)
                            if len(received) > MAX_MESSAGE:
                                raise WorkerError("save core response exceeds protocol limit")
                            if b"\n" in received:
                                line, rest = received.split(b"\n", 1)
                                if rest:
                                    raise WorkerError("unexpected extra save core response")
                                result = json.loads(line)
                                if (type(result) is not dict or type(result.get("version")) is not int or result.get("version") != VERSION
                                        or type(result.get("id")) is not int or result["id"] != request_id):
                                    raise WorkerError("save core protocol/version/request ID mismatch")
                                if "error" in result:
                                    err = result["error"]
                                    if type(err) is not dict or type(err.get("message")) is not str:
                                        raise WorkerError("malformed save core error")
                                    raise CoreError(err["message"], err.get("code", "CORE_ERROR"), err.get("operationIndex"))
                                if "result" not in result:
                                    raise WorkerError("missing save core result")
                                return result["result"]
        except CoreError:
            raise
        except (OSError, ValueError, WorkerError) as e:
            self._close()
            if isinstance(e, WorkerError):
                raise
            raise WorkerError(f"save core protocol failure: {e}") from e


_worker = Worker()
atexit.register(_worker.close)


def request(op, raw=b"", **args):
    return _worker.request(op, raw, **args)


def result_bytes(result):
    return base64.b64decode(result["bytes"], validate=True)


def patch_pokemon(raw, **changes):
    """Harness fixture edit, intentionally retaining cached stats and unused moves."""
    return result_bytes(request("patchPokemon", raw, changes=changes, tailPolicy="preserve"))


def compatibility_mon(mon):
    """Field-name adapter only; all interpretation belongs to TypeScript."""
    fields = ("hp", "attack", "defense", "speed", "spAttack", "spDefense")
    # SaveFile caches inspection results: callers must never alias that cache.
    mon = copy.deepcopy(mon)
    result = mon
    result.update(species=mon["speciesId"], checksum_ok=mon["checksumOk"], bad_egg=mon["badEgg"],
                  fateful=int(mon["fateful"]), exp=mon["experience"], ot_id=mon["otId"],
                  moves=[m["id"] for m in mon["moves"]], pp=[m["pp"] for m in mon["moves"]],
                  ivs=[mon["ivs"][f] for f in fields], evs=[mon["evs"][f] for f in fields],
                  ot_name=mon.get("otName", []))
    if mon.get("party") is not None:
        party = mon["party"]
        result.update(level=party["level"], hp=party["currentHp"], stats=[party["stats"][f] for f in fields])
    return result


def decode_pokemon(raw):
    return compatibility_mon(request("decodePokemon", raw, diagnostic=True))


def atomic_write(path, data, source=None):
    """Publish a completed new fixture atomically without overwriting any file."""
    path = Path(path)
    if source is not None and path.resolve() == Path(source).resolve():
        raise ValueError("fixture output must differ from the seed save")
    if path.exists():
        raise FileExistsError(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # Atomic creation, including a concurrent writer racing our existence check.
        os.link(tmp, path)
    finally:
        os.unlink(tmp)
