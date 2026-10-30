import os
import subprocess
import sys

import pytest

from milo.transport.instance_lock import AlreadyRunning, acquire

HOLD = "import sys, time; from pathlib import Path; from milo.transport.instance_lock import acquire; " \
       "acquire(Path(sys.argv[1])); print('held', flush=True); time.sleep(30)"


def test_a_second_process_cannot_take_the_lock_until_the_first_is_gone(tmp_path):
    path = tmp_path / "run" / "brain.lock"
    holder = subprocess.Popen([sys.executable, "-c", HOLD, str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        with pytest.raises(AlreadyRunning) as e:
            acquire(path)
        assert e.value.pid == holder.pid
        assert str(holder.pid) in str(e.value)
    finally:
        holder.kill()
        holder.wait()
    fd = acquire(path)
    assert path.read_text().strip() == str(os.getpid())
    os.close(fd)


def test_the_lock_is_per_open_file_so_one_process_can_not_take_it_twice(tmp_path):
    path = tmp_path / "brain.lock"
    fd = acquire(path)
    try:
        with pytest.raises(AlreadyRunning):
            acquire(path)
    finally:
        os.close(fd)
