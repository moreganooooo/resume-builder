import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import voice_metrics  # noqa: E402


class TestVoiceMetrics(unittest.TestCase):

    def test_split_sentences_handles_abbreviations_and_decimals(self):
        text = "I grew revenue by 14.5% at Acme Inc. in St. Louis. For e.g., we built tools for Ph.D. researchers."
        sentences = voice_metrics.split_sentences(text)
        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0], "I grew revenue by 14.5% at Acme Inc. in St. Louis.")
        self.assertEqual(sentences[1], "For e.g., we built tools for Ph.D. researchers.")

    def test_split_sentences_handles_empty_or_whitespace(self):
        self.assertEqual(voice_metrics.split_sentences(""), [])
        self.assertEqual(voice_metrics.split_sentences("   \n\t  "), [])

    def test_compute_sentence_length_stats(self):
        sentences = [
            "Short sentence.",                       # 2 words
            "This is a medium length sentence here.", # 7 words
            "This is a substantially longer compound sentence designed to verify that the standard deviation calculation works properly.", # 17 words
        ]
        stats = voice_metrics.compute_sentence_length_stats(sentences)
        self.assertEqual(stats["counts"], [2, 7, 17])
        self.assertAlmostEqual(stats["mean"], 8.666, places=2)
        self.assertGreater(stats["std_dev"], 6.0)
        self.assertEqual(stats["span"], 15)
        self.assertEqual(stats["min"], 2)
        self.assertEqual(stats["max"], 17)

    def test_compute_sentence_length_stats_empty(self):
        stats = voice_metrics.compute_sentence_length_stats([])
        self.assertEqual(stats["counts"], [])
        self.assertEqual(stats["mean"], 0.0)
        self.assertEqual(stats["std_dev"], 0.0)
        self.assertEqual(stats["span"], 0)

    def test_uniform_ai_text_triggers_variance_violation(self):
        # Monotonous synthetic paragraph where every sentence is exactly 10-11 words
        paragraphs = [
            "The quick brown fox jumps over the very lazy sleeping dog today. "
            "Another quick brown fox jumps over another very lazy sleeping dog. "
            "A third quick brown fox jumps over that same lazy sleeping dog. "
            "Every single sentence has almost the exact same number of words."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertTrue(any("monotonous" in v.lower() or "std dev" in v.lower() for v in violations))

    def test_dynamic_human_text_passes_all_checks(self):
        paragraphs = [
            "I love building systems that work quietly in the background — so people don’t have to. "
            "Over the past six years at Treering, I spearheaded our outbound communication engine, connecting with thousands of school coordinators and driving an unexpected 17% revenue surge through deeply personalized messaging. "
            "Clarity and empathy win every time.",
            "That loop of ideate, execute, and optimize is where I do my best work. "
            "Whether designing complex Salesforce workflows or crafting narrative email sequences, I focus on respecting the reader's time while earning their trust."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertEqual(violations, [])

    def test_type_token_ratio_flags_repetitive_text(self):
        # Extremely repetitive vocabulary of 100+ tokens
        repetitive = "Marketing strategy growth team systems. " * 25
        letter_data = {"body_paragraphs": [repetitive]}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertTrue(any("lexical diversity" in v.lower() or "type-token" in v.lower() for v in violations))

    def test_consecutive_opener_detection(self):
        paragraphs = [
            "I built the marketing pipeline from scratch. "
            "I managed five cross-functional specialists daily. "
            "I delivered $4M in pipeline value during Q3."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        violations = voice_metrics.analyze_voice_metrics(letter_data)
        self.assertTrue(any("consecutive sentences begin with" in v.lower() for v in violations))

    def test_custom_threshold_overrides_respected(self):
        paragraphs = [
            "This is a sentence. This is another sentence. This is yet another sentence. This is the last sentence."
        ]
        letter_data = {"body_paragraphs": paragraphs}
        # With very lenient thresholds, no violations
        lenient_rules = {
            "thresholds": {
                "sentence_std_dev_min": 0.0,
                "sentence_span_min": 0,
                "type_token_ratio_min": 0.1,
                "max_consecutive_same_opener": 10,
            }
        }
        violations = voice_metrics.analyze_voice_metrics(letter_data, rules=lenient_rules)
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
