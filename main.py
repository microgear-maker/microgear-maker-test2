import asyncio
import hmac
import hashlib
import time
import json
import websockets
import requests
import os

API_KEY = os.environ["BYBIT_API_KEY"]
API_SECRET = os.environ["BYBIT_API_SECRET"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]

open_positions = {}
pending_orders = {}
pending_tasks = {}

def format_price(price):
    try:
        p = float(price)
        s = f"{p:.10f}".rstrip("0")
        decimals = len(s.split(".")[1]) if "." in s else 0
        decimals = max(decimals, 2)
        return f"${p:,.{decimals}f}"
    except:
        return str(price)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_signature(secret, params_str):
    return hmac.new(secret.encode(), params_str.encode(), hashlib.sha256).hexdigest()

async def flush_order(order_id):
    await asyncio.sleep(3)
    
    order = pending_orders.pop(order_id, None)
    pending_tasks.pop(order_id, None)
    if not order:
        return

    symbol = order["symbol"]
    side = order["side"]
    total_qty = order["total_qty"]
    side_text = "🟢 ПОКУПКА" if side == "Buy" else "🔴 ПРОДАЖА"

    avg_price = order["total_value"] / total_qty if total_qty else 0
    price_fmt = format_price(avg_price)

    existing = open_positions.get(symbol)

    if existing and existing["side"] == side:
        old_qty = existing["qty"]
        old_price = existing["price"]
        new_qty = old_qty + total_qty
        new_avg = (old_price * old_qty + avg_price * total_qty) / new_qty
        open_positions[symbol] = {"side": side, "qty": new_qty, "price": new_avg}

        text = (
            f"<b>➕ ДОБИРАЕМ ПОЗИЦИЮ</b>\n"
            f"Пара: <b>{symbol}</b>\n"
            f"Направление: {side_text}\n"
            f"Добавлено: <b>{total_qty}</b> по {price_fmt}\n"
            f"Итого в позиции: <b>{new_qty}</b>\n"
            f"Средняя цена входа: <b>{format_price(new_avg)}</b>\n"
            f"🆔 Order ID: <code>{order_id}</code>"
        )

    elif existing and existing["side"] != side:
        old_qty = existing["qty"]
        remaining = round(old_qty - total_qty, 10)

        if remaining <= 0:
            open_positions.pop(symbol, None)
            text = (
                f"<b>🔒 ПОЗИЦИЯ ЗАКРЫТА</b>\n"
                f"Пара: <b>{symbol}</b>\n"
                f"Цена закрытия: <b>{price_fmt}</b>\n"
                f"Количество: <b>{total_qty}</b>\n"
                f"🆔 Order ID: <code>{order_id}</code>"
            )
        else:
            open_positions[symbol]["qty"] = remaining
            text = (
                f"<b>📉 ЧАСТИЧНОЕ ЗАКРЫТИЕ</b>\n"
                f"Пара: <b>{symbol}</b>\n"
                f"Закрыто: <b>{total_qty}</b> по {price_fmt}\n"
                f"Осталось в позиции: <b>{remaining}</b>\n"
                f"🆔 Order ID: <code>{order_id}</code>"
            )

    else:
        open_positions[symbol] = {"side": side, "qty": total_qty, "price": avg_price}
        text = (
            f"<b>⚡ НОВАЯ ПОЗИЦИЯ</b>\n"
            f"Пара: <b>{symbol}</b>\n"
            f"Направление: {side_text}\n"
            f"Цена входа: <b>{price_fmt}</b>\n"
            f"Количество: <b>{total_qty}</b>\n"
            f"🆔 Order ID: <code>{order_id}</code>"
        )

    send_telegram(text)
    print(f"Отправлено: {symbol} {side} {total_qty} @ {avg_price}")

async def connect():
    uri = "wss://stream.bybit.com/v5/private"
    
    while True:
        try:
            async with websockets.connect(uri) as ws:
                expires = int((time.time() + 10) * 1000)
                sign_str = f"GET/realtime{expires}"
                signature = get_signature(API_SECRET, sign_str)
                
                auth = {"op": "auth", "args": [API_KEY, expires, signature]}
                await ws.send(json.dumps(auth))
                await asyncio.sleep(1)
                
                subscribe = {"op": "subscribe", "args": ["execution"]}
                await ws.send(json.dumps(subscribe))
                print("✅ Подключено к Bybit WebSocket")
                
                async for message in ws:
                    data = json.loads(message)
                    await handle_message(data)
                    
        except Exception as e:
            print(f"Ошибка: {e}, переподключение через 5 сек...")
            await asyncio.sleep(5)

async def handle_message(data):
    if "topic" not in data:
        return
    
    try:
        if data["topic"] == "execution":
            for item in data["data"]:
                symbol = item.get("symbol", "—")
                side = item.get("side", "—")
                price = item.get("execPrice", "—")
                qty = float(item.get("execQty", 0))
                order_id = item.get("orderId", "—")
                exec_type = item.get("execType", "")

                if exec_type == "Funding":
                    return

                try:
                    price_float = float(price)
                except:
                    price_float = 0

                if order_id in pending_orders:
                    pending_orders[order_id]["total_qty"] += qty
                    pending_orders[order_id]["total_value"] += price_float * qty
                else:
                    pending_orders[order_id] = {
                        "symbol": symbol,
                        "side": side,
                        "total_qty": qty,
                        "total_value": price_float * qty,
                    }

                if order_id in pending_tasks:
                    pending_tasks[order_id].cancel()
                
                task = asyncio.create_task(flush_order(order_id))
                pending_tasks[order_id] = task

    except Exception as e:
        print(f"Ошибка обработки: {e} | Данные: {data}")

asyncio.run(connect())
