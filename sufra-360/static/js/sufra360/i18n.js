/**
 * SUFRA 360, in three languages.
 *
 * Every user-facing string in this application goes through T() — the HTML,
 * the panel, the booking drawer, the waitlist, the menu, validation, toasts
 * and the table-state words the 3D lamps are labelled with. Nothing is left
 * as a literal in a template string, because that is exactly how half a UI
 * ends up still in English after the language is switched.
 *
 * Server-side messages (a refused booking, a closed kitchen) arrive already
 * translated where SUFRA OS knows the guest's language; anything that comes
 * back as an English error code is mapped through ERRORS below.
 */

const KEY = 'sufra360-lang';
export const LANGS = ['en', 'az', 'ru'];

const DICT = {
  // ---------------------------------------------------------------- entry
  'entry.kicker': ['Waterfront · Live restaurant', 'Dəniz kənarı · Canlı restoran', 'Набережная · Живой ресторан'],
  'entry.sub': ['Three hundred and sixty degrees', 'Üç yüz altmış dərəcə', 'Триста шестьдесят градусов'],
  'entry.preparing': ['Preparing', 'Hazırlanır', 'Подготовка'],
  'entry.enter': ['Enter the restaurant', 'Restorana daxil ol', 'Войти в ресторан'],
  'entry.waking': ['Waking the restaurant…', 'Restoran oyanır…', 'Ресторан просыпается…'],

  // ------------------------------------------------------------------ hud
  'hud.live': ['Live restaurant', 'Canlı restoran', 'Живой ресторан'],
  'hud.tables': ['tables', 'masa', 'столов'],
  'hud.available': ['available', 'boş', 'свободно'],
  'hud.occupied': ['occupied', 'dolu', 'занято'],
  'hud.reserved': ['reserved', 'rezerv', 'забронировано'],
  'hud.guests': ['guests', 'qonaq', 'гостей'],
  'hud.load': ['load', 'yük', 'загрузка'],
  'hud.overview': ['Overview', 'Ümumi görünüş', 'Обзор'],
  'hud.diag': ['Diag', 'Diaqnostika', 'Диагн.'],
  'hud.reserve': ['Reserve', 'Rezerv et', 'Забронировать'],
  'hud.menu': ['Menu', 'Menyu', 'Меню'],
  'hud.ask': ['Ask AI', 'AI-dan soruş', 'Спросить AI'],
  'hud.about': ['About', 'Haqqında', 'О нас'],
  'zones.all': ['Whole room', 'Bütün zal', 'Весь зал'],
  'about.title': ['About us', 'Haqqımızda', 'О нас'],
  'about.hours': ['Opening hours', 'İş saatları', 'Часы работы'],
  'about.seating': ['We seat between {open} and {last}, closing at {close}.',
    'Qonaqları {open} ilə {last} arasında qəbul edirik, bağlanış {close}.',
    'Мы принимаем гостей с {open} до {last}, закрытие в {close}.'],
  'about.tables': ['{n} tables across {z} areas.', '{z} zonada {n} masa.',
    '{n} столов в {z} зонах.'],
  'about.contact': ['Contact', 'Əlaqə', 'Контакты'],
  'about.policy': ['Your table is held for {grace} minutes after the booked time.',
    'Masanız təsdiqlənmiş vaxtdan sonra {grace} dəqiqə saxlanılır.',
    'Ваш столик сохраняется {grace} минут после забронированного времени.'],
  'about.close': ['Close', 'Bağla', 'Закрыть'],
  'hud.scene': ['Scene', 'Səhnə', 'Сцена'],
  'hud.timeofday': ['Time of day', 'Günün vaxtı', 'Время суток'],
  'hud.auto': ['Auto', 'Avtomatik', 'Авто'],
  'hud.day': ['Day', 'Gündüz', 'День'],
  'hud.sunset': ['Sunset', 'Gün batımı', 'Закат'],
  'hud.night': ['Night', 'Gecə', 'Ночь'],
  'hud.weather': ['Weather', 'Hava', 'Погода'],
  'hud.quality': ['Quality', 'Keyfiyyət', 'Качество'],
  'hud.quality.note': ['Balanced keeps the look and drops the heavy passes.',
    'Balanslaşdırılmış görünüşü saxlayır, ağır effektləri söndürür.',
    'Сбалансированный режим сохраняет вид и отключает тяжёлые эффекты.'],
  'hud.connecting': ['connecting', 'qoşulur', 'подключение'],
  'hud.livelink': ['live', 'canlı', 'онлайн'],
  'hud.polling': ['polling', 'yoxlanır', 'опрос'],
  'hud.feedgone': ['restaurant unavailable', 'restoran əlçatan deyil', 'ресторан недоступен'],
  'hud.language': ['Language', 'Dil', 'Язык'],

  // ------------------------------------------------------------- service
  'service.lunch': ['Lunch service', 'Nahar servisi', 'Обеденный сервис'],
  'service.dinner': ['Dinner service', 'Şam servisi', 'Ужин'],
  'service.closed': ['Closed', 'Bağlıdır', 'Закрыто'],
  'service.livesuffix': ['Live', 'Canlı', 'Онлайн'],

  // --------------------------------------------------------- table states
  'state.AVAILABLE': ['Available', 'Boş', 'Свободен'],
  'state.OCCUPIED': ['Occupied', 'Dolu', 'Занят'],
  'state.RESERVED_SOON': ['Reserved soon', 'Tezliklə rezerv', 'Скоро бронь'],
  'state.RESERVED': ['Unavailable', 'Əlçatmaz', 'Недоступен'],
  'state.HELD': ['Being booked', 'Rezerv edilir', 'Бронируется'],
  'state.HELD_BY_YOU': ['Held for you', 'Sizin üçün saxlanılır', 'Удержан для вас'],
  'state.LATE': ['Guest late', 'Qonaq gecikir', 'Гость опаздывает'],
  'state.CLEANING': ['Being cleared', 'Təmizlənir', 'Убирается'],
  'state.BLOCKED': ['Out of service', 'İstifadədə deyil', 'Не используется'],
  'state.INCOMPATIBLE': ['Wrong size', 'Ölçü uyğun deyil', 'Не тот размер'],
  'state.PAST': ['Time has passed', 'Vaxt keçib', 'Время прошло'],
  'state.CLOSED': ['Not seating then', 'O vaxt qəbul yoxdur', 'В это время не сажаем'],
  'state.UNKNOWN': ['—', '—', '—'],

  // ------------------------------------------------------- availability bar
  'av.title': ['Check availability', 'Boş yerləri yoxla', 'Проверить доступность'],
  'av.date': ['Date', 'Tarix', 'Дата'],
  'av.time': ['Time', 'Saat', 'Время'],
  'av.guests': ['Guests', 'Qonaq', 'Гостей'],
  'av.check': ['Show tables', 'Masaları göstər', 'Показать столы'],
  'av.live': ['Live view', 'Canlı görünüş', 'Живой вид'],
  'av.showing': ['Availability for {date} at {time} · {party} guests',
    '{date}, saat {time} · {party} qonaq üçün boş yerlər',
    'Доступность на {date} в {time} · {party} гостей'],
  'av.livenow': ['Showing the restaurant right now', 'Restoran indi belədir',
    'Ресторан прямо сейчас'],
  'av.count': ['{n} tables available', '{n} masa boşdur', 'Свободно столов: {n}'],
  'av.none': ['No tables free for that slot. You can join the waitlist.',
    'Bu vaxt üçün boş masa yoxdur. Gözləmə siyahısına yazıla bilərsiniz.',
    'На это время свободных столов нет. Можно записаться в лист ожидания.'],
  'av.past': ['That time has already passed. Please choose a later time.',
    'Bu vaxt artıq keçib. Zəhmət olmasa, daha gec bir vaxt seçin.',
    'Это время уже прошло. Пожалуйста, выберите более позднее время.'],
  'av.closed': ['We are not seating at that time.', 'Bu vaxt qonaq qəbul etmirik.',
    'В это время мы не принимаем гостей.'],

  // --------------------------------------------------------------- panel
  'panel.table': ['Table {n}', 'Masa {n}', 'Стол {n}'],
  'panel.setting': ['Setting', 'Şərait', 'Обстановка'],
  'panel.atmosphere': ['Atmosphere', 'Atmosfer', 'Атмосфера'],
  'panel.suits': ['Suits', 'Uyğundur', 'Подходит'],
  'panel.quiet': ['Quiet', 'Sakit', 'Тишина'],
  'panel.view': ['View', 'Mənzərə', 'Вид'],
  'panel.privacy': ['Privacy', 'Məxfilik', 'Приватность'],
  'panel.romantic': ['Romantic', 'Romantik', 'Романтика'],
  'panel.seats': ['Seats', 'Yerlər', 'Мест'],
  'panel.seatsval': ['{v} guests', '{v} qonaq', '{v} гостей'],
  'panel.frombar': ['From the bar', 'Bardan', 'От бара'],
  'panel.fromkitchen': ['From the kitchen', 'Mətbəxdən', 'От кухни'],
  'panel.towater': ['To the water', 'Suya qədər', 'До воды'],
  'panel.guestsnow': ['Guests', 'Qonaqlar', 'Гости'],
  'panel.seatedat': ['Seated', 'Oturub', 'Посажены'],
  'panel.elapsed': ['Elapsed', 'Keçən vaxt', 'Прошло'],
  'panel.arriving': ['Arriving', 'Gəlir', 'Прибытие'],
  'panel.arrivingval': ['{time} · {n} guests', '{time} · {n} qonaq', '{time} · {n} гостей'],
  'panel.reserve': ['Reserve this table', 'Bu masanı rezerv et', 'Забронировать этот стол'],
  'panel.waitlist': ['Join the waitlist', 'Gözləmə siyahısına yazıl', 'Записаться в лист ожидания'],
  'panel.askabout': ['Ask about this table', 'Bu masa haqqında soruş', 'Спросить об этом столе'],
  'panel.nextfree': ['Next free at {time}', 'Növbəti boş vaxt {time}', 'Освободится в {time}'],
  'panel.freeallevening': ['Free all evening', 'Bütün axşam boşdur', 'Свободен весь вечер'],
  'panel.freeuntil': ['Free until {time}', '{time}-a qədər boşdur', 'Свободен до {time}'],
  'panel.allround': ['A solid all-round table.', 'Hər məqsəd üçün yaxşı masa.',
    'Хороший стол на любой случай.'],
  'panel.bestfor': ['Best for {list}.', 'Ən uyğun: {list}.', 'Лучше всего для: {list}.'],
  'panel.close': ['Close', 'Bağla', 'Закрыть'],
  'panel.unavailablefor': ['Not available for {date} at {time}',
    '{date}, saat {time} üçün əlçatan deyil', 'Недоступен {date} в {time}'],

  // ------------------------------------------------------------- booking
  'bk.head': ['Reserve table {n}', '{n} nömrəli masanı rezerv et', 'Бронирование стола {n}'],
  'bk.step1': ['Step 1 of 2', 'Addım 1 / 2', 'Шаг 1 из 2'],
  'bk.step2': ['Step 2 of 2', 'Addım 2 / 2', 'Шаг 2 из 2'],
  'bk.date': ['Date', 'Tarix', 'Дата'],
  'bk.time': ['Time', 'Saat', 'Время'],
  'bk.guests': ['Guests', 'Qonaqlar', 'Гости'],
  'bk.occasion': ['Occasion', 'Münasibət', 'Повод'],
  'bk.occasion.none': ['None', 'Yoxdur', 'Нет'],
  'bk.occasion.birthday': ['Birthday', 'Ad günü', 'День рождения'],
  'bk.occasion.anniversary': ['Anniversary', 'İldönümü', 'Годовщина'],
  'bk.occasion.business': ['Business', 'İş görüşü', 'Деловой ужин'],
  'bk.occasion.celebration': ['Celebration', 'Qeyd', 'Праздник'],
  'bk.occasion.date': ['Date night', 'Romantik görüş', 'Свидание'],
  'bk.occasion.family': ['Family meal', 'Ailə yeməyi', 'Семейный ужин'],
  'bk.pref': ['Preference', 'Üstünlük', 'Пожелание'],
  'bk.pref.ph': ['e.g. away from the door', 'məsələn, qapıdan uzaq', 'например, подальше от двери'],
  'bk.next': ['Hold this table & continue', 'Masanı saxla və davam et', 'Удержать стол и продолжить'],
  'bk.holdnote': ['We hold it for {min} minutes while you finish.',
    'Siz doldurduğunuz müddətdə masanı {min} dəqiqə saxlayırıq.',
    'Мы удерживаем стол {min} минут, пока вы заполняете форму.'],
  'bk.holding': ['Holding table {n}…', '{n} nömrəli masa saxlanılır…', 'Удерживаем стол {n}…'],
  'bk.notfree': ['Table {n} is not free at {time}.', '{n} nömrəli masa saat {time}-də boş deyil.',
    'Стол {n} не свободен в {time}.'],
  'bk.askalt': ['Ask for an alternative', 'Alternativ təklif et', 'Предложить альтернативу'],
  'bk.almost': ['Almost done', 'Az qaldı', 'Почти готово'],
  'bk.summary': ['Table {n} · {date} at {time} · {party} guests',
    'Masa {n} · {date}, saat {time} · {party} qonaq',
    'Стол {n} · {date} в {time} · {party} гостей'],
  'bk.first': ['First name', 'Ad', 'Имя'],
  'bk.last': ['Last name', 'Soyad', 'Фамилия'],
  'bk.email': ['Email', 'E-poçt', 'Эл. почта'],
  'bk.phone': ['Mobile', 'Mobil nömrə', 'Мобильный'],
  'bk.allergies': ['Allergies', 'Allergiyalar', 'Аллергии'],
  'bk.allergies.ph': ['Anything we must avoid', 'Qaçınmalı olduğumuz hər şey',
    'Что нам следует исключить'],
  'bk.dietary': ['Dietary requirements', 'Pəhriz tələbləri', 'Особенности питания'],
  'bk.dietary.ph': ['e.g. two vegans', 'məsələn, iki vegan', 'например, двое веганов'],
  'bk.access': ['Accessibility', 'Əlçatanlıq', 'Доступность'],
  'bk.access.ph': ['e.g. step-free route', 'məsələn, pilləsiz yol', 'например, вход без ступеней'],
  'bk.chairs': ['High chairs', 'Uşaq stulu', 'Детские стулья'],
  'bk.requests': ['Requests', 'Xüsusi istəklər', 'Пожелания'],
  'bk.requests.ph': ['Anything else we should know', 'Bilməli olduğumuz başqa bir şey',
    'Что ещё нам стоит знать'],
  'bk.confirm': ['Confirm reservation', 'Rezervasiyanı təsdiqlə', 'Подтвердить бронирование'],
  'bk.back': ['Back', 'Geri', 'Назад'],
  'bk.confirming': ['Confirming…', 'Təsdiqlənir…', 'Подтверждаем…'],
  'bk.missing': ['Please fill in your {fields}.', 'Zəhmət olmasa doldurun: {fields}.',
    'Пожалуйста, заполните: {fields}.'],
  'bk.holdexpired': ['The hold expired. Go back and pick a time again.',
    'Saxlama müddəti bitdi. Geri qayıdıb vaxtı yenidən seçin.',
    'Удержание истекло. Вернитесь и выберите время снова.'],

  // ------------------------------------------------------- success screen
  'ok.title': ['Thank you', 'Təşəkkür edirik', 'Спасибо'],
  'ok.body': ['Your reservation has been received and confirmed.',
    'Rezervasiyanız qəbul edildi və təsdiqləndi.',
    'Ваше бронирование получено и подтверждено.'],
  'ok.calendar': ['Add to calendar', 'Təqvimə əlavə et', 'Добавить в календарь'],
  'ok.google': ['Google Calendar', 'Google Təqvim', 'Google Календарь'],
  'ok.done': ['Back to the restaurant', 'Restorana qayıt', 'Вернуться в ресторан'],

  // ------------------------------------------------------------- waitlist
  'wl.title': ['Join the waitlist', 'Gözləmə siyahısına yazıl', 'Записаться в лист ожидания'],
  'wl.blurb': ['We will call you as soon as a suitable table frees up.',
    'Uyğun masa boşalan kimi Sizə zəng edəcəyik.',
    'Мы позвоним, как только освободится подходящий стол.'],
  'wl.name': ['Name', 'Ad, soyad', 'Имя'],
  'wl.area': ['Preferred area', 'Üstünlük verilən zona', 'Предпочитаемая зона'],
  'wl.area.ph': ['e.g. terrace', 'məsələn, teras', 'например, терраса'],
  'wl.join': ['Join the waitlist', 'Siyahıya yazıl', 'Записаться'],
  'wl.joining': ['Adding you…', 'Əlavə edilir…', 'Добавляем…'],
  'wl.done': ['You are on the waitlist. We will be in touch about {date} at {time}.',
    'Siz gözləmə siyahısındasınız. {date}, saat {time} barədə Sizinlə əlaqə saxlayacağıq.',
    'Вы в листе ожидания. Мы свяжемся с вами по поводу {date} в {time}.'],
  'wl.donenow': ['You are on the waitlist. Quoted wait: about {min} minutes.',
    'Siz gözləmə siyahısındasınız. Təxmini gözləmə: {min} dəqiqə.',
    'Вы в листе ожидания. Ориентировочное ожидание: около {min} минут.'],

  // ----------------------------------------------------------------- menu
  'menu.title': ['The Menu', 'Menyu', 'Меню'],
  'menu.note': ['Browse only. Ordering happens in the dining room.',
    'Yalnız baxış üçün. Sifariş zalda verilir.',
    'Только просмотр. Заказ оформляется в зале.'],
  'menu.back': ['Back to the restaurant', 'Restorana qayıt', 'Вернуться в ресторан'],
  'menu.soldout': ['Sold out', 'Bitib', 'Закончилось'],
  'menu.unavailable': ['The menu is unavailable right now.', 'Menyu hazırda əlçatan deyil.',
    'Меню сейчас недоступно.'],

  // ------------------------------------------------------------------ ask
  'ask.ph': ['Ask where to sit… "somewhere quiet by the water for two"',
    'Harada oturmaq barədə soruşun… "iki nəfər üçün su kənarında sakit yer"',
    'Спросите, где сесть… «тихое место у воды на двоих»'],
  'ask.go': ['Ask', 'Soruş', 'Спросить'],
  'ask.quiet2': ['Quiet for two', 'İki nəfər üçün sakit', 'Тихо на двоих'],
  'ask.water': ['By the water', 'Su kənarında', 'У воды'],
  'ask.romantic': ['Romantic', 'Romantik', 'Романтично'],
  'ask.family': ['Family', 'Ailə üçün', 'Для семьи'],
  'ask.nonsmoking': ['Non-smoking', 'Siqaretsiz', 'Для некурящих'],
  'ask.shade': ['Shade', 'Kölgə', 'В тени'],
  'ask.privacy': ['Privacy', 'Məxfilik', 'Приватность'],
  'ask.soon': ['Arriving soon', 'Tezliklə gəlir', 'Скоро придут'],
  'ask.thinking': ['Thinking…', 'Düşünür…', 'Думаю…'],
  'ask.failed': ['I could not answer that just now.', 'Hazırda cavab verə bilmədim.',
    'Сейчас не удалось ответить.'],

  // ---------------------------------------------------------------- misc
  'toast.booked': ['Table {n} is booked.', '{n} nömrəli masa rezerv edildi.', 'Стол {n} забронирован.'],
  'toast.offline': ['The restaurant system is not responding. Please try again in a moment.',
    'Restoran sistemi cavab vermir. Bir azdan yenidən cəhd edin.',
    'Система ресторана не отвечает. Попробуйте ещё раз через минуту.'],
  'err.generic': ['That booking was refused.', 'Bu rezervasiya qəbul edilmədi.',
    'Бронирование отклонено.'],
  'loading': ['Waking the restaurant…', 'Restoran oyanır…', 'Ресторан просыпается…'],
};

// Error codes SUFRA OS returns, in the guest's own language.
const ERRORS = {
  capacity: ['That party size does not fit this table.', 'Bu qonaq sayı bu masaya uyğun deyil.',
    'Такое количество гостей не помещается за этот стол.'],
  closed: ['We are not seating at that time.', 'Bu vaxt qonaq qəbul etmirik.',
    'В это время мы не принимаем гостей.'],
  conflict: ['That table was taken a moment ago. Please pick another time or table.',
    'Bu masa bir az əvvəl tutuldu. Başqa vaxt və ya masa seçin.',
    'Этот стол только что заняли. Выберите другое время или стол.'],
  bad_email: ['That email address does not look right.', 'E-poçt ünvanı düzgün görünmür.',
    'Адрес электронной почты выглядит неверным.'],
  bad_date: ['Please choose a valid date and time.', 'Zəhmət olmasa düzgün tarix və saat seçin.',
    'Пожалуйста, выберите корректные дату и время.'],
  past: ['That time has already passed. Please choose a later time.',
    'Bu vaxt artıq keçib. Zəhmət olmasa, daha gec bir vaxt seçin.',
    'Это время уже прошло. Пожалуйста, выберите более позднее время.'],
  missing_fields: ['Some details are still missing.', 'Bəzi məlumatlar çatışmır.',
    'Некоторые данные ещё не заполнены.'],
  unknown_table: ['That table is not available.', 'Bu masa əlçatan deyil.', 'Этот стол недоступен.'],
  blocked: ['That table is out of service.', 'Bu masa istifadədə deyil.',
    'Этот стол выведен из обслуживания.'],
  party: ['Please choose a valid party size.', 'Zəhmət olmasa düzgün qonaq sayı seçin.',
    'Пожалуйста, выберите корректное количество гостей.'],
  no_capacity: ['No table can take that party at that time. You can join the waitlist.',
    'Bu vaxt üçün uyğun masa yoxdur. Gözləmə siyahısına yazıla bilərsiniz.',
    'На это время нет подходящего стола. Можно записаться в лист ожидания.'],
  restaurant_unavailable: ['The restaurant system is not responding. Please try again in a moment.',
    'Restoran sistemi cavab vermir. Bir azdan yenidən cəhd edin.',
    'Система ресторана не отвечает. Попробуйте ещё раз через минуту.'],
};

// Words the attribute chips are built from, so the panel is not half English.
const WORDS = {
  Outdoors: ['Outdoors', 'Açıq havada', 'На улице'],
  Indoors: ['Indoors', 'Qapalı məkanda', 'В помещении'],
  'Near the water': ['Near the water', 'Su kənarında', 'У воды'],
  'By a window': ['By a window', 'Pəncərə yanında', 'У окна'],
  'Under an umbrella': ['Under an umbrella', 'Çətir altında', 'Под зонтом'],
  'Under cover': ['Under cover', 'Örtük altında', 'Под навесом'],
  'Open air': ['Open air', 'Açıq hava', 'Открытый воздух'],
  'Smoking permitted': ['Smoking permitted', 'Siqaret çəkməyə icazə var', 'Курение разрешено'],
  'Non-smoking': ['Non-smoking', 'Siqaret çəkmək qadağandır', 'Для некурящих'],
  Quiet: ['Quiet', 'Sakit', 'Тихо'],
  Lively: ['Lively', 'Canlı', 'Оживлённо'],
  'Moderate buzz': ['Moderate buzz', 'Orta səs-küy', 'Умеренно шумно'],
  'Private room': ['Private room', 'Xüsusi otaq', 'Отдельный зал'],
  'Semi-private': ['Semi-private', 'Yarı-xüsusi', 'Полуприватно'],
  'Open room': ['Open room', 'Ümumi zal', 'Общий зал'],
  'Premium view': ['Premium view', 'Əla mənzərə', 'Отличный вид'],
  Romantic: ['Romantic', 'Romantik', 'Романтично'],
  'Family friendly': ['Family friendly', 'Ailələr üçün', 'Для семей'],
  'Group table': ['Group table', 'Qrup masası', 'Стол для компании'],
  'Step-free': ['Step-free', 'Pilləsiz', 'Без ступеней'],
  indoors: ['indoors', 'qapalı məkanda', 'в помещении'],
  outdoors: ['outdoors', 'açıq havada', 'на улице'],
  'a date': ['a date', 'görüş', 'свидания'],
  'a group': ['a group', 'qrup', 'компании'],
  'quiet conversation': ['quiet conversation', 'sakit söhbət', 'тихой беседы'],
  'a working dinner': ['a working dinner', 'işgüzar şam', 'делового ужина'],
  families: ['families', 'ailələr', 'семей'],
  'watching the water': ['watching the water', 'suya baxmaq', 'видов на воду'],
  'drinks and small plates': ['drinks and small plates', 'içki və qəlyanaltı', 'напитков и закусок'],
  'live music nights': ['live music nights', 'canlı musiqi axşamları', 'вечеров живой музыки'],
};

let lang = (() => {
  try {
    const stored = localStorage.getItem(KEY);
    if (LANGS.indexOf(stored) >= 0) return stored;
  } catch (e) { /* private mode: fall through to the default */ }
  const nav = (navigator.language || 'en').slice(0, 2).toLowerCase();
  return LANGS.indexOf(nav) >= 0 ? nav : 'en';
})();

const listeners = [];
const index = () => LANGS.indexOf(lang);

function fill(text, vars) {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (m, k) => (vars[k] == null ? m : String(vars[k])));
}

export function T(key, vars) {
  const row = DICT[key];
  if (!row) return fill(key, vars);
  return fill(row[index()] || row[0], vars);
}

/** Translate a word that arrives from the attribute/chip vocabulary. */
export function W(word) {
  const row = WORDS[word];
  return row ? (row[index()] || row[0]) : word;
}

/** Turn a server refusal into the guest's own language. */
export function E(payload) {
  if (!payload) return T('err.generic');
  const row = ERRORS[payload.error];
  if (row) return row[index()] || row[0];
  return payload.message || T('err.generic');
}

export function getLang() { return lang; }

export function setLang(next) {
  if (LANGS.indexOf(next) < 0 || next === lang) return;
  lang = next;
  try { localStorage.setItem(KEY, next); } catch (e) { /* nothing to persist to */ }
  document.documentElement.lang = next;
  applyStatic();
  listeners.forEach((fn) => { try { fn(next); } catch (e) {} });
}

export function onLangChange(fn) { listeners.push(fn); }

/** Everything marked up in the HTML, in one pass. */
export function applyStatic(root) {
  const scope = root || document;
  scope.querySelectorAll('[data-i18n]').forEach((el) => {
    el.textContent = T(el.getAttribute('data-i18n'));
  });
  scope.querySelectorAll('[data-i18n-ph]').forEach((el) => {
    el.setAttribute('placeholder', T(el.getAttribute('data-i18n-ph')));
  });
  scope.querySelectorAll('[data-i18n-title]').forEach((el) => {
    el.setAttribute('title', T(el.getAttribute('data-i18n-title')));
  });
  document.documentElement.lang = lang;
}

/** A date the guest recognises, in their own language and the venue's clock.
 *  Azerbaijani is spelled out rather than left to Intl: not every browser
 *  ships an az-AZ calendar, and the ones that do not quietly produce "M09 12",
 *  which is worse than no localisation at all. */
const MONTHS = {
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
  az: ['yan', 'fev', 'mar', 'apr', 'may', 'iyun', 'iyul', 'avq', 'sen', 'okt', 'noy', 'dek'],
  ru: ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'],
};
const WEEKDAYS = {
  en: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
  az: ['B.', 'B.e.', 'Ç.a.', 'Ç.', 'C.a.', 'C.', 'Ş.'],
  ru: ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'],
};

export function niceDate(iso) {
  try {
    const d = new Date(iso + 'T12:00:00');
    if (isNaN(d.getTime())) return iso;
    const l = lang;
    return `${WEEKDAYS[l][d.getDay()]} ${d.getDate()} ${MONTHS[l][d.getMonth()]}`;
  } catch (e) { return iso; }
}
