"""Design-system styling for the Click CLI's help and error output.

The Go dashboard's CLI renders through fang with the palette from
``guidelines/cli-fang.card.html``; fang cannot wrap a Click app, so this
module applies the same palette to Click's own formatter: brand accent for
the program name and commands, Blue (INFO) section headings, Peach flags,
muted descriptions, and a Red "✗ Error" header with a fix line.

Color goes through ``click.style``, and Click's echo strips ANSI when the
output is not a terminal, so piped help and CliRunner tests stay plain.
``NO_COLOR`` is honored explicitly as well.
"""

import os
import re

import click
import theme

_OPTION_TOKEN = re.compile(r"(?<![\w-])(--?[A-Za-z][\w-]*)")


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


PROGRAM = _hex_rgb(theme.BRAND_ACCENT)
HEADING = _hex_rgb(theme.INFO)
FLAG = _hex_rgb(theme.PEACH)
DESCRIPTION = _hex_rgb(theme.MUTED)
ERROR = _hex_rgb(theme.ERROR)


def _color_enabled() -> bool:
    return not os.environ.get("NO_COLOR")


def _paint(text: str, rgb: tuple[int, int, int], bold: bool = False) -> str:
    if not _color_enabled():
        return text
    return click.style(text, fg=rgb, bold=bold)


def _paint_flags(text: str) -> str:
    """Color every option token (``--profile``, ``-v``) in a term."""
    return _OPTION_TOKEN.sub(lambda m: _paint(m.group(1), FLAG), text)


class StyledHelpFormatter(click.HelpFormatter):
    """Click's formatter with the design system's CLI palette."""

    def write_usage(self, prog: str, args: str = "", prefix: str | None = None) -> None:
        """Render the usage line with a colored program name."""
        label = _paint("Usage:", HEADING, bold=True)
        self.write(
            f"{' ' * self.current_indent}{label} {_paint(prog, PROGRAM, bold=True)}"
        )
        if args:
            self.write(" " + _paint_flags(args))
        self.write("\n")

    def write_heading(self, heading: str) -> None:
        """Render a section heading in Blue."""
        self.write(
            f"{' ' * self.current_indent}{_paint(heading + ':', HEADING, bold=True)}\n"
        )

    def write_dl(self, rows, col_max: int = 30, col_spacing: int = 2) -> None:
        """Render a term/description list: flags Peach, commands accent,
        descriptions muted. Widths are measured before coloring so ANSI
        codes never skew the column alignment."""
        rows = list(rows)
        if not rows:
            return
        first_col = min(max(len(term) for term, _ in rows), col_max) + col_spacing
        text_width = max(self.width - first_col - self.current_indent, 10)
        indent = " " * self.current_indent
        for term, desc in rows:
            styled = (
                _paint_flags(term)
                if term.lstrip().startswith("-")
                else _paint(term, PROGRAM)
            )
            self.write(indent + styled)
            if not desc:
                self.write("\n")
                continue
            if len(term) <= first_col - col_spacing:
                self.write(" " * (first_col - len(term)))
            else:
                self.write("\n" + " " * (first_col + self.current_indent))
            lines = click.formatting.wrap_text(
                desc, text_width, preserve_paragraphs=True
            ).splitlines()
            self.write(_paint(lines[0], DESCRIPTION) + "\n")
            for line in lines[1:]:
                self.write(
                    " " * (first_col + self.current_indent)
                    + _paint(line, DESCRIPTION)
                    + "\n"
                )

    def write_text(self, text: str) -> None:
        """Render free text (the command docstring) muted."""
        start = len(self.buffer)
        super().write_text(text)
        body = "".join(self.buffer[start:])
        del self.buffer[start:]
        self.write(
            "\n".join(
                _paint(line, DESCRIPTION) if line.strip() else line
                for line in body.split("\n")
            )
        )


class StyledContext(click.Context):
    """Context that builds help with StyledHelpFormatter."""

    formatter_class = StyledHelpFormatter


def _show_error(exc: click.ClickException) -> None:
    """Print "✗ Error <message>" plus the usage hint as the fix line."""
    head = _paint("✗ Error", ERROR, bold=True)
    click.echo(f"{head} {exc.format_message()}", err=True)
    if isinstance(exc, click.UsageError) and exc.ctx is not None:
        fix = f"Try '{exc.ctx.command_path} --help' for the available options."
        click.echo("  " + _paint(fix, DESCRIPTION), err=True)


def _styled(exc: click.ClickException) -> click.ClickException:
    """Swap the exception's own show() for the styled one. Click's
    standalone main still catches it, calls show() and exits with its code,
    so exit statuses are exactly what they were."""
    exc.show = lambda file=None: _show_error(exc)  # type: ignore[method-assign]
    return exc


class StyledCommand(click.Command):
    """A command whose help and errors use the design-system palette."""

    context_class = StyledContext


class StyledGroup(click.Group):
    """A group whose subcommands and subgroups are styled too."""

    context_class = StyledContext
    command_class = StyledCommand
    group_class = type  # subgroups are StyledGroup as well

    def make_context(self, info_name, args, parent=None, **extra):
        """Build the context, restyling any parse error it raises."""
        try:
            return super().make_context(info_name, args, parent=parent, **extra)
        except click.ClickException as exc:
            _styled(exc)
            raise

    def invoke(self, ctx):
        """Invoke the subcommand, restyling any Click error it raises."""
        try:
            return super().invoke(ctx)
        except click.ClickException as exc:
            _styled(exc)
            raise
