import os
import sys
import argparse
import json
from pathlib import Path
from getpass import getpass
import requests
from github import Github, GithubException
from datetime import datetime
import zoneinfo
from subscription_converter import save_raw_subscription
from hiddify_subscription import save_hiddify_subscription
from combined_subscription import build_combined_subscriptions

# Определение времени по МСК
zone = zoneinfo.ZoneInfo("Europe/Moscow")
thistime = datetime.now(zone)
offset = thistime.strftime("%H:%M | %d.%m.%Y")

CONFIG_PATH = Path(__file__).resolve().parents[1] / "local_config.json"
LOCAL_CONFIG = {}
if CONFIG_PATH.exists():
    with CONFIG_PATH.open(encoding="utf-8") as file:
        LOCAL_CONFIG = json.load(file)

GITHUB_TOKEN = (
    os.environ.get("MY_TOKEN")
    or os.environ.get("GITHUB_TOKEN")
    or LOCAL_CONFIG.get("GITHUB_TOKEN", "")
)
REPO_NAME_1 = (
    os.environ.get("GITHUB_REPOSITORY")
    or os.environ.get("REPO_NAME_1")
    or LOCAL_CONFIG.get("REPO_NAME_1", "")
)

# Если локальная папка не существует, создаём её
if not os.path.exists("githubmirror"):
    os.mkdir("githubmirror")

# Список URL и локальных/удалённых путей
URLS = [
    "https://istanbulsydneyhotel.com/blogs/site/sni.php?security=reality", #1
    "https://istanbulsydneyhotel.com/blogs/site/sni.php", #2
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt", #3
    "https://raw.githubusercontent.com/acymz/AutoVPN/refs/heads/main/data/V2.txt", #4
    "https://raw.githubusercontent.com/AliDev-ir/FreeVPN/main/pcvpn",  #5
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/V2RAY_RAW.txt",  #6
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/All_Configs_Sub.txt",  #7
    "https://shadowmere.xyz/api/b64sub/",  #8
    "https://vpn.fail/free-proxy/v2ray",   #9
    "https://raw.githubusercontent.com/Proxydaemitelegram/Proxydaemi44/refs/heads/main/Proxydaemi44",  #10
    "https://raw.githubusercontent.com/soroushmirzaei/telegram-configs-collector/main/splitted/mixed",   #11
    "https://raw.githubusercontent.com/mheidari98/.proxy/refs/heads/main/all",   #12
    "https://github.com/Kwinshadow/TelegramV2rayCollector/raw/refs/heads/main/sublinks/mix.txt",   #13
    "https://github.com/LalatinaHub/Mineral/raw/refs/heads/master/result/nodes",   #14
    "https://github.com/4n0nymou3/multi-proxy-config-fetcher/raw/refs/heads/main/configs/proxy_configs.txt",   #15
    "https://github.com/freefq/free/raw/refs/heads/master/v2",    #16
    "https://github.com/MhdiTaheri/V2rayCollector_Py/raw/refs/heads/main/sub/Mix/mix.txt", #17
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/refs/heads/main/All_Configs_Sub.txt", #18
    "https://github.com/MhdiTaheri/V2rayCollector/raw/refs/heads/main/sub/mix",   #19
    "https://raw.githubusercontent.com/mehran1404/Sub_Link/refs/heads/main/V2RAY-Sub.txt",  #20
    "https://raw.githubusercontent.com/shabane/kamaji/master/hub/merged.txt",   #21
    "https://raw.githubusercontent.com/wuqb2i4f/xray-config-toolkit/main/output/base64/mix-uri",   #22
    "https://raw.githubusercontent.com/V2RAYCONFIGSPOOL/V2RAY_SUB/refs/heads/main/v2ray_configs.txt",  #23
    "https://raw.githubusercontent.com/Delta-Kronecker/V2ray-Config/refs/heads/main/config/tcp-pass/batch_013.txt",  #24
    "https://raw.githubusercontent.com/morpheusadam/v2ray-config/main/subs/bundles/best.txt",  #25
    "https://raw.githubusercontent.com/Alirewa/V2ray-Configs/main/config.txt",  #26
    "https://raw.githubusercontent.com/chaishpish/free_server_v2ray/main/@TFMTProto",  #27
]

REMOTE_PATHS = [f"githubmirror/{i+1}.txt" for i in range(len(URLS))]
LOCAL_PATHS = [f"githubmirror/{i+1}.txt" for i in range(len(URLS))]


def fetch_data(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def save_to_local_file(path, content):
    with open(path, "w", encoding="utf-8") as file:
        file.write(content)
    print(f"Данные сохранены локально в {path}", flush=True)


def upload_to_github(local_path, remote_path):
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Файл {local_path} не найден.")

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME_1)

    with open(local_path, "r", encoding="utf-8") as file:
        content = file.read()

    try:
        file_in_repo = repo.get_contents(remote_path)
        repo.update_file(
            path=remote_path,
            message=f"Обновление конфига по часовому поясу Европа/Москва: {offset}",
            content=content,
            sha=file_in_repo.sha
        )
    except GithubException as e:
        if e.status != 404:
            raise
        repo.create_file(
            path=remote_path,
            message=f"Первый коммит по часовому поясу Европа/Москва: {offset}",
            content=content
        )


def print_progress(completed, total):
    fraction = completed / total if total else 1
    filled = int(20 * fraction)
    bar = "#" * filled + "-" * (20 - filled)
    print(
        f"Обработано: [{bar}] {fraction:.0%} ({completed}/{total})",
        flush=True
    )


def ensure_github_credentials():
    global GITHUB_TOKEN

    if not REPO_NAME_1:
        raise RuntimeError(
            "Укажите REPO_NAME_1 в local_config.json или задайте "
            "GITHUB_REPOSITORY / REPO_NAME_1 в окружении."
        )

    if not GITHUB_TOKEN:
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Для ввода токена запустите скрипт в терминале или задайте "
                "GITHUB_TOKEN в local_config.json либо MY_TOKEN / GITHUB_TOKEN в окружении."
            )
        try:
            GITHUB_TOKEN = getpass(
                f"Введите GitHub токен для {REPO_NAME_1} (ввод скрыт): "
            ).strip()
        except EOFError:
            raise RuntimeError("Ввод токена прерван.") from None
    if not GITHUB_TOKEN:
        raise RuntimeError(
            "Токен не введён. Нужен GitHub токен с правом записи Contents "
            "в репозиторий " + REPO_NAME_1
        )


def fetch_source(url, local_path, progress, failed_sources):
    print(f"\n{progress} Скачивание {url}", flush=True)
    try:
        data = fetch_data(url)
        if not data.strip():
            raise ValueError("Источник вернул пустые данные")
        return data
    except (requests.RequestException, ValueError) as error:
        failed_sources.append((url, local_path, str(error)))
        print(f"{progress} Источник пропущен: {error}", flush=True)
        return None


def convert_source(data, local_path, progress):
    raw_path = os.path.join("raw", os.path.basename(local_path))
    print(f"{progress} Преобразование в {raw_path}", flush=True)
    try:
        config = save_raw_subscription(data, raw_path)
    except ValueError as error:
        print(f"{progress} JSON не создан для {raw_path}: {error}", flush=True)
        return []
    paths = [raw_path]
    hiddify_path = os.path.join(
        "hiddify", os.path.splitext(os.path.basename(local_path))[0] + ".json"
    )
    try:
        paths.extend(save_hiddify_subscription(config, hiddify_path))
    except ValueError as error:
        print(
            f"{progress} Подписка Hiddify не создана для {hiddify_path}: {error}",
            flush=True
        )
    return paths


def upload_files(paths):
    uploaded_count = 0
    for local_path, remote_path in paths:
        upload_to_github(local_path, remote_path)
        uploaded_count += 1
    return uploaded_count


def report_failed_sources(failed_sources):
    if not failed_sources:
        return
    print("Пропущенные источники и ожидаемые файлы:", flush=True)
    for url, local_path, error in failed_sources:
        name = os.path.basename(local_path)
        print(
            f"- {url}: {error}\n"
            f"  {local_path}; raw/{name}; hiddify/{os.path.splitext(name)[0]}.json",
            flush=True
        )


def main(local_only=False):
    if not local_only:
        ensure_github_credentials()
    total = len(URLS)
    completed = 0
    uploaded_count = 0
    failed_sources = []
    print(f"Обновление {total} конфигов в {REPO_NAME_1}", flush=True)
    print_progress(completed, total)
    try:
        for index, (url, local_path, remote_path) in enumerate(
            zip(URLS, LOCAL_PATHS, REMOTE_PATHS), start=1
        ):
            progress = f"[{index}/{total}]"
            data = fetch_source(url, local_path, progress, failed_sources)
            if data is None:
                print_progress(index, total)
                continue
            print(f"{progress} Сохранение {local_path}", flush=True)
            save_to_local_file(local_path, data)
            converted_paths = convert_source(data, local_path, progress)
            if not local_only:
                paths = [(local_path, remote_path)]
                paths.extend((path, path) for path in converted_paths)
                uploaded_count += upload_files(paths)
            completed += 1
            print_progress(index, total)
    except Exception as error:
        print(
            f"Произошла ошибка: {error}. Завершено {completed}/{total} конфигов.",
            flush=True
        )
        raise
    report_failed_sources(failed_sources)
    if total and completed == 0:
        raise RuntimeError("Не удалось получить данные ни из одного источника.")
    combined_paths = build_combined_subscriptions()
    if not local_only:
        uploaded_count += upload_files((path, path) for path in combined_paths)
        print(
            f"\nОтправка в GitHub {REPO_NAME_1} завершена: файлов {uploaded_count}, "
            f"обработано источников {completed}/{total}.",
            flush=True
        )
    else:
        print(
            f"\nОбработка завершена: обновлено локально {completed}/{total} конфигов.",
            flush=True
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Обновление конфигов VPN и подписок Hiddify")
    parser.add_argument(
        "--local-only", action="store_true",
        help="Скачать и преобразовать данные без токена и отправки через GitHub API"
    )
    main(local_only=parser.parse_args().local_only)
