import os
import subprocess
import sys

import pytest

from milo import system
from milo.transport.instance_lock import AlreadyRunning, acquire

HOLD = "import sys, time, os; from pathlib import Path; from milo.transport.instance_lock import acquire; " \
       "acquire(Path(sys.argv[1])); print(os.getpid(), flush=True); time.sleep(30)"


def test_a_second_process_cannot_take_the_lock_until_the_first_is_gone(tmp_path):
    path = tmp_path / "run" / "brain.lock"
    holder = subprocess.Popen([sys.executable, "-c", HOLD, str(path)], stdout=subprocess.PIPE, text=True)
    try:
        actual_pid = int(holder.stdout.readline().strip())
        with pytest.raises(AlreadyRunning) as e:
            acquire(path)
        assert e.value.pid == actual_pid
        assert str(actual_pid) in str(e.value)
    finally:
        system.signal_processes(holder.pid, [actual_pid], force=True)
        holder.wait()
    fd = acquire(path)
    os.lseek(fd, 0, os.SEEK_SET)
    assert os.read(fd, 32).decode().strip() == str(os.getpid())
    os.close(fd)


def test_the_lock_is_per_open_file_so_one_process_can_not_take_it_twice(tmp_path):
    path = tmp_path / "brain.lock"
    fd = acquire(path)
    try:
        with pytest.raises(AlreadyRunning):
            acquire(path)
    finally:
        os.close(fd)
