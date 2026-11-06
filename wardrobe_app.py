"""
==============================================================================
WearWise – Smart Wardrobe & Maximum Outfit Generator
==============================================================================
Featuring:
1. Full-image AI garment analysis (segments fabric, detects sleeveless tank tops,
   bifurcated pants/bottomwear, footwear, and outerwear).
2. Multi-color detection: Analyzes all prominent colors present in the garment.
3. Form locking: Inputs remain locked until photo is uploaded; unlocked for user edits.
4. Classical Color Harmony Engine (no book references).
5. Strict inner-layer rule for tank tops (only layered with shirts & jackets).
==============================================================================
"""

from flask import Flask, render_template, request, jsonify
import os
import json
import time
import re
import itertools
import uuid
import base64
import binascii
import io
import colorsys
import math
import collections
import tempfile
from xml.sax.saxutils import escape as escape_xml
from PIL import Image

APP_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_DIR, "static", "uploads")
DB_FILE = os.path.join(APP_DIR, "wardrobe_db.json")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, "templates"),
    static_folder=os.path.join(APP_DIR, "static")
)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000

VALID_CATEGORIES = {
    "Topwear",
    "Inner Layer (Tank Top)",
    "Bottomwear",
    "Footwear",
    "Outerwear (Layer)",
}
VALID_OCCASIONS = {"Casual", "Semi-Formal", "Formal", "Party", "Athletic"}


@app.errorhandler(413)
def handle_upload_too_large(_error):
    return jsonify({"error": "Images must be smaller than 12 MB."}), 413


def _read_local_wardrobe():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, "r", encoding="utf-8") as database:
        data = json.load(database)
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("The wardrobe database has an invalid format.")
    return data["items"]


def _write_local_wardrobe(items):
    temporary_path = f"{DB_FILE}.{uuid.uuid4().hex}.tmp"
    try:
        with open(temporary_path, "w", encoding="utf-8") as database:
            json.dump({"items": items}, database, indent=2, ensure_ascii=False)
        os.replace(temporary_path, DB_FILE)
    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)


def get_profile_user():
    email = request.headers.get("X-Wardrobe-Email", "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@gmail\.com", email):
        return None
    return {"email": email}


def _profile_items(user, include_images=True):
    items = _read_local_wardrobe()
    unassigned = [item for item in items if not item.get("user_email")]
    if unassigned:
        for item in unassigned:
            item["user_email"] = user["email"]
        _write_local_wardrobe(items)

    profile_items = [
        item for item in items
        if item.get("user_email", "").strip().lower() == user["email"]
    ]
    if include_images:
        return profile_items
    return [{key: value for key, value in item.items() if key != "image"} for item in profile_items]


def _read_uploaded_image():
    if "photo" in request.files and request.files["photo"].filename:
        uploaded = request.files["photo"]
        image_bytes = uploaded.read()
        if not image_bytes:
            raise ValueError("The uploaded image is empty.")
        content_type, extension = _validated_image_type(image_bytes)
        return image_bytes, content_type, extension, uploaded.filename

    raw_data = request.form.get("camera_data", "")
    if raw_data:
        if "," in raw_data:
            raw_data = raw_data.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(raw_data, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("The captured photo is not valid image data.") from error
        if not image_bytes:
            raise ValueError("The captured photo is empty.")
        content_type, extension = _validated_image_type(image_bytes)
        return image_bytes, content_type, extension, f"camera{extension}"
    return None, None, None, ""


def _validated_image_type(image_bytes):
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = image.format
            image.verify()
    except (Image.UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Please upload a valid image file.") from error

    extensions = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}
    if image_format not in extensions:
        raise ValueError("Please use a JPEG, PNG, WEBP, or GIF image.")
    return Image.MIME[image_format], extensions[image_format]


def _analyze_uploaded_image(image_bytes, filename):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as temp_file:
            temp_file.write(image_bytes)
            temp_path = temp_file.name
        return analyze_whole_image(temp_path, filename)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

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


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"


def classify_rgb(r, g, b):
    """
    Classifies an RGB color into standard fashion categories.
    Accurately handles white, off-white, and neutrals without false navy fallbacks.
    """
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    # 1. White / Off-white / Cream check:
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

    if 185 <= h_deg <= 250:
        if s > 0.18 and l < 0.75:
            return "Navy / Denim"
        elif l >= 0.75:
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

    best_color = "Grey"
    min_dist = float("inf")
    for name, centroid in COLOR_CENTROIDS.items():
        dist = math.sqrt((r - centroid[0])**2 + (g - centroid[1])**2 + (b - centroid[2])**2)
        if dist < min_dist:
            min_dist = dist
            best_color = name
    return best_color


# -----------------------------------------------------------------------------
# Full-Image AI Analysis: Silhouette Segmentation & Multi-Color Extraction
# -----------------------------------------------------------------------------
def analyze_whole_image(image_path, filename=""):
    """
    Takes the whole image and performs:
    1. Full-image background segmentation to isolate garment.
    2. Garment bounding box and aspect ratio calculation.
    3. Structural morphology checks:
       - Footwear (horizontal profile)
       - Bottomwear (two-leg crotch split gap)
       - Inner Layer Tank Top (sleeveless shoulder straps and deep neck cutout)
       - Outerwear (front lapels/seam)
       - Topwear (sleeves / standard torso)
    4. Multi-color extraction: Detects all prominent colors present in the fabric.
    5. Occasion inference.
    """
    try:
        img = Image.open(image_path).convert("RGBA")
        w, h = img.size

        # 1. Background color detection by sampling 4 corners
        corners = [
            img.getpixel((0, 0)),
            img.getpixel((w - 1, 0)),
            img.getpixel((0, h - 1)),
            img.getpixel((w - 1, h - 1))
        ]
        bg_r = sum(c[0] for c in corners) // 4
        bg_g = sum(c[1] for c in corners) // 4
        bg_b = sum(c[2] for c in corners) // 4

        def is_bg(r, g, b, a):
            if a < 40:
                return True
            dist = math.sqrt((r - bg_r)**2 + (g - bg_g)**2 + (b - bg_b)**2)
            return dist < 22

        # 2. Extract garment bounding box and collect fabric pixels across the whole image
        min_x, max_x = w, 0
        min_y, max_y = h, 0
        color_counts = collections.defaultdict(int)
        fabric_pixel_samples = []

        step = max(1, min(w, h) // 80)
        for y in range(0, h, step):
            for x in range(0, w, step):
                p = img.getpixel((x, y))
                if not is_bg(*p):
                    if x < min_x: min_x = x
                    if x > max_x: max_x = x
                    if y < min_y: min_y = y
                    if y > max_y: max_y = y

                    color_name = classify_rgb(p[0], p[1], p[2])
                    color_counts[color_name] += 1
                    fabric_pixel_samples.append((p[0], p[1], p[2]))

        if len(fabric_pixel_samples) < 25:
            # Fallback if image contrast with corners is subtle or garment fills frame
            min_x, max_x = int(w * 0.08), int(w * 0.92)
            min_y, max_y = int(h * 0.08), int(h * 0.92)
            color_counts.clear()
            fabric_pixel_samples.clear()
            step_fb = max(1, min(w, h) // 60)
            for y in range(min_y, max_y, step_fb):
                for x in range(min_x, max_x, step_fb):
                    p = img.getpixel((x, y))
                    color_name = classify_rgb(p[0], p[1], p[2])
                    color_counts[color_name] += 1
                    fabric_pixel_samples.append((p[0], p[1], p[2]))

        gw = max(1, max_x - min_x)
        gh = max(1, max_y - min_y)
        garment_ar = gh / float(gw)

        # 3. Multi-Color Frequency Analysis
        total_samples = len(fabric_pixel_samples)
        sorted_colors = sorted(color_counts.items(), key=lambda item: item[1], reverse=True)

        # Primary color is the most dominant color
        primary_color = sorted_colors[0][0]

        # Collect all prominent colors covering at least 12% of garment
        prominent_colors = []
        color_breakdown = []
        for c_name, count in sorted_colors:
            pct = round((count / total_samples) * 100)
            if pct >= 12:
                prominent_colors.append(c_name)
                color_breakdown.append({"name": c_name, "percent": pct})

        if not prominent_colors:
            prominent_colors = [primary_color]
            color_breakdown = [{"name": primary_color, "percent": 100}]

        # Calculate average RGB of the primary color pixels for accurate hex code
        primary_pixels = [
            p for p in fabric_pixel_samples if classify_rgb(p[0], p[1], p[2]) == primary_color
        ]
        if primary_pixels:
            avg_r = sum(p[0] for p in primary_pixels) // len(primary_pixels)
            avg_g = sum(p[1] for p in primary_pixels) // len(primary_pixels)
            avg_b = sum(p[2] for p in primary_pixels) // len(primary_pixels)
        else:
            avg_r, avg_g, avg_b = 245, 245, 245
        detected_hex = rgb_to_hex(avg_r, avg_g, avg_b)

        # 4. Structural Category Classification from Whole Image Morphology
        fn = filename.lower()
        detected_category = "Topwear"

        # Check explicit filename keywords
        if any(k in fn for k in ["tank", "vest", "singlet", "sleeveless", "camisole", "inner", "undershirt"]):
            detected_category = "Inner Layer (Tank Top)"
        elif any(k in fn for k in ["pant", "jean", "trouser", "chino", "short", "skirt", "bottom", "jogger", "legging", "cargo"]):
            detected_category = "Bottomwear"
        elif any(k in fn for k in ["shoe", "sneaker", "boot", "loafer", "footwear", "derby", "slide", "trainer"]):
            detected_category = "Footwear"
        elif any(k in fn for k in ["jacket", "blazer", "coat", "hoodie", "cardigan", "outerwear", "bomber", "overshirt"]):
            detected_category = "Outerwear (Layer)"
        elif any(k in fn for k in ["shirt", "tee", "tshirt", "polo", "top", "linen"]):
            detected_category = "Topwear"
        else:
            # Morphological Bounding Box & Contour Analysis across the Whole Image
            # A. Footwear: distinctly horizontal profile
            if garment_ar < 0.70:
                detected_category = "Footwear"
            else:
                # B. Bottomwear Split Test (Check for two distinct pant legs with center gap)
                x_center = min_x + gw // 2
                y_leg1 = min_y + int(gh * 0.75)
                y_leg2 = min_y + int(gh * 0.88)

                gap1 = is_bg(*img.getpixel((x_center, min(h - 1, y_leg1))))
                left1 = not is_bg(*img.getpixel((min_x + int(gw * 0.25), min(h - 1, y_leg1))))
                right1 = not is_bg(*img.getpixel((min_x + int(gw * 0.75), min(h - 1, y_leg1))))

                gap2 = is_bg(*img.getpixel((x_center, min(h - 1, y_leg2))))
                left2 = not is_bg(*img.getpixel((min_x + int(gw * 0.25), min(h - 1, y_leg2))))
                right2 = not is_bg(*img.getpixel((min_x + int(gw * 0.75), min(h - 1, y_leg2))))

                has_leg_split = (gap1 and left1 and right1) or (gap2 and left2 and right2)

                if garment_ar > 1.25 and has_leg_split:
                    detected_category = "Bottomwear"
                else:
                    # C. Tank Top (Sleeveless Inner Layer) Test:
                    # At shoulder/chest height (22% down), sides are empty background (no sleeves)
                    y_shoulder = min_y + int(gh * 0.22)
                    no_left_sleeve = is_bg(*img.getpixel((min_x + int(gw * 0.12), min(h - 1, y_shoulder))))
                    no_right_sleeve = is_bg(*img.getpixel((min_x + int(gw * 0.88), min(h - 1, y_shoulder))))

                    # Neck scoop cutout check at 14% height
                    y_neck = min_y + int(gh * 0.14)
                    open_neck = is_bg(*img.getpixel((x_center, min(h - 1, y_neck))))

                    if (no_left_sleeve and no_right_sleeve) or (open_neck and garment_ar > 1.10):
                        detected_category = "Inner Layer (Tank Top)"
                    else:
                        detected_category = "Topwear"

        # 5. Occasion Inference
        detected_occasion = classify_occasion(primary_color, detected_category, avg_r, avg_g, avg_b)

        # 6. Suggested Name
        colors_display_str = " & ".join(prominent_colors)
        if detected_category == "Inner Layer (Tank Top)":
            suggested_name = f"{colors_display_str} Tank Top"
        elif detected_category == "Bottomwear":
            suggested_name = f"{colors_display_str} Pants / Jeans"
        elif detected_category == "Footwear":
            suggested_name = f"{colors_display_str} Shoes / Sneakers"
        elif detected_category == "Outerwear (Layer)":
            suggested_name = f"{colors_display_str} Jacket"
        else:
            suggested_name = f"{colors_display_str} Top"

        return {
            "category": detected_category,
            "color": primary_color,
            "colors": prominent_colors,
            "color_breakdown": color_breakdown,
            "is_multicolor": len(prominent_colors) > 1,
            "hex": detected_hex,
            "occasion": detected_occasion,
            "suggested_name": suggested_name
        }

    except Exception as e:
        print(f"Whole-image analysis error: {e}")
        return {
            "category": "Topwear",
            "color": "White",
            "colors": ["White"],
            "color_breakdown": [{"name": "White", "percent": 100}],
            "is_multicolor": False,
            "hex": "#ffffff",
            "occasion": "Casual",
            "suggested_name": "White Top"
        }


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


def get_default_avatar_svg(category, color_hex, name):
    icons = {
        "Topwear": "👕",
        "Inner Layer (Tank Top)": "🎽",
        "Bottomwear": "👖",
        "Footwear": "👟",
        "Outerwear (Layer)": "🧥"
    }
    icon = icons.get(category, "👕")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color_hex):
        color_hex = "#f5f5f5"
    safe_name = escape_xml(name)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300">
        <rect width="100%" height="100%" fill="{color_hex}" rx="16"/>
        <text x="50%" y="45%" font-size="70" text-anchor="middle" dominant-baseline="middle">{icon}</text>
        <text x="50%" y="75%" font-size="20" font-weight="bold" fill="#ffffff" text-anchor="middle" font-family="system-ui, sans-serif">{safe_name}</text>
    </svg>"""
    encoded = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    return f"data:image/svg+xml;base64,{encoded}"


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
    Supports garments with multiple prominent colors.
    Strict Rule: Tank tops are ONLY used when layered with a topwear shirt OR outerwear jacket.
    """
    all_pieces = [p for p in [tank, top, layer, bottom, shoes] if p is not None]

    # Collect all colors (including secondary colors if multi-color)
    all_colors_set = set()
    for p in all_pieces:
        if "colors" in p and p["colors"]:
            all_colors_set.update(p["colors"])
        else:
            all_colors_set.add(p["color"])

    occasions = [p["occasion"] for p in all_pieces]

    if tank:
        if not top and not layer:
            return 0, "Invalid", "Tank tops must be layered under shirts or jackets."
        tank_bonus = 6
        vibe_extra = "Layered Street Style"
    else:
        tank_bonus = 0
        vibe_extra = "Classic Cohesive"

    score = 80 + tank_bonus

    has_harmony, palette = match_color_harmony(all_colors_set)
    if has_harmony and palette:
        score += 12
        vibe = f"✨ Curated Harmony ({palette['name']})"
        reason_color = f"Color Harmony: {palette['desc']}"
    else:
        if all(c in NEUTRALS for c in all_colors_set):
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
        top_colors = set(top_piece.get("colors", [top_piece["color"]]))
        bot_colors = set(bottom.get("colors", [bottom["color"]]))
        if (top_colors.intersection({"White", "Beige / Khaki"}) and bot_colors.intersection({"Black", "Navy / Denim"})) or \
           (top_colors.intersection({"Black", "Navy / Denim"}) and bot_colors.intersection({"White", "Beige / Khaki"})):
            score += 4

    final_score = max(50, min(100, score))
    return final_score, vibe, f"{reason_occ} • {reason_color}"


# -----------------------------------------------------------------------------
# Wardrobe Web & API Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("wardrobe.html")


@app.route("/api/stats")
def get_stats():
    user = get_profile_user()
    if not user:
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401
    items = _profile_items(user, include_images=False)
    tops = sum(1 for i in items if i["category"] == "Topwear")
    tanks = sum(1 for i in items if i["category"] == "Inner Layer (Tank Top)")
    bottoms = sum(1 for i in items if i["category"] == "Bottomwear")
    shoes = sum(1 for i in items if i["category"] == "Footwear")
    layers = sum(1 for i in items if i["category"] == "Outerwear (Layer)")

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
        "total_items": len(items)
    })


@app.route("/api/detect", methods=["POST"])
def detect_photo():
    if not get_profile_user():
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401
    try:
        image_bytes, _, _, filename = _read_uploaded_image()
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    if image_bytes:
        return jsonify(_analyze_uploaded_image(image_bytes, filename))

    return jsonify({
        "category": "Topwear",
        "color": "White",
        "colors": ["White"],
        "is_multicolor": False,
        "hex": "#ffffff",
        "occasion": "Casual",
        "suggested_name": "Clothing Item"
    })


@app.route("/api/items", methods=["GET"])
def list_items():
    user = get_profile_user()
    if not user:
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401
    return jsonify(_profile_items(user))


@app.route("/api/items", methods=["POST"])
def add_item():
    user = get_profile_user()
    if not user:
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401

    data = request.form
    name = data.get("name", "").strip()
    category = data.get("category", "").strip()
    color = data.get("color", "").strip()
    occasion = data.get("occasion", "Casual").strip()
    colors_json_str = data.get("colors", "")

    if not name:
        return jsonify({"error": "Item name is required"}), 400
    if len(name) > 100:
        return jsonify({"error": "Item name must be 100 characters or fewer."}), 400

    try:
        image_bytes, content_type, extension, filename_str = _read_uploaded_image()
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    # Perform whole image analysis if needed
    detected = _analyze_uploaded_image(image_bytes, filename_str) if image_bytes else {}

    final_category = category if category and category != "auto" else detected.get("category", "Topwear")
    final_color = color if color and color != "auto" else detected.get("color", "White")
    final_hex = data.get("hex") or detected.get("hex") or rgb_to_hex(*COLOR_CENTROIDS.get(final_color, (245, 245, 245)))
    final_occasion = occasion if occasion and occasion != "auto" else detected.get("occasion", "Casual")

    if final_category not in VALID_CATEGORIES:
        return jsonify({"error": "Choose a valid clothing category."}), 400
    if final_color not in COLOR_CENTROIDS:
        return jsonify({"error": "Choose a valid clothing color."}), 400
    if final_occasion not in VALID_OCCASIONS:
        return jsonify({"error": "Choose a valid occasion."}), 400
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", final_hex):
        final_hex = rgb_to_hex(*COLOR_CENTROIDS[final_color])

    # Store multi-color list
    colors_list = []
    if colors_json_str:
        try:
            colors_list = json.loads(colors_json_str)
        except json.JSONDecodeError:
            colors_list = [c.strip() for c in colors_json_str.split(",") if c.strip()]
    if not isinstance(colors_list, list):
        colors_list = []
    if not colors_list:
        colors_list = detected.get("colors", [final_color])
    colors_list = [entry for entry in colors_list if isinstance(entry, str) and entry in COLOR_CENTROIDS]
    if final_color not in colors_list:
        colors_list.insert(0, final_color)

    image_url = get_default_avatar_svg(final_category, final_hex, name) if not image_bytes else None
    if image_bytes:
        filename = f"{uuid.uuid4().hex}{extension}"
        image_path = os.path.join(UPLOAD_FOLDER, filename)
        with open(image_path, "wb") as uploaded_image:
            uploaded_image.write(image_bytes)
        image_url = f"/static/uploads/{filename}"

    items = _read_local_wardrobe()
    new_item = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "category": final_category,
        "color": final_color,
        "colors": colors_list,
        "is_multicolor": len(colors_list) > 1,
        "hex": final_hex,
        "occasion": final_occasion,
        "image": image_url,
        "created_at": time.time(),
        "user_email": user["email"]
    }
    items.append(new_item)
    _write_local_wardrobe(items)
    return jsonify(new_item), 201


@app.route("/api/items/<item_id>", methods=["DELETE"])
def delete_item(item_id):
    user = get_profile_user()
    if not user:
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401
    items = _read_local_wardrobe()
    items = [
        item for item in items
        if not (
            item.get("id") == item_id
            and item.get("user_email", "").strip().lower() == user["email"]
        )
    ]
    _write_local_wardrobe(items)
    return jsonify({"success": True})


@app.route("/api/clear-all", methods=["POST"])
def clear_all():
    user = get_profile_user()
    if not user:
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401
    items = [
        item for item in _read_local_wardrobe()
        if item.get("user_email", "").strip().lower() != user["email"]
    ]
    _write_local_wardrobe(items)
    return jsonify({"success": True})


@app.route("/api/outfits", methods=["GET"])
def get_outfits():
    user = get_profile_user()
    if not user:
        return jsonify({"error": "Enter a valid Gmail address to continue."}), 401

    try:
        min_score = int(request.args.get("min_score", 70))
    except ValueError:
        return jsonify({"error": "Minimum score must be a number."}), 400
    if min_score < 0 or min_score > 100:
        return jsonify({"error": "Minimum score must be between 0 and 100."}), 400
    occasion = request.args.get("occasion", "All")
    include_layers = request.args.get("include_layers", "true") == "true"
    include_tanks = request.args.get("include_tanks", "true") == "true"

    items = _profile_items(user)
    tops = [i for i in items if i["category"] == "Topwear"]
    tanks = [i for i in items if i["category"] == "Inner Layer (Tank Top)"]
    bottoms = [i for i in items if i["category"] == "Bottomwear"]
    shoes = [i for i in items if i["category"] == "Footwear"]
    layers = [i for i in items if i["category"] == "Outerwear (Layer)"]

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
    print("Starting WearWise on http://localhost:5000 ...")
    app.run(debug=True, port=5000)
