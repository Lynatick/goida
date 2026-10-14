import base64
from contextlib import redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from combined_subscription import build_combined_subscriptions
from subscription_report import subscription_counts


class SubscriptionReportTest(unittest.TestCase):
    def test_conversion_exclusions_and_base64(self):
        content = "# comment\ntrojan://secret@one.example:443\nunsupported://node\nbroken line\n"
        expected = {"configs": 1, "excluded": 2}
        self.assertEqual(subscription_counts(content), expected)
        self.assertEqual(subscription_counts(base64.b64encode(content.encode()).decode()), expected)

    def test_all_invalid_entries_and_empty_source(self):
        self.assertEqual(subscription_counts("unsupported://one\nbroken line"), {"configs": 0, "excluded": 2})
        self.assertEqual(subscription_counts(""), {"configs": 0, "excluded": 0})
        self.assertEqual(subscription_counts('{"outbounds": "invalid"}'), {"configs": None, "excluded": None})

    def test_native_config_counts_servers_without_selection_groups(self):
        content = json.dumps({
            "outbounds": [{"type": "direct"}, {"type": "selector"}, {"type": "trojan"}],
            "endpoints": [{"type": "wireguard"}]
        })
        self.assertEqual(subscription_counts(content), {"configs": 2, "excluded": 0})

    def test_combined_report_deduplicates_and_updates_homepage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror = root / "githubmirror"
            mirror.mkdir()
            node = "trojan://secret@one.example:443"
            mirror.joinpath("1.txt").write_text(node + "\nunsupported://one\nbroken line")
            mirror.joinpath("2.txt").write_text(node + "\nunsupported://one")
            homepage = root / "index.html"
            homepage.write_text("before<!-- subscription-updated:start -->old time<!-- subscription-updated:end --><!-- subscription-report:start -->old<!-- subscription-report:end -->after")
            with redirect_stdout(io.StringIO()), patch("subscription_report.datetime") as clock:
                clock.now.return_value = datetime(2026, 10, 14, 14, 28, 0, tzinfo=ZoneInfo("Europe/Moscow"))
                paths = build_combined_subscriptions(root)
            report = json.loads(root.joinpath("subscription-stats.json").read_text())
            self.assertEqual(report["all"], {"configs": 1, "excluded": 2})
            self.assertEqual(report["1"], {"configs": 1, "excluded": 2})
            self.assertEqual(report["2"], {"configs": 1, "excluded": 1})
            self.assertIn("index.html", paths)
            html = homepage.read_text()
            self.assertTrue(html.startswith("before"))
            self.assertTrue(html.endswith("after"))
            self.assertIn('<time datetime="2026-10-14T14:28:00+03:00">14.10.2026 14:28:00 МСК</time>', html)
            self.assertNotIn("old time", html)
            clock.now.assert_called_once_with(ZoneInfo("Europe/Moscow"))
            self.assertIn('<th scope="row">Все</th>', html)
            self.assertIn('<td class="numeric">1</td><td class="numeric">2</td>', html)
            self.assertIn('data-copy="hiddify-all-json"', html)
            self.assertIn('data-copy="githubmirror-2-txt"', html)
            self.assertNotIn("secret", root.joinpath("subscription-stats.json").read_text())


if __name__ == "__main__":
    unittest.main()
