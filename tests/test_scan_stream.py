import io
import json
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import scan_stream


class TestScanStream(unittest.TestCase):

    def test_emit_and_parse_events(self):
        buf = io.StringIO()
        emitter = scan_stream.ScanStreamEmitter(target_stream=buf)

        ev1 = emitter.emit_event(
            event_type="job_discovered",
            message="Found role on Greenhouse",
            job_id="gh_101",
            title="Senior Automation Engineer",
            company="Figma",
            score=88.5,
            source="Greenhouse",
        )

        ev2 = emitter.emit_event(
            event_type="scan_complete",
            message="Batch scan finished",
            details={"scanned": 10, "passed": 3},
        )

        lines = buf.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 2)

        parsed1 = scan_stream.parse_ndjson_line(lines[0])
        self.assertIsNotNone(parsed1)
        self.assertEqual(parsed1.event_type, "job_discovered")
        self.assertEqual(parsed1.company, "Figma")
        self.assertEqual(parsed1.score, 88.5)

        parsed2 = scan_stream.parse_ndjson_line(lines[1])
        self.assertIsNotNone(parsed2)
        self.assertEqual(parsed2.event_type, "scan_complete")
        self.assertEqual(parsed2.details["scanned"], 10)

    def test_monitor_state_update(self):
        state = scan_stream.ScanMonitorState()

        state.update(
            scan_stream.ScanEvent(event_type="job_discovered", message="Discovered")
        )
        state.update(
            scan_stream.ScanEvent(event_type="job_evaluating", message="Evaluating")
        )
        state.update(
            scan_stream.ScanEvent(
                event_type="job_evaluated", score=85.0, message="Evaluated High"
            )
        )
        state.update(
            scan_stream.ScanEvent(
                event_type="job_evaluated", score=65.0, message="Evaluated Mid"
            )
        )
        state.update(
            scan_stream.ScanEvent(event_type="job_filtered", message="Filtered")
        )
        state.update(scan_stream.ScanEvent(event_type="job_deduped", message="Deduped"))
        state.update(
            scan_stream.ScanEvent(event_type="scan_complete", message="Complete")
        )

        self.assertEqual(state.discovered, 1)
        self.assertEqual(state.evaluated, 2)
        self.assertEqual(state.high_fit, 1)
        self.assertEqual(state.filtered, 1)
        self.assertEqual(state.deduped, 1)
        self.assertTrue(state.is_complete)
        self.assertEqual(len(state.recent_events), 7)


if __name__ == "__main__":
    unittest.main()
