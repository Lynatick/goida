"""Combine numbered URI subscriptions into shared mirror, raw and Hiddify files."""

import argparse
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from hiddify_subscription import build_hiddify_config
from subscription_converter import ConversionError, convert_subscription, decode_base64, uri_outbound
from subscription_report import save_subscription_report
from protocol_subscriptions import (
    build_protocol_subscriptions, remove_stale_group_files, remove_stale_type_files,
)


def connection_key(link):
    """Identify the actual proxy settings, ignoring the source's display name."""
    node = uri_outbound(link)
    return json.dumps(
        {key: value for key, value in node.items() if key != "tag"},
        sort_keys=True, ensure_ascii=False,
    )


def build_combined_subscriptions(root="."):
    root = Path(root)
    sources = sorted(
        (path for path in (root / "githubmirror").glob("*.txt") if path.stem.isdigit()),
        key=lambda path: int(path.stem)
    )
    links = {}
    invalid_lines = 0
    invalid_links = set()
    for path in sources:
        text = path.read_text(encoding="utf-8-sig").strip()
        if not text:
            continue
        if "://" not in text and not text.startswith(("{", "[")):
            text = decode_base64(text).strip()
        if text.startswith(("{", "[")):
            raise ConversionError(
                f"{path}: полные JSON-конфигурации нельзя объединить в список URI "
                "без потери правил. Общие файлы не обновлены."
            )
        skipped = 0
        for line in text.splitlines():
            link = line.strip()
            if link and not link.startswith(("#", "//")):
                if "://" not in link:
                    skipped += 1
                    continue
                try:
                    key = connection_key(link)
                except (ValueError, TypeError, KeyError, AttributeError):
                    if link not in invalid_links:
                        invalid_links.add(link)
                        skipped += 1
                    continue
                links.setdefault(key, link)
        if skipped:
            invalid_lines += skipped
            print(f"{path}: пропущено некорректных строк: {skipped}", flush=True)
    if not links:
        raise ConversionError("Нет URI для общей подписки")

    mirror = "\n".join(links.values()) + "\n"
    config, issues = convert_subscription(mirror)
    hiddify = build_hiddify_config(config)
    outputs = {
        "githubmirror/all.txt": mirror,
        "raw/all.txt": json.dumps(config, ensure_ascii=False, indent=1) + "\n",
        "hiddify/all.json": json.dumps(hiddify, ensure_ascii=False, indent=1) + "\n"
    }
    with TemporaryDirectory(prefix=".goida-stage-", dir=root) as stage_name:
        stage = Path(stage_name)
        for name, content in outputs.items():
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")
        homepage = root / "index.html"
        if homepage.exists():
            shutil.copyfile(homepage, stage / "index.html")
        protocol_paths, protocol_counts = build_protocol_subscriptions(config, stage)
        report_paths = save_subscription_report(
            stage, sources, config, invalid_lines + sum(issues.values()),
            protocol_counts=protocol_counts,
            protocol_uri_counts=json.loads((stage / "protocol-stats.json").read_text())["uri_types"]
        )
        paths = list(outputs) + protocol_paths + report_paths
        for name in paths:
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / name, destination)
        published = set(paths)
        remove_stale_group_files(root, published)
        remove_stale_type_files(root, published)
    print(
        f"Общая подписка: источников {len(sources)}, уникальных подключений {len(links)}, "
        f"серверов Hiddify {len(config['outbounds'])}, "
        f"пропущено {invalid_lines + sum(issues.values())}",
        flush=True
    )
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Корень репозитория")
    args = parser.parse_args()
    build_combined_subscriptions(args.root)


if __name__ == "__main__":
    main()
