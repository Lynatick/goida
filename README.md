Наведите курсор на блок со ссылкой и нажмите кнопку копирования в его правом верхнем углу.
Затем в Hiddify выберите **Новый профиль → Добавить из буфера обмена**.

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/1.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/2.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/3.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/4.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/5.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/6.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/7.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/8.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/9.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/10.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/11.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/12.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/13.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/14.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/15.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/16.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/17.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/18.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/19.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/20.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/21.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/22.json
```

```text
https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/23.json
```

Общие подписки всех источников:

- [Hiddify — все серверы](https://raw.githubusercontent.com/Lynatick/goida/main/hiddify/all.json)
- [Исходные URI — все конфигурации](https://raw.githubusercontent.com/Lynatick/goida/main/githubmirror/all.txt)
- [Объединённый JSON sing-box](https://raw.githubusercontent.com/Lynatick/goida/main/raw/all.txt)

Общие файлы создаются при запуске `source/main.py`. Пересобрать их из локальных
источников без скачивания: `python3 source/combined_subscription.py`.

Настройки GitHub хранятся в `local_config.json` в корне проекта. Для новой
установки скопируйте `local_config.example.json` в `local_config.json` и заполните
`GITHUB_TOKEN` и `REPO_NAME_1` (в формате `owner/repo`). Локальный файл исключён
из Git через `.gitignore`. Переменные окружения `MY_TOKEN` / `GITHUB_TOKEN` и
`GITHUB_REPOSITORY` / `REPO_NAME_1` имеют приоритет над значениями из файла.
Для запуска с `--local-only` настройки GitHub не обязательны.

На главной странице таблица объединяет ссылки Hiddify, исходные URI и количество поддерживаемых
конфигов и повреждённых или неподдерживаемых записей, исключённых при
преобразовании. Отчёт `subscription-stats.json` и таблица на странице обновляются
при сборке общих подписок. В строке «Все» повторы удаляются и не считаются
ошибками. Сетевая доступность серверов в этих числах не учитывается.

Повторяющиеся URI исключаются. Неподдерживаемые записи остаются в общем списке URI,
а при преобразовании в JSON пропускаются с отчётом. Полные JSON-конфигурации
с отдельными правилами маршрутизации не объединяются: сборка завершится ошибкой
и сохранит прежние общие файлы.

Проверка YouTube в Hiddify: обновите профиль, подключитесь и в разделе **Прокси**
в группе **Выбор сервера** оставьте выбранным **Автовыбор · YouTube**. Эта группа проверяет соединение
с `https://www.youtube.com/generate_204` через серверы подписки и автоматически
выбирает сервер по задержке; интервал проверки — 3 минуты.
Это HTTP-тест доступности YouTube, а не проверка воспроизведения видео: ограничения
конкретных роликов, CDN `googlevideo.com` и запросы подтверждения аккаунта им не проверяются.
Для автоматического выбора используется только тестовый адрес YouTube.
Язык установленного приложения Hiddify — русский; названия новых групп тоже на русском.
Описание встроенного теста: [URLTest sing-box](https://sing-box.sagernet.org/configuration/outbound/urltest/).

Лимит 20 одновременных проверок требует отдельной сборки ядра Hiddify:
в штатном ядре лимит 10 задан в исходном коде, подписка его не меняет.
[Патч лимита 20](patches/hiddify-urltest-20.patch) подготовлен для ядра
`c9d6f0f00b2eda34e4fb71863e4e0a62b3e931a0` и его подмодуля sing-box
`0a02b7729f6a211436bb8bdcd8696c283eb27767`.
Применение к исходникам подмодуля: `git -C hiddify-sing-box apply /путь/к/hiddify-urltest-20.patch`.
Патч влияет на лимит URLTest во всех группах; установка нового ядра выполняется отдельно.

Проверка получения видеоданных через ядро Hiddify (macOS, Python 3.10+):

```bash
python3 -m pip install -r source/requirements-youtube.txt
python3 source/youtube_check.py --config hiddify/4.json --node 1 --count 3
```

Нужны установленный Hiddify и JavaScript runtime для yt-dlp (например, Node.js).
Скрипт использует ядро из `/Applications/Hiddify.app`, запускает временный локальный
прокси для каждого выбранного сервера и проверяет страницу тестового ролика,
получение адреса видеопотока и загрузку до 16 КиБ видео с `googlevideo.com`.
Группы выбора и автоматического тестирования не учитываются в нумерации серверов.
Приложение Hiddify запускать не требуется; системный VPN и настройки прокси не меняются.

Другой ролик можно указать через `--video`, другое ядро — через `--core`.
Отчёт сохраняется в `reports/youtube.json` (не включается в Git).
`media_received` означает получение фрагмента MP4/WebM через выбранный прокси;
`connection_failed` — ошибку доступа к странице; `core_error` — ошибку запуска ядра;
`inconclusive` — сайт доступен, но видео не подтверждено (включая CAPTCHA,
ограничения ролика или ошибку yt-dlp). Тест не гарантирует воспроизведение всех
роликов и не измеряет скорость длительного просмотра.
Для извлечения адреса видеопотока используется [yt-dlp](https://github.com/yt-dlp/yt-dlp).

Подписки по типу подключения представлены в столбце **По типу · общий файл** на
HTML-странице. Они формируются из `raw/all.txt`: каждый файл содержит серверы
одного протокола и группы выбора/проверки Hiddify. Оригинальный JSON без групп
сохраняется в `raw/by-type/<тип>.json`, профиль — в `hiddify/by-type/<тип>.json`.
Проверяются структура, адрес, порт, UUID, поля авторизации и параметры Reality;
некорректные записи исключаются с отчётом. Проверка доступности по сети не запускается.
Файлы пересоздаются при обычном обновлении подписок. Отдельная пересборка:

```bash
python3 source/protocol_subscriptions.py
```

Ниже JSON-подписок в последнем столбце находятся исходные URI-подписки по протоколам:
`githubmirror/by-type/<тип>.txt`. Они собираются из `githubmirror/all.txt` без
изменения исходных ссылок. Сохраняются только корректные URI, соответствующие
подключениям в общем JSON; дубликаты исключаются, `hy2` относится к `hysteria2`.

Автоматическое обновление выполняется [в GitHub Actions](https://github.com/Lynatick/goida/actions/workflows/update-profiles.yml)
ежедневно в **12:00 по Москве**, начиная с **14 октября 2026 года**.
Расписание `0 9 * * *` задано в UTC. Выполнение происходит на серверах GitHub;
локальный компьютер и Hiddify для обновления не нужны.

Workflow скачивает источники, формирует подписки и таблицу, проверяет JSON и
отправляет изменённые файлы одним коммитом. Для недоступных источников сохраняются
предыдущие данные. Если изменений нет, новый коммит не создаётся. После отправки
запрашивается пересборка существующего GitHub Pages, чтобы обновить таблицу.
Используется встроенный `GITHUB_TOKEN`; личный токен в secrets добавлять не нужно.

Ручной запуск: **Actions → Ежедневное обновление профилей → Run workflow**.
Отключение опции **Обновить профили** запускает только проверки workflow.
Журнал, итог и сведения о пропущенных источниках доступны в соответствующем запуске.
GitHub может запускать задания с задержкой; время 12:00 — время постановки в расписание.
