"""Offline artifact checks. Does not certify or implement a browser adapter."""

import json
from html.parser import HTMLParser
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent
FIXTURES = json.loads((BASE / "FIXTURES_SANITIZED.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((BASE / "SELECTOR_REGISTRY_CANDIDATE.json").read_text(encoding="utf-8"))


class Fragment(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class ReconArtifacts(unittest.TestCase):
    def attrs(self, name, tag):
        found = [a for t, a in Fragment(FIXTURES["fragments"][name]).elements if t == tag]
        self.assertEqual(len(found), 1)
        return found[0]

    def test_ml_url_and_empty_submit_state(self):
        self.assertEqual(self.attrs("ml_url", "textarea")["id"], "url-0")
        self.assertEqual(self.attrs("ml_url", "textarea")["maxlength"], "1000000")
        self.assertIn("disabled", self.attrs("ml_generate_empty", "button"))
        self.assertTrue(FIXTURES["semantic_states"]["ml_invalid_url"]["generate_enabled"])
        self.assertFalse(FIXTURES["semantic_states"]["ml_invalid_url"]["submitted"])

    def test_ml_label_validation_evidence(self):
        attrs = self.attrs("ml_label_invalid", "input")
        self.assertEqual(attrs["maxlength"], "30")
        self.assertEqual(attrs["aria-invalid"], "true")
        self.assertEqual(attrs["data-testid"], "input-create-label")

    def test_toolbar_candidate_unique_missing_and_duplicate(self):
        html = FIXTURES["fragments"]["ml_toolbar_share"]

        def cardinality(fragment):
            return sum(a.get("data-testid") == "generate_link_button"
                       for _, a in Fragment(fragment).elements)

        self.assertEqual(cardinality(html), 1)
        self.assertEqual(cardinality(html.replace("generate_link_button", "changed")), 0)
        self.assertEqual(cardinality(html + html), 2)
        # Cardinality evidence only: a future adapter must refuse 0 and 2.

    def test_shopee_context_and_tracking_evidence(self):
        attrs = self.attrs("sp_detail_product", "a")
        self.assertEqual(attrs["href"], "https://shopee.com.br/product/1487590844/22193956904")
        self.assertEqual(self.attrs("sp_subid_1", "input")["id"], "customLink_sub_id1")
        state = FIXTURES["semantic_states"]["sp_custom"]
        self.assertEqual(state["max_subids_documented"], 5)
        self.assertEqual(state["error"], "Número inválido")
        self.assertFalse(state["submitted"])

    def test_registry_has_evidence_fallbacks_and_candidate_status(self):
        self.assertEqual(REGISTRY["status"], "CANDIDATE_NOT_APPROVED")
        for entry in REGISTRY["entries"]:
            for key in ("capability", "page", "element", "primary_selector", "fallback_1",
                        "fallback_2", "why_stable", "ambiguity_risk", "observed_states", "evidence"):
                self.assertTrue(entry[key], (entry["element"], key))
            fixture = entry["fixture"]
            if fixture.startswith("semantic_states."):
                self.assertIn(fixture.split(".", 1)[1], FIXTURES["semantic_states"])
            else:
                self.assertIn(fixture, FIXTURES["fragments"])

    def test_no_private_header_or_credential_fixture(self):
        # Narrow denylist, reviewed alongside the document; not a universal secret scanner.
        raw = json.dumps(FIXTURES, ensure_ascii=False).lower()
        for forbidden in ("nav-header-menu", "g-recaptcha-response", "access_token",
                          "refresh_token", "authorization:", "set-cookie", "rafael",
                          "melquíades", "trace_id", "rblayering"):
            self.assertNotIn(forbidden, raw)
        api = FIXTURES["semantic_states"]["sp_api_no_access"]
        self.assertFalse(api["app_id_available"])
        self.assertFalse(api["secret_available"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
