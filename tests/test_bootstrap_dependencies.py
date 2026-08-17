import unittest


class TestBootstrapDependenciesImportable(unittest.TestCase):

    def test_python_docx_importable(self):
        import docx  # noqa: F401

    def test_python_pptx_importable(self):
        from pptx import Presentation  # noqa: F401

    def test_odfpy_importable(self):
        from odf import teletype, text  # noqa: F401
        from odf.opendocument import load  # noqa: F401

    def test_openpyxl_importable(self):
        import openpyxl  # noqa: F401


if __name__ == "__main__":
    unittest.main()
