"""Guards the .docx exports' visual contract with the PDF.

These assertions are deliberately about the things that were WRONG before
docx_theme existed -- Word's factory Calibri/blue-heading/1-inch look -- and
about the one place the file format refuses to store what the template asks
for (see BODY_PT's half-point note).
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import docx_theme  # noqa: E402
from docx import Document  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402


class TestDocxTheme(unittest.TestCase):
    def setUp(self):
        self.doc = Document()
        docx_theme.apply_document_theme(self.doc, layout="compact")

    def test_page_margins_match_the_pdf(self):
        for section in self.doc.sections:
            for margin in (
                section.top_margin,
                section.bottom_margin,
                section.left_margin,
                section.right_margin,
            ):
                self.assertEqual(docx_theme.PAGE_MARGIN_IN, margin.inches)
            # A header distance wider than the margin would silently push
            # the text block back inward.
            self.assertLessEqual(
                section.header_distance.inches, section.top_margin.inches
            )

    def test_body_and_heading_fonts_replace_words_defaults(self):
        normal = self.doc.styles["Normal"]
        self.assertEqual(docx_theme.BODY_FONT, normal.font.name)
        self.assertEqual(docx_theme.BODY_PT, normal.font.size.pt)
        for style_name in ("Title", "Heading 1"):
            style = self.doc.styles[style_name]
            self.assertEqual(docx_theme.HEADING_FONT, style.font.name)
            # Word ships both of these in a blue-grey; the design is black.
            self.assertEqual(docx_theme.TEXT_COLOR, style.font.color.rgb, style_name)

    def test_body_size_is_representable_in_half_points(self):
        # OOXML stores w:sz in half-points, so a size off that grid is
        # rounded silently. If someone sets BODY_PT back to the template's
        # 9.75, this catches it before a shrunken .docx ships.
        for size in (
            docx_theme.BODY_PT,
            docx_theme.LETTER_BODY_PT,
            docx_theme.SECTION_TITLE_PT,
            docx_theme.NAME_PT,
            docx_theme.LETTER_NAME_PT,
        ):
            self.assertEqual(
                size, round(size * 2) / 2, f"{size}pt is not on the half-point grid"
            )

    def test_headings_carry_no_inherited_border(self):
        # Word's Title style has a bottom border of its own; a section
        # heading's rule is added per-paragraph instead, so an inherited one
        # would double it.
        for style_name in ("Title", "Heading 1"):
            ppr = self.doc.styles[style_name].element.find(qn("w:pPr"))
            if ppr is not None:
                self.assertEqual([], ppr.findall(qn("w:pBdr")), style_name)

    def test_section_heading_draws_the_grey_rule(self):
        paragraph = docx_theme.section_heading(self.doc, "Work Experience")
        bottom = paragraph._p.find(qn("w:pPr")).find(qn("w:pBdr")).find(qn("w:bottom"))
        self.assertEqual("single", bottom.get(qn("w:val")))
        self.assertEqual(docx_theme.RULE_COLOR, bottom.get(qn("w:color")))
        # 0.018cm in the CSS is ~0.51pt, and w:sz counts eighths of a point.
        self.assertEqual("4", bottom.get(qn("w:sz")))

    def test_section_heading_can_be_drawn_without_a_rule(self):
        paragraph = docx_theme.section_heading(self.doc, "Education", rule=False)
        ppr = paragraph._p.find(qn("w:pPr"))
        self.assertTrue(ppr is None or ppr.find(qn("w:pBdr")) is None)

    def test_style_run_fills_every_font_slot(self):
        paragraph = self.doc.add_paragraph()
        run = paragraph.add_run("x")
        docx_theme.style_run(run, bold=True)
        rfonts = run._element.get_or_add_rPr().find(qn("w:rFonts"))
        self.assertEqual(docx_theme.BODY_FONT, rfonts.get(qn("w:ascii")))
        self.assertEqual(docx_theme.BODY_FONT, rfonts.get(qn("w:hAnsi")))
        self.assertEqual(docx_theme.BODY_FONT, rfonts.get(qn("w:eastAsia")))
        # The complex-script slot carries the fallback, which is where a
        # reader without DM Sans installed should land.
        self.assertEqual(docx_theme.BODY_FALLBACK, rfonts.get(qn("w:cs")))
        self.assertTrue(run.bold)

    def test_pipe_join_greys_only_the_separators(self):
        paragraph = self.doc.add_paragraph()
        docx_theme.pipe_join(paragraph, ["Acme", "Austin, TX", "2024"])
        self.assertEqual("Acme | Austin, TX | 2024", paragraph.text)
        for run in paragraph.runs:
            expected = (
                docx_theme.RULE_COLOR
                if run.text.strip() == "|"
                else str(docx_theme.TEXT_COLOR)
            )
            self.assertEqual(expected, str(run.font.color.rgb), run.text)

    def test_pipe_join_skips_blanks_without_leaving_a_stray_separator(self):
        paragraph = self.doc.add_paragraph()
        docx_theme.pipe_join(paragraph, ["", "Acme", None, "2024"])
        self.assertEqual("Acme | 2024", paragraph.text)

    def test_layout_falls_back_to_compact_like_render_html_does(self):
        for value in (None, "", "   ", "nonsense", "RELAXED"):
            resolved = docx_theme.resolve_layout(value)
            self.assertIn(resolved, docx_theme.LINE_SPACING)
        self.assertEqual("compact", docx_theme.resolve_layout("nonsense"))
        self.assertEqual("relaxed", docx_theme.resolve_layout("RELAXED"))

    def test_layout_choice_changes_leading(self):
        spacings = []
        for layout in ("compact", "balanced", "relaxed"):
            doc = Document()
            docx_theme.apply_document_theme(doc, layout=layout)
            spacings.append(doc.styles["Normal"].paragraph_format.line_spacing)
        self.assertEqual(sorted(spacings), spacings)
        self.assertEqual(len(set(spacings)), 3)

    def test_letter_scale_overrides_the_resume_body_size(self):
        doc = Document()
        docx_theme.apply_document_theme(
            doc,
            layout="compact",
            body_pt=docx_theme.LETTER_BODY_PT,
            line_spacing=docx_theme.LETTER_LINE_SPACING,
        )
        normal = doc.styles["Normal"]
        self.assertEqual(docx_theme.LETTER_BODY_PT, normal.font.size.pt)
        self.assertEqual(
            docx_theme.LETTER_LINE_SPACING, normal.paragraph_format.line_spacing
        )

    def test_theme_survives_a_round_trip_to_disk(self):
        # Everything above is asserted on the in-memory document; a style
        # edit that does not serialise would pass all of it and still ship
        # a Calibri file.
        docx_theme.section_heading(self.doc, "Skills")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "themed.docx")
            self.doc.save(path)
            reopened = Document(path)
        self.assertEqual(docx_theme.BODY_FONT, reopened.styles["Normal"].font.name)
        self.assertEqual(
            docx_theme.HEADING_FONT, reopened.styles["Heading 1"].font.name
        )
        self.assertEqual(
            docx_theme.PAGE_MARGIN_IN, reopened.sections[0].left_margin.inches
        )


if __name__ == "__main__":
    unittest.main()
