"""atomic_write.py -- one context manager so a knowledge-base/profile/
checkpoint write survives a crash, Ctrl-C, or laptop sleep mid-write.

B13: `open(path, "w")` truncates the target to 0 bytes at open, before a
single byte of the new content is written -- every KB/profile/checkpoint
writer that reopened its target file in place shared that destructive
window, and there was no atomic-write helper anywhere in this codebase
(`grep -rn "os.replace\\|os.rename\\|tempfile\\|NamedTemporary" scripts/*.py`
returned nothing).

atomic_write() closes that window: write to a sibling temp file in the
same directory (same filesystem, so the replace below is atomic), then
os.replace() it over the real path only once the write completed without
raising. A failure anywhere in between leaves the original file
untouched and removes the temp file -- it never leaves a half-written
file at the real path, and never leaves a stray lock file behind.

Same directory matters twice: os.replace() is only guaranteed atomic
within a single filesystem, and a stray temp file left in
profiles/<name>/ (a real, user-visible project directory) is a nuisance
someone will notice, unlike one in a real OS temp dir.
"""

import contextlib
import os
import tempfile


@contextlib.contextmanager
def atomic_write(path, mode="w", **kwargs):
    """Drop-in replacement for `open(path, mode, **kwargs)` as a `with`
    target for durable writes. Yields a file object to write to; on a
    clean exit, atomically replaces `path` with what was written. On any
    exception, `path` is left exactly as it was and the temp file is
    removed."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, mode, **kwargs) as f:
            yield f
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
