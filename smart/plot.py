"""Графік залежності затримки й втрат від навантаження.
Запуск з кореня репозиторію: python smart/plot.py
Вхід: results/load.csv; вихід: results/latency.png
"""
import csv

import matplotlib
matplotlib.use("Agg")                        # без вікна — одразу у файл
import matplotlib.pyplot as plt              # noqa: E402

with open("results/load.csv", encoding="utf-8") as f:
    rows = sorted(csv.DictReader(f), key=lambda r: float(r["rate"]))
rate = [float(r["rate"]) for r in rows]

fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(rate, [float(r["lat_mean_ms"]) for r in rows], "o-",
        label="середня затримка")
ax.plot(rate, [float(r["lat_p95_ms"]) for r in rows], "s--",
        label="95-й процентиль")
ax.set_xlabel("Навантаження λ, повідомлень/с")
ax.set_ylabel("Затримка доставки, мс")
ax.set_yscale("log")
ax.grid(True, which="both", alpha=0.3)

loss = ax.twinx()                            # друга вісь — частка втрат
loss.plot(rate, [100 * float(r["loss"]) for r in rows], "^:",
          color="tab:red", label="втрати ε")
loss.set_ylabel("Частка втрат ε, %")

lines = ax.get_lines() + loss.get_lines()
ax.legend(lines, [x.get_label() for x in lines], loc="upper left")
fig.tight_layout()
fig.savefig("results/latency.png", dpi=150)
print("Графік: results/latency.png")
