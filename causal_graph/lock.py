import contextlib
import fcntl

from .topic import ensure_graph_dir


@contextlib.contextmanager
def topic_lock(topic: str):
    d = ensure_graph_dir(topic)
    lock_path = d / ".lock"
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
