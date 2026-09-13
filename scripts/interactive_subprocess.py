"""interactive_subprocess.py -- runs an interactive Go TUI/prompt binary
as a real foreground subprocess while guaranteeing the child is cleaned
up no matter how the parent goes away.

WHY THIS EXISTS

Every interactive Go binary this project shells out to -- the prompt
binary (charm_prompt.py), the onboarding wizard (menu.py's
_run_go_bootstrap_wizard), and the main dashboard TUI (dashboard.py) --
used a bare subprocess.run(cmd) with no explicit child-process lifecycle
management. subprocess.run() only kills its child on an exception raised
INSIDE its own call (its internal `except: process.kill(); raise` covers
a KeyboardInterrupt that arrives while blocked in communicate()/wait()),
but has zero coverage for SIGTERM or SIGHUP delivered to the parent --
Python's default disposition for both is immediate termination with no
Python code running at all, `finally` blocks included, so the child is
simply abandoned. Real, observed impact: ~30 orphaned
dashboard/bin/prompt processes accumulated over several days on one
machine, one per interrupted menu prompt, each sitting forever waiting
on a keystroke that would never arrive.

This wraps Popen with (1) a try/finally that guarantees cleanup on any
Python-level exception, including KeyboardInterrupt, and (2) SIGTERM/
SIGHUP handlers registered once at import time that run the same
cleanup before restoring the default disposition and re-signaling --
covering the cases a bare subprocess.run() cannot reach at all.

SIGINT is deliberately NOT hooked here. Python's default SIGINT handler
already raises KeyboardInterrupt, which the try/finally below already
catches, and menu.py's own top-level `except KeyboardInterrupt` is what
turns Ctrl-C into "Cancelled." and keeps the menu loop alive -- installing
a custom SIGINT handler here would only risk changing that existing,
relied-upon behavior for no benefit.
"""

import atexit
import os
import signal
import subprocess
import time

_active_processes: set = set()

# How long to wait for a terminate()'d child to exit on its own before
# escalating to kill() -- long enough for the Go program's own huh/
# Bubbletea teardown (restoring terminal raw mode, etc.) to run, short
# enough that a genuinely stuck child doesn't hang parent shutdown.
_GRACE_PERIOD_SECONDS = 2.0


def _terminate_all(signum=None, _frame=None) -> None:
    """Best-effort cleanup of every still-tracked child: terminate()
    first (lets the Go program restore terminal state cleanly if it gets
    the chance), escalating to kill() for anything still alive after the
    grace period. Snapshots the set before iterating since a process
    finishing mid-loop mutates it (see run()'s finally)."""
    procs = [p for p in list(_active_processes) if p.poll() is None]
    for proc in procs:
        try:
            proc.terminate()
        except OSError:
            pass

    if procs:
        deadline = time.time() + _GRACE_PERIOD_SECONDS
        for proc in procs:
            try:
                proc.wait(timeout=max(0.0, deadline - time.time()))
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except OSError:
                    pass

    if signum is not None:
        # Restore the default disposition and re-raise -- the parent
        # should still actually terminate on SIGTERM/SIGHUP, just with
        # its children cleaned up first, not have the signal silently
        # swallowed.
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)


atexit.register(_terminate_all)

# SIGHUP: the terminal window/tab running the parent gets closed.
# SIGTERM: the parent is killed directly (kill <pid>, a process manager).
# Neither triggers Python's normal exception-unwinding/finally machinery
# by default -- this is exactly the gap a bare subprocess.run() call
# cannot cover on its own.
for _sig in (signal.SIGTERM, getattr(signal, "SIGHUP", None)):
    if _sig is None:
        continue  # SIGHUP doesn't exist on Windows.
    try:
        signal.signal(_sig, _terminate_all)
    except ValueError:
        # Not called from the main thread (e.g. a test runner importing
        # this module from a worker thread) -- the try/finally in run()
        # below still covers the exception-based cleanup path regardless.
        pass


def run(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """Drop-in replacement for subprocess.run(cmd, **kwargs) for an
    interactive Go TUI/prompt binary. Accepts the same kwargs
    (cwd/env/text/check/timeout, plus capture_output as a convenience for
    stdout=PIPE, stderr=PIPE) -- the only behavioral difference from
    subprocess.run() is that this module's SIGTERM/SIGHUP handlers and
    atexit hook can find and clean up the child even when the parent
    never gets a chance to run its own exception handling."""
    check = kwargs.pop("check", False)
    timeout = kwargs.pop("timeout", None)
    if kwargs.pop("capture_output", False):
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE

    proc = subprocess.Popen(cmd, **kwargs)
    _active_processes.add(proc)
    try:
        stdout_data, stderr_data = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_data, stderr_data = proc.communicate()
        raise subprocess.TimeoutExpired(
            cmd, timeout, output=stdout_data, stderr=stderr_data
        )
    except BaseException:
        # Covers KeyboardInterrupt (Ctrl-C while blocked here) and any
        # other exception -- same principle as subprocess.run()'s own
        # internal handling, just also reached from this wrapper.
        proc.kill()
        proc.wait()
        raise
    finally:
        _active_processes.discard(proc)

    result = subprocess.CompletedProcess(
        cmd, proc.returncode, stdout=stdout_data, stderr=stderr_data
    )
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(
            proc.returncode, cmd, output=stdout_data, stderr=stderr_data
        )
    return result
