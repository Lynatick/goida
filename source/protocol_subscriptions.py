"""Split a combined sing-box dataset into validated single-protocol subscriptions."""

import argparse
from collections import Counter
from copy import deepcopy
import json
import re
from pathlib import Path
from uuid import UUID

from hiddify_subscription import NON_PROXY_TYPES, build_hiddify_config
from subscription_converter import ConversionError, SS_METHODS, decode_base64, server_fields, uri_outbound, validate_json_config


SUPPORTED_TYPES = {"vmess", "vless", "trojan", "shadowsocks", "hysteria2", "tuic", "anytls"}
GROUP_SIZE = 2000
GROUP_BASE_URL = "https://raw.githubusercontent.com/Lynatick/goida/main"


def validate_node(node):
    kind = node.get("type")
    if kind not in SUPPORTED_TYPES:
        raise ConversionError("Неподдерживаемый тип подключения")
    server_fields(node.get("server"), node.get("server_port"))
    if type(node.get("server_port")) is not int:
        raise ConversionError("Порт должен быть целым числом")
    if kind in ("vmess", "vless", "tuic"):
        UUID(node.get("uuid", ""))
    if kind in ("trojan", "shadowsocks", "hysteria2", "tuic", "anytls"):
        if not isinstance(node.get("password"), str):
            raise ConversionError("Не указан пароль")
    if kind == "shadowsocks" and node.get("method") not in SS_METHODS:
        raise ConversionError("Неподдерживаемое шифрование Shadowsocks")
    if kind == "vmess" and (type(node.get("alter_id", 0)) is not int or node.get("alter_id", 0) < 0):
        raise ConversionError("Некорректный alter_id")
    if kind == "vmess" and node.get("security", "auto") not in {
        "auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305", "aes-128-ctr"
    }:
        raise ConversionError("Неподдерживаемое шифрование VMess")
    if kind == "vless" and node.get("flow", "") not in ("", "xtls-rprx-vision"):
        raise ConversionError("Неподдерживаемый flow VLESS")
    transport = node.get("transport")
    if transport is not None and (not isinstance(transport, dict) or transport.get("type") not in {
        "ws", "grpc", "http", "httpupgrade", "quic"
    }):
        raise ConversionError("Неподдерживаемый транспорт")
    tls = node.get("tls")
    if tls is not None:
        if not isinstance(tls, dict):
            raise ConversionError("Некорректные параметры TLS")
        reality = tls.get("reality")
        if reality is not None and (not isinstance(reality, dict) or
                                   reality.get("enabled") and not reality.get("public_key")):
            raise ConversionError("Некорректные параметры Reality")


def group_subscription_outputs(kind, nodes):
    outputs = {}
    links = []
    for number, start in enumerate(range(0, len(nodes), GROUP_SIZE), start=1):
        group = {"outbounds": nodes[start:start + GROUP_SIZE], "endpoints": []}
        path = f"hiddify/groups/{kind}{number}.json"
        outputs[path] = build_hiddify_config(group)
        links.append(f"{GROUP_BASE_URL}/{path}")
    outputs[f"hiddify/groups/{kind}-list.txt"] = "\n".join(links) + "\n"
    return outputs, links


def remove_stale_group_files(root, outputs):
    group_root = Path(root) / "hiddify/groups"
    flat_names = re.compile(rf"(?:{'|'.join(sorted(SUPPORTED_TYPES))})\d+\.json")
    for path in group_root.rglob("*"):
        if not path.is_file():
            continue
        if path.parent == group_root:
            generated = path.name == "all.txt" or path.name in {
                f"{kind}-list.txt" for kind in SUPPORTED_TYPES
            } or bool(flat_names.fullmatch(path.name))
        else:
            generated = path.parent.name in SUPPORTED_TYPES and (
                path.name == "list.txt" or (path.suffix == ".json" and path.stem.isdigit())
            )
        if generated and path.relative_to(root).as_posix() not in outputs:
            path.unlink()
    for kind in SUPPORTED_TYPES:
        directory = group_root / kind
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def build_protocol_subscriptions(config, root="."):
    validate_json_config(config)
    # A single-protocol dataset cannot retain arbitrary full-profile routing.
    if any(key not in {"outbounds", "endpoints"} for key in config):
        raise ConversionError("Для разделения нужен общий список подключений без правил полного профиля")
    groups = {}
    issues = Counter()
    for node in config.get("outbounds", []) + config.get("endpoints", []):
        if node.get("type") in NON_PROXY_TYPES:
            continue
        try:
            validate_node(node)
        except (ValueError, TypeError, AttributeError) as error:
            issues[str(error)] += 1
            continue
        groups.setdefault(node["type"], []).append(deepcopy(node))
    if not groups:
        raise ConversionError("Нет корректных подключений для разделения по типам")
    outputs = {}
    counts = {}
    group_counts = {}
    all_group_links = []
    for kind, nodes in sorted(groups.items()):
        dataset = {"outbounds": nodes, "endpoints": []}
        profile = build_hiddify_config(dataset)
        outputs[f"raw/by-type/{kind}.json"] = dataset
        outputs[f"hiddify/by-type/{kind}.json"] = profile
        counts[kind] = len(nodes)
        group_outputs, links = group_subscription_outputs(kind, nodes)
        outputs.update(group_outputs)
        group_counts[kind] = len(links)
        all_group_links.extend(links)
    outputs["hiddify/groups/all.txt"] = "\n".join(all_group_links) + "\n"
    uri_counts = {}
    original = Path(root) / "githubmirror/all.txt"
    if original.exists():
        allowed = {
            json.dumps({key: value for key, value in node.items() if key != "tag"}, sort_keys=True)
            for nodes in groups.values() for node in nodes
        }
        uri_groups = {}
        text = original.read_text(encoding="utf-8-sig").strip()
        if text and "://" not in text and not text.startswith(("{", "[")):
            text = decode_base64(text)
        for line in text.splitlines():
            link = line.strip()
            if not link or link.startswith(("#", "//")):
                continue
            try:
                node = uri_outbound(link)
                validate_node(node)
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
            fingerprint = json.dumps({key: value for key, value in node.items() if key != "tag"}, sort_keys=True)
            if fingerprint in allowed:
                uri_groups.setdefault(node["type"], {}).setdefault(link, None)
        for kind, links in sorted(uri_groups.items()):
            outputs[f"githubmirror/by-type/{kind}.txt"] = "\n".join(links) + "\n"
            uri_counts[kind] = len(links)
    outputs["protocol-stats.json"] = {
        "types": counts, "uri_types": uri_counts, "groups": group_counts,
        "group_size": GROUP_SIZE, "excluded": sum(issues.values())
    }
    for name, value in outputs.items():
        destination = Path(root) / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    remove_stale_group_files(Path(root), outputs)
    print(f"Подписки по типам: {counts}; исключено некорректных записей {sum(issues.values())}", flush=True)
    for reason, count in issues.items():
        print(f"  {reason}: {count}", flush=True)
    return list(outputs), counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root)
    config = json.loads((root / "raw/all.txt").read_text(encoding="utf-8"))
    _, counts = build_protocol_subscriptions(config, root)
    from subscription_report import save_subscription_report
    sources = sorted((path for path in (root / "githubmirror").glob("*.txt") if path.stem.isdigit()), key=lambda path: int(path.stem))
    stats = root / "subscription-stats.json"
    excluded = json.loads(stats.read_text())["all"]["excluded"] if stats.exists() else 0
    save_subscription_report(root, sources, config, excluded, protocol_counts=counts,
                             protocol_uri_counts=json.loads((root / "protocol-stats.json").read_text())["uri_types"])


if __name__ == "__main__":
    main()
