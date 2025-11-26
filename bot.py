import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, ConversationHandler
from database import Database
from config import BOT_TOKEN, ADMIN_ID

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
db = Database()

# Состояния для ConversationHandler
WAITING_FOR_WISHLIST = 1


def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь админом"""
    return user_id == ADMIN_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    
    if db.is_registered(user.id):
        await update.message.reply_text(
            f"Привет, {user.first_name}! Ты уже зарегистрирован в игре тайного санты! 🎅\n\n"
            "Используй /menu для доступа к меню."
        )
    else:
        db.add_user(user.id, user.username or '', user.first_name, user.last_name)
        await update.message.reply_text(
            f"Привет, {user.first_name}! 🎅\n\n"
            "Ты успешно зарегистрирован в игре тайного санты!\n"
            "Жди, пока админ раздаст роли.\n\n"
            "Используй /menu для доступа к меню."
        )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню"""
    user = update.effective_user
    
    if is_admin(user.id):
        # Админ-меню
        keyboard = [
            [InlineKeyboardButton("👤 Мой получатель", callback_data="my_receiver")],
            [InlineKeyboardButton("🎁 Мой вишлист", callback_data="my_wishlist")],
            [InlineKeyboardButton("✏️ Редактировать вишлист", callback_data="edit_wishlist")],
            [InlineKeyboardButton("📋 Список участников", callback_data="list_users")],
            [InlineKeyboardButton("🎲 Раздать роли", callback_data="distribute")],
            [InlineKeyboardButton("🚫 Управление исключениями", callback_data="manage_exclusions")],
            [InlineKeyboardButton("🗑 Удалить пользователя", callback_data="remove_user_menu")],
            [InlineKeyboardButton("📊 Текущие распределения", callback_data="view_assignments")],
        ]
    else:
        # Обычное меню
        keyboard = [
            [InlineKeyboardButton("👤 Мой получатель", callback_data="my_receiver")],
            [InlineKeyboardButton("🎁 Мой вишлист", callback_data="my_wishlist")],
            [InlineKeyboardButton("✏️ Редактировать вишлист", callback_data="edit_wishlist")],
            [InlineKeyboardButton("🚪 Выйти из игры", callback_data="leave_game")],
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите действие:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    if query.data == "list_users":
        await handle_list_users(query, user)
    elif query.data == "distribute":
        await handle_distribute(query, user, context)
    elif query.data == "manage_exclusions":
        await handle_manage_exclusions(query, user)
    elif query.data == "view_assignments":
        await handle_view_assignments(query, user)
    elif query.data == "my_receiver":
        await handle_my_receiver(query, user)
    elif query.data.startswith("add_exclusion_"):
        user_id = int(query.data.split("_")[-1])
        await handle_add_exclusion_menu(query, user, user_id)
    elif query.data.startswith("exclude_"):
        user1_id, user2_id = map(int, query.data.split("_")[1:])
        await handle_add_exclusion(query, user, user1_id, user2_id)
    elif query.data == "remove_exclusion_menu":
        await handle_remove_exclusion_menu(query, user)
    elif query.data.startswith("remove_exclusion_"):
        exclusion_id = int(query.data.split("_")[-1])
        await handle_remove_exclusion(query, user, exclusion_id)
    elif query.data == "back_to_menu":
        await handle_back_to_menu(query, user)
    elif query.data == "remove_user_menu":
        await handle_remove_user_menu(query, user)
    elif query.data.startswith("remove_user_"):
        user_id = int(query.data.split("_")[-1])
        await handle_remove_user(query, user, user_id)
    elif query.data == "leave_game":
        await handle_leave_game(query, user)
    elif query.data == "confirm_leave":
        await handle_confirm_leave(query, user)
    elif query.data == "my_wishlist":
        await handle_my_wishlist(query, user)
    # edit_wishlist обрабатывается через ConversationHandler


async def handle_list_users(query, user):
    """Показать список участников"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    users = db.get_all_users()
    if not users:
        await query.edit_message_text("📋 Пока нет зарегистрированных участников.")
        return
    
    text = "📋 Список участников:\n\n"
    for u in users:
        # Структура: user_id, username, first_name, last_name, registered_at, wishlist
        user_id, username, first_name, last_name, _, wishlist = u
        name = f"{first_name} {last_name or ''}".strip()
        text += f"• {name} (@{username or 'без username'})\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_distribute(query, user, context: ContextTypes.DEFAULT_TYPE):
    """Раздать роли"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    users = db.get_all_users()
    if len(users) < 2:
        await query.edit_message_text(
            "❌ Для распределения нужно минимум 2 участника!"
        )
        return
    
    # Очищаем предыдущие распределения
    db.clear_assignments()
    
    # Пытаемся распределить роли
    success, assignments = distribute_roles(users)
    
    if not success:
        await query.edit_message_text(
            "❌ Не удалось распределить роли с учетом всех исключений.\n"
            "Попробуйте изменить исключения или добавить больше участников."
        )
        return
    
    # Сохраняем распределения
    for giver_id, receiver_id in assignments:
        db.save_assignment(giver_id, receiver_id)
    
    # Отправляем сообщения участникам
    sent_count = 0
    failed_count = 0
    
    for giver_id, receiver_id in assignments:
        receiver = db.get_user(receiver_id)
        if receiver:
            # Структура: user_id, username, first_name, last_name, registered_at, wishlist
            _, _, receiver_name, receiver_last, _, wishlist = receiver
            receiver_full_name = f"{receiver_name} {receiver_last or ''}".strip()
            
            text = f"🎅 Тайный Санта!\n\n"
            text += f"Роли распределены! 🎲\n\n"
            text += f"Ты даришь подарок: {receiver_full_name} 🎁\n\n"
            
            # Добавляем вишлист, если он есть
            if wishlist:
                text += f"📝 Вишлист получателя:\n{wishlist}"
            else:
                text += "📝 Вишлист получателя не указан."
            
            try:
                await context.bot.send_message(
                    chat_id=giver_id,
                    text=text
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Не удалось отправить сообщение пользователю {giver_id}: {e}")
                failed_count += 1
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    result_text = f"✅ Роли успешно распределены!\n\n"
    result_text += f"📤 Сообщения отправлены: {sent_count} из {len(assignments)} участникам"
    if failed_count > 0:
        result_text += f"\n❌ Не удалось отправить: {failed_count}"
    
    await query.edit_message_text(result_text, reply_markup=reply_markup)


def distribute_roles(users, max_attempts=1000):
    """
    Распределить роли с учетом исключений.
    Использует алгоритм с перестановками.
    """
    user_ids = [u[0] for u in users]
    
    for attempt in range(max_attempts):
        # Перемешиваем список получателей
        receivers = user_ids.copy()
        random.shuffle(receivers)
        
        # Создаем пары (даритель -> получатель)
        assignments = list(zip(user_ids, receivers))
        
        # Проверяем, что никто не дарит сам себе
        if any(giver == receiver for giver, receiver in assignments):
            continue
        
        # Проверяем исключения
        valid = True
        for giver_id, receiver_id in assignments:
            if db.has_exclusion(giver_id, receiver_id):
                valid = False
                break
        
        if valid:
            return True, assignments
    
    return False, []


async def handle_manage_exclusions(query, user):
    """Управление исключениями"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    users = db.get_all_users()
    exclusions = db.get_exclusions()
    
    text = "🚫 Управление исключениями\n\n"
    text += "Текущие исключения:\n"
    
    if exclusions:
        for exc in exclusions:
            exc_id, user1_id, user2_id = exc
            user1 = db.get_user(user1_id)
            user2 = db.get_user(user2_id)
            if user1 and user2:
                name1 = f"{user1[2]} {user1[3] or ''}".strip()
                name2 = f"{user2[2]} {user2[3] or ''}".strip()
                text += f"• {name1} ↔ {name2}\n"
    else:
        text += "Нет исключений\n"
    
    text += "\nДобавить исключение:\n"
    text += "Выберите первого участника:"
    
    keyboard = []
    for u in users:
        # Структура: user_id, username, first_name, last_name, registered_at, wishlist
        user_id, username, first_name, last_name, _, wishlist = u
        name = f"{first_name} {last_name or ''}".strip()
        keyboard.append([InlineKeyboardButton(
            f"➕ {name}",
            callback_data=f"add_exclusion_{user_id}"
        )])
    
    # Добавляем кнопки для удаления исключений
    if exclusions:
        keyboard.append([InlineKeyboardButton("🗑 Удалить исключение", callback_data="remove_exclusion_menu")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_add_exclusion_menu(query, user, user1_id):
    """Меню выбора второго участника для исключения"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    users = db.get_all_users()
    user1 = db.get_user(user1_id)
    
    text = f"Выберите второго участника для исключения с {user1[2]}:\n"
    
    keyboard = []
    for u in users:
        user2_id, username, first_name, last_name, wishlist, _ = u
        if user2_id == user1_id:
            continue
        if db.has_exclusion(user1_id, user2_id):
            continue
        name = f"{first_name} {last_name or ''}".strip()
        keyboard.append([InlineKeyboardButton(
            f"🚫 {name}",
            callback_data=f"exclude_{user1_id}_{user2_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_exclusions")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_add_exclusion(query, user, user1_id, user2_id):
    """Добавить исключение"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    db.add_exclusion(user1_id, user2_id)
    user1 = db.get_user(user1_id)
    user2 = db.get_user(user2_id)
    name1 = f"{user1[2]} {user1[3] or ''}".strip()
    name2 = f"{user2[2]} {user2[3] or ''}".strip()
    
    await query.edit_message_text(
        f"✅ Исключение добавлено: {name1} ↔ {name2}"
    )
    # Возвращаемся к управлению исключениями
    await handle_manage_exclusions(query, user)


async def handle_remove_exclusion_menu(query, user):
    """Меню удаления исключений"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    exclusions = db.get_exclusions()
    
    if not exclusions:
        await query.edit_message_text("Нет исключений для удаления.")
        return
    
    text = "🗑 Выберите исключение для удаления:\n\n"
    
    keyboard = []
    for exc in exclusions:
        exc_id, user1_id, user2_id = exc
        user1 = db.get_user(user1_id)
        user2 = db.get_user(user2_id)
        if user1 and user2:
            name1 = f"{user1[2]} {user1[3] or ''}".strip()
            name2 = f"{user2[2]} {user2[3] or ''}".strip()
            keyboard.append([InlineKeyboardButton(
                f"🗑 {name1} ↔ {name2}",
                callback_data=f"remove_exclusion_{exc_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="manage_exclusions")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_remove_exclusion(query, user, exclusion_id):
    """Удалить исключение"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    exclusions = db.get_exclusions()
    exclusion = next((e for e in exclusions if e[0] == exclusion_id), None)
    
    if exclusion:
        _, user1_id, user2_id = exclusion
        db.remove_exclusion(user1_id, user2_id)
        await query.edit_message_text("✅ Исключение удалено.")
        # Возвращаемся к управлению исключениями
        await handle_manage_exclusions(query, user)
    else:
        await query.edit_message_text("❌ Исключение не найдено.")


async def handle_view_assignments(query, user):
    """Показать текущие распределения"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    assignments = db.get_all_assignments()
    
    if not assignments:
        text = "📊 Распределения еще не были созданы."
    else:
        text = "📊 Текущие распределения:\n\n"
        for ass in assignments:
            _, giver_id, receiver_id, _ = ass
            giver = db.get_user(giver_id)
            receiver = db.get_user(receiver_id)
            if giver and receiver:
                giver_name = f"{giver[2]} {giver[3] or ''}".strip()
                receiver_name = f"{receiver[2]} {receiver[3] or ''}".strip()
                text += f"🎁 {giver_name} → {receiver_name}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_my_receiver(query, user):
    """Показать, кому пользователь должен дарить"""
    receiver_id = db.get_assignment(user.id)
    
    if receiver_id is None:
        await query.edit_message_text(
            "⏳ Роли еще не были распределены. Ждите, пока админ раздаст роли."
        )
        return
    
    receiver = db.get_user(receiver_id)
    if receiver:
        # Структура: user_id, username, first_name, last_name, registered_at, wishlist
        _, _, receiver_name, receiver_last, _, wishlist = receiver
        receiver_full_name = f"{receiver_name} {receiver_last or ''}".strip()
        
        text = f"🎅 Тайный Санта!\n\n"
        text += f"Ты даришь подарок: {receiver_full_name} 🎁\n\n"
        
        # Добавляем вишлист, если он есть
        if wishlist:
            text += f"📝 Вишлист получателя:\n{wishlist}"
        else:
            text += "📝 Вишлист получателя не указан."
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await query.edit_message_text("❌ Получатель не найден.")


async def handle_back_to_menu(query, user):
    """Вернуться в меню"""
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("👤 Мой получатель", callback_data="my_receiver")],
            [InlineKeyboardButton("🎁 Мой вишлист", callback_data="my_wishlist")],
            [InlineKeyboardButton("✏️ Редактировать вишлист", callback_data="edit_wishlist")],
            [InlineKeyboardButton("📋 Список участников", callback_data="list_users")],
            [InlineKeyboardButton("🎲 Раздать роли", callback_data="distribute")],
            [InlineKeyboardButton("🚫 Управление исключениями", callback_data="manage_exclusions")],
            [InlineKeyboardButton("🗑 Удалить пользователя", callback_data="remove_user_menu")],
            [InlineKeyboardButton("📊 Текущие распределения", callback_data="view_assignments")],
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("👤 Мой получатель", callback_data="my_receiver")],
            [InlineKeyboardButton("🎁 Мой вишлист", callback_data="my_wishlist")],
            [InlineKeyboardButton("✏️ Редактировать вишлист", callback_data="edit_wishlist")],
            [InlineKeyboardButton("🚪 Выйти из игры", callback_data="leave_game")],
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите действие:", reply_markup=reply_markup)


async def handle_remove_user_menu(query, user):
    """Меню выбора пользователя для удаления"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    users = db.get_all_users()
    
    if not users:
        await query.edit_message_text("Нет пользователей для удаления.")
        return
    
    text = "🗑 Выберите пользователя для удаления:\n\n"
    text += "⚠️ Внимание: будут удалены все связанные данные (исключения, распределения)\n\n"
    
    keyboard = []
    for u in users:
        # Структура: user_id, username, first_name, last_name, registered_at, wishlist
        user_id, username, first_name, last_name, _, wishlist = u
        name = f"{first_name} {last_name or ''}".strip()
        # Не показываем админа в списке для удаления
        if user_id == ADMIN_ID:
            continue
        keyboard.append([InlineKeyboardButton(
            f"🗑 {name}",
            callback_data=f"remove_user_{user_id}"
        )])
    
    if not keyboard:
        await query.edit_message_text("Нет пользователей для удаления (кроме админа).")
        return
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_remove_user(query, user, user_id_to_remove):
    """Удалить пользователя"""
    if not is_admin(user.id):
        await query.edit_message_text("❌ У вас нет прав доступа.")
        return
    
    # Нельзя удалить админа
    if user_id_to_remove == ADMIN_ID:
        await query.edit_message_text("❌ Нельзя удалить администратора.")
        return
    
    user_to_remove = db.get_user(user_id_to_remove)
    if not user_to_remove:
        await query.edit_message_text("❌ Пользователь не найден.")
        return
    
    # Структура: user_id, username, first_name, last_name, registered_at, wishlist
    _, _, first_name, last_name, _, _ = user_to_remove
    name = f"{first_name} {last_name or ''}".strip()
    
    # Удаляем пользователя
    db.remove_user(user_id_to_remove)
    
    await query.edit_message_text(f"✅ Пользователь {name} успешно удален из игры.")
    
    # Возвращаемся в меню
    await handle_back_to_menu(query, user)


async def handle_leave_game(query, user):
    """Выход пользователя из игры"""
    if is_admin(user.id):
        await query.edit_message_text("❌ Администратор не может выйти из игры.")
        return
    
    if not db.is_registered(user.id):
        await query.edit_message_text("❌ Вы не зарегистрированы в игре.")
        return
    
    # Подтверждение выхода
    keyboard = [
        [InlineKeyboardButton("✅ Да, выйти", callback_data="confirm_leave")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "⚠️ Вы уверены, что хотите выйти из игры?\n\n"
        "Все ваши данные будут удалены (исключения, распределения).",
        reply_markup=reply_markup
    )


async def handle_confirm_leave(query, user):
    """Подтверждение выхода из игры"""
    if is_admin(user.id):
        await query.edit_message_text("❌ Администратор не может выйти из игры.")
        return
    
    if not db.is_registered(user.id):
        await query.edit_message_text("❌ Вы не зарегистрированы в игре.")
        return
    
    # Удаляем пользователя
    db.remove_user(user.id)
    
    await query.edit_message_text(
        "✅ Вы успешно вышли из игры.\n\n"
        "Используйте /start для повторной регистрации."
    )


async def handle_my_wishlist(query, user):
    """Показать вишлист пользователя"""
    wishlist = db.get_wishlist(user.id)
    
    text = "🎁 Мой вишлист:\n\n"
    if wishlist:
        text += wishlist
    else:
        text += "Вишлист еще не заполнен.\n\n"
        text += "Используйте кнопку '✏️ Редактировать вишлист' для добавления."
    
    keyboard = [
        [InlineKeyboardButton("✏️ Редактировать вишлист", callback_data="edit_wishlist")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def handle_edit_wishlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование вишлиста"""
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    
    current_wishlist = db.get_wishlist(user.id)
    
    text = "✏️ Редактирование вишлиста\n\n"
    if current_wishlist:
        text += f"Текущий вишлист:\n{current_wishlist}\n\n"
    
    text += "Отправьте новый вишлист текстовым сообщением.\n"
    text += "Или отправьте /cancel для отмены."
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="back_to_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)
    
    # Возвращаем состояние для ConversationHandler
    return WAITING_FOR_WISHLIST


async def receive_wishlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить вишлист от пользователя"""
    user = update.effective_user
    wishlist_text = update.message.text
    
    # Сохраняем вишлист
    db.update_wishlist(user.id, wishlist_text)
    
    # Проверяем, есть ли распределение и кто дарит подарок этому пользователю
    giver_id = db.get_giver_by_receiver(user.id)
    
    if giver_id:
        # Получаем информацию о пользователе, который обновил вишлист
        user_info = db.get_user(user.id)
        if user_info:
            _, _, first_name, last_name, _, _ = user_info
            user_full_name = f"{first_name} {last_name or ''}".strip()
            
            # Отправляем уведомление дарителю
            notification_text = f"🔔 Обновление вишлиста!\n\n"
            notification_text += f"Получатель {user_full_name} обновил свой вишлист:\n\n"
            notification_text += f"{wishlist_text}"
            
            try:
                await context.bot.send_message(
                    chat_id=giver_id,
                    text=notification_text
                )
                logger.info(f"Уведомление об обновлении вишлиста отправлено дарителю {giver_id}")
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление дарителю {giver_id}: {e}")
    
    await update.message.reply_text(
        "✅ Вишлист успешно обновлен!\n\n"
        f"Ваш вишлист:\n{wishlist_text}\n\n"
        "Используйте /menu для возврата в меню."
    )
    
    return ConversationHandler.END


async def cancel_wishlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменить редактирование вишлиста"""
    await update.message.reply_text("❌ Редактирование вишлиста отменено.")
    return ConversationHandler.END


def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Создайте файл .env и добавьте BOT_TOKEN=ваш_токен")
        return
    
    if ADMIN_ID == 0:
        logger.error("ADMIN_ID не установлен! Создайте файл .env и добавьте ADMIN_ID=ваш_telegram_id")
        return
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # ConversationHandler для редактирования вишлиста
    async def cancel_wishlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text("❌ Редактирование вишлиста отменено.")
        return ConversationHandler.END
    
    wishlist_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_edit_wishlist, pattern="^edit_wishlist$")],
        states={
            WAITING_FOR_WISHLIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_wishlist),
                CallbackQueryHandler(cancel_wishlist_callback, pattern="^back_to_menu$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_wishlist),
        ],
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(wishlist_handler)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    logger.info("Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()

