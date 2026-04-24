"""Generate SaveBot navigation map as .excalidraw file."""
import json, random, string

elements = []
nonce = lambda: random.randint(100000000, 999999999)

def rect(id, x, y, w, h, stroke, bg, label, bound_ids=None):
    be = [{"id": id+"_t", "type": "text"}]
    if bound_ids:
        for bid in bound_ids:
            be.append({"id": bid, "type": "arrow"})
    elements.append({
        "type": "rectangle", "id": id, "x": x, "y": y, "width": w, "height": h,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
        "angle": 0, "groupIds": [], "boundElements": be, "link": None, "locked": False,
        "roundness": {"type": 3}, "version": 1, "versionNonce": nonce(), "isDeleted": False,
        "updated": 1, "seed": nonce()
    })
    elements.append({
        "type": "text", "id": id+"_t", "x": x+10, "y": y+h/2-10, "width": w-20, "height": 20,
        "text": label, "fontSize": 14, "fontFamily": 2, "textAlign": "center",
        "verticalAlign": "middle", "containerId": id, "originalText": label,
        "strokeColor": "#1e1e1e", "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
        "angle": 0, "groupIds": [], "boundElements": None, "link": None, "locked": False,
        "version": 1, "versionNonce": nonce(), "isDeleted": False, "updated": 1, "seed": nonce(),
        "lineHeight": 1.2
    })

def note(id, x, y, text, color="#868e96"):
    elements.append({
        "type": "text", "id": id, "x": x, "y": y, "width": 300, "height": 16,
        "text": text, "fontSize": 12, "fontFamily": 2, "textAlign": "left",
        "verticalAlign": "top", "containerId": None, "originalText": text,
        "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
        "angle": 0, "groupIds": [], "boundElements": None, "link": None, "locked": False,
        "version": 1, "versionNonce": nonce(), "isDeleted": False, "updated": 1, "seed": nonce(),
        "lineHeight": 1.2
    })

def arrow(id, sx, sy, ex, ey, src_id, dst_id, color="#868e96", label=None):
    dx = ex - sx
    dy = ey - sy
    be = []
    if label:
        be.append({"id": id+"_lbl", "type": "text"})
    elements.append({
        "type": "arrow", "id": id, "x": sx, "y": sy, "width": abs(dx), "height": abs(dy),
        "points": [[0, 0], [dx, dy]],
        "lastCommittedPoint": None,
        "startBinding": {"elementId": src_id, "focus": 0, "gap": 5},
        "endBinding": {"elementId": dst_id, "focus": 0, "gap": 5},
        "startArrowhead": None, "endArrowhead": "arrow",
        "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
        "angle": 0, "groupIds": [], "boundElements": be, "link": None, "locked": False,
        "version": 1, "versionNonce": nonce(), "isDeleted": False, "updated": 1, "seed": nonce()
    })
    if label:
        lx = sx + dx/2 - 20
        ly = sy + dy/2 - 8
        elements.append({
            "type": "text", "id": id+"_lbl", "x": lx, "y": ly, "width": 80, "height": 16,
            "text": label, "fontSize": 12, "fontFamily": 2, "textAlign": "center",
            "verticalAlign": "middle", "containerId": id, "originalText": label,
            "strokeColor": color, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0, "opacity": 100,
            "angle": 0, "groupIds": [], "boundElements": None, "link": None, "locked": False,
            "version": 1, "versionNonce": nonce(), "isDeleted": False, "updated": 1, "seed": nonce(),
            "lineHeight": 1.2
        })

GREEN = "#2f9e44"
GBG = "#b2f2bb"
YELLOW = "#e8590c"
YBG = "#ffec99"
RED = "#e03131"
RBG = "#ffc9c9"
BLUE = "#4263eb"
BBG = "#bac8ff"

# ── LEGEND ──
note("leg0", 20, 20, "КАРТА НАВИГАЦИИ SAVEBOT", "#1e1e1e")
note("leg1", 20, 45, "🟢 Зелёный = 1 клик    🟡 Жёлтый = 2 клика", "#1e1e1e")
note("leg2", 20, 65, "🔴 Красный = 3+ клика   🔵 Синий = Save Flow", "#1e1e1e")
note("leg3", 20, 85, "⚠️ = Проблемная зона навигации", RED)

# ── COLUMN 0: Entry + Save Flow ──
rect("kb", 50, 200, 230, 130, "#1e1e1e", "#e9ecef",
     "Главная клавиатура\nBrowse | Search\nPinned | Recent\nSettings")
rect("sv1", 50, 400, 200, 60, BLUE, BBG, "Авто-сохранение")
note("sv1n", 55, 465, "Сетка категорий, Pin, Delete")
rect("sv2", 50, 510, 200, 60, BLUE, BBG, "Ручное сохранение")
note("sv2n", 55, 575, "Confirm / Change Cat / Cancel")
rect("sv3", 50, 620, 200, 60, BLUE, BBG, "Выбор категории (save)")

# ── COLUMN 1: Level 1 (Green) ──
rect("cat", 400, 160, 200, 55, GREEN, GBG, "📂 Список категорий")
note("catn", 405, 220, "Кнопки категорий + [Ещё]")
rect("src_res", 400, 270, 200, 55, GREEN, GBG, "🔍 Результаты поиска")
note("srcn", 405, 330, "AI-парсинг + FTS5")
rect("pin", 400, 380, 200, 55, GREEN, GBG, "📌 Закреплённые")
rect("rec", 400, 470, 200, 55, GREEN, GBG, "🕐 Недавние")
rect("set", 400, 560, 200, 55, GREEN, GBG, "⚙️ Настройки")
note("setn", 405, 620, "auto_save, digest, brief")
rect("cmg", 400, 680, 200, 55, GREEN, GBG, "📋 Управление категориями")
note("cmgn", 405, 740, "/categories → Info/Rename/Delete")

# ── COLUMN 2: Level 2 (Yellow) ──
rect("ci", 740, 140, 210, 70, YELLOW, YBG, "📄 Элементы категории\nСортировка: 🕐📌📋📨")
note("cin", 745, 215, "Клик → Item View, 🗑 Delete")
rect("hub", 740, 290, 210, 110, YELLOW, YBG, "📋 Ещё (Hub)\nТеги | Каналы\nКоллекции | Карта\nЗабытые | +Категория")
rect("day", 740, 460, 200, 50, YELLOW, YBG, "📅 Выбор дня дайджеста")
rect("time", 740, 550, 200, 50, YELLOW, YBG, "🕐 Выбор времени brief")
rect("cinfo", 740, 650, 200, 55, YELLOW, YBG, "ℹ️ Инфо о категории")

# ── COLUMN 3: Level 3 (Red) ──
rect("iv", 1100, 60, 220, 170, RED, RBG,
     "👁 Просмотр элемента\n◀ Пред | 1/N | След ▶\n📌Pin 📂Move 🗑Del\n🏷Tags 📝Note\n🔗Related 📁Collection")
rect("tc", 1100, 290, 200, 55, RED, RBG, "🏷 Облако тегов")
rect("ti", 1100, 390, 200, 55, RED, RBG, "🏷 Элементы по тегу")
rect("sl", 1100, 500, 200, 55, RED, RBG, "📨 Каналы-источники")
rect("si", 1100, 600, 200, 55, RED, RBG, "📨 Элементы канала")
rect("cl", 1100, 710, 200, 55, RED, RBG, "📁 Коллекции")
rect("cli", 1100, 810, 200, 55, RED, RBG, "📁 Элементы коллекции")
rect("km", 1100, 920, 200, 55, RED, RBG, "🗺 Карта знаний")
rect("fg", 1100, 1030, 200, 55, RED, RBG, "💤 Забытые элементы")

# ── COLUMN 4: Item View sub-screens ──
rect("mv", 1440, 80, 180, 55, RED, RBG, "📂 Переместить в...")
rect("dc", 1440, 180, 180, 55, RED, RBG, "🗑 Подтвердить удаление")

# ── ARROWS: Keyboard → Level 1 ──
arrow("a1", 280, 230, 400, 185, "kb", "cat", GREEN, "Browse")
arrow("a2", 280, 260, 400, 295, "kb", "src_res", GREEN, "Search")
arrow("a3", 280, 280, 400, 405, "kb", "pin", GREEN, "Pinned")
arrow("a4", 280, 290, 400, 495, "kb", "rec", GREEN, "Recent")
arrow("a5", 280, 300, 400, 585, "kb", "set", GREEN, "Settings")

# ── ARROWS: Level 1 → Level 2 ──
arrow("a6", 600, 175, 740, 165, "cat", "ci", YELLOW, "категория")
arrow("a7", 600, 195, 740, 330, "cat", "hub", YELLOW, "Ещё")
arrow("a8", 600, 580, 740, 480, "set", "day", YELLOW)
arrow("a9", 600, 590, 740, 570, "set", "time", YELLOW)
arrow("a10", 600, 705, 740, 675, "cmg", "cinfo", YELLOW, "Info")

# ── ARROWS: Level 2 → Level 3 ──
arrow("a11", 950, 170, 1100, 130, "ci", "iv", RED, "клик")
arrow("a12", 950, 310, 1100, 310, "hub", "tc", RED, "Теги")
arrow("a13", 950, 340, 1100, 520, "hub", "sl", RED, "Каналы")
arrow("a14", 950, 360, 1100, 730, "hub", "cl", RED, "Коллекции")
arrow("a15", 950, 380, 1100, 940, "hub", "km", RED, "Карта")
arrow("a16", 950, 390, 1100, 1050, "hub", "fg", RED, "Забытые")

# ── ARROWS: within Level 3 (vertical) ──
arrow("a17", 1200, 345, 1200, 390, "tc", "ti", "#868e96")
arrow("a18", 1200, 555, 1200, 600, "sl", "si", "#868e96")
arrow("a19", 1200, 765, 1200, 810, "cl", "cli", "#868e96")

# ── ARROWS: Item View → sub-screens ──
arrow("a20", 1320, 120, 1440, 105, "iv", "mv", RED, "Move")
arrow("a21", 1320, 180, 1440, 205, "iv", "dc", RED, "Delete")

# ── WARNING BADGES ──
rect("w1", 970, 280, 120, 40, RED, RBG, "⚠️ BOTTLENECK")
note("w1n", 970, 325, "6 фич за 1 кнопкой!", RED)
rect("w4", 1340, 60, 90, 35, RED, RBG, "⚠️ 8 кнопок")
rect("w5", 610, 270, 120, 35, RED, RBG, "⚠️ Нет «назад»")

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "https://excalidraw.com",
    "elements": elements,
    "appState": {
        "viewBackgroundColor": "#f8f9fa",
        "gridSize": None
    },
    "files": {}
}

with open("docs/navigation-map.excalidraw", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)

print(f"Done! {len(elements)} elements")
print("File: docs/navigation-map.excalidraw")
