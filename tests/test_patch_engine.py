import unittest

from scripts.patch_engine import (
    JsonPatchError,
    apply_patch,
    create_bullet_replace_patch,
    parse_json_pointer,
    patch_resume_bullet,
)


class TestPatchEngine(unittest.TestCase):
    def setUp(self):
        self.doc = {
            "name": "Alex Rivera",
            "experience": [
                {
                    "company": "Acme Corp",
                    "role": "Staff Engineer",
                    "bullets": [
                        "Architected distributed pipeline scaling to 10M QPS.",
                        "Mentored 5 junior engineers across 2 quarters.",
                    ],
                }
            ],
            "skills": ["Python", "Go"],
        }

    def test_parse_json_pointer(self):
        self.assertEqual(parse_json_pointer(""), [])
        self.assertEqual(
            parse_json_pointer("/experience/0/bullets/1"),
            ["experience", 0, "bullets", 1],
        )
        with self.assertRaises(JsonPatchError):
            parse_json_pointer("invalid_pointer")

    def test_replace_bullet(self):
        new_text = "Spearheaded microservices migration achieving 99.99% uptime."
        patched = patch_resume_bullet(self.doc, 0, 1, new_text)
        self.assertEqual(patched["experience"][0]["bullets"][1], new_text)
        # Verify original doc is unchanged
        self.assertEqual(
            self.doc["experience"][0]["bullets"][1],
            "Mentored 5 junior engineers across 2 quarters.",
        )

    def test_add_and_remove_operations(self):
        patch = [
            {"op": "add", "path": "/skills/-", "value": "Rust"},
            {"op": "remove", "path": "/skills/0"},
        ]
        patched = apply_patch(self.doc, patch)
        self.assertEqual(patched["skills"], ["Go", "Rust"])

    def test_test_operation(self):
        valid_patch = [
            {"op": "test", "path": "/name", "value": "Alex Rivera"},
            {"op": "replace", "path": "/name", "value": "A. Rivera"},
        ]
        patched = apply_patch(self.doc, valid_patch)
        self.assertEqual(patched["name"], "A. Rivera")

        invalid_patch = [
            {"op": "test", "path": "/name", "value": "Wrong Name"},
        ]
        with self.assertRaises(JsonPatchError):
            apply_patch(self.doc, invalid_patch)

    def test_index_out_of_bounds_raises(self):
        with self.assertRaises(JsonPatchError):
            patch_resume_bullet(self.doc, 99, 0, "Nonexistent role")


if __name__ == "__main__":
    unittest.main()
