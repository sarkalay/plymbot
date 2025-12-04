# gabagool_1dollar_test.py
import asyncio
import json
import time
import os
import hashlib
import websockets
import requests
from ecdsa import SigningKey, SECP256k1
from dotenv import load_dotenv

load_dotenv()

# ==================== $1 TEST CONFIG ====================
PRIVATE_KEY_HEX = os.getenv("PRIVATE_KEY")    # သင့် wallet ရဲ့ private key
API_KEY = os.getenv("API_KEY")                # Polymarket မှာ ဖန်တီးထားတဲ့ API key

# ဒီနေ့ တကယ်ရှိနေတဲ့ Bitcoin 15-min market (Dec 2025 အခုချိန်)
MARKET = "0x8e9b6942b4dac3117dadfacac2edb390b6d62d59c14152774bb5fcd983fc134e"   # တကယ့် condition_id
YES_TOKEN = "97903176351431922708174589095785250720005603322548408400250303502737367801340"
NO_TOKEN  = "107823720557377457341718799936440916152062911999998247062332407139732672032472"

# $1 စမ်းဖို့ ပဲ ထားထားတာ
MAX_EXPOSURE = 5.0               # အများဆုံး $5 ပဲ သုံးမယ်
TARGET_PAIR_COST = 0.985         # နည်းနည်းလျှော့ထားတာ (ပိုလွယ်အောင်)
MIN_PROFIT_TO_EXIT = 0.7         # 70 cents ရရင် ချက်ချင်းထွက်

qty_yes = qty_no = cost_yes = cost_no = 0.0

sk = SigningKey.from_string(bytes.fromhex(PRIVATE_KEY_HEX), curve=SECP256k1)

def get_pair_cost():
    if qty_yes + qty_no == 0: return 999
    return (cost_yes/qty_yes if qty_yes else 0) + (cost_no/qty_no if qty_no else 0)

def sign_order(order):
    msg = json.dumps(order, separators=(',',':')).encode()
    return sk.sign(hashlib.sha256(msg).digest()).hex()

async def place_order(side: str, price: float, usd_amount: float):
    token_id = YES_TOKEN if side == "YES" else NO_TOKEN
    amount = round(usd_amount / price, 6)

    order = {
        "token_id": token_id,
        "price": f"{price:.4f}",
        "amount": f"{amount}",
        "side": "BUY",
        "market": MARKET,
        "api_key": API_KEY,
        "nonce": str(int(time.time()*1000))
    }
    order["signature"] = sign_order(order)

    r = requests.post("https://clob.polymarket.com/order", json=order, timeout=10)
    if r.status_code == 200:
        print(f"  SUCCESS: {side} ${usd_amount} ဝယ်ပြီး")
        return amount
    else:
        print(f"  FAILED: {r.text[:100]}")
        return 0

async def main():
    global qty_yes, qty_no, cost_yes, cost_no

    uri = "wss://clob.polymarket.com/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"method":"subscribe","channel":"book","market":MARKET}))
        print("Bot စတင်ပြီး... $1 စမ်းနေသည်။ Ctrl+C နှိပ်ရင် ရပ်မယ်။")

        while True:
            msg = json.loads(await ws.recv())
            if "book" not in msg: continue
            asks = msg["book"]["asks"]
            yes_price = float(asks[0][0])
            no_price  = float(asks[1][0])

            pair = get_pair_cost()
            exposure = cost_yes + cost_no
            locked = min(qty_yes, qty_no) - exposure

            print(f"\rYES {yes_price:.3f} | NO {no_price:.3f} | Pair {pair:.3f} | Exp ${exposure:.2f} | Lock ${locked:+.2f}", end="")

            # အမြတ်ရပြီဆိုရင် ချက်ချင်းထွက်
            if locked >= MIN_PROFIT_TO_EXIT:
                print(f"\nSUCCESS: ${locked:.2f} အမြတ်ရပြီး! Bot ရပ်တယ်။")
                break

            if exposure >= MAX_EXPOSURE:
                continue

            # $1 ပဲ ဝယ်မယ်
            for side, price in [("YES", yes_price), ("NO", no_price)]:
                if exposure >= MAX_EXPOSURE: break

                # ဝယ်ရင် Pair Cost ဘယ်လောက်ဖြစ်မလဲ?
                test_usd = 1.0
                test_shares = test_usd / price
                if side == "YES":
                    new_avg = (cost_yes + test_usd) / (qty_yes + test_shares)
                    proj = new_avg + (cost_no/qty_no if qty_no else 0)
                else:
                    new_avg = (cost_no + test_usd) / (qty_no + test_shares)
                    proj = new_avg + (cost_yes/qty_yes if qty_yes else 0)

                if proj < TARGET_PAIR_COST:
                    shares = await place_order(side, price, 1.0)
                    if shares > 0:
                        if side == "YES":
                            qty_yes += shares; cost_yes += 1.0
                        else:
                            qty_no += shares; cost_no += 1.0

            await asyncio.sleep(0.5)

if __name__ == "__main__":
    asyncio.run(main())
