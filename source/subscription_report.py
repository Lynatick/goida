"""Publish subscription counts and conversion exclusions on the home page."""

from datetime import datetime
import json
import re
from zoneinfo import ZoneInfo
from pathlib import Path

from hiddify_subscription import NON_PROXY_TYPES
from subscription_converter import (
    ConversionError, convert_subscription, decode_base64, uri_outbound,
)


def proxy_count(config):
    configs = config if isinstance(config, list) else [config]
    return sum(
        1 for item in configs
        for node in item.get("outbounds", []) + item.get("endpoints", [])
        if node.get("type", node.get("protocol"))
        not in NON_PROXY_TYPES | {"freedom", "blackhole"}
    )


def subscription_counts(content):
    try:
        config, issues = convert_subscription(content)
        return {"configs": proxy_count(config), "excluded": sum(issues.values())}
    except (ValueError, TypeError):
        # All-invalid URI subscriptions still need a meaningful exclusion count.
        text = content.strip().lstrip("\ufeff").strip()
        if not text:
            return {"configs": 0, "excluded": 0}
        if "://" not in text and not text.startswith(("{", "[")):
            try:
                text = decode_base64(text).strip()
            except (ValueError, UnicodeError):
                return {"configs": None, "excluded": None}
        if text.startswith(("{", "[")):
            return {"configs": None, "excluded": None}
        excluded = 0
        for line in text.splitlines():
            link = line.strip()
            if not link or link.startswith(("#", "//")):
                continue
            try:
                uri_outbound(link)
            except (ConversionError, ValueError, TypeError, KeyError, AttributeError):
                excluded += 1
        return {"configs": 0, "excluded": excluded}


def render_subscription_rows(rows, protocol_counts=None, protocol_uri_counts=None):
    cells = []
    base_url = "https://raw.githubusercontent.com/Lynatick/goida/main"
    for name, row in rows.items():
        label = "Все" if name == "all" else f"{int(name):02d}"
        count = "—" if row["configs"] is None else f'{row["configs"]:,}'.replace(",", "\u202f")
        excluded = "—" if row["excluded"] is None else f'{row["excluded"]:,}'.replace(",", "\u202f")
        cells.append(f'          <tr><th scope="row">{label}</th>')
        for directory, suffix in (("hiddify", "json"), ("githubmirror", "txt")):
            link_id = f"{directory}-{name}-{suffix}"
            url = f"{base_url}/{directory}/{name}.{suffix}"
            cells.append(
                f'            <td><div class="subscription-link">'
                f'<a id="{link_id}" class="filename" href="{url}" title="{url}" '
                f'aria-label="Ссылка {directory}: {label}">{name}.{suffix}</a>'
                f'<button type="button" data-copy="{link_id}" '
                f'aria-label="Копировать ссылку {directory}: {label}">Копировать</button>'
                f'</div></td>'
            )
        cells.append(f'            <td class="numeric">{count}</td><td class="numeric">{excluded}</td>')
        if protocol_counts is not None and name == "all":
            cells.append(f'            <td rowspan="{len(rows)}" class="protocol-links">')
            cells.append('              <div class="protocol-heading">Hiddify · JSON</div>')
            for kind, total in sorted(protocol_counts.items()):
                link_id = f"protocol-{kind}"
                url = f"{base_url}/hiddify/by-type/{kind}.json"
                type_count = f"{total:,}".replace(",", "\u202f")
                cells.append(
                    f'              <div class="subscription-link">'
                    f'<a id="{link_id}" class="filename" href="{url}" title="{url}">{kind}.json</a>'
                    f'<span class="numeric">{type_count}</span>'
                    f'<button type="button" data-copy="{link_id}" '
                    f'aria-label="Копировать ссылку {kind}.json">Копировать</button></div>'
                )
            if protocol_uri_counts:
                cells.append('              <div class="protocol-heading">Исходные URI</div>')
                for kind, total in sorted(protocol_uri_counts.items()):
                    link_id = f"protocol-uri-{kind}"
                    url = f"{base_url}/githubmirror/by-type/{kind}.txt"
                    type_count = f"{total:,}".replace(",", "\u202f")
                    cells.append(
                        f'              <div class="subscription-link">'
                        f'<a id="{link_id}" class="filename" href="{url}" title="{url}">{kind}.txt</a>'
                        f'<span class="numeric">{type_count}</span>'
                        f'<button type="button" data-copy="{link_id}" '
                        f'aria-label="Копировать ссылку {kind}.txt">Копировать</button></div>'
                    )
            cells.append('            </td>')
        cells.append('          </tr>')
    return "\n".join(cells)


def render_last_updated(html):
    updated = datetime.now(ZoneInfo("Europe/Moscow"))
    timestamp = updated.isoformat(timespec="seconds")
    label = updated.strftime("%d.%m.%Y %H:%M:%S")
    block = (
        '<!-- subscription-updated:start -->\n'
        f'    <p class="last-updated">Последнее обновление: '
        f'<time datetime="{timestamp}">{label} МСК</time></p>\n'
        '    <!-- subscription-updated:end -->'
    )
    return re.sub(
        r"<!-- subscription-updated:start -->.*?<!-- subscription-updated:end -->",
        block, html, count=1, flags=re.DOTALL
    )


def save_subscription_report(root, sources, combined_config, combined_excluded, protocol_counts=None, protocol_uri_counts=None):
    root = Path(root)
    rows = {"all": {"configs": proxy_count(combined_config), "excluded": combined_excluded}}
    for path in sources:
        rows[path.stem] = subscription_counts(path.read_text(encoding="utf-8-sig"))
    destination = root / "subscription-stats.json"
    destination.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    outputs = ["subscription-stats.json"]
    homepage = root / "index.html"
    if homepage.exists():
        html = homepage.read_text(encoding="utf-8")
        start = "<!-- subscription-report:start -->"
        end = "<!-- subscription-report:end -->"
        if start in html and end in html:
            before, rest = html.split(start, 1)
            _, after = rest.split(end, 1)
            html = before + start + "\n" + render_subscription_rows(rows, protocol_counts, protocol_uri_counts) + "\n          " + end + after
            homepage.write_text(render_last_updated(html), encoding="utf-8")
            outputs.append("index.html")
    return outputs
