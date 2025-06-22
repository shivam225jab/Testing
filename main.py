# main.py

import logging
import json
import os
import uuid
from functools import wraps
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "7731491024:AAGbDm-TIJ0C_S9CwOV0lrcMQ08Qb1eHW8Y")  # Recommended to use environment variables
ADMIN_IDS = [5924971946]  # <-- IMPORTANT: Replace with your Telegram User ID
DATA_FILE = "data.json"
CURRENCY_SYMBOL = "₹"
ITEMS_PER_PAGE = 5  # For pagination

# --- CONVERSATION STATES ---
# Using constants for states makes the code more readable
REDEEM_CODE_STATE, WITHDRAW_AMOUNT_STATE, WITHDRAW_UPI_STATE, ADMIN_ADD_CODE_VALUE, \
ADMIN_ADD_CODE_TEXT, ADMIN_ADD_LINK_URL, ADMIN_ADD_LINK_TITLE, ADMIN_EDIT_BALANCE_ID, \
ADMIN_EDIT_BALANCE_AMOUNT, ADMIN_REMOVE_USER_ID, ADMIN_SEND_MESSAGE_CONFIRM, \
ADMIN_SET_SUPPORT_INFO, ADMIN_SET_HOW_TO, ADMIN_ADD_ADMIN_ID, ADMIN_REMOVE_ADMIN_ID = range(16)

# --- LOGGING SETUP ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- DATA HANDLING ---
def load_data():
    """Loads data from JSON file. Returns a default structure if file doesn't exist."""
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Default structure
        return {
            "users": {},
            "codes": {},
            "links": [],
            "config": {
                "support_info": "No support info set.",
                "how_to_video": "No how-to video set.",
                "admins": ADMIN_IDS, # Initialize with hardcoded admin
            },
            "pending_withdrawals": {},
        }

def save_data(data):
    """Saves data to JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# Load data at startup
bot_data = load_data()


# --- DECORATORS (for security) ---
def admin_only(func):
    """Decorator to restrict a handler to admins."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in bot_data["config"]["admins"]:
            await update.callback_query.answer("Access Denied!", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped


# --- HELPER FUNCTIONS ---
def get_user_data(user_id):
    """Ensures a user entry exists and returns it."""
    user_id_str = str(user_id)
    if user_id_str not in bot_data["users"]:
        bot_data["users"][user_id_str] = {
            "balance": 0.0,
            "redeemed_codes": [],
            "pending_withdrawals": [],
            "withdrawal_history": [],
        }
    return bot_data["users"][user_id_str]

def build_menu(buttons, n_cols):
    """Builds an inline keyboard menu from a list of buttons."""
    return [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]

def back_button(menu_type="main"):
    """Returns a standard back button."""
    return InlineKeyboardButton("⬅️ Back", callback_data=f"back_to_{menu_type}")


# --- MAIN MENU and /start COMMAND ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command."""
    user = update.effective_user
    get_user_data(user.id) # Ensure user is in our database
    save_data(bot_data) # Save in case it's a new user

    if user.id in bot_data["config"]["admins"]:
        await show_admin_menu(update, context)
    else:
        await show_user_menu(update, context)

async def show_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, message_text=None) -> None:
    """Displays the main user menu."""
    user = update.effective_user
    welcome_message = message_text or (
        f"👋 Welcome, {user.first_name}!\n\n"
        "This is your Reward Bot. Use the buttons below to navigate."
    )
    
    keyboard = [
        InlineKeyboardButton("💰 Wallet", callback_data="user_wallet"),
        InlineKeyboardButton("🎯 Earn", callback_data="user_earn"),
        InlineKeyboardButton("🔑 Redeem Code", callback_data="user_redeem"),
        InlineKeyboardButton("💵 Withdraw", callback_data="user_withdraw"),
        InlineKeyboardButton("❌ Cancel Withdraw", callback_data="user_cancel_withdraw_list"),
        InlineKeyboardButton("🔍 Check Pending", callback_data="user_check_withdraw"),
        InlineKeyboardButton("🛠️ Get Support", callback_data="user_support"),
        InlineKeyboardButton("🎥 How to Use", callback_data="user_how_to"),
    ]

    reply_markup = InlineKeyboardMarkup(build_menu(keyboard, n_cols=2))
    
    if update.callback_query:
        await update.callback_query.edit_message_text(text=welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text=welcome_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --- USER FEATURE HANDLERS ---
async def wallet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows user's wallet balance."""
    query = update.callback_query
    await query.answer()
    user_id_str = str(query.from_user.id)
    user = get_user_data(user_id_str)
    
    text = (
        f"<b>💰 Your Wallet</b>\n\n"
        f"<b>Current Balance:</b> {CURRENCY_SYMBOL}{user['balance']:.2f}\n\n"
        f"Manage your earnings and withdrawals here."
    )
    reply_markup = InlineKeyboardMarkup([[back_button("main")]])
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def earn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays earning links."""
    query = update.callback_query
    await query.answer()
    
    if not bot_data["links"]:
        text = "🎯 <b>Earn Links</b>\n\nNo earning opportunities available right now. Please check back later!"
        reply_markup = InlineKeyboardMarkup([[back_button("main")]])
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return

    text = "🎯 <b>Earn Links</b>\n\nClick on a link below to complete the task and earn rewards:\n"
    keyboard = []
    for link in bot_data["links"]:
        keyboard.append([InlineKeyboardButton(link['title'], url=link['url'])])
    keyboard.append([back_button("main")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --- REDEEM CODE ---
async def redeem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🔑 <b>Redeem Code</b>\n\nPlease send the redeem code now."
    reply_markup = InlineKeyboardMarkup([[back_button("main")]])
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return REDEEM_CODE_STATE

async def redeem_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code_text = update.message.text.strip()
    
    if code_text not in bot_data["codes"]:
        await update.message.reply_text("❌ Invalid code. Please try again or go back.", reply_markup=InlineKeyboardMarkup([[back_button("main")]]))
        return REDEEM_CODE_STATE

    code_info = bot_data["codes"][code_text]
    if str(user_id) in code_info.get("used_by", []):
        await update.message.reply_text("❌ You have already used this code.", reply_markup=InlineKeyboardMarkup([[back_button("main")]]))
        return REDEEM_CODE_STATE

    user_data = get_user_data(user_id)
    amount = code_info["value"]
    user_data["balance"] += amount
    
    if "used_by" not in code_info:
        code_info["used_by"] = []
    code_info["used_by"].append(str(user_id))
    user_data["redeemed_codes"].append(code_text)
    
    save_data(bot_data)
    
    await update.message.reply_text(f"✅ Success! {CURRENCY_SYMBOL}{amount:.2f} has been added to your wallet.")
    await show_user_menu(update, context, message_text=f"✅ Code redeemed! Your new balance is {CURRENCY_SYMBOL}{user_data['balance']:.2f}")
    return ConversationHandler.END


# --- WITHDRAWAL PROCESS ---
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = get_user_data(query.from_user.id)
    if user_data["balance"] <= 0:
        await query.answer("You have no balance to withdraw.", show_alert=True)
        return ConversationHandler.END

    text = f"💵 <b>Withdraw Funds</b>\n\nYour balance is {CURRENCY_SYMBOL}{user_data['balance']:.2f}.\n\nPlease enter the amount you wish to withdraw."
    reply_markup = InlineKeyboardMarkup([[back_button("main")]])
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    return WITHDRAW_AMOUNT_STATE

async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a number.", reply_markup=InlineKeyboardMarkup([[back_button("main")]]))
        return WITHDRAW_AMOUNT_STATE
    
    user_data = get_user_data(update.effective_user.id)
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be positive.", reply_markup=InlineKeyboardMarkup([[back_button("main")]]))
        return WITHDRAW_AMOUNT_STATE
    if amount > user_data["balance"]:
        await update.message.reply_text(f"❌ Insufficient balance. You can withdraw up to {CURRENCY_SYMBOL}{user_data['balance']:.2f}.", reply_markup=InlineKeyboardMarkup([[back_button("main")]]))
        return WITHDRAW_AMOUNT_STATE

    context.user_data["withdraw_amount"] = amount
    await update.message.reply_text("Great. Now, please enter your UPI ID (e.g., yourname@okbank).")
    return WITHDRAW_UPI_STATE

async def withdraw_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    upi_id = update.message.text.strip()
    amount = context.user_data["withdraw_amount"]
    user_id_str = str(update.effective_user.id)
    user_data = get_user_data(user_id_str)
    
    # Deduct from balance
    user_data["balance"] -= amount
    
    # Create withdrawal request
    withdrawal_id = str(uuid.uuid4())
    request = {
        "id": withdrawal_id,
        "user_id": user_id_str,
        "amount": amount,
        "upi": upi_id,
        "timestamp": datetime.now().isoformat()
    }

    # Store in both central and user records
    bot_data["pending_withdrawals"][withdrawal_id] = request
    user_data["pending_withdrawals"].append(withdrawal_id)

    save_data(bot_data)
    
    await update.message.reply_text(f"✅ Withdrawal request for {CURRENCY_SYMBOL}{amount:.2f} to {upi_id} has been submitted. It will be processed soon.")
    await show_user_menu(update, context, message_text=f"✅ Withdrawal requested. Your new balance is {CURRENCY_SYMBOL}{user_data['balance']:.2f}")
    
    context.user_data.clear()
    return ConversationHandler.END


# --- CHECK & CANCEL WITHDRAWAL ---
async def list_pending_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE, for_cancellation=False):
    query = update.callback_query
    await query.answer()
    user_id_str = str(query.from_user.id)
    user_data = get_user_data(user_id_str)
    
    pending_ids = user_data.get("pending_withdrawals", [])
    
    if not pending_ids:
        title = "❌ Cancel Withdrawal" if for_cancellation else "🔍 Pending Withdrawals"
        text = f"<b>{title}</b>\n\nYou have no pending withdrawal requests."
        reply_markup = InlineKeyboardMarkup([[back_button("main")]])
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        return
        
    title = "❌ Select a withdrawal to cancel" if for_cancellation else "🔍 Your Pending Withdrawals"
    text = f"<b>{title}</b>\n\nHere are your current requests:\n"
    
    keyboard = []
    for w_id in pending_ids:
        # Check if the withdrawal still exists centrally
        if w_id in bot_data["pending_withdrawals"]:
            w_details = bot_data["pending_withdrawals"][w_id]
            button_text = f"{CURRENCY_SYMBOL}{w_details['amount']:.2f} to {w_details['upi']}"
            if for_cancellation:
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"user_cancel_withdraw_confirm_{w_id}")])
            else:
                 # In check mode, buttons aren't needed, but you could add details
                 text += f"\n- <b>ID:</b> ...{w_id[-6:]}\n  <b>Amount:</b> {CURRENCY_SYMBOL}{w_details['amount']:.2f}\n  <b>UPI:</b> {w_details['upi']}\n"
    
    if for_cancellation:
        keyboard.append([back_button("main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: # Just checking
        reply_markup = InlineKeyboardMarkup([[back_button("main")]])
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def cancel_withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refunds the amount and removes the withdrawal request."""
    query = update.callback_query
    await query.answer()
    user_id_str = str(query.from_user.id)
    w_id = query.data.split("_")[-1]

    if w_id not in bot_data["pending_withdrawals"]:
        await query.answer("This withdrawal request is already processed or invalid.", show_alert=True)
        return

    withdrawal_data = bot_data["pending_withdrawals"][w_id]
    
    # Security check: ensure the user owns this withdrawal
    if withdrawal_data["user_id"] != user_id_str:
        await query.answer("Error: Mismatch.", show_alert=True)
        return

    user_data = get_user_data(user_id_str)

    # Refund balance
    user_data["balance"] += withdrawal_data["amount"]

    # Remove from lists
    user_data["pending_withdrawals"].remove(w_id)
    del bot_data["pending_withdrawals"][w_id]

    save_data(bot_data)
    
    await query.edit_message_text(
        f"✅ Withdrawal of {CURRENCY_SYMBOL}{withdrawal_data['amount']:.2f} has been cancelled and refunded to your wallet.",
        reply_markup=InlineKeyboardMarkup([[back_button("main")]]),
        parse_mode=ParseMode.HTML
    )


# --- SUPPORT & HOW-TO ---
async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (f"<b>🛠️ Get Support</b>\n\n"
            f"For any help, please contact us:\n"
            f"{bot_data['config']['support_info']}")
    reply_markup = InlineKeyboardMarkup([[back_button("main")]])
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def how_to_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = f"🎥 <b>How to Use</b>\n\nWatch this video guide:\n{bot_data['config']['how_to_video']}"
    reply_markup = InlineKeyboardMarkup([[back_button("main")]])
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# =========================================================================================
# ================================= ADMIN SECTION =========================================
# =========================================================================================

async def show_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main admin menu."""
    text = "🛡️ <b>Admin Panel</b>\n\nWelcome, Admin! Manage the bot from here."
    keyboard = [
        InlineKeyboardButton("➕ Add Code", callback_data="admin_add_code"),
        InlineKeyboardButton("📎 Add Link", callback_data="admin_add_link"),
        InlineKeyboardButton("👁️ View Users", callback_data="admin_view_users_0"),
        InlineKeyboardButton("🧾 View Withdrawals", callback_data="admin_view_withdrawals_0"),
        InlineKeyboardButton("✏️ Edit Balance", callback_data="admin_edit_balance"),
        InlineKeyboardButton("🗑️ Remove User", callback_data="admin_remove_user"),
        InlineKeyboardButton("🗨️ Send Message", callback_data="admin_send_message"),
        InlineKeyboardButton("☎️ Set Support Info", callback_data="admin_set_support"),
        InlineKeyboardButton("🎬 Set How-to-Use", callback_data="admin_set_howto"),
        InlineKeyboardButton("🛂 Add Admin", callback_data="admin_add_admin"),
        InlineKeyboardButton("🚫 Remove Admin", callback_data="admin_remove_admin"),
        InlineKeyboardButton("⬅️ Back to User Menu", callback_data="back_to_main"),
    ]
    reply_markup = InlineKeyboardMarkup(build_menu(keyboard, n_cols=2))
    
    # Message could come from /start (no query) or a button press (query)
    if update.callback_query:
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else: # from /start
        await update.message.reply_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

@admin_only
async def admin_add_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🔢 Please enter the new redeem code text (e.g., WELCOME50)."
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup([[back_button("admin")]]))
    return ADMIN_ADD_CODE_TEXT

@admin_only
async def admin_add_code_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_text = update.message.text.strip()
    if code_text in bot_data["codes"]:
        await update.message.reply_text("This code already exists. Please choose a different one.", reply_markup=InlineKeyboardMarkup([[back_button("admin")]]))
        return ADMIN_ADD_CODE_TEXT
        
    context.user_data["new_code_text"] = code_text
    await update.message.reply_text(f"✅ Code text set to `{code_text}`.\n\nNow, please enter the value of this code in {CURRENCY_SYMBOL}.", parse_mode=ParseMode.MARKDOWN_V2)
    return ADMIN_ADD_CODE_VALUE

@admin_only
async def admin_add_code_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = float(update.message.text)
    except ValueError:
        await update.message.reply_text("Invalid value. Please enter a number.", reply_markup=InlineKeyboardMarkup([[back_button("admin")]]))
        return ADMIN_ADD_CODE_VALUE

    code_text = context.user_data["new_code_text"]
    bot_data["codes"][code_text] = {"value": value, "used_by": []}
    save_data(bot_data)
    
    context.user_data.clear()
    await update.message.reply_text(f"✅ Success! Code `{code_text}` with value {CURRENCY_SYMBOL}{value:.2f} has been created.", parse_mode=ParseMode.MARKDOWN_V2)
    await show_admin_menu(update, context)
    return ConversationHandler.END
    
@admin_only
async def admin_view_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    page = int(query.data.split("_")[-1])
    
    user_ids = list(bot_data["users"].keys())
    
    if not user_ids:
        text = "No users found."
        reply_markup = InlineKeyboardMarkup([[back_button("admin")]])
        await query.edit_message_text(text=text, reply_markup=reply_markup)
        return

    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    paginated_users = user_ids[start_index:end_index]
    
    text = "👁️ <b>Users List</b> (Page {}):\n\n".format(page + 1)
    for use