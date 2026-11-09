from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from protocol_subscriptions import GROUP_BASE_URL, GROUP_SIZE, build_protocol_subscriptions
from subscription_converter import ConversionError, convert_subscription
from subscription_report import render_group_rows, render_subscription_rows


class ProtocolSubscriptionTest(unittest.TestCase):
    def test_single_protocol_groups_preserve_tls_and_exclude_invalid_node(self):
        vless = {
            "type": "vless", "tag": "VLESS", "server": "vless.example", "server_port": 443,
            "uuid": "cbb3f877-d1fb-344c-87a9-d153bffd5484",
            "tls": {"enabled": True, "reality": {"enabled": True, "public_key": "test-key"}}
        }
        trojan = {"type": "trojan", "tag": "Trojan", "server": "trojan.example", "server_port": 443, "password": "secret"}
        config = {"outbounds": [vless, trojan, dict(vless, uuid="invalid"), dict(trojan, server_port=0)], "endpoints": []}
        original = deepcopy(config)
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            paths, counts = build_protocol_subscriptions(config, directory)
            self.assertEqual(config, original)
            self.assertEqual(counts, {"trojan": 1, "vless": 1})
            for kind in counts:
                raw = json.loads(Path(directory, f"raw/by-type/{kind}.json").read_text())
                self.assertEqual({node["type"] for node in raw["outbounds"]}, {kind})
                profile = json.loads(Path(directory, f"hiddify/by-type/{kind}.json").read_text())
                self.assertEqual(profile["outbounds"][2:], raw["outbounds"])
                self.assertEqual(profile["outbounds"][1]["outbounds"], [raw["outbounds"][0]["tag"]])
            self.assertEqual(json.loads(Path(directory, "protocol-stats.json").read_text())["excluded"], 2)
            self.assertIn("hiddify/by-type/vless.json", paths)

    def test_invalid_dataset_or_native_rules_do_not_overwrite_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory, "protocol-stats.json")
            previous.write_text("previous")
            for config in (
                {"outbounds": [{"type": "trojan", "server": "example.com", "server_port": 443}]},
                {"outbounds": [{"type": "trojan"}], "route": {"rules": [{"outbound": "proxy"}]}}
            ):
                with self.assertRaises(ConversionError):
                    build_protocol_subscriptions(config, directory)
                self.assertEqual(previous.read_text(), "previous")

    def test_table_links_only_in_combined_row_and_use_copy_buttons(self):
        rows = {"all": {"configs": 2, "excluded": 0}, "1": {"configs": 2, "excluded": 0}}
        html = render_subscription_rows(rows, {"vless": 2})
        self.assertIn('rowspan="2"', html)
        self.assertEqual(html.count('data-copy="protocol-vless"'), 1)
        self.assertIn('/hiddify/by-type/vless.json', html)
        self.assertIn('>vless.json</a>', html)

    def test_grouped_profiles_and_link_lists_have_2000_nodes_at_most(self):
        node = {
            "type": "vless", "server": "vless.example", "server_port": 443,
            "uuid": "cbb3f877-d1fb-344c-87a9-d153bffd5484"
        }
        nodes = [dict(node, tag=f"{index}. Node") for index in range(1, GROUP_SIZE + 2)]
        trojan = {"type": "trojan", "tag": "Trojan", "server": "trojan.example", "server_port": 443, "password": "secret"}
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            paths, counts = build_protocol_subscriptions({"outbounds": nodes + [trojan]}, root)
            self.assertEqual(counts, {"vless": 2001, "trojan": 1})
            first = json.loads(root.joinpath("hiddify/groups/vless1.json").read_text())
            second = json.loads(root.joinpath("hiddify/groups/vless2.json").read_text())
            self.assertEqual(len(first["outbounds"]) - 2, GROUP_SIZE)
            self.assertEqual(len(second["outbounds"]) - 2, 1)
            self.assertEqual(first["outbounds"][1]["outbounds"], [node["tag"] for node in nodes[:GROUP_SIZE]])
            links = root.joinpath("hiddify/groups/vless-list.txt").read_text().splitlines()
            self.assertEqual(links, [f"{GROUP_BASE_URL}/hiddify/groups/vless{number}.json" for number in (1, 2)])
            self.assertEqual(root.joinpath("hiddify/groups/all.txt").read_text().splitlines(), [
                f"{GROUP_BASE_URL}/hiddify/groups/trojan1.json", *links
            ])
            self.assertIn("hiddify/groups/vless2.json", paths)
            stats = json.loads(root.joinpath("protocol-stats.json").read_text())
            self.assertEqual(stats["groups"], {"trojan": 1, "vless": 2})
            self.assertEqual(stats["group_size"], GROUP_SIZE)
            old_directory = root / "hiddify/groups/vless"
            old_directory.mkdir()
            old_directory.joinpath("1.json").write_text("old")
            old_directory.joinpath("list.txt").write_text("old")
            build_protocol_subscriptions({"outbounds": nodes[:1]}, root)
            self.assertFalse(root.joinpath("hiddify/groups/vless2.json").exists())
            self.assertFalse(root.joinpath("hiddify/groups/trojan1.json").exists())
            self.assertFalse(root.joinpath("hiddify/groups/trojan-list.txt").exists())
            self.assertFalse(old_directory.exists())

    def test_group_table_links_and_counts(self):
        html = render_group_rows({"vless": 2001})
        self.assertIn('data-copy="group-vless-1"', html)
        self.assertIn('data-copy="group-vless-2"', html)
        self.assertIn('rowspan="2"', html)
        self.assertIn('data-copy="group-list-vless"', html)
        self.assertIn('>vless2.json</a>', html)
        self.assertIn('>2\u202f000</td>', html)


    def test_original_uri_files_preserve_links_and_exclude_unmatched_or_invalid(self):
        first = "hy2://secret@hy.example:443?sni=example.com#Original"
        second = "trojan://secret@trojan.example:443#Original"
        config, _ = convert_subscription(first + "\n" + second)
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            root = Path(directory)
            mirror = root / "githubmirror"
            mirror.mkdir()
            mirror.joinpath("all.txt").write_text(
                first + "\n" + first + "\n" + second + "\n"
                "broken line\ntrojan://missing-auth.example:443\n"
                "trojan://other@not-in-json.example:443\n"
            )
            paths, _ = build_protocol_subscriptions(config, root)
            self.assertEqual(mirror.joinpath("by-type/hysteria2.txt").read_text(), first + "\n")
            self.assertEqual(mirror.joinpath("by-type/trojan.txt").read_text(), second + "\n")
            stats = json.loads(root.joinpath("protocol-stats.json").read_text())
            self.assertEqual(stats["uri_types"], {"hysteria2": 1, "trojan": 1})
            self.assertIn("githubmirror/by-type/hysteria2.txt", paths)
            html = render_subscription_rows({"all": {"configs": 2, "excluded": 0}}, stats["types"], stats["uri_types"])
            self.assertLess(html.index("hysteria2.json"), html.index("hysteria2.txt"))
            self.assertIn('data-copy="protocol-uri-hysteria2"', html)
            self.assertIn('/githubmirror/by-type/hysteria2.txt', html)


if __name__ == "__main__":
    unittest.main()
