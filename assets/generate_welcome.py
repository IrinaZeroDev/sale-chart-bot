"""Генерирует Welcome-картинку бота (640x360 PNG) — та же палитра и стиль
персонажа, что и в аватарке (assets/generate_avatar.py), но полноростовая
сцена с приветственным жестом и чат-пузырями — для более дружелюбного,
«живого» первого впечатления на стартовом экране бота.

Требует Pillow:
    pip install pillow
    python assets/generate_welcome.py

Результат: assets/bot_welcome.png — загрузить вручную через @BotFather
→ /mybots → Edit Bot → Edit Welcome Message → Edit Welcome Picture,
отправить файл как «Фото» (не как файл/документ).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from generate_avatar import DEEP_BLUE, LIGHT_BG, NAVY, TURQUOISE, WHITE

WIDTH, HEIGHT = 640, 360


def _bubble(draw: ImageDraw.ImageDraw, box: list[int], fill, tail_left: bool) -> None:
    draw.rounded_rectangle(box, radius=18, fill=fill)
    x0, y0, x1, y1 = box
    tail_y = y1 - 10
    if tail_left:
        draw.polygon([(x0 + 18, tail_y), (x0 + 18, tail_y + 16), (x0 - 2, tail_y + 4)], fill=fill)
    else:
        draw.polygon([(x1 - 18, tail_y), (x1 - 18, tail_y + 16), (x1 + 2, tail_y + 4)], fill=fill)
    dot_color = WHITE if fill == TURQUOISE else NAVY
    cx = x0 + 22
    cy = (y0 + y1) // 2 - 6
    for i in range(3):
        draw.ellipse([cx + i * 20, cy, cx + i * 20 + 12, cy + 12], fill=dot_color)


def generate(output_path: Path) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), LIGHT_BG)
    draw = ImageDraw.Draw(img)

    # Мягкая "тень"-подложка под персонажем
    draw.ellipse([70, 300, 330, 340], fill=(214, 231, 244))

    # --- Персонаж: голова + тело + машущая рука ---
    cx = 195  # смещаем влево, справа место под чат-пузыри

    # Тело
    draw.rounded_rectangle([cx - 95, 210, cx + 95, 330], radius=46, fill=NAVY)

    # Наушники
    draw.ellipse([cx - 145, 55, cx - 65, 175], fill=NAVY)
    draw.ellipse([cx + 65, 55, cx + 145, 175], fill=NAVY)
    draw.ellipse([cx - 122, 78, cx - 88, 152], fill=TURQUOISE)
    draw.ellipse([cx + 88, 78, cx + 122, 152], fill=TURQUOISE)

    # Голова
    draw.rounded_rectangle([cx - 110, 30, cx + 110, 230], radius=58, fill=NAVY)
    draw.arc([cx - 135, 20, cx + 135, 175], start=200, end=340, fill=NAVY, width=16)

    # Глаза
    eye_y = 115
    draw.ellipse([cx - 55, eye_y, cx - 19, eye_y + 36], fill=WHITE)
    draw.ellipse([cx + 19, eye_y, cx + 55, eye_y + 36], fill=WHITE)
    draw.ellipse([cx - 47, eye_y + 10, cx - 27, eye_y + 30], fill=DEEP_BLUE)
    draw.ellipse([cx + 27, eye_y + 10, cx + 47, eye_y + 30], fill=DEEP_BLUE)

    # Улыбка
    draw.arc([cx - 48, 140, cx + 48, 200], start=20, end=160, fill=TURQUOISE, width=12)

    # Машущая рука — приподнятый овал справа от тела + короткие "линии движения"
    hand_cx, hand_cy = cx + 130, 230
    draw.ellipse([hand_cx - 26, hand_cy - 26, hand_cx + 26, hand_cy + 26], fill=NAVY)
    draw.ellipse([hand_cx - 14, hand_cy - 14, hand_cx + 14, hand_cy + 14], fill=TURQUOISE)
    for i, r in enumerate((44, 60, 76)):
        bbox = [hand_cx - r, hand_cy - r, hand_cx + r, hand_cy + r]
        draw.arc(bbox, start=300, end=340, fill=NAVY, width=5 - i)

    # --- Чат-пузыри справа: "диалог" с клиентом ---
    _bubble(draw, [400, 60, 600, 128], TURQUOISE, tail_left=True)
    _bubble(draw, [370, 158, 560, 222], WHITE, tail_left=True)
    _bubble(draw, [420, 250, 600, 310], TURQUOISE, tail_left=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    print(f"Сохранено: {output_path} ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    generate(Path(__file__).parent / "bot_welcome.png")
