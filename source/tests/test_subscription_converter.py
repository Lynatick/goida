import base64
import ast
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from subscription_converter import (
    ConversionError, connection_count, convert_subscription, save_raw_subscription
)


USER_ID = "cbb3f877-d1fb-344c-87a9-d153bffd5484"


def encode(value):
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def vmess(**overrides):
    fields = {
        "add": "v35.hdacd.com", "port": "30835", "id": USER_ID,
        "aid": 2, "ps": "🇭🇰_HK_中国香港->🇫🇷_FR_法国", "net": "tcp"
    }
    fields.update(overrides)
    return "vmess://" + encode(json.dumps(fields, ensure_ascii=False))


def singbox_config():
    return {
        "outbounds": [{
            "type": "vless", "tag": "proxy", "server": "host.test",
            "server_port": 443, "uuid": USER_ID,
            "tls": {
                "enabled": True, "server_name": "example.com",
                "reality": {"enabled": True, "public_key": "key", "short_id": "abcd"}
            }
        }],
        "route": {"rules": [{"domain_suffix": ["example.com"], "outbound": "proxy"}]},
        "dns": {"servers": [{"type": "udp", "tag": "dns", "server": "1.1.1.1"}]},
        "inbounds": [{"type": "mixed", "listen": "127.0.0.1", "listen_port": 1080}]
    }


def xray_config():
    return {
        "remarks": "Xray config",
        "outbounds": [{
            "protocol": "vless", "tag": "proxy",
            "settings": {"vnext": [{
                "address": "host.test", "port": 443,
                "users": [{"id": USER_ID, "encryption": "none"}]
            }]},
            "streamSettings": {
                "network": "tcp", "security": "reality",
                "realitySettings": {
                    "serverName": "example.com", "publicKey": "key", "shortId": "abcd"
                }
            }
        }],
        "routing": {"rules": [{"type": "field", "domain": ["example.com"], "outboundTag": "proxy"}]},
        "dns": {"servers": ["1.1.1.1"]}
    }


class SubscriptionConversionTest(unittest.TestCase):
    def test_vmess_matches_requested_example(self):
        config, issues = convert_subscription(vmess())
        self.assertEqual(config, {
            "outbounds": [{
                "type": "vmess", "tag": "1. 🇭🇰_HK_中国香港->🇫🇷_FR_法国",
                "server": "v35.hdacd.com", "server_port": 30835,
                "uuid": USER_ID, "security": "auto", "alter_id": 2,
                "authenticated_length": True, "packet_encoding": "xudp"
            }],
            "endpoints": []
        })
        self.assertFalse(issues)

    def test_base64_subscription_comments_and_unique_tags(self):
        text = "# comment\n" + vmess() + "\n// profile metadata\n" + vmess()
        encoded = encode(text)
        wrapped = "\n".join(encoded[i:i + 50] for i in range(0, len(encoded), 50))
        config, issues = convert_subscription(wrapped)
        self.assertEqual(len(config["outbounds"]), 2)
        self.assertEqual([item["tag"] for item in config["outbounds"]], [
            "1. 🇭🇰_HK_中国香港->🇫🇷_FR_法国",
            "2. 🇭🇰_HK_中国香港->🇫🇷_FR_法国",
        ])
        self.assertFalse(issues)

    def test_vmess_websocket_preserves_tls_and_early_data(self):
        config, _ = convert_subscription(vmess(
            net="ws", host="cdn.example.com", path="/ws?ed=2048", tls="tls",
            sni="tls.example.com", alpn="h2,http/1.1", allowInsecure="false"
        ))
        outbound = config["outbounds"][0]
        self.assertEqual(outbound["transport"], {
            "type": "ws", "path": "/ws", "headers": {"Host": "cdn.example.com"},
            "max_early_data": 2048, "early_data_header_name": "Sec-WebSocket-Protocol"
        })
        self.assertEqual(outbound["tls"], {
            "enabled": True, "server_name": "tls.example.com",
            "insecure": False, "alpn": ["h2", "http/1.1"]
        })

    def test_vless_ipv6_reality_and_grpc(self):
        link = (
            f"vless://{USER_ID}@[2001:db8::1]:443?security=reality&pbk=public-key"
            "&sid=abcdef&fp=chrome&sni=example.com&type=grpc&serviceName=tunnel#Test"
        )
        config, _ = convert_subscription(link)
        outbound = config["outbounds"][0]
        self.assertEqual(outbound["server"], "2001:db8::1")
        self.assertEqual(outbound["transport"], {"type": "grpc", "service_name": "tunnel"})
        self.assertEqual(outbound["tls"]["reality"]["public_key"], "public-key")
        self.assertEqual(outbound["tls"]["utls"]["fingerprint"], "chrome")

    def test_trojan_password_and_explicit_false(self):
        config, _ = convert_subscription("trojan://p%40ss%3Aword@host.test:443?allowInsecure=0")
        outbound = config["outbounds"][0]
        self.assertEqual(outbound["password"], "p@ss:word")
        self.assertEqual(outbound["tls"], {"enabled": True, "insecure": False})

    def test_shadowsocks_supported_encodings_and_plugin(self):
        links = [
            "ss://" + encode("aes-256-gcm:pass:word") + "@host.test:8388#One",
            "ss://" + encode("aes-256-gcm:pass:word@host.test:8388") + "#Two",
            "ss://aes-256-gcm:pass%3Aword@host.test:8388#Three"
        ]
        for link in links:
            with self.subTest(link=link):
                config, _ = convert_subscription(link)
                outbound = config["outbounds"][0]
                self.assertEqual(outbound["method"], "aes-256-gcm")
                self.assertEqual(outbound["password"], "pass:word")
                self.assertEqual(outbound["server_port"], 8388)
        config, _ = convert_subscription(links[0].split("#")[0] + "?plugin=obfs-local%3Bobfs%3Dhttp")
        self.assertEqual(config["outbounds"][0]["plugin_opts"], "obfs=http")

    def test_legacy_shadowsocks_json(self):
        link = "ss://" + encode(json.dumps({
            "add": "host.test", "port": 8388, "scy": "aes-128-gcm", "id": "pass"
        }))
        config, _ = convert_subscription(link)
        self.assertEqual(config["outbounds"][0]["password"], "pass")

    def test_standard_base64_shadowsocks_containing_slash(self):
        encoded = base64.b64encode(b"aes-256-gcm:???@host.test:8388").decode()
        self.assertIn("/", encoded)
        config, _ = convert_subscription("ss://" + encoded)
        self.assertEqual(config["outbounds"][0]["password"], "???")

    def test_hysteria_tuic_and_anytls(self):
        links = [
            "hy2://user%3Apass@host.test?obfs=salamander&obfs-password=secret&sni=example.com",
            f"tuic://{USER_ID}:pass@host.test:443?congestion_control=bbr&udp_relay_mode=native",
            "anytls://password@host.test:443?sni=example.com"
        ]
        config, issues = convert_subscription("\n".join(links))
        self.assertFalse(issues)
        self.assertEqual([item["type"] for item in config["outbounds"]], ["hysteria2", "tuic", "anytls"])
        self.assertEqual(config["outbounds"][0]["password"], "user:pass")
        self.assertEqual(config["outbounds"][0]["server_port"], 443)
        self.assertEqual(config["outbounds"][1]["password"], "pass")

    def test_unsupported_transports_and_invalid_nodes_reported(self):
        text = "\n".join([
            vmess(), "vmess://invalid", f"vless://{USER_ID}@host.test:443?type=xhttp",
            f"vless://{USER_ID}@host.test:443?security=reality", "ssr://unsupported"
        ])
        config, issues = convert_subscription(text)
        self.assertEqual(len(config["outbounds"]), 1)
        self.assertEqual(sum(issues.values()), 4)
        self.assertIn("Неподдерживаемый транспорт: xhttp", issues)

    def test_invalid_input_does_not_overwrite_existing_raw_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "1.txt"
            path.write_text("existing data")
            for content in ("", "<html>404</html>", "vmess://broken"):
                with self.subTest(content=content), self.assertRaises(ValueError):
                    save_raw_subscription(content, path)
                self.assertEqual(path.read_text(), "existing data")

    def test_same_filename_utf8_json_and_existing_singbox_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw" / "1.txt"
            with redirect_stdout(io.StringIO()):
                config = save_raw_subscription(vmess(), path)
            text = path.read_text()
            self.assertIn("🇭🇰", text)
            self.assertEqual(json.loads(text), config)
            converted, _ = convert_subscription(text)
            self.assertEqual(converted, config)

    def test_full_singbox_config_preserves_routing_dns_reality_and_tags(self):
        original = singbox_config()
        config, issues = convert_subscription(json.dumps(original))
        self.assertEqual(config, original)
        self.assertFalse(issues)
        self.assertNotIn("endpoints", config)

    def test_full_xray_config_preserves_protocol_and_engine_specific_fields(self):
        original = xray_config()
        config, issues = convert_subscription(json.dumps(original))
        self.assertEqual(config, original)
        self.assertFalse(issues)
        self.assertNotIn("type", config["outbounds"][0])

    def test_json_array_keeps_each_full_config_and_conflicting_tags_separate(self):
        dataset = [singbox_config(), xray_config()]
        dataset[1]["routing"]["rules"][0]["domain"] = ["different.test"]
        config, issues = convert_subscription(json.dumps(dataset))
        self.assertEqual(config, dataset)
        self.assertFalse(issues)
        self.assertEqual(connection_count(config), 2)
        self.assertEqual(config[0]["outbounds"][0]["tag"], "proxy")
        self.assertEqual(config[1]["outbounds"][0]["tag"], "proxy")

    def test_base64_json_array_is_saved_under_same_filename(self):
        dataset = [singbox_config(), xray_config()]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "raw" / "21.txt"
            with redirect_stdout(io.StringIO()):
                save_raw_subscription(encode(json.dumps(dataset)), path)
            self.assertEqual(json.loads(path.read_text()), dataset)

    def test_endpoint_only_json_config_preserved(self):
        config = {"endpoints": [{"type": "wireguard", "tag": "vpn", "private_key": "private-key"}]}
        result, _ = convert_subscription(json.dumps([config]))
        self.assertEqual(result, [config])
        self.assertEqual(connection_count(result), 1)

    def test_invalid_json_array_does_not_partially_overwrite_existing_output(self):
        datasets = [[], [singbox_config(), 42], [singbox_config(), {"outbounds": "invalid"}],
                    [{"outbounds": [{}]}], [[singbox_config()]]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "21.txt"
            path.write_text("existing data")
            for dataset in datasets:
                with self.subTest(dataset=dataset), self.assertRaises(ConversionError):
                    save_raw_subscription(json.dumps(dataset), path)
                self.assertEqual(path.read_text(), "existing data")

    def test_main_saves_and_uploads_original_and_converted_file(self):
        module = ast.parse((Path(__file__).parents[1] / "main.py").read_text())
        functions = [
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name in {
                "main", "ensure_github_credentials", "fetch_source",
                "convert_source", "upload_files", "report_failed_sources"
            }
        ]
        original = "githubmirror/1.txt"
        raw = "raw/1.txt"
        save = Mock()
        upload = Mock()
        convert = Mock()
        hiddify = Mock(return_value=["hiddify/1.json"])
        namespace = {
            "GITHUB_TOKEN": "dummy-token", "REPO_NAME_1": "owner/repo",
            "URLS": ["source"], "LOCAL_PATHS": [original], "REMOTE_PATHS": [original],
            "requests": Mock(RequestException=RuntimeError),
            "fetch_data": Mock(return_value="data"), "save_to_local_file": save,
            "save_raw_subscription": convert, "upload_to_github": upload,
            "save_hiddify_subscription": hiddify,
            "build_combined_subscriptions": Mock(return_value=[
                "githubmirror/all.txt", "raw/all.txt", "hiddify/all.json"
            ]),
            "print_progress": Mock(), "print": Mock(), "os": os
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), "main.py", "exec"), namespace)
        namespace["main"]()
        save.assert_called_once_with(original, "data")
        convert.assert_called_once_with("data", raw)
        hiddify.assert_called_once_with(convert.return_value, "hiddify/1.json")
        self.assertEqual([call.args for call in upload.call_args_list], [
            (original, original), (raw, raw), ("hiddify/1.json", "hiddify/1.json"),
            ("githubmirror/all.txt", "githubmirror/all.txt"),
            ("raw/all.txt", "raw/all.txt"), ("hiddify/all.json", "hiddify/all.json")
        ])
        upload.reset_mock()
        namespace["build_combined_subscriptions"].return_value = []
        convert.side_effect = ConversionError("Unsupported source")
        namespace["main"]()
        upload.assert_called_once_with(original, original)

    def test_local_only_skips_token_upload_and_unavailable_sources(self):
        module = ast.parse((Path(__file__).parents[1] / "main.py").read_text())
        functions = [
            node for node in module.body
            if isinstance(node, ast.FunctionDef) and node.name in {
                "main", "ensure_github_credentials", "fetch_source",
                "convert_source", "upload_files", "report_failed_sources"
            }
        ]
        save = Mock()
        upload = Mock()
        convert = Mock()
        namespace = {
            "GITHUB_TOKEN": None, "REPO_NAME_1": "owner/repo",
            "URLS": ["missing", "working"],
            "LOCAL_PATHS": ["githubmirror/1.txt", "githubmirror/2.txt"],
            "REMOTE_PATHS": ["githubmirror/1.txt", "githubmirror/2.txt"],
            "fetch_data": Mock(side_effect=[RuntimeError("404"), "data"]),
            "requests": Mock(RequestException=RuntimeError),
            "save_to_local_file": save, "save_raw_subscription": convert,
            "save_hiddify_subscription": Mock(return_value=["hiddify/2.json"]),
            "build_combined_subscriptions": Mock(return_value=[]),
            "upload_to_github": upload, "print_progress": Mock(),
            "print": Mock(), "os": os, "getpass": Mock()
        }
        exec(compile(ast.Module(body=functions, type_ignores=[]), "main.py", "exec"), namespace)
        namespace["main"](local_only=True)
        namespace["getpass"].assert_not_called()
        namespace["build_combined_subscriptions"].assert_called_once_with()
        upload.assert_not_called()
        save.assert_called_once_with("githubmirror/2.txt", "data")
        convert.assert_called_once_with("data", "raw/2.txt")
        self.assertTrue(any(
            "raw/1.txt; hiddify/1.json" in call.args[0]
            for call in namespace["print"].call_args_list
        ))


if __name__ == "__main__":
    unittest.main()
