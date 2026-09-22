"""logstyle.py -- the Python half of the project's log format.

The design system asks for "structured levelled logging with the same
palette [so] the log file [looks] like the program that wrote it." The Go
side gets that from `charmbracelet/log` with this project's theme applied
(`dashboard/internal/theme/logstyles.go`). This module is the Python side of
the same contract.

`bootstrap-error.log` was the concrete complaint: a raw
`traceback.format_exc()` with one hand-written English sentence on top. A
traceback tells you where Python was; it does not tell you WHEN, at which of
express setup's eight stages, or for which profile -- and express setup fails
with partial state on disk, so those are the three questions actually being
asked. Worse, there was nothing machine-readable in it, so a second failure
appended nothing comparable to the first.

The format is charmbracelet/log's text format, deliberately, rather than a
Python-flavoured lookalike:

    2026-09-22 14:03:11 ERRO <message> key=value key="value with spaces"

* The level tags are the library's own four-character labels (`DEBU`, `INFO`,
  `WARN`, `ERRO`, `FATA`) -- they are what a reader greps for, and a log the
  two halves of this program write differently is two log formats.
* Values are logfmt-quoted, so a stage name containing spaces survives being
  read back by anything that parses logfmt.
* NO color. The Go logger colorizes because it writes to a terminal; this
  writes to a file, where escape sequences are something to strip before you
  can read it. The shared thing is the structure, not the ANSI.

A multi-line payload (a traceback) is written AFTER the record rather than
squeezed into a value: one record per line is the property that makes the
rest of the file greppable, and a 40-line quoted traceback would destroy it.
"""

import datetime
import re

# The library's own labels (charmbracelet/log's logger_test.go asserts on
# exactly these strings). Kept as a mapping rather than a slice so a caller
# names a level rather than indexing one.
LEVELS = {
    "debug": "DEBU",
    "info": "INFO",
    "warn": "WARN",
    "error": "ERRO",
    "fatal": "FATA",
}

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

_BARE = re.compile(r"^[A-Za-z0-9_./:@+-]+$")


def _quote(value: object) -> str:
    """logfmt-quote a value unless it is already unambiguous bare."""
    text = str(value)
    if text and _BARE.match(text):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def format_record(
    level: str,
    message: str,
    when: datetime.datetime | None = None,
    **fields: object,
) -> str:
    """One log line in charmbracelet/log's text format.

    An unknown level is reported as `INFO` rather than raising: a logging
    call must never be the thing that takes down the error handler it was
    added to.
    """
    tag = LEVELS.get(level.lower(), LEVELS["info"])
    stamp = (when or datetime.datetime.now()).strftime(TIMESTAMP_FORMAT)
    parts = [stamp, tag, message.strip()]
    for key, value in fields.items():
        parts.append(f"{key}={_quote(value)}")
    return " ".join(parts)


def format_failure(
    message: str,
    detail: str = "",
    when: datetime.datetime | None = None,
    **fields: object,
) -> str:
    """An ERRO record, plus any multi-line detail indented beneath it.

    The indent is what keeps the detail visibly subordinate to its record
    without pretending to be one: a line that starts with a space is not a
    new record, to a reader or to a logfmt parser.
    """
    out = [format_record("error", message, when=when, **fields)]
    body = detail.rstrip()
    if body:
        out.extend("    " + line for line in body.splitlines())
    return "\n".join(out) + "\n"
