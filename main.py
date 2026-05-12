import asyncio
import hmac
import hashlib
import time
import json
import websockets
import requests
import os
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont

API_KEY = os.environ["BYBIT_API_KEY"]
API_SECRET = os.environ["BYBIT_API_SECRET"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

open_positions = {}
pending_orders = {}
pending_tasks = {}

BG = (26, 29, 38)
BG2 = (18, 20, 28)
BORDER = (42, 45, 58)
TEXT = (232, 234, 240)
MUTED = (90, 95, 122)
GREEN = (14, 203, 129)
RED = (246, 70, 93)
YELLOW = (240, 185, 11)

FONT_REG = "/tmp/roboto.ttf"
FONT_BOLD = "/tmp/roboto_bold.ttf"


def download_fonts():
    try:
        urllib.request.urlretrieve(
            "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf",
            FONT_REG
        )

        urllib.request.urlretrieve(
            "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf",
            FONT_BOLD
        )

        print("✅ Шрифты загружены")

    except Exception as e:
        print(f"Ошибка загрузки шрифтов: {e}")


def load_positions():
    try:
        timestamp = str(int(time.time() * 1000))
        params = "category=linear&settleCoin=USDT"

        sign_str = timestamp + API_KEY + "5000" + params

        signature = hmac.new(
            API_SECRET.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()

        headers = {
            "X-BAPI-API-KEY": API_KEY,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "X-BAPI-SIGN": signature,
        }

        url = f"https://api.bybit.com/v5/position/list?{params}"

        resp = requests.get(url, headers=headers)
        data = resp.json()

        for item in data.get("result", {}).get("list", []):

            size = float(item.get("size", 0))

            if size > 0:
                symbol = item["symbol"]
                side = item["side"]
                avg_price = float(item.get("avgPrice", 0))

                open_positions[symbol] = {
                    "side": side,
                    "qty": size,
                    "price": avg_price
                }

                print(
                    f"Загружена позиция: "
                    f"{symbol} {side} {size} @ {avg_price}"
                )

        print(f"✅ Загружено позиций: {len(open_positions)}")

    except Exception as e:
        print(f"Ошибка загрузки позиций: {e}")


download_fonts()
load_positions()


def get_font(size, bold=False):
    try:
        path = FONT_BOLD if bold else FONT_REG
        return ImageFont.truetype(path, size)

    except:
        return ImageFont.load_default()


def draw_rounded_rect(draw, xy, radius, fill, border=None):
    x1, y1, x2, y2 = xy

    draw.rounded_rectangle(
        [x1, y1, x2, y2],
        radius=radius,
        fill=fill,
        outline=border,
        width=1
    )


def make_card(card_type, symbol, side, price, qty, extra=None):

    W, H = 600, 280 if extra else 240

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw_rounded_rect(
        draw,
        [0, 0, W - 1, H - 1],
        16,
        BG,
        BORDER
    )

    if card_type == "new":
        type_color = GREEN
        type_text = "НОВАЯ ПОЗИЦИЯ"

    elif card_type == "add":
        type_color = YELLOW
        type_text = "ДОБИРАЕМ ПОЗИЦИЮ"

    elif card_type == "close":
        type_color = RED
        type_text = "ПОЗИЦИЯ ЗАКРЫТА"

    elif card_type == "partial":
        type_color = RED
        type_text = "ЧАСТИЧНОЕ ЗАКРЫТИЕ"

    else:
        type_color = TEXT
        type_text = card_type

    now = time.strftime("%d.%m.%Y  %H:%M")

    f11 = get_font(16)
    f13 = get_font(18)
    f15 = get_font(20)
    f26 = get_font(34, bold=True)
    f12 = get_font(15)

    draw.text((24, 22), type_text, font=f13, fill=type_color)

    draw.text(
        (W - 24, 22),
        now,
        font=f11,
        fill=MUTED,
        anchor="ra"
    )

    draw.text((24, 58), symbol, font=f26, fill=TEXT)

    badge_text = "LONG" if side == "Buy" else "SHORT"
    badge_color = GREEN if side == "Buy" else RED

    bw = 90
    bx = W - 24 - bw
    by = 55

    draw_rounded_rect(
        draw,
        [bx, by, bx + bw, by + 30],
        15,
        (20, 60, 40) if side == "Buy" else (60, 20, 30),
        badge_color
    )

    draw.text(
        (bx + bw // 2, by + 15),
        badge_text,
        font=f13,
        fill=badge_color,
        anchor="mm"
    )

    draw.line(
        [(24, 105), (W - 24, 105)],
        fill=BORDER,
        width=1
    )

    cells = []

    if card_type in ("new", "close", "partial"):

        label1 = (
            "Цена входа"
            if card_type == "new"
            else "Цена закрытия"
        )

        cells = [
            (label1, price),
            ("Количество", str(qty)),
        ]

    elif card_type == "add":

        cells = [
            ("Добавлено", str(qty)),
            ("Цена", price),
            ("Итого в позиции", extra.get("total_qty", "")),
            ("Средняя цена", extra.get("avg_price", "")),
        ]

    cell_w = (W - 48 - 10) // 2

    for i, (label, value) in enumerate(cells):

        col = i % 2
        row = i // 2

        cx = 24 + col * (cell_w + 10)
        cy = 118 + row * 80

        draw_rounded_rect(
            draw,
            [cx, cy, cx + cell_w, cy + 64],
            10,
            BG2
        )

        draw.text(
            (cx + 14, cy + 12),
            label,
            font=f12,
            fill=MUTED
        )

        draw.text(
            (cx + 14, cy + 36),
            str(value),
            font=f15,
            fill=TEXT
        )

    return img


def format_price(price):
    try:
        p = float(price)

        s = f"{p:.10f}".rstrip("0")

        decimals = (
            len(s.split(".")[1])
            if "." in s
            else 0
        )

        decimals = max(decimals, 2)

        return f"${p:,.{decimals}f}"

    except:
        return str(price)


def send_photo(img):

    buf = io.BytesIO()

    img.save(buf, format="PNG")

    buf.seek(0)

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"

    requests.post(
        url,
        data={"chat_id": TG_CHAT_ID},
        files={"photo": ("card.png", buf, "image/png")}
    )


def send_telegram(text):

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML"
        }
    )


def get_signature(secret, params_str):

    return hmac.new(
        secret.encode(),
        params_str.encode(),
        hashlib.sha256
    ).hexdigest()


async def flush_order(order_id):

    await asyncio.sleep(3)

    order = pending_orders.pop(order_id, None)

    pending_tasks.pop(order_id, None)

    if not order:
        return

    symbol = order["symbol"]
    side = order["side"]
    total_qty = order["total_qty"]

    avg_price = (
        order["total_value"] / total_qty
        if total_qty
        else 0
    )

    price_fmt = format_price(avg_price)

    existing = open_positions.get(symbol)

    try:

        if existing and existing["side"] == side:

            old_qty = existing["qty"]
            old_price = existing["price"]

            new_qty = old_qty + total_qty

            new_avg = (
                (old_price * old_qty)
                + (avg_price * total_qty)
            ) / new_qty

            open_positions[symbol] = {
                "side": side,
                "qty": new_qty,
                "price": new_avg
            }

            img = make_card(
                "add",
                symbol,
                side,
                price_fmt,
                total_qty,
                extra={
                    "total_qty": str(round(new_qty, 8)),
                    "avg_price": format_price(new_avg)
                }
            )

            send_photo(img)

        elif existing and existing["side"] != side:

            old_qty = existing["qty"]

            remaining = round(
                old_qty - total_qty,
                10
            )

            if remaining <= 0:

                open_positions.pop(symbol, None)

                img = make_card(
                    "close",
                    symbol,
                    side,
                    price_fmt,
                    total_qty
                )

            else:

                open_positions[symbol]["qty"] = remaining

                img = make_card(
                    "partial",
                    symbol,
                    side,
                    price_fmt,
                    total_qty
                )

            send_photo(img)

        else:

            open_positions[symbol] = {
                "side": side,
                "qty": total_qty,
                "price": avg_price
            }

            img = make_card(
                "new",
                symbol,
                side,
                price_fmt,
                total_qty
            )

            send_photo(img)

        print(
            f"Отправлено: "
            f"{symbol} "
            f"{side} "
            f"{total_qty} "
            f"@ {avg_price}"
        )

    except Exception as e:

        print(f"Ошибка карточки: {e}")

        send_telegram(
            f"Сделка: "
            f"{symbol} "
            f"{side} "
            f"{total_qty} "
            f"@ {price_fmt}"
        )


async def handle_message(data):

    if "topic" not in data:
        return

    try:

        if data["topic"] == "execution":

            for item in data["data"]:

                symbol = item.get("symbol", "—")
                side = item.get("side", "—")
                price = item.get("execPrice", "0")
                qty = float(item.get("execQty", 0))
                order_id = item.get("orderId", "—")
                exec_type = item.get("execType", "")

                if exec_type == "Funding":
                    continue

                try:
                    price_float = float(price)

                except:
                    price_float = 0

                if order_id in pending_orders:

                    pending_orders[order_id]["total_qty"] += qty

                    pending_orders[order_id]["total_value"] += (
                        price_float * qty
                    )

                else:

                    pending_orders[order_id] = {
                        "symbol": symbol,
                        "side": side,
                        "total_qty": qty,
                        "total_value": price_float * qty,
                    }

                if order_id in pending_tasks:
                    pending_tasks[order_id].cancel()

                task = asyncio.create_task(
                    flush_order(order_id)
                )

                pending_tasks[order_id] = task

    except Exception as e:

        print(
            f"Ошибка обработки: "
            f"{e} | Данные: {data}"
        )


async def connect():

    uri = "wss://stream.bybit.com/v5/private"

    while True:

        try:

            async with websockets.connect(uri) as ws:

                expires = int(
                    (time.time() + 10) * 1000
                )

                sign_str = f"GET/realtime{expires}"

                signature = get_signature(
                    API_SECRET,
                    sign_str
                )

                auth = {
                    "op": "auth",
                    "args": [
                        API_KEY,
                        expires,
                        signature
                    ]
                }

                await ws.send(json.dumps(auth))

                await asyncio.sleep(1)

                subscribe = {
                    "op": "subscribe",
                    "args": ["execution"]
                }

                await ws.send(json.dumps(subscribe))

                print("✅ Подключено к Bybit WebSocket")

                async for message in ws:

                    data = json.loads(message)

                    await handle_message(data)

        except Exception as e:

            print(
                f"Ошибка: {e}, "
                f"переподключение через 5 сек..."
            )

            await asyncio.sleep(5)


asyncio.run(connect())
