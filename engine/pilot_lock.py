"""Cooperative lifetime exclusion for one private pilot's local file store."""

from contextlib import contextmanager
import os
from pathlib import Path
import stat


LOCK_NAME = '.pilot-runtime.lock'


class PilotLockError(Exception):
    """Fixed, credential-free error at the launcher boundary."""


def _lock(fd):
    if os.name == 'nt':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        # Windows permits locking beyond EOF; the file stays empty.
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    elif os.name == 'posix':
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:
        raise PilotLockError('unsupported_pilot_lock_platform')


@contextmanager
def pilot_lock(root, *, check_only=False):
    """Hold until process shutdown. Check-only never creates a lock file.

    The caller must validate the private root first. Never unlink this file:
    replacing its identity could let a second process acquire a different lock.
    A stopped/crashed process releases the OS lock; file existence is not liveness.
    This coordinates participating launchers on a protected local filesystem,
    not arbitrary scripts, old launchers, copied roots or hostile local writers.
    """
    path = Path(root) / LOCK_NAME
    fd = None
    try:
        try:
            if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
                raise PilotLockError('private_pilot_lock_path_invalid')
            flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
            if not check_only:
                flags |= os.O_CREAT
            try:
                fd = os.open(path, flags, 0o600)
            except FileNotFoundError:
                if not check_only:
                    raise
            if fd is not None:
                os.set_inheritable(fd, False)
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    raise PilotLockError('private_pilot_lock_path_invalid')
                _lock(fd)
        except OSError:
            raise PilotLockError('private_pilot_storage_in_use_or_unavailable') from None
        yield
    finally:
        if fd is not None:
            # Closing the handle releases the lock even after failed startup.
            os.close(fd)
