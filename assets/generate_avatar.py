"""Генерирует аватарку бота по палитре из ревью тимлида: синий/бирюзовый/
белый, минималистичный дружелюбный робот.

Требует Pillow (dev-инструмент, не рантайм-зависимость бота):
    pip install pillow
    python assets/generate_avatar.py

Результат: assets/bot_avatar.png (640x360 — формат, который требует
@BotFather для /setuserpic) и assets/bot_avatar_square.png (512x512,
на случай если пригодится квадратный вариант где-то ещё). Bot API не
позволяет боту установить себе аватар программно — загружать вручную
через @BotFather → /mybots → Edit Bot → Edit Botpic → отправить как «Фото».
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
NAVY = (26, 58, 92)
DEEP_BLUE = (20, 45, 74)
TURQUOISE = (45, 200, 195)
LIGHT_BG = (234, 244, 251)
WHITE = (255, 255, 255)

BOTFATHER_SIZE = (640, 360)


def _draw_square() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), WHITE)
    draw = ImageDraw.Draw(img)

    # Мягкий фоновый круг
    margin = 12
    draw.ellipse([margin, margin, SIZE - margin, SIZE - margin], fill=LIGHT_BG)

    # "Наушники" — два навy-круга по бокам головы
    draw.ellipse([48, 168, 148, 328], fill=NAVY)
    draw.ellipse([364, 168, 464, 328], fill=NAVY)
    draw.ellipse([78, 198, 118, 298], fill=TURQUOISE)
    draw.ellipse([394, 198, 434, 298], fill=TURQUOISE)

    # Голова робота — скруглённый прямоугольник
    head_box = [126, 120, 386, 380]
    draw.rounded_rectangle(head_box, radius=70, fill=NAVY)

    # Дуга-обод сверху (соединяет наушники)
    draw.arc([88, 108, 424, 300], start=200, end=340, fill=NAVY, width=20)

    # Глаза
    eye_y = 235
    draw.ellipse([182, eye_y, 226, eye_y + 44], fill=WHITE)
    draw.ellipse([286, eye_y, 330, eye_y + 44], fill=WHITE)
    draw.ellipse([196, eye_y + 12, 220, eye_y + 36], fill=DEEP_BLUE)
    draw.ellipse([300, eye_y + 12, 324, eye_y + 36], fill=DEEP_BLUE)

    # Улыбка
    draw.arc([196, 268, 316, 340], start=20, end=160, fill=TURQUOISE, width=14)

    # Бирюзовый чат-пузырь снизу справа
    bubble_box = [318, 322, 452, 410]
    draw.rounded_rectangle(bubble_box, radius=24, fill=TURQUOISE)
    draw.polygon([(330, 400), (330, 424), (356, 402)], fill=TURQUOISE)
    for dx in (352, 386, 420):
        draw.ellipse([dx, 356, dx + 16, 372], fill=WHITE)

    return img


def generate(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    square = _draw_square()

    square_path = output_dir / "bot_avatar_square.png"
    square.save(square_path, "PNG")
    print(f"Сохранено: {square_path}")

    # BotFather требует конкретно 640x360 — вписываем квадратный рисунок по
    # высоте и центрируем на белом фоне (совпадает с фоном самого рисунка,
    # так что шва не видно).
    width, height = BOTFATHER_SIZE
    scaled = square.resize((height, height), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), WHITE)
    canvas.paste(scaled, ((width - height) // 2, 0))

    wide_path = output_dir / "bot_avatar.png"
    canvas.save(wide_path, "PNG")
    print(f"Сохранено: {wide_path} ({width}x{height}) — этот файл для @BotFather")


if __name__ == "__main__":
    generate(Path(__file__).parent)
