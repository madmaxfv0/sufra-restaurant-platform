
/*
============================================================
SUFRA FINAL UI I18N
Permanent static translation layer.
No external translation service required for these UI strings.
============================================================
*/

(() => {
  const getLang = () => {
    try {
      return localStorage.getItem("nova-lang") ||
             localStorage.getItem("nova-command-lang") ||
             "en";
    } catch {
      return "en";
    }
  };

  const T = {
    "Sea bass fillet": ["Sea bass fillet", "Филе сибаса"],
    "Dover sole": ["Dover sole", "Дуврская камбала"],
    "Turbot": ["Turbot", "Тюрбо"],
    "Scallops": ["Scallops", "Морские гребешки"],
    "Tuna loin": ["Tuna loin", "Филе тунца"],
    "Native lobster": ["Native lobster", "Европейский омар"],
    "Oysters": ["Oysters", "Устрицы"],
    "Oscietra caviar": ["Oscietra caviar", "Осетровая икра"],
    "Ribeye, dry aged": ["Ribeye, dry aged", "Рибай сухого вызревания"],
    "Sirloin": ["Sirloin", "Стриплойн"],
    "Lamb rack": ["Lamb rack", "Каре ягнёнка"],
    "Duck leg": ["Duck leg", "Утиная ножка"],
    "Chicken, whole": ["Chicken, whole", "Целая курица"],
    "Bone marrow": ["Bone marrow", "Костный мозг"],
    "Burrata": ["Burrata", "Буррата"],
    "Parmesan 24mo": ["Parmesan 24mo", "Пармезан, выдержка 24 месяца"],
    "Comté": ["Comté", "Сыр комте"],
    "Butter, cultured": ["Butter, cultured", "Кислосливочное масло"],
    "Double cream": ["Double cream", "Жирные сливки"],
    "Mascarpone": ["Mascarpone", "Маскарпоне"],
    "Eggs": ["Eggs", "Яйца"],
    "Black truffle": ["Black truffle", "Чёрный трюфель"],
    "Girolles": ["Girolles", "Лисички"],
    "Porcini, dried": ["Porcini, dried", "Сушёные белые грибы"],
    "Asparagus": ["Asparagus", "Спаржа"],
    "Datterini tomato": ["Datterini tomato", "Томаты даттерини"],
    "Vine tomato": ["Vine tomato", "Томаты на ветке"],
    "Watermelon": ["Watermelon", "Арбуз"],
    "Aubergine": ["Aubergine", "Баклажан"],
    "Cauliflower": ["Cauliflower", "Цветная капуста"],
    "Hispi cabbage": ["Hispi cabbage", "Остроконечная капуста"],
    "Green beans": ["Green beans", "Стручковая фасоль"],
    "Ratte potato": ["Ratte potato", "Картофель ратте"],
    "Maris Piper": ["Maris Piper", "Картофель марис пайпер"],
    "Basil": ["Basil", "Базилик"],
    "Lemon, Amalfi": ["Lemon, Amalfi", "Лимон амальфи"],
    "Cherries": ["Cherries", "Вишня"],
    "Pomegranate": ["Pomegranate", "Гранат"],
    "Avocado": ["Avocado", "Авокадо"],
    "Pistachio, Bronte": ["Pistachio, Bronte", "Фисташки бронте"],
    "Almond, flaked": ["Almond, flaked", "Миндальные лепестки"],
    "Chocolate 70%": ["Chocolate 70%", "Шоколад 70%"],
    "Vanilla pod": ["Vanilla pod", "Стручок ванили"],
    "00 flour": ["00 flour", "Мука типа 00"],
    "Sourdough starter": ["Sourdough starter", "Хлебная закваска"],
    "Carnaroli rice": ["Carnaroli rice", "Рис карнароли"],
    "Panko": ["Panko", "Сухари панко"],
    "Tahini": ["Tahini", "Тахини"],
    "Harissa": ["Harissa", "Харисса"],
    "Yuzu juice": ["Yuzu juice", "Сок юдзу"],
    "Sesame seed": ["Sesame seed", "Кунжут"],
    "Olive oil, Sicilian": ["Olive oil, Sicilian", "Сицилийское оливковое масло"],
    "Gordal olives": ["Gordal olives", "Оливки гордаль"],
    "Prosecco": ["Prosecco", "Просекко"],
    "Campari": ["Campari", "Кампари"],
    "Gin": ["Gin", "Джин"],
    "Barolo Vietti 2018": ["Barolo Vietti 2018", "Бароло Виетти 2018"],
    "Chablis 1er Cru": ["Chablis 1er Cru", "Шабли Премьер Крю"],
    "Seedlip Garden": ["Seedlip Garden", "Сидлип Гарден"],
    "Coffee beans": ["Coffee beans", "Кофейные зёрна"],
    "Dish ingredient usage": ["Dish ingredient usage", "Расход ингредиентов по блюдам"],
    "Recipe quantities × portions prepared. These are estimates, not weighed kitchen measurements.": ["Recipe quantities × portions prepared. These are estimates, not weighed kitchen measurements.", "Расход по рецепту × приготовленные порции. Это расчётные данные, а не фактическое взвешивание на кухне."],
    "Usage period": ["Usage period", "Период расхода"],
    "Days": ["Days", "Дней"],
    "Plan portions": ["Plan portions", "Количество порций для расчёта"],
    "Calculate": ["Calculate", "Рассчитать"],
    "Edit recipe": ["Edit recipe", "Изменить рецепт"],
    "Prepared portions": ["Prepared portions", "Приготовлено порций"],
    "Recorded in selected period": ["Recorded in selected period", "За выбранный период"],
    "Planned portions": ["Planned portions", "Планируемые порции"],
    "Preview only — stock is unchanged": ["Preview only — stock is unchanged", "Предварительный расчёт — остатки не меняются"],
    "Recipe needed. Enter the kitchen’s quantities per portion to calculate ingredient use.": ["Recipe needed. Enter the kitchen’s quantities per portion to calculate ingredient use.", "Нужен рецепт. Укажите нормы кухни на одну порцию для расчёта расхода."],
    "Per portion": ["Per portion", "На порцию"],
    "Used for this dish": ["Used for this dish", "Расход на это блюдо"],
    "Remaining stock": ["Remaining stock", "Остаток на складе"],
    "Needed for plan": ["Needed for plan", "Нужно по плану"],
    "After planned cooking": ["After planned cooking", "Остаток после приготовления"],
    "Previous recipe ingredient": ["Previous recipe ingredient", "Ингредиент предыдущего рецепта"],
    "Remaining stock includes all recorded deliveries, dishes, waste and adjustments. The plan is a preview and does not deduct stock.": ["Remaining stock includes all recorded deliveries, dishes, waste and adjustments. The plan is a preview and does not deduct stock.", "Остаток учитывает все записанные поставки, блюда, списания и корректировки. План — предварительный расчёт без списания со склада."],
    "Enter a whole number of portions from 1 to 10000.": ["Enter a whole number of portions from 1 to 10000.", "Введите целое число порций от 1 до 10000."],
    "Generate QR": ["Generate QR", "Создать QR-код"],
    "View QR": ["View QR", "Показать QR-код"],
    "Regenerate QR": ["Regenerate QR", "Заменить QR-код"],
    "Employee access": ["Employee access", "Доступ сотрудника"],
    "Use the employee’s existing four-digit PIN.": ["Use the employee’s existing four-digit PIN.", "Используйте текущий четырёхзначный PIN сотрудника."],
    "Download QR": ["Download QR", "Скачать QR-код"],
    "Print badge": ["Print badge", "Распечатать пропуск"],
    "Copy login link": ["Copy login link", "Скопировать ссылку входа"],
    "g": ["g", "г"],
    "kg": ["kg", "кг"],
    "ml": ["ml", "мл"],
    "l": ["l", "л"],
    "unit": ["unit", "шт."],
    "pcs": ["pcs", "шт."],
    "Dish": ["Yemək", "Блюдо"],
    "Unit": ["Vahid", "Ед. изм."],
    "Qty per portion": ["Porsiya üçün miqdar", "Количество на порцию"],
    /* ---------- UNIVERSAL ---------- */

    "Home": ["Ana səhifə", "Главная"],
    "Overview": ["Ümumi baxış", "Обзор"],
    "Command centre": ["İdarəetmə mərkəzi", "Центр управления"],
    "Live operations": ["Canlı əməliyyatlar", "Операции в реальном времени"],
    "Floor": ["Zal", "Зал"],
    "Reservations": ["Rezervasiyalar", "Бронирования"],
    "Orders": ["Sifarişlər", "Заказы"],
    "Kitchen": ["Mətbəx", "Кухня"],
    "Menu": ["Menyu", "Меню"],
    "Inventory": ["Ehtiyatlar", "Запасы"],

    /* ---------- SUFRA ANBAR ---------- */
    /* The module is "Anbar" in Azerbaijani and "Склад" in Russian — the
       words a warehouse manager in Baku actually uses. */
    "Warehouse": ["Anbar", "Склад"],
    "Anbar": ["Anbar", "Склад"],
    "Opening Warehouse…": ["Anbar açılır…", "Открываем склад…"],
    "Supplier to shelf to plate — one chain, one set of numbers.":
      ["Təchizatçıdan rəfə, rəfdən boşqaba — bir zəncir, bir rəqəm sistemi.",
       "От поставщика на полку и в тарелку — одна цепочка, одни цифры."],
    "Opening Anbar…": ["Anbar açılır…", "Открываем склад…"],

    "Receiving": ["Qəbul", "Приёмка"],
    "Purchases": ["Satınalmalar", "Закупки"],
    "Transfers": ["Daxili köçürmələr", "Перемещения"],
    "Stocktake": ["İnventarizasiya", "Инвентаризация"],
    "Waste": ["Zay", "Списание"],
    "Recipes & Costing": ["Reseptlər və maya dəyəri", "Рецепты и себестоимость"],
    "AI Intelligence": ["Süni intellekt təhlili", "ИИ-аналитика"],
    "Reports": ["Hesabatlar", "Отчёты"],
    "Activity": ["Hərəkətlər", "Движения"],
    "Categories": ["Kateqoriyalar", "Категории"],

    /* stock status */
    "Healthy": ["Normal", "В норме"],
    "Low": ["Az qalıb", "Мало на складе"],
    "Low stock": ["Az qalıb", "Мало на складе"],
    "Critical": ["Kritik", "Критично"],
    "Out of stock": ["Bitib", "Нет в наличии"],
    "Over-stocked": ["Artıq ehtiyat", "Избыток"],
    "Expiring soon": ["Vaxtı bitir", "Истекает срок"],
    "Expired": ["Vaxtı bitib", "Просрочено"],
    "Quarantined": ["Karantində", "На карантине"],

    /* dashboard */
    "Inventory value": ["Ehtiyatın dəyəri", "Стоимость запасов"],
    "Food cost": ["Məhsul maya dəyəri", "Себестоимость продуктов"],
    "Deliveries due": ["Gözlənilən çatdırılmalar", "Ожидаемые поставки"],
    "Pending orders": ["Təsdiq gözləyən sifarişlər", "Заказы на утверждении"],
    "Open alerts": ["Açıq xəbərdarlıqlar", "Открытые оповещения"],
    "Variance": ["Fərq", "Расхождение"],
    "Waste today": ["Bu günün zayı", "Списание за сегодня"],
    "Waste rate": ["Zay nisbəti", "Доля списаний"],
    "Stock health": ["Ehtiyatın vəziyyəti", "Состояние запасов"],
    "Value by category": ["Kateqoriya üzrə dəyər", "Стоимость по категориям"],
    "Critical items": ["Kritik mallar", "Критичные позиции"],
    "Upcoming deliveries": ["Gözlənilən çatdırılmalar", "Ближайшие поставки"],
    "Purchases vs consumption": ["Alışlar və istehlak", "Закупки и расход"],
    "SUFRA AI daily brief": ["SUFRA AI gündəlik icmalı", "Ежедневная сводка SUFRA AI"],
    "Alerts": ["Xəbərdarlıqlar", "Оповещения"],

    /* table headings */
    "On hand": ["Mövcuddur", "В наличии"],
    "Reorder": ["Sifariş həddi", "Точка заказа"],
    "Reorder at": ["Sifariş həddi", "Точка заказа"],
    "Reorder point": ["Sifariş həddi", "Точка заказа"],
    "Minimum stock": ["Minimum ehtiyat", "Минимальный запас"],
    "Target stock": ["Hədəf ehtiyat", "Целевой запас"],
    "Maximum stock": ["Maksimum ehtiyat", "Максимальный запас"],
    "Cost": ["Maya dəyəri", "Себестоимость"],
    "Value": ["Dəyər", "Стоимость"],
    "Location": ["Saxlama yeri", "Место хранения"],
    "Storage location": ["Saxlama yeri", "Место хранения"],
    "Supplier": ["Təchizatçı", "Поставщик"],
    "Item": ["Mal", "Позиция"],
    "Qty": ["Miqdar", "Кол-во"],
    "Quantity": ["Miqdar", "Количество"],
    "Balance": ["Qalıq", "Остаток"],
    "Reason": ["Səbəb", "Причина"],
    "Comment": ["Şərh", "Комментарий"],
    "Expires": ["Bitmə tarixi", "Годен до"],
    "Delivered": ["Çatdırılıb", "Доставлено"],
    "Accepted": ["Qəbul edilib", "Принято"],
    "Rejected": ["Rədd edilib", "Отклонено"],
    "Quality": ["Keyfiyyət", "Качество"],
    "Batch": ["Partiya", "Партия"],
    "Lead": ["Çatdırılma müddəti", "Срок поставки"],
    "Score": ["Reytinq", "Рейтинг"],
    "On time": ["Vaxtında", "Вовремя"],
    "Deliveries": ["Çatdırılmalar", "Поставки"],
    "Spend": ["Xərc", "Расходы"],
    "Margin": ["Marja", "Маржа"],
    "Movement": ["Hərəkət", "Движение"],
    "System": ["Sistem", "Система"],
    "Counted": ["Sayılıb", "Подсчитано"],
    "Cost impact": ["Maliyyə təsiri", "Влияние на стоимость"],

    /* movements */
    "Opening balance": ["Açılış qalığı", "Начальный остаток"],
    "Delivery received": ["Çatdırılma qəbul edildi", "Поставка принята"],
    "Sold": ["Satılıb", "Продано"],
    "Transfer in": ["Daxil olan köçürmə", "Приход перемещением"],
    "Transfer out": ["Çıxan köçürmə", "Расход перемещением"],
    "Manual adjustment": ["Əl ilə düzəliş", "Ручная корректировка"],
    "Returned to supplier": ["Təchizatçıya qaytarılıb", "Возврат поставщику"],
    "Returned to stock": ["Anbara qaytarılıb", "Возврат на склад"],

    /* waste reasons */
    "Spoilage": ["Xarab olub", "Порча"],
    "Preparation waste": ["Hazırlıq tullantısı", "Отходы при заготовке"],
    "Overproduction": ["Artıq istehsal", "Перепроизводство"],
    "Returned dish": ["Qaytarılmış yemək", "Возврат блюда"],
    "Damaged": ["Zədələnib", "Повреждено"],
    "Incorrect preparation": ["Səhv hazırlanıb", "Ошибка приготовления"],
    "Staff meal": ["İşçi yeməyi", "Питание персонала"],
    "Quality rejection": ["Keyfiyyətə görə rədd", "Отказ по качеству"],

    /* actions */
    "Add item": ["Mal əlavə et", "Добавить позицию"],
    "Add first item": ["İlk malı əlavə et", "Добавить первую позицию"],
    "Add inventory item": ["Anbara mal əlavə et", "Добавить позицию на склад"],
    "Adjust stock": ["Ehtiyatı düzəlt", "Скорректировать запас"],
    "Log waste": ["Zayı qeyd et", "Записать списание"],
    "Record waste": ["Zayı qeyd et", "Записать списание"],
    "Edit item": ["Malı redaktə et", "Редактировать позицию"],
    "Record delivery": ["Çatdırılmanı qeyd et", "Записать поставку"],
    "Confirm and take into stock": ["Təsdiqlə və anbara götür", "Подтвердить и оприходовать"],
    "Raise purchase order": ["Satınalma sifarişi yarat", "Создать заказ поставщику"],
    "Raise order": ["Sifariş yarat", "Создать заказ"],
    "Add supplier": ["Təchizatçı əlavə et", "Добавить поставщика"],
    "New transfer": ["Yeni köçürmə", "Новое перемещение"],
    "Request transfer": ["Köçürmə tələb et", "Запросить перемещение"],
    "Start stocktake": ["İnventarizasiyaya başla", "Начать инвентаризацию"],
    "Start count": ["Saymağa başla", "Начать подсчёт"],
    "Save counts": ["Sayımı yadda saxla", "Сохранить подсчёт"],
    "Approve and adjust": ["Təsdiqlə və düzəlt", "Утвердить и скорректировать"],
    "Approve": ["Təsdiqlə", "Утвердить"],
    "Mark sent": ["Göndərilmiş kimi işarələ", "Отметить отправленным"],
    "Send": ["Göndər", "Отправить"],
    "Confirm received": ["Qəbulu təsdiqlə", "Подтвердить получение"],
    "Add ingredient": ["İnqrediyent əlavə et", "Добавить ингредиент"],
    "Add recipe": ["Resept əlavə et", "Добавить рецепт"],
    "Save recipe": ["Resepti yadda saxla", "Сохранить рецепт"],
    "Add line": ["Sətir əlavə et", "Добавить строку"],
    "Export CSV": ["CSV ixrac et", "Экспорт в CSV"],
    "Open": ["Aç", "Открыть"],
    "Apply adjustment": ["Düzəlişi tətbiq et", "Применить корректировку"],

    /* intelligence */
    "Tomorrow's demand": ["Sabahkı tələbat", "Спрос на завтра"],
    "Smart reordering": ["Ağıllı sifariş", "Умный заказ"],
    "Suggested order": ["Təklif olunan sifariş", "Рекомендуемый заказ"],
    "Anomalies": ["Anomaliyalar", "Аномалии"],
    "Expiry & FEFO": ["Son istifadə və FEFO", "Сроки годности и FEFO"],
    "Food cost intelligence": ["Maya dəyəri təhlili", "Аналитика себестоимости"],
    "Waste intelligence": ["Zay təhlili", "Аналитика списаний"],
    "Supplier recommendations": ["Təchizatçı tövsiyələri", "Рекомендации по поставщикам"],
    "Price movement": ["Qiymət dəyişməsi", "Динамика цен"],
    "Price rises reaching the menu": ["Menyuya təsir edən qiymət artımları",
                                      "Рост цен, влияющий на меню"],
    "Dish costing": ["Yeməyin maya dəyəri", "Себестоимость блюд"],
    "Dishes without a recipe": ["Reseptsiz yeməklər", "Блюда без рецепта"],
    "Costed dishes": ["Maya dəyəri hesablanmış yeməklər", "Блюда с расчётом"],
    "Missing recipes": ["Çatışmayan reseptlər", "Отсутствующие рецепты"],
    "high confidence": ["yüksək etibarlılıq", "высокая достоверность"],
    "medium confidence": ["orta etibarlılıq", "средняя достоверность"],
    "low confidence": ["aşağı etibarlılıq", "низкая достоверность"],

    /* reports */
    "Inventory valuation": ["Ehtiyatın qiymətləndirilməsi", "Оценка запасов"],
    "Inventory movement": ["Ehtiyatın hərəkəti", "Движение запасов"],
    "Purchasing": ["Satınalma", "Закупки"],
    "Supplier performance": ["Təchizatçıların göstəriciləri", "Показатели поставщиков"],
    "Stock variance": ["Ehtiyat fərqi", "Расхождение запасов"],
    "Product consumption": ["Məhsul istehlakı", "Расход продуктов"],
    "Expiry risk": ["Son istifadə riski", "Риск просрочки"],
    "Price changes": ["Qiymət dəyişiklikləri", "Изменения цен"],
    "Stock movement ledger": ["Ehtiyat hərəkəti jurnalı", "Журнал движения запасов"],
    "Warehouse actions": ["Anbar əməliyyatları", "Действия на складе"],

    /* Anbar — card sub-labels */
    "at or under reorder point": ["sifariş həddində və ya aşağı", "на уровне точки заказа или ниже"],
    "awaiting approval": ["təsdiq gözləyir", "ожидает утверждения"],
    "below minimum": ["minimumdan aşağı", "ниже минимума"],
    "confirmed deliveries": ["təsdiqlənmiş çatdırılmalar", "подтверждённые поставки"],
    "consume no stock when sold": ["satılanda ehtiyatdan silinmir", "при продаже не списываются"],
    "expected in": ["gözlənilir", "ожидается"],
    "have a recipe on file": ["resepti var", "имеют рецепт"],
    "menu average": ["menyu üzrə orta", "среднее по меню"],
    "need review": ["baxılmalıdır", "требуют внимания"],
    "nothing on the shelf": ["rəfdə heç nə yoxdur", "на полке ничего нет"],
    "of purchases": ["alışlardan", "от закупок"],
    "physical vs ledger": ["faktiki və jurnal", "факт против журнала"],
    "same window": ["eyni dövr", "тот же период"],
    "this month": ["bu ay", "в этом месяце"],
    "this week": ["bu həftə", "на этой неделе"],
    "within 72 hours": ["72 saat ərzində", "в течение 72 часов"],
    "60 active lines": ["60 aktiv mal", "60 активных позиций"],

    /* Anbar — panel descriptions */
    "Every active line, by where it sits against its own thresholds.":
      ["Hər aktiv mal, öz həddlərinə görə.",
       "Каждая активная позиция относительно собственных порогов."],
    "Where the capital on the shelves actually sits.":
      ["Rəflərdəki kapitalın həqiqi bölgüsü.",
       "Где на самом деле лежит капитал на полках."],
    "What runs out first if nobody acts.":
      ["Heç nə edilməsə, ilk nə bitəcək.",
       "Что закончится первым, если ничего не предпринять."],
    "Orders approved or sent and not yet received.":
      ["Təsdiqlənmiş və ya göndərilmiş, hələ qəbul edilməmiş sifarişlər.",
       "Заказы утверждены или отправлены, но ещё не получены."],
    "Open findings, newest first.":
      ["Açıq tapıntılar, ən yenisi əvvəl.", "Открытые находки, новые сверху."],
    "Value received against value sold through recipes, last 30 days.":
      ["Son 30 gündə qəbul edilən dəyər və reseptlər üzrə satılan dəyər.",
       "Принятая стоимость против проданной через рецепты за 30 дней."],
    "Demand over supplier lead time, minus what is on hand and already coming.":
      ["Təchizat müddəti üzrə tələbat, mövcud və yolda olan çıxılmaqla.",
       "Спрос за срок поставки минус остаток и то, что уже в пути."],
    "Earliest date first, against how much demand will realistically use.":
      ["Ən yaxın tarix əvvəl, real tələbatla müqayisədə.",
       "Сначала ближайший срок, в сравнении с реальным спросом."],
    "Observations, not accusations. Each one shows the arithmetic behind it.":
      ["Müşahidələr, ittiham deyil. Hər birinin arxasındakı hesablama göstərilir.",
       "Наблюдения, а не обвинения. За каждым показан расчёт."],
    "Quantity, not just a threshold trip. Open \"Why?\" on any line for the arithmetic.":
      ["Sadəcə hədd deyil, konkret miqdar. Hesablama üçün istənilən sətirdə «Niyə?» açın.",
       "Не просто порог, а конкретное количество. Откройте «Почему?» для расчёта."],
    "Ingredient cost at today's weighted average, against the menu price.":
      ["Bugünkü orta çəkili maya dəyəri, menyu qiyməti ilə müqayisədə.",
       "Себестоимость по средневзвешенной цене против цены в меню."],
    "Same ingredient, more than one quote. Price is only part of the answer.":
      ["Eyni məhsul, bir neçə təklif. Qiymət cavabın yalnız bir hissəsidir.",
       "Один продукт, несколько предложений. Цена — лишь часть ответа."],
    "Where the cheapest quote is not automatically the right one.":
      ["Ən ucuz təklif həmişə ən doğrusu deyil.",
       "Где самое дешёвое предложение не всегда верное."],
    "Which dishes a supplier increase actually hurts, and by how much a month.":
      ["Təchizatçı artımının hansı yeməklərə və ayda nə qədər təsir etdiyi.",
       "На какие блюда влияет рост цен поставщика и насколько в месяц."],
    "What each line last cost against the time before.":
      ["Hər malın son qiyməti əvvəlki ilə müqayisədə.",
       "Последняя цена каждой позиции против предыдущей."],
    "Patterns found in the last 30 days of entries.":
      ["Son 30 günün qeydlərində tapılan təkrarlanan hallar.",
       "Закономерности за последние 30 дней записей."],
    "Every entry, with who recorded it.":
      ["Hər qeyd və onu kimin etdiyi.", "Каждая запись и кто её сделал."],
    "Every gram in and out, append-only. This is the audit trail.":
      ["Hər qram giriş və çıxış, yalnız əlavə olunur. Bu, audit izidir.",
       "Каждый грамм прихода и расхода, только добавление. Это аудиторский след."],
    "Who changed what, and what it was before.":
      ["Kim nəyi dəyişdi və əvvəl necə idi.", "Кто что изменил и как было раньше."],

    /* Anbar — empty states */
    "No open alerts.": ["Açıq xəbərdarlıq yoxdur.", "Открытых оповещений нет."],
    "Nothing logged.": ["Heç nə qeyd edilməyib.", "Ничего не записано."],
    "Nothing needs ordering right now.":
      ["Hazırda sifariş tələb olunmur.", "Сейчас заказывать нечего."],
    "Nothing needs ordering. Every line covers expected demand over its lead time.":
      ["Sifariş tələb olunmur. Hər mal təchizat müddəti üzrə tələbatı ödəyir.",
       "Заказывать нечего. Каждая позиция покрывает спрос за срок поставки."],
    "Nothing expires within seven days.":
      ["Yeddi gün ərzində vaxtı bitən yoxdur.", "В ближайшие семь дней ничего не истекает."],
    "Nothing unusual. Consumption, prices and adjustments all sit inside their normal range.":
      ["Qeyri-adi heç nə yoxdur. İstehlak, qiymətlər və düzəlişlər normal həddədir.",
       "Ничего необычного. Расход, цены и корректировки в пределах нормы."],
    "Every costed dish sits inside its expected margin.":
      ["Maya dəyəri hesablanmış hər yemək gözlənilən marja daxilindədir.",
       "Каждое рассчитанное блюдо укладывается в ожидаемую маржу."],
    "No recipes on file, so ingredient demand cannot be projected yet.":
      ["Resept yoxdur, ona görə inqrediyent tələbatı hesablana bilmir.",
       "Рецептов нет, поэтому спрос на ингредиенты пока не рассчитать."],
    "No rows fall inside the selected window.":
      ["Seçilmiş dövrə uyğun qeyd yoxdur.", "В выбранном периоде записей нет."],
    "No warehouse actions recorded yet.":
      ["Hələ anbar əməliyyatı qeyd edilməyib.", "Действий на складе пока не зафиксировано."],
    "Nothing to show yet.": ["Hələ göstəriləcək heç nə yoxdur.", "Пока нечего показать."],
    "All categories": ["Bütün kateqoriyalar", "Все категории"],
    "All locations": ["Bütün saxlama yerləri", "Все места хранения"],
    "All statuses": ["Bütün statuslar", "Все статусы"],
    "All suppliers": ["Bütün təchizatçılar", "Все поставщики"],
    "Suppliers": ["Təchizatçılar", "Поставщики"],
    "Guests": ["Qonaqlar", "Гости"],
    "Staff": ["Heyət", "Персонал"],
    "Analytics": ["Analitika", "Аналитика"],
    "Finance": ["Maliyyə", "Финансы"],
    "Settings": ["Ayarlar", "Настройки"],
    "Accounting": ["Mühasibatlıq", "Бухгалтерия"],
    "AI Copilot": ["AI köməkçi", "AI-помощник"],

    "Owner": ["Sahibkar", "Владелец"],
    "General Manager": ["Baş menecer", "Генеральный менеджер"],
    "Manager": ["Menecer", "Менеджер"],
    "Restaurant Manager": ["Restoran meneceri", "Менеджер ресторана"],
    "Waiter": ["Ofisiant", "Официант"],
    "Bartender": ["Barmen", "Бармен"],
    "Host": ["Hostes", "Хостес"],
    "Cashier": ["Kassir", "Кассир"],
    "Inventory Manager": ["Anbar meneceri", "Менеджер склада"],

    "Open": ["Aç", "Открыть"],
    "Close": ["Bağla", "Закрыть"],
    "Save": ["Yadda saxla", "Сохранить"],
    "Save changes": ["Dəyişiklikləri yadda saxla", "Сохранить изменения"],
    "Cancel": ["Ləğv et", "Отменить"],
    "Delete": ["Sil", "Удалить"],
    "Remove": ["Sil", "Удалить"],
    "Edit": ["Redaktə et", "Редактировать"],
    "Add": ["Əlavə et", "Добавить"],
    "Confirm": ["Təsdiqlə", "Подтвердить"],
    "Continue": ["Davam et", "Продолжить"],
    "Back": ["Geri", "Назад"],
    "Done": ["Hazırdır", "Готово"],
    "Search": ["Axtar", "Поиск"],
    "Filters": ["Filtrlər", "Фильтры"],
    "All": ["Hamısı", "Все"],
    "None": ["Heç biri", "Нет"],
    "Yes": ["Bəli", "Да"],
    "No": ["Xeyr", "Нет"],
    "Now": ["İndi", "Сейчас"],
    "Today": ["Bu gün", "Сегодня"],
    "Tomorrow": ["Sabah", "Завтра"],
    "Notes": ["Qeydlər", "Заметки"],
    "Status": ["Status", "Статус"],
    "Actions": ["Əməliyyatlar", "Действия"],
    "Language": ["Dil", "Язык"],
    "Notifications": ["Bildirişlər", "Уведомления"],
    "Profile": ["Profil", "Профиль"],
    "Switch user": ["İstifadəçini dəyiş", "Сменить пользователя"],
    "Light mode": ["Açıq rejim", "Светлая тема"],
    "Dark mode": ["Tünd rejim", "Тёмная тема"],

    /* ---------- FLOOR / TABLES ---------- */

    "The room": ["Zal", "Зал"],
    "Drag a table to redraw the floor. Tap one to open it.":
      ["Zal planını dəyişmək üçün masanı sürüşdürün. Açmaq üçün masaya toxunun.",
       "Перетащите стол, чтобы изменить план зала. Нажмите на стол, чтобы открыть его."],

    "Tables": ["Masalar", "Столы"],
    "Active tables": ["Aktiv masalar", "Активные столы"],
    "Tables & waiter assignments": ["Masalar və ofisiant təyinatları", "Столы и назначения официантов"],
    "Assignments update the waiter tablet immediately.":
      ["Təyinatlar ofisiant planşetində dərhal yenilənir.",
       "Назначения сразу обновляются на планшете официанта."],

    "Table": ["Masa", "Стол"],
    "Seats": ["Yerlər", "Места"],
    "Zone": ["Zona", "Зона"],
    "Terrace": ["Terras", "Терраса"],
    "Main room": ["Əsas zal", "Основной зал"],
    "MAIN ROOM": ["ƏSAS ZAL", "ОСНОВНОЙ ЗАЛ"],
    "TERRACE": ["TERRAS", "ТЕРРАСА"],
    "BAR": ["BAR", "БАР"],

    "Free": ["Boş", "Свободен"],
    "Reserved": ["Rezerv edilib", "Забронирован"],
    "Held": ["Saxlanılıb", "Удерживается"],
    "Just sat": ["Yeni oturub", "Только сели"],
    "Ordering": ["Sifariş verir", "Заказывают"],
    "Eating": ["Yemək yeyir", "Едят"],
    "In the kitchen": ["Mətbəxdə", "На кухне"],
    "Food at the pass": ["Servisə hazırdır", "Готово к выдаче"],
    "Bill asked for": ["Hesab istənilib", "Попросили счёт"],
    "Needs clearing": ["Təmizlənməlidir", "Нужно убрать"],
    "Wants a waiter": ["Ofisiant çağırır", "Вызывает официанта"],
    "In service": ["Xidmətdə", "В обслуживании"],

    "State": ["Vəziyyət", "Состояние"],
    "In this state": ["Bu vəziyyətdə", "В этом состоянии"],
    "Walk-in, no profile attached.":
      ["Rezervasiyasız qonaq, profil əlavə edilməyib.",
       "Гость без бронирования, профиль не привязан."],

    "Move this table to": ["Masanın vəziyyətini dəyiş", "Изменить состояние стола"],
    "Free the table": ["Masanı boşalt", "Освободить стол"],

    "Allergies": ["Allergiyalar", "Аллергии"],
    "Allergy": ["Allergiya", "Аллергия"],
    "Record an allergy": ["Allergiyanı qeyd et", "Записать аллергию"],
    "Allergy recorded on table":
      ["Allergiya masada qeyd edildi", "Аллергия записана для стола"],
    "Acknowledge allergy":
      ["Allergiyanı təsdiqlə", "Подтвердить аллергию"],

    /* ---------- RESERVATIONS ---------- */

    "Guest reservation": ["Qonaq rezervasiyası", "Бронирование гостя"],
    "Make a booking": ["Rezervasiya yarat", "Создать бронь"],
    "Take a booking": ["Rezervasiya qəbul et", "Принять бронь"],
    "Add to waitlist": ["Gözləmə siyahısına əlavə et", "Добавить в лист ожидания"],
    "Waitlist": ["Gözləmə siyahısı", "Лист ожидания"],
    "Awaiting table": ["Masa gözləyir", "Ожидает стол"],
    "Party size": ["Qonaq sayı", "Количество гостей"],
    "First name": ["Ad", "Имя"],
    "Last name": ["Soyad", "Фамилия"],
    "Phone": ["Telefon", "Телефон"],
    "Email": ["E-poçt", "Эл. почта"],
    "Occasion": ["Münasibət", "Повод"],
    "Seating preference": ["Oturma üstünlüyü", "Пожелание по посадке"],
    "Accessibility": ["Əlçatanlıq", "Доступность"],
    "High chairs": ["Uşaq stulları", "Детские стулья"],
    "Special request": ["Xüsusi istək", "Особое пожелание"],
    "Confirmation language": ["Təsdiq dili", "Язык подтверждения"],
    "No-show": ["Gəlmədi", "Не пришёл"],
    "No-show risk": ["Gəlməmə riski", "Риск неявки"],
    "Late": ["Gecikir", "Опаздывает"],
    "Seated": ["Oturub", "Посажен"],
    "Completed": ["Tamamlandı", "Завершено"],

    /* ---------- GUEST APP ---------- */

    "Tonight's menu.": ["Bu axşamın menyusu.", "Меню на этот вечер."],
    "Browse, filter and save what catches your eye. Your waiter will take the order.":
      ["Menyuya baxın, filtr edin və bəyəndiyiniz yeməkləri yadda saxlayın. Sifarişi ofisiantınız qəbul edəcək.",
       "Просматривайте меню, используйте фильтры и сохраняйте понравившиеся блюда. Заказ примет ваш официант."],

    "Still water": ["Qazsız su", "Вода без газа"],
    "ask the team": ["komandaya bildirin", "попросить персонал"],
    "Cutlery": ["Çəngəl-bıçaq", "Столовые приборы"],
    "extra sets": ["əlavə dəst", "дополнительный комплект"],
    "A waiter": ["Ofisiant", "Официант"],
    "someone will come": ["ofisiant yaxınlaşacaq", "к вам подойдут"],
    "The bill": ["Hesab", "Счёт"],
    "ask your waiter": ["ofisiantdan istəyin", "попросить официанта"],
    "Manager": ["Menecer", "Менеджер"],
    "ask for a manager": ["menecer çağırın", "позвать менеджера"],
    "Complaint": ["Şikayət", "Жалоба"],
    "tell management": ["rəhbərliyə bildirin", "сообщить руководству"],

    "Search dishes or ingredients":
      ["Yemək və ya inqrediyent axtar", "Поиск блюда или ингредиента"],

    "Not sure what to choose?":
      ["Nə seçəcəyinizə əmin deyilsiniz?", "Не знаете, что выбрать?"],

    "Ask about ingredients, dietary needs or pairings. Nothing is ordered from this screen.":
      ["İnqrediyentlər, pəhriz tələbləri və uyğun seçimlər haqqında soruşun. Bu ekrandan sifariş göndərilmir.",
       "Спросите об ингредиентах, диетических требованиях или сочетаниях. С этого экрана заказ не отправляется."],

    "Something light but high protein":
      ["Yüngül və zülalı yüksək bir şey", "Что-нибудь лёгкое и с высоким содержанием белка"],

    "Ask": ["Soruş", "Спросить"],
    "What's vegan?": ["Hansı yeməklər vegandır?", "Что есть веганского?"],
    "Nothing with nuts": ["Qoz-fındıqsız", "Без орехов"],
    "What wine goes with the sea bass?":
      ["Dəniz levreyi ilə hansı şərab uyğundur?", "Какое вино подойдёт к сибасу?"],
    "Gluten free dessert":
      ["Qlütensiz desert", "Десерт без глютена"],

    "For severe allergies, always speak directly with your waiter. Saved dishes are a shortlist only and are never sent to the kitchen.":
      ["Ciddi allergiyalar zamanı mütləq birbaşa ofisiantla danışın. Yadda saxlanılan yeməklər yalnız seçim siyahısıdır və mətbəxə göndərilmir.",
       "При серьёзной аллергии обязательно поговорите непосредственно с официантом. Сохранённые блюда — только список вариантов и не отправляются на кухню."],

    "Saved dishes": ["Yadda saxlanılan yeməklər", "Сохранённые блюда"],
    "Your shortlist to show your waiter.":
      ["Ofisianta göstərə biləcəyiniz seçimlər.", "Ваш список блюд для официанта."],

    "Saving a dish does not place an order. Your waiter confirms every item, modifier and allergy with you.":
      ["Yeməyi yadda saxlamaq sifariş yaratmır. Ofisiant bütün yeməkləri, dəyişiklikləri və allergiyaları sizinlə təsdiqləyir.",
       "Сохранение блюда не оформляет заказ. Официант подтверждает с вами каждую позицию, изменение и аллергию."],

    "Good to know": ["Faydalı məlumat", "Полезная информация"],
    "Useful information without replacing human service.":
      ["Canlı xidməti əvəz etməyən faydalı məlumat.", "Полезная информация, не заменяющая живое обслуживание."],

    "Need something?": ["Nəsə lazımdır?", "Что-нибудь нужно?"],

    "Use menu filters for browsing, then tell your waiter about any allergy before ordering.":
      ["Menyu filtrlərindən istifadə edin və sifarişdən əvvəl bütün allergiyalar barədə ofisianta məlumat verin.",
       "Используйте фильтры меню и обязательно сообщите официанту об аллергиях до заказа."],

    "Water, cutlery, your waiter and the bill can be requested from the Menu screen.":
      ["Su, çəngəl-bıçaq, ofisiant və hesabı Menyu ekranından istəyə bilərsiniz.",
       "Воду, приборы, официанта и счёт можно запросить на экране меню."],

    "Ordering": ["Sifariş", "Заказ"],

    "Menu": ["Menyu", "Меню"],
    "Saved": ["Yadda saxlanılan", "Сохранённые"],
    "Info": ["Məlumat", "Информация"],

    "Save to my selections":
      ["Seçimlərimə əlavə et", "Сохранить в мои варианты"],
    "Remove from saved":
      ["Yadda saxlanılandan sil", "Удалить из сохранённых"],
    "Back to menu":
      ["Menyuya qayıt", "Вернуться в меню"],

    /* ---------- WAITER APP ---------- */

    "Opening waiter access…":
      ["Ofisiant girişi açılır…", "Открываем доступ официанта…"],
    "Loading your team.":
      ["Heyətiniz yüklənir.", "Загружаем вашу команду."],

    "Good morning": ["Sabahınız xeyir", "Доброе утро"],
    "Good afternoon": ["Günortanız xeyir", "Добрый день"],
    "Good evening": ["Axşamınız xeyir", "Добрый вечер"],

    "My section": ["Mənim bölməm", "Моя секция"],
    "Where you're needed": ["Harada sizə ehtiyac var", "Где вы нужны"],
    "Tasks": ["Tapşırıqlar", "Задачи"],
    "Order": ["Sifariş", "Заказ"],
    "Profile": ["Profil", "Профиль"],

    "No active tables assigned to you yet.":
      ["Hələ sizə aktiv masa təyin edilməyib.",
       "Вам пока не назначены активные столы."],

    "Blue tables are yours. Coloured rings show requests and food ready at the pass.":
      ["Mavi masalar sizindir. Rəngli halqalar sorğuları və servisə hazır yeməkləri göstərir.",
       "Синие столы назначены вам. Цветные кольца показывают запросы гостей и готовые блюда."],

    "Guest called you": ["Qonaq sizi çağırır", "Гость вызывает вас"],
    "Guest requested a manager":
      ["Qonaq menecer istəyib", "Гость попросил менеджера"],
    "Guest complaint": ["Qonaq şikayəti", "Жалоба гостя"],
    "Manager requested": ["Menecer çağırışı", "Вызов менеджера"],

    "Send order to kitchen":
      ["Sifarişi mətbəxə göndər", "Отправить заказ на кухню"],
    "Send course": ["Kursu göndər", "Отправить курс"],
    "Keep draft": ["Qaralamanı saxla", "Сохранить черновик"],
    "Kitchen note": ["Mətbəx qeydi", "Заметка для кухни"],
    "No Sauce": ["Sous olmasın", "Без соуса"],
    "No butter": ["Kərə yağı olmasın", "Без сливочного масла"],
    "No dairy": ["Süd məhsulları olmasın", "Без молочных продуктов"],
    "No garlic": ["Sarımsaq olmasın", "Без чеснока"],
    "No onion": ["Soğan olmasın", "Без лука"],
    "No salt": ["Duz olmasın", "Без соли"],
    "Medium Rare": ["Az-orta bişmiş", "Medium rare"],
    "Medium": ["Orta bişmiş", "Medium"],
    "Medium Well": ["Orta-yaxşı bişmiş", "Medium well"],

    "AI CHECK": ["AI YOXLAMA", "AI-ПРОВЕРКА"],
    "AI Order Inspector":
      ["AI Sifariş Yoxlayıcısı", "AI-проверка заказа"],
    "No order risks detected.":
      ["Sifariş üzrə risk aşkarlanmadı.", "Риски в заказе не обнаружены."],

    "Nothing ordered yet":
      ["Hələ heç nə sifariş edilməyib", "Пока ничего не заказано"],
    "Nothing ordered yet.":
      ["Hələ heç nə sifariş edilməyib.", "Пока ничего не заказано."],

    "Nothing waiting.":
      ["Gözləyən yoxdur.", "Ничего не ожидает."],
    "Nothing waiting at the pass.":
      ["Servisə hazır gözləyən yemək yoxdur.", "На выдаче ничего не ожидает."],

    "Take payment":
      ["Ödənişi qəbul et", "Принять оплату"],
    "Card": ["Kart", "Карта"],
    "Cash": ["Nağd", "Наличные"],
    "Tip": ["Çaypulu", "Чаевые"],
    "No tip": ["Çaypulu yoxdur", "Без чаевых"],
    "Amount": ["Məbləğ", "Сумма"],

    /* ---------- KITCHEN ---------- */

    "KITCHEN PASS": ["MƏTBƏX SERVİSİ", "КУХОННАЯ ВЫДАЧА"],
    "Kitchen pressure": ["Mətbəx yükü", "Загрузка кухни"],
    "Kitchen load": ["Mətbəx yükü", "Загрузка кухни"],
    "Ready": ["Hazırdır", "Готово"],
    "Cooking": ["Hazırlanır", "Готовится"],
    "Waiting": ["Gözləyir", "Ожидает"],
    "Fire now": ["İndi başla", "Начать сейчас"],

    /* ---------- MENU MANAGEMENT ---------- */

    "Add dish": ["Yemək əlavə et", "Добавить блюдо"],
    "Add section": ["Bölmə əlavə et", "Добавить раздел"],
    "Add menu section": ["Menyu bölməsi əlavə et", "Добавить раздел меню"],
    "Dish name · English": ["Yeməyin adı · İngiliscə", "Название блюда · Английский"],
    "Name · Azerbaijani": ["Ad · Azərbaycanca", "Название · Азербайджанский"],
    "Name · Russian": ["Ad · Rusca", "Название · Русский"],
    "Description · English": ["Təsvir · İngiliscə", "Описание · Английский"],
    "Description · Azerbaijani": ["Təsvir · Azərbaycanca", "Описание · Азербайджанский"],
    "Description · Russian": ["Təsvir · Rusca", "Описание · Русский"],
    "Photo": ["Foto", "Фото"],
    "Upload photo": ["Foto yüklə", "Загрузить фото"],
    "Save dish": ["Yeməyi yadda saxla", "Сохранить блюдо"],
    "Mark unavailable": ["Mövcud deyil kimi qeyd et", "Снять с продажи"],
    "Mark unavailable now": ["İndi satışdan çıxar", "Снять с продажи сейчас"],
    "Manage active dishes": ["Aktiv yeməkləri idarə et", "Управление активными блюдами"],

    /* ---------- INVENTORY / BUSINESS ---------- */

    "Ingredient": ["İnqrediyent", "Ингредиент"],
    "Needed": ["Lazımdır", "Требуется"],
    "Revenue": ["Gəlir", "Выручка"],
    "Gross margin": ["Ümumi marja", "Валовая маржа"],
    "Food cost": ["Məhsul maya dəyəri", "Себестоимость продуктов"],
    "Guest satisfaction": ["Qonaq məmnunluğu", "Удовлетворённость гостей"],

    /* ---------- EMPTY STATES ---------- */

    "No data yet.": ["Hələ məlumat yoxdur.", "Данных пока нет."],
    "Nothing to show yet.": ["Hələ göstəriləcək heç nə yoxdur.", "Пока нечего показывать."],
    "Nothing open.": ["Açıq heç nə yoxdur.", "Ничего открытого."],
    "Nothing booked for this day.":
      ["Bu gün üçün rezervasiya yoxdur.", "На этот день бронирований нет."],
    "No upcoming bookings.":
      ["Yaxın rezervasiya yoxdur.", "Предстоящих бронирований нет."],
    "All quiet.": ["Hər şey sakitdir.", "Всё спокойно."],
    "Everything is available.":
      ["Hər şey mövcuddur.", "Всё доступно."]
  };

  Object.assign(T, window.SUFRA_CORE_TRANSLATIONS || {}, window.SUFRA_TRANSLATIONS || {});
  const folded = new Map(Object.keys(T).map(key => [key.toLocaleLowerCase(), key]));

  function translateExact(text, lang) {
    if (!text || lang === "en") return null;

    const cleaned = String(text).trim().replace(/\s+/g, " ");
    if (!cleaned) return null;

    const row = T[cleaned] || T[folded.get(cleaned.toLocaleLowerCase())];
    if (row) return lang === "az" ? row[0] : row[1];

    let m;

    if ((m = cleaned.match(/^Table\s+(\d+)$/i))) {
      return lang === "az" ? `Masa ${m[1]}` : `Стол ${m[1]}`;
    }

    if ((m = cleaned.match(/^Table\s+(\d+)\s+QR\s+link$/i))) {
      return lang === "az"
        ? `Masa ${m[1]} QR keçidi`
        : `QR-ссылка стола ${m[1]}`;
    }

    if ((m = cleaned.match(/^(\d+) seats$/i))) {
      return lang === "az"
        ? `${m[1]} yer`
        : `${m[1]} мест`;
    }

    if ((m = cleaned.match(/^(\d+) guests$/i))) {
      return lang === "az"
        ? `${m[1]} qonaq`
        : `${m[1]} гостей`;
    }

    if ((m = cleaned.match(/^(\d+) bookings$/i))) {
      return lang === "az"
        ? `${m[1]} rezervasiya`
        : `${m[1]} бронирований`;
    }

    if ((m = cleaned.match(/^(\d+) min$/i))) {
      return lang === "az"
        ? `${m[1]} dəq`
        : `${m[1]} мин`;
    }

    if ((m = cleaned.match(/^(\d+)m$/i))) {
      return lang === "az"
        ? `${m[1]} dəq`
        : `${m[1]} мин`;
    }

    if ((m = cleaned.match(/^Table\s+(\d+)\s+has\s+a\s+(.+)\s+restriction\.$/i))) {
      return lang === "az"
        ? `Masa ${m[1]} üçün ${m[2]} məhdudiyyəti var.`
        : `У стола ${m[1]} ограничение: ${m[2]}.`;
    }

    if ((m = cleaned.match(/^Manager requested\s+·\s+Table\s+(\d+)$/i))) {
      return lang === "az"
        ? `Menecer çağırışı · Masa ${m[1]}`
        : `Вызов менеджера · Стол ${m[1]}`;
    }

    if ((m = cleaned.match(/^Guest complaint\s+·\s+Table\s+(\d+)$/i))) {
      return lang === "az"
        ? `Qonaq şikayəti · Masa ${m[1]}`
        : `Жалоба гостя · Стол ${m[1]}`;
    }

    if ((m = cleaned.match(/^ORDER CHANGE\s+·\s+Table\s+(\d+)$/i))) {
      return lang === "az"
        ? `SİFARİŞ DƏYİŞİKLİYİ · Masa ${m[1]}`
        : `ИЗМЕНЕНИЕ ЗАКАЗА · Стол ${m[1]}`;
    }

    return translateParts(cleaned, lang);
  }

  function translateParts(text, lang) {
    const az = lang === 'az';
    const tr = value => translateExact(value, lang) || value;
    let m;
    // Preserve IDs, URLs, names and user-entered content; translate UI patterns.
    if (/^(?:https?:|mailto:|\/)/.test(text)) return null;
    if ((m=text.match(/^([+⊘♡＋✓←→]\s*)(.+)$/))) return m[1]+tr(m[2]);
    if ((m=text.match(/^(.+?)\s*\((\d+)\)$/))) return tr(m[1])+' ('+m[2]+')';
    if ((m=text.match(/^(.+?):$/))) return tr(m[1])+':';
    if ((m=text.match(/^(.+) is (\d+)% of waste value$/))) return az?`${tr(m[1])} itki dəyərinin ${m[2]}%-ni təşkil edir`:`${tr(m[1])}: ${m[2]}% стоимости списаний`;
    if ((m=text.match(/^(₼[\d.,-]+) of (₼[\d.,-]+) wasted over (\d+) days came from (.+)\.$/))) return az?`${m[3]} gündə ${m[2]} itkinin ${m[1]} hissəsi ${tr(m[4])} üzrədir.`:`Из ${m[2]} списаний за ${m[3]} дней на ${tr(m[4])} приходится ${m[1]}.`;
    if ((m=text.match(/^(.+) accounts for (\d+)% of waste$/))) return az?`${tr(m[1])}: itkinin ${m[2]}%-i`:`${tr(m[1])}: ${m[2]}% списаний`;
    if ((m=text.match(/^(₼[\d.,-]+) of waste is logged on (\w+)s\. Compare (\w+) ordering against actual (\w+) covers before the next delivery\.$/))) return az?`${tr(m[2])}: ${m[1]} itki. Növbəti tədarükdən əvvəl bu günün alışlarını faktiki qonaq sayı ilə müqayisə edin.`:`${tr(m[2])}: списания ${m[1]}. Перед следующей поставкой сравните закупки на этот день с фактическим числом гостей.`;
    if ((m=text.match(/^(.+) is the single largest wasted line$/))) return az?`${tr(m[1])} ən böyük itki maddəsidir`:`${tr(m[1])} — крупнейшая позиция списаний`;
    if ((m=text.match(/^(₼[\d.,-]+) over (\d+) days\. Check par level, order frequency and prep batch size for this item\.$/))) return az?`${m[2]} gündə ${m[1]}. Ehtiyat normasını, sifariş tezliyini və hazırlıq partiyasının həcmini yoxlayın.`:`${m[1]} за ${m[2]} дней. Проверьте норму запаса, частоту заказов и размер заготовок.`;
    if ((m=text.match(/^(.+) runs at ([\d.]+)% food cost$/))) return az?`${tr(m[1])}: qida maya dəyəri ${m[2]}%`:`${tr(m[1])}: себестоимость продуктов ${m[2]}%`;
    if ((m=text.match(/^(₼[\d.,-]+) of ingredients against a (₼[\d.,-]+) menu price \((₼[\d.,-]+) contribution\)\. House average is ([\d.]+)%\.$/))) return az?`İnqrediyentlər ${m[1]}, menyu qiyməti ${m[2]} (marjinal gəlir ${m[3]}). Restoran üzrə orta göstərici ${m[4]}%.`:`Ингредиенты ${m[1]}, цена меню ${m[2]} (маржинальный доход ${m[3]}). Среднее по ресторану ${m[4]}%.`;
    if ((m=text.match(/^(.+) now costs more than the menu assumes$/))) return az?`${tr(m[1])}: maya dəyəri menyudakı hesablamanı aşıb`:`${tr(m[1])}: себестоимость выше заложенной в меню`;
    if ((m=text.match(/^Recipe cost is (₼[\d.,-]+) against the (₼[\d.,-]+) the menu was priced on — ([\d.]+)% higher\.$/))) return az?`Reseptin maya dəyəri ${m[1]}, menyuda əsas götürülən ${m[2]} — ${m[3]}% yüksəkdir.`:`Себестоимость рецепта ${m[1]} вместо заложенных в меню ${m[2]} — на ${m[3]}% выше.`;
    if ((m=text.match(/^House average ([\d.]+)% across (\d+) costed dishes\.$/))) return az?`${m[2]} hesablanmış yemək üzrə orta göstərici ${m[1]}%.`:`Среднее по ${m[2]} рассчитанным блюдам: ${m[1]}%.`;
    if ((m=text.match(/^Forecast confidence: (\w+)(.*)$/))) return (az?'Proqnoz etibarlılığı: ':'Уверенность прогноза: ')+tr(m[1])+(m[2].startsWith(' · ')?' · '+tr(m[2].slice(3)):tr(m[2]));
    if ((m=text.match(/^generated (.+)$/))) return (az?'yaradılıb ':'создано ')+m[1];
    if (text==='. Where history is thin, Anbar gives a rules-based recommendation and says so rather than inventing precision.') return az?'. Tarixçə az olduqda, anbar qaydalara əsaslanan tövsiyə verir və bunu açıq bildirir.':'. Если истории мало, склад даёт рекомендацию по правилам и явно сообщает об этом.';
    if ((m=text.match(/^(\d+) covers booked$/))) return az?`${m[1]} qonaq rezerv edilib`:`Забронировано гостей: ${m[1]}`;
    if ((m=text.match(/^(\d+) expected including walk-ins\.$/))) return az?`Rezervasiyasız gələnlərlə birlikdə ${m[1]} qonaq gözlənilir.`:`Ожидается ${m[1]} гостей, включая визиты без брони.`;
    if ((m=text.match(/^debits = (₼[\d.,-]+) credits$/))) return az?`debet = ${m[1]} kredit`:`дебет = кредит ${m[1]}`;
    if ((m=text.match(/^Tonight tracks (\d+)% (above|below) a typical (\w+)$/))) return az?`Bu axşam proqnoz adi ${tr(m[3])} göstəricisindən ${m[1]}% ${m[2]==='above'?'yuxarıdır':'aşağıdır'}`:`Сегодня прогноз на ${m[1]}% ${m[2]==='above'?'выше':'ниже'} обычного уровня (${tr(m[3])})`;
    if ((m=text.match(/^Forecast ([£₼][\d,.]+) against a usual ([£₼][\d,.]+)\. (\d+) covers already booked\.$/))) return az?`Proqnoz ${m[1]}, adi göstərici ${m[2]}. ${m[3]} qonaq artıq rezerv edilib.`:`Прогноз ${m[1]}, обычный уровень ${m[2]}. Уже забронировано ${m[3]} гостей.`;
    if ((m=text.match(/^(.+) closed with (₼[\d.,-]+) variance$/))) return az?`${m[1]} sayımı ${m[2]} fərqlə bağlanıb`:`${m[1]} закрыта с расхождением ${m[2]}`;
    if ((m=text.match(/^(\d+) lines adjusted\. Worth reviewing the largest differences before the next count\.$/))) return az?`${m[1]} sətir düzəldilib. Növbəti sayımdan əvvəl ən böyük fərqləri yoxlayın.`:`Скорректировано позиций: ${m[1]}. Перед следующей инвентаризацией проверьте крупнейшие расхождения.`;
    if ((m=text.match(/^Above (₼[\d.,-]+) an order needs owner or GM approval\.$/))) return az?`${m[1]} məbləğindən yuxarı sifariş sahibkar və ya baş menecer təsdiqi tələb edir.`:`Заказ свыше ${m[1]} требует одобрения владельца или генерального менеджера.`;
    if ((m=text.match(/^Basis: settled bills over the last (\d+) days\. Total (₼[\d.,-]+)\. Nothing is ordered until a manager raises and approves it\.$/))) return az?`Əsas: son ${m[1]} günün ödənilmiş hesabları. Cəmi ${m[2]}. Menecer yaratmadan və təsdiqləmədən sifariş verilmir.`:`Основание: оплаченные счета за ${m[1]} дней. Итого ${m[2]}. Заказ размещается после создания и одобрения менеджером.`;
    if ((m=text.match(/^(₼[\d.,-]+) over (\d+) days$/))) return az?`${m[2]} gündə ${m[1]}`:`${m[1]} за ${m[2]} дней`;
    if ((m=text.match(/^([\d.]+)% of purchases\.$/))) return m[1]+(az?'% alışlardan.':'% закупок.');
    if ((m=text.match(/^(.+): (\d+) ingredients, cost (₼[\d.,-]+)$/))) return az?`${tr(m[1])}: ${m[2]} inqrediyent, maya dəyəri ${m[3]}`:`${tr(m[1])}: ${m[2]} ингредиентов, себестоимость ${m[3]}`;
    if (text.includes(' · ')) return text.split(' · ').map(tr).join(' · ');
    if (text.includes(' → ')) return text.split(' → ').map(tr).join(' → ');
    if ((m=text.match(/^(general|restaurant|inventory)_manager$/i))) return tr(m[1]+' manager');
    if ((m=text.match(/^(.+) — (SUFRA|NOVA)$/))) return tr(m[1])+' — SUFRA';
    if ((m=text.match(/^SECTION ([A-Z])$/i))) return (az?'BÖLMƏ ':'СЕКЦИЯ ')+m[1];
    if ((m=text.match(/^QR code for Table (\d+)$/))) return az?`Masa ${m[1]} üçün QR kod`:`QR-код стола ${m[1]}`;
    if ((m=text.match(/^(\d+) h(?: (\d+))?$/))) return az?`${m[1]} saat${m[2]?' '+m[2]+' dəq':''}`:`${m[1]} ч${m[2]?' '+m[2]+' мин':''}`;
    if ((m=text.match(/^(\d+) hours?$/))) return m[1]+(az?' saat':' ч');
    if ((m=text.match(/^([\d.,]+)\s*(kg|ml|unit|pcs|g|l)$/))) return m[1]+' '+tr(m[2]);
    if ((m=text.match(/^([\d.,]+)m$/))) return m[1]+(az?' dəq':' мин');
    if ((m=text.match(/^(\d+)\/(\d+) in service$/))) return az?`${m[1]}/${m[2]} xidmətdə`:`Обслуживается ${m[1]} из ${m[2]}`;
    if ((m=text.match(/^oldest (\d+)m$/))) return az?`ən köhnə ${m[1]} dəq`:`самому давнему ${m[1]} мин`;
    if ((m=text.match(/^(\d+) on shift(?: now)?$/))) return az?`${m[1]} nəfər növbədə`:`На смене: ${m[1]}`;
    if ((m=text.match(/^([\d.,-]+)% (full|margin|risk|of sales)$/))) {
      const labels={full:['doludur','заполнено'],margin:['marja','маржа'],risk:['risk','риск'],'of sales':['satışdan','от продаж']};
      return m[1]+'% '+labels[m[2]][az?0:1];
    }
    if ((m=text.match(/^(\d+) (items|employees|tables|orders|covers|lines|ingredients|suppliers|transfers|counts|entries|days?|deliveries recorded|forecast covers|reservations|unavailable)$/))) {
      const labels={items:['məhsul','позиций'],employees:['əməkdaş','сотрудников'],tables:['masa','столов'],orders:['sifariş','заказов'],covers:['qonaq','гостей'],lines:['sətir','позиций'],ingredients:['inqrediyent','ингредиентов'],suppliers:['təchizatçı','поставщиков'],transfers:['köçürmə','перемещений'],counts:['sayım','инвентаризаций'],entries:['qeyd','записей'],day:['gün','дней'],days:['gün','дней'],'deliveries recorded':['qeydə alınmış çatdırılma','записанных поставок'],'forecast covers':['proqnoz qonaq','гостей по прогнозу'],reservations:['rezervasiya','бронирований'],unavailable:['mövcud deyil','нет в наличии']};
      return m[1]+' '+labels[m[2]][az?0:1];
    }
    if ((m=text.match(/^(Out of stock|Expired|Critical|Expiring soon|Low|Over-stocked|Healthy):? (\d+)$/i))) return tr(m[1])+': '+m[2];
    if ((m=text.match(/^(Flagged|Quality issue on|Shortage reported|requested by|received by|by|invoice|transfer|stocktake):? (.+)$/i))) {
      const labels={flagged:['Qeyd edilib','Отмечено'],'quality issue on':['Keyfiyyət problemi','Проблема качества'],'shortage reported':['Çatışmazlıq bildirilib','Сообщение о нехватке'],'requested by':['Sorğu verən','Запросил'],'received by':['Qəbul edən','Принял'],by:['Tərəfindən','Автор'],invoice:['Faktura','Счёт'],transfer:['Köçürmə','Перемещение'],stocktake:['Sayım','Инвентаризация']};
      return labels[m[1].toLowerCase()][az?0:1]+': '+tr(m[2]);
    }
    if ((m=text.match(/^(₼[\d.,-]+) (sales|contribution|at risk|this week|beyond expected use)$/))) {
      const labels={sales:['satış','продаж'],contribution:['marjinal gəlir','маржинального дохода'],'at risk':['risk altındadır','под риском'],'this week':['bu həftə','за неделю'],'beyond expected use':['gözlənilən sərfdən artıq','сверх ожидаемого расхода']};return m[1]+' '+labels[m[2]][az?0:1];
    }
    if ((m=text.match(/^Demand ([+-]\d+%)$/))) return (az?'Tələb ':'Спрос ')+m[1];
    if ((m=text.match(/^(.+) per (kg|unit|l)$/))) return m[1]+(az?' / ':' за ')+tr(m[2]);
    if ((m=text.match(/^([0-9-]+) to ([0-9-]+)$/))) return m[1]+' — '+m[2];
    if ((m=text.match(/^(.+?) separate secure settlement window$/))) return tr(m[1])+(az?' ayrıca təhlükəsiz ödəniş pəncərəsi':' отдельное защищённое окно оплаты');
    const months={Jan:['yan','янв.'],Feb:['fev','февр.'],Mar:['mar','мар.'],Apr:['apr','апр.'],May:['may','мая'],Jun:['iyn','июн.'],Jul:['iyl','июл.'],Aug:['avq','авг.'],Sep:['sen','сент.'],Oct:['okt','окт.'],Nov:['noy','нояб.'],Dec:['dek','дек.']};
    if ((m=text.match(/^(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(.*)$/))) return m[1]+' '+months[m[2]][az?0:1]+m[3];
    return null;
  }

  function translateNode(node) {
    const lang = getLang();
    if (lang === "en") return;

    if (
      !node ||
      !node.parentElement ||
      node.parentElement.closest(
        "script, style, code, pre, textarea, .nova-lang-global, #command-lang, [data-i18n-skip], [translate=no]"
      )
    ) return;

    // Labels may be translated, but their submitted enum values must stay stable.
    const option = node.parentElement.closest("option");
    if (option && !option.hasAttribute("value")) option.value = option.textContent;
    const raw = node.nodeValue;
    const stripped = raw.trim();

    if (!stripped) return;

    const translated = translateExact(stripped, lang);

    if (translated && translated !== stripped) {
      node.nodeValue = raw.replace(stripped, translated);
    }
  }

  function translateAttributes(root) {
    const lang = getLang();
    if (lang === "en") return;

    root.querySelectorAll?.(
      "[placeholder], [title], [aria-label], [alt], [data-label], option"
    ).forEach(el => {
      ["placeholder", "title", "aria-label", "alt", "data-label"].forEach(attr => {
        const raw = el.getAttribute?.(attr);
        if (!raw) return;

        const translated = translateExact(raw.trim(), lang);
        if (translated) el.setAttribute(attr, translated);
      });

      if (el.tagName === "OPTION") {
        const raw = el.textContent.trim();
        const translated = translateExact(raw, lang);
        if (translated) el.textContent = translated;
      }
    });
  }

  function apply(root = document.body) {
    if (!root) return;

    const lang = getLang();

    document.documentElement.lang =
      lang === "az" ? "az" :
      lang === "ru" ? "ru" : "en";

    if (lang === "en") return;

    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );

    let node;
    while ((node = walker.nextNode())) {
      translateNode(node);
    }

    translateAttributes(root);
    const title = translateExact(document.title, lang);
    if (title && title !== document.title) document.title = title;
  }

  let mutationTimer;

  function start() {
    apply();

    const observer = new MutationObserver(() => {
      // Scan the final DOM once per batch. Looking only at the last batch's
      // addedNodes lost earlier inserts and all textContent/attribute updates.
      clearTimeout(mutationTimer);
      mutationTimer = setTimeout(() => {
        observer.disconnect();
        apply();
        observe();
      }, 25);
    });
    const observe = () => observer.observe(document.body, {
      childList: true, subtree: true, characterData: true, attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label", "alt", "data-label"]
    });
    observe();

    window.addEventListener("nova-language-changed", () => {
      setTimeout(() => apply(), 10);
    });

    window.addEventListener("storage", e => {
      if (
        e.key === "nova-lang" ||
        e.key === "nova-command-lang"
      ) {
        setTimeout(() => apply(), 10);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start, {once: true});
  } else {
    start();
  }

  window.SUFRA_FINAL_I18N = {
    apply,
    translate: text => translateExact(text, getLang())
  };
})();
