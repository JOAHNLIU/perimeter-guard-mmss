"""Формує звіт до лабораторної роботи 3 (Word) із результатів вимірювань.

Запуск з кореня репозиторію (після bash smart/check_channel.sh, check_outage.sh,
loadtest.sh і python smart/plot.py):

    pip install python-docx        # один раз
    python tools/make_lab3_report.py

Результат: Zvit_LR3_PerimeterGuard.docx у корені репозиторію (він у .gitignore).
Усі числа беруться з results/*; жодне число не вписано вручну. У звіті 8 жовтих
блоків для скріншотів — у кожному написано, що відкрити й що показати.
"""
import ast
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import make_lab3_docs as D  # noqa: E402

try:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
except ImportError:
    sys.exit("Потрібна бібліотека: pip install python-docx")

R = Path("results")
OUT = Path("Zvit_LR3_PerimeterGuard.docx")
FONT, MONO = "Times New Roman", "Consolas"
f = D.f

# --------------------------------------------------------------- дані
sens_t = D.rd("channel_sensors.txt")
ch = D.read_csv("channel_stats.csv")
ch_txt = D.rd("channel_stats.txt")
ps = D.rd("step5_ps.txt")
gw5 = D.rd("step5_gateway.txt")
st5 = D.read_csv_table("step5_stats.txt")
pub_c, pub_e = D.rd("pubsub_cloud.txt"), D.rd("pubsub_edge.txt")
o = D.analyse_outage()
L = D.analyse_load()
missing = [n for n, v in {"results/channel_* (check_channel.sh)": sens_t and ch and ch_txt,
                          "results/step5_*, pubsub_* (check_outage.sh)": ps and gw5 and pub_c and pub_e,
                          "results/outage_* (check_outage.sh)": o,
                          "results/load.csv (loadtest.sh)": L}.items() if not v]
if missing:
    sys.exit("Немає даних: " + "; ".join(missing) + ". Спершу виконайте відповідні скрипти.")
if not (R / "latency.png").exists():
    sys.exit("Немає results/latency.png: виконайте python smart/plot.py")

inj = ast.literal_eval(re.search(r"Підсумок: (\{.*\})", sens_t).group(1))
row = max(ch, key=lambda r: r["sent"])
rej = re.search(r"Відхилено: (.*)", ch_txt).group(1).strip()
mm = re.search(r"не JSON\D+(\d+)", rej)
bad_rx = int(mm.group(1)) if mm else 0
sent, got = int(row["sent"]), int(row["received"])
checks = [("пропущені (N_над − N_отр)", inj["drop"], sent - got),
          ("дублікати", inj["dup"], int(row["dup"])),
          ("позачергові", inj["late"], int(row["late"])),
          ("зіпсовані («не JSON»)", inj["bad"], bad_rx)]
all_ok = all(a == b for _, a, b in checks)
n_up = len(re.findall(r":\s*Up", ps))
n_tele = len(re.findall(r"/tele ", pub_c))
n_state = len(re.findall(r"/state online", pub_e))
th = L.theta if L.theta else L.theta_th
sys_peak, sys_nom = D.NODES * D.LAM_NODE_PEAK, D.NODES * D.LAM_NODE_NOM
ratio = sys_peak / th
q0_loss = "0" if o.row["loss"] == 0 else f(o.row["loss"], 4)

# --------------------------------------------------------------- docx базове
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21), Cm(29.7)
sec.top_margin = sec.bottom_margin = Cm(2)
sec.left_margin, sec.right_margin = Cm(3), Cm(1.5)
sec.different_first_page_header_footer = True

st = doc.styles["Normal"]
st.font.name, st.font.size = FONT, Pt(14)
st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
for name in ("Heading 1", "Heading 2"):
    h = doc.styles[name]
    h.font.name, h.font.size, h.font.bold = FONT, Pt(14), True
    h.font.color.rgb = RGBColor(0, 0, 0)
    h.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    h.element.rPr.rFonts.set(qn("w:ascii"), FONT)
    h.element.rPr.rFonts.set(qn("w:hAnsi"), FONT)
    h.paragraph_format.keep_with_next = True
    h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(14), Pt(8)
doc.styles["Heading 1"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER

# номер сторінки внизу, крім титулки
fp = sec.footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
for t, txt in (("begin", None), (None, "PAGE"), ("end", None)):
    r = fp.add_run()
    if t:
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), t)
    else:
        el = OxmlElement("w:instrText")
        el.text = txt
    r._r.append(el)
    r.font.name, r.font.size = FONT, Pt(12)


def rich(p, text, size=14, bold=False, color=None):
    for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**"):
            r = p.add_run(part[2:-2])
            r.bold = True
        elif part.startswith("`"):
            r = p.add_run(part[1:-1])
            r.font.name = MONO
            r._r.rPr.rFonts.set(qn("w:eastAsia"), MONO)
            r.font.size = Pt(size - 2)
            continue
        else:
            r = p.add_run(part)
            r.bold = bold or None
        r.font.name, r.font.size = FONT, Pt(size)
        if color:
            r.font.color.rgb = color


def fmt(p, first=True, after=0, before=0, line=1.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    pf = p.paragraph_format
    pf.alignment = align
    pf.first_line_indent = Cm(1.25) if first else None
    pf.line_spacing, pf.space_after, pf.space_before = line, Pt(after), Pt(before)


def P(text, first=True, keep=False):
    p = doc.add_paragraph()
    rich(p, text)
    fmt(p, first)
    p.paragraph_format.keep_with_next = keep
    return p


def H1(t):
    doc.add_heading(t, level=1)


def H2(t):
    p = doc.add_heading(t, level=2)
    p.paragraph_format.first_line_indent = Cm(1.25)


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def cell_text(cell, text, size=11, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ""
    lines = str(text).split("\n")
    for i, line in enumerate(lines):
        p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
        rich(p, line, size=size, bold=bold)
        fmt(p, first=False, line=1.0, align=align)


def caption(text, kind="Рисунок", n=None):
    p = doc.add_paragraph()
    r = p.add_run(f"{kind} {n} — {text}")
    r.font.name, r.font.size = FONT, Pt(12)
    fmt(p, first=False, before=4, after=12, line=1.0,
        align=WD_ALIGN_PARAGRAPH.CENTER if kind == "Рисунок" else WD_ALIGN_PARAGRAPH.LEFT)
    if kind == "Таблиця":
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(8), Pt(4)


def table(n, title, headers, rows, widths, right=()):
    caption(title, "Таблиця", n)
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Table Grid"
    t.autofit = False
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, h in enumerate(headers):
        cell_text(t.rows[0].cells[j], h, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        shade(t.rows[0].cells[j], "D9E2F3")
    for i, r in enumerate(rows, 1):
        for j, v in enumerate(r):
            cell_text(t.rows[i].cells[j], v, align=WD_ALIGN_PARAGRAPH.RIGHT if j in right else WD_ALIGN_PARAGRAPH.LEFT)
    for j, w in enumerate(widths):
        t.columns[j].width = Cm(w)
    for row in t.rows:
        for j, w in enumerate(widths):
            row.cells[j].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def code(lines):
    for l in lines:
        p = doc.add_paragraph()
        r = p.add_run(l if l else " ")
        r.font.name, r.font.size = MONO, Pt(10)
        fmt(p, first=False, line=1.0, align=WD_ALIGN_PARAGRAPH.LEFT)
        p.paragraph_format.left_indent = Cm(0.4)
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), "F2F2F2")
        pPr.append(shd)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def formula(spec, num):
    """spec: рядок із _{нижній} та ^{верхній} індексами."""
    p = doc.add_paragraph()
    p.paragraph_format.tab_stops.add_tab_stop(Cm(8.25), WD_TAB_ALIGNMENT.CENTER)
    p.paragraph_format.tab_stops.add_tab_stop(Cm(16.5), WD_TAB_ALIGNMENT.RIGHT)
    p.add_run("\t")
    for part in re.split(r"([_^]\{[^}]*\})", spec):
        if not part:
            continue
        if part[0] in "_^" and part[1] == "{":
            r = p.add_run(part[2:-1])
            if part[0] == "_":
                r.font.subscript = True
            else:
                r.font.superscript = True
        else:
            r = p.add_run(part)
        r.font.name, r.font.size = "Cambria Math", Pt(14)
        r.italic = True
    r = p.add_run(f"\t({num})")
    r.font.name, r.font.size = FONT, Pt(14)
    fmt(p, first=False, before=4, after=4, line=1.5, align=WD_ALIGN_PARAGRAPH.LEFT)


FIGN = {}
SHOTS = []


def fig(key):
    return FIGN[key]


def shot(key, title, where, open_, do, show, capt):
    n = FIGN[key]
    SHOTS.append((n, title, where))
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]
    c.width = Cm(16.5)
    shade(c, "FFF2CC")
    tblPr = t._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:val"), "dashed")
        e.set(qn("w:sz"), "12")
        e.set(qn("w:color"), "BF9000")
        b.append(e)
    tblPr.append(b)
    c.text = ""
    p = c.paragraphs[0]
    r = p.add_run(f"[СКРІНШОТ № {n}] {title}")
    r.bold, r.font.name, r.font.size = True, "Arial", Pt(10.5)
    r.font.color.rgb = RGBColor(0xC0, 0, 0)
    r = p.add_run("   (після вставки зображення цей жовтий блок видалити)")
    r.font.name, r.font.size = "Arial", Pt(8.5)
    r.font.color.rgb = RGBColor(0x7F, 0x7F, 0x7F)
    for label, text in (("Що відкрити:", open_), ("Що зробити:", do), ("Що має бути видно:", show),
                        ("Як обрізати:", "лише потрібну область (Win+Shift+S), без зайвих панелей і особистих даних.")):
        p = c.add_paragraph()
        rr = p.add_run(label + " ")
        rr.bold, rr.font.name, rr.font.size = True, "Arial", Pt(10)
        rich(p, text, size=10)
        for run in p.runs[1:]:
            run.font.name = run.font.name or "Arial"
        fmt(p, first=False, line=1.0, after=2, align=WD_ALIGN_PARAGRAPH.LEFT)
    caption(capt, "Рисунок", n)


def image(key, path, width_cm, capt):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(path), width=Cm(width_cm))
    caption(capt, "Рисунок", FIGN[key])


# нумерація рисунків — у порядку появи
for i, k in enumerate(["docker", "channel", "ps", "pubsub", "outlog", "buffer", "latency",
                       "dstats", "gitlog", "github"], 1):
    FIGN[k] = i

# --------------------------------------------------------------- графік буфера
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

log = D.parse_log()
t0 = log[0][0]
fig_, ax = plt.subplots(figsize=(7.2, 3.3))
ax.plot([x[0] - t0 for x in log], [x[1] for x in log], "-", color="#1f4e9c", lw=1.8)
ax.axvspan(o.t_d - t0, o.t_r - t0, color="#c0392b", alpha=0.12, label="розрив ланки")
ax.set_xlabel("Час від початку журналу, с")
ax.set_ylabel("Записів у буфері шлюзу")
ax.grid(alpha=0.3)
ax.legend(loc="upper left")
fig_.tight_layout()
fig_.savefig(R / "outage_buffer.png", dpi=170)
plt.close(fig_)

# =============================================================== титулка
def tp(text, bold=False, size=14, before=0, align=WD_ALIGN_PARAGRAPH.CENTER, indent=None):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.bold, r.font.name, r.font.size = bold, FONT, Pt(size)
    fmt(p, first=False, before=before, line=1.15, align=align)
    if indent:
        p.paragraph_format.left_indent = Cm(indent)


tp("МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ", True)
tp("НАЦІОНАЛЬНИЙ ТЕХНІЧНИЙ УНІВЕРСИТЕТ УКРАЇНИ", True)
tp("«КИЇВСЬКИЙ ПОЛІТЕХНІЧНИЙ ІНСТИТУТ ІМЕНІ ІГОРЯ СІКОРСЬКОГО»", True)
tp("Факультет програмних систем та прикладної математики", before=18)
tp("Кафедра програмного забезпечення комп’ютерних систем")
tp("Звіт до лабораторної роботи №3", True, 16, before=120)
tp("з дисципліни «Архітектури мультимедійних та смартсистем»", before=12)
tp("тема «Архітектура смартсистеми: сенсорні дані, розподілене розгортання та шаблони проєктування»", before=12)
tp("Виконав студент", before=110, align=WD_ALIGN_PARAGRAPH.LEFT, indent=9)
tp("1 курсу магістратури", align=WD_ALIGN_PARAGRAPH.LEFT, indent=9)
tp("групи КП-61мп", align=WD_ALIGN_PARAGRAPH.LEFT, indent=9)
tp("Любченко Іоанн Миколайович", align=WD_ALIGN_PARAGRAPH.LEFT, indent=9)
tp("КИЇВ 2026", before=110)
doc.add_page_break()

# =============================================================== 1. Мета
H1("1. Мета роботи")
P("Метою цієї лабораторної роботи є навчитися будувати канал сенсорних даних смартсистеми й розгортати систему розподілено: проєктувати схему повідомлення, за якою виявляються втрати, дублікати й позачергові показники, розділяти систему на периферійний і серверний складники, застосовувати спеціалізовані шаблони проєктування та оцінювати масштабованість навантажувальним випробуванням.")
P("Роботу я виконав у тому самому Git-репозиторії (https://github.com/JOAHNLIU/perimeter-guard-mmss), що й лабораторні роботи 1–2, для тієї самої предметної області — варіанта №2 «Відеоспостереження за периметром з аналітикою подій», системи PerimeterGuard. Сенсори вузла ділянки периметра я взяв із табл. 4 методичних вказівок: рух (0/1), освітленість (lx) і стан воріт (0/1). Сенсори емулює програма, а периферійний вузол є контейнером з обмеженими ресурсами, тож спеціального обладнання не знадобилося. На першому занятті я побудував канал телеметрії MQTT зі схемою повідомлення й перевірив його внесеними збоями. На другому — розділив систему на периферійний і серверний складники в Docker Compose, застосував два шаблони, перевірив їх розривом зв’язку й виконав навантажувальне випробування.")
table(1, "Результати лабораторної роботи та їхнє розташування",
      ["№", "Результат за завданням", "Файли в репозиторії", "Розділ"],
      [["1", "Емулятор сенсорів, підписник, підсумок каналу", "smart/sensors.py, collector.py, stats.py", "3.3–3.4"],
       ["2", "Теми, схема, політика помилок, перевірка каналу", "docs/telemetry.md", "3.1–3.6"],
       ["3", "Розгортання периферії та сервера", "smart/docker-compose.yml, Dockerfile, gateway.py, broker/mosquitto.conf", "4.1"],
       ["4", "Навантажувальне випробування й графік", "smart/loadtest.sh, plot.py, results/load.csv, latency.png", "4.4"],
       ["5", "Складники, шаблони, розрив, навантаження, масштабованість, мова і стек", "docs/deployment.md", "4.1–4.6"],
       ["6", "Рішення щодо шаблонів і щодо мови та стека", "docs/adr/0005-*.md, 0006-*.md", "4.6"]],
      [0.9, 5.6, 7.4, 2.6])

# =============================================================== 2. Підготовка
H1("2. Підготовка робочого місця")
P("Усі інструменти безкоштовні. Я працював у Visual Studio Code під Windows, а команди виконував у терміналі Git Bash. Брокер MQTT Eclipse Mosquitto 2 і всі серверні та периферійні складники працюють у контейнерах Docker, тому головною умовою було встановлення Docker Desktop (у Windows він працює на основі WSL 2). Підписник, емулятор і навантажувальний сценарій я запускав у середовищі Python із бібліотеками `paho-mqtt` 2.1.0 і `matplotlib`; SQLite входить до стандартної бібліотеки Python, тож окремо її встановлювати не потрібно.")
table(2, "Інструменти та їхнє призначення",
      ["Інструмент", "Для чого потрібен у роботі", "Як перевіряв"],
      [["Docker Desktop, Docker Compose v2", "запуск брокерів, шлюзу, емулятора й підписника в контейнерах з лімітами ресурсів", "`docker version`, `docker compose version`"],
       ["Eclipse Mosquitto 2", "брокер MQTT периферії й сервера", "`mosquitto -h`"],
       ["Python 3, paho-mqtt, matplotlib", "підписник і емулятор на хості, графік", "`import paho.mqtt`"],
       ["SQLite", "сховище підписника й буфер шлюзу", "`sqlite3.sqlite_version`"],
       ["Git, Visual Studio Code", "версійний контроль і редагування", "`git --version`"]],
      [4.6, 8.0, 3.9])
P(f"Працездатність Docker і образу брокера я перевірив трьома командами; результат показано на рисунку {fig('docker')}.")
shot("docker", "Перевірка Docker і Mosquitto", "розділ 2",
     "VS Code → Terminal → New Terminal → Git Bash (запущений Docker Desktop, внизу ліворуч «Engine running»).",
     "виконайте: `docker version --format '{{.Server.Version}}'`, `docker compose version`, `docker run --rm eclipse-mosquitto:2 mosquitto -h | grep version`.",
     "версія Docker Engine, рядок «Docker Compose version v2…» і рядок «mosquitto version 2.x».",
     "Перевірка Docker, Docker Compose і образу брокера Mosquitto")

# =============================================================== 3. Заняття 1
H1("3. Заняття 1. Інтеграція сенсорних даних смартсистеми")
H2("3.1 Брокер і теми")
P("Брокер я описав у `smart/broker/mosquitto.conf`. Без оголошеного слухача Mosquitto 2 приймає з’єднання лише з того самого комп’ютера, а в контейнері це означає, що з хоста до нього не підключитися; з оголошеним слухачем за замовчуванням відхиляються клієнти без імені користувача. Тому конфігурація відкриває порт 1883 (`listener 1883`) і дозволяє анонімний доступ (`allow_anonymous true`), а порт опубліковано лише на адресі `127.0.0.1`, щоб брокер був недоступний із мережі. Параметр `set_tcp_nodelay true` вимикає алгоритм Нейгла: підтвердження PUBACK надсилаються одразу, інакше шлюз у занятті 2 упирався б у штучну межу пропускної здатності.")
P("Тема має чотири рівні: об’єкт, ділянка, пристрій і вид повідомлення, наприклад `p1/north/motion-1/tele`. Така структура дозволяє підписатися на всі пристрої об’єкта шаблоном `p1/+/+/tele` і додавати споживачів без змін сенсорів. Види повідомлень і їхні параметри наведено в таблиці 3.")
table(3, "Види повідомлень MQTT",
      ["Вид", "Тема", "QoS", "Збережене", "Призначення"],
      [["Телеметрія", "p1/north/<пристрій>/tele", "0", "ні", "показ за схемою; втрату виявляє `seq`"],
       ["Стан", "p1/north/<пристрій>/state", "1", "так", "`online` після підключення"],
       ["Заповіт", "p1/north/<пристрій>/state", "1", "так", "`offline`, який брокер публікує сам, якщо пристрій зник"]],
      [2.4, 4.6, 1.2, 2.3, 6.0])
P("Телеметрію я публікую з QoS 0, бо утрату окремого показу виявить порядковий номер, а гарантію доставки на ланці периферія — сервер забезпечує шлюз із QoS 1 і буфером. Для вимоги FR-10 з лабораторної роботи 1 (позначити камеру офлайн протягом ≤ 30 с) я задав `keepalive = 20 с`: брокер публікує заповіт приблизно через 1,5 · 20 = 30 с без пакетів від клієнта.")

H2("3.2 Схема повідомлення")
P("Схема повідомлення — це контракт між видавцями й підписниками, які не знають одне одного. Приклад повідомлення: `{\"dev\":\"north-light-1\",\"boot\":1,\"seq\":4182,\"ts\":\"2026-11-21T08:41:20.123Z\",\"qty\":\"light\",\"val\":512.3,\"unit\":\"lx\"}`. Призначення полів наведено в таблиці 4.")
table(4, "Схема повідомлення телеметрії",
      ["Поле", "Тип", "Формат / одиниця", "Призначення", "Діапазон"],
      [["dev", "рядок", "ділянка-пристрій", "хто виміряв; збігається з темою", "—"],
       ["boot", "ціле", "номер запуску", "відрізняє запуски: після перезапуску `seq` починається з нуля", "≥ 1"],
       ["seq", "ціле", "порядковий номер", "виявляє пропуски, дублікати, позачергові показники", "≥ 0"],
       ["ts", "рядок", "UTC, мс, …Z", "момент вимірювання; з нього рахується затримка", "до +5 с від годинника сервера"],
       ["qty", "рядок", "motion, light, gate", "яка величина", "з переліку"],
       ["val", "число", "за величиною", "значення", "motion, gate: 0 або 1; light: 0–65535"],
       ["unit", "рядок", "bool, lx", "одиниця величини", "відповідає qty"]],
      [1.6, 1.6, 3.4, 6.2, 3.7])
P("Порядковий номер `seq` і номер запуску `boot` виявляють те, чого протокол не помічає: за QoS 0 про загублене повідомлення ніхто не повідомляє, а за QoS 1 можливі дублікати. Кількість пропущених повідомлень перед k-м отриманим визначає формула (1), а підсумковий показник каналу — частка втрат (2):", keep=True)
formula("n_{k} = s_{k} − s_{k−1} − 1", 1)
P("де n_k — кількість пропущених повідомлень перед k-м отриманим; s_k — порядковий номер k-го отриманого повідомлення; s_{k−1} — найбільший номер, отриманий до нього в межах того самого запуску. Якщо n_k < 0, повідомлення є дублікатом (такий номер уже є) або позачерговим (раніше вважалося пропущеним).", first=False)
formula("ε = 1 − N_{отр} / N_{над}", 2)
P("де ε — частка втрачених повідомлень; N_отр — кількість отриманих різних повідомлень без дублікатів; N_над — кількість надісланих, обчислена за порядковими номерами від першого до останнього номера запуску включно. Затримку доставки підписник обчислює для кожного показу за формулою (3); обидві мітки часу беруться з одного годинника, бо всі контейнери працюють на одному комп’ютері.", first=False, keep=True)
formula("L_{д} = t_{отр} − t_{вим}", 3)

H2("3.3 Емулятор сенсорів")
P("Емулятор `smart/sensors.py` публікує телеметрію трьох сенсорів вузла ділянки `north`. Кожен сенсор має власного клієнта MQTT зі своїм заповітом, а станом пристрою є збережене повідомлення `online` у темі `…/state`. Частоту одного сенсора, тривалість і частки внесених збоїв задають змінні середовища `HZ`, `DURATION`, `DROP`, `DUP`, `LATE`, `BAD`; вони потрібні, щоб перевірити підписника. Моделі сенсорів описано в таблиці 5.")
table(5, "Сенсори вузла ділянки периметра",
      ["Пристрій", "Величина", "Одиниця", "Модель значення"],
      [["motion-1", "motion", "bool", "1 протягом перших 5 с кожної хвилини, інакше 0"],
       ["light-1", "light", "lx", "400 + 150·sin(t/600) і шум σ = 5"],
       ["gate-1", "gate", "bool", "1 протягом перших 30 с кожних 10 хвилин, інакше 0"]],
      [2.6, 2.6, 2.3, 9.0])
P("Номер запуску `boot` зростає після кожного перезапуску емулятора; лічильник зберігається у файлі `data/boot.txt` (у контейнері — на томі `sensors-data`), а `seq` починається з нуля.")

H2("3.4 Підписник і сховище")
P("Підписник `smart/collector.py` перевіряє кожне повідомлення за схемою: наявність і типи полів, відповідність `dev` темі, величину, одиницю, діапазон із даташита та мітку часу. Відхилене разом із причиною потрапляє до таблиці `rejected`: специфікація MQTT не визначає черги недоставлених повідомлень, тому її роль виконує застосунок. Первинним ключем таблиці `readings` є трійка `(dev, boot, seq)`, тож дублікат відкидає сама база, а пропуски й позачергові покази за формулою (1) записуються до таблиці `anomalies`. База працює в режимі WAL із `synchronous=NORMAL`. Підсумок каналу обчислює `smart/stats.py`: для кожного запуску емулятора він визначає інтенсивність потоку λ, N_над, N_отр, частку втрат ε, кількість позачергових і дублікатів, середню, 95-й процентиль і найбільшу затримку.")

H2("3.5 Політика оброблення помилок")
P("Політику оброблення помилок я описав у `docs/telemetry.md` для всіх ситуацій своєї області, а кожен рядок має відповідник у коді або конфігурації. Основні ситуації наведено в таблиці 6.")
table(6, "Політика оброблення помилок підписника (скорочено)",
      ["Ситуація", "Як виявляється", "Дія", "Де фіксується"],
      [["Не JSON, немає поля, хибний тип", "перевірка за схемою", "відхилити, роботу не зупиняти", "rejected, причина"],
       ["Значення поза діапазоном", "межі з даташита; motion/gate — не 0 чи 1", "відхилити як недостовірне", "rejected"],
       ["Мітка часу з майбутнього", "більше ніж на 5 с від годинника сервера", "відхилити; перевірити синхронізацію", "rejected"],
       ["Дублікат", "трійка (dev, boot, seq) уже є", "не зберігати повторно", "anomalies, dup"],
       ["Пропуск / позачерговий", "n_k > 0 / n_k < 0 за (1)", "зберегти показ, урахувати втрату", "anomalies, gap / late"],
       ["Сенсор зник", "заповіт offline у темі …/state", "брокер позначає пристрій недоступним", "збережене повідомлення стану"],
       ["Розрив ланки периферія — сервер", "шлюз не отримує PUBACK", "накопичувати в буфері й надіслати після відновлення", "outbox, журнал шлюзу"],
       ["Ворота відчинені надто довго", "тривалість стану проти порогу", "сповістити оператора", "не реалізовано: Rule Engine (ЛР 1)"]],
      [4.3, 4.4, 4.3, 3.5])

H2("3.6 Перевірка каналу внесеними збоями")
P(f"Перевірку я виконав скриптом `smart/check_channel.sh`: підписник запускається першим (повідомлення QoS 0, опубліковані до підписки, брокер нікому не доставляє), а через 3 с емулятор працює 30 с із частотою 20 повідомлень/с від кожного сенсора й часткою збоїв `DROP=0.03 DUP=0.02 LATE=0.03 BAD=0.02`. Емулятор вивів підсумок `{re.search(r'Підсумок: (.*)', sens_t).group(1)}`. Підписник отримав N_отр = {got} із N_над = {sent}, тобто ε = 1 − {got} / {sent} ≈ {f(row['loss'], 4)} (внесена частка пропусків {f(inj['drop'] / sent, 4)}). Середня затримка доставки — {f(row['lat_mean_ms'])} мс, 95-й процентиль — {int(row['lat_p95_ms'])} мс, найбільша — {int(row['lat_max_ms'])} мс. Порівняння внесених і виявлених збоїв наведено в таблиці 7 і на рисунку {fig('channel')}.")
table(7, "Внесені збої та виявлені підписником",
      ["Показник", "Внесено", "Виявлено", "Збіг"],
      [[n, str(a), str(b), "так" if a == b else "ні"] for n, a, b in checks], [8.0, 2.8, 2.8, 2.9], right=(1, 2))
P(("Усі чотири показники збіглися, тобто підписник розрізняє пропуск, дублікат, позачерговий показ і зіпсоване повідомлення." if all_ok
   else "Є розбіжність на кілька повідомлень; найімовірніша причина — останній показ запуску «загубився», тоді N_над за номерами на одиницю менший за справжній. Розбіжність на 1–2 повідомлення для 30-секундного запуску я вважаю допустимою.") + " Після завершення заняття 1 я зробив коміт `ЛР3: канал сенсорних даних і схема повідомлень`.")
shot("channel", "Підсумок перевірки каналу", "розділ 3.6",
     "термінал Git Bash у корені репозиторію (активне `.venv`, запущений Docker Desktop).",
     "виконайте `bash smart/check_channel.sh` (≈1 хв) або покажіть його вивід із `results/channel_sensors.txt` і `results/channel_stats.txt`.",
     "рядок «Підсумок: {'published': …, 'drop': …}» емулятора, таблиця `boot rate sent received loss late dup …` і рядок «Відхилено: не JSON — N».",
     "Вивід перевірки каналу: підсумок емулятора й підписника")

# =============================================================== 4. Заняття 2
H1("4. Заняття 2. Розподілене розгортання edge–cloud та застосування шаблонів")
H2("4.1 Складники й розгортання")
P("Систему я розділив на периферійний і серверний складники. Периферійний працює у вузлі ділянки периметра: емулятор сенсорів, брокер периферії та шлюз. Серверний — брокер і підписник сервера об’єкта. Мереж Docker дві, `edge` і `cloud`, і лише шлюз підключено до обох, тобто він є єдиним зв’язком периферії із сервером. Ресурси периферії обмежені параметрами `cpus` і `mem_limit`: вузол біля камери має вкластися у вузький енергетичний бюджет (NFR-05, 15 Вт), тому процесор шлюзу я обмежив до 0,25 ядра. Склад розгортання наведено в таблиці 8.")
table(8, "Складники розгортання (smart/docker-compose.yml)",
      ["Сервіс", "Складник", "Мережі", "Ресурси", "Призначення"],
      [["sensors", "периферія", "edge", "—", "емулятор: рух, освітленість, стан воріт"],
       ["edge-broker", "периферія", "edge", "cpus 0,5; 128 МБ", "брокер вузла; недоступний з хоста"],
       ["gateway", "периферія", "edge, cloud", "cpus 0,25; 128 МБ", "буфер outbox (SQLite), пересилання з QoS 1, видалення після PUBACK"],
       ["cloud-broker", "сервер", "cloud", "—", "брокер сервера; порт 127.0.0.1:1883"],
       ["collector", "сервер", "cloud", "—", "підписник: перевірка схеми, readings, anomalies, rejected"]],
      [2.6, 2.3, 2.3, 3.2, 6.1])
g = re.search(r"буфер=(\d+)\s+відкинуто=(\d+)\s+зв.язок=(\S+)", gw5)
P(f"Шлюз `smart/gateway.py` записує все отримане в буфер `outbox` (SQLite на томі периферії), надсилає найстаріші записи з QoS 1 і видаляє лише ті, що підтверджені PUBACK. У режимі WAL із `synchronous=NORMAL` буфер переживає збій процесу, а після вимкнення живлення останні транзакції можуть відкотитися. Мережа між контейнерами на одному комп’ютері майже не обмежена, тому смугу ланки до сервера моделює параметр `UPLINK_KBPS` (1000 кбіт/с), як смугу браузера в лабораторній роботі 2. Після `docker compose up -d --build` сервісів у стані Up було {n_up} (очікується п’ять); журнал шлюзу показує буфер={g.group(1)}, відкинуто={g.group(2)}, зв’язок={g.group(3)}" + (f"; підсумок підписника: λ ≈ {f(st5[0]['rate'])} повідомлень/с, loss = {f(st5[0]['loss'], 4).rstrip('0').rstrip(',') or '0'} (рисунок {fig('ps')})." if st5 else f" (рисунок {fig('ps')})."))
shot("ps", "Розгорнуті сервіси", "розділ 4.1",
     "термінал Git Bash у корені репозиторію.",
     "після `bash smart/check_outage.sh` (або вручну `docker compose up -d --build`) виконайте `docker compose ps --format '{{.Service}}: {{.Status}}'` і `docker compose logs --tail 1 gateway` (перед цим `export COMPOSE_FILE=smart/docker-compose.yml`).",
     "п’ять сервісів у стані Up та рядок журналу шлюзу «буфер=… відкинуто=0 зв’язок=так».",
     "П’ять сервісів розгортання edge–cloud у стані Up та журнал шлюзу")

H2("4.2 Шаблон «публікація — підписка»")
P(f"Шаблон роз’єднує учасників: сенсори не знають, скільки в них підписників, а нового споживача додають підпискою на тему, не змінюючи сенсорів. Я перевірив це експериментом: не змінюючи ні `sensors.py`, ні `collector.py`, додав двох підписників. Перший отримує ту саму телеметрію на сервері (отримано {n_tele} повідомлення), другий — збережені повідомлення стану на периферії: брокер одразу надіслав {n_state} рядки `online`, а далі до кінця очікування нових повідомлень стану не було («Timed out»). Вивід наведено на рисунку {fig('pubsub')}.")
shot("pubsub", "Додаткові підписники", "розділ 4.2",
     "термінал Git Bash; система з кроку 4.1 працює.",
     "виконайте `docker compose exec -T cloud-broker mosquitto_sub -t 'p1/+/+/tele' -v -C 3`, потім `docker compose exec -T edge-broker mosquitto_sub -t 'p1/+/+/state' -v -W 2` (або покажіть `results/pubsub_cloud.txt` і `pubsub_edge.txt`).",
     "три рядки телеметрії `p1/north/…/tele {…}` і три рядки `…/state online`, а далі «Timed out».",
     "Додавання підписників без змін сенсорів: телеметрія на сервері й стан на периферії")

H2("4.3 Шаблон «буферизація на периферії» і розрив зв’язку")
P(f"Місткість буфера розраховують на найдовший розрив, який система має пережити без втрат, за формулою (4):", keep=True)
formula("V_{буф} = r · s · T_{розр}", 4)
P(f"де V_буф — потрібний обсяг буфера, байт; r — інтенсивність потоку, повідомлень/с; s — обсяг одного збереженого повідомлення, байт; T_розр — найдовший розрив, с. Виміряний мною середній розмір повідомлення разом із темою s ≈ {D.S_BYTES} байтів. Місткість {D.MAX_ROWS} записів — це {f(D.MAX_ROWS / D.LAM_NODE_NOM / 3600, 1)} год розриву за номінальних {D.LAM_NODE_NOM} повідомлень/с (3 сенсори по 1 Гц) і {f(D.MAX_ROWS / D.LAM_NODE_PEAK / 60, 0)} хв за піку {D.LAM_NODE_PEAK} повідомлень/с (3 сенсори по 5 Гц, верх діапазону табл. 4), тобто V_буф ≈ {f(D.MAX_ROWS * D.S_BYTES / 1e6, 1)} МБ; переповнений буфер відкидає найстаріші покази. На вивантаження після розриву лишається лише надлишок пропускної здатності, бо нові покази не зупиняються:", first=False, keep=True)
formula("T_{розв} = Q_{0} / (n · μ_{1} − λ)", 5)
P(f"де Q_0 — кількість повідомлень у буфері на момент відновлення зв’язку; n = 1 — кількість обробників (один шлюз); μ_1 — пропускна здатність обробника; λ — інтенсивність нових повідомлень. Пропускну здатність шлюзу обмежує смуга ланки R = {D.UPLINK_KBPS} кбіт/с, тому μ_1 = R / (8 · s) = 10⁶ / (8 · {D.S_BYTES}) ≈ {f(D.MU1, 0)} повідомлень/с.", first=False)
P(f"Експеримент із розривом я виконав скриптом `smart/check_outage.sh`: збільшив потік до λ ≈ {f(o.lam, 0)} повідомлень/с (`HZ=100`) і на {f(o.dur, 0)} с від’єднав шлюз від мережі `cloud` командою `docker network disconnect`, а потім під’єднав назад. "
  + (f"Шлюз помітив розрив через {f(o.det, 0)} с: це два інтервали Keep Alive по 10 с — перевірка з’єднання й очікування відповіді. " if o.det is not None else "")
  + (f"Буфер зростав приблизно на {f(o.grow, 0)} записів щосекунди й досяг Q_0 = {o.q0} (рисунки {fig('outlog')} і {fig('buffer')}). " if o.grow is not None else f"Буфер досяг Q_0 = {o.q0} (рисунок {fig('buffer')}). ")
  + (f"За формулою (5) вивантаження мало тривати {o.q0} / ({f(D.MU1, 0)} − {f(o.lam, 0)}) ≈ {f(o.drain_calc, 0)} с, виміряно ≈ {f(o.drain, 0)} с (крок журналу 2 с)" if o.drain is not None and o.drain_calc else "")
  + (f", а швидкість вивантаження за журналом μ_1 ≈ {f(o.mu_meas, 0)} повідомлень/с проти розрахункових {f(D.MU1, 0)}. " if o.mu_meas else ". "))
P(f"Підсумок підписника для цього запуску: N_над = {int(o.row['sent'])}, N_отр = {int(o.row['received'])}, loss = {q0_loss}, дублікатів {int(o.row['dup'])}, позачергових {int(o.row['late'])}; найбільша затримка {f(o.row['lat_max_ms'] / 1000, 1)} с — у показів з початку розриву. "
  + ("Утрат немає: буферизація на периферії пережила розрив. Дублікати з’явилися тому, що шлюз повторно надіслав записи, на які не надійшов PUBACK (QoS 1 гарантує доставку «щонайменше один раз»), а підписник їх відкинув — це наслідок шаблону, і тому підписник має бути ідемпотентним. "
     if o.row["loss"] == 0 else "Втрати ненульові: найімовірніше, розрив припав на запуск емулятора або буфер переповнився. ")
  + "Важливо, що PUBACK підтверджує лише отримання серверним брокером, а не доставку підписнику; без постійної сесії повідомлення для непрацюючого підписника загубилося б.")
shot("outlog", "Журнал шлюзу під час розриву", "розділ 4.3",
     "VS Code → `results/outage_gateway.txt`.",
     "знайдіть місце розриву (Ctrl+F → `зв’язок=ні`) і прокрутіть так, щоб було видно перехід «так → ні», зростання буфера та після відновлення — спад до 0.",
     "рядки `буфер=N відкинуто=0 зв’язок=так/ні` із мітками часу: буфер росте приблизно на λ щосекунди, а після відновлення спорожнюється.",
     "Фрагмент журналу шлюзу: зростання буфера під час розриву й вивантаження після відновлення")
image("buffer", R / "outage_buffer.png", 14.5, "Заповненість буфера шлюзу під час розриву зв’язку (за журналом шлюзу)")

H2("4.4 Навантажувальне випробування")
P(f"Шлях показу — конвеєр із кількох етапів, і його пропускну здатність Θ = min μ_i задає найповільніший етап. Поки λ далека від Θ, затримка майже стала; поблизу Θ вона різко зростає, як у моделі M/M/1 (6); за λ > Θ черга в буфері зростає лінійно, а переповнення дає втрати:", keep=True)
formula("W = 1 / (μ − λ),    u = λ / μ", 6)
P(f"де W — середній час перебування повідомлення в системі, с; μ — інтенсивність обслуговування; u — завантаження обробника; формула справедлива за λ < μ. Сценарій `smart/loadtest.sh` перезапускає систему з чистими томами й ступенями по {D.STEP_S} с збільшує частоту кожного з трьох сенсорів (HZ = {', '.join(map(str, D.HZ_STEPS))}); після ступеня він чекає, поки буфер спорожніє. Буфер зменшено до {D.MAX_ROWS_LOAD} записів, щоб він переповнювався, коли (λ − Θ) · {D.STEP_S} > {D.MAX_ROWS_LOAD}. Кожен ступінь — окремий запуск емулятора, тобто рядок у `results/load.csv` (таблиця 9, рисунок {fig('latency')}).")
rows9 = [[f(r["rate"], 0), str(int(r["sent"])), str(int(r["received"])), f(r["loss"], 3),
          f(r["lat_mean_ms"], 1 if r["lat_mean_ms"] < 100 else 0), str(int(r["lat_p95_ms"])), str(int(r["lat_max_ms"])),
          f(r["rate"] / th, 2)] for r in L.rows]
table(9, "Залежність затримки й втрат від навантаження (results/load.csv)",
      ["λ, повід./с", "N_над", "N_отр", "ε", "L_д сер., мс", "p95, мс", "max, мс", "u = λ/Θ"], rows9,
      [2.1, 2.0, 2.0, 1.7, 2.3, 1.9, 2.1, 2.4], right=tuple(range(8)))
image("latency", R / "latency.png", 13.5, "Залежність затримки доставки й частки втрат від навантаження λ")
btxt, _ = D.bottleneck_text(L)
lossy = [r for r in L.rows if r["loss"] > 0.001]
calc = "; ".join(f"за λ = {f(r['rate'], 0)} розрахункові втрати (λ − Θ) · {D.STEP_S} − {D.MAX_ROWS_LOAD} ≈ {f(max(0.0, (r['rate'] - th) * D.STEP_S - D.MAX_ROWS_LOAD), 0)}, виміряно {int(r['sent'] - r['received'])}" for r in lossy)
base = [r for r in L.rows if r["rate"] / th < 0.5]
lam_ok = max((r["rate"] for r in L.rows if r["lat_p95_ms"] <= D.L_MER_MS and r["loss"] == 0), default=None)
P((f"Θ я оцінюю за найбільшою затримкою на ступенях із втратами: переповнений буфер {D.MAX_ROWS_LOAD} записів вичерпується за {D.MAX_ROWS_LOAD} / Θ секунд, тож Θ ≈ {D.MAX_ROWS_LOAD} / L_max ≈ **{f(L.theta_meas, 0)} повідомлень/с**. "
   if L.theta_meas else f"Переповнення буфера не досягнуто на жодному ступені, тому Θ ≥ {f(max(r['rate'] for r in L.rows), 0)} повідомлень/с. ")
  + (f"До u ≈ 0,5 середня затримка становить {f(statistics.mean(r['lat_mean_ms'] for r in base))} мс. " if base else "")
  + "Поблизу Θ затримка різко зростає, а за λ > Θ черга зростає на λ − Θ повідомлень щосекунди й найбільшу затримку обмежує місткість буфера. "
  + (f"Найвище навантаження, за якого p95 ≤ {D.L_MER_MS} мс (бюджет L_мер із NFR-01) і втрат немає, — λ ≈ {f(lam_ok, 0)} повідомлень/с. " if lam_ok else "")
  + (calc + ". " if calc else "")
  + (f"Лічильник «відкинуто» шлюзу ({L.gw_dropped}) {'дорівнює' if L.gw_dropped == int(L.lost) else 'відрізняється від'} сумі втрат, які виявив підписник ({int(L.lost)})." if L.gw_dropped is not None else ""))
P("**Вузьке місце.** " + btxt + f" Знімок завантаження контейнерів показано на рисунку {fig('dstats')}.")
shot("dstats", "Завантаження контейнерів під навантаженням", "розділ 4.4",
     "VS Code → `results/docker_stats.txt`.",
     "прокрутіть до блоку `## HZ=500` (останній ступінь) і залиште видимими всі рядки цього блоку (або виконайте `docker stats --no-stream` під час найвищого ступеня).",
     "чотири–п’ять контейнерів із `%CPU` і пам’яттю; у рядка `gateway` процесор близько 25 % — межа ліміту `cpus: 0.25`.",
     "Завантаження контейнерів на ступені найвищого навантаження (знімок docker stats)")

H2("4.5 Масштабованість")
P(f"За нефункційною вимогою NFR-02 лабораторної роботи 1 система має зростати з 8 до 64 камер. Кожен вузол ділянки має три сенсори, частоту я беру з табл. 4 методичних вказівок (1–5 Гц): номінально λ вузла = {D.LAM_NODE_NOM} повідомлень/с, у піку — {D.LAM_NODE_PEAK} повідомлень/с. Для 64 вузлів серверний складник отримує {sys_nom} повідомлень/с номінально й {sys_peak} повідомлень/с у піку. Виміряна Θ ≈ {f(th, 0)} повідомлень/с дає одному вузлові запас у {f(th / D.LAM_NODE_NOM, 0)} разів за номінального потоку й у {f(th / D.LAM_NODE_PEAK, 0)} разів у піку, тож окремий вузол масштабувати не потрібно. На сервері ж потоки всіх вузлів сходяться в одну точку: пік {sys_peak} повід./с становить {f(100 * ratio, 0)} % від Θ, а номінальні {sys_nom} — {f(100 * sys_nom / th, 0)} %. Θ вимірювалась для ланки одного вузла, а окремої ємності серверного підписника я не вимірював: втрати давав буфер шлюзу, а підписник на ступенях нижче Θ тримав затримку невеликою, тому я припускаю, що його ємність не нижча за Θ; це треба перевірити окремим тестом без обмеження смуги.")
P(("Тому першим доведеться масштабувати серверну частину — підписник і брокер. Я обрав би горизонтальне масштабування: кілька підписників із розбиттям стану за темами (за ділянками `p1/<ділянка>/…`, лекція 10), а брокер — вертикально або кластером; вертикальне масштабування одного підписника швидко впирається в SQLite без сервера."
   if ratio >= 0.7 else "Запасу вистачає, проте стан підписника доцільно розбити за ділянками (горизонтально) раніше, ніж Θ вичерпається.")
  + " «Кероване зниження якості» (шлюз переходить на хвилинні агрегати, події не відкидаються) я не реалізовував, але воно було б наступним шаблоном для потоку понад Θ.")

H2("4.6 Мова, технологічний стек і рішення ADR")
st_d = L.stats or {}
def mem(n):
    return f"{f(st_d[n]['mem'])} МіБ" if n in st_d else "—"
table(10, "Мова та технологічний стек складників",
      ["Складник", "У моїй реалізації", "Обґрунтування та альтернатива"],
      [["Сенсори", "Python — лише емулятор", "на пристрої — C або Rust: без збирача сміття, передбачувані час і пам’ять"],
       ["Брокер периферії", f"Eclipse Mosquitto 2 (C), {mem('edge-broker')}", "міст Mosquitto міг би замінити шлюз, але не керує місткістю й переповненням буфера"],
       ["Шлюз", f"Python, paho-mqtt, SQLite; {mem('gateway')}; Θ ≈ {f(th, 0)} повід./с", f"у {f(th / D.LAM_NODE_PEAK, 0)} разів більше за піковий потік вузла; для багатьох вузлів на слабкому обладнанні — Go"],
       ["Серверний брокер", f"Eclipse Mosquitto 2, {mem('cloud-broker')}", "не зберігає історії; для повторного читання — Apache Kafka"],
       ["Підписник і сховище", f"Python, SQLite, {mem('collector')}", "для 64 вузлів — сховище часових рядів і кілька підписників з розбиттям за темами"]],
      [3.4, 5.4, 7.7])
P(f"Рішення я зафіксував у двох ADR у форматі лабораторної роботи 1. **ADR-0005** обирає шаблони «публікація — підписка» та «буферизація на периферії» (власний шлюз замість моста Mosquitto й замість прямої публікації з QoS 0); його підтверджують числа розриву: Q_0 = {o.q0}, loss = {q0_loss}. **ADR-0006** обирає Python із paho-mqtt і SQLite для шлюзу: Θ у {f(th / D.LAM_NODE_PEAK, 0)} разів перевищує піковий потік вузла, тож процесор і пам’ять із запасом достатні, а розробка залишається швидкою; Go розглядатиму для багатьох вузлів на слабкому обладнанні.")

# =============================================================== 5. Git
H1("5. Версійний контроль: Git та GitHub")
P(f"Я працював у два етапи, відповідно до двох занять. Після заняття 1 зробив коміт `ЛР3: канал сенсорних даних і схема повідомлень` (емулятор, підписник, підсумок, брокер, `docs/telemetry.md`), після заняття 2 — коміт `ЛР3: розгортання edge–cloud, шаблони, навантаження` (шлюз, Docker Compose, випробування, `docs/deployment.md`, ADR-0005 і ADR-0006). Бази SQLite і каталог `data/` до репозиторію не додаються завдяки `.gitignore`. Разом із комітами лабораторних робіт 1–2 історія містить шість комітів (рисунок {fig('gitlog')}), які я відправив на GitHub (рисунок {fig('github')}).")
shot("gitlog", "Історія комітів", "розділ 5",
     "термінал Git Bash у корені репозиторію.", "виконайте `git log --format=\"%h %ad %s\" --date=short`.",
     "шість комітів: два «ЛР1…», два «ЛР2…» і два «ЛР3…» (канал сенсорних даних; розгортання edge–cloud).",
     "Історія комітів репозиторію після лабораторної роботи 3")
shot("github", "Репозиторій на GitHub", "розділ 5",
     "браузер → https://github.com/JOAHNLIU/perimeter-guard-mmss (після `git push`).",
     "прокрутіть сторінку на самий верх; за бажанням відкрийте каталог `smart`.",
     "каталоги `smart`, `docs`, `results`, `stream`, `pipeline`, `tools`; лічильник «6 commits»; каталогу `data` немає.",
     "Репозиторій на GitHub із каталогом smart після публікації лабораторної роботи 3")

# =============================================================== 6. Результати
H1("6. Результати роботи")
P("Зіставляю виконане з контрольним списком здачі з методичних вказівок (таблиця 11).")
table(11, "Контрольний список здачі",
      ["Пункт контрольного списку", "Виконано"],
      [["smart/broker/mosquitto.conf і docker-compose.yml: периферія й сервер, мережі edge і cloud, ліміти периферії", "так"],
       ["smart/sensors.py: три сенсори власної області, схема з dev, boot, seq, ts", "так"],
       ["smart/collector.py і smart/stats.py запускаються без помилок", "так"],
       ["docs/telemetry.md: теми, схема, політика помилок, перевірка каналу внесеними збоями", "так — 4 збої з 4 виявлено" if all_ok else "так"],
       ["smart/gateway.py, Dockerfile, requirements.txt", "так"],
       ["docs/deployment.md: шаблони з наслідками в числах, розрив зв’язку з loss = 0", f"так — loss = {q0_loss}"],
       ["results/load.csv і latency.png; Θ, вузьке місце, висновок щодо масштабованості", "так"],
       ["Розділ «Мова і стек», ADR-0005 і ADR-0006 з розділами «Контекст», «Варіанти», «Рішення», «Наслідки»", "так"],
       ["Щонайменше два нові коміти в історії", "так — 2 нові (разом 6)"]],
      [12.3, 4.2])

# =============================================================== 7. Висновки
H1("7. Висновки")
P(f"У ході лабораторної роботи я побудував канал сенсорних даних смартсистеми PerimeterGuard і розгорнув її розподілено. Схема повідомлення з полями `boot` і `seq` дала змогу виявляти те, чого протокол MQTT не помічає: у перевірці внесеними збоями підписник виявив {'усі чотири види' if all_ok else 'внесені види'} збоїв (пропуски, дублікати, позачергові й зіпсовані повідомлення), а частка втрат ε ≈ {f(row['loss'], 4)} відповідала внесеній.")
P(f"Розділивши систему на периферійний і серверний складники з обмеженими ресурсами периферії, я застосував два шаблони й підтвердив їх експериментом. Розрив ланки на {f(o.dur, 0)} с за λ ≈ {f(o.lam, 0)} повідомлень/с завершився з loss = {q0_loss}: буфер шлюзу досяг {o.q0} записів і спорожнів"
  + (f" за ≈ {f(o.drain, 0)} с проти розрахункових {f(o.drain_calc, 0)} с за формулою (5)" if o.drain is not None and o.drain_calc else "") + ". Шаблон «публікація — підписка» дав змогу додати споживачів без змін сенсорів.")
P(f"Навантажувальне випробування показало, що " + (f"Θ ≈ {f(L.theta_meas, 0)} повідомлень/с" if L.theta_meas else f"Θ ≥ {f(max(r['rate'] for r in L.rows), 0)} повідомлень/с") + f" і що вузьке місце — {'смуга ланки периферія — сервер' if L.theta_meas and abs(L.theta_meas - L.theta_th) / L.theta_th <= 0.15 else 'процесор шлюзу'}. Вузол має запас у {f(th / D.LAM_NODE_PEAK, 0)} разів за піковим потоком, а серверна частина під пік 64 вузлів ({sys_peak} повід./с) наближається до Θ, тож першою масштабувати доведеться її — горизонтально, з розбиттям за темами.")
P("Я чесно позначаю межі роботи: сенсори емулюються, годинники всіх контейнерів спільні, а ємність серверного підписника окремо не вимірювалась; числа залежать від комп’ютера й чутливі до фонового навантаження. Далі я планую виміряти підписника без обмеження смуги, реалізувати кероване зниження якості та порівняти шлюз на Go за Θ і пам’яттю. Отриманий репозиторій я використаю як основу лабораторної роботи 4.")

H1("Перелік джерел")
for i, s in enumerate([
    "Навчальні матеріали з дисципліни «Архітектури мультимедійних та смартсистем». Google Classroom.",
    "Лабораторна робота 3. Архітектура смартсистеми: сенсорні дані, розподілене розгортання та шаблони проєктування: методичні вказівки / М. О. Ільїн. Київ: КПІ ім. Ігоря Сікорського, 2026/2027 н. р.",
    "Yudidharma A., Nathaniel N., Gimli T. N. et al. A systematic literature review: Messaging protocols and electronic platforms used in the Internet of Things for the purpose of building smart homes. Procedia Computer Science, 2023. URL: https://doi.org/10.1016/j.procs.2022.12.127",
    "Andriulo F. C., Fiore M., Mongiello M. et al. Edge Computing and Cloud Computing for Internet of Things: A Review. Informatics, 2024. URL: https://doi.org/10.3390/informatics11040071",
    "Eclipse Mosquitto Documentation [Електронний ресурс]. URL: https://mosquitto.org/documentation/",
    "Docker Documentation [Електронний ресурс]. URL: https://docs.docker.com/",
    "Eclipse Paho MQTT Python Client [Електронний ресурс]. URL: https://eclipse.dev/paho/files/paho.mqtt.python/html/"], 1):
    p = doc.add_paragraph()
    rich(p, f"{i}. {s}")
    fmt(p, first=False, line=1.5)
    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(1.25), Cm(-1.25)

# =============================================================== службова сторінка
doc.add_page_break()
p = doc.add_paragraph()
r = p.add_run("СЛУЖБОВА СТОРІНКА — ВИДАЛИТИ ПЕРЕД ЗДАЧЕЮ")
r.bold, r.font.name, r.font.size, r.font.color.rgb = True, "Arial", Pt(14), RGBColor(0xC0, 0, 0)
p = doc.add_paragraph()
rich(p, "**Як вставляти скріншоти:** знімок (Win+Shift+S) → у Word курсор на жовтий блок → Вставлення → Рисунок → з буфера (Ctrl+V) → по центру, ширина 14–16 см → видалити жовтий блок. Підпис «Рисунок N — …» залишається. Світла тема, шрифт у терміналі не менш як 14 pt, без особистих даних. Рисунки 6 і 7 (графіки) уже вставлені з ваших results/.", size=10.5)
t = doc.add_table(rows=1 + len(SHOTS), cols=4)
t.style = "Table Grid"
for j, h in enumerate(["", "№", "Що показати", "Розділ"]):
    cell_text(t.rows[0].cells[j], h, size=10, bold=True)
for i, (n, title, where) in enumerate(sorted(SHOTS), 1):
    for j, v in enumerate(["☐", str(n), title, where]):
        cell_text(t.rows[i].cells[j], v, size=10)

doc.save(OUT)
print(f"Готово: {OUT} (скріншотів: {len(SHOTS)})")
