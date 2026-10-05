"""Offline evidence/guardrail simulation; no browser, network or adapter implementation."""

import copy
import hashlib
import json
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
DATA = json.loads((BASE / "FOLLOWUP_EVIDENCE.json").read_text(encoding="utf-8"))
EXPECTED_DESTINATION = "CASA EM ORDEM | PROMOS #1"
EXPECTED_BLOCKS = ["RADAR RECON 20261002", "Teste técnico no grupo sandbox.",
                   "https://example.com/radar-recon"]
EXPECTED_HASH = hashlib.sha256("\n".join(EXPECTED_BLOCKS).encode("utf-8")).hexdigest()


def draft_evidence_matches(record):
    """Checks this recorded sandbox projection only, not production destination identity."""
    actual_hash = hashlib.sha256("\n".join(record["blocks"]).encode("utf-8")).hexdigest()
    return (record["destination_name"] == EXPECTED_DESTINATION
            and actual_hash == EXPECTED_HASH and record["send_count"] == 1)


class FollowupEvidence(unittest.TestCase):
    def test_sandbox_preflight_projection(self):
        self.assertTrue(draft_evidence_matches(DATA["whatsapp"]))
        self.assertEqual(DATA["whatsapp"]["click_send_count"], 1)
        self.assertTrue(DATA["authorization"]["single_sandbox_message"])

    def test_destination_mismatch_projection(self):
        altered = copy.deepcopy(DATA["whatsapp"])
        altered["destination_name"] = "OTHER DESTINATION"
        self.assertFalse(draft_evidence_matches(altered))

    def test_message_mismatch_projection(self):
        altered = copy.deepcopy(DATA["whatsapp"])
        altered["blocks"][0] += " changed"
        self.assertFalse(draft_evidence_matches(altered))

    def test_missing_and_ambiguous_send_projection(self):
        for count in (0, 2):
            altered = copy.deepcopy(DATA["whatsapp"])
            altered["send_count"] = count
            self.assertFalse(draft_evidence_matches(altered))

    def test_post_send_evidence_and_limits(self):
        record = DATA["whatsapp"]
        self.assertTrue(record["post_composer_empty"])
        self.assertTrue(record["post_message_marker_present"])
        self.assertEqual(record["post_message_status"], "Enviada")
        self.assertFalse(record["persistent_destination_id_confirmed"])
        self.assertFalse(record["delivered_or_read_confirmed"])
        self.assertEqual(record["message_id_value"], "<redacted>")

    def test_tracking_roundtrip(self):
        record = DATA["shopee"]
        self.assertEqual(len(record["subids"]), 5)
        self.assertEqual("-".join(record["subids"]), record["advanced_utm_content"])
        self.assertEqual(record["custom_utm_content"], "recon20261002-sandbox---")
        self.assertTrue(record["product_title_confirmed"])

    def test_ml_results_and_negative_attempt(self):
        self.assertTrue(DATA["ml"]["bar_short_equal_generator_short"])
        self.assertTrue(DATA["ml"]["landing_expected_product_observed"])
        self.assertEqual(DATA["ml"]["invalid_error"], "Não foi possível gerar o link.")
        self.assertFalse(DATA["authorization"]["auto_enabled"])

    def test_candidate_registry_and_sanitization(self):
        self.assertEqual(DATA["selector_registry"]["status"], "CANDIDATE")
        for entry in DATA["selector_registry"]["entries"]:
            for key in ("primary", "fallback_1", "fallback_2", "ambiguity", "states", "evidence"):
                self.assertTrue(entry[key])
        raw = json.dumps(DATA, ensure_ascii=False)
        for private in ("gads_t_sig", "mmp_pid", "uls_trackid", "matt_tool=", "ref=",
                        "rblayering", "@g.us", "3EB03", "Melquíades"):
            self.assertNotIn(private, raw)


if __name__ == "__main__":
    print("Sandbox canonical SHA256:", EXPECTED_HASH)
    unittest.main(verbosity=2)
