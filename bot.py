# gabagool_full_pro_2025.py
# လိုအပ်တာ: pip install websockets ecdsa requests python-dotenv hashlib

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

# ==================== CONFIG ====================
PRIVATE_KEY_HEX = os.getenv("PRIVATE_KEY")          # 64-char hex (0x မပါ)
API_KEY = os.getenv("API_KEY")                      # pk_...

MARKET = "0x8a03b8f1f7c3e7ae5e9f0a8b2b6930d5c6f9c1b8e8d8f8e8d8f8e8d8f8e8d8f"  # တကယ်ဈေးကွက် ID

TARGET_PAIR_COST = 0.982        # ဘယ်လောက်အထိ ညှစ်မယ်
MAX_EXPOSURE = 4000             # တစ်ဈေးကွက်မှာ အများဆုံး USD
MIN_PROFIT_TO_EXIT = 18         # အနည်းဆုံး ဒေါ်လာ ၁၈ အမြတ်ရရင် ချက်ချင်းထွက်
BASE_URL = "https://clob.polymarket.com"

# လက်ကျန်မှတ်တမ်း
qty_yes = qty_no = cost_yes = cost_no = 0.0

sk = SigningKey.from_string(bytes.fromhex(PRIVATE_KEY_HEX), curve=SECP256k1)
vk = sk.verifying_key

def get_pair_cost():
    if qty_yes + qty_no == 0: return 999
    return (cost_yes / qty_yes if qty_yes else 0) + (cost_no / qty_no if qty_no else 0)

def sign_order(order):
    msg = json.dumps(order, separators=(',', ':'), ensure_ascii=False).encode()
    msg_hash = hashlib.sha256(msg).digest()
    signature = sk.sign(msg_hash)
    return signature.hex()

async def place_order(side: str, price: float, amount: float):
    token_id = "97903176351431922708174589095785250720005603322548408400250303502737367801340" if side == "YES" else "107823720557377457341718799936440916152062911999998247062332407139732672032472"
    
    order = {
        "token_id": token_id,
        "price": f"{price:.4f}",
        "amount": f"{amount:.6f}",
        "side": "BUY",
        "market": MARKET,
        "api_key": API_KEY,
        "nonce": str(int(time.time() * 1000))
    }
    order["signature"] = sign_order(order)
    
    try:
        r = requests.post(f"{BASE_URL}/order", json=order, timeout=10)
        if r.status_code == 200:
            print(f"  SUCCESS: BUY {amount:.2f} {side} @ {price:.4f}")
            return True
        else:
            print(f"  FAILED: {r.text}")
            return False
    except Exception as e:
        print("Order error:", e)
        return False

async def cancel_and_exit():
    global qty_yes, qty_no, cost_yes, cost_no
    print("\nAUTO-EXIT စတင်နေသည်...")
    
    # အားလုံးကို market price နဲ့ sell back
    for side, qty in [("YES", qty_yes), ("NO", qty_no)]:
        if qty > 0.1:
            token_id = requests.get(f"{BASE_URL}/markets?market={MARKET}").json()["tokens"]
            token = next(t for t in token_id if t["outcome"] == side)
            sell_order = {
                "token_id": token["token_id"],
                "amount": f"{qty:.6f}",
                "side": "SELL",
                "market": MARKET,
                "api_key": API_KEY,
                "nonce": str(int(time.time() * 1000))
            }
            sell_order["signature"] = sign_order(sell_order)
            requests.post(f"{BASE_URL}/order", json=sell_order)
            print(f"  SOLD {qty:.2f} {side}")
    
    profit = min(qty_yes, qty_no) - (cost_yes + cost_no)
    print(f"FINAL LOCKED PROFIT: ${profit:.2f}")
    qty_yes = qty_no = cost_yes = cost_no = 0
    return profit

async def main():
    global qty_yes, qty_no, cost_yes, cost_no
    
    uri = "wss://clob.polymarket.com/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "method": "subscribe",
            "channel": "book",
            "market": MARKET
        }))
        
        print("Gabagool Pro Bot 2025 စတင်ပြီး! အမြတ်လော့ခ်ချဖို့ စောင့်နေသည်...")
        
        while True:
            try:
                msg = json.loads(await ws.recv())
                if "book" not in msg: continue
                
                asks = msg["book"]["asks"]
                yes_price = float(asks[0][0])  # YES ask
                no_price  = float(asks[1][0])  # NO ask
                
                pair_cost = get_pair_cost()
                exposure = cost_yes + cost_no
                locked = min(qty_yes, qty_no) - exposure
                
                print(f"\rYES {yes_price:.4f} | NO {no_price:.4f} | Pair {pair_cost:.4f} | Exp ${exposure:,.0f} | Lock ${locked:+.1f}", end="")
                
                # AUTO-EXIT
                if locked >= MIN_PROFIT_TO_EXIT:
                    await cancel_and_exit()
                    print("ထပ်စရန် Enter နှိပ်ပါ...")
                    input()
                    continue
                
                # AUTO-BUY logic
                if exposure >= MAX_EXPOSURE:
                    continue
                    
                for side, price in [("YES", yes_price), ("NO", no_price)]:
                    if exposure + 50 >= MAX_EXPOSURE: break
                        
                    test_amount = 400 / price
                    if side == "YES":
                        new_avg = (cost_yes + test_amount * price) / (qty_yes + test_amount) if qty_yes + test_amount > 0 else price
                        projected = new_avg + (cost_no / qty_no if qty_no else 0)
                    else:
                        new_avg = (cost_no + test_amount * price) / (qty_no + test_amount) if qty_no + test_amount > 0 else price
                        projected = new_avg + (cost_yes / qty_yes if qty_yes else 0)
                    
                    if projected < TARGET_PAIR_COST:
                        amount = min(800, (MAX_EXPOSURE - exposure) * 0.9) / price
                        amount = round(amount, 2)
                        
                        if await place_order(side, price, amount):
                            if side == "YES":
                                qty_yes += amount
                                cost_yes += amount * price
                            else:
                                qty_no += amount
                                cost_no += amount * price
                            print(f"  BOUGHT {amount:.1f} {side} @ {price:.4f} → Pair {get_pair_cost():.4f}")
                
                await asyncio.sleep(0.35)
                
            except Exception as e:
                print("Error:", e)
                await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
