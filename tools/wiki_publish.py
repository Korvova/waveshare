# -*- coding: utf-8 -*-
"""Публикация документации Unirack-1 в Яндекс Вики.

Страницы эпика лежат в wiki/ (index.md — сам эпик); пользовательские
документы не дублируются, а берутся напрямую из MQTT-2-0/*.md (см. FILES).

Запуск:
    WIKI_TOKEN=<токен> python tools/wiki_publish.py            все страницы
    WIKI_TOKEN=<токен> python tools/wiki_publish.py instrukcija только эту

Токен в репозиторий не коммитим — берём из переменной окружения WIKI_TOKEN.
Получить новый: https://oauth.yandex.ru/authorize?response_type=token&client_id=22fcafe69ac24efe82098b7d8d5d869d
"""
import json
import os
import sys
import urllib.request
import urllib.error

BASE = "https://api.wiki.yandex.net/v1"
ORG = "d0d0f076-05d6-4525-84fd-206271e76feb"
ROOT = "homepage/iniciativa.-proekty-rms/jepik-waveshare-unirack"

# заголовки страниц: имя -> заголовок в вики
TITLES = {
    "index": "⌛Эпик. Waveshare Unirack",
    "t-proshivka": "✅Т. Прошивка Unirack-1",
    "instrukcija": "✅Инструкция пользователя",
    "kontakty": "✅Контакты (клеммник)",
    "chek-list": "✅Чек-лист приёмки",
    "protokol-mqtt": "✅Протокол MQTT",
    "proshivka-i-obnovlenie": "✅Прошивка и обновление устройств",
}

# страницы, которые живут не в wiki/, а прямо в документации прошивки
FILES = {
    "instrukcija": "MQTT-2-0/ИНСТРУКЦИЯ.md",
    "kontakty": "MQTT-2-0/КОНТАКТЫ.md",
    "chek-list": "MQTT-2-0/CHECKLIST.md",
    "protokol-mqtt": "MQTT-2-0/ПРОТОКОЛ_MQTT.md",
}

TOKEN = os.environ.get("WIKI_TOKEN", "")
if not TOKEN:
    sys.exit("Не задана переменная окружения WIKI_TOKEN")

HEADERS = {
    "Authorization": "OAuth " + TOKEN,
    "X-Collab-Org-Id": ORG,
    "Content-Type": "application/json",
}


def request(method, path, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else None
    req = urllib.request.Request(BASE + path, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def publish(name, text):
    slug = ROOT if name == "index" else "%s/%s" % (ROOT, name)
    title = TITLES.get(name, name)
    code, page = request("GET", "/pages?slug=%s" % slug)
    if code == 200 and isinstance(page, dict) and page.get("id"):
        code, res = request("POST", "/pages/%d" % page["id"],
                            {"title": title, "content": text})
        action = "обновлена"
    else:
        code, res = request("POST", "/pages",
                            {"slug": slug, "title": title, "content": text})
        action = "создана"
    ok = code in (200, 201)
    print("%-28s %s  %s" % (name, "OK " if ok else "ОШИБКА %s" % code, action if ok else res))
    return ok


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    wiki_dir = os.path.join(repo, "wiki")
    only = sys.argv[1:]

    names = [n[:-3] for n in sorted(os.listdir(wiki_dir)) if n.endswith(".md")]
    names += [n for n in FILES if n not in names]
    # index первым: он задаёт родителя для остальных
    names.sort(key=lambda n: (n != "index", n))

    failed = 0
    for name in names:
        if only and name not in only:
            continue
        path = os.path.join(repo, FILES[name]) if name in FILES else os.path.join(wiki_dir, name + ".md")
        with open(path, encoding="utf-8") as f:
            if not publish(name, f.read()):
                failed += 1
    print("Готово." if not failed else "Ошибок: %d" % failed)


if __name__ == "__main__":
    main()
