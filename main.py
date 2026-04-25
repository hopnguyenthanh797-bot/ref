import os
import re
import math
import shutil
import zipfile
import asyncio
import aiofiles
import aiohttp
from datetime import datetime, timezone
from typing import Optional

# ==========================================
# FIX LỖI EVENT LOOP CỦA PYTHON TRÊN RENDER
# ==========================================
try:
    asyncio.get_running_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from fastapi import FastAPI, Request
import uvicorn

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneNumberBannedError

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.client.default import DefaultBotProperties

from config import config
from database import db
from api_trumsmm import trum_api

# ==========================================
# KHỞI TẠO HỆ THỐNG
# ==========================================
app = FastAPI()
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

ITEMS_PER_PAGE = 8

class AdminStates(StatesGroup):
    waiting_for_markup = State()
    waiting_for_guide = State()
    waiting_for_bank = State()
    waiting_for_search_user = State()
    waiting_for_add_money = State()
    waiting_for_deduct_money = State()
    waiting_for_broadcast = State()

# ==========================================
# HỆ THỐNG GIỮ BOT CHẠY 24/7 (ANTI-SLEEP)
# ==========================================
async def keep_alive_task():
    """Tự động Ping máy chủ mỗi 10 phút để Render không tắt Bot"""
    while True:
        await asyncio.sleep(600)  # Nghỉ 10 phút
        try:
            url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{config.PORT}")
            async with aiohttp.ClientSession() as session:
                await session.get(url)
                print(f"[24/7 KEEP ALIVE] Đã ping thành công: {url}")
        except Exception as e:
            print(f"[24/7 KEEP ALIVE] Lỗi ping: {e}")

# ==========================================
# CÁC HÀM BỔ TRỢ (HELPERS)
# ==========================================
def get_vip_info(total_deposit: int):
    tiers = [
        (0, "🌱 Member", 0, 500000),
        (500000, "🥉 VIP 1", 5, 2000000),
        (2000000, "🥈 VIP 2", 10, 10000000),
        (10000000, "🥇 VIP 3", 15, 50000000)
    ]
    current_tier = tiers[0]
    for tier in tiers:
        if total_deposit >= tier[0]:
            current_tier = tier
    
    rank_name, discount, next_target = current_tier[1], current_tier[2], current_tier[3]
    
    if total_deposit >= tiers[-1][3]:
        progress, bar, remain = 100, "██████████", 0
    else:
        progress = int((total_deposit / next_target) * 100)
        filled = int(progress / 10)
        bar = "█" * filled + "▒" * (10 - filled)
        remain = next_target - total_deposit
        
    return rank_name, discount, progress, bar, remain

def create_divider():
    return "━━━━━━━━━━━━━━━━━━━━━━"

async def extract_otp_from_messages(client: TelegramClient, chat_id: int = 777000) -> Optional[str]:
    """Fetch the recent otp code from telegram service notifications with Time Filter."""
    try:
        current_time = datetime.now(timezone.utc)
        
        # reverse=False gets the newest messages first
        messages = await client.get_messages(chat_id, limit=5, reverse=False)

        for message in messages:
            if message.text:
                # Regex tìm chuỗi 5 chữ số (bắt cả bản tiếng Anh lẫn tiếng Việt)
                match = re.search(r'\b(\d{5})\b', message.text)
                if match:
                    otp_code: str = match.group(1)
                    message_time = message.date
                    time_diff = (current_time - message_time).total_seconds()

                    # allow up to 180 seconds buffer (3 phút) để khách kịp thao tác
                    if 0 <= time_diff <= 180:
                        print(f"[✓] OTP Code Found: {otp_code}")
                        print(f"    Message Age: {int(time_diff)} seconds")
                        return otp_code
                    else:
                        print(f"[!] Bỏ qua mã cũ {otp_code} (Tuổi thọ: {int(time_diff)}s)")

        return None

    except Exception as e:
        print(f"[✗] Error extracting OTP: {str(e)}")
        return None

# ==========================================
# GIAO DIỆN CHÍNH & CÁ NHÂN TỐI ƯU
# ==========================================
async def get_main_menu_markup():
    settings = await db.get_settings()
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Sản Phẩm", callback_data="menu_categories"),
        InlineKeyboardButton(text="🏦 Nạp Tiền", callback_data="menu_deposit")
    )
    builder.row(
        InlineKeyboardButton(text="📚 Hướng Dẫn", url=settings['guide_link']),
        InlineKeyboardButton(text="👤 Cá Nhân", callback_data="menu_profile")
    )
    builder.row(
        InlineKeyboardButton(text="🌐 Ngôn ngữ", callback_data="ignore_btn"),
        InlineKeyboardButton(text="⚠️ Điều khoản", callback_data="ignore_btn")
    )
    if config.ADMIN_IDS:
        builder.row(InlineKeyboardButton(text="👑 Bảng Điều Khiển Admin 👑", callback_data="admin_panel"))
    return builder.as_markup()

async def render_home_text(user_id, full_name, balance):
    return (
        f"🌟 <b>HỆ THỐNG SHOP TELEGRAM TỰ ĐỘNG</b> 🌟\n"
        f"{create_divider()}\n"
        f"👋 Chào mừng: <b>{full_name}</b>\n"
        f"🆔 ID của bạn: <code>{user_id}</code>\n"
        f"💰 Số dư: <b>{balance:,} VNĐ</b>\n"
        f"{create_divider()}\n"
        f"💡 <i>Mẹo: Sau khi mua hàng, hãy <b>Forward file .zip</b> vào bot để hệ thống tự động giải nén và lấy OTP đăng nhập nhé!</i>"
    )

@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    user = await db.get_user(message.from_user.id, message.from_user.full_name)
    text = await render_home_text(user['user_id'], message.from_user.full_name, user['balance'])
    await message.answer(text, reply_markup=await get_main_menu_markup())

@dp.callback_query(F.data == "menu_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    text = await render_home_text(user['user_id'], call.from_user.full_name, user['balance'])
    await call.message.edit_text(text, reply_markup=await get_main_menu_markup())

@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    await call.answer()
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    rank, discount, progress, bar, remain = get_vip_info(user['total_deposit'])
    
    try:
        reg_date = datetime.fromisoformat(user['created_at'].replace("Z", "+00:00"))
        days_diff = (datetime.now(reg_date.tzinfo) - reg_date).days
        date_str = reg_date.strftime("%d.%m.%Y")
    except:
        date_str, days_diff = "N/A", 0

    items_bought = user['total_spent'] // 5000 if user['total_spent'] > 0 else 0

    text = (
        f"📌 <b>HỒ SƠ CÁ NHÂN</b>\n"
        f"{create_divider()}\n"
        f"🆔 ID: <code>{user['user_id']}</code>\n"
        f"👤 Tên: <b>{user['full_name']}</b>\n"
        f"💰 Số dư: <b>{user['balance']:,} VNĐ</b>\n\n"
        f"🏆 <b>Thông Tin Cấp Bậc</b>\n"
        f"🔸 Hạng: <b>{rank}</b> (Giảm {discount}%)\n"
        f"🔸 Tổng nạp: <b>{user['total_deposit']:,} VNĐ</b>\n"
        f"🔸 Tiến trình: {bar} <b>{progress}%</b>\n"
        f"<i>(Nạp thêm {remain:,}đ để thăng hạng)</i>\n\n"
        f"📊 <b>Thống Kê</b>\n"
        f"🛍 Đã mua: <b>{items_bought}</b> sản phẩm\n"
        f"💸 Đã tiêu: <b>{user['total_spent']:,} VNĐ</b>\n"
        f"📅 Tham gia: <b>{date_str}</b> ({days_diff} ngày trước)\n"
        f"{create_divider()}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏦 Nạp tiền", callback_data="menu_deposit"),
        InlineKeyboardButton(text="📜 Lịch sử mua", callback_data="menu_history")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại Trang Chủ", callback_data="menu_main"))
    await call.message.edit_text(text, reply_markup=builder.as_markup())

# ==========================================
# PHÂN LỚP DANH MỤC & SẢN PHẨM
# ==========================================
@dp.callback_query(F.data == "menu_categories")
async def show_categories(call: CallbackQuery):
    await call.answer("Đang đồng bộ dữ liệu...", show_alert=False)
    res = await trum_api.get_services()
    if not res.get("success"):
        return await call.message.edit_text("❌ Hệ thống đang bảo trì, vui lòng quay lại sau.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Quay lại", callback_data="menu_main")]]))
    
    builder = InlineKeyboardBuilder()
    for cat in res.get("data", []):
        total_stock = sum([p.get("stock", 0) for p in cat.get("positions", [])])
        if total_stock > 0:
            builder.row(InlineKeyboardButton(text=f"📁 {cat.get('category_name')} | (Kho: {total_stock})", callback_data=f"showcat_{cat.get('category_id')}_1"))
            
    builder.row(InlineKeyboardButton(text="⬅️ Quay lại Trang Chủ", callback_data="menu_main"))
    await call.message.edit_text(f"🛒 <b>DANH MỤC SẢN PHẨM</b>\n{create_divider()}\n<i>Vui lòng chọn danh mục bên dưới:</i>", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("showcat_"))
async def show_products_in_cat(call: CallbackQuery):
    await call.answer()
    parts = call.data.split("_")
    cat_id, page = int(parts[1]), int(parts[2])
    
    res = await trum_api.get_services()
    settings = await db.get_settings()
    markup_pct = settings['markup_percent']
    
    cat_name_display = "Sản Phẩm"
    active_products = []
    
    for cat in res.get("data", []):
        if cat.get("category_id") == cat_id:
            cat_name_display = cat.get("category_name")
            active_products = [p for p in cat.get("positions", []) if p.get("stock") > 0]
            break

    total_pages = max(1, math.ceil(len(active_products) / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * ITEMS_PER_PAGE
    current_page_products = active_products[start_idx:start_idx + ITEMS_PER_PAGE]

    builder = InlineKeyboardBuilder()
    for pos in current_page_products:
        original_price = pos.get("price")
        sell_price = int(original_price + (original_price * markup_pct / 100))
        btn_text = f"📦 {pos.get('position_name')} | {sell_price:,}đ | [{pos.get('stock')}]"
        builder.row(InlineKeyboardButton(text=btn_text, callback_data=f"buy_{pos.get('position_id')}_{sell_price}"))
    
    # Điều hướng
    nav_row = []
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Trước", callback_data=f"showcat_{cat_id}_{page-1}") if page > 1 else InlineKeyboardButton(text="➖", callback_data="ignore_btn"))
        nav_row.append(InlineKeyboardButton(text=f"Trang {page}/{total_pages}", callback_data="ignore_btn"))
        nav_row.append(InlineKeyboardButton(text="Sau ➡️", callback_data=f"showcat_{cat_id}_{page+1}") if page < total_pages else InlineKeyboardButton(text="➖", callback_data="ignore_btn"))
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="⬅️ Trở lại Danh Mục", callback_data="menu_categories"))
    await call.message.edit_text(f"🏷 <b>{cat_name_display.upper()}</b>\n{create_divider()}", reply_markup=builder.as_markup())

# ==========================================
# MUA HÀNG & LỊCH SỬ
# ==========================================
@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery):
    await call.answer("⏳ Hệ thống đang xử lý đơn hàng...", show_alert=False) 
    _, pos_id, sell_price = call.data.split("_")
    sell_price, pos_id = int(sell_price), int(pos_id)
    
    user = await db.get_user(call.from_user.id, call.from_user.full_name)
    _, discount, _, _, _ = get_vip_info(user['total_deposit'])
    final_price = int(sell_price - (sell_price * discount / 100))
    
    if user['balance'] < final_price:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="💳 Nạp Tiền Ngay", callback_data="menu_deposit"))
        builder.row(InlineKeyboardButton(text="⬅️ Chọn sản phẩm khác", callback_data="menu_categories"))
        return await call.message.edit_text(f"❌ <b>SỐ DƯ KHÔNG ĐỦ!</b>\n{create_divider()}\n💰 Yêu cầu: <b>{final_price:,}đ</b>\n💵 Hiện có: <b>{user['balance']:,}đ</b>", reply_markup=builder.as_markup())
    
    buy_res = await trum_api.buy_product(product_id=pos_id, quantity=1)
    
    if buy_res.get("success"):
        await db.update_balance(user['user_id'], -final_price)
        links = buy_res.get("download", [])
        if links:
            file_url = links[0]
            file_content = await trum_api.download_file(file_url)
            await db.add_order(user['user_id'], f"Product_{pos_id}", final_price, file_content if file_content else file_url)
            
            text = (
                f"✅ <b>GIAO DỊCH THÀNH CÔNG!</b>\n{create_divider()}\n"
                f"💸 Thanh toán: <b>{final_price:,} VNĐ</b>\n"
                f"📥 Dữ liệu của bạn đã sẵn sàng.\n\n"
                f"⚠️ <b>HƯỚNG DẪN TỰ ĐỘNG LẤY OTP:</b>\n"
                f"1. Tải file ZIP bên dưới về máy.\n"
                f"2. Chuyển tiếp (Forward) file đó lại vào bot này.\n"
                f"3. Bot sẽ tự động trích xuất OTP và mã 2FA.\n"
                f"{create_divider()}"
            )
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="📥 Tải File Tài Khoản (.ZIP)", url=file_url))
            builder.row(InlineKeyboardButton(text="⬅️ Quay lại Trang Chủ", callback_data="menu_main"))
            await call.message.edit_text(text, reply_markup=builder.as_markup())
    else:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Thử lại", callback_data="menu_categories"))
        await call.message.edit_text(f"❌ <b>LỖI TỪ NHÀ CUNG CẤP</b>\n{create_divider()}\n{buy_res.get('message')}\n<i>(Tiền của bạn được bảo toàn)</i>", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_history")
async def show_history(call: CallbackQuery):
    await call.answer()
    orders = await db.get_history(call.from_user.id)
    if not orders:
        text = "📭 <i>Bạn chưa có giao dịch nào.</i>"
    else:
        text = f"📜 <b>LỊCH SỬ 5 ĐƠN GẦN NHẤT</b>\n{create_divider()}\n"
        for od in orders:
            dt = datetime.fromisoformat(od['created_at'].replace("Z", "+00:00")).strftime("%d/%m %H:%M")
            text += f"📦 {od['product_name']} | <b>{od['price']:,}đ</b>\n"
            text += f"🗓 <i>{dt}</i>\n"
            short_data = od['resource_data'][:30] + "..." if len(od['resource_data']) > 30 else od['resource_data']
            text += f"🔑 <code>{short_data}</code>\n{create_divider()}\n"

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Trở về Hồ Sơ", callback_data="menu_profile"))
    await call.message.edit_text(text, reply_markup=builder.as_markup())

# ==========================================
# LUỒNG XỬ LÝ FILE ZIP VÀ LẤY OTP TỰ ĐỘNG
# ==========================================
@dp.message(F.document)
async def handle_zip_document(message: Message):
    if not message.document.file_name.endswith('.zip'):
        return
        
    loading_msg = await message.answer("🔄 <i>Đang tiếp nhận và giải nén dữ liệu, lọc rác tdata...</i>")
    
    file_id = message.document.file_id
    file_name = message.document.file_name
    user_id = message.from_user.id
    
    temp_dir = f"temp_{user_id}_{message.message_id}"
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = os.path.join(temp_dir, file_name)
    
    try:
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, zip_path)
        
        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
            
        session_files = []
        two_fa_code = "Không có"
        
        # Quét tìm file session Telethon và file 2FA.txt, bỏ qua các tdata vô dụng
        for root, _, files in os.walk(extract_dir):
            for f in files:
                if f.endswith('.session'):
                    session_files.append(os.path.join(root, f))
                # Tự động bắt pass 2FA (Bắt tên file chứa chữ 2fa)
                elif '2fa' in f.lower() and f.endswith('.txt'):
                    try:
                        with open(os.path.join(root, f), 'r', encoding='utf-8') as txt_file:
                            two_fa_code = txt_file.read().strip()
                    except:
                        pass
                    
        session_count = len(session_files)
        
        if session_count == 0:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return await loading_msg.edit_text("❌ Định dạng không hỗ trợ. Không tìm thấy file .session (Telethon SQLite) trong file ZIP này.")

        text = (
            f"✅ <b>TẢI LÊN THÀNH CÔNG</b>\n"
            f"{create_divider()}\n"
            f"📁 Thư mục: <code>{file_name.replace('.zip', '')}</code>\n"
            f"🚀 Số tài khoản: <b>{session_count}</b>\n"
            f"{create_divider()}\n"
            f"👇 <i>Chọn phiên làm việc bên dưới để truy xuất OTP:</i>"
        )
        
        builder = InlineKeyboardBuilder()
        safe_session_dir = f"sessions_data/{user_id}"
        os.makedirs(safe_session_dir, exist_ok=True)
        
        # Lưu pass 2FA chung vào thư mục của user này
        with open(os.path.join(safe_session_dir, "2fa_saved.txt"), "w", encoding="utf-8") as f:
            f.write(two_fa_code)
        
        for index, session_path in enumerate(session_files, start=1):
            phone_number = os.path.basename(session_path).replace('.session', '')
            safe_session_path = os.path.join(safe_session_dir, f"{phone_number}.session")
            
            shutil.copy(session_path, safe_session_path)
            builder.row(InlineKeyboardButton(text=f"{index}. {phone_number}", callback_data=f"info_sess_{phone_number}"))
            
        await loading_msg.delete()
        await message.answer(text, reply_markup=builder.as_markup())
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ Xử lý file thất bại: {str(e)}")
    finally:
        # Xóa rác tdata để nhẹ server
        shutil.rmtree(temp_dir, ignore_errors=True)

@dp.callback_query(F.data.startswith("info_sess_"))
async def session_info_handler(call: CallbackQuery):
    await call.answer()
    phone_number = call.data.replace("info_sess_", "")
    user_id = call.from_user.id
    
    two_fa_code = "Không có"
    safe_session_dir = f"sessions_data/{user_id}"
    try:
        with open(os.path.join(safe_session_dir, "2fa_saved.txt"), "r", encoding="utf-8") as f:
            two_fa_code = f.read().strip()
    except:
        pass
    
    text = (
        f"📱 <b>THÔNG TIN TÀI KHOẢN</b>\n"
        f"{create_divider()}\n"
        f"📞 <b>Phone :</b> <code>{phone_number}</code>\n"
        f"🔐 <b>2FA :</b> <code>{two_fa_code}</code>\n"
        f"{create_divider()}\n"
        f"⬇️ Hãy nhập SĐT trên vào app Telegram của bạn, sau đó ấn nút <b>[✅ Check]</b> để lấy mã OTP."
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Check (Lấy Mã OTP)", callback_data=f"getotp_{user_id}_{phone_number}"))
    await call.message.answer(text, reply_markup=builder.as_markup())

# ==========================================
# CỖ MÁY QUÉT OTP - NÂNG CẤP CHỐNG BAN (MÔ PHỎNG NGƯỜI DÙNG)
# ==========================================
@dp.callback_query(F.data.startswith("getotp_"))
async def check_otp_handler(call: CallbackQuery):
    await call.answer("Đang thâm nhập hệ thống Telegram lấy mã...", show_alert=False)
    _, user_id, phone_number = call.data.split("_")
    
    work_dir = f"sessions_data/{user_id}"
    full_session_path = os.path.join(work_dir, f"{phone_number}.session")
    
    if not os.path.exists(full_session_path):
        return await call.message.answer("❌ Dữ liệu phiên đã hết hạn hoặc bị xóa khỏi máy chủ.")

    # TẦNG BẢO MẬT 1 & 3: Giả lập Thiết bị xịn & Tắt nhận bản cập nhật ngầm
    client = TelegramClient(
        session=os.path.join(work_dir, phone_number),
        api_id=2040, 
        api_hash="b18441a1ff607e10a989891a5462e627",
        device_model="Samsung Galaxy S24 Ultra",  # Lừa Telegram đây là điện thoại
        system_version="Android 14.0",            # Hệ điều hành chuẩn
        app_version="10.14.5",                    # Phiên bản app tự nhiên
        lang_code="en",
        system_lang_code="en",
        receive_updates=False                     # Không online diện rộng
    )
    
    try:
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            return await call.message.answer("❌ Phiên đăng nhập không hợp lệ hoặc đã bị Telegram đăng xuất (Session Die).")
        
        # TẦNG BẢO MẬT 2: Giả lập độ trễ của con người (Tránh thao tác quá nhanh)
        await asyncio.sleep(2) 
            
        # Áp dụng siêu hàm chống trùng mã của sếp
        otp_code = await extract_otp_from_messages(client)
                    
        await client.disconnect()
        
        if otp_code:
            await call.message.answer(f"🎉 <b>THÀNH CÔNG!</b>\nMã đăng nhập Telegram của bạn là: <code>{otp_code}</code>")
        else:
            await call.message.answer("⚠️ <b>Chưa có mã gửi về hoặc mã đã cũ!</b>\nHãy chắc chắn bạn đã bấm 'Send Code as SMS' trên ứng dụng của bạn, chờ 5 giây và Check lại.")
            
    except PhoneNumberBannedError:
        await call.message.answer("❌ Tài khoản này đã bị Telegram BAN hoàn toàn (Banned).")
    except Exception as e:
        error_info = str(e)
        print(f"[TELETHON ERROR] {error_info}")
        await call.message.answer(f"❌ Có lỗi kỹ thuật xảy ra:\n<code>{error_info}</code>")
    finally:
        if client.is_connected():
            await client.disconnect()

# ==========================================
# NẠP TIỀN & SEPAY WEBHOOK
# ==========================================
@dp.callback_query(F.data == "menu_deposit")
async def show_deposit(call: CallbackQuery):
    await call.answer()
    settings = await db.get_settings()
    user_id = call.from_user.id
    text = (
        f"🏦 <b>CỔNG NẠP TIỀN TỰ ĐỘNG</b>\n"
        f"{create_divider()}\n"
        f"💳 Chuyển khoản đến:\n<b>{settings['bank_info']}</b>\n\n"
        f"📝 Nội dung CK: <code>NAP {user_id}</code>\n"
        f"<i>(Chạm vào nội dung để copy)</i>\n"
        f"{create_divider()}\n"
        f"⏳ <i>Hệ thống tự động cộng tiền trong 1-3 phút.</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Trở về Trang Chủ", callback_data="menu_main"))
    await call.message.edit_text(text, reply_markup=builder.as_markup())

@app.get("/")
async def root():
    return {"status": "success", "message": "Bot is running 24/7 on Render!"}

@app.post("/sepay-webhook")
async def sepay_webhook(request: Request):
    try:
        data = await request.json()
        amount = int(data.get("transferAmount", 0))
        content = data.get("content", "").upper()
        match = re.search(r'NAP\s*(\d+)', content)
        if match and amount > 0:
            user_id = int(match.group(1))
            new_bal = await db.update_balance(user_id, amount, is_deposit=True)
            try:
                await bot.send_message(user_id, f"🎉 <b>NẠP TIỀN THÀNH CÔNG!</b>\nBạn được cộng <b>{amount:,}đ</b>.\nSố dư: <b>{new_bal:,}đ</b>")
            except: pass
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==========================================
# BẢNG ĐIỀU KHIỂN ADMIN PRO MAX
# ==========================================
def get_cancel_button():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ Hủy thao tác", callback_data="admin_cancel"))
    return b.as_markup()

@dp.callback_query(F.data == "admin_cancel")
async def admin_cancel_action(call: CallbackQuery, state: FSMContext):
    await call.answer("Đã hủy thao tác!", show_alert=False)
    await state.clear()
    await admin_menu(call)

@dp.callback_query(F.data == "admin_panel")
async def admin_menu(call: CallbackQuery):
    if call.from_user.id not in config.ADMIN_IDS:
        return await call.answer("❌ Truy cập từ chối!", show_alert=True)
    await call.answer("Đang lấy thống kê...", show_alert=False)
    
    balance_res = await trum_api.get_balance()
    admin_balance = balance_res.get("balance", 0) if balance_res.get("success") else "Lỗi API"
    
    try:
        u_res = await asyncio.to_thread(lambda: db.client.table('users').select('user_id', count='exact').execute())
        total_users = u_res.count if u_res.count else 0
        r_res = await asyncio.to_thread(lambda: db.client.table('users').select('total_spent').execute())
        total_revenue = sum(item['total_spent'] for item in r_res.data) if r_res.data else 0
    except:
        total_users, total_revenue = 0, 0

    text = (
        f"👑 <b>BẢNG ĐIỀU KHIỂN QUẢN TRỊ</b>\n"
        f"{create_divider()}\n"
        f"🏦 Nguồn TrumSMM: <b>{admin_balance:,} đ</b>\n"
        f"👥 Tổng User: <b>{total_users}</b>\n"
        f"💸 Doanh Thu: <b>{total_revenue:,} đ</b>\n"
        f"{create_divider()}"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="👥 Quản Lý User", callback_data="admin_users"), InlineKeyboardButton(text="⚙️ Cài Đặt", callback_data="admin_settings"))
    b.row(InlineKeyboardButton(text="📢 Gửi Thông Báo", callback_data="admin_broadcast"), InlineKeyboardButton(text="🧹 Dọn Rác Server", callback_data="admin_cleanup"))
    b.row(InlineKeyboardButton(text="⬅️ Thoát Admin", callback_data="menu_main"))
    try: await call.message.edit_text(text, reply_markup=b.as_markup())
    except: pass

@dp.callback_query(F.data == "admin_cleanup")
async def admin_cleanup(call: CallbackQuery):
    shutil.rmtree("sessions_data", ignore_errors=True)
    await call.answer("Đã dọn dẹp toàn bộ dữ liệu Session rác trên Server!", show_alert=True)

@dp.callback_query(F.data == "admin_settings")
async def admin_settings_menu(call: CallbackQuery):
    await call.answer()
    s = await db.get_settings()
    text = (
        f"⚙️ <b>CÀI ĐẶT HỆ THỐNG</b>\n{create_divider()}\n"
        f"📈 Lãi suất: <b>{s['markup_percent']}%</b>\n"
        f"📚 HD: <code>{s['guide_link']}</code>\n"
        f"💳 Bank: <code>{s['bank_info']}</code>"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📈 Sửa Lãi Suất", callback_data="admin_set_markup"))
    b.row(InlineKeyboardButton(text="📚 Sửa HD", callback_data="admin_set_guide"), InlineKeyboardButton(text="💳 Sửa Bank", callback_data="admin_set_bank"))
    b.row(InlineKeyboardButton(text="⬅️ Quay Lại", callback_data="admin_panel"))
    await call.message.edit_text(text, reply_markup=b.as_markup())

@dp.callback_query(F.data.in_(["admin_set_markup", "admin_set_guide", "admin_set_bank"]))
async def ask_for_setting(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.data == "admin_set_markup":
        await call.message.edit_text("Nhập % lãi mới:", reply_markup=get_cancel_button())
        await state.set_state(AdminStates.waiting_for_markup)
    elif call.data == "admin_set_guide":
        await call.message.edit_text("Nhập Link HD:", reply_markup=get_cancel_button())
        await state.set_state(AdminStates.waiting_for_guide)
    elif call.data == "admin_set_bank":
        await call.message.edit_text("Nhập Bank mới:", reply_markup=get_cancel_button())
        await state.set_state(AdminStates.waiting_for_bank)

@dp.message(AdminStates.waiting_for_markup)
async def save_markup(message: Message, state: FSMContext):
    await db.update_setting("markup_percent", int(message.text))
    await message.answer("✅ Đã lưu lãi suất!")
    await state.clear()

@dp.message(AdminStates.waiting_for_guide)
async def save_guide(message: Message, state: FSMContext):
    await db.update_setting("guide_link", message.text)
    await message.answer("✅ Đã lưu HD!")
    await state.clear()

@dp.message(AdminStates.waiting_for_bank)
async def save_bank(message: Message, state: FSMContext):
    await db.update_setting("bank_info", message.text)
    await message.answer("✅ Đã lưu Bank!")
    await state.clear()

@dp.callback_query(F.data == "admin_users")
async def admin_users_menu(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("🔍 Nhập <b>UserID</b>:", reply_markup=get_cancel_button())
    await state.set_state(AdminStates.waiting_for_search_user)

@dp.message(AdminStates.waiting_for_search_user)
async def search_user_result(message: Message, state: FSMContext):
    user_id = int(message.text)
    res = await asyncio.to_thread(lambda: db.client.table('users').select('*').eq('user_id', user_id).execute())
    if not res.data: return await message.answer("❌ Không tìm thấy User!", reply_markup=get_cancel_button())
    user = res.data[0]
    rank, _, _, _, _ = get_vip_info(user['total_deposit'])
    
    text = (
        f"👤 <b>USER INFO</b>\n{create_divider()}\n"
        f"ID: <code>{user['user_id']}</code>\n"
        f"Tên: <b>{user['full_name']}</b> | Hạng: <b>{rank}</b>\n"
        f"Dư: <b>{user['balance']:,} đ</b>\n"
        f"Nạp: <b>{user['total_deposit']:,} đ</b> | Chi: <b>{user['total_spent']:,} đ</b>"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="➕ Cộng tiền", callback_data=f"addbal_{user_id}"), InlineKeyboardButton(text="➖ Trừ tiền", callback_data=f"deductbal_{user_id}"))
    b.row(InlineKeyboardButton(text="⬅️ Trở lại", callback_data="admin_panel"))
    await message.answer(text, reply_markup=b.as_markup())
    await state.clear()

@dp.callback_query(F.data.startswith("addbal_") | F.data.startswith("deductbal_"))
async def ask_balance_change(call: CallbackQuery, state: FSMContext):
    await call.answer()
    action, user_id = call.data.split("_")
    await state.update_data(target_user=user_id)
    await call.message.edit_text(f"Nhập số tiền {'CỘNG' if action=='addbal' else 'TRỪ'}:", reply_markup=get_cancel_button())
    await state.set_state(AdminStates.waiting_for_add_money if action=="addbal" else AdminStates.waiting_for_deduct_money)

@dp.message(AdminStates.waiting_for_add_money)
async def process_add_money(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id, amount = int(data['target_user']), int(message.text)
    new_bal = await db.update_balance(user_id, amount, is_deposit=True)
    await message.answer(f"✅ Xong. Dư mới: {new_bal:,}đ")
    try: await bot.send_message(user_id, f"🎉 Admin đã cộng {amount:,}đ!") 
    except: pass
    await state.clear()

@dp.message(AdminStates.waiting_for_deduct_money)
async def process_deduct_money(message: Message, state: FSMContext):
    data = await state.get_data()
    new_bal = await db.update_balance(int(data['target_user']), -int(message.text))
    await message.answer(f"✅ Xong. Dư mới: {new_bal:,}đ")
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def ask_broadcast_msg(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await call.message.edit_text("📢 Nhập nội dung thông báo:", reply_markup=get_cancel_button())
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def send_broadcast(message: Message, state: FSMContext):
    await message.answer("⏳ Đang gửi...")
    res = await asyncio.to_thread(lambda: db.client.table('users').select('user_id').limit(1000).execute())
    users = res.data if res.data else []
    ok, fail = 0, 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], f"📢 <b>THÔNG BÁO TỪ ADMIN:</b>\n\n{message.text}")
            ok += 1
            await asyncio.sleep(0.05)
        except: fail += 1
    await message.answer(f"✅ <b>Hoàn tất!</b> Thành công: {ok} | Lỗi (Block): {fail}")
    await state.clear()

@dp.callback_query(F.data == "ignore_btn")
async def ignore_callback(call: CallbackQuery):
    await call.answer("🛠 Tính năng đang được nâng cấp!", show_alert=False)

# ==========================================
# CHẠY HỆ THỐNG
# ==========================================
async def start_telegram_bot():
    print("🚀 Khởi động Bot Reseller MMO 24/7...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(start_telegram_bot())
    asyncio.create_task(keep_alive_task())

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, log_level="info")
