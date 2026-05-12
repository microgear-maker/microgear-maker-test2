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

# Хранилище открытых позиций в памяти
open_positions = {}  # { "BTCUSDT": { "side": "Buy", "qty": 15, "price": 10000 } }

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"})

def get_signature(secret, params_str):
    return hmac.new(secret.encode(), params_str.encode(), hashlib.sha256).hexdigest()

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
                order_type = item.get("orderType", "—")
                order_id = item.get("orderId", "—")
                exec_type = item.get("execType", "")

                # Пропускаем финансовые записи (funding fee и тд)
                if exec_type == "Funding":
                    return

                try:
                    price_fmt = f"${float(price):,.2f}"
                    price_float = float(price)
                except:
                    price_fmt = price
                    price_float = 0

                side_text = "🟢 ПОКУПКА" if side == "Buy" else "🔴 ПРОДАЖА"

                # Проверяем есть ли уже позиция по этой монете
                existing = open_positions.get(symbol)

                if existing and existing["side"] == side:
                    # Докупаем / добавляем в ту же сторону
                    old_qty = existing["qty"]
                    old_price = existing["price"]
                    new_qty = old_qty + qty
                    # Средняя цена входа
                    new_avg = (old_price * old_qty + price_float * qty) / new_qty
                    
                    open_positions[symbol] = {
                        "side": side,
                        "qty": new_qty,
                        "price": new_avg
                    }

                    text = (
                        f"<b>➕ ДОБИРАЕМ ПОЗИЦИЮ</b>\n"
                        f"Пара: <b>{symbol}</b>\n"
                        f"Направление: {side_text}\n"
                        f"Добавлено: <b>{qty}</b> по {price_fmt}\n"
                        f"Итого в позиции: <b>{new_qty}</b>\n"
                        f"Средняя цена входа: <b>${new_avg:,.2f}</b>\n"
                        f"🆔 Order ID: <code>{order_id}</code>"
                    )

                elif existing and existing["side"] != side:
                    # Закрываем или переворачиваем позицию
                    old_qty = existing["qty"]
                    remaining = old_qty - qty

                    if remaining <= 0:
                        # Полное закрытие
                        open_positions.pop(symbol, None)
                        text = (
                            f"<b>🔒 ПОЗИЦИЯ ЗАКРЫТА</b>\n"
                            f"Пара: <b>{symbol}</b>\n"
                            f"Цена закрытия: <b>{price_fmt}</b>\n"
                            f"Количество: <b>{qty}</b>\n"
                            f"🆔 Order ID: <code>{order_id}</code>"
                        )
                    else:
                        # Частичное закрытие
                        open_positions[symbol]["qty"] = remaining
                        text = (
                            f"<b>📉 ЧАСТИЧНОЕ ЗАКРЫТИЕ</b>\n"
                            f"Пара: <b>{symbol}</b>\n"
                            f"Закрыто: <b>{qty}</b> по {price_fmt}\n"
                            f"Осталось в позиции: <b>{remaining}</b>\n"
                            f"🆔 Order ID: <code>{order_id}</code>"
                        )

                else:
                    # Новая позиция
                    open_positions[symbol] = {
                        "side": side,
                        "qty": qty,
                        "price": price_float
                    }
                    text = (
                        f"<b>⚡ НОВАЯ ПОЗИЦИЯ</b>\n"
                        f"Пара: <b>{symbol}</b>\n"
                        f"Направление: {side_text}\n"
                        f"Цена входа: <b>{price_fmt}</b>\n"
                        f"Количество: <b>{qty}</b>\n"
                        f"Тип: {order_type}\n"
                        f"🆔 Order ID: <code>{order_id}</code>"
                    )

                send_telegram(text)
                print(f"Сделка: {symbol} {side} {qty} @ {price}")

    except Exception as e:
        print(f"Ошибка обработки: {e} | Данные: {data}")

asyncio.run(connect())
