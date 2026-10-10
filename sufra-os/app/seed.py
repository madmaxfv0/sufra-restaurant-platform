"""
Demo data for a 30-table waterfront restaurant in Baku.

Two things matter here:
1. The floor plan is hand-placed, not random — a random scatter looks fake.
2. We generate 180 days of trading history with *real structure* in it
   (weekday effect, rain effect, seasonality, noise). The forecasting model
   in intelligence.py has to have a signal to find, or the whole
   "predictive" layer is theatre.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from .database import create_db, engine
from .models import (
    DayStat, DiningTable, Feedback, Guest, Ingredient, ItemState, MenuItem,
    Order, OrderItem, RecipeLine, Reservation, Role, Staff, Station,
    TableStatus, WasteLog,
)
from .security import hash_pin

rng = random.Random(7)   # fixed seed = the demo looks the same every run


# ---------------------------------------------------------------- floor plan
# (number, seats, zone, x, y, shape) — x/y are fractions of the room.

FLOOR = [
    # Terrace, along the top
    (1, 2, "Terrace", 0.09, 0.12, "round"), (2, 2, "Terrace", 0.21, 0.12, "round"),
    (3, 4, "Terrace", 0.33, 0.12, "square"), (4, 4, "Terrace", 0.46, 0.12, "square"),
    (5, 2, "Terrace", 0.58, 0.12, "round"), (6, 6, "Terrace", 0.72, 0.13, "banquette"),
    # Main room, two ranks
    (7, 2, "Main", 0.12, 0.34, "round"), (8, 2, "Main", 0.24, 0.34, "round"),
    (9, 4, "Main", 0.37, 0.35, "square"), (10, 4, "Main", 0.50, 0.35, "square"),
    (11, 2, "Main", 0.63, 0.34, "round"), (12, 6, "Main", 0.78, 0.35, "banquette"),
    (13, 2, "Main", 0.12, 0.52, "round"), (14, 4, "Main", 0.25, 0.53, "square"),
    (15, 4, "Main", 0.38, 0.53, "square"), (16, 4, "Main", 0.51, 0.53, "square"),
    (17, 2, "Main", 0.64, 0.52, "round"), (18, 6, "Main", 0.78, 0.53, "banquette"),
    (19, 2, "Main", 0.12, 0.70, "round"), (20, 2, "Main", 0.24, 0.70, "round"),
    (21, 4, "Main", 0.37, 0.71, "square"), (22, 4, "Main", 0.50, 0.71, "square"),
    (23, 8, "Main", 0.66, 0.71, "banquette"),
    # Bar counter, bottom left
    (24, 2, "Bar", 0.11, 0.88, "round"), (25, 2, "Bar", 0.21, 0.88, "round"),
    (26, 2, "Bar", 0.31, 0.88, "round"), (27, 2, "Bar", 0.41, 0.88, "round"),
    # Private dining
    (28, 10, "Private", 0.88, 0.15, "banquette"),
    (29, 6, "Private", 0.88, 0.42, "banquette"),
    (30, 4, "Private", 0.88, 0.68, "square"),
]

# name, role, avatar initial, section (where the role has one)
STAFF = [
    ("Amira Osei", Role.OWNER, "A", ""),
    ("Daniel Voss", Role.GENERAL_MANAGER, "D", ""),
    ("Elena Rossi", Role.RESTAURANT_MANAGER, "E", ""),
    ("Leyla Huseynova", Role.HOST, "L", "Front desk"),
    ("Sofia Marchetti", Role.WAITER, "S", "Section A"),
    ("Tomas Novak", Role.WAITER, "T", "Section A"),
    ("Omar Haddad", Role.WAITER, "O", "Section A"),
    ("Aya Karim", Role.WAITER, "A", "Section B"),
    ("Luca Ferrari", Role.WAITER, "L", "Section B"),
    ("Nina Petrova", Role.WAITER, "N", "Section C"),
    ("Ravi Menon", Role.WAITER, "R", "Section C"),
    ("Chloe Dupont", Role.WAITER, "C", "Terrace"),
    ("Jonas Weber", Role.WAITER, "J", "Terrace"),
    ("Maya Osei", Role.WAITER, "M", "Private dining"),
    ("Hiroshi Tanaka", Role.KITCHEN, "H", ""),
    ("Pierre Laurent", Role.KITCHEN, "P", ""),
    ("Sara Ahmadi", Role.KITCHEN, "S", ""),
    ("Dmitri Volkov", Role.KITCHEN, "D", ""),
    ("Grace Owusu", Role.KITCHEN, "G", ""),
    ("Ben Carter", Role.BARTENDER, "B", "Bar"),
    ("Zoe Lindqvist", Role.BARTENDER, "Z", "Bar"),
    ("Marcus Bell", Role.CASHIER, "M", "Front desk"),
    ("Priya Nair", Role.INVENTORY_MANAGER, "P", ""),
]

# name, course, station, price, cost, minutes, tags, protein, kcal, blurb
MENU = [
    ("Oyster & Champagne Mignonette", "Snack", Station.COLD, 4.5, 1.4, 3, "gf,shellfish", 4, 40, "Six from Carlingford, three ways."),
    ("Gordal Olives", "Snack", Station.COLD, 6, 1.1, 2, "vegan,gf", 1, 90, "Warmed with orange peel."),
    ("Sourdough & Cultured Butter", "Snack", Station.PASTRY, 7, 1.2, 4, "vegetarian,gluten", 6, 320, "Two-day ferment, house butter."),
    ("Burrata, Datterini, Basil Oil", "Starter", Station.COLD, 17, 4.8, 6, "vegetarian,gf,dairy", 14, 380, "Puglian burrata, still warm."),
    ("Tuna Crudo, Yuzu, Sesame", "Starter", Station.COLD, 21, 7.2, 7, "gf,fish,sesame", 24, 220, "Line-caught, cured four hours."),
    ("Hand-Dived Scallop", "Starter", Station.GRILL, 24, 9.1, 9, "gf,shellfish", 18, 260, "Grilled in the shell, brown butter."),
    ("Beef Tartare, Smoked Yolk", "Starter", Station.COLD, 19, 6.0, 8, "gf,egg", 26, 340, "Hand-cut sirloin, aged eight weeks."),
    ("Wild Mushroom Croquette", "Starter", Station.HOT, 14, 3.2, 10, "vegetarian,gluten,dairy", 9, 410, "Girolles, aged comté."),
    ("Vine Tomato & Watermelon", "Starter", Station.COLD, 13, 2.6, 5, "vegan,gf", 3, 150, "Ten varieties, verjus."),
    ("Porcini Risotto", "Main", Station.HOT, 26, 6.4, 18, "vegetarian,gf,dairy", 15, 620, "Carnaroli, 24-month parmesan."),
    ("Grilled Sea Bass, Asparagus", "Main", Station.GRILL, 34, 12.5, 16, "gf,fish", 42, 480, "Whole fillet, Cornish day boat."),
    ("Dover Sole Meunière", "Main", Station.GRILL, 52, 21.0, 20, "gf,fish,dairy", 48, 610, "On the bone, filleted at table."),
    ("Dry-Aged Ribeye 400g", "Main", Station.GRILL, 58, 23.4, 22, "gf", 76, 980, "60-day aged, bone marrow butter."),
    ("Rack of Lamb, Harissa", "Main", Station.GRILL, 41, 15.2, 24, "gf,halal", 52, 720, "Herdwick, north-facing pasture."),
    ("Truffle Tagliatelle", "Main", Station.HOT, 38, 11.0, 14, "vegetarian,gluten,egg,dairy", 18, 780, "Fresh pasta, winter black truffle."),
    ("Lobster Ravioli", "Main", Station.HOT, 44, 19.6, 19, "gluten,shellfish,dairy", 34, 640, "Native lobster, bisque."),
    ("Confit Duck Leg, Cherry", "Main", Station.HOT, 33, 9.8, 21, "gf", 46, 700, "Slow-cooked nine hours."),
    ("Aubergine Katsu", "Main", Station.HOT, 24, 4.4, 15, "vegan,gluten", 12, 560, "Panko crust, curry from scratch."),
    ("Cauliflower Steak, Tahini", "Main", Station.GRILL, 22, 3.8, 17, "vegan,gf,sesame", 11, 430, "Charred whole, pomegranate."),
    ("Roast Chicken for Two", "Main", Station.HOT, 46, 12.0, 35, "gf,halal", 88, 1100, "Landes chicken, forty minutes."),
    ("Triple-Cooked Chips", "Side", Station.HOT, 8, 1.0, 8, "vegan,gf", 5, 380, "Three days in the making."),
    ("Charred Hispi Cabbage", "Side", Station.GRILL, 9, 1.4, 9, "vegetarian,gf,dairy", 6, 210, "Anchovy butter, or without."),
    ("Green Beans, Almond", "Side", Station.HOT, 8, 1.2, 6, "vegan,gf,nuts", 5, 180, "Blanched to order."),
    ("Truffle Mash", "Side", Station.HOT, 10, 2.1, 7, "vegetarian,gf,dairy", 4, 420, "Ratte potato, a lot of butter."),
    ("Chocolate Nemesis", "Dessert", Station.PASTRY, 13, 2.8, 6, "vegetarian,gf,egg,dairy", 7, 540, "Flourless, seventy percent."),
    ("Lemon Tart, Basil", "Dessert", Station.PASTRY, 12, 2.2, 5, "vegetarian,gluten,egg,dairy", 6, 460, "Amalfi lemons, torched."),
    ("Tiramisu al Cucchiaio", "Dessert", Station.PASTRY, 12, 2.4, 5, "vegetarian,gluten,egg,dairy", 8, 500, "Served in the bowl it set in."),
    ("Pistachio Cannolo", "Dessert", Station.PASTRY, 11, 2.0, 4, "vegetarian,gluten,nuts,dairy", 7, 430, "Filled to order, Bronte pistachio."),
    ("Vanilla Ice Cream, Olive Oil", "Dessert", Station.PASTRY, 9, 1.3, 3, "vegetarian,gf,dairy", 4, 300, "Madagascan vanilla, Sicilian oil."),
    ("Cheese, Four Ways", "Dessert", Station.COLD, 16, 5.5, 5, "vegetarian,dairy,nuts", 22, 520, "From La Fromagerie, with quince."),
    ("Negroni Sbagliato", "Drink", Station.BAR, 14, 3.0, 3, "vegan,gf,cocktail", 0, 150, "Prosecco instead of gin."),
    ("Martini, Very Cold", "Drink", Station.BAR, 16, 3.4, 3, "vegan,gf,cocktail", 0, 180, "Stirred fifty turns, lemon or olive."),
    ("Garden Spritz (0%)", "Drink", Station.BAR, 9, 1.6, 3, "vegan,gf,cocktail,zero", 0, 60, "Seedlip, cucumber, elderflower."),
    ("Barolo, Vietti 2018", "Drink", Station.BAR, 88, 34.0, 2, "vegan,gf,wine,red", 0, 620, "Decanted thirty minutes."),
    ("Chablis 1er Cru", "Drink", Station.BAR, 62, 24.0, 2, "vegan,gf,wine,white", 0, 580, "Montmains, mineral and taut."),
    ("Sparkling Water", "Drink", Station.BAR, 5, 0.5, 1, "vegan,gf", 0, 0, "Filtered in-house, refilled free."),
    ("Espresso", "Drink", Station.BAR, 4, 0.4, 2, "vegan,gf", 0, 5, "Single origin, changed monthly."),
    ("Amaro Nonino", "Drink", Station.BAR, 12, 3.2, 1, "vegan,gf,digestif", 0, 130, "For after, not before."),
    ("Whole Turbot to Share", "Main", Station.GRILL, 96, 42.0, 30, "gf,fish", 92, 900, "Two to three people, market price."),
    ("Caviar Service 30g", "Snack", Station.COLD, 120, 58.0, 4, "gf,fish,dairy", 12, 210, "Oscietra, blini, crème fraîche."),
    # Quick-add utility items — the waiter's one-tap favourites row needs
    # these to actually exist as orderable dishes, not just labels.
    ("Still Water", "Drink", Station.BAR, 0, 0.1, 1, "vegan,gf", 0, 0, "Filtered in-house, complimentary."),
    ("Cappuccino", "Drink", Station.BAR, 5, 0.6, 3, "vegetarian,gf", 0, 90, "Double shot, oat milk on request."),
    ("Bread & Butter", "Snack", Station.PASTRY, 6, 1.2, 2, "vegetarian,gluten,dairy", 0, 240, "Sourdough, cultured butter."),
    ("Extra Sauce", "Side", Station.HOT, 0, 0.3, 1, "vegetarian,gf", 0, 30, "A little more on the side."),
]

# name, unit, par level, cost/unit, supplier, store
INGREDIENTS = [
    ("Sea bass fillet", "kg", 14, 22.0, "Cornish Day Boats", "Fish fridge"),
    ("Dover sole", "kg", 8, 38.0, "Cornish Day Boats", "Fish fridge"),
    ("Turbot", "kg", 6, 34.0, "Cornish Day Boats", "Fish fridge"),
    ("Scallops", "kg", 5, 42.0, "Cornish Day Boats", "Fish fridge"),
    ("Tuna loin", "kg", 4, 46.0, "Billingsgate Prime", "Fish fridge"),
    ("Native lobster", "kg", 6, 52.0, "Billingsgate Prime", "Fish fridge"),
    ("Oysters", "unit", 120, 1.1, "Carlingford", "Fish fridge"),
    ("Oscietra caviar", "kg", 0.5, 1600.0, "Attilus", "Fish fridge"),
    ("Ribeye, dry aged", "kg", 18, 28.0, "Turner & Son", "Meat fridge"),
    ("Sirloin", "kg", 8, 24.0, "Turner & Son", "Meat fridge"),
    ("Lamb rack", "kg", 10, 26.0, "Turner & Son", "Meat fridge"),
    ("Duck leg", "kg", 12, 14.0, "Turner & Son", "Meat fridge"),
    ("Chicken, whole", "kg", 16, 9.5, "Turner & Son", "Meat fridge"),
    ("Bone marrow", "kg", 3, 11.0, "Turner & Son", "Meat fridge"),
    ("Burrata", "kg", 6, 18.0, "Sapori d'Italia", "Dairy fridge"),
    ("Parmesan 24mo", "kg", 5, 24.0, "Sapori d'Italia", "Dairy fridge"),
    ("Comté", "kg", 4, 26.0, "La Fromagerie", "Dairy fridge"),
    ("Butter, cultured", "kg", 14, 8.4, "Neal's Yard", "Dairy fridge"),
    ("Double cream", "L", 12, 3.6, "Neal's Yard", "Dairy fridge"),
    ("Mascarpone", "kg", 6, 9.0, "Sapori d'Italia", "Dairy fridge"),
    ("Eggs", "unit", 240, 0.42, "Clarence Court", "Dry store"),
    ("Black truffle", "kg", 0.6, 780.0, "Tartufi Bianchi", "Dairy fridge"),
    ("Girolles", "kg", 4, 32.0, "Wild Harvest", "Veg fridge"),
    ("Porcini, dried", "kg", 2, 88.0, "Wild Harvest", "Dry store"),
    ("Asparagus", "kg", 9, 9.5, "Covent Garden Greens", "Veg fridge"),
    ("Datterini tomato", "kg", 10, 6.2, "Covent Garden Greens", "Veg fridge"),
    ("Vine tomato", "kg", 12, 4.4, "Covent Garden Greens", "Veg fridge"),
    ("Watermelon", "kg", 8, 2.2, "Covent Garden Greens", "Veg fridge"),
    ("Aubergine", "kg", 10, 3.8, "Covent Garden Greens", "Veg fridge"),
    ("Cauliflower", "kg", 12, 2.6, "Covent Garden Greens", "Veg fridge"),
    ("Hispi cabbage", "kg", 10, 2.4, "Covent Garden Greens", "Veg fridge"),
    ("Green beans", "kg", 8, 5.2, "Covent Garden Greens", "Veg fridge"),
    ("Ratte potato", "kg", 20, 3.1, "Covent Garden Greens", "Veg fridge"),
    ("Maris Piper", "kg", 30, 1.4, "Covent Garden Greens", "Dry store"),
    ("Basil", "kg", 2, 22.0, "Covent Garden Greens", "Veg fridge"),
    ("Lemon, Amalfi", "kg", 6, 7.8, "Sapori d'Italia", "Veg fridge"),
    ("Cherries", "kg", 5, 11.0, "Covent Garden Greens", "Veg fridge"),
    ("Pomegranate", "kg", 4, 6.4, "Covent Garden Greens", "Veg fridge"),
    ("Avocado", "unit", 40, 1.3, "Covent Garden Greens", "Veg fridge"),
    ("Pistachio, Bronte", "kg", 2, 46.0, "Sapori d'Italia", "Dry store"),
    ("Almond, flaked", "kg", 3, 14.0, "Sapori d'Italia", "Dry store"),
    ("Chocolate 70%", "kg", 6, 18.0, "Valrhona", "Dry store"),
    ("Vanilla pod", "unit", 60, 3.9, "Valrhona", "Dry store"),
    ("00 flour", "kg", 25, 1.8, "Shipton Mill", "Dry store"),
    ("Sourdough starter", "kg", 4, 0.0, "In-house", "Dry store"),
    ("Carnaroli rice", "kg", 14, 4.6, "Sapori d'Italia", "Dry store"),
    ("Panko", "kg", 6, 3.4, "Asia Foods", "Dry store"),
    ("Tahini", "kg", 4, 8.2, "Levant Supply", "Dry store"),
    ("Harissa", "kg", 3, 9.4, "Levant Supply", "Dry store"),
    ("Yuzu juice", "L", 2, 34.0, "Asia Foods", "Dry store"),
    ("Sesame seed", "kg", 2, 6.8, "Asia Foods", "Dry store"),
    ("Olive oil, Sicilian", "L", 18, 12.5, "Sapori d'Italia", "Dry store"),
    ("Gordal olives", "kg", 6, 9.8, "Sapori d'Italia", "Dry store"),
    ("Prosecco", "unit", 24, 9.0, "Berry Bros", "Cellar"),
    ("Campari", "L", 6, 18.0, "Berry Bros", "Cellar"),
    ("Gin", "L", 8, 24.0, "Berry Bros", "Cellar"),
    ("Barolo Vietti 2018", "unit", 18, 34.0, "Berry Bros", "Cellar"),
    ("Chablis 1er Cru", "unit", 24, 24.0, "Berry Bros", "Cellar"),
    ("Seedlip Garden", "L", 4, 21.0, "Berry Bros", "Cellar"),
    ("Coffee beans", "kg", 8, 22.0, "Assembly Roast", "Dry store"),
]

# dish name -> [(ingredient name, qty per portion)]
RECIPES = {
    "Grilled Sea Bass, Asparagus": [("Sea bass fillet", 0.22), ("Asparagus", 0.12), ("Butter, cultured", 0.03)],
    "Dover Sole Meunière": [("Dover sole", 0.45), ("Butter, cultured", 0.06), ("Lemon, Amalfi", 0.05)],
    "Whole Turbot to Share": [("Turbot", 0.9), ("Butter, cultured", 0.08), ("Lemon, Amalfi", 0.08)],
    "Hand-Dived Scallop": [("Scallops", 0.16), ("Butter, cultured", 0.02)],
    "Tuna Crudo, Yuzu, Sesame": [("Tuna loin", 0.11), ("Yuzu juice", 0.02), ("Sesame seed", 0.01)],
    "Lobster Ravioli": [("Native lobster", 0.18), ("00 flour", 0.09), ("Eggs", 1.0), ("Double cream", 0.05)],
    "Oyster & Champagne Mignonette": [("Oysters", 6.0)],
    "Caviar Service 30g": [("Oscietra caviar", 0.03), ("Double cream", 0.02), ("Eggs", 1.0)],
    "Dry-Aged Ribeye 400g": [("Ribeye, dry aged", 0.4), ("Bone marrow", 0.05), ("Butter, cultured", 0.03)],
    "Beef Tartare, Smoked Yolk": [("Sirloin", 0.13), ("Eggs", 1.0)],
    "Rack of Lamb, Harissa": [("Lamb rack", 0.32), ("Harissa", 0.03)],
    "Confit Duck Leg, Cherry": [("Duck leg", 0.3), ("Cherries", 0.06)],
    "Roast Chicken for Two": [("Chicken, whole", 1.4), ("Butter, cultured", 0.05)],
    "Burrata, Datterini, Basil Oil": [("Burrata", 0.15), ("Datterini tomato", 0.1), ("Basil", 0.01), ("Olive oil, Sicilian", 0.02)],
    "Porcini Risotto": [("Carnaroli rice", 0.09), ("Porcini, dried", 0.012), ("Parmesan 24mo", 0.03), ("Butter, cultured", 0.03)],
    "Truffle Tagliatelle": [("00 flour", 0.11), ("Eggs", 2.0), ("Black truffle", 0.006), ("Parmesan 24mo", 0.03)],
    "Wild Mushroom Croquette": [("Girolles", 0.09), ("Comté", 0.03), ("Panko", 0.04)],
    "Vine Tomato & Watermelon": [("Vine tomato", 0.14), ("Watermelon", 0.12), ("Basil", 0.005)],
    "Aubergine Katsu": [("Aubergine", 0.26), ("Panko", 0.05)],
    "Cauliflower Steak, Tahini": [("Cauliflower", 0.3), ("Tahini", 0.04), ("Pomegranate", 0.04)],
    "Triple-Cooked Chips": [("Maris Piper", 0.28)],
    "Truffle Mash": [("Ratte potato", 0.22), ("Butter, cultured", 0.05), ("Black truffle", 0.002)],
    "Charred Hispi Cabbage": [("Hispi cabbage", 0.24), ("Butter, cultured", 0.02)],
    "Green Beans, Almond": [("Green beans", 0.15), ("Almond, flaked", 0.02)],
    "Chocolate Nemesis": [("Chocolate 70%", 0.08), ("Eggs", 2.0), ("Butter, cultured", 0.05)],
    "Lemon Tart, Basil": [("Lemon, Amalfi", 0.09), ("Eggs", 1.5), ("00 flour", 0.05)],
    "Tiramisu al Cucchiaio": [("Mascarpone", 0.09), ("Eggs", 1.0), ("Coffee beans", 0.02)],
    "Pistachio Cannolo": [("Pistachio, Bronte", 0.04), ("00 flour", 0.04), ("Mascarpone", 0.05)],
    "Vanilla Ice Cream, Olive Oil": [("Double cream", 0.12), ("Vanilla pod", 0.2), ("Olive oil, Sicilian", 0.01)],
    "Cheese, Four Ways": [("Comté", 0.06), ("Parmesan 24mo", 0.03)],
    "Sourdough & Cultured Butter": [("Sourdough starter", 0.02), ("00 flour", 0.08), ("Butter, cultured", 0.04)],
    "Gordal Olives": [("Gordal olives", 0.09)],
    "Negroni Sbagliato": [("Prosecco", 0.3), ("Campari", 0.03)],
    "Martini, Very Cold": [("Gin", 0.07)],
    "Garden Spritz (0%)": [("Seedlip Garden", 0.05), ("Prosecco", 0.15)],
    "Barolo, Vietti 2018": [("Barolo Vietti 2018", 1.0)],
    "Chablis 1er Cru": [("Chablis 1er Cru", 1.0)],
    "Espresso": [("Coffee beans", 0.018)],
}

RU_INGREDIENT_NAMES = {
    "Sea bass fillet": "Филе сибаса",
    "Dover sole": "Морской язык (солея)",
    "Turbot": "Тюрбо (калкан)",
    "Scallops": "Морские гребешки",
    "Tuna loin": "Тунец (поясница)",
    "Native lobster": "Омар местный",
    "Oysters": "Устрицы",
    "Oscietra caviar": "Икра осётра (осцетра)",
    "Ribeye, dry aged": "Рибай сухого вызревания",
    "Sirloin": "Стриплойн",
    "Lamb rack": "Каре ягнёнка",
    "Duck leg": "Утиная ножка",
    "Chicken, whole": "Курица целая",
    "Bone marrow": "Костный мозг",
    "Burrata": "Буррата",
    "Parmesan 24mo": "Пармезан 24 мес.",
    "Comté": "Конте",
    "Butter, cultured": "Сливочное масло фермерское",
    "Double cream": "Жирные сливки",
    "Mascarpone": "Маскарпоне",
    "Eggs": "Яйца",
    "Black truffle": "Трюфель чёрный",
    "Girolles": "Лисички",
    "Porcini, dried": "Белые грибы сушёные",
    "Asparagus": "Спаржа",
    "Datterini tomato": "Помидоры датерини",
    "Vine tomato": "Помидоры на ветке",
    "Watermelon": "Арбуз",
    "Aubergine": "Баклажан",
    "Cauliflower": "Цветная капуста",
    "Hispi cabbage": "Капуста остроконечная",
    "Green beans": "Стручковая фасоль",
    "Ratte potato": "Картофель ратт",
    "Maris Piper": "Картофель марис пайпер",
    "Basil": "Базилик",
    "Lemon, Amalfi": "Лимон амальфи",
    "Cherries": "Вишня",
    "Pomegranate": "Гранат",
    "Avocado": "Авокадо",
    "Pistachio, Bronte": "Фисташки бронте",
    "Almond, flaked": "Миндаль хлопьями",
    "Chocolate 70%": "Шоколад 70%",
    "Vanilla pod": "Стручок ванили",
    "00 flour": "Мука 00",
    "Sourdough starter": "Закваска",
    "Carnaroli rice": "Рис карнароли",
    "Panko": "Панко (сухари)",
    "Tahini": "Тахини",
    "Harissa": "Харисса",
    "Yuzu juice": "Сок юзу",
    "Sesame seed": "Семена кунжута",
    "Olive oil, Sicilian": "Оливковое масло сицилийское",
    "Gordal olives": "Оливки гордаль",
    "Prosecco": "Просекко",
    "Campari": "Кампари",
    "Gin": "Джин",
    "Barolo Vietti 2018": "Бароло Вьетти 2018",
    "Chablis 1er Cru": "Шабли Премье Крю",
    "Seedlip Garden": "Сидлип гарден",
    "Coffee beans": "Кофейные зёрна",
}

FIRST = ["Amelia", "Jonah", "Priya", "Nikolai", "Yasmin", "Theo", "Camille", "Idris",
         "Freya", "Rafael", "Leila", "Hugo", "Mei", "Anders", "Zara", "Emre",
         "Beatrice", "Kwame", "Sabine", "Diego", "Noor", "Felix", "Anouk", "Tariq",
         "Isolde", "Mateo", "Rania", "Casper", "Juno", "Salim"]
LAST = ["Whitfield", "Achebe", "Bergström", "Castellanos", "Dubois", "Eriksen",
        "Farhadi", "Grimaldi", "Hollingsworth", "Ivanova", "Jamison", "Kowalski",
        "Lindqvist", "Moreau", "Nakamura", "Oyelaran", "Pereira", "Qureshi",
        "Radcliffe", "Solberg", "Takahashi", "Ustinov", "Valdez", "Wintour"]

ALLERGIES = ["", "", "", "", "nuts", "shellfish", "gluten", "dairy", "sesame", "fish"]
PREFS = ["", "", "Terrace", "Away from the pass", "Corner banquette", "Bar counter",
         "Not near the door", "Quiet table"]


def wipe() -> None:
    """Drop the file and start clean. Demo data should be reproducible."""
    from .database import DB_PATH
    if DB_PATH.exists():
        DB_PATH.unlink()


def build() -> None:
    wipe()
    create_db()
    today = date.today()

    # PINs are printed to the console below and never stored in plaintext —
    # see security.hash_pin. This list exists only for that printout.
    demo_pins: list[tuple] = []

    with Session(engine) as s:
        # --- staff -----------------------------------------------------
        for i, (name, role, avatar, section) in enumerate(STAFF):
            pin = f"{1000 + i * 37 % 9000:04d}"
            demo_pins.append((name, role.value, section, pin))
            s.add(Staff(name=name, role=role, avatar=avatar, section=section,
                        pin_hash=hash_pin(pin),
                        on_shift=rng.random() > 0.25,
                        covers_served=rng.randint(180, 640),
                        avg_service_seconds=rng.randint(140, 320)))
        s.commit()

        waiters = s.exec(select(Staff).where(Staff.role == Role.WAITER)).all()

        # --- floor -----------------------------------------------------
        for number, seats, zone, x, y, shape in FLOOR:
            s.add(DiningTable(number=number, seats=seats, zone=zone, x=x, y=y,
                              shape=shape, status=TableStatus.AVAILABLE,
                              waiter_id=rng.choice(waiters).id))
        s.commit()

        # --- menu ------------------------------------------------------
        for (name, course, station, price, cost, minutes, tags,
             protein, kcal, blurb) in MENU:
            # Popularity is loosely inverse to price, with noise. Gives menu
            # engineering something interesting to classify.
            base = max(6, int(900 / (price + 6)))
            # No stock photography. Each dish gets a hue and the guest app
            # renders a plate from it, so the menu looks composed rather
            # than like a folder of mismatched jpegs.
            hue = {"Snack": 44, "Starter": 96, "Main": 18, "Side": 128,
                   "Dessert": 330, "Drink": 268}.get(course, 150)
            hue = (hue + rng.randint(-22, 22)) % 360
            s.add(MenuItem(name=name, course=course, station=station, price=price,
                           food_cost=cost, base_minutes=minutes, tags=tags,
                           protein_g=protein, kcal=kcal, blurb=blurb, hue=hue,
                           spice=rng.choices([0, 0, 0, 1, 2], [60, 12, 10, 12, 6])[0],
                           signature=price > 40 or rng.random() < 0.12,
                           sold_30d=int(base * rng.uniform(0.5, 2.4))))
        s.commit()

        # --- stock -----------------------------------------------------
        # Seven ingredients are deliberately run down. Mid-week that is just
        # what a walk-in looks like, and it gives the shortage model
        # something real to catch instead of a screen of green ticks.
        RUNNING_LOW = {"Sea bass fillet", "Burrata", "Asparagus", "Black truffle",
                       "Ratte potato", "Chicken, whole", "Double cream"}
        for name, unit, par, cost, supplier, store in INGREDIENTS:
            if name in RUNNING_LOW:
                level = par * rng.uniform(0.10, 0.28)
            else:
                level = par * rng.uniform(0.55, 1.9)
            s.add(Ingredient(name=name, name_ru=RU_INGREDIENT_NAMES.get(name, ""), unit=unit, par_level=par, in_stock=round(level, 2),
                             cost_per_unit=cost, supplier=supplier, store=store,
                             expires_on=today + timedelta(days=rng.randint(2, 40))))
        s.commit()

        items = {m.name: m for m in s.exec(select(MenuItem)).all()}
        ings = {i.name: i for i in s.exec(select(Ingredient)).all()}
        for dish, lines in RECIPES.items():
            if dish not in items:
                continue
            for ing_name, qty in lines:
                if ing_name in ings:
                    s.add(RecipeLine(menu_item_id=items[dish].id,
                                     ingredient_id=ings[ing_name].id,
                                     qty_per_portion=qty))
        s.commit()

        # --- guests ----------------------------------------------------
        dish_names = [m for m in items if items[m].course == "Main"]
        for _ in range(100):
            visits = rng.choices([1, 2, 3, 5, 8, 14, 22], [40, 20, 14, 10, 8, 5, 3])[0]
            s.add(Guest(
                name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                visits=visits,
                vip=visits >= 12 or rng.random() < 0.05,
                allergies=rng.choice(ALLERGIES),
                likes=rng.choice(dish_names),
                seating_pref=rng.choice(PREFS),
                avg_spend=round(rng.uniform(52, 190), 2),
                note=rng.choice(["", "", "", "Always orders the same thing.",
                                 "Prefers still water, no ice.",
                                 "Writes for a food magazine.",
                                 "Celebrating something most visits."]),
            ))
        s.commit()

        guests = s.exec(select(Guest)).all()

        # --- reservations: today and the next three days ---------------
        occasions = ["", "", "", "", "Birthday", "Anniversary", "Business", "Date"]
        now = datetime.now()
        for day_offset in range(0, 4):
            covers_target = rng.randint(34, 46)
            made = 0
            while made < covers_target:
                hour = rng.choices([12, 13, 18, 19, 20, 21],
                                   [8, 10, 14, 26, 24, 18])[0]
                minute = rng.choice([0, 15, 30, 45])
                when = datetime.combine(today + timedelta(days=day_offset),
                                        datetime.min.time()).replace(hour=hour, minute=minute)
                g = rng.choice(guests)
                s.add(Reservation(
                    guest_id=g.id, party_size=rng.choices([2, 2, 2, 3, 4, 4, 6, 8],
                                                          [30, 20, 12, 10, 12, 8, 5, 3])[0],
                    starts_at=when, occasion=rng.choice(occasions),
                    status="confirmed" if when > now else rng.choice(["seated", "confirmed"]),
                    note=g.note if rng.random() < 0.2 else "",
                    source=rng.choices(["website", "phone", "walk-in", "instagram", "concierge"],
                                       [46, 22, 14, 12, 6])[0],
                    deposit=round(rng.choice([0, 0, 0, 25, 50]) * 1.0, 2),
                ))
                made += 1
        s.commit()

        # --- 180 days of trading history -------------------------------
        # The signal we plant: weekday effect, rain suppresses walk-ins,
        # summer lifts terrace covers, holidays spike, plus noise.
        for back in range(180, 0, -1):
            d = today - timedelta(days=back)
            wd = d.weekday()
            weekday_lift = [0.72, 0.78, 0.86, 0.95, 1.18, 1.32, 1.05][wd]
            season = 1 + 0.12 * ((d.timetuple().tm_yday % 365) / 365 - 0.5) * 2
            rain = max(0.0, rng.gauss(1.6, 2.4))
            rain_drag = 1 - min(0.18, rain * 0.02)
            holiday = rng.random() < 0.04
            event = rng.random() < 0.12
            covers = int(150 * weekday_lift * season * rain_drag
                         * (1.15 if holiday else 1.0)
                         * (1.08 if event else 1.0)
                         * rng.uniform(0.92, 1.08))
            spend = rng.uniform(78, 96) * (1.06 if wd >= 4 else 1.0)
            s.add(DayStat(day=d, weekday=wd, covers=covers,
                          revenue=round(covers * spend, 2),
                          reservations=int(covers * rng.uniform(0.55, 0.78)),
                          rain_mm=round(rain, 1),
                          temp_c=round(rng.gauss(16, 6), 1),
                          is_holiday=holiday, local_event=event))
        s.commit()

        # --- waste + feedback history ----------------------------------
        reasons = ["expired", "prep mistake", "returned", "overproduction", "damaged"]
        ing_list = list(ings.values())
        for back in range(30, 0, -1):
            for _ in range(rng.randint(2, 6)):
                ing = rng.choice(ing_list)
                s.add(WasteLog(ingredient_id=ing.id,
                               qty=round(rng.uniform(0.2, 3.4), 2),
                               reason=rng.choices(reasons, [20, 22, 12, 34, 12])[0],
                               logged_on=today - timedelta(days=back)))
        for _ in range(120):
            s.add(Feedback(table_id=rng.randint(1, 30),
                           food=rng.choices([3, 4, 5], [4, 24, 72])[0],
                           service=rng.choices([2, 3, 4, 5], [3, 8, 26, 63])[0],
                           atmosphere=rng.choices([4, 5], [18, 82])[0],
                           speed=rng.choices([2, 3, 4, 5], [8, 18, 34, 40])[0],
                           created_at=now - timedelta(days=rng.randint(0, 20),
                                                      minutes=rng.randint(0, 900))))
        s.commit()

        # --- orders already closed earlier today ------------------------
        # Without these the dashboard opens at zero and looks broken. Service
        # started at noon; we replay it so revenue-by-hour has a real shape.
        menu = s.exec(select(MenuItem)).all()
        by_course: dict[str, list[MenuItem]] = {}
        for m in menu:
            by_course.setdefault(m.course, []).append(m)
        tables_all = s.exec(select(DiningTable)).all()
        waiter_ids = [w.id for w in waiters]

        # The seeded service runs from noon to whatever hour it currently is.
        # Opening the app at 09:00 would otherwise produce a completely empty
        # dashboard, so anything that would land in the future is pulled back
        # into the last few hours instead. Every timestamp stays in the past.
        start_hour = 12
        end_hour = max(16, min(now.hour, 23))
        for hour in range(start_hour, end_hour):
            # Lunch peak at 13:00, dinner building from 18:00.
            weight = {12: 5, 13: 8, 14: 5, 15: 2, 16: 1, 17: 3,
                      18: 7, 19: 11, 20: 12, 21: 9, 22: 5}.get(hour, 3)
            for _ in range(weight):
                t = rng.choice(tables_all)
                opened = now.replace(hour=hour, minute=rng.randint(0, 55),
                                     second=0, microsecond=0)
                if opened > now:
                    opened = now - timedelta(minutes=rng.randint(20, 200))
                order = Order(table_id=t.id, waiter_id=rng.choice(waiter_ids),
                              opened_at=opened,
                              closed_at=opened + timedelta(minutes=rng.randint(55, 110)),
                              paid=True, tip=round(rng.uniform(4, 26), 2))
                s.add(order)
                s.commit()
                s.refresh(order)
                party = rng.choices([2, 2, 3, 4, 6], [40, 24, 14, 16, 6])[0]
                for _p in range(party):
                    for course, chance in (("Main", 1.0), ("Starter", 0.6),
                                           ("Drink", 0.8), ("Side", 0.4),
                                           ("Dessert", 0.45), ("Snack", 0.3)):
                        if rng.random() <= chance and by_course.get(course):
                            dish = rng.choice(by_course[course])
                            s.add(OrderItem(order_id=order.id, menu_item_id=dish.id,
                                            station=dish.station, state=ItemState.SERVED,
                                            fired_at=opened + timedelta(minutes=rng.randint(2, 40)),
                                            ready_at=opened + timedelta(minutes=rng.randint(10, 55)),
                                            promised_minutes=dish.base_minutes))
        s.commit()

        from .seed_ops import build_ops
        build_ops(s)

    print(f"Seeded: 30 tables, {len(STAFF)} staff, 40 dishes, 61 ingredients, "
          "100 guests, ~160 reservations, 180 days of history, "
          "and today's service so far.")
    print()
    print("Demo staff PINs — for signing in at /waiter or /admin.")
    print("Real PINs are never stored or shown anywhere in the app itself;")
    print("this printout is the only place they exist in plain text,")
    print("because this is a demo.")
    print("-" * 62)
    for name, role, section, pin in demo_pins:
        label = role.replace("_", " ")
        where = f" · {section}" if section else ""
        print(f"  {name:<20} {label:<20}{where:<16} PIN {pin}")
    print("-" * 62)


if __name__ == "__main__":
    build()
