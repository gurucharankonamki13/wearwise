"""
==============================================================================
StyleMatrix – Smart Wardrobe & Maximum Outfit Generator
==============================================================================
Clean, premium wardrobe & outfit generator powered by classical color harmonies.

Key Features:
1. Robust Category Detection: Distinguishes Tank Tops, Tops, Bottomwear, and Footwear
   without misclassifying vertical photos as bottomwear.
2. Accurate Color Detection: Correctly classifies white, off-white, black, grey,
   and colors without false navy/denim fallbacks.
3. Classical Color Harmony Engine: Applies timeless 2-piece, 3-piece, and 4-piece
   color combinations with clean, elegant styling (no book references).
4. Strict inner-layer rule for tank tops (only layered with shirts & jackets).
==============================================================================
"""

from flask import Flask, render_template, request, jsonify
import os
import itertools
import uuid
import base64
import colorsys
import math
from PIL import Image

app = Flask(__name__, template_folder="templates", static_folder="static")

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# -----------------------------------------------------------------------------
# Classical Color Harmony Palettes
# -----------------------------------------------------------------------------
CURATED_COLOR_HARMONIES = [
    {
        "id": 1,
        "name": "Classic Modernist",
        "colors": {"Navy / Denim", "Beige / Khaki", "Yellow / Orange"},
        "desc": "Indigo, Pale Ecru, and Warm Amber"
    },
    {
        "id": 14,
        "name": "Scholarly Elegance",
        "colors": {"Grey", "Yellow / Orange", "White"},
        "desc": "Slate Grey, Saffron Ochre, and Crisp White"
    },
    {
        "id": 23,
        "name": "Imperial Maritime",
        "colors": {"Navy / Denim", "Beige / Khaki", "Red / Crimson"},
        "desc": "Deep Navy, Sand Khaki, and Rich Wine"
    },
    {
        "id": 42,
        "name": "Organic Minimalist",
        "colors": {"Olive / Green", "Grey", "White"},
        "desc": "Sage Olive, Charcoal Slate, and Off-White"
    },
    {
        "id": 58,
        "name": "Earth & Indigo",
        "colors": {"Olive / Green", "Brown", "Navy / Denim"},
        "desc": "Olive Green, Terracotta Brown, and Indigo"
    },
    {
        "id": 67,
        "name": "Timeless Tailoring",
        "colors": {"Beige / Khaki", "Black", "White"},
        "desc": "Warm Camel, Jet Black, and Crisp White"
    },
    {
        "id": 89,
        "name": "Serene Harmony",
        "colors": {"Pastel / Light", "Navy / Denim", "Brown"},
        "desc": "Pale Celadon, Prussian Navy, and Chestnut"
    },
    {
        "id": 112,
        "name": "Subtle Poetics",
        "colors": {"Pastel / Light", "Grey", "Black"},
        "desc": "Dusty Rose/Pastel, Slate Grey, and Deep Black"
    },
    {
        "id": 135,
        "name": "Vintage Printmaker",
        "colors": {"Yellow / Orange", "Navy / Denim", "Beige / Khaki"},
        "desc": "Mustard Ochre, Prussian Blue, and Raw Taupe"
    },
    {
        "id": 164,
        "name": "High-Contrast Graphic",
        "colors": {"Black", "White", "Red / Crimson"},
        "desc": "Jet Black, Pure White, and Japanese Vermilion"
    },
    {
        "id": 180,
        "name": "Rugged Heritage",
        "colors": {"Beige / Khaki", "Navy / Denim", "Brown"},
        "desc": "Field Khaki, Indigo Denim, and Rust Brown"
    },
    {
        "id": 205,
        "name": "Forest Atelier",
        "colors": {"Olive / Green", "Beige / Khaki", "Brown"},
        "desc": "Deep Olive, Unbleached Linen, and Espresso"
    },
    {
        "id": 240,
        "name": "Coastal Tones",
        "colors": {"Pastel / Light", "Beige / Khaki", "Grey"},
        "desc": "Pale Sky Blue, Sandstone, and Soft Charcoal"
    },
    {
        "id": 280,
        "name": "Evening Twilight",
        "colors": {"Red / Crimson", "Grey", "Navy / Denim"},
        "desc": "Deep Burgundy, Silver Grey, and Midnight Navy"
    },
    {
        "id": 310,
        "name": "Traditional Atelier",
        "colors": {"Brown", "Olive / Green", "White"},
        "desc": "Raw Umber, Muted Moss, and Bleached Hemp"
    },
    {
        "id": 332,
        "name": "Monochrome Noir",
        "colors": {"Black", "Grey", "White"},
        "desc": "Deep Black, Silver Mist, and Pure White"
    }
]

NEUTRALS = {"Black", "White", "Grey", "Navy / Denim", "Beige / Khaki", "Brown"}

COLOR_CENTROIDS = {
    "Black": (24, 24, 27),
    "White": (245, 245, 247),
    "Grey": (113, 113, 122),
    "Navy / Denim": (30, 58, 138),
    "Beige / Khaki": (194, 166, 128),
    "Olive / Green": (63, 98, 18),
    "Brown": (120, 53, 15),
    "Red / Crimson": (185, 28, 28),
    "Pastel / Light": (147, 197, 253),
    "Yellow / Orange": (217, 119, 6)
}


def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c * 2 for c in hex_str])
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


def classify_rgb(r, g, b):
    """
    Accurately classifies an RGB color into standard fashion categories.
    Prevents white or neutral fabrics from falsely classifying as Navy / Denim.
    """
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    # 1. White / Off-white / Cream check:
    # If all RGB channels are bright and the spread between them is small
    if min_c > 190 and diff < 38:
        return "White"
    if min_c > 215 and diff < 45:
        return "White"

    # 2. Black check:
    if max_c < 45:
        return "Black"

    # 3. Grey check:
    if diff < 18:
        if min_c > 180:
            return "White"
        elif max_c < 55:
            return "Black"
        else:
            return "Grey"

    # 4. HLS Hue and Saturation Analysis:
    rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
    h, l, s = colorsys.rgb_to_hls(rn, gn, bn)
    h_deg = h * 360.0

    if l < 0.16:
        return "Black"
    if l > 0.85 and s < 0.22:
        return "White"
    if s < 0.14:
        return "Grey"

    # Specific color families
    if 185 <= h_deg <= 250:
        # Require true blue saturation and moderate lightness to be Navy / Denim
        if s > 0.20 and l < 0.70:
            return "Navy / Denim"
        elif l >= 0.70:
            return "Pastel / Light"
        else:
            return "Grey"

    if 65 <= h_deg <= 165:
        return "Olive / Green"
    if 25 <= h_deg <= 55 and s < 0.60 and l > 0.38:
        return "Beige / Khaki"
    if 15 <= h_deg <= 45 and l < 0.44:
        return "Brown"
    if h_deg < 20 or h_deg > 338:
        return "Red / Crimson"
    if 35 <= h_deg <= 65:
        return "Yellow / Orange"
    if l > 0.65 and s > 0.16:
        return "Pastel / Light"

    # Nearest Euclidean fallback against true centroids
    best_color = "Grey"
    min_dist = float("inf")
    for name, centroid in COLOR_CENTROIDS.items():
        dist = math.sqrt((r - centroid[0])**2 + (g - centroid[1])**2 + (b - centroid[2])**2)
        if dist < min_dist:
            min_dist = dist
            best_color = name
    return best_color


# -----------------------------------------------------------------------------
# Robust Category Detection from Image Morphology & Attributes
# -----------------------------------------------------------------------------
def detect_category_from_image(img, filename=""):
    """
    Classifies clothing category accurately.
    Crucially: NEVER defaults to Bottomwear purely due to vertical portrait aspect ratio!
    """
    fn = filename.lower()

    # 1. Exact keyword hints from filename
    if any(k in fn for k in ["tank", "vest", "singlet", "sleeveless", "camisole", "inner"]):
        return "Inner Layer (Tank Top)"
    if any(k in fn for k in ["pant", "jean", "trouser", "chino", "short", "skirt", "bottom", "jogger"]):
        return "Bottomwear"
    if any(k in fn for k in ["shoe", "sneaker", "boot", "loafer", "footwear", "derby", "slide"]):
        return "Footwear"
    if any(k in fn for k in ["jacket", "blazer", "coat", "hoodie", "cardigan", "outerwear", "bomber"]):
        return "Outerwear (Layer)"
    if any(k in fn for k in ["shirt", "tee", "tshirt", "polo", "top", "linen"]):
        return "Topwear"

    # 2. Geometric & Morphological Analysis
    w, h = img.size
    aspect_ratio = h / float(w)

    # Footwear is predominantly horizontal
    if aspect_ratio < 0.70:
        return "Footwear"

    # Sample background color from image border
    bg = img.getpixel((5, 5))
    def is_bg(x, y):
        try:
            p = img.getpixel((min(w-1, max(0, x)), min(h-1, max(0, y))))
            dist = math.sqrt((p[0]-bg[0])**2 + (p[1]-bg[1])**2 + (p[2]-bg[2])**2)
            return dist < 32 or (p[0] > 240 and p[1] > 240 and p[2] > 240 and bg[0] > 230)
        except Exception:
            return True

    # 3. Bottomwear Split Check:
    # In trousers/jeans, the lower 20% (around y = 85%) has a gap between two legs (centerline is background).
    # In tops and tank tops, the bottom hem is continuous fabric (centerline is fabric).
    y_lower = int(h * 0.85)
    center_is_gap = is_bg(w // 2, y_lower)
    left_is_leg = not is_bg(int(w * 0.28), y_lower)
    right_is_leg = not is_bg(int(w * 0.72), y_lower)

    # Only classify as Bottomwear if there's an actual leg gap AND tall profile
    if aspect_ratio > 1.4 and center_is_gap and left_is_leg and right_is_leg:
        return "Bottomwear"

    # 4. Tank Top vs Regular Top:
    # A tank top is sleeveless: at shoulder level (y = 22%), the left 18% and right 18% are empty background.
    y_shoulder = int(h * 0.24)
    no_left_sleeve = is_bg(int(w * 0.12), y_shoulder)
    no_right_sleeve = is_bg(int(w * 0.88), y_shoulder)
    
    # Check for upper neckline cutout
    y_neck = int(h * 0.15)
    open_neck = is_bg(w // 2, y_neck)

    if (no_left_sleeve and no_right_sleeve) or (open_neck and aspect_ratio > 1.1):
        return "Inner Layer (Tank Top)"

    return "Topwear"


def classify_occasion(color, category, r, g, b):
    rn, gn, bn = r / 255.0, g / 255.0, b / 255.0
    _, l, s = colorsys.rgb_to_hls(rn, gn, bn)

    if category == "Inner Layer (Tank Top)":
        return "Casual"
    if category == "Topwear":
        if color in {"White", "Navy / Denim", "Grey"} and s < 0.4:
            return "Formal"
        if color in {"Beige / Khaki", "Olive / Green"}:
            return "Casual"
        if color in {"Red / Crimson", "Yellow / Orange"}:
            return "Party"
        return "Casual"
    if category == "Outerwear (Layer)":
        if color in {"Black", "Grey", "Navy / Denim"}:
            return "Semi-Formal"
        return "Casual"
    if category == "Bottomwear":
        if color in {"Grey", "Black"} and s < 0.2:
            return "Formal"
        if color == "Beige / Khaki":
            return "Semi-Formal"
        return "Casual"
    if category == "Footwear":
        if color in {"Brown", "Black"} and l < 0.4:
            return "Formal"
        return "Casual"
    return "Casual"


def analyze_image_file(image_path, filename=""):
    """
    Extracts category, dominant color, hex code, and occasion from image.
    Uses smart fabric pixel sampling (filters out plain background).
    """
    try:
        img = Image.open(image_path).convert("RGB")
        w, h = img.size

        # Detect category
        detected_category = detect_category_from_image(img, filename)

        # Sample fabric pixels by filtering out background
        bg = img.getpixel((5, 5))
        fabric_pixels = []

        step_x = max(1, w // 25)
        step_y = max(1, h // 25)

        for x in range(int(w * 0.2), int(w * 0.8), step_x):
            for y in range(int(h * 0.25), int(h * 0.8), step_y):
                p = img.getpixel((x, y))
                dist = math.sqrt((p[0]-bg[0])**2 + (p[1]-bg[1])**2 + (p[2]-bg[2])**2)
                # Ignore plain background
                if dist > 24 and not (p[0] > 242 and p[1] > 242 and p[2] > 242 and bg[0] > 230):
                    fabric_pixels.append(p)

        if not fabric_pixels:
            fabric_pixels = [img.getpixel((w // 2, h // 2))]

        avg_r = sum(p[0] for p in fabric_pixels) // len(fabric_pixels)
        avg_g = sum(p[1] for p in fabric_pixels) // len(fabric_pixels)
        avg_b = sum(p[2] for p in fabric_pixels) // len(fabric_pixels)

        detected_hex = rgb_to_hex(avg_r, avg_g, avg_b)
        detected_color = classify_rgb(avg_r, avg_g, avg_b)
        detected_occasion = classify_occasion(detected_color, detected_category, avg_r, avg_g, avg_b)

        return {
            "category": detected_category,
            "color": detected_color,
            "hex": detected_hex,
            "occasion": detected_occasion
        }
    except Exception as e:
        print(f"Analysis error: {e}")
        return {
            "category": "Topwear",
            "color": "White",
            "hex": "#ffffff",
            "occasion": "Casual"
        }


def get_default_avatar_svg(category, color_hex, name):
    icons = {
        "Topwear": "👕",
        "Inner Layer (Tank Top)": "🎽",
        "Bottomwear": "👖",
        "Footwear": "👟",
        "Outerwear (Layer)": "🧥"
    }
    icon = icons.get(category, "👕")
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
        <rect width="100%" height="100%" fill="{color_hex}" rx="16"/>
        <text x="50%" y="45%" font-size="70" text-anchor="middle" dominant-baseline="middle">{icon}</text>
        <text x="50%" y="75%" font-size="20" font-weight="bold" fill="#ffffff" text-anchor="middle" font-family="system-ui, sans-serif">{name}</text>
    </svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


# -----------------------------------------------------------------------------
# Wardrobe State: Clean & Empty on First Visit
# -----------------------------------------------------------------------------
wardrobe_items = []


def match_color_harmony(outfit_colors_set):
    """
    Checks if the outfit's colors match any classical color harmony.
    """
    for palette in CURATED_COLOR_HARMONIES:
        intersection = outfit_colors_set.intersection(palette["colors"])
        if len(intersection) >= 2:
            return True, palette
    return False, None


def calculate_outfit_score(top=None, bottom=None, shoes=None, layer=None, tank=None):
    """
    Evaluates color harmony, style coherence, and occasion alignment.
    Strict Rule: Tank tops are ONLY used when layered with a topwear shirt OR outerwear jacket.
    """
    all_pieces = [p for p in [tank, top, layer, bottom, shoes] if p is not None]
    colors = [p["color"] for p in all_pieces]
    occasions = [p["occasion"] for p in all_pieces]
    unique_colors = set(colors)

    if tank:
        if not top and not layer:
            return 0, "Invalid", "Tank tops must be layered under shirts or jackets."
        tank_bonus = 6
        vibe_extra = "Layered Street Style"
    else:
        tank_bonus = 0
        vibe_extra = "Classic Cohesive"

    score = 80 + tank_bonus

    has_harmony, palette = match_color_harmony(unique_colors)
    if has_harmony and palette:
        score += 12
        vibe = f"✨ Curated Harmony ({palette['name']})"
        reason_color = f"Color Harmony: {palette['desc']}"
    else:
        if all(c in NEUTRALS for c in colors):
            score += 8
            vibe = f"Minimalist Neutral Palette ({vibe_extra})"
            reason_color = "Clean timeless neutral harmony"
        else:
            vibe = f"Coordinated Modern ({vibe_extra})"
            reason_color = "Balanced tonal color pairing"

    unique_occ = set(occasions)
    if len(unique_occ) == 1:
        score += 6
        reason_occ = f"Cohesive {occasions[0]} aesthetic"
    elif "Formal" in unique_occ and "Athletic" in unique_occ:
        score -= 20
        reason_occ = "Contrasting formal & athletic garments"
    else:
        score += 4
        reason_occ = "Versatile smart-casual balance"

    top_piece = top or layer or tank
    if top_piece and bottom:
        if (top_piece["color"] in {"White", "Beige / Khaki"} and bottom["color"] in {"Black", "Navy / Denim"}) or \
           (top_piece["color"] in {"Black", "Navy / Denim"} and bottom["color"] in {"White", "Beige / Khaki"}):
            score += 4

    final_score = max(50, min(100, score))
    return final_score, vibe, f"{reason_occ} • {reason_color}"


# -----------------------------------------------------------------------------
# Web Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("wardrobe.html")


@app.route("/api/stats")
def get_stats():
    tops = sum(1 for i in wardrobe_items if i["category"] == "Topwear")
    tanks = sum(1 for i in wardrobe_items if i["category"] == "Inner Layer (Tank Top)")
    bottoms = sum(1 for i in wardrobe_items if i["category"] == "Bottomwear")
    shoes = sum(1 for i in wardrobe_items if i["category"] == "Footwear")
    layers = sum(1 for i in wardrobe_items if i["category"] == "Outerwear (Layer)")

    base = tops * bottoms * shoes
    standard_layered = base * layers if layers else 0
    tank_with_top = (tanks * tops * bottoms * shoes) if tanks and tops else 0
    tank_with_layer = (tanks * layers * bottoms * shoes) if tanks and layers else 0
    tank_triple_layer = (tanks * tops * layers * bottoms * shoes) if tanks and tops and layers else 0

    total = base + standard_layered + tank_with_top + tank_with_layer + tank_triple_layer

    return jsonify({
        "tops": tops,
        "tanks": tanks,
        "bottoms": bottoms,
        "shoes": shoes,
        "layers": layers,
        "total_combinations": total,
        "total_items": len(wardrobe_items)
    })


@app.route("/api/detect", methods=["POST"])
def detect_photo():
    temp_path = None
    filename = ""

    if "photo" in request.files and request.files["photo"].filename != "":
        file = request.files["photo"]
        filename = file.filename
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
        temp_name = f"temp_{uuid.uuid4().hex}.{ext}"
        temp_path = os.path.join(UPLOAD_FOLDER, temp_name)
        file.save(temp_path)
    elif "camera_data" in request.form and request.form["camera_data"]:
        raw_b64 = request.form["camera_data"]
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",")[1]
        img_bytes = base64.b64decode(raw_b64)
        temp_name = f"temp_{uuid.uuid4().hex}.jpg"
        temp_path = os.path.join(UPLOAD_FOLDER, temp_name)
        with open(temp_path, "wb") as f:
            f.write(img_bytes)

    if temp_path and os.path.exists(temp_path):
        result = analyze_image_file(temp_path, filename)
        try:
            os.remove(temp_path)
        except Exception:
            pass
        return jsonify(result)

    return jsonify({
        "category": "Topwear",
        "color": "White",
        "hex": "#ffffff",
        "occasion": "Casual"
    })


@app.route("/api/items", methods=["GET"])
def list_items():
    return jsonify(wardrobe_items)


@app.route("/api/items", methods=["POST"])
def add_item():
    data = request.form
    name = data.get("name", "").strip()
    category = data.get("category", "auto")
    color = data.get("color", "auto")
    exact_hex = data.get("hex", "").strip()
    occasion = data.get("occasion", "auto")

    if not name:
        return jsonify({"error": "Item name is required"}), 400

    image_url = None
    saved_filepath = None
    filename_str = ""

    if "photo" in request.files and request.files["photo"].filename != "":
        file = request.files["photo"]
        filename_str = file.filename
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
        filename = f"{uuid.uuid4().hex}.{ext}"
        saved_filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(saved_filepath)
        image_url = f"/static/uploads/{filename}"
    elif "camera_data" in data and data["camera_data"]:
        raw_b64 = data["camera_data"]
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",")[1]
        img_bytes = base64.b64decode(raw_b64)
        filename = f"{uuid.uuid4().hex}.jpg"
        saved_filepath = os.path.join(UPLOAD_FOLDER, filename)
        with open(saved_filepath, "wb") as f:
            f.write(img_bytes)
        image_url = f"/static/uploads/{filename}"

    detected = {}
    if saved_filepath and os.path.exists(saved_filepath):
        detected = analyze_image_file(saved_filepath, filename_str)

    # Respect user explicit selections
    final_category = category if (category and category != "auto") else detected.get("category", "Topwear")
    final_color = color if (color and color != "auto") else detected.get("color", "White")
    final_hex = exact_hex if exact_hex else detected.get("hex", "#ffffff")
    final_occasion = occasion if (occasion and occasion != "auto") else detected.get("occasion", "Casual")

    if exact_hex and (color == "auto" or not color):
        r, g, b = hex_to_rgb(exact_hex)
        final_color = classify_rgb(r, g, b)

    if not image_url:
        image_url = get_default_avatar_svg(final_category, final_hex, name)

    new_item = {
        "id": str(uuid.uuid4().hex[:8]),
        "name": name,
        "category": final_category,
        "color": final_color,
        "hex": final_hex,
        "occasion": final_occasion,
        "image": image_url
    }
    wardrobe_items.append(new_item)
    return jsonify(new_item), 201


@app.route("/api/items/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    global wardrobe_items
    wardrobe_items = [i for i in wardrobe_items if i["id"] != item_id]
    return jsonify({"success": True})


@app.route("/api/clear-all", methods=["POST"])
def clear_all():
    global wardrobe_items
    wardrobe_items = []
    return jsonify({"success": True})


@app.route("/api/outfits", methods=["GET"])
def get_outfits():
    min_score = int(request.args.get("min_score", 70))
    occasion = request.args.get("occasion", "All")
    include_layers = request.args.get("include_layers", "true") == "true"
    include_tanks = request.args.get("include_tanks", "true") == "true"

    tops = [i for i in wardrobe_items if i["category"] == "Topwear"]
    tanks = [i for i in wardrobe_items if i["category"] == "Inner Layer (Tank Top)"]
    bottoms = [i for i in wardrobe_items if i["category"] == "Bottomwear"]
    shoes = [i for i in wardrobe_items if i["category"] == "Footwear"]
    layers = [i for i in wardrobe_items if i["category"] == "Outerwear (Layer)"]

    if not bottoms or not shoes or (not tops and not (tanks and layers)):
        return jsonify({
            "outfits": [],
            "message": "Add at least 1 Topwear, 1 Bottomwear, and 1 Footwear (or Tank Top + Jacket) to generate outfits."
        })

    results = []

    # 1. Standard 3-Piece Outfit (Topwear + Bottom + Shoes)
    for t, b, s in itertools.product(tops, bottoms, shoes):
        score, vibe, reason = calculate_outfit_score(top=t, bottom=b, shoes=s, layer=None, tank=None)
        if score >= min_score:
            if occasion == "All" or t["occasion"] == occasion or b["occasion"] == occasion:
                results.append({
                    "id": f"{t['id']}_{b['id']}_{s['id']}",
                    "type": "Standard Look",
                    "tank": None, "top": t, "bottom": b, "shoes": s, "layer": None,
                    "score": score, "vibe": vibe, "reason": reason
                })

    # 2. Standard Layered 4-Piece (Topwear + Jacket + Bottom + Shoes)
    if include_layers and layers:
        for t, b, s, l in itertools.product(tops, bottoms, shoes, layers):
            score, vibe, reason = calculate_outfit_score(top=t, bottom=b, shoes=s, layer=l, tank=None)
            if score >= min_score:
                if occasion == "All" or t["occasion"] == occasion or b["occasion"] == occasion:
                    results.append({
                        "id": f"{t['id']}_{b['id']}_{s['id']}_{l['id']}",
                        "type": "Jacket Layered",
                        "tank": None, "top": t, "bottom": b, "shoes": s, "layer": l,
                        "score": score, "vibe": vibe, "reason": reason
                    })

    # 3. Tank Top Layered Under Shirt (Tank + Topwear + Bottom + Shoes)
    if include_tanks and tanks and tops:
        for tk, t, b, s in itertools.product(tanks, tops, bottoms, shoes):
            score, vibe, reason = calculate_outfit_score(top=t, bottom=b, shoes=s, layer=None, tank=tk)
            if score >= min_score:
                if occasion == "All" or tk["occasion"] == occasion or t["occasion"] == occasion:
                    results.append({
                        "id": f"{tk['id']}_{t['id']}_{b['id']}_{s['id']}",
                        "type": "Tank + Open Shirt Layer",
                        "tank": tk, "top": t, "bottom": b, "shoes": s, "layer": None,
                        "score": score, "vibe": vibe,
                        "reason": f"🎽 Inner Tank Top under {t['name']}. {reason}"
                    })

    # 4. Tank Top Layered Under Jacket (Tank + Jacket + Bottom + Shoes)
    if include_tanks and include_layers and tanks and layers:
        for tk, l, b, s in itertools.product(tanks, layers, bottoms, shoes):
            score, vibe, reason = calculate_outfit_score(top=None, bottom=b, shoes=s, layer=l, tank=tk)
            if score >= min_score:
                if occasion == "All" or tk["occasion"] == occasion or l["occasion"] == occasion:
                    results.append({
                        "id": f"{tk['id']}_{l['id']}_{b['id']}_{s['id']}",
                        "type": "Tank + Outerwear Layer",
                        "tank": tk, "top": None, "bottom": b, "shoes": s, "layer": l,
                        "score": score, "vibe": vibe,
                        "reason": f"🎽 Inner Tank Top styled with {l['name']}. {reason}"
                    })

    # 5. Full 3-Layer Masterclass (Tank + Shirt + Jacket + Bottom + Shoes)
    if include_tanks and include_layers and tanks and tops and layers:
        for tk, t, l, b, s in itertools.product(tanks, tops, layers, bottoms, shoes):
            score, vibe, reason = calculate_outfit_score(top=t, bottom=b, shoes=s, layer=l, tank=tk)
            if score >= min_score:
                if occasion == "All" or tk["occasion"] == occasion or t["occasion"] == occasion:
                    results.append({
                        "id": f"{tk['id']}_{t['id']}_{l['id']}_{b['id']}_{s['id']}",
                        "type": "Triple Layer Masterclass",
                        "tank": tk, "top": t, "bottom": b, "shoes": s, "layer": l,
                        "score": score, "vibe": vibe,
                        "reason": f"🎽 Inner Tank Top + {t['name']} + {l['name']}. {reason}"
                    })

    results.sort(key=lambda x: x["score"], reverse=True)
    return jsonify({
        "total_generated": len(results),
        "outfits": results[:90]
    })


if __name__ == "__main__":
    print("Starting StyleMatrix on http://localhost:5000 ...")
    app.run(debug=True, port=5000)
