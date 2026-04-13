import os
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, Request
import uvicorn
import asyncio
from database import init_db, get_user, add_balance, update_user_info
from tinproxy_api import TinProxy

# --- CẤU HÌNH ---
BOT_TOKEN = "8774975242:AAGWZdhXiinSQPC-1b12MIBAsMZONEjVvts"
TIN_PROXY_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMDU1ODMxOTYyNzM1NzcxMTUxMDciLCJleHAiOjE3NzYxNDQ1MzUsImlhdCI6MTc3NjA1ODEzNX0.YFf449fPSbApxtNUKPUFqygV3i4oLxF1h1mPoPLBnzI"
SEPAY_API_KEY = "8EX4HZHKG6C17JMLLHTBKVNJC7GPUSVBVEYWAUQLWGR2R0BM6WOPDSO53MBQFWNX" # Dùng để verify webhook

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()
proxy_manager = TinProxy(TIN_PROXY_TOKEN)

# --- WEBHOOK SEPAY (Nạp tiền Auto) ---
@app.post("/sepay-webhook")
async def sepay_webhook(request: Request):
    data = await request.json()
    # Kiểm tra mã nạp tiền trong nội dung chuyển khoản (Ví dụ: NAP123456)
    content = data.get("content", "") 
    amount = int(data.get("amount", 0))
    
    # Giả sử cú pháp nạp là NAP + ID người dùng (VD: NAP5678901)
    if "NAP" in content.upper():
        try:
            user_id = int(content.upper().replace("NAP", "").strip())
            add_balance(user_id, amount)
            await bot.send_message(user_id, f"✅ Nạp tiền thành công!\n+ {amount:,} VNĐ vào tài khoản.")
            return {"status": "success"}
        except:
            pass
    return {"status": "failed"}

# --- BOT HANDLERS ---
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    init_db()
    balance = get_user(message.from_user.id)
    if not balance:
        add_balance(message.from_user.id, 0)
        balance = [0]
    
    text = (f"🌟 CHÀO MỪNG BẠN ĐẾN VỚI PROXY BOT\n\n"
            f"🆔 ID của bạn: `{message.from_user.id}`\n"
            f"💰 Số dư: {balance[0]:,} VNĐ\n\n"
            f"Nội dung nạp: `NAP{message.from_user.id}`")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Mua Proxy", callback_data="buy_menu")],
        [InlineKeyboardButton(text="💰 Nạp Tiền", callback_data="recharge")],
        [InlineKeyboardButton(text="👤 Tài Khoản", callback_data="account")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "buy_menu")
async def buy_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇻🇳 Proxy Tĩnh VN (4k/ngày)", callback_data="buy_vn_static")],
        [InlineKeyboardButton(text="🔄 Proxy Dân Cư Xoay (8k/ngày)", callback_data="buy_rotating")],
        [InlineKeyboardButton(text="🇺🇸 Proxy US (13.2k/tháng)", callback_data="buy_us")],
        [InlineKeyboardButton(text="⬅️ Quay lại", callback_data="back_home")]
    ])
    await call.message.edit_text("Chọn loại Proxy bạn muốn mua:", reply_markup=kb)

# Xử lý mua Proxy VN Tĩnh
@dp.callback_query(F.data == "buy_vn_static")
async def buy_vn_static(call: types.CallbackQuery):
    user_id = call.from_user.id
    balance = get_user(user_id)[0]
    price = 4000
    
    if balance < price:
        await call.answer("❌ Số dư không đủ! Vui lòng nạp thêm.", show_alert=True)
        return

    # Gọi API TinProxy (Ở đây bạn cần mapping đúng ID sản phẩm của TinProxy)
    result = proxy_manager.buy_proxy(service_id="vn_static_1day")
    
    if result.get("success"):
        add_balance(user_id, -price) # Trừ tiền
        proxy_info = result.get("proxy") # IP:PORT:USER:PASS
        await call.message.answer(f"✅ Mua thành công!\nProxy của bạn: `{proxy_info}`", parse_mode="Markdown")
    else:
        await call.message.answer("❌ Hệ thống TinProxy đang bảo trì hoặc hết hàng.")

# Chạy Bot song song với Webhook
async def main():
    # Chạy Webhook trên port Render cấp (mặc định 10000)
    config = uvicorn.Config(app, host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
    server = uvicorn.Server(config)
    
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
    
