"""Convert URI subscriptions and preserve native sing-box/Xray JSON datasets."""

import argparse
import base64
import binascii
from collections import Counter
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlencode, urlsplit, urlunsplit
from uuid import UUID


class ConversionError(ValueError):
    pass


def decode_base64(value):
    compact = "".join(value.split())
    try:
        return base64.b64decode(
            compact + "=" * (-len(compact) % 4), altchars=b"-_", validate=True
        ).decode("utf-8-sig")
    except (ValueError, binascii.Error, UnicodeError) as error:
        raise ConversionError("Некорректный Base64") from error


def boolean(value):
    text = str(value).lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no", ""):
        return False
    raise ConversionError("Некорректное логическое значение")


def server_fields(server, port):
    if not isinstance(server, str) or not server.strip():
        raise ConversionError("Не указан сервер")
    server = server.strip().strip("[]")
    if any(character.isspace() for character in server) or "/" in server:
        raise ConversionError("Некорректный адрес сервера")
    port = int(port)
    if not 1 <= port <= 65535:
        raise ConversionError("Некорректный порт сервера")
    return {"server": server, "server_port": port}


def tls_fields(params, required=False, quic=False):
    security = str(params.get("security", "tls" if required else "none")).lower()
    if security in ("", "none") and not required:
        return None
    if security not in ("", "none", "tls", "reality"):
        raise ConversionError("Неподдерживаемый режим TLS")
    tls = {"enabled": True}
    name = params.get("sni") or params.get("serverName")
    if name:
        tls["server_name"] = name
    for key in ("allowInsecure", "allowinsecure", "insecure", "allow_insecure"):
        if key in params:
            tls["insecure"] = boolean(params[key])
            break
    if params.get("alpn"):
        tls["alpn"] = [item.strip() for item in params["alpn"].split(",") if item.strip()]
    if params.get("fp") and not quic:
        tls["utls"] = {"enabled": True, "fingerprint": params["fp"]}
    if security == "reality":
        if not params.get("pbk"):
            raise ConversionError("Не указан публичный ключ Reality")
        tls["reality"] = {
            "enabled": True,
            "public_key": params["pbk"],
            "short_id": params.get("sid", "")
        }
    return tls


def transport_fields(params):
    kind = str(params.get("type") or "tcp").lower()
    header = str(params.get("headerType") or "none").lower()
    if kind in ("tcp", "raw"):
        if header == "none":
            return None
        if header != "http":
            raise ConversionError("Неподдерживаемый заголовок TCP")
        kind = "http"
    if kind == "h2":
        kind = "http"
    if kind not in ("ws", "grpc", "http", "httpupgrade", "quic"):
        raise ConversionError("Неподдерживаемый транспорт: " + kind[:40])
    result = {"type": kind}
    path = params.get("path") or "/"
    host = params.get("host")
    if kind == "grpc":
        result["service_name"] = params.get("serviceName") or params.get("path") or ""
    elif kind == "ws":
        parts = urlsplit(path)
        query = parse_qs(parts.query, keep_blank_values=True)
        if "ed" in query:
            result["max_early_data"] = int(query.pop("ed")[0])
            result["early_data_header_name"] = "Sec-WebSocket-Protocol"
            path = urlunsplit(parts._replace(query=urlencode(query, doseq=True)))
        result["path"] = path
        if host:
            result["headers"] = {"Host": host}
    elif kind in ("http", "httpupgrade"):
        result["path"] = path
        if host:
            result["host"] = host.split(",") if kind == "http" else host
    elif params.get("quicSecurity", "none") != "none" or params.get("key"):
        raise ConversionError("Шифрование транспорта QUIC не поддерживается")
    return result


def add_connection_fields(outbound, params, required_tls=False, quic=False):
    tls = tls_fields(params, required=required_tls, quic=quic)
    if tls:
        outbound["tls"] = tls
    if not quic and outbound["type"] in ("vmess", "vless", "trojan"):
        transport = transport_fields(params)
        if transport:
            outbound["transport"] = transport


def vmess_outbound(link):
    data = json.loads(decode_base64(link.split("://", 1)[1].split("#", 1)[0]))
    if not isinstance(data, dict):
        raise ConversionError("Ожидается объект VMess")
    security = data.get("scy") or data.get("security") or "auto"
    if security not in ("auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305", "aes-128-ctr"):
        raise ConversionError("Неподдерживаемое шифрование VMess")
    outbound = {
        "type": "vmess",
        "tag": data.get("ps") or "VMess",
        **server_fields(data.get("add"), data.get("port")),
        "uuid": str(UUID(data["id"])),
        "security": security,
        "alter_id": int(data.get("aid") or 0),
        "authenticated_length": True,
        "packet_encoding": "xudp"
    }
    if outbound["alter_id"] < 0:
        raise ConversionError("Некорректный alter_id")
    params = dict(data)
    params["security"] = data.get("tls") or "none"
    params["type"] = data.get("net") or "tcp"
    params["headerType"] = data.get("type") or "none"
    add_connection_fields(outbound, params)
    return outbound


SS_METHODS = {
    "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
    "2022-blake3-chacha20-poly1305", "none", "aes-128-gcm", "aes-192-gcm",
    "aes-256-gcm", "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
    "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "aes-128-cfb", "aes-192-cfb",
    "aes-256-cfb", "rc4-md5", "chacha20-ietf", "xchacha20"
}


def shadowsocks_outbound(link):
    payload, _, fragment = link.split("://", 1)[1].partition("#")
    payload, _, query = payload.partition("?")
    if "@" not in payload:
        decoded = decode_base64(unquote(payload))
        if decoded.lstrip().startswith("{"):
            data = json.loads(decoded)
            outbound = {
                "type": "shadowsocks", "tag": data.get("ps") or "Shadowsocks",
                **server_fields(data.get("add"), data.get("port")),
                "method": data.get("method") or data["scy"],
                "password": data.get("password") or data["id"]
            }
            if outbound["method"] not in SS_METHODS:
                raise ConversionError("Неподдерживаемое шифрование Shadowsocks")
            if data.get("net", "tcp") not in ("tcp", "raw", ""):
                raise ConversionError("Неподдерживаемый транспорт Shadowsocks JSON")
            return outbound
        payload = decoded
    credentials, address = payload.rsplit("@", 1)
    parts = urlsplit("ss://" + address + "?" + query + "#" + fragment)
    credentials = unquote(credentials)
    if ":" not in credentials:
        credentials = decode_base64(credentials)
    method, password = credentials.split(":", 1)
    if method not in SS_METHODS:
        raise ConversionError("Неподдерживаемое шифрование Shadowsocks")
    outbound = {
        "type": "shadowsocks", "tag": unquote(parts.fragment) or "Shadowsocks",
        **server_fields(parts.hostname, parts.port),
        "method": method, "password": password
    }
    params = parse_qs(parts.query)
    if params.get("plugin"):
        plugin, _, options = params["plugin"][0].partition(";")
        plugin = "obfs-local" if plugin == "simple-obfs" else plugin
        if plugin not in ("obfs-local", "v2ray-plugin"):
            raise ConversionError("Неподдерживаемый плагин Shadowsocks")
        outbound.update(plugin=plugin, plugin_opts=options)
    return outbound


def uri_outbound(link):
    scheme = link.split("://", 1)[0].lower()
    if scheme == "vmess":
        return vmess_outbound(link)
    if scheme == "ss":
        return shadowsocks_outbound(link)
    if scheme not in ("vless", "trojan", "hysteria2", "hy2", "tuic", "anytls"):
        raise ConversionError("Неподдерживаемый протокол: " + scheme[:40])
    parts = urlsplit(link)
    params = {key: values[0] for key, values in parse_qs(parts.query, keep_blank_values=True).items()}
    kind = "hysteria2" if scheme == "hy2" else scheme
    outbound = {
        "type": kind, "tag": unquote(parts.fragment) or kind.upper(),
        **server_fields(parts.hostname, parts.port or (443 if kind in ("hysteria2", "anytls") else None))
    }
    if parts.username is None:
        raise ConversionError("Не указаны данные авторизации")
    username = unquote(parts.username)
    if kind in ("vless", "tuic"):
        outbound["uuid"] = str(UUID(username))
    if kind == "vless":
        if params.get("encryption", "none") not in ("none", ""):
            raise ConversionError("Неподдерживаемое шифрование VLESS")
        if params.get("flow"):
            if params["flow"] != "xtls-rprx-vision":
                raise ConversionError("Неподдерживаемый flow VLESS")
            outbound["flow"] = params["flow"]
        outbound["packet_encoding"] = "xudp"
    elif kind == "tuic":
        outbound["password"] = unquote(parts.password or "")
        for key in ("congestion_control", "udp_relay_mode"):
            if params.get(key):
                outbound[key] = params[key]
    else:
        outbound["password"] = unquote(parts.netloc.rsplit("@", 1)[0])
    if kind == "hysteria2" and params.get("obfs"):
        if params["obfs"] != "salamander":
            raise ConversionError("Неподдерживаемый obfs Hysteria2")
        outbound["obfs"] = {
            "type": "salamander",
            "password": params.get("obfs-password") or params.get("obfsPassword") or ""
        }
    add_connection_fields(
        outbound, params, required_tls=kind != "vless", quic=kind in ("tuic", "hysteria2")
    )
    return outbound


def validate_json_config(config, location="JSON"):
    """Check the container structure without rewriting engine-specific fields."""
    if not isinstance(config, dict):
        raise ConversionError(f"{location}: ожидается полная конфигурация JSON")
    outbounds = config.get("outbounds", [])
    endpoints = config.get("endpoints", [])
    if not isinstance(outbounds, list) or not isinstance(endpoints, list):
        raise ConversionError(f"{location}: outbounds/endpoints должны быть списками")
    if not outbounds and not endpoints:
        raise ConversionError(f"{location}: JSON не содержит подключений")
    for index, outbound in enumerate(outbounds):
        if not isinstance(outbound, dict) or not any(
            isinstance(outbound.get(key), str) and outbound[key]
            for key in ("type", "protocol")
        ):
            raise ConversionError(
                f"{location}.outbounds[{index}]: не указан type (sing-box) "
                "или protocol (Xray/V2Ray)"
            )
    for index, endpoint in enumerate(endpoints):
        if not isinstance(endpoint, dict) or not isinstance(endpoint.get("type"), str) or not endpoint["type"]:
            raise ConversionError(f"{location}.endpoints[{index}]: не указан type")


def connection_count(config):
    configs = config if isinstance(config, list) else [config]
    return sum(len(item.get("outbounds", [])) + len(item.get("endpoints", [])) for item in configs)


def convert_subscription(content):
    """Return a config/dataset and rejection counts; keep native JSON intact."""
    text = content.strip().lstrip("\ufeff").strip()
    if not text:
        raise ConversionError("Источник пуст")
    if "://" not in text and not text.startswith(("{", "[")):
        text = decode_base64(text).strip()
    issues = Counter()
    if text.startswith(("{", "[")):
        config = json.loads(text)
        if isinstance(config, list):
            if not config:
                raise ConversionError("JSON-массив пуст")
            for index, item in enumerate(config):
                validate_json_config(item, f"JSON[{index}]")
        else:
            validate_json_config(config)
        return config, issues
    outbounds = []
    for line in text.splitlines():
        link = line.strip()
        if not link or link.startswith(("#", "//")):
            continue
        try:
            outbound = uri_outbound(link)
            outbound["tag"] = f"{len(outbounds) + 1}. {outbound['tag']}"
            outbounds.append(outbound)
        except ConversionError as error:
            issues[str(error)] += 1
        except (ValueError, TypeError, KeyError, AttributeError):
            issues["Повреждённая запись"] += 1
    if not outbounds:
        reasons = "; ".join(f"{reason}: {count}" for reason, count in issues.items())
        raise ConversionError("Нет поддерживаемых подключений. " + reasons)
    return {"outbounds": outbounds, "endpoints": []}, issues


def save_raw_subscription(content, path):
    config, issues = convert_subscription(content)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    count = connection_count(config)
    dataset_info = f", полных конфигураций {len(config)}" if isinstance(config, list) else ""
    print(
        f"JSON сохранён в {path}: подключений {count}{dataset_info}, "
        f"пропущено {sum(issues.values())}",
        flush=True
    )
    return config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default="githubmirror")
    parser.add_argument("--output-dir", default="raw")
    args = parser.parse_args()
    paths = sorted(Path(args.directory).glob("*.txt"))
    if not paths:
        parser.error("В каталоге нет файлов *.txt")
    failed = 0
    for path in paths:
        try:
            save_raw_subscription(path.read_text(encoding="utf-8-sig"), Path(args.output_dir) / path.name)
        except (ValueError, OSError) as error:
            failed += 1
            print(f"Не удалось создать {Path(args.output_dir) / path.name}: {error}", flush=True)
    print(f"Преобразовано файлов: {len(paths) - failed}/{len(paths)}", flush=True)
    return int(failed > 0)


if __name__ == "__main__":
    raise SystemExit(main())
