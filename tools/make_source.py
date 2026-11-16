"""Генератор власного вихідного відео «периметр об'єкта» (60 с, 1920x1080, 30 кадр/с).

Запуск з кореня репозиторію: python tools/make_source.py
Вихід: data/source.mp4 (H.264, CRF 18, без звуку).

Сцена: огорожа периметра, смуга трави, дорога. На 5-20 с повз огорожу
проходить людина, на 24-36 с проїжджає автомобіль, на 40-50 с пробігає
тварина, на 52-59 с людина повертається. Додано шум матриці та повільну
зміну освітленості, щоб відео поводилося як запис справжньої камери.
Усі кадри малюються програмою, тому матеріал власний, без ліцензійних обмежень.
"""
import subprocess
from pathlib import Path

import cv2
import numpy as np

W, H, FPS, SECONDS = 1920, 1080, 30, 60
OUT = Path("data/source.mp4")
rng = np.random.default_rng(2026)


def background():
    bg = np.zeros((H, W, 3), np.uint8)
    for y in range(0, 420):                       # небо
        k = y / 420
        bg[y, :] = (int(235 - 40 * k), int(200 - 30 * k), int(150 - 20 * k))
    bg[420:560] = (60, 90, 55)                    # дерева вдалині
    for x in range(0, W, 37):
        cv2.circle(bg, (x + 10, 430 + (x * 7) % 40), 55 + (x % 5) * 6,
                   (45, 100 + (x % 7) * 4, 50), -1)
    bg[560:820] = (70, 130, 80)                   # трава
    grass = rng.integers(-18, 18, (260, W, 1), dtype=np.int16)
    bg[560:820] = np.clip(bg[560:820].astype(np.int16) + grass, 0, 255)
    bg[820:1080] = (95, 95, 100)                  # дорога
    cv2.line(bg, (0, 950), (W, 950), (200, 200, 200), 6)
    for x in range(0, W, 220):                    # розмітка
        cv2.line(bg, (x, 1000), (x + 110, 1000), (230, 230, 230), 8)
    for x in range(0, W, 120):                    # огорожа: стовпи й сітка
        cv2.rectangle(bg, (x, 600), (x + 10, 840), (90, 90, 95), -1)
    for y in range(620, 840, 22):
        cv2.line(bg, (0, y), (W, y), (130, 130, 135), 2)
    for x in range(0, W, 24):
        cv2.line(bg, (x, 620), (x + 18, 840), (120, 120, 125), 1)
    return bg


def person(img, x, y, t):
    swing = int(14 * np.sin(t * 6))
    cv2.circle(img, (x, y - 150), 18, (170, 190, 220), -1)
    cv2.rectangle(img, (x - 22, y - 130), (x + 22, y - 40), (40, 40, 160), -1)
    cv2.line(img, (x - 10, y - 40), (x - 10 + swing, y + 30), (30, 30, 30), 14)
    cv2.line(img, (x + 10, y - 40), (x + 10 - swing, y + 30), (30, 30, 30), 14)


def car(img, x, y):
    cv2.rectangle(img, (x, y - 70), (x + 260, y), (30, 30, 190), -1)
    cv2.rectangle(img, (x + 50, y - 120), (x + 200, y - 70), (60, 60, 200), -1)
    cv2.rectangle(img, (x + 62, y - 110), (x + 120, y - 74), (210, 220, 230), -1)
    cv2.rectangle(img, (x + 130, y - 110), (x + 190, y - 74), (210, 220, 230), -1)
    for cx in (x + 55, x + 205):
        cv2.circle(img, (cx, y), 28, (15, 15, 15), -1)
        cv2.circle(img, (cx, y), 12, (160, 160, 160), -1)


def animal(img, x, y, t):
    sw = int(10 * np.sin(t * 14))
    cv2.ellipse(img, (x, y - 30), (45, 24), 0, 0, 360, (60, 90, 140), -1)
    cv2.circle(img, (x + 48, y - 42), 14, (60, 90, 140), -1)
    for dx, s in ((-28, sw), (-10, -sw), (14, sw), (32, -sw)):
        cv2.line(img, (x + dx, y - 12), (x + dx + s, y + 12), (40, 60, 100), 7)


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    bg = background()
    enc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
         "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium",
         "-pix_fmt", "yuv420p", "-an", str(OUT)], stdin=subprocess.PIPE)
    noise = np.zeros((H, W, 3), np.int16)
    for n in range(SECONDS * FPS):
        t = n / FPS
        light = 1.0 + 0.06 * np.sin(t / 9.0)      # повільна зміна освітлення
        frame = np.clip(bg.astype(np.float32) * light, 0, 255).astype(np.uint8)
        if 5 <= t < 20:
            person(frame, int(100 + (t - 5) / 15 * 1700), 790, t)
        if 24 <= t < 36:
            car(frame, int(1900 - (t - 24) / 12 * 2200), 1030)
        if 40 <= t < 50:
            animal(frame, int(150 + (t - 40) / 10 * 1600), 760, t)
        if 52 <= t < 59:
            person(frame, int(1800 - (t - 52) / 7 * 1500), 800, t)
        cv2.randn(noise, 0, 2.0)                  # шум матриці
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        enc.stdin.write(frame.tobytes())
    enc.stdin.close()
    enc.wait()
    print(f"Готово: {OUT}")


if __name__ == "__main__":
    main()
