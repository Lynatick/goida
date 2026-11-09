import base64
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from combined_subscription import build_combined_subscriptions
from subscription_converter import ConversionError


class CombinedSubscriptionTest(unittest.TestCase):
    def test_mixed_encodings_duplicates_and_repeated_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror = root / "githubmirror"
            mirror.mkdir()
            first = "trojan://secret@one.example:443#First"
            second = "trojan://secret@two.example:443#Second"
            mirror.joinpath("1.txt").write_text(first + "\n" + first)
            mirror.joinpath("2.txt").write_text(base64.b64encode(
                ("# Comment\n" + first + "\n" + second).encode()
            ).decode())
            mirror.joinpath("all.txt").write_text("trojan://old@old.example:443")
            with redirect_stdout(io.StringIO()):
                paths = build_combined_subscriptions(root)
            self.assertEqual(paths, [
                "githubmirror/all.txt", "raw/all.txt", "hiddify/all.json",
                "raw/by-type/trojan.json", "hiddify/by-type/trojan.json",
                "hiddify/groups/trojan1.json", "hiddify/groups/trojan-list.txt",
                "hiddify/groups/all.txt", "githubmirror/by-type/trojan.txt", "protocol-stats.json",
                "subscription-stats.json"
            ])
            self.assertEqual(mirror.joinpath("all.txt").read_text(), first + "\n" + second + "\n")
            raw = json.loads(root.joinpath("raw/all.txt").read_text())
            self.assertEqual([item["server"] for item in raw["outbounds"]], ["one.example", "two.example"])
            profile = json.loads(root.joinpath("hiddify/all.json").read_text())
            self.assertEqual(profile["route"]["final"], "Выбор сервера")
            self.assertEqual(profile["outbounds"][1]["outbounds"], [item["tag"] for item in raw["outbounds"]])
            stats = json.loads(root.joinpath("subscription-stats.json").read_text())
            self.assertEqual(stats["all"], {"configs": 2, "excluded": 0})
            self.assertEqual(stats["1"], {"configs": 2, "excluded": 0})
            before = {path: root.joinpath(path).read_text() for path in paths}
            with redirect_stdout(io.StringIO()):
                build_combined_subscriptions(root)
            self.assertEqual(before, {path: root.joinpath(path).read_text() for path in paths})

    def test_native_json_cannot_overwrite_existing_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror = root / "githubmirror"
            mirror.mkdir()
            mirror.joinpath("1.txt").write_text(json.dumps({
                "outbounds": [{"type": "trojan", "tag": "proxy"}],
                "route": {"rules": [{"outbound": "proxy"}]}
            }))
            mirror.joinpath("all.txt").write_text("previous")
            with self.assertRaises(ConversionError):
                build_combined_subscriptions(root)
            self.assertEqual(mirror.joinpath("all.txt").read_text(), "previous")
            self.assertFalse(root.joinpath("raw/all.txt").exists())

    def test_corrupt_line_does_not_abort_combination_of_valid_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror = root / "githubmirror"
            mirror.mkdir()
            first = "trojan://secret@one.example:443"
            second = "trojan://secret@two.example:443"
            mirror.joinpath("7.txt").write_text(first + "\ny+'ù`\\x84 corrupted data\n")
            mirror.joinpath("8.txt").write_text(second)
            output = io.StringIO()
            with redirect_stdout(output):
                build_combined_subscriptions(root)
            self.assertEqual(mirror.joinpath("all.txt").read_text(), first + "\n" + second + "\n")
            self.assertIn("пропущено некорректных строк без URI: 1", output.getvalue())
            self.assertEqual(len(json.loads(root.joinpath("raw/all.txt").read_text())["outbounds"]), 2)

    def test_only_corrupt_lines_keep_existing_aggregate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mirror = root / "githubmirror"
            mirror.mkdir()
            mirror.joinpath("7.txt").write_text("# metadata\ncorrupted line")
            mirror.joinpath("all.txt").write_text("previous")
            with redirect_stdout(io.StringIO()), self.assertRaises(ConversionError):
                build_combined_subscriptions(root)
            self.assertEqual(mirror.joinpath("all.txt").read_text(), "previous")


if __name__ == "__main__":
    unittest.main()
