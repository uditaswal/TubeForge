"""Pass the Compose Unix listener to the unchanged socket-activated runner."""
import fcntl
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from tubeforge.host_codex_runner import CODEX_HOME, CODEX_NODE, RUNNER_ROOT, bubblewrap_args
from tubeforge.long_form.admission import local_tokenizer


def main():
    os.umask(0o077)
    CODEX_HOME.mkdir(mode=0o700, exist_ok=True)
    local_tokenizer()
    with tempfile.TemporaryDirectory(dir=RUNNER_ROOT) as folder:
        command = bubblewrap_args(Path(folder))
        # Exercise the real namespace and pinned executable with zero model calls.
        subprocess.run([*command[:command.index("--") + 1], str(CODEX_NODE), "--version"], check=True, timeout=10)

    path = Path("/run/tubeforge-codex/codex.sock")
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if path.is_socket():
            path.unlink()
        with socket.socket(socket.AF_UNIX) as listener:
            listener.bind(str(path))
            path.chmod(0o660)
            listener.listen(16)
            # Lock and listener must both survive exec. Keep the lock above fd 3.
            lock_fd = fcntl.fcntl(lock.fileno(), fcntl.F_DUPFD, 4)
            os.set_inheritable(lock_fd, True)
            os.dup2(listener.fileno(), 3, inheritable=True)
            os.environ.update(LISTEN_PID=str(os.getpid()), LISTEN_FDS="1")
            os.execv(sys.executable, [sys.executable, "-m", "tubeforge.host_codex_runner"])


if __name__ == "__main__":
    main()
