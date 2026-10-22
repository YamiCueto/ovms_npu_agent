"""Cross-process exclusion for this application's clients of the same model."""
import hashlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def model_lock(client):
    identity = f'{getattr(client, "base_url", "local")}:{client.model}'
    digest = hashlib.sha256(identity.encode()).hexdigest()[:24]
    path = Path(tempfile.gettempdir()) / f'npu-agent-{digest}.lock'
    with path.open('a+b') as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Modelo ocupado por otra ejecucion local') from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)
