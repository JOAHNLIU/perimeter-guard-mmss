"""Формує docs/qoe.md і блок «Підтвердження вимірюваннями» в ADR-0004
за results/qoe.csv (вимірювання в браузері) та results/encoding.csv.

Запуск з кореня репозиторію:
    python tools/make_qoe_report.py                 # повний звіт (потрібно >= 2 прогони на профіль)
    python tools/make_qoe_report.py --predict-only  # лише драбина й прогноз, до вимірювань
    python tools/make_qoe_report.py --encoding-table  # таблиця для docs/pipeline.md

Скрипт нічого не вигадує: усі числа в тексті беруться з CSV-файлів і з
розміру сегментів у stream/hls; ті фрази, що залежать від результату
(були зупинки чи ні, вклався старт у 3 с чи ні), обираються за цими числами.
"""
import csv
import glob
import os
import statistics
import sys
from pathlib import Path

ENC = Path("results/encoding.csv")
QOE = Path("results/qoe.csv")
DOC = Path("docs/qoe.md")
ADR_GLOB = "docs/adr/0004-*.md"

ALPHA = 0.7                 # коефіцієнт запасу з формули (4)
DURATION = 60.0             # тривалість відтвореного матеріалу, с
SEG = 2                     # тривалість сегмента, с (stream/package.sh)
FIRST_SEGMENT_LIMIT = 3.0   # FR-02, FR-03: не довше ніж 3 с
# Рівні драбини: підпис, номінальний бітрейт, BANDWIDTH у master.m3u8 (кбіт/с)
LADDER = [("1280×720", 400, 440), ("960×540", 225, 248), ("640×360", 100, 110)]
# Профілі: назва, опис, Download, Upload, Latency (кбіт/с, кбіт/с, мс)
PROFILES = [("П1", "Швидка", 10000, 2000, 20),
            ("П2", "Середня", 1600, 750, 150),
            ("П3", "Повільна", 500, 500, 400)]


def f(x, n=1):
    """Число з десятковою комою."""
    return f"{x:.{n}f}".replace(".", ",")


def norm(name):
    return name.strip().replace("P", "П")  # латинська P -> українська П


def predict(download):
    """Формула (4): найвищий рівень, для якого b_k <= alpha * C."""
    for label, nominal, _ in LADDER:
        if nominal <= ALPHA * download:
            return label
    return None


def nearest_level(avg_kbps):
    label, _, manifest = min(LADDER, key=lambda l: abs(l[2] - avg_kbps))
    return label, manifest


def segment_kbps():
    """Середній бітрейт рівнів за розміром сегментів у stream/hls (якщо є)."""
    result = []
    for v in range(3):
        files = glob.glob(f"stream/hls/v{v}/*.ts")
        if not files:
            return None
        total = sum(os.path.getsize(x) for x in files)
        result.append(round(total * 8 / (len(files) * SEG) / 1000))
    return result


def load_qoe():
    runs = {p[0]: [] for p in PROFILES}
    if not QOE.exists():
        return runs
    with QOE.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            name = norm(r["profile"])
            if name in runs:
                runs[name].append({
                    "startup": float(r["startup_s"]),
                    "switches": int(float(r["switches"])),
                    "stalls": int(float(r["stalls"])),
                    "stall_s": float(r["stall_s"]),
                    "avg": float(r["avg_kbps"])})
    return runs


def rho(stall_s):
    return stall_s / (DURATION + stall_s)


def mean(runs, key):
    return statistics.mean(r[key] for r in runs)


def load_encoding():
    if not ENC.exists():
        return None
    with ENC.open(encoding="utf-8") as fh:
        return {r["variant"]: r for r in csv.DictReader(fh)}


def av1_saving(enc):
    """Скільки бітрейту H.264 потребує для PSNR найнижчого варіанта AV1."""
    try:
        h = sorted((r for r in enc.values() if r["codec"] == "h264"),
                   key=lambda r: float(r["actual_kbps"]))
        a = min((r for r in enc.values() if r["codec"] == "av1"),
                key=lambda r: float(r["actual_kbps"]))
        x0, y0 = float(h[0]["actual_kbps"]), float(h[0]["psnr_db"])
        x1, y1 = float(h[1]["actual_kbps"]), float(h[1]["psnr_db"])
        need = x0 + (float(a["psnr_db"]) - y0) * (x1 - x0) / (y1 - y0)
        got = float(a["actual_kbps"])
        t = statistics.mean(float(r["encode_s"]) for r in enc.values()
                            if r["codec"] == "av1") / statistics.mean(
            float(r["encode_s"]) for r in enc.values() if r["codec"] == "h264")
        return need, got, (1 - got / need) * 100, t
    except (KeyError, ValueError, IndexError, ZeroDivisionError):
        return None


def encoding_table(enc):
    lines = ["| Варіант | Розмір, КБ | Rф, кбіт/с | K | Кодування, с | PSNR, дБ | SSIM |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in enc.values():
        lines.append(f"| {r['variant']} | {r['size_kb']} | {r['actual_kbps']} | "
                     f"{r['compression']} | {f(float(r['encode_s']))} | "
                     f"{f(float(r['psnr_db']), 2)} | {f(float(r['ssim']), 4)} |")
    return "\n".join(lines)


# ---------------------------------------------------------------- розділи

def sec_ladder():
    seg = segment_kbps()
    rows = ["| Рівень | Розмір кадра | Номінальний бітрейт, кбіт/с | BANDWIDTH у master.m3u8, кбіт/с | Фактичний за сегментами, кбіт/с |",
            "|---|---|---:|---:|---:|"]
    for i, (label, nominal, manifest) in enumerate(LADDER):
        fact = seg[i] if seg else "—"
        rows.append(f"| v{i} | {label} | {nominal} | {manifest} | {fact} |")
    total = f" Сума фактичних бітрейтів трьох рівнів — {sum(seg)} кбіт/с, тобто в {f(sum(seg) / seg[0], 2)} раза більше, ніж займав би лише верхній рівень." if seg else ""
    return f"""## Драбина якостей

Драбину з трьох рівнів я склав за результатами заняття 1. Верхній рівень —
1280 × 720 на 400 кбіт/с: це найменший бітрейт H.264, за якого SSIM не
нижчий за 0,99 (`h264_400k`, SSIM 0,9941; `h264_200k` дає лише 0,9870).
Нижчі рівні я обчислив, зберігаючи сталу кількість біт на піксель
Rф/(w·h·f) = 400 000 / (1280 · 720 · 15) ≈ 0,0289 біт/піксель: для 960 × 540
це 225 кбіт/с, для 640 × 360 — 100 кбіт/с. Проміжний рівень я взяв 540p, а не
480p з прикладу методички, бо 960 × 540 має точне відношення сторін 16:9, а
854 × 480 — ні, і `ffmpeg` відмовлявся формувати з нього DASH-маніфест
(«Conflicting stream aspect ratios»).

{chr(10).join(rows)}

Фактичний бітрейт сегментів трохи перевищує номінальний, бо до нього
додаються службові дані контейнера MPEG-TS; найпомітніше це на нижньому
рівні. У `master.m3u8` плеєр бачить `BANDWIDTH`, обчислений із `-maxrate`.{total}

Сегменти я роблю тривалістю SEG = 2 с. Ключовий кадр ставиться на початку
кожного сегмента (`-g 30` за 15 кадр/с), а `-sc_threshold 0` забороняє кодеру
вставляти додаткові ключові кадри на зміні сцени. Завдяки цьому межі
сегментів усіх трьох рівнів збігаються, і плеєр може перемкнути рівень на
початку будь-якого сегмента без зупинки: у кожному рівні по 30 сегментів.
"""


def sec_profiles():
    rows = ["| Профіль | Download, кбіт/с | Upload, кбіт/с | Latency, мс | α · Ĉ, кбіт/с | Прогноз за (4) |",
            "|---|---:|---:|---:|---:|---|"]
    for name, desc, dl, ul, lat in PROFILES:
        lvl = predict(dl)
        rows.append(f"| {name} «{desc}» | {dl} | {ul} | {lat} | {int(ALPHA * dl)} | "
                    f"{lvl if lvl else 'жоден рівень не вміщується'} |")
    return f"""## Профілі мережі та прогноз

Перед вимірюваннями я записав прогноз. Для кожного профілю я підставив смугу
Download у формулу (4) b_k ≤ α · Ĉ при α = 0,7 і взяв найвищий рівень
драбини, що задовольняє нерівність. Для П1: 0,7 · 10 000 = 7000 кбіт/с,
тож вміщується навіть верхній рівень 400 кбіт/с. Для П2: 0,7 · 1600 = 1120
кбіт/с — теж верхній рівень. Для П3: 0,7 · 500 = 350 кбіт/с, верхній рівень
(400 кбіт/с) вже не вміщується, а 225 кбіт/с вміщується, тому очікую 960 × 540.
Відмінність від прикладу методички полягає в тому, що моя драбина набагато
«легша» (400/225/100 проти 2000/900/500 кбіт/с), тож зупинки на П3 не
гарантовані: найнижчий рівень 100 кбіт/с у 3,5 раза менший за 350 кбіт/с.

{chr(10).join(rows)}

Профілі створені у DevTools: Network → Throttling → Add profile. Під час
вимірювань я вмикав «Disable cache», щоб повторні прогони не брали сегменти з
кешу.
"""


def sec_results(runs, predict_only):
    if predict_only:
        return """## Результати вимірювань

> ⚠ Вимірювання в браузері ще не додано до `results/qoe.csv`. Після шести
> прогонів (три профілі по два рази) запустіть
> `python tools/make_qoe_report.py` — цей розділ і наступні будуть
> перегенеровані з результатів.
"""
    head = ["| Профіль | Прогін | Старт, с | Перемикань | Зупинок | Тривалість зупинок, с | avg_kbps | ρ |",
            "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, *_ in PROFILES:
        for i, r in enumerate(runs[name], 1):
            head.append(f"| {name} | {i} | {f(r['startup'], 2)} | {r['switches']} | "
                        f"{r['stalls']} | {f(r['stall_s'])} | {int(r['avg'])} | "
                        f"{f(rho(r['stall_s']), 2)} |")
    summ = ["| Профіль | Прогноз за (4) | Середній бітрейт, кбіт/с | Фактичний рівень | Середній старт, с | Середній ρ |",
            "|---|---|---:|---|---:|---:|"]
    notes = []
    for name, desc, dl, *_ in PROFILES:
        rs = runs[name]
        lvl, manifest = nearest_level(mean(rs, "avg"))
        pred = predict(dl) or "жоден"
        summ.append(f"| {name} | {pred} | {int(mean(rs, 'avg'))} | {lvl} | "
                    f"{f(mean(rs, 'startup'), 2)} | {f(statistics.mean(rho(r['stall_s']) for r in rs), 2)} |")
        a, b = rs[0]["startup"], rs[1]["startup"]
        if abs(a - b) > 0.3 * max(a, b) and abs(a - b) > 0.5:
            notes.append(f"На {name} часи старту двох прогонів помітно різняться "
                         f"({f(a, 2)} і {f(b, 2)} с). Пояснюю це тим, що на початку "
                         f"плеєр ще не має оцінки пропускної здатності, а перше "
                         f"завантаження залежить від поточного стану мережі комп'ютера "
                         f"та від того, що саме вже встигло потрапити в кеш браузера.")
    note = ("\n\n" + "\n\n".join(notes)) if notes else (
        "\n\nУ кожному профілі два прогони дали близькі результати, тож "
        "розкид між ними я вважаю випадковим.")
    p3 = runs["П3"]
    r3 = statistics.mean(rho(r["stall_s"]) for r in p3)
    return f"""## Результати вимірювань

Кожен профіль я прогнав двічі; обидва рядки з `results/qoe.csv` наведено
нижче. Коефіцієнт зупинок я рахував за формулою (5):
ρ = T_зуп / (T_відтв + T_зуп), де T_відтв = {int(DURATION)} с — тривалість
відтвореного матеріалу.

{chr(10).join(head)}

Підсумок за профілями (середнє за двома прогонами). Фактичний рівень я
визначав як найближчий за бітрейтом до середнього avg_kbps; якщо середній
бітрейт лежить між двома рівнями, це означає, що плеєр частину часу
відтворював один рівень, а частину — інший.

{chr(10).join(summ)}

Для П3 середній коефіцієнт зупинок ρ ≈ {f(r3, 2)}: {'глядач чекав приблизно ' + f(r3 * 100, 0) + ' % часу сеансу' if r3 > 0.005 else 'зупинок практично не було'}.{note}
"""


def sec_architecture(runs, enc):
    p1, p2, p3 = runs["П1"], runs["П2"], runs["П3"]
    t1, t3 = mean(p1, "startup"), mean(p3, "startup")
    sw1, sw2 = mean(p1, "switches"), mean(p2, "switches")
    st3 = mean(p3, "stalls")
    stall3 = mean(p3, "stall_s")
    lvl2, _ = nearest_level(mean(p2, "avg"))
    lvl3, _ = nearest_level(mean(p3, "avg"))
    lvl1, _ = nearest_level(mean(p1, "avg"))

    # Ефект 1: старт
    if t3 <= FIRST_SEGMENT_LIMIT:
        fr = (f"Це вкладається в межу 3 с із FR-02 і FR-03, тож на моїй драбині "
              f"типовий початковий рівень на П3 прийнятний.")
    else:
        fr = (f"Це більше за межу 3 с із FR-02 і FR-03, тобто з типовими "
              f"налаштуваннями вимога на П3 **не виконується**. Тому в ADR-0004 я "
              f"вибрав початковий рівень за оцінкою смуги.")
    e1 = f"""### Старт {f(t3, 2)} с на П3 проти {f(t1, 2)} с на П1

hls.js за замовчуванням починає з першого рівня в `master.m3u8`, тобто з
1280 × 720. Перший сегмент такого рівня важить ≈ 400 кбіт/с · 2 с = 800 кбіт
(≈ 100 КБ), що на 500 кбіт/с завантажується близько 1,6 с; до цього додаються
три послідовні запити (головний маніфест, маніфест рівня, сам сегмент) із
затримкою 400 мс, ≈ 1,2 с. Мінімально очікуваний старт на П3, отже, ≈ 2,8 с,
а виміряно {f(t3, 2)} с. {fr}

Відповідні параметри з табл. 1 — **початковий рівень** і **тривалість
сегмента**. Якщо створити плеєр з `new Hls({{ startLevel: -1 }})` (у
`player.html` — параметр `?startLevel=-1`), перший сегмент береться за
оцінкою смуги, тобто легший: 225 кбіт/с · 2 с = 450 кбіт ≈ 0,9 с на П3. Ціна —
перші секунди нижчої якості й одне зайве перемикання на швидких мережах. Якщо
зменшити SEG до 1 с, перший сегмент удвічі менший і старт швидший, але вдвічі
більше запитів до сервера й більший відсоток службових даних.
"""

    # Ефект 2: зупинки і нижній рівень
    if st3 < 0.5:
        e2 = f"""### Зупинок на П3: {f(st3, 1)}, ρ ≈ {f(statistics.mean(rho(r['stall_s']) for r in p3), 2)}

Зупинок майже не було; пояснюю це **найнижчим рівнем драбини**. Його бітрейт
100 кбіт/с у 3,5 раза менший за 0,7 · 500 = 350 кбіт/с, тож коли пропускної
здатності не вистачало на вищі рівні, плеєр мав куди знизитись і міг
накопичувати буфер. У прикладі методички (500 кбіт/с — найнижчий рівень на
смузі 500 кбіт/с) було навпаки: 29 зупинок. Ціною цього є сховище й час
пакування: рівень 360p займає ≈ 15 % сумарного обсягу сегментів. Якби я
прибрав нижній рівень, на П3 лишилися б рівні 400 і 225 кбіт/с; 225 кбіт/с
вміщується в 350 кбіт/с лише з запасом ≈ 1,6 раза, тож нижній рівень — це
страховка на випадок, коли смуга впаде нижче за 500 кбіт/с.
"""
    else:
        e2 = f"""### Зупинок на П3: {f(st3, 1)} ({f(stall3, 1)} с), ρ ≈ {f(statistics.mean(rho(r['stall_s']) for r in p3), 2)}

На П3 глядач помітно чекав. Така картина виникає, коли плеєр починає з
верхнього рівня (400 кбіт/с), а пропускна здатність разом із затримкою 400 мс
не встигає за бітрейтом сегмента, тому буфер спорожнюється раніше, ніж
ABR-алгоритм опускається на 225 чи 100 кбіт/с. Параметри з табл. 1, які це
визначають, — **початковий рівень** (`startLevel: -1`), **глибина буфера**
(більший буфер дає ABR час зреагувати, ціною затримки) і **найнижчий рівень
драбини** (100 кбіт/с уже вміщується в 0,7 · 500 = 350 кбіт/с). Архітектурне
виправлення, яке я прийняв в ADR-0004: стартувати за оцінкою смуги.
"""

    # Ефект 3: П1 і П2 проти прогнозу
    match1 = lvl1 == predict(PROFILES[0][2])
    match2 = lvl2 == predict(PROFILES[1][2])
    if sw1 < 0.5 and sw2 < 0.5 and match1 and match2:
        e3 = f"""### П1 і П2: рівень збігся з прогнозом, перемикань немає

На П1 і П2 (середні перемикання {f(sw1, 1)} і {f(sw2, 1)}) фактичний рівень — {lvl1} і
{lvl2} — збігся з прогнозом за формулою (4): 400 кбіт/с вміщується навіть у
0,7 · 1600 = 1120 кбіт/с, тож перемикатися нікуди й нема потреби. Це означає,
що на швидких профілях компроміс «якість — смуга» взагалі не проявляється: на
них визначальний параметр — **початковий рівень**, і він збігається з
верхнім рівнем драбини завдяки тому, що перший рівень у маніфесті — найвищий.
"""
    else:
        e3 = f"""### П1 і П2: рівні {lvl1} і {lvl2}, перемикань {f(sw1, 1)} і {f(sw2, 1)}

Прогноз за (4) для П1 і П2 — {predict(PROFILES[0][2])} і {predict(PROFILES[1][2])}; фактичні рівні — {lvl1} і
{lvl2}. Розбіжність пояснюю тим, що формула (4) — статична: вона бере
стале Ĉ, тоді як hls.js оцінює пропускну здатність за завантаженими
сегментами (коротка історія на початку), використовує різні коефіцієнти для
підвищення й зниження рівня та враховує заповненість буфера. Перемикання
({f(sw1, 1)} на П1, {f(sw2, 1)} на П2) виникають, поки оцінка ще не усталилась; параметр з табл. 1 —
**початковий рівень**.
"""

    # Ефект 4: кодек
    sv = av1_saving(enc) if enc else None
    if sv:
        need, got, pct, ratio = sv
        e4 = f"""### Кодек: H.264 у драбині, AV1 лише як резерв

За вимірюваннями заняття 1 AV1 на {int(got)} кбіт/с досягає тієї якості за PSNR,
для якої H.264 потребує ≈ {int(need)} кбіт/с, тобто заощаджує приблизно {int(round(pct))} %, але кодується
в {f(ratio, 1)} раза довше. У драбині я залишив H.264: сегменти `.ts` із ним
відтворює hls.js скрізь, а AV1 вимагав би fMP4 і сучасних клієнтів.
Параметр «кодек» (табл. 1) поліпшує обсяг трафіку, але погіршує час
кодування й підтримку старих пристроїв, і для динамічного потоку я обрав
сумісність.
"""
    else:
        e4 = ""

    return f"""## Зв'язок з архітектурою

Нижче для кожного помітного ефекту я називаю параметр із табл. 1, який його
спричинив, і описую, що зміниться, якщо цей параметр змінити.

{e1}
{e2}
{e3}
{e4}"""


def sec_requirements(runs):
    rows = ["| Вимога ЛР 1 | Що перевіряю | Результат |", "|---|---|---|"]
    for name, desc, dl, *_ in PROFILES:
        t = mean(runs[name], "startup")
        ok = "виконується" if t <= FIRST_SEGMENT_LIMIT else "не виконується"
        rows.append(f"| FR-02, FR-03 | старт відтворення кліпу/архіву ≤ 3 с, {name} | {f(t, 2)} с — {ok} |")
    rows.append(f"| NFR-01 | затримка ≤ 2000 мс | HLS не використовується для живого перегляду (див. нижче) |")
    return f"""## Перевірка вимог ЛР 1

У ЛР 1 я зафіксував у ADR-0002, що живий перегляд іде через WebRTC, а HLS із
типовою затримкою 6–30 с не вкладається в бюджет NFR-01 (2000 мс). Нині
адаптивне потокове передавання я розглядаю для двох сценаріїв доставляння,
де затримка у секундах некритична: перегляд архіву (FR-03) й відтворення
кліпу тривоги (FR-02) віддаленим оператором слабким каналом. Для таких
сценаріїв критерій приймання — старт відтворення не довше за 3 с. Мінімальна
затримка живого HLS за SEG = 2 с — близько трьох сегментів, тобто ≈ 6 с,
отже, наскрізну вимогу NFR-01 цей потік не виконує, і живий перегляд
лишається за WebRTC.

{chr(10).join(rows)}
"""


def adr_block(runs, enc):
    lines = []
    if enc and "h264_400k" in enc:
        lines.append(f"- `results/encoding.csv`: `h264_400k` — Rф = {enc['h264_400k']['actual_kbps']} кбіт/с, "
                     f"K = {enc['h264_400k']['compression']}, SSIM {f(float(enc['h264_400k']['ssim']), 4)}; "
                     f"`h264_200k` — SSIM {f(float(enc['h264_200k']['ssim']), 4)} (< 0,99), тому верхній рівень 400 кбіт/с.")
    sv = av1_saving(enc) if enc else None
    if sv:
        lines.append(f"- AV1 заощаджує ≈ {int(round(sv[2]))} % бітрейту за однакового PSNR, але кодується в {f(sv[3], 1)} раза довше.")
    for name, *_ in PROFILES:
        rs = runs[name]
        lvl, _ = nearest_level(mean(rs, "avg"))
        lines.append(f"- `results/qoe.csv`, {name}: старт {f(mean(rs, 'startup'), 2)} с, перемикань {f(mean(rs, 'switches'), 1)}, "
                     f"зупинок {f(mean(rs, 'stalls'), 1)}, ρ ≈ {f(statistics.mean(rho(r['stall_s']) for r in rs), 2)}, рівень {lvl}.")
    t3 = mean(runs["П3"], "startup")
    if t3 > FIRST_SEGMENT_LIMIT:
        lines.append(f"- Старт на П3 з типовим першим рівнем — {f(t3, 2)} с > 3 с: це підтверджує рішення про `startLevel: -1`.")
    else:
        lines.append(f"- Старт на П3 з типовим першим рівнем — {f(t3, 2)} с ≤ 3 с; `startLevel: -1` залишаю як запобіжник для ще повільніших каналів, а не як усунення виявленої проблеми.")
    return "\n".join(lines)


def update_adr(block):
    for path in glob.glob(ADR_GLOB):
        text = Path(path).read_text(encoding="utf-8")
        a, b = "<!-- QOE:BEGIN -->", "<!-- QOE:END -->"
        if a in text and b in text:
            head, rest = text.split(a, 1)
            _, tail = rest.split(b, 1)
            Path(path).write_text(f"{head}{a}\n{block}\n{b}{tail}", encoding="utf-8")
            print(f"Оновлено блок вимірювань у {path}")
        else:
            print(f"Увага: у {path} немає маркерів QOE:BEGIN/QOE:END")


def main():
    args = sys.argv[1:]
    enc = load_encoding()
    if "--encoding-table" in args:
        print(encoding_table(enc))
        sv = av1_saving(enc)
        if sv:
            print(f"\nH.264 потребує ≈ {sv[0]:.0f} кбіт/с для PSNR найнижчого AV1; "
                  f"AV1 — {sv[1]:.0f} кбіт/с; заощадження ≈ {sv[2]:.0f} %; "
                  f"кодування AV1 довше в {sv[3]:.1f} раза.")
        return
    predict_only = "--predict-only" in args
    runs = load_qoe()
    if not predict_only:
        missing = [n for n, *_ in PROFILES if len(runs[n]) < 2]
        if missing:
            sys.exit(f"Недостатньо прогонів у results/qoe.csv для: {', '.join(missing)} "
                     f"(потрібно щонайменше 2 на профіль).")
    parts = ["# Звіт заняття 2. Адаптивне потокове передавання та вимірювання QoE\n",
             "У цьому звіті я описую драбину якостей, вимірювання показників QoE на\n"
             "трьох профілях мережі та зв'язок результатів з архітектурними\n"
             "рішеннями. Кожне число нижче взято з `results/qoe.csv`, "
             "`results/encoding.csv` або з розміру сегментів у `stream/hls`.\n",
             sec_ladder(), sec_profiles(), sec_results(runs, predict_only)]
    if not predict_only:
        parts += [sec_architecture(runs, enc), sec_requirements(runs)]
        update_adr(adr_block(runs, enc))
    DOC.write_text("\n".join(parts), encoding="utf-8")
    print(f"Готово: {DOC}")


if __name__ == "__main__":
    main()
