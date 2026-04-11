import telebot
from telebot import types
import json
import os
from telebot.types import ChatMemberAdministrator
from filelock import FileLock
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import threading



TOKEN = "8548769965:AAGiFT1QufOG4IBLgo0RjnRAMa0uM5ugCh8"
bot = telebot.TeleBot(TOKEN)
admins = [6302038392]  # Danh sách ID admin


# Hàm thêm người mời vào invited.json
def add_invited(user_id, referrer):
    """Thêm user vào danh sách mời (invited.json)."""
    lock = FileLock("invited.json.lock")
    with lock:
        invited = {}
        if os.path.exists("invited.json"):
            with open("invited.json", "r", encoding="utf-8") as f:
                invited = json.load(f)
        if user_id not in invited:
            invited[user_id] = referrer
            with open("invited.json", "w", encoding="utf-8") as f:
                json.dump(invited, f, indent=2)

# Hàm lấy và xoá người mời khỏi invited.json
def pop_referrer(user_id):
    """Lấy và xoá người mời khỏi danh sách (invited.json)."""
    lock = FileLock("invited.json.lock")
    with lock:
        if not os.path.exists("invited.json"):
            return None
        with open("invited.json", "r", encoding="utf-8") as f:
            invited = json.load(f)
        referrer = invited.pop(user_id, None)
        if referrer:
            with open("invited.json", "w", encoding="utf-8") as f:
                json.dump(invited, f, indent=2)
        return referrer

# Hàm cập nhật số dư người dùng trong userdata.json
def update_user_balance(user_id, new_balance):
    """Cập nhật số dư của người dùng trong file userdata.json."""
    lock = FileLock("userdata.json.lock")
    with lock:
        userdata = {}
        if os.path.exists("userdata.json"):
            with open("userdata.json", "r", encoding="utf-8") as f:
                userdata = json.load(f)
        userdata[user_id] = {"balance": new_balance}
        with open("userdata.json", "w", encoding="utf-8") as f:
            json.dump(userdata, f, indent=2)

# Hàm lấy số dư người dùng từ userdata.json
def get_user_balance(user_id):
    """Lấy số dư của người dùng từ file userdata.json."""
    if not os.path.exists("userdata.json"):
        return 0
    with open("userdata.json", "r", encoding="utf-8") as f:
        userdata = json.load(f)
    return userdata.get(user_id, {}).get("balance", 0)

# ==== TẠO FILE config.json NẾU CHƯA CÓ ====
def init_config():
    if not os.path.exists("config.json"):
        default_config = {
            "ref_bonus": 1,
            "min_rut": 1000
        }
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)

# ==== TẠO FILE invited.json NẾU CHƯA CÓ ====
def init_invited():
    if not os.path.exists("invited.json"):
        with open("invited.json", "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

admins = [6302038392]
# ==== GỌI NGAY KHI CHẠY ====
init_config()
init_invited()

def get_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)

def check_admin_channel(bot, channel_username):
    try:
        member = bot.get_chat_member(channel_username, bot.get_me().id)
        return isinstance(member, ChatMemberAdministrator)
    except Exception as e:
        print(f"Lỗi kiểm tra kênh {channel_username}: {e}")
        return False


# Tên file lưu dữ liệu
invited = {}
USER_FILE = "users.txt"
INVITED_FILE = "invited.json"
CHANNEL_FILE = "channels.txt"
CONFIG_PATH = "config.json"

def is_admins(user_id):
    try:
        with open('admins.txt', 'r') as f:
            admin_ids = [line.strip() for line in f.readlines()]
            return str(user_id) in admin_ids
    except FileNotFoundError:
        return False

with open("config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
    
with open("invited.json", "r", encoding="utf-8") as f:
    invited = json.load(f)

def is_banned(user_id):
    if not os.path.exists("ban_user.json"):
        return False
    with open("ban_user.json", "r") as f:
        banned = json.load(f)
    return str(user_id) in banned

def load_json(filename):
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            json.dump({}, f)
    with open(filename, "r") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

def load_channels():
    if not os.path.exists(CHANNEL_FILE):
        open(CHANNEL_FILE, "w").close()
    with open(CHANNEL_FILE, "r") as f:
        return [line.strip() for line in f if line.strip()]

def is_admin(user_id):
    if not os.path.exists("admins.txt"):
        return False
    with open("admins.txt", "r") as f:
        return str(user_id) in f.read().splitlines()
def is_admin(user_id):
    return (user_id) in admins


def save_config(data):
    with open("config.json", "w") as f:
        json.dump(data, f)

@bot.message_handler(commands=['doibot'])
def doi_token(message):
    user_id = str(message.from_user.id)

    # Kiểm tra quyền admin
    with open("admins.txt", "r") as f:
        admins = [line.strip() for line in f.readlines()]

    if user_id not in admins:
        bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")
        return

    try:
        # Lấy token mới từ nội dung tin nhắn
        parts = message.text.split(" ")
        if len(parts) != 2:
            bot.reply_to(message, "Vui lòng dùng đúng định dạng: /doibot api_TOKEN")
            return
        new_token = parts[1]

        # Cập nhật config.json
        import json
        with open("config.json", "r") as f:
            config = json.load(f)

        config["bot_token"] = new_token

        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)

        bot.reply_to(message, "✅ Đã cập nhật token mới. Đang khởi động lại bot...")

        # Khởi động lại bot (tuỳ môi trường)
        import os
        os.execl(sys.executable, sys.executable, *sys.argv)

    except Exception as e:
        bot.reply_to(message, f"Lỗi: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    from telebot import types
    user_id = str(message.from_user.id)
    args = message.text.split()

    # Lưu người dùng mới vào users.txt và tạo số dư ban đầu
    if not os.path.exists("users.txt"):
        open("users.txt", "w").close()
    with open("users.txt", "r") as f:
        users = f.read().splitlines()
    if user_id not in users:
        with open("users.txt", "a") as f:
            f.write(user_id + "\n")
        update_user_balance(user_id, 0)

        # Lưu người mời nếu có
        if len(args) > 1:
            referrer = args[1]
            if referrer != user_id:
                add_invited(user_id, referrer)

    # Gửi danh sách kênh cần tham gia
    channels = load_channels()
    if not channels:
        bot.send_message(message.chat.id, "Hiện tại chưa có kênh nào để tham gia.")
        return

    text = "🔍 Vui lòng vào tất cả các nhóm sau để sử dụng bot\n"
    for ch in channels:
        text += f"\n💠 {ch}"


    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("✅ Tôi đã tham gia", callback_data="check_join")
    markup.add(btn)
    bot.send_message(message.chat.id, text, reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "check_join")
def check_join(call):
    try:
        # Trả lời callback ngay để tránh lỗi timeout
        bot.answer_callback_query(call.id, text="⏳ Đang kiểm tra...")
    except Exception as e:
        print("Lỗi trả lời callback:", e)

    # Xử lý logic trong thread để không bị delay
    threading.Thread(target=check_join_logic, args=(call,)).start()

def check_join_logic(call):
    user_id = str(call.from_user.id)
    channels = load_channels()
    not_joined = []
    ref_bonus = get_config().get("ref_bonus", 1)

    # Kiểm tra user đã vào đủ kênh chưa
    for ch in channels:
        try:
            member = bot.get_chat_member(ch, int(user_id))
            if member.status in ['left', 'kicked']:
                not_joined.append(ch)
        except:
            not_joined.append(ch)

    if not_joined:
        msg = "❌ Bạn chưa tham gia các kênh sau:\n" + "\n".join(f"💠 {ch}" for ch in not_joined)
        bot.send_message(call.message.chat.id, msg)
        return

    # Người dùng đã tham gia đầy đủ kênh
    # Cộng thưởng cho người mời nếu có
    referrer = pop_referrer(user_id)
    if referrer:
        old_balance = get_user_balance(referrer)
        update_user_balance(referrer, old_balance + ref_bonus)
        try:
            bot.send_message(referrer, f"🎁 BẠN NHẬN {ref_bonus}đ TỪ LƯỢT GIỚI THIỆU {user_id}!")
        except:
            pass

    # Gửi menu chính
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True)
    menu.row("💰 Số dư của tôi")
    menu.row("🛒 Rút code", "📮MỜI BẠN BÈ")
    menu.row("📄 Link Game", "📊 Thống kê bot")
    bot.send_message(call.message.chat.id, "✅ Vui lòng thả cảm xúc!3 bài gần nhất để được ưu tiên @ChiaSeKinhNghiemGame!", reply_markup=menu)
    



@bot.message_handler(func=lambda message: message.text == "💰 Số dư của tôi")
def show_balance(message):
    if is_banned(message.from_user.id):
        return bot.reply_to(message, "Bạn đã bị cấm sử dụng bot.")

    user_id = str(message.from_user.id)
    balance = 0
    config = get_config()

    # Mặc định lấy balance = 0
    if os.path.exists("userdata.json"):
        with open("userdata.json", "r") as f:
            data = json.load(f)
        if user_id in data:
            balance = data[user_id].get("balance", 0)

    # Luôn gửi text, kể cả khi balance = 0
    text = f"""
💰 Số dư của bạn
─────
✨ Hiện tại: {balance} VND
👉 Mời bạn bè để nhận thêm ngẫu nhiên {config["ref_bonus"]} VND mỗi người!
"""
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.message_handler(commands=['napcode'])
def handle_themcode(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")

    msg = bot.reply_to(message, "Gửi tất cả code, mỗi dòng 1 code.")
    bot.register_next_step_handler(msg, save_codes)

def save_codes(message):
    codes = message.text.strip().splitlines()

    if not os.path.exists("codes.txt"):
        open("codes.txt", "w", encoding="utf-8").close()

    with open("codes.txt", "r", encoding="utf-8") as f:
        existing_codes = set(line.strip() for line in f if line.strip())

    new_codes = [code.strip() for code in codes if code.strip() and code.strip() not in existing_codes]

    if not new_codes:
        return bot.reply_to(message, "Không có code mới nào được thêm (tất cả đều trùng).")

    with open("codes.txt", "a", encoding="utf-8") as f:
        for code in new_codes:
            f.write(code + "\n")

    bot.reply_to(message, f"✅Đã thêm {len(new_codes)} code mới thành công!")

@bot.message_handler(commands=['themcode'])
def handle_themcode(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    lines = message.text.split('\n')
    
    if len(lines) < 2:
        return bot.reply_to(message, "Vui lòng gửi các code sau lệnh /themcode, mỗi code 1 dòng.")

    codes = [line.strip() for line in lines[1:] if line.strip()]

    if not os.path.exists("codes.txt"):
        open("codes.txt", "w", encoding="utf-8").close()

    with open("codes.txt", "r", encoding="utf-8") as f:
        existing_codes = set(line.strip() for line in f if line.strip())

    new_codes = [code for code in codes if code not in existing_codes]

    if not new_codes:
        return bot.reply_to(message, "Không có code mới nào được thêm (tất cả đều trùng).")

    with open("codes.txt", "a", encoding="utf-8") as f:
        for code in new_codes:
            f.write(code + "\n")

    bot.reply_to(message, f"Đã thêm {len(new_codes)} code mới.")

@bot.message_handler(commands=['rutcode'])
def rutcode_command(message):
    if is_banned(message.from_user.id):
       return bot.reply_to(message, "Bạn đã bị cấm sử dụng bot.")
    args = message.text.split()
    if len(args) < 3:
        return bot.reply_to(message, "Dùng: /rutcode <ghi_chú> <số_tiền>")

    note = args[1]
    try:
        amount = int(args[2])
    except:
        return bot.reply_to(message, "Số tiền không hợp lệ.")

    user_id = str(message.from_user.id)

    # Kiểm tra tham gia kênh
    channels = load_channels()
    not_joined = []
    for ch in channels:
        try:
            status = bot.get_chat_member(ch, message.from_user.id).status
            if status in ['left', 'kicked']:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    if not_joined:
        msg = "❌Bạn chưa tham gia đủ kiểm tra lại:\n"
        for ch in not_joined:
            msg += f"• {ch}\n"
        return bot.reply_to(message, msg)

    # Lấy số dư
    if not os.path.exists("userdata.json"):
        return bot.reply_to(message, "Không có dữ liệu số dư.")
    with open("userdata.json", "r", encoding="utf-8") as f:
        balances = json.load(f)

    if user_id not in balances:
        return bot.reply_to(message, "Bạn chưa có tài khoản số dư.")
    balance = balances[user_id]["balance"]

    # Kiểm tra min_rut
    config = get_config()
    min_rut = config.get("min_rut", 10000)

    if amount < min_rut:
        return bot.reply_to(message, f"Số tiền rút tối thiểu là {min_rut}đ.")
    if balance < amount:
        return bot.reply_to(message, f"Bạn không đủ số dư để rút {amount}đ.")

    # Rút code từ file
    if not os.path.exists("codes.txt"):
        return bot.reply_to(message, "Không tìm thấy file codes.txt.")
    with open("codes.txt", "r", encoding="utf-8") as f:
        codes = f.read().splitlines()
    if not codes:
        return bot.reply_to(message, "⚠️ Hiện tại không còn code nào.")

    code = codes.pop(0)
    with open("codes.txt", "w", encoding="utf-8") as f:
        for c in codes:
            f.write(c + "\n")

    # Trừ tiền
    balances[user_id]["balance"] -= amount
    with open("userdata.json", "w", encoding="utf-8") as f:
        json.dump(balances, f)

    # Ghi log
    log_entry = {"user_id": user_id, "amount": amount}
    if os.path.exists("log_rutcode.json"):
        with open("log_rutcode.json", "r", encoding="utf-8") as f:
            logs = json.load(f)
    else:
        logs = []
    logs.append(log_entry)
    with open("log_rutcode.json", "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2)

    # Gửi code cho người dùng
    bot.reply_to(message, f"📤 Rút Thành Công {note} \n\n 💵SỐ TIỀN: {amount} VNDD\n CODE: {code}")

    # Thông báo admin
    if os.path.exists("admins.txt"):
        with open("admins.txt", "r") as f:
            admin_ids = [line.strip() for line in f if line.strip()]
        for admin_id in admin_ids:
            try:
                bot.send_message(
                    int(admin_id),
                    f"Yêu cầu rút từ @{message.from_user.username} \n(🆔: {message.from_user.id})\n\n-TÊN NHÂN VẬT: {note}\n-Số tiền: {amount} VND.\n-CODE: {code}"
                )
            except:
                pass

@bot.message_handler(commands=['themadmin'])
def add_admin(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")
    
    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Dùng: /themadmin <user_id>")

    new_admin = args[1]

    if not os.path.exists("admins.txt"):
        open("admins.txt", "w").close()

    with open("admins.txt", "r") as f:
        admins = f.read().splitlines()

    if new_admin in admins:
        return bot.reply_to(message, "Người này đã là admin.")

    with open("admins.txt", "a") as f:
        f.write(new_admin + "\n")

    bot.reply_to(message, f"Đã thêm admin mới: {new_admin}")

@bot.message_handler(commands=['xoaadmin'])
def remove_admin(message):
    if not is_admin(message.from_user.id):
        return bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")

    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Dùng: /xoaadmin user_id")

    remove_id = args[1]

    if not os.path.exists("admins.txt"):
        return bot.reply_to(message, "Danh sách admin trống.")

    with open("admins.txt", "r") as f:
        admins = f.read().splitlines()

    if remove_id not in admins:
        return bot.reply_to(message, "Người này không phải admin.")

    admins.remove(remove_id)

    with open("admins.txt", "w") as f:
        for admin in admins:
            f.write(admin + "\n")

    bot.reply_to(message, f"Đã xoá admin: {remove_id}")

@bot.message_handler(commands=['themkenh'])
def add_channel(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Dùng: /themkenh @tenkenh")

    chat_id = args[1]
    channels = load_channels()

    if chat_id in channels:
        return bot.reply_to(message, "Kênh đã có trong danh sách.")

    channels.append(chat_id)
    with open("channels.txt", "w") as f:
        for ch in channels:
            f.write(ch + "\n")

    bot.reply_to(message, f"Đã thêm kênh: {chat_id}")

@bot.message_handler(commands=['xoakenh'])
def remove_channel(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Dùng: /xoakenh @tenkenh")

    chat_id = args[1]
    channels = load_channels()

    if chat_id not in channels:
        return bot.reply_to(message, "Không tìm thấy kênh trong danh sách.")

    channels.remove(chat_id)
    with open("channels.txt", "w") as f:
        for ch in channels:
            f.write(ch + "\n")

    bot.reply_to(message, f"Đã xoá kênh: {chat_id}")

@bot.message_handler(commands=['minrut'])
def set_min_rut_command(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Dùng: /minrut <số_tiền>")

    try:
        value = int(args[1])
        config = get_config()
        config["min_rut"] = value
        save_config(config)
        bot.reply_to(message, f"✅ Đã cập nhật min_rut = {value}đ")
    except:
        bot.reply_to(message, "Vui lòng nhập số hợp lệ.")

@bot.message_handler(commands=['thuongmoiban'])
def set_ref_bonus(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

    args = message.text.split()
    if len(args) < 2:
        return bot.reply_to(message, "Dùng: /thuongmoiban <số_tiền>")

    try:
        value = int(args[1])
        config = get_config()
        config["ref_bonus"] = value
        save_config(config)
        bot.reply_to(message, f"✅ Đã cập nhật tiền thưởng mời bạn = {value}đ")
    except:
        bot.reply_to(message, "Vui lòng nhập số hợp lệ.")

@bot.message_handler(commands=["dsadmin"])
def check_admins(message):
    user_id = str(message.from_user.id)

    try:
        with open("admins.txt", "r", encoding="utf-8") as f:
            lines = f.readlines()
            admins = [line.strip() for line in lines if line.strip()]

        if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
              return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

        if not admins:
            bot.reply_to(message, "Danh sách admin đang trống.")
            return

        msg = "✅<b>Danh sách admin:</b>\n"
        for admin_id in admins:
            msg += f"- <code>{admin_id}</code>\n"

        bot.reply_to(message, msg, parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"Lỗi khi đọc file admins.txt: {e}")

@bot.message_handler(func=lambda message: message.text == "📊 Thống kê bot")
def handle_thongke_button(message):
    if is_banned(message.from_user.id):
        return bot.reply_to(message, "Bạn đã bị cấm sử dụng bot.")
    # Tổng người dùng từ users.txt
    if os.path.exists("users.txt"):
        with open("users.txt", "r", encoding="utf-8") as f:
            users = [line.strip() for line in f if line.strip()]
        total_users = len(users)
    else:
        total_users = 0

    # Thống kê rút code
    total_rut = 0
    total_amount = 0
    if os.path.exists("log_rutcode.json"):
        with open("log_rutcode.json", "r", encoding="utf-8") as f:
            logs = json.load(f)
        total_rut = len(logs)
        total_amount = sum(log.get("amount", 0) for log in logs)

    # Gửi kết quả
    text = (
        f"📈<b> Thống kê bot</b>\n"
        f"─────\n"
        f"👥 Tổng số user: <b>{total_users}</b>\n"
        f"🔁 Tổng số lượt rút: <b>{total_rut}</b>\n"
        f"💸 Tổng tiền đã rút: <b>{total_amount}VND</b>"
    )
    bot.reply_to(message, text, parse_mode="HTML")

@bot.message_handler(commands=["naptien"])
def nap_tien(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    try:
        _, target_id, amount = message.text.strip().split()
        target_id = str(target_id)
        amount = int(amount)

        if not os.path.exists("userdata.json"):
            return bot.reply_to(message, "Không tìm thấy file userdata.json.")

        with open("userdata.json", "r", encoding="utf-8") as f:
            balances = json.load(f)

        if target_id not in balances:
            balances[target_id] = {"balance": 0}

        balances[target_id]["balance"] += amount

        with open("userdata.json", "w", encoding="utf-8") as f:
            json.dump(balances, f, ensure_ascii=False, indent=2)

        new_balance = balances[target_id]["balance"]
        bot.reply_to(message, f"✅ Đã nạp {amount}đ cho ID {target_id}.\nSố dư mới: {new_balance}đ")
    except Exception as e:
        bot.reply_to(message, f"Lỗi: {e}")

@bot.message_handler(commands=["trutien"])
def tru_tien(message):
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

    try:
        _, target_id, amount = message.text.strip().split()
        target_id = str(target_id)
        amount = int(amount)

        if not os.path.exists("userdata.json"):
            return bot.reply_to(message, "Không tìm thấy file userdata.json.")

        with open("userdata.json", "r", encoding="utf-8") as f:
            balances = json.load(f)

        if target_id not in balances:
            return bot.reply_to(message, "Người dùng chưa có tài khoản.")

        if balances[target_id]["balance"] < amount:
            return bot.reply_to(message, "Số dư người dùng không đủ để trừ.")

        balances[target_id]["balance"] -= amount

        with open("userdata.json", "w", encoding="utf-8") as f:
            json.dump(balances, f, ensure_ascii=False, indent=2)

        new_balance = balances[target_id]["balance"]
        bot.reply_to(message, f"✅ Đã trừ {amount}đ của ID {target_id}.\nSố dư mới: {new_balance}đ")
    except Exception as e:
        bot.reply_to(message, f"Lỗi: {e}")

@bot.message_handler(commands=["ban"])
def ban_user(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")
    
    args = message.text.strip().split()
    if len(args) != 2:
        return bot.reply_to(message, "Dùng đúng cú pháp: /ban <user_id>")

    ban_id = str(args[1])

    if not os.path.exists("ban_user.json"):
        with open("ban_user.json", "w") as f:
            json.dump([], f)

    with open("ban_user.json", "r") as f:
        banned = json.load(f)

    if ban_id in banned:
        return bot.reply_to(message, "Người dùng này đã bị ban trước đó.")

    banned.append(ban_id)
    with open("ban_user.json", "w") as f:
        json.dump(banned, f)

    bot.reply_to(message, f"Đã ban user ID {ban_id}.")

@bot.message_handler(commands=["unban"])
def unban_user(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

    args = message.text.strip().split()
    if len(args) != 2:
        return bot.reply_to(message, "Dùng đúng cú pháp: /unban <user_id>")

    unban_id = str(args[1])

    if not os.path.exists("ban_user.json"):
        return bot.reply_to(message, "Danh sách ban đang trống.")

    with open("ban_user.json", "r") as f:
        banned = json.load(f)

    if unban_id not in banned:
        return bot.reply_to(message, "ID này không nằm trong danh sách ban.")

    banned.remove(unban_id)
    with open("ban_user.json", "w") as f:
        json.dump(banned, f)

    bot.reply_to(message, f"✅ Đã gỡ ban người dùng ID {unban_id}.")

@bot.message_handler(commands=["linkanh"])
def set_invite_image(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "❗ Vui lòng nhập đúng cú pháp:\n/linkanh https://link_anh.jpg")

    image_url = args[1].strip()

    config = get_config()
    config["invite_image"] = image_url
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    bot.reply_to(message, f"✅ Đã cập nhật ảnh giới thiệu:\n{image_url}")

@bot.message_handler(func=lambda message: message.text == "📮MỜI BẠN BÈ")
def handle_invite_friends(message):
    if is_banned(message.from_user.id):
        return bot.reply_to(message, "Bạn đã bị cấm sử dụng bot.")
    
    config = get_config()
    user_id = message.from_user.id
    invite_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    invited_count = len(invited.get(str(user_id), []))

    caption = f"""
<b>🔍 LINK GIỚI THIỆU CỦA BẠN: </b> <code>{invite_link}</code>

<b>🔻 MỜI 1 BẠN = {config["ref_bonus"]} VNĐ</b>
<b>🤝 ĐIỂM TỐI THIỂU GIAO DỊCH: {config["min_rut"]} VNĐ</b>
"""

    # Nút chia sẻ xuất hiện ngay dưới tin nhắn
    share_text = f"Tham gia bot nhận quà: {invite_link}"
    share_url = f"https://t.me/share/url?url={invite_link}&text={share_text}"
    
    markup = types.InlineKeyboardMarkup()
    share_btn = types.InlineKeyboardButton("📤 Chia sẻ vào nhóm", url=share_url)
    markup.add(share_btn)

    invite_image = config.get("invite_image")
    if invite_image:
        bot.send_photo(message.chat.id, photo=invite_image, caption=caption, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, caption, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['checkadmin'])
def handle_check_admin(message):
    user_id = message.from_user.id

    if not os.path.exists("admins.txt") or str(user_id) not in [line.strip() for line in open("admins.txt")]:
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

    try:
        with open("channels.txt", "r", encoding="utf-8") as f:
            channels = [line.strip() for line in f if line.strip()]
    except:
        return bot.reply_to(message, "Không tìm thấy file channels.txt.")

    da_admin = []
    khong_admin = []

    for channel in channels:
        try:
            member = bot.get_chat_member(channel, bot.get_me().id)
            if member.status in ['administrator', 'creator']:
                da_admin.append(channel)
            else:
                khong_admin.append(channel)
        except:
            khong_admin.append(channel)

    msg = "<b>KẾT QUẢ KIỂM TRA ADMIN:</b>\n\n"
    if da_admin:
        msg += "✅<b>Kênh đã nâng admin:</b>\n" + "\n".join(da_admin) + "\n"
    if khong_admin:
        msg += "❌<b>Kênh chưa nâng admin:</b>\n" + "\n".join(khong_admin)

    bot.reply_to(message, msg, parse_mode="HTML")
    
@bot.message_handler(func=lambda message: message.text == "📄 Link Game")
def send_game_link(message):
    config = load_config()
    link = config.get("game_link", None)

    if link:
        text = f"""
🎮 *Link Game Chính Thức:*
[{link}]({link})
"""
        markup = InlineKeyboardMarkup()
        button = InlineKeyboardButton("🎮 VÔ NGAY", url=link)
        markup.add(button)

        bot.send_message(message.chat.id, text, parse_mode='Markdown', reply_markup=markup)
    else:
        bot.reply_to(message, "Hiện chưa có link game nào được cập nhật.")

CONFIG_PATH = "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


@bot.message_handler(commands=['uplink'])
def handle_uplink(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng.")

    try:
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            bot.reply_to(message, "Vui lòng nhập link game. Ví dụ:\n/uplink https://abc.com")
            return

        new_link = parts[1].strip()
        config = load_config()
        config["game_link"] = new_link
        save_config(config)

        bot.reply_to(message, f"Đã cập nhật link game:\n{new_link}")
    except Exception as e:
        bot.reply_to(message, f"Lỗi: {e}")


@bot.message_handler(commands=["menu"])
def send_admin_menu(message):
    from telebot import types
    user_id = str(message.from_user.id)

    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng menu admin.")

    markup = types.InlineKeyboardMarkup(row_width=2)

    # Nhóm: Quản lý kênh
    markup.add(
        types.InlineKeyboardButton("➕ /themkenh", callback_data="admin_themkenh"),
        types.InlineKeyboardButton("➖ /xoakenh", callback_data="admin_xoakenh")
    )

    # Nhóm: Admin
    markup.add(
        types.InlineKeyboardButton("👤 /themadmin", callback_data="admin_themadmin"),
        types.InlineKeyboardButton("❌ /xoaadmin", callback_data="admin_xoaadmin"),
        types.InlineKeyboardButton("📋 /dsadmin", callback_data="admin_dsadmin")
    )

    # Nhóm: Code
    markup.add(
        types.InlineKeyboardButton("➕ /themcode", callback_data="admin_themcode"),
        types.InlineKeyboardButton("🗑️ /xoacode", callback_data="admin_xoacode"),
        types.InlineKeyboardButton("🔥 /xoacodeall", callback_data="admin_xoacodeall"),
        types.InlineKeyboardButton("📄 /dscode", callback_data="admin_dscode"),
        types.InlineKeyboardButton("🔍 /checkcode", callback_data="admin_checkcode")
    )

    # Nhóm: Quản lý số dư
    markup.add(
        types.InlineKeyboardButton("➕ /naptien", callback_data="admin_naptien"),
        types.InlineKeyboardButton("➖ /trutien", callback_data="admin_trutien")
    )

    # Nhóm: Cài đặt hệ thống
    markup.add(
        types.InlineKeyboardButton("🎁 /thuongmoiban", callback_data="admin_thuongmoiban"),
        types.InlineKeyboardButton("💰 /minrut", callback_data="admin_minrut"),
        types.InlineKeyboardButton("🔗 /uplink", callback_data="admin_uplink")
    )

    # Nhóm: Ban user
    markup.add(
        types.InlineKeyboardButton("🚫 /ban", callback_data="admin_ban"),
        types.InlineKeyboardButton("✅ /unban", callback_data="admin_unban"),
        types.InlineKeyboardButton("📃 /dsban", callback_data="admin_dsban")
    )
    #tu bo sung
    markup.add(
        types.InlineKeyboardButton("/thongbao", callback_data="thong_bao"),
        types.InlineKeyboardButton("/chat", callback_data="chat_user")
    )

    bot.send_message(
        message.chat.id,
        "📋 <b>Menu quản trị:</b>\nChọn thao tác bên dưới:",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda message: message.text == "🛒 Rút code")
def send_user_count(message):
    if is_banned(message.from_user.id):
       return bot.reply_to(message, "Bạn đã bị cấm sử dụng bot.")
    bot.send_message(message.chat.id, f"Hướng Dẫn Thực Hiện:\n"
                                      f"─────\n"
                                      f"➡️/rutcode [ID TELE OR TNV]  [ SỐ TIỀN ]\n"
                                      f"VD  /rutcode xuanson 1000")

@bot.message_handler(commands=["dsban"])
def handle_dsban(message):
    user_id = str(message.from_user.id)

    # Kiểm tra quyền admin
    try:
        with open("admins.txt", "r") as f:
            admins = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        admins = []

    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    # Đọc danh sách bị ban
    try:
        with open("ban_user.json", "r", encoding="utf-8") as f:
            banned_users = json.load(f)
    except:
        banned_users = []

    if not banned_users:
        return bot.reply_to(message, "✅ Hiện tại không có ai bị ban.")

    ban_list = "\n".join([f"🔹 {uid}" for uid in banned_users])
    bot.reply_to(message, f"📛 Danh sách người dùng bị ban:\n\n {ban_list}")

                                   

@bot.message_handler(commands=['myid'])
def get_my_id(message):
    user_id = message.from_user.id
    bot.reply_to(message, f"🆔 ID Telegram của bạn là: <code>{user_id}</code>", parse_mode="HTML")
    
@bot.message_handler(commands=['dscode'])
def handle_xem_code(message):
    user_id = str(message.from_user.id)

    # Kiểm tra admin
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    if not os.path.exists("codes.txt"):
        return bot.reply_to(message, "⚠️ File codes.txt chưa tồn tại.")

    with open("codes.txt", "r", encoding="utf-8") as f:
        codes = [line.strip() for line in f if line.strip()]

    if not codes:
        return bot.reply_to(message, "✅ Danh sách code đang trống.")

    # Giới hạn độ dài nếu code quá nhiều
    if len("\n".join(codes)) > 4000:
        bot.reply_to(message, f"📄 Tổng số code: {len(codes)}\n(Danh sách quá dài, hãy kiểm tra file trực tiếp)")
    else:
        bot.reply_to(message, f"📄 Danh sách code:\n\n" + "\n".join(codes))

@bot.message_handler(commands=['xoacode'])
def handle_delete_code(message):
    user_id = str(message.from_user.id)
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "Vui lòng nhập mã code để xoá. Ví dụ: /xoacode ABC123")

    code_to_delete = args[1].strip()

    if not os.path.exists("codes.txt"):
        return bot.reply_to(message, "File codes.txt chưa tồn tại.")

    with open("codes.txt", "r", encoding="utf-8") as f:
        codes = [line.strip() for line in f if line.strip()]

    if code_to_delete not in codes:
        return bot.reply_to(message, "❌ Mã code không tồn tại.")

    codes.remove(code_to_delete)

    with open("codes.txt", "w", encoding="utf-8") as f:
        for code in codes:
            f.write(code + "\n")

    bot.reply_to(message, f"✅ Đã xoá mã code: <code>{code_to_delete}</code>", parse_mode="HTML")

@bot.message_handler(commands=['xoacodeall'])
def handle_delete_all_codes(message):
    user_id = str(message.from_user.id)

    # Kiểm tra quyền admin
    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    # Kiểm tra file codes.txt
    if not os.path.exists("codes.txt"):
        return bot.reply_to(message, "⚠️ File codes.txt chưa tồn tại.")

    with open("codes.txt", "r", encoding="utf-8") as f:
        codes = [line.strip() for line in f if line.strip()]

    if not codes:
        return bot.reply_to(message, "✅ Danh sách code đã trống.")

    # Xóa toàn bộ nội dung
    open("codes.txt", "w", encoding="utf-8").close()
    bot.reply_to(message, f"🗑️ Đã xóa toàn bộ {len(codes)} mã code.")

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def handle_admin_callback(call):
    command = call.data.replace("admin_", "")
    user_id = str(call.from_user.id)

    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.answer_callback_query(call.id, "Bạn không có quyền", show_alert=True)

    bot.answer_callback_query(call.id)

    commands_map = {
        "themkenh": "/themkenh @tenkenh",
        "xoakenh": "/xoakenh @tenkenh",
        "themadmin": "/themadmin user_id",
        "xoaadmin": "/xoaadmin user_id",
        "dsadmin": "/dsadmin",
        "themcode": "/themcode (gửi danh sách code)",
        "xoacode": "/xoacode MÃ_CODE",
        "xoacodeall": "/xoacodeall",
        "dscode": "/xemcode",
        "checkcode": "/checkcode",
        "naptien": "/naptien user_id số_tiền",
        "trutien": "/trutien user_id số_tiền",
        "thuongmoiban": "/thuongmoiban số_tiền",
        "minrut": "/minrut số_tiền",
        "uplink": "/uplink LINK",
        "ban": "/ban user_id",
        "unban": "/unban user_id",
        "dsban": "/dsban",
        "thong_bao": "/thongbao",
        "chat_user": "/chat"
    }

    if command in commands_map:
        bot.send_message(call.message.chat.id, f"✏️ Gõ lệnh: <code>{commands_map[command]}</code>", parse_mode="HTML")
    else:
        bot.send_message(call.message.chat.id, f"⚠️ Lệnh không xác định: /{command}")

@bot.message_handler(commands=['thongbao'])
def broadcast_message(message):
    user_id = str(message.from_user.id)
    admin_id = str(message.from_user.id)

    # Kiểm tra admin
    try:
        with open("admins.txt", "r") as f:
            admins = [line.strip() for line in f]
    except:
        admins = []

    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    args = message.text.split(" ", 1)
    if len(args) < 2:
        return bot.reply_to(message, "📢 Dùng: /thongbao nội_dung_thông_báo")

    content = args[1]

    # Đọc danh sách user
    try:
        with open("users.txt", "r") as f:
            users = [line.strip() for line in f if line.strip()]
    except:
        return bot.reply_to(message, "Không tìm thấy file users.txt.")

    success = 0
    fail = 0
    for uid in users:
        try:
            bot.send_message(uid, content)
            success += 1
        except:
            fail += 1
            continue

    bot.reply_to(message, f"✅ Đã gửi thông báo đến {success} người dùng.\n❌ Lỗi khi gửi đến {fail} người.")

@bot.message_handler(commands=["chat"])
def send_to_user(message):
    user_id = str(message.from_user.id)
    admin_id = str(message.from_user.id)

    # Kiểm tra admin
    try:
        with open("admins.txt", "r") as f:
            admins = [line.strip() for line in f]
    except:
        admins = []

    if not os.path.exists("admins.txt") or user_id not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    # Phân tích nội dung
    args = message.text.split(" ", 2)
    if len(args) < 3:
        return bot.reply_to(message, "❗ Dùng: /chat user_id nội_dung")

    user_id = args[1]
    content = args[2]

    try:
        bot.send_message(user_id, content)
        bot.reply_to(message, f"✅ Đã gửi tin nhắn đến {user_id}")
    except Exception as e:
        bot.reply_to(message, f"❌ Gửi thất bại: {e}")

@bot.message_handler(commands=['checkcode'])
def check_codes(message):
    user_id = message.from_user.id

    # Check if the user is an admin
    if not os.path.exists("admins.txt") or str(user_id) not in open("admins.txt").read():
        return bot.reply_to(message, "⛔️ Bạn không có quyền sử dụng lệnh này.")

    try:
        with open("codes.txt", "r") as f:
            codes = [line.strip() for line in f if line.strip()]
        total = len(codes)
        bot.reply_to(message, f"✅Tổng số code còn lại: {total}")
    except Exception as e:
        bot.reply_to(message, f"Lỗi khi kiểm tra code: {e}")


# Đọc danh sách user và admin
def get_users():
    try:
        with open('users.txt', 'r') as f:
            return [int(line.strip()) for line in f if line.strip()]
    except:
        return []

def get_admins():
    try:
        with open('admins.txt', 'r') as f:
            return [int(line.strip()) for line in f if line.strip()]
    except:
        return []

# Xử lý lệnh /thongbaofull
@bot.message_handler(commands=['thongbaofull'])
def handle_thongbao(message):
    if message.from_user.id not in get_admins():
        bot.reply_to(message, "Bạn không có quyền sử dụng lệnh này.")
        return
    msg = bot.reply_to(message, "Gửi ảnh kèm caption bạn muốn thông báo cho tất cả user:")
    bot.register_next_step_handler(msg, process_announcement)

# Xử lý ảnh kèm caption
def process_announcement(message):
    if not message.photo:
        bot.reply_to(message, "Vui lòng gửi 1 ảnh kèm caption.")
        return

    caption = message.caption or ""
    file_id = message.photo[-1].file_id
    users = get_users()

    success = 0
    failed = 0

    for uid in users:
        try:
            bot.send_photo(uid, file_id, caption)
            success += 1
        except:
            failed += 1

    bot.reply_to(message, f"Gửi thông báo hoàn tất.\n"
                          f"✅ Thành công: {success}\n"
                          f"❌ Thất bại: {failed}")



bot.infinity_polling(timeout=60, long_polling_timeout=1)

