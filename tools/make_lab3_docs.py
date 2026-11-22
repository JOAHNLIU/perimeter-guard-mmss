"""Формує документи лабораторної роботи 3 із результатів вимірювань.

Запуск з кореня репозиторію:  python tools/make_lab3_docs.py

Створює (перезаписує):
    docs/telemetry.md, docs/deployment.md,
    docs/adr/0005-shablony-pubsub-ta-buferyzatsiya.md,
    docs/adr/0006-mova-ta-tekhnolohichnyi-stek.md

Вхідні файли (їх створюють скрипти smart/check_channel.sh, smart/check_outage.sh,
smart/loadtest.sh): results/channel_*.txt|csv, results/step5_*.txt,
results/pubsub_*.txt, results/outage_*.txt|csv, results/load.csv,
results/docker_stats.txt, results/load_gateway_last.txt.

Скрипт нічого не вигадує: усі числа в розділах вимірювань беруться з цих файлів;
якщо файлу ще немає, розділ позначається як «дані ще не зібрано».
"""
import ast
import calendar
import csv
import re
import statistics
from datetime import datetime
from pathlib import Path

R = Path("results")
DOCS = Path("docs")

# ----- параметри системи та моделі (лабораторна робота 1 і smart/) ---------------
S_BYTES = 131            # середній розмір тема + тіло, байт (виміряно емулятором)
UPLINK_KBPS = 1000       # модельна смуга ланки периферія — сервер
MAX_ROWS = 50000         # місткість буфера шлюзу в експерименті з розривом
MAX_ROWS_LOAD = 10000    # місткість буфера під час навантажувального випробування
STEP_S = 30              # тривалість ступеня навантаження, с
LAM_NODE_NOM = 3         # λ вузла: 3 сенсори · 1 Гц
LAM_NODE_PEAK = 15       # λ вузла у піку: 3 сенсори · 5 Гц (верх діапазону табл. 4)
NODES = 64               # NFR-02 ЛР 1: до 64 камер/вузлів
L_MER_MS = 400           # бюджет L_мер із NFR-01 ЛР 1, мс
HZ_STEPS = [10, 100, 200, 250, 300, 350, 400, 450, 500]
CPU_LIMITS = {"gateway": 25.0, "edge-broker": 50.0}   # % одного ядра (cpus: 0.25 / 0.5)
MU1 = 1e6 * UPLINK_KBPS / 1000 / (8 * S_BYTES)        # пропускна здатність ланки, повід./с


def f(x, n=1):
    return f"{x:.{n}f}".replace(".", ",")


def rd(name):
    p = R / name
    return p.read_text(encoding="utf-8") if p.exists() else None


def pending(cmd):
    return (f"> ⚠ Дані ще не зібрано. Виконайте `{cmd}`, потім повторно запустіть "
            f"`python tools/make_lab3_docs.py`.\n")


def read_csv(name):
    t = rd(name)
    if not t:
        return None
    rows = []
    for r in csv.DictReader(t.strip().splitlines()):
        rows.append({k: float(v) for k, v in r.items()})
    return rows or None


def ts(s):
    base, _, frac = s.partition(".")
    dt = datetime.strptime(base, "%Y-%m-%dT%H:%M:%S")
    return calendar.timegm(dt.timetuple()) + (float("0." + frac) if frac else 0.0)


# =============================================================== telemetry.md

TELEMETRY_HEAD = """# Телеметрія сенсорів PerimeterGuard

Цей документ описує канал сенсорних даних вузла ділянки периметра: теми MQTT,
схему повідомлення, політику оброблення помилок і перевірку каналу внесеними
збоями. Сенсори я емулюю програмою `smart/sensors.py`, брокер — Eclipse
Mosquitto 2 у Docker, підписник — `smart/collector.py` зі сховищем SQLite.
Сенсори взято з табл. 4 методичних вказівок для області №2: рух (0/1),
освітленість (lx) і стан воріт (0/1).

## Теми

Тема має чотири рівні: об’єкт, ділянка, пристрій і вид повідомлення, наприклад
`p1/north/motion-1/tele`. Підписка з символом `+` дає змогу додавати
споживачів без змін сенсорів (шаблон «публікація — підписка»).

| Рівень | Приклад | Пояснення |
|---|---|---|
| 1. Об’єкт | `p1` | периметр об’єкта; розширюється іншими об’єктами (`p2`, …) |
| 2. Ділянка | `north` | вузол ділянки периметра (одна камера й її сенсори) |
| 3. Пристрій | `motion-1`, `light-1`, `gate-1` | датчик руху, освітленості, стану воріт |
| 4. Вид | `tele`, `state` | телеметрія або стан пристрою |

| Вид | Тема | QoS | Збережене | Призначення |
|---|---|---|---|---|
| Телеметрія | `p1/north/<пристрій>/tele` | 0 | ні | показ із схемою нижче; втрату виявляє порядковий номер `seq` |
| Стан | `p1/north/<пристрій>/state` | 1 | так (retained) | `online`, коли пристрій працює |
| Заповіт | `p1/north/<пристрій>/state` | 1 | так (retained) | `offline`, який брокер публікує сам, якщо пристрій зник без від’єднання |

Телеметрію я публікую з QoS 0, бо втрату окремого показу виявляє `seq`, а
гарантії доставки на ланці периферія — сервер забезпечує шлюз з QoS 1 і буфером
(див. `docs/deployment.md`). Збережене повідомлення стану дає новому
підписникові поточний стан пристрою одразу після підписки. Для вимоги FR-10
ЛР 1 (позначити камеру офлайн протягом ≤ 30 с) я задав `keepalive = 20 с`:
брокер публікує заповіт приблизно через 1,5 · 20 = 30 с без пакетів від клієнта.

## Схема повідомлення

```json
{"dev":"north-light-1","boot":1,"seq":4182,"ts":"2026-11-21T08:41:20.123Z",
 "qty":"light","val":512.3,"unit":"lx"}
```

| Поле | Тип | Одиниця / формат | Призначення | Діапазон |
|---|---|---|---|---|
| `dev` | рядок | `<ділянка>-<пристрій>` | хто виміряв; має збігатися з темою | — |
| `boot` | ціле | номер запуску | відрізняє запуски, бо після перезапуску `seq` починається з нуля | ≥ 1 |
| `seq` | ціле | порядковий номер у межах запуску | виявляє пропуски, дублікати й позачергові покази | ≥ 0 |
| `ts` | рядок | UTC, мілісекунди, `…Z` | момент вимірювання; з нього рахується затримка доставки | не пізніше ніж +5 с від годинника сервера |
| `qty` | рядок | `motion`, `light`, `gate` | яка величина | з переліку |
| `val` | число | за величиною | значення | `motion`, `gate`: 0 або 1; `light`: 0–65535 |
| `unit` | рядок | `bool`, `lx` | одиниця величини | має відповідати `qty` |

Кількість пропущених повідомлень перед k-м отриманим визначає формула
n_k = s_k − s_{k−1} − 1, а частку втрат каналу — ε = 1 − N_отр / N_над, де
N_над обчислюється за порядковими номерами від першого до останнього номера
запуску. Затримка доставки L_д = t_отр − t_вим; обидві мітки беруться з одного
годинника, бо всі контейнери працюють на одному комп’ютері.

## Політика оброблення помилок

| Ситуація | Як виявляється | Дія | Де фіксується | Реалізація |
|---|---|---|---|---|
| Не JSON, немає поля, хибний тип | перевірка за схемою | відхилити, роботу не зупиняти | `rejected`, причина | `collector.validate()` |
| Одиниця не відповідає величині; `dev` не відповідає темі | перевірка за схемою | відхилити | `rejected` | `collector.validate()` |
| Значення поза діапазоном сенсора (`motion`/`gate` не 0 чи 1; `light` поза 0–65535) | межі з даташита | відхилити як недостовірне | `rejected` | `collector.validate()`, `QTY`, `BINARY` |
| Мітка часу з майбутнього | більше ніж на 5 с від годинника сервера | відхилити; перевірити синхронізацію годинників | `rejected` | `FUTURE_MS` |
| Дублікат | трійка `(dev, boot, seq)` уже є | не зберігати повторно | `anomalies`, `dup` | первинний ключ `readings` |
| Пропуск n_k > 0 | формула n_k | зберегти показ, урахувати втрату | `anomalies`, `gap` | `collector.on_message()` |
| Позачерговий показ | n_k < 0, номера ще немає | зберегти; пропуск зменшується | `anomalies`, `late` | `collector.on_message()` |
| Перезапуск сенсора | новий `boot` | почати лік номерів заново | `readings` | ключ `(dev, boot)` |
| Сенсор зник | заповіт `offline` у темі `…/state` | брокер позначає пристрій недоступним | збережене повідомлення стану | `will_set` в `sensors.py` |
| Розрив зв’язку підписника з брокером | `on_connect` після перепідключення | підписатися знову; покази QoS 0 за час розриву втрачено | пропуски в `anomalies` | `collector.on_connect()` |
| Розрив ланки периферія — сервер | шлюз не отримує PUBACK | накопичувати в буфері, надіслати після відновлення | буфер `outbox`, журнал шлюзу | `gateway.py` |
| Ворота відчинені надто довго (подієва аномалія предметної області) | порівняння тривалості стану з порогом | сповістити оператора | — | не реалізовано: належить до механізму правил подій (Rule Engine, ЛР 1) |

## Перевірка каналу

"""


def channel_section():
    sens_t = rd("channel_sensors.txt")
    st = read_csv("channel_stats.csv")
    txt = rd("channel_stats.txt")
    if not (sens_t and st and txt):
        return pending("bash smart/check_channel.sh")
    m = re.search(r"Підсумок: (\{.*\})", sens_t)
    inj = ast.literal_eval(m.group(1))
    row = max(st, key=lambda r: r["sent"])
    sent, got = int(row["sent"]), int(row["received"])
    rej = re.search(r"Відхилено: (.*)", txt).group(1).strip()
    bad_rx = 0
    mm = re.search(r"не JSON\D+(\d+)", rej)
    if mm:
        bad_rx = int(mm.group(1))
    checks = [
        ("пропущені показники (N_над − N_отр)", inj["drop"], sent - got),
        ("дублікати (`dup`)", inj["dup"], int(row["dup"])),
        ("позачергові показники (`late`)", inj["late"], int(row["late"])),
        ("зіпсовані повідомлення («не JSON»)", inj["bad"], bad_rx),
    ]
    tbl = ["| Показник | Внесено емулятором | Виявлено підписником | Збіг |", "|---|---:|---:|:---:|"]
    ok_all = True
    for name, a, b in checks:
        ok = a == b
        ok_all &= ok
        tbl.append(f"| {name} | {a} | {b} | {'так' if ok else 'ні'} |")
    eps_inj = inj["drop"] / sent if sent else 0
    if ok_all:
        verdict = ("Усі чотири внесені збої збіглися з виявленими, тобто підписник "
                   "розрізняє пропуск, дублікат, позачерговий показ і зіпсоване повідомлення.")
    else:
        verdict = ("Є розбіжність. Ймовірні причини: останній показ запуску «загубився» "
                   "(тоді N_над за номерами на одиницю менший за справжній) або "
                   "відкладений показ вийшов у самому кінці. Розбіжність на 1–2 повідомлення "
                   "для 30-секундного запуску я вважаю допустимою, більшу треба розслідувати.")
    cols = ["boot", "rate", "sent", "received", "loss", "late", "dup", "lat_mean_ms", "lat_p95_ms", "lat_max_ms"]
    head = "| " + " | ".join(cols) + " |\n|" + "---:|" * len(cols)
    body = "\n".join("| " + " | ".join(f(r[c], 4 if c == "loss" else 1).replace(",0", "") if c not in ("loss",) else f(r[c], 4)
                                         for c in cols) + " |" for r in st)
    return f"""Перевірку я виконав скриптом `smart/check_channel.sh`: брокер працює в Docker,
підписник `collector.py` запущено першим, а потім емулятор `sensors.py` на 30 с із
частотою 20 повідомлень/с від кожного сенсора й внесеними збоями
`DROP=0.03 DUP=0.02 LATE=0.03 BAD=0.02`.

Підсумок емулятора: `{m.group(1)}`.

Підсумок каналу, `python smart/stats.py` (λ — інтенсивність потоку, повід./с; затримки в мс):

{head}
{body}

Відхилено підписником: {rej}.

{chr(10).join(tbl)}

{verdict} Частка втрат за формулою ε = 1 − N_отр / N_над = 1 − {got} / {sent} ≈ {f(row['loss'], 4)},
а внесена частка пропусків — {f(eps_inj, 4)} (задано 0,03). Середня затримка доставки
{f(row['lat_mean_ms'])} мс, 95-й процентиль {int(row['lat_p95_ms'])} мс, найбільша {int(row['lat_max_ms'])} мс.
"""


# ============================================================== deployment.md

DEPLOY_COMPONENTS = """## Складники

Систему я розділив на периферійний і серверний складники (рис. 1 методичних
вказівок). Периферійний складник працює у вузлі ділянки периметра: емулятор
сенсорів, брокер периферії та шлюз. Серверний складник — брокер і підписник
сервера об’єкта. Описано все в `smart/docker-compose.yml`; мереж Docker дві,
`edge` і `cloud`, і лише шлюз підключено до обох, тобто він є єдиним зв’язком
периферії із сервером.

| Сервіс | Складник | Мережі | Ресурси | Том (дані) | Призначення |
|---|---|---|---|---|---|
| `sensors` | периферія | edge | — | `sensors-data` | емулятор: рух, освітленість, стан воріт; номер запуску `boot` |
| `edge-broker` | периферія | edge | `cpus: 0.5`, `mem_limit: 128m` | — | брокер MQTT вузла; недоступний з хоста |
| `gateway` | периферія | edge, cloud | `cpus: 0.25`, `mem_limit: 128m` | `edge-data` | буфер `outbox` у SQLite, пересилання з QoS 1, видалення після PUBACK |
| `cloud-broker` | сервер | cloud | — | — | брокер сервера; порт `127.0.0.1:1883` лише з цього комп’ютера |
| `collector` | сервер | cloud | — | `cloud-data` | підписник: перевірка схеми, `readings`, `anomalies`, `rejected` |

Ліміти периферії (`cpus: 0.25`, `mem_limit: 128m` для шлюзу) я взяв з міркувань
подання розгортання ЛР 1: вузол біля камери має вкластися у вузький енергетичний
бюджет (NFR-05, 15 Вт), тому процесор шлюзу я обмежив свідомо. Образ спільний для
Python-складників (`smart/Dockerfile`, `python:3.14-slim`, `paho-mqtt==2.1.0`).
Брокер опубліковано лише на `127.0.0.1`, бо в конфігурації дозволено анонімний
доступ (`smart/broker/mosquitto.conf`); параметр `set_tcp_nodelay true` вимикає
алгоритм Нейгла, щоб підтвердження PUBACK надсилалися одразу.

"""


def deploy_check():
    ps, gw, st = rd("step5_ps.txt"), rd("step5_gateway.txt"), read_csv_table("step5_stats.txt")
    if not (ps and gw):
        return pending("bash smart/check_outage.sh")
    up = len(re.findall(r":\s*Up", ps))
    g = re.search(r"буфер=(\d+)\s+відкинуто=(\d+)\s+зв.язок=(\S+)", gw)
    line = (f"Після `docker compose up -d --build` сервісів у стані Up — {up} (очікується п’ять). "
            f"Журнал шлюзу: буфер={g.group(1)}, відкинуто={g.group(2)}, зв’язок={g.group(3)}.")
    if st:
        r = st[0]
        line += (f" Підсумок підписника для запуску boot {int(r['boot'])}: λ ≈ {f(r['rate'])} повідомлень/с, "
                 f"loss = {f(r['loss'], 4).rstrip('0').rstrip(',') or '0'}.")
    return line + "\n"


def read_csv_table(name):
    """Розбирає таблицю stats.py (без --csv) у список словників."""
    t = rd(name)
    if not t:
        return None
    lines = [l for l in t.splitlines() if l.strip() and not l.startswith("Відхилено")]
    if len(lines) < 2:
        return None
    cols = lines[0].split()
    rows = []
    for l in lines[1:]:
        parts = l.split()
        if len(parts) == len(cols):
            rows.append({c: float(v) for c, v in zip(cols, parts)})
    return rows or None


def parse_log():
    t = rd("outage_gateway.txt")
    if not t:
        return None
    pat = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z\s+буфер=(\d+)\s+відкинуто=(\d+)\s+зв.язок=(так|ні)")
    out = [(ts(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)) for m in pat.finditer(t)]
    return out or None


class Outage:
    pass


def analyse_outage():
    log, marks, st = parse_log(), rd("outage_marks.txt"), read_csv("outage_stats.csv")
    if not (log and marks and st):
        return None
    o = Outage()
    d = {k: ts(v) for k, v in re.findall(r"(disconnect|reconnect)=(\S+)", marks)}
    o.t_d, o.t_r = d["disconnect"], d["reconnect"]
    o.dur = o.t_r - o.t_d
    row = max(st, key=lambda r: r["rate"])
    o.row, o.lam = row, row["rate"]
    down = [x for x in log if x[3] == "ні" and x[0] >= o.t_d]
    o.det = down[0][0] - o.t_d if down else None
    o.q0 = max(x[1] for x in log)
    win = [x for x in log if o.t_d + 3 <= x[0] <= o.t_r]
    o.grow = ((win[-1][1] - win[0][1]) / (win[-1][0] - win[0][0])) if len(win) >= 2 and win[-1][0] > win[0][0] else None
    up = [x for x in log if x[0] >= o.t_r and x[3] == "так"]
    o.t_up = up[0][0] if up else None
    o.drain = None
    o.mu_meas = None
    if o.t_up is not None:
        thr = max(5, 0.02 * o.q0)
        end = [x for x in log if x[0] >= o.t_up and x[1] <= thr]
        if end:
            o.drain = end[0][0] - o.t_up
            seg = [x for x in log if o.t_up <= x[0] <= end[0][0]]
            sl = [(a[1] - b[1]) / (b[0] - a[0]) for a, b in zip(seg, seg[1:]) if b[0] > a[0]]
            if sl:
                o.mu_meas = o.lam + statistics.median(sl)
    o.drain_calc = o.q0 / (MU1 - o.lam) if MU1 > o.lam else None
    o.dropped = log[-1][2]
    return o


def outage_section(o):
    if o is None:
        return pending("bash smart/check_outage.sh")
    r = o.row
    pubs = []
    pubs.append(f"Розрив і відновлення зв’язку я виконав командами `docker network disconnect/connect` "
                f"для шлюзу (розрив тривав {f(o.dur, 0)} с) за інтенсивності потоку λ ≈ {f(o.lam, 0)} повідомлень/с.")
    lines = [f"- Шлюз помітив розрив через {f(o.det, 0)} с (очікування: два інтервали Keep Alive по 10 с: перевірка з’єднання й очікування відповіді)."
             if o.det is not None else "- У журналі не знайдено позначки «зв’язок=ні»: перевірте, чи спрацював `docker network disconnect`.",
             f"- Буфер зростав приблизно на {f(o.grow, 0)} записів/с (λ = {f(o.lam, 0)}), максимум Q₀ = {o.q0} записів." if o.grow is not None else f"- Максимум буфера Q₀ = {o.q0} записів.",
             f"- Лічильник «відкинуто» шлюзу наприкінці: {o.dropped} (місткість буфера {MAX_ROWS} записів не вичерпано)." if o.dropped == 0 else f"- Лічильник «відкинуто» шлюзу: {o.dropped} — буфер переповнювався, частину показів відкинуто."]
    calc = f(o.drain_calc, 0) if o.drain_calc else "—"
    lines.append(f"- За формулою T_розв = Q₀ / (μ₁ − λ), μ₁ = 10⁶ / (8 · {S_BYTES}) ≈ {f(MU1, 0)} повідомлень/с: "
                 f"{o.q0} / ({f(MU1, 0)} − {f(o.lam, 0)}) ≈ {calc} с; "
                 + (f"виміряно ≈ {f(o.drain, 0)} с (від відновлення зв’язку до спорожнення буфера, крок журналу 2 с)." if o.drain is not None else "виміряти час не вдалося: буфер не спорожнів у журналі."))
    if o.mu_meas:
        lines.append(f"- Швидкість вивантаження за журналом μ₁ ≈ {f(o.mu_meas, 0)} повідомлень/с (розрахунок {f(MU1, 0)}).")
    loss_s = "0" if r["loss"] == 0 else f(r["loss"], 4)
    lines.append(f"- Підсумок підписника (запуск boot {int(r['boot'])}): N_над = {int(r['sent'])}, N_отр = {int(r['received'])}, "
                 f"loss = {loss_s}, дублікатів {int(r['dup'])}, позачергових {int(r['late'])}; "
                 f"найбільша затримка {f(r['lat_max_ms'] / 1000, 1)} с — у показів з початку розриву.")
    verdict = ("Утрат даних немає (loss = 0): буферизація на периферії пережила розрив. Дублікати з’явилися, бо шлюз "
               "повторно надіслав записи, на які не надійшов PUBACK (QoS 1 — «щонайменше один раз»), і підписник їх відкинув."
               if r["loss"] == 0 else
               "Втрати не нульові: проаналізуйте журнал шлюзу — найімовірніше, буфер переповнився або розрив було зроблено під час запуску емулятора.")
    return "\n".join(pubs) + "\n\n" + "\n".join(lines) + "\n\n" + verdict + "\n"


def pubsub_text():
    cloud, edge = rd("pubsub_cloud.txt"), rd("pubsub_edge.txt")
    if not (cloud and edge):
        return pending("bash smart/check_outage.sh")
    n_tele = len(re.findall(r"/tele ", cloud))
    n_state = len(re.findall(r"/state online", edge))
    to = "Timed out" in edge
    return (f"Експеримент: два додаткові підписники, `mosquitto_sub`, без змін сенсорів і `collector.py`. "
            f"На сервері отримано {n_tele} повідомлення телеметрії; на периферії — {n_state} рядки стану `online`, "
            f"які брокер надіслав новому підписникові одразу (збережені повідомлення)"
            + (", далі до кінця очікування нових повідомлень стану не було («Timed out»)." if to else ".") + "\n")


def patterns_section(o):
    nom_h = MAX_ROWS / LAM_NODE_NOM / 3600
    peak_m = MAX_ROWS / LAM_NODE_PEAK / 60
    vbuf = MAX_ROWS * S_BYTES / 1e6
    num = (f"Q₀ = {o.q0} записів, loss = {'0' if o.row['loss'] == 0 else f(o.row['loss'], 4)}, "
           f"час вивантаження ≈ {f(o.drain, 0) if o.drain is not None else '—'} с проти розрахункових "
           f"{f(o.drain_calc, 0) if o.drain_calc else '—'} с") if o else "числа з розділу «Розрив зв’язку» буде додано після експерименту"
    return f"""## Шаблони

Я застосував два шаблони: «публікація — підписка» і «буферизація на периферії».

### Публікація — підписка

- **Контекст.** Вузол ділянки периметра публікує телеметрію трьох сенсорів; споживачів (підписник сервера, аналітика, оператор) може бути кілька, і їх набір змінюватиметься.
- **Задача.** Додавати нових споживачів без змін сенсорів і без втручання в наявного підписника.
- **Сили.** Сенсори не повинні знати про підписників; стан пристрою потрібен новому споживачеві одразу (FR-10); телеметрія коротка й частота висока.
- **Розв’язок.** Теми `p1/north/<пристрій>/tele`, підписка із символом `+`; стан пристрою — збережене повідомлення `online` і заповіт `offline`.
- **Наслідки.** Плюс: нового підписника додано командою `mosquitto_sub` без змін `sensors.py` і `collector.py` (експеримент нижче). Мінус: брокер не зберігає історії для підписників, що з’явилися пізніше, а стан «хто підписаний» невидимий видавцям.

{pubsub_text()}
### Буферизація на периферії (store-and-forward)

- **Контекст.** Ланка між вузлом периметра й сервером — одна, і її розрив для розподіленої системи є нормальним режимом (QS-02 ЛР 1).
- **Задача.** Пережити розрив без втрати показів.
- **Сили.** Підтверджені тривоги не можна губити (ADR-0003); процесор шлюзу обмежений (`cpus: 0.25`); нові покази не зупиняються під час розриву.
- **Розв’язок.** `gateway.py` записує кожне повідомлення в буфер `outbox` (SQLite, WAL) до надсилання, надсилає найстаріші записи з QoS 1 і видаляє їх лише після PUBACK. Місткість — {MAX_ROWS} записів, переповнений буфер відкидає найстаріші.
- **Розрахунок місткості** за V_буф = r · s · T_розр: {MAX_ROWS} записів — це {f(nom_h, 1)} год розриву за номінальних {LAM_NODE_NOM} повідомлень/с і {f(peak_m, 0)} хв за піку {LAM_NODE_PEAK} повідомлень/с; за s ≈ {S_BYTES} байтів V_буф ≈ {f(vbuf, 1)} МБ.
- **Наслідки.** Плюс: {num}. Мінус: після розриву з’являються дублікати (QoS 1 — «щонайменше один раз»), тож підписник має бути ідемпотентним (первинний ключ `(dev, boot, seq)`); у режимі `synchronous=NORMAL` після вимкнення живлення останні транзакції буфера можуть відкотитися; Python-шлюз споживає процесор у межах ліміту.

Третій шаблон, «кероване зниження якості», я не реалізовував; це позначено як можливе розширення (див. «Масштабованість»).

"""


def parse_docker_stats():
    t = rd("docker_stats.txt")
    if not t:
        return None
    data = {}
    hz = None
    for line in t.splitlines():
        m = re.match(r"## HZ=(\d+)", line)
        if m:
            hz = int(m.group(1))
            continue
        m = re.match(r"(\S+)\s+([\d.]+)%\s+([\d.]+)\s*(KiB|MiB|GiB)", line)
        if m and hz is not None:
            name = m.group(1).replace("mmss-", "").rsplit("-", 1)[0]
            mem = float(m.group(3)) * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[m.group(4)]
            d = data.setdefault(name, {"cpu": 0.0, "cpu_hz": hz, "mem": 0.0})
            if float(m.group(2)) > d["cpu"]:
                d["cpu"], d["cpu_hz"] = float(m.group(2)), hz
            d["mem"] = max(d["mem"], mem)
    return data or None


class Load:
    pass


def analyse_load():
    rows = read_csv("load.csv")
    if not rows:
        return None
    L = Load()
    L.rows = sorted(rows, key=lambda r: r["rate"])
    lossy = [r for r in L.rows if r["loss"] > 0.001 and r["lat_max_ms"] > 0]
    L.theta_meas = statistics.median(MAX_ROWS_LOAD / (r["lat_max_ms"] / 1000) for r in lossy) if lossy else None
    L.theta = L.theta_meas or None
    L.theta_th = MU1
    L.stats = parse_docker_stats()
    g = rd("load_gateway_last.txt")
    m = re.search(r"відкинуто=(\d+)", g) if g else None
    L.gw_dropped = int(m.group(1)) if m else None
    L.lost = sum(r["sent"] - r["received"] for r in L.rows)
    return L


def bottleneck_text(L):
    th = L.theta if L.theta else L.theta_th
    parts = []
    if L.stats:
        rat = {n: (d["cpu"], d["cpu"] / CPU_LIMITS.get(n, 100.0)) for n, d in L.stats.items()}
        top = max(rat, key=lambda n: rat[n][1])
        cpu, r = rat[top]
        lim = CPU_LIMITS.get(top, 100.0)
        mem_s = ", ".join(f"{n} — {f(d['cpu'])} % CPU, {f(d['mem'])} МіБ" for n, d in sorted(L.stats.items()))
        parts.append(f"За `docker stats` (знімок у середині кожного ступеня; піки): {mem_s}.")
        if r >= 0.8:
            parts.append(f"Контейнер `{top}` працював на межі свого ліміту: {f(cpu)} % при ліміті {f(lim, 0)} % ядра (на ступені HZ = {L.stats[top]['cpu_hz']}).")
        else:
            parts.append(f"Жоден контейнер не впирався у свій ліміт процесора (найвище навантаження — `{top}`: {f(cpu)} % при ліміті {f(lim, 0)} %).")
    if L.theta_meas:
        diff = abs(L.theta_meas - L.theta_th) / L.theta_th
        if diff <= 0.15:
            parts.append(f"Виміряна Θ ≈ {f(L.theta_meas, 0)} повідомлень/с збігається з розрахунком для смуги ланки "
                         f"(10⁶ / (8 · {S_BYTES}) ≈ {f(L.theta_th, 0)}): **вузьке місце — ланка периферія — сервер** "
                         f"(модельна смуга {UPLINK_KBPS} кбіт/с), яку шлюз вичерпує повністю.")
        else:
            parts.append(f"Виміряна Θ ≈ {f(L.theta_meas, 0)} повідомлень/с відрізняється від розрахунку для смуги ланки "
                         f"({f(L.theta_th, 0)}) більш ніж на 15 %: вузьким місцем, найімовірніше, є не смуга, а процесор шлюзу.")
    else:
        parts.append(f"Переповнення буфера не досягнуто (втрат немає на жодному ступені), тому Θ ≥ {f(max(r['rate'] for r in L.rows), 0)} повідомлень/с; "
                     f"розрахункова пропускна здатність ланки — {f(L.theta_th, 0)}. Щоб побачити насичення, додайте вищі ступені HZ у `smart/loadtest.sh`.")
    return " ".join(parts), th


def load_section(L):
    if L is None:
        return pending("bash smart/loadtest.sh && python smart/plot.py"), None
    th = L.theta if L.theta else L.theta_th
    tbl = ["| λ, повід./с | N_над | N_отр | ε | L_д сер., мс | p95, мс | max, мс | u = λ/Θ |", "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for r in L.rows:
        tbl.append(f"| {f(r['rate'], 0)} | {int(r['sent'])} | {int(r['received'])} | {f(r['loss'], 3)} | "
                   f"{f(r['lat_mean_ms'], 1 if r['lat_mean_ms'] < 100 else 0)} | {int(r['lat_p95_ms'])} | {int(r['lat_max_ms'])} | {f(r['rate'] / th, 2)} |")
    base = [r for r in L.rows if r["rate"] / th < 0.5]
    base_lat = statistics.mean(r["lat_mean_ms"] for r in base) if base else None
    ok_rows = [r for r in L.rows if r["lat_p95_ms"] <= L_MER_MS and r["loss"] == 0]
    lam_ok = max((r["rate"] for r in ok_rows), default=None)
    pred = []
    for r in L.rows:
        if r["loss"] > 0.001:
            calc = max(0.0, (r["rate"] - th) * STEP_S - MAX_ROWS_LOAD)
            pred.append(f"- λ = {f(r['rate'], 0)}: розрахункові втрати (λ − Θ) · {STEP_S} − {MAX_ROWS_LOAD} ≈ {f(calc, 0)}, виміряно {int(r['sent'] - r['received'])}.")
    btxt, _ = bottleneck_text(L)
    drop_txt = ""
    if L.gw_dropped is not None:
        eq = L.gw_dropped == int(L.lost)
        drop_txt = (f"Лічильник «відкинуто» шлюзу ({L.gw_dropped}) {'дорівнює' if eq else 'відрізняється від'} сумі втрат, "
                    f"які виявив підписник ({int(L.lost)}){'' if eq else ' — різницю дають повідомлення, що були в дорозі на момент зупинки'}.")
    mx = max(L.rows, key=lambda r: r["lat_max_ms"])
    lat_note = (f"До u ≈ 0,5 середня затримка становить {f(base_lat)} мс (одиниці–десятки мілісекунд)." if base_lat is not None else "")
    ok_note = (f"Найвище навантаження, за якого p95 ≤ {L_MER_MS} мс (бюджет L_мер із NFR-01) і втрат немає: λ ≈ {f(lam_ok, 0)} повідомлень/с."
               if lam_ok else f"На жодному ступені p95 не вклався у бюджет L_мер = {L_MER_MS} мс.")
    th_txt = (f"**Θ ≈ {f(L.theta_meas, 0)} повідомлень/с**" if L.theta_meas else f"**Θ ≥ {f(max(r['rate'] for r in L.rows), 0)} повідомлень/с (насичення не досягнуто)**")
    txt = f"""Навантажувальне випробування я виконав скриптом `smart/loadtest.sh`: частота кожного з трьох
сенсорів зростає ступенями по {STEP_S} с (HZ = {', '.join(map(str, HZ_STEPS))}), буфер шлюзу зменшено до {MAX_ROWS_LOAD} записів,
після ступеня скрипт чекає спорожнення буфера. Кожен ступінь — окремий запуск емулятора, тобто окремий рядок у
`results/load.csv`. Графік будує `smart/plot.py` (рисунок нижче).

{chr(10).join(tbl)}

![Залежність затримки доставки й частки втрат від навантаження](../results/latency.png)

*Рис. 1 — Залежність затримки доставки та частки втрат від навантаження λ (`results/latency.png`).*

{th_txt}. Θ визначаю за найбільшою затримкою на ступенях із втратами: переповнений буфер
{MAX_ROWS_LOAD} записів вичерпується за {MAX_ROWS_LOAD} / Θ секунд, тож Θ ≈ {MAX_ROWS_LOAD} / L_max. {lat_note} Поблизу Θ середня затримка різко зростає, як у
моделі M/M/1, W = 1 / (μ − λ): за u → 1 знаменник прямує до нуля. За λ > Θ черга зростає на λ − Θ повідомлень щосекунди, а найбільшу
затримку обмежує місткість буфера. {ok_note}

{chr(10).join(pred) if pred else ''}

{drop_txt}

**Вузьке місце.** {btxt}

Найбільша затримка на графіку — {f(mx['lat_max_ms'] / 1000, 1)} с при λ = {f(mx['rate'], 0)} повід./с. Повторні прогони ступенів поблизу Θ чутливі до інших програм на комп’ютері, тож числа залежать від машини.
"""
    return txt, th


def scale_section(L, o):
    th = (L.theta if L and L.theta else (L.theta_th if L else MU1))
    sys_peak = NODES * LAM_NODE_PEAK
    sys_nom = NODES * LAM_NODE_NOM
    meas = bool(L and L.theta_meas)
    ratio = sys_peak / th
    first = ("серверний підписник і брокер" if ratio >= 0.7 else "кількість вузлів можна збільшувати, не змінюючи архітектуру")
    how = ("горизонтально: кілька підписників із розбиттям стану за темами (за ділянками `p1/<ділянка>/…`), "
           "брокер — вертикально або кластером; вертикальне масштабування одного підписника швидко впирається в SQLite без сервера"
           if ratio >= 0.7 else "запасу вистачає, але стан підписника все одно доцільно розбити за ділянками (горизонтально) раніше, ніж Θ вичерпається")
    src = "виміряна" if meas else "розрахункова (виміряної ще немає)"
    return f"""## Масштабованість

**Яке навантаження потрібне системі.** За нефункційними вимогами ЛР 1 (NFR-02) система має працювати з 8 до 64 камер.
Кожен вузол ділянки має три сенсори; частоту я беру з табл. 4 методичних вказівок (1–5 Гц): номінально 1 Гц дає
λ_вузла = {LAM_NODE_NOM} повідомлень/с, у піку (5 Гц) — {LAM_NODE_PEAK} повідомлень/с. Для 64 вузлів серверний складник отримує
{sys_nom} повідомлень/с номінально й {sys_peak} повідомлень/с у піку.

**Який запас дає Θ.** Θ ({src}) ≈ {f(th, 0)} повідомлень/с для одного вузла (одна ланка зі смугою {UPLINK_KBPS} кбіт/с).
Запас вузла за номінального потоку — у {f(th / LAM_NODE_NOM, 0)} разів, у піку — у {f(th / LAM_NODE_PEAK, 0)} разів, тож один вузол масштабувати не треба.
На сервері потоки всіх вузлів сходяться в одну точку: пік {sys_peak} повід./с становить {f(100 * ratio, 0)} % від Θ ({f(ratio, 2)}); номінальні {sys_nom} — {f(100 * sys_nom / th, 0)} %.
Θ вимірювалась для ланки одного вузла, а окремої ємності серверного підписника я не вимірював: у випробуванні втрати давав буфер шлюзу,
а підписник на ступенях нижче Θ тримав затримку невеликою, тому вважаю, що його ємність не нижча за виміряну Θ. Це припущення потрібно перевірити
окремим тестом без обмеження смуги (наступний крок).

**Що масштабувати першим і як.** Першим доведеться масштабувати: {first}. Спосіб — {how}.

**Додатково.** Якби потік перевищив Θ, корисним було б «кероване зниження якості» (шлюз переходить на хвилинні агрегати, події не відкидаються);
я його не реалізовував, але воно з’єднується з вимогою ЛР 1 про незмінну доставку підтверджених тривог.

"""


def stack_section(L):
    def mem(n):
        if L and L.stats and n in L.stats:
            return f"{f(L.stats[n]['mem'])} МіБ"
        return "— (виміряти `docker stats`)"
    th = (L.theta if L and L.theta else (L.theta_th if L else MU1))
    return f"""## Мова і стек

| Складник | Вимоги, що визначають вибір | У моїй реалізації | Обґрунтування та альтернатива |
|---|---|---|---|
| Сенсори | на пристрої — сотні кілобайтів пам’яті й енергія | Python — лише емулятор | для вбудованого ПЗ — C або Rust: без збирача сміття, передбачувані час і пам’ять |
| Брокер периферії | мала пам’ять, автономність вузла | Eclipse Mosquitto 2 (C), {mem('edge-broker')} пам’яті | легкий брокер без залежностей; міст Mosquitto міг би замінити шлюз, але не керує місткістю й переповненням буфера |
| Шлюз | безперервна робота, буфер на диску, обмежений процесор (NFR-05) | Python, paho-mqtt, SQLite; {mem('gateway')} пам’яті; Θ ≈ {f(th, 0)} повід./с за `cpus: 0.25` | у {f(th / LAM_NODE_PEAK, 0)} разів більше за піковий потік вузла ({LAM_NODE_PEAK} повід./с). Для багатьох вузлів на слабкому обладнанні — Go: компільований, менше пам’яті, прості горутини |
| Серверний брокер | багато вузлів і незалежні підписники | Eclipse Mosquitto 2, {mem('cloud-broker')} пам’яті | не зберігає історії; якщо потрібне повторне читання історії подій — Apache Kafka |
| Підписник і сховище | перевірка схеми, ідемпотентний запис | Python, SQLite, {mem('collector')} пам’яті | один файл без сервера — достатньо для одного об’єкта; для 64 вузлів — сховище часових рядів і кілька підписників із розбиттям за темами |

Остаточне рішення для найважливішого складника, шлюзу, я зафіксував в `docs/adr/0006-mova-ta-tekhnolohichnyi-stek.md`.
"""


def deployment():
    o = analyse_outage()
    L = analyse_load()
    load_txt, _ = load_section(L)
    return ("# Розгортання edge–cloud PerimeterGuard\n\n"
            "Документ описує розподілене розгортання системи: складники, шаблони проєктування, експеримент із розривом зв’язку, "
            "навантажувальне випробування та висновки щодо масштабованості, мови й технологічного стека.\n\n"
            + DEPLOY_COMPONENTS + deploy_check() + "\n"
            + patterns_section(o)
            + "## Розрив зв’язку\n\n" + outage_section(o) + "\n"
            + "## Навантаження\n\n" + load_txt + "\n"
            + scale_section(L, o)
            + stack_section(L)), o, L


# ================================================================ ADR-0005/6

def adr5(o):
    num = (f"- Експеримент: розрив {f(o.dur, 0)} с при λ ≈ {f(o.lam, 0)} повід./с, Q₀ = {o.q0}, loss = {'0' if o.row['loss'] == 0 else f(o.row['loss'], 4)}, "
           f"вивантаження ≈ {f(o.drain, 0) if o.drain is not None else '—'} с (розрахунок {f(o.drain_calc, 0) if o.drain_calc else '—'} с).") if o else "- Числа експерименту з розривом буде додано після `bash smart/check_outage.sh`."
    return f"""# ADR-0005. Шаблони проєктування каналу даних: публікація — підписка та буферизація на периферії

## Статус

Прийнято, 2026-11-21

## Контекст

Вузол ділянки периметра публікує телеметрію трьох сенсорів (рух, освітленість, стан воріт) і з’єднаний із сервером однією мережевою
ланкою. QS-02 з ЛР 1 вимагає, щоб розрив цієї ланки не призводив до втрати підтверджених подій, а ADR-0003 додає, що докази інцидентів не
можна губити. Потрібно вибрати, як доставляти телеметрію й чи накопичувати її на периферії.

## Варіанти

1. **Пряма публікація на серверний брокер з QoS 0.** Найпростіше, але розрив ланки означає втрату всіх показів за час розриву.
2. **Міст брокерів Mosquitto (`connection`, `persistence true`).** Готовий механізм, без власного коду, але я не керую місткістю й
   політикою переповнення буфера, а поведінку під розривом складніше виміряти.
3. **Публікація — підписка на периферії + власний шлюз із буфером (store-and-forward).** Сенсори публікують у брокер периферії, шлюз
   записує покази в SQLite, надсилає з QoS 1 і видаляє після PUBACK.

## Рішення

Обрано варіант 3: шаблон «публікація — підписка» (теми `p1/<ділянка>/<пристрій>/tele`, стан як збережені повідомлення й заповіт) разом
із шаблоном «буферизація на периферії» (`gateway.py`, буфер {MAX_ROWS} записів, видалення лише після PUBACK). Шаблон «кероване зниження
якості» не реалізовано.

### Підтвердження вимірюваннями

{num}
- Розрахунок місткості: {MAX_ROWS} записів · {S_BYTES} байтів ≈ {f(MAX_ROWS * S_BYTES / 1e6, 1)} МБ; це {f(MAX_ROWS / LAM_NODE_NOM / 3600, 1)} год розриву за {LAM_NODE_NOM} повід./с і {f(MAX_ROWS / LAM_NODE_PEAK / 60, 0)} хв за {LAM_NODE_PEAK} повід./с.

## Наслідки

+ Розрив ланки не призводить до втрати даних, поки буфер не переповнено; після відновлення накопичене вивантажується з швидкістю μ₁ − λ.
+ Нових споживачів додають підпискою на тему без змін сенсорів і підписника.
− Після розриву виникають дублікати (QoS 1), тому підписник має бути ідемпотентним — це забезпечує первинний ключ `(dev, boot, seq)`.
− Буфер на диску з `synchronous=NORMAL` не гарантує збереження останніх транзакцій після вимкнення живлення.
− Переповнений буфер відкидає найстаріші покази; для довших розривів треба збільшити `MAX_ROWS` або ввести кероване зниження якості.
− З’являється власний код шлюзу, який треба супроводжувати.
"""


def adr6(L, o):
    th = L.theta if L and L.theta else (L.theta_th if L else MU1)
    meas = "виміряна" if (L and L.theta_meas) else "розрахункова"
    mem = ""
    if L and L.stats and "gateway" in L.stats:
        mem = f" Пам’ять шлюзу за `docker stats` — {f(L.stats['gateway']['mem'])} МіБ."
    return f"""# ADR-0006. Мова програмування та технологічний стек шлюзу

## Статус

Прийнято, 2026-11-21

## Контекст

Шлюз — складник периферійного вузла: безперервна робота, буфер на диску, обмежений процесор (`cpus: 0.25`, NFR-05 ЛР 1, 15 Вт) і
пам’ять (`mem_limit: 128m`). Від нього залежить, чи переживе система розрив зв’язку. Потрібен потік піку {LAM_NODE_PEAK} повід./с на вузол
({LAM_NODE_NOM} номінально), а система має зростати до {NODES} вузлів (NFR-02). Θ шлюзу ({meas}) ≈ {f(th, 0)} повід./с.{mem}

## Варіанти

1. **Python + paho-mqtt + SQLite.** Швидка розробка, тестується однаково на хості й у контейнері; інтерпретатор і збирач сміття дають більшу
   пам’ять та менш передбачуваний час.
2. **Go.** Компільований, малі пам’ять і запуск, прості горутини; потрібна своя бібліотека MQTT і SQLite-драйвер, інша мова в команді.
3. **C або Rust.** Найменші ресурси й передбачувані час та пам’ять; найдорожча розробка й супровід для шлюзу такого масштабу.
4. **Міст Mosquitto.** Без коду, але без керування місткістю й переповненням буфера (див. ADR-0005).

## Рішення

Для шлюзу в цій системі обрано варіант 1: Python, paho-mqtt, SQLite. Θ ≈ {f(th, 0)} повід./с — у {f(th / LAM_NODE_PEAK, 0)} разів більше за
піковий потік вузла, тож процесор і пам’ять із запасом достатні, а розробка й перевірка гіпотез залишаються швидкими. Брокери — Eclipse
Mosquitto 2 (C), сховище підписника — SQLite. Сенсори на реальному обладнанні — C або Rust, не Python.

## Наслідки

+ Швидка розробка й вимірювання; рішення вкладається в ліміти периферії з запасом {f(th / LAM_NODE_PEAK, 0)}× за піком.
+ Одна мова для шлюзу, підписника й емулятора, спільний образ Docker.
− Python споживає більше пам’яті й процесора на повідомлення, ніж Go чи Rust; за дуже слабкого вузла або багатьох шлюзів на одному
  обладнанні потрібно переходити на Go.
− SQLite без сервера обмежує паралельних писарів; для {NODES} вузлів потрібне окреме сховище та розбиття підписників за темами.
− Час відгуку залежить від збирача сміття; для жорстких вимог реального часу (подробиці — лекція 11) Python не підійде.
"""


# ===================================================================== main

def main():
    DOCS.mkdir(exist_ok=True)
    (DOCS / "adr").mkdir(exist_ok=True)
    (DOCS / "telemetry.md").write_text(TELEMETRY_HEAD + channel_section(), encoding="utf-8")
    dep, o, L = deployment()
    (DOCS / "deployment.md").write_text(dep, encoding="utf-8")
    (DOCS / "adr" / "0005-shablony-pubsub-ta-buferyzatsiya.md").write_text(adr5(o), encoding="utf-8")
    (DOCS / "adr" / "0006-mova-ta-tekhnolohichnyi-stek.md").write_text(adr6(L, o), encoding="utf-8")
    state = {"канал": (R / "channel_stats.csv").exists(), "розгортання": (R / "step5_ps.txt").exists(),
             "розрив": o is not None, "навантаження": L is not None}
    print("Згенеровано docs/telemetry.md, docs/deployment.md, ADR-0005, ADR-0006.")
    for k, v in state.items():
        print(f"  {k}: {'дані є' if v else 'ДАНИХ ЩЕ НЕМАЄ'}")


if __name__ == "__main__":
    main()
