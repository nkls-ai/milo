"""Windows primitives: DACL-protected files, locks, process groups and authenticated local streams.

The endpoint file is a private capability, never a public listening address.
Authentication completes before the protocol handler sends or receives events.
"""
from __future__ import annotations

import asyncio
import contextlib
import errno
import hmac
import json
import os
import secrets
import signal
import socket
import stat
import subprocess
import shutil
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

ClientHandler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


def replace_file(source: Path, target: Path) -> None:
    """NTFS rename can briefly meet an indexer/antivirus handle without delete sharing."""
    for delay in (0, 0.005, 0.01, 0.02, 0.04, 0.08, 0.16):
        if delay:
            time.sleep(delay)
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if delay == 0.16:
                raise


@contextlib.contextmanager
def _directory(path: Path):
    """Pin every ancestor against rename and refuse directory reparse points."""
    import win32con
    import win32file
    import pywintypes

    handles = []
    try:
        absolute = path.absolute()
        for folder in [*reversed(absolute.parents), absolute]:
            handle = win32file.CreateFile(str(folder), 0x80,
                                         win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE, None,
                                         win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS |
                                         0x00200000, None)
            handles.append(handle)
            if win32file.GetFileInformationByHandle(handle)[0] & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
                raise OSError(errno.ELOOP, "refusing a linked directory", str(folder))
        yield
    except pywintypes.error as e:
        if e.winerror in (2, 3):
            raise FileNotFoundError(errno.ENOENT, e.strerror) from None
        raise OSError(e.winerror, e.strerror) from None
    finally:
        for handle in reversed(handles):
            handle.Close()


def open_child_no_follow(folder: Path, name: str) -> int:
    with _directory(folder):
        return open_no_follow(folder / name)


def unlink_child_no_follow(folder: Path, name: str) -> None:
    with _directory(folder):
        (folder / name).unlink()


def restore_file(source: Path, target: Path, mode: int) -> None:
    with _directory(target.parent):
        tmp = target.with_name(f"milo-undo-{secrets.token_hex(8)}-{target.name}")
        try:
            with tmp.open("xb") as written, source.open("rb") as copy:
                shutil.copyfileobj(copy, written)
            info = source.stat()
            os.utime(tmp, ns=(info.st_atime_ns, info.st_mtime_ns))
            make_private(tmp, mode)
            replace_file(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)


def clear_steering(workdir: Path, names: tuple[str, ...]) -> None:
    """Walk with non-share-delete directory handles: ancestors cannot be swapped for junctions.

    Reparse points are never entered. A locked or unreadable branch fails closed.
    """
    import win32con
    import win32file
    import pywintypes

    forbidden = frozenset(name.casefold() for name in names)

    def sweep(folder: Path, depth: int = 0, remove: bool = False) -> None:
        if depth > 32:
            raise OSError("worker folder is too deep to inspect")
        handle = win32file.CreateFile(str(folder), win32con.GENERIC_READ,
                                     win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE, None,
                                     win32con.OPEN_EXISTING, win32con.FILE_FLAG_BACKUP_SEMANTICS |
                                     0x00200000, None)
        try:
            if win32file.GetFileInformationByHandle(handle)[0] & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
                raise OSError(errno.ELOOP, "refusing to enter a worker junction", str(folder))
            for entry in list(folder.iterdir()):
                try:
                    info = entry.lstat()
                    linked = bool(info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)
                    delete = remove or entry.name.casefold() in forbidden
                    if linked:
                        if delete:
                            entry.rmdir() if stat.S_ISDIR(info.st_mode) else entry.unlink()
                    elif stat.S_ISDIR(info.st_mode):
                        sweep(entry, depth + 1, delete)
                    elif delete:
                        entry.unlink()
                except FileNotFoundError:
                    continue
        finally:
            handle.Close()
        if remove:
            folder.rmdir()

    try:
        sweep(workdir)
    except pywintypes.error as e:
        raise OSError(e.winerror, e.strerror, str(workdir)) from None


def _user():
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally:
        token.Close()


def _security(target: int | Path):
    import msvcrt
    import win32security as sec
    import pywintypes
    flags = sec.OWNER_SECURITY_INFORMATION | sec.DACL_SECURITY_INFORMATION
    try:
        if isinstance(target, int):
            return sec.GetSecurityInfo(msvcrt.get_osfhandle(target), sec.SE_FILE_OBJECT, flags)
        return sec.GetNamedSecurityInfo(str(target), sec.SE_FILE_OBJECT, flags)
    except pywintypes.error as e:
        if e.winerror in (2, 3):
            raise FileNotFoundError(errno.ENOENT, e.strerror) from None
        raise OSError(e.winerror, e.strerror) from None


def open_no_follow(path: Path) -> int:
    import msvcrt
    import win32con
    import win32file
    import pywintypes
    try:
        handle = win32file.CreateFile(str(path), win32con.GENERIC_READ | 0x00020000 |
                                     0x00040000, win32con.FILE_SHARE_READ, None,
                                     win32con.OPEN_EXISTING, 0x00200000, None)
    except pywintypes.error as e:
        if e.winerror in (2, 3):
            raise FileNotFoundError(errno.ENOENT, "file not found", str(path)) from None
        raise OSError(e.winerror, e.strerror, str(path)) from None
    try:
        if win32file.GetFileInformationByHandle(handle)[0] & win32con.FILE_ATTRIBUTE_REPARSE_POINT:
            raise OSError(errno.ELOOP, "reparse points are not secret files", str(path))
        return msvcrt.open_osfhandle(handle.Detach(), os.O_RDONLY | os.O_BINARY)
    finally:
        handle.Close()


def owned_by_me(info: os.stat_result | int | Path) -> bool:
    return _security(info).GetSecurityDescriptorOwner() == _user()


def open_to_others(info: os.stat_result | int | Path) -> bool:
    import win32security as sec
    acl = _security(info).GetSecurityDescriptorDacl()
    if acl is None:
        return True
    trusted = [_user(), sec.CreateWellKnownSid(sec.WinLocalSystemSid),
               sec.CreateWellKnownSid(sec.WinBuiltinAdministratorsSid)]
    for index in range(acl.GetAceCount()):
        header, mask, *rest = acl.GetAce(index)
        if header[0] in (sec.ACCESS_ALLOWED_ACE_TYPE, sec.ACCESS_ALLOWED_OBJECT_ACE_TYPE):
            if mask and rest[-1] not in trusted:
                return True
    return False


def make_private(target: int | Path, mode: int) -> None:
    import msvcrt
    import win32con
    import win32security as sec
    import win32file
    acl = sec.ACL()
    inheritance = (sec.OBJECT_INHERIT_ACE | sec.CONTAINER_INHERIT_ACE
                   if not isinstance(target, int) and target.is_dir() else 0)
    acl.AddAccessAllowedAceEx(sec.ACL_REVISION, inheritance, 0x001F01FF, _user())
    flags = sec.DACL_SECURITY_INFORMATION | sec.PROTECTED_DACL_SECURITY_INFORMATION
    if isinstance(target, int):
        # Reopen the same kernel object with WRITE_DAC; CRT descriptors don't
        # necessarily carry it. No second lookup through a mutable pathname.
        handle = win32file.ReOpenFile(msvcrt.get_osfhandle(target), 0x00060000,
                                     win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE |
                                     win32con.FILE_SHARE_DELETE, 0)
        try:
            sec.SetSecurityInfo(handle, sec.SE_FILE_OBJECT, flags, None, None, acl, None)
        finally:
            handle.Close()
    else:
        if target.is_symlink() or target.is_junction():
            raise OSError(errno.ELOOP, "refusing a linked private directory", str(target))
        sec.SetNamedSecurityInfo(str(target), sec.SE_FILE_OBJECT, flags, None, None, acl, None)


def try_lock(fd: int) -> bool:
    import msvcrt
    # Lock a sentinel outside the PID text so another process can still report
    # the owner's PID (Windows byte locks also deny reads by other handles).
    os.lseek(fd, 4096, os.SEEK_SET)
    try:
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    except OSError as e:
        if e.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return False
        raise
    return True


def isolated_process() -> dict[str, Any]:
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}


def signal_processes(root: int, tree: list[int], *, force: bool) -> None:
    import psutil
    pids = set(tree)
    try:
        pids.update(p.pid for p in psutil.Process(root).children(recursive=True))
    except psutil.Error:
        pass
    # CTRL_BREAK is unsafe for a process without its own attached console: it
    # can reach the launching terminal. Protocol-level interruption is handled
    # by the model adapter; OS teardown only touches the recorded process tree.
    for pid in [*pids, root]:
        try:
            process = psutil.Process(pid)
            if process.username().casefold() == psutil.Process().username().casefold():
                process.kill() if force else process.terminate()
        except psutil.Error:
            pass


def process_table() -> dict[int, tuple[int, str]]:
    import psutil
    table = {}
    for process in psutil.process_iter(["pid", "ppid", "create_time"]):
        try:
            info = process.info
            table[info["pid"]] = (info["ppid"], str(info["create_time"]))
        except psutil.Error:
            pass
    return table


async def start_local_server(client: ClientHandler, path: Path, *, limit: int | None = None) -> asyncio.Server:
    path.parent.mkdir(parents=True, exist_ok=True)
    make_private(path.parent, 0o700)
    token = secrets.token_hex(32)

    async def authenticated(reader, writer):
        try:
            supplied = await asyncio.wait_for(reader.readline(), 3.0)
            if not hmac.compare_digest(supplied, (token + "\n").encode("ascii")):
                return
            writer.write(b"OK\n")
            await writer.drain()
            await client(reader, writer)
        except (OSError, ValueError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(authenticated, "127.0.0.1", 0,
                                        **({"limit": limit} if limit is not None else {}))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY, 0o600)
        try:
            # The private parent already grants only this user. Protect this file's ACL
            # too; CRT-created descriptors don't carry WRITE_DAC access.
            make_private(path, 0o600)
            os.write(fd, json.dumps({"port": server.sockets[0].getsockname()[1], "token": token}).encode())
        finally:
            os.close(fd)
    except BaseException:
        server.close()
        await server.wait_closed()
        raise
    return server


def connect_local(path: Path, timeout_s: float | None = None) -> socket.socket:
    if not owned_by_me(path.parent) or open_to_others(path.parent):
        raise PermissionError("Milo's endpoint directory must be private")
    fd = open_no_follow(path)
    with os.fdopen(fd, "rb") as endpoint:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or not owned_by_me(fd) or open_to_others(fd):
            raise PermissionError("Milo's endpoint must be a private file owned by you")
        try:
            address = json.load(endpoint)
            token, port = address["token"], address["port"]
        except (ValueError, KeyError, TypeError) as e:
            raise OSError("invalid Milo endpoint") from e
    if not isinstance(token, str) or len(token) != 64 or not isinstance(port, int) or not 0 < port < 65536:
        raise OSError("invalid Milo endpoint")
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout_s if timeout_s is not None else 3.0)
    try:
        sock.sendall((token + "\n").encode("ascii"))
        if b"".join(sock.recv(1) for _ in range(3)) != b"OK\n":
            raise PermissionError("Milo endpoint authentication failed")
        sock.settimeout(timeout_s)
        return sock
    except BaseException:
        sock.close()
        raise


def peer_is_me(sock: socket.socket | None) -> bool:
    # The capability was checked before handing this socket to a protocol handler.
    return sock is not None and sock.getpeername()[0] == "127.0.0.1"


def precise_timers() -> None:
    """1 ms timers for this process. Windows rounds every wait, asyncio's included, up to its 15.6 ms tick by
    default, so an 80 ms hold confirm landed up to ~16 ms late and live-speech polls drifted. Since Windows 10
    2004 this applies to the calling process only; it costs a little power while Milo runs, as for any audio app."""
    import ctypes
    try:
        ctypes.WinDLL("winmm").timeBeginPeriod(1)
    except (OSError, AttributeError):
        pass


def event_loop():
    """The brain's asyncio loop. Python 3.12's loop clock on Windows is GetTickCount64, 15.6 ms steps, and asyncio
    fires a timer up to one step early or late; this loop keeps time with QueryPerformanceCounter instead, so the
    80 ms hold confirm and the 0.1 s live-speech polls run when they should."""
    import asyncio
    import time

    class PreciseLoop(asyncio.ProactorEventLoop):
        def __init__(self):
            super().__init__()
            self._clock_resolution = time.get_clock_info("perf_counter").resolution

        def time(self) -> float:
            return time.perf_counter()

    return PreciseLoop()
