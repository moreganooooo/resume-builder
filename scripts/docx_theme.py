"""
docx_theme.py — the single place that makes a .docx look like the PDF.

Both .docx exporters used to build a bare ``Document()``, which means every
one of them shipped Word's factory look: Calibri 11pt body, Cambria-blue
``Heading 1``, a blue-underlined ``Title``, and 1-inch margins -- nothing
like the DM Serif Display / DM Sans black-on-white sheet that
``resume-engine/templates/cv-template.html`` renders through Chromium. The
two exports were the same CONTENT in two different designs.

The constants below are transcribed from that template (and from
``generate-pdf.mjs``'s own page margins), so a change to the PDF's look has
exactly one counterpart to update here rather than two hand-tuned files to
keep in step. Where the CSS has no docx equivalent the difference is
commented rather than silently approximated.

**This is presentation only -- it does not touch the ATS story.** A .docx
parser reads the document's text runs; it neither knows nor cares what font
or colour a run carries, so restyling cannot change what a keyword scanner
extracts. The ligature ban the HTML template documents at length is a real
extraction hazard and does not arise here: python-docx writes plain
characters, and no ``liga`` feature is enabled anywhere in this file.

**Fonts are named, not embedded.** DM Sans and DM Serif Display live in
``resume-engine/fonts/`` for Chromium's benefit; python-docx has no font
embedding, so a reader without them installed sees Word's substitute. Every
font is therefore declared with a generic fallback in the same run
properties (``w:cs``), and the layout is chosen to survive substitution --
nothing here depends on DM Sans's exact metrics the way the PDF's page-fit
loop does.
"""

from docx.enum.text import WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml.shared import OxmlElement
from docx.shared import Inches, Pt, RGBColor

# --- Type ---------------------------------------------------------------
# cv-template.html: 'DM Sans' body, 'DM Serif Display' for the name and
# every section title.
BODY_FONT = "DM Sans"
HEADING_FONT = "DM Serif Display"

# The substitute a reader without those fonts should land on. Naming one
# explicitly beats letting Word pick: a serif heading that falls back to a
# sans-serif loses the only typographic contrast the design has.
BODY_FALLBACK = "Arial"
HEADING_FALLBACK = "Georgia"

# --- Size ---------------------------------------------------------------
# From the template, with one forced deviation. **OOXML stores a font size
# in HALF-POINTS (``w:sz``), so the template's 9.75pt is not representable
# in a .docx at all** -- python-docx rounds it silently, and it rounds DOWN
# to 9.5, which would make the .docx read visibly smaller than the PDF it
# is supposed to mirror. 10.0 is the same 0.25pt away from 9.75 in the
# other direction, so it is the closest legal size that does not shrink the
# document. Do not "fix" this back to 9.75: the file format will take the
# value and quietly change it.
BODY_PT = 10.0
NAME_PT = 36.0
TAGLINE_PT = 15.0
# The contact row is body-sized in the template and stays tied to it here,
# rather than being restated, so the two cannot drift apart.
CONTACT_PT = BODY_PT
SECTION_TITLE_PT = 16.0

# coverletter-template.html is set a notch larger than the resume (10.5pt
# body, 32pt name, 14pt tagline) because it is a one-page letter rather
# than a density-constrained CV. Same design, different scale -- so the
# letter's sizes live here too rather than as literals in its exporter.
LETTER_BODY_PT = 10.5
LETTER_NAME_PT = 32.0
LETTER_TAGLINE_PT = 14.0
# .letter-body's line-height, notably looser than the resume's 1.15.
LETTER_LINE_SPACING = 1.5

# --- Colour -------------------------------------------------------------
# The template is black text on white with one grey used for every rule and
# pipe separator (#9aa3af).
TEXT_COLOR = RGBColor(0x00, 0x00, 0x00)
RULE_COLOR = "9AA3AF"

# --- Geometry -----------------------------------------------------------
# generate-pdf.mjs passes a uniform 0.5in margin to page.pdf().
PAGE_MARGIN_IN = 0.5

# render_html.LAYOUT_CSS's three variants differ (for our purposes) only in
# leading, so the same profile.yml `resume_layout:` value drives both
# exports. Read through resolve_layout() rather than indexed directly, so an
# unknown value degrades to compact here exactly as it does there.
LINE_SPACING = {"compact": 1.15, "balanced": 1.20, "relaxed": 1.25}

# Paragraph spacing, in points, for each layout. The CSS expresses these as
# per-element margins; docx has only space_before/space_after on a style, so
# these are the CSS values collapsed to the one knob that exists.
_SECTION_SPACE = {"compact": 8.0, "balanced": 9.0, "relaxed": 12.0}
_BLOCK_SPACE = {"compact": 2.0, "balanced": 3.0, "relaxed": 4.0}


def resolve_layout(layout: str | None) -> str:
    """Normalises a profile's `resume_layout:` to a key every table here
    has. Mirrors render_html._profile_layout()'s compact default, so a
    profile with a typo'd or missing value gets the same treatment in both
    exports instead of one falling back and the other raising."""
    key = str(layout or "").strip().lower()
    return key if key in LINE_SPACING else "compact"


def profile_layout() -> str:
    """The active profile's layout, resolved. Delegates to render_html so
    there is one reader of `resume_layout:` rather than two that could
    disagree about precedence or defaults."""
    try:
        import render_html

        return resolve_layout(render_html._profile_layout())
    except Exception:
        # Same posture as render_html's own guard: a resume that renders
        # with default leading is a far better outcome than one that does
        # not render at all because profile.yml could not be read.
        return "compact"


def _set_rfonts(element, font: str, fallback: str) -> None:
    """Writes all four font slots on a run's or a style's properties.

    python-docx's ``.font.name`` setter writes only ``w:ascii``/``w:hAnsi``;
    the complex-script and East-Asian slots keep whatever was inherited,
    which is how a document ends up half-DM-Sans in some readers. The
    fallback goes in ``w:cs`` so a reader without the named font has
    somewhere sensible to land.
    """
    rpr = element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:ascii"), font)
    rfonts.set(qn("w:hAnsi"), font)
    rfonts.set(qn("w:eastAsia"), font)
    rfonts.set(qn("w:cs"), fallback)


def style_run(
    run,
    *,
    font: str = BODY_FONT,
    fallback: str = BODY_FALLBACK,
    size_pt: float = BODY_PT,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor | str | None = None,
) -> None:
    """Applies one of this sheet's type styles to a single run."""
    run.font.name = font
    run.font.size = Pt(size_pt)
    run.bold = bold
    run.italic = italic
    if color is None:
        color = TEXT_COLOR
    if isinstance(color, str):
        color = RGBColor.from_string(color)
    run.font.color.rgb = color
    _set_rfonts(run._element, font, fallback)


def style_font(
    style,
    *,
    font: str = BODY_FONT,
    fallback: str = BODY_FALLBACK,
    size_pt: float = BODY_PT,
) -> None:
    """The style-level counterpart of style_run().

    A named style carries a ``w:rPr`` of its own, not a run's, so this
    cannot simply call style_run(): a style has no ``bold``/``italic``
    attribute to set, and reaching for one raises. Keeping them separate is
    also what lets a style stay weight-neutral while individual runs inside
    it go bold.
    """
    style.font.name = font
    style.font.size = Pt(size_pt)
    style.font.color.rgb = TEXT_COLOR
    _set_rfonts(style.element, font, fallback)


def add_bottom_rule(paragraph, color: str = RULE_COLOR) -> None:
    """The thin grey rule under a section title, a job-meta line and an
    education header (CSS: ``border-bottom: 0.018cm solid #9aa3af``).

    0.018cm is ~0.51pt; ``w:sz`` counts eighths of a point, so 4 is the
    exact equivalent rather than a rounded guess.
    """
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    for existing in borders.findall(qn("w:bottom")):
        borders.remove(existing)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    borders.append(bottom)


def space(paragraph, *, before: float = 0.0, after: float = 0.0) -> None:
    """Sets a paragraph's own spacing, for the places where the CSS margin
    is specific to one block rather than to the style as a whole."""
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)


def _style_paragraph_style(style, layout: str, leading: float | None = None) -> None:
    """Applies the shared body treatment to a named paragraph style."""
    fmt = style.paragraph_format
    fmt.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    fmt.line_spacing = LINE_SPACING[layout] if leading is None else leading
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(_BLOCK_SPACE[layout])
    # Word's default template justifies nothing but does add widow control
    # that can push a single line to the next page. The PDF's own
    # break-inside rules live on .job/.edu-item, which have no paragraph
    # equivalent, so this is left on: a stranded line is the failure the
    # HTML is also trying to avoid.
    fmt.keep_together = True


def apply_document_theme(
    doc,
    layout: str | None = None,
    *,
    body_pt: float = BODY_PT,
    line_spacing: float | None = None,
) -> str:
    """Restyles a fresh ``Document()`` to match the PDF and returns the
    resolved layout key, so a caller can size its own spacing from the same
    tables rather than re-reading profile.yml.

    Call this BEFORE adding content: python-docx resolves a paragraph's
    style at add time, but the style objects mutated here are shared, so
    ordering only matters for the explicit per-paragraph overrides.
    """
    key = resolve_layout(layout) if layout is not None else profile_layout()
    leading = LINE_SPACING[key] if line_spacing is None else line_spacing

    for section in doc.sections:
        section.top_margin = Inches(PAGE_MARGIN_IN)
        section.bottom_margin = Inches(PAGE_MARGIN_IN)
        section.left_margin = Inches(PAGE_MARGIN_IN)
        section.right_margin = Inches(PAGE_MARGIN_IN)
        # A header/footer distance larger than the margin silently pushes
        # the text block inward, which would undo the line above.
        section.header_distance = Inches(0.25)
        section.footer_distance = Inches(0.25)

    styles = doc.styles

    normal = styles["Normal"]
    style_font(normal, size_pt=body_pt)
    _style_paragraph_style(normal, key, leading)

    # Word's "Title" carries a blue bottom border and a blue-grey face out
    # of the box -- both have to go, or the name line arrives underlined in
    # a colour that appears nowhere else in the design.
    title = styles["Title"]
    style_font(title, font=HEADING_FONT, fallback=HEADING_FALLBACK, size_pt=NAME_PT)
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(0)
    title.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    _clear_style_borders(title)

    # Heading 1 is the section title: DM Serif Display 16pt, black, with
    # its rule added per-paragraph by section_heading() (a style-level
    # border cannot be suppressed for the one-off headings that need none).
    heading = styles["Heading 1"]
    style_font(
        heading, font=HEADING_FONT, fallback=HEADING_FALLBACK, size_pt=SECTION_TITLE_PT
    )
    heading.paragraph_format.space_before = Pt(_SECTION_SPACE[key])
    heading.paragraph_format.space_after = Pt(2)
    heading.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    heading.paragraph_format.line_spacing = 1.15
    heading.paragraph_format.keep_with_next = True
    _clear_style_borders(heading)

    try:
        bullets = styles["List Bullet"]
    except KeyError:
        # A caller supplying its own template may not define it; the
        # bullets then render with Normal, which is styled above.
        bullets = None
    if bullets is not None:
        style_font(bullets, size_pt=body_pt)
        _style_paragraph_style(bullets, key, leading)
        # .job li carries a 1px bottom margin against the 16px list indent;
        # the indent is the list style's own and is left alone.
        bullets.paragraph_format.space_after = Pt(1 if key == "compact" else 2)

    return key


def _clear_style_borders(style) -> None:
    """Removes a built-in style's inherited paragraph borders (Word's Title
    and Heading styles ship with them; nothing in this design wants one it
    did not ask for)."""
    ppr = style.element.find(qn("w:pPr"))
    if ppr is None:
        return
    for borders in ppr.findall(qn("w:pBdr")):
        ppr.remove(borders)


def name_heading(doc, text: str):
    """The resume/letter name line."""
    paragraph = doc.add_paragraph(style="Title")
    style_run(
        paragraph.add_run(text),
        font=HEADING_FONT,
        fallback=HEADING_FALLBACK,
        size_pt=NAME_PT,
    )
    return paragraph


def section_heading(doc, text: str, *, rule: bool = True):
    """A section title plus the grey rule the template draws under it."""
    paragraph = doc.add_paragraph(style="Heading 1")
    style_run(
        paragraph.add_run(text),
        font=HEADING_FONT,
        fallback=HEADING_FALLBACK,
        size_pt=SECTION_TITLE_PT,
    )
    if rule:
        add_bottom_rule(paragraph)
    return paragraph


def body_paragraph(doc, text: str = "", **run_kwargs):
    """A plain body paragraph, styled. ``text`` may be empty when the
    caller intends to add its own mixed-weight runs."""
    paragraph = doc.add_paragraph()
    if text:
        style_run(paragraph.add_run(text), **run_kwargs)
    return paragraph


def pipe_join(paragraph, parts, *, bold: bool = False, size_pt: float = BODY_PT):
    """Writes ``a | b | c`` with the separators in the template's grey
    rather than the text colour. Joining with a plain string would render
    the pipes as loud as the content, which is the one thing the CSS is
    careful about (``.sep``/``.separator`` are grey everywhere)."""
    items = [p for p in parts if p]
    for i, item in enumerate(items):
        if i:
            style_run(paragraph.add_run(" | "), size_pt=size_pt, color=RULE_COLOR)
        style_run(paragraph.add_run(str(item)), size_pt=size_pt, bold=bold)
    return paragraph


__all__ = [
    "BODY_FONT",
    "HEADING_FONT",
    "BODY_PT",
    "NAME_PT",
    "TAGLINE_PT",
    "CONTACT_PT",
    "SECTION_TITLE_PT",
    "LETTER_BODY_PT",
    "LETTER_LINE_SPACING",
    "LETTER_NAME_PT",
    "LETTER_TAGLINE_PT",
    "TEXT_COLOR",
    "RULE_COLOR",
    "PAGE_MARGIN_IN",
    "LINE_SPACING",
    "add_bottom_rule",
    "apply_document_theme",
    "body_paragraph",
    "name_heading",
    "pipe_join",
    "profile_layout",
    "resolve_layout",
    "section_heading",
    "space",
    "style_font",
    "style_run",
]
