"""
Image generation utilities for PricePoa infographics.

Ported from the mobile HTML design: a brand wordmark bar, a header card with
query / date badges and a store legend, one card per product with a grid of
per-store prices (cheapest highlighted in green, savings tags in red), a
"quick summary" card, and a verified footer.

Everything is laid out in *logical* pixels on a 390px-wide mobile canvas (the
same width as the HTML) and rendered at SS x supersampling, then downscaled to
OUT_SCALE x for crisp, anti-aliased edges.

Fonts: the design uses Plus Jakarta Sans (body) and Space Grotesk (prices and
labels). Drop these static TTFs into  <this folder>/fonts/  (or set the
PRICEPOA_FONT_DIR env var):
    PlusJakartaSans-Regular.ttf, PlusJakartaSans-SemiBold.ttf, PlusJakartaSans-Bold.ttf
    SpaceGrotesk-SemiBold.ttf,  SpaceGrotesk-Bold.ttf
If they are missing it falls back to DejaVu Sans, so nothing breaks.

Public API (unchanged from the previous generator):
    generate_product_options_image(data)
    generate_shopping_list_image(data)
    generate_single_product_image(data)
"""
from io import BytesIO
from datetime import datetime
import logging
import math
import os
import re

from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger("uvicorn.error")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BRAND_NAME = "PricePoa"
STATUS_LABEL = "VERIFIED"          # pill in the header card (the HTML says "Live")
CURRENCY = "KSh"
FOOTER_NOTE = "Prices verified by PricePoa"

LOGICAL_W = 390                    # same width as the HTML
MARGIN = 16
GAP = 12
CARD_W = LOGICAL_W - 2 * MARGIN    # 358
SHADOW_PAD = 14

SS = 3                             # supersampling factor while drawing
OUT_SCALE = 2                      # final pixels per logical px (390 -> 780 px wide)
MAX_SIDE_SUM = 9800                # Telegram sendPhoto: width + height <= 10000


def u(v):
    """Logical px -> supersampled px."""
    return int(round(v * SS))


# ---------------------------------------------------------------------------
# Palette (from the HTML's tailwind config)
# ---------------------------------------------------------------------------

def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """Blend a -> b; t is the share of b."""
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))


WHITE = (255, 255, 255)
SURFACE = hex_rgb("#fbf8ff")
SURFACE_LOW = hex_rgb("#f3f2ff")
SURFACE_CONT = hex_rgb("#ededfc")
SURFACE_HIGH = hex_rgb("#e7e7f6")
ON_SURFACE = hex_rgb("#191b25")
ON_SURFACE_VAR = hex_rgb("#474557")
OUTLINE_VAR = hex_rgb("#c8c4da")
PRIMARY = hex_rgb("#2e00b5")
PRIMARY_CONT = hex_rgb("#4100f5")
PRIMARY_FIXED = hex_rgb("#e4dfff")
ON_PRIMARY_FIXED = hex_rgb("#150066")
SECONDARY = hex_rgb("#006d38")
SECONDARY_CONT = hex_rgb("#74f9a0")
SECONDARY_FIXED = hex_rgb("#77fca3")
ON_SECONDARY_FIXED = hex_rgb("#00210d")
ON_SECONDARY_FIXED_VAR = hex_rgb("#005228")
TERTIARY = hex_rgb("#770003")
TERTIARY_FIXED = hex_rgb("#ffdad5")
ON_TERTIARY_FIXED_VAR = hex_rgb("#930005")
ERROR = hex_rgb("#ba1a1a")
BEST_BG = hex_rgb("#D4FCE3")
BEST_BORDER = hex_rgb("#059669")
BEST_TEXT = hex_rgb("#064E3B")

OUTLINE_SOFT = mix(WHITE, OUTLINE_VAR, 0.45)
ROW_BG = mix(WHITE, SURFACE_LOW, 0.6)
SUMMARY_BG = mix(WHITE, PRIMARY_FIXED, 0.3)

# (colour, alpha, dy, blur) in logical px
SHADOW_SM = ((0, 0, 0), 0.07, 1, 3)


def glow(color, alpha=0.14):
    return (color, alpha, 6, 8)


# Store themes: accent colour + legend pill colours. The first three match the
# HTML (Naivas green, Chandarana purple, Quickmart red); others fill in after.
STORE_THEMES = [
    dict(accent=SECONDARY, pill_bg=mix(SURFACE, SECONDARY_CONT, 0.4), pill_fg=ON_SECONDARY_FIXED_VAR),
    dict(accent=PRIMARY, pill_bg=SURFACE_CONT, pill_fg=PRIMARY),
    dict(accent=TERTIARY, pill_bg=TERTIARY_FIXED, pill_fg=ON_TERTIARY_FIXED_VAR),
    dict(accent=hex_rgb("#b45309"), pill_bg=hex_rgb("#fef3c7"), pill_fg=hex_rgb("#78350f")),
    dict(accent=hex_rgb("#0f766e"), pill_bg=hex_rgb("#ccfbf1"), pill_fg=hex_rgb("#134e4a")),
    dict(accent=hex_rgb("#be185d"), pill_bg=hex_rgb("#fce7f3"), pill_fg=hex_rgb("#831843")),
]
_PREFERRED_THEME = {"naivas": 0, "chandarana": 1, "quickmart": 2}
_KNOWN_CODES = {
    "naivas": "NVS", "chandarana": "CH", "quickmart": "QM", "carrefour": "CRF",
    "tuskys": "TSK", "eastmatt": "EM", "cleanshelf": "CS", "khetia": "KH",
}

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_DIR = os.environ.get("PRICEPOA_FONT_DIR") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fonts"
)
_FONT_FILES = {                      # role -> (file, is_bold_for_fallback)
    "body": ("PlusJakartaSans-Regular.ttf", False),
    "body_semi": ("PlusJakartaSans-SemiBold.ttf", True),
    "body_bold": ("PlusJakartaSans-Bold.ttf", True),
    "label_semi": ("SpaceGrotesk-SemiBold.ttf", True),
    "label_bold": ("SpaceGrotesk-Bold.ttf", True),
}
_FALLBACKS = {
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"],
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
}
_font_cache = {}
_font_warned = False


def font(role, size):
    """Font for a role at a logical size (cached)."""
    global _font_warned
    key = (role, size)
    if key in _font_cache:
        return _font_cache[key]
    fname, bold = _FONT_FILES[role]
    f = None
    for i, path in enumerate([os.path.join(FONT_DIR, fname)] + _FALLBACKS[bold]):
        try:
            f = ImageFont.truetype(path, u(size))
            if i > 0 and not _font_warned:
                logger.info(f"Infographic fonts not found in {FONT_DIR}; using fallback font")
                _font_warned = True
            break
        except (IOError, OSError):
            continue
    if f is None:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f


_SCRATCH = ImageDraw.Draw(Image.new("L", (4, 4)))


def tw(s, f):
    """Text width in logical px."""
    return _SCRATCH.textlength(s, font=f) / SS


def ellipsize(s, f, max_w):
    s = str(s)
    if tw(s, f) <= max_w:
        return s
    while s and tw(s.rstrip() + "\u2026", f) > max_w:
        s = s[:-1]
    return s.rstrip() + "\u2026"


def wrap_lines(s, f, max_w, max_lines=2):
    words = str(s or "").split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        if tw(trial, f) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return [ellipsize(l, f, max_w) for l in lines]


def fit_font(role, size, txt, max_w, min_size=10):
    s = size
    while s > min_size and tw(txt, font(role, s)) > max_w:
        s -= 0.5
    return font(role, s)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def parse_amount(value) -> float:
    """Pull a float out of things like '479 KES', '1,250', 479.0, etc."""
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = "".join(c for c in str(value) if c.isdigit() or c == ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def fmt_kes(v):
    if v is None:
        return "N/A"
    if abs(v - round(v)) < 0.005:
        return f"{CURRENCY} {v:,.0f}"
    return f"{CURRENCY} {v:,.1f}"


def display_name(s):
    """Capitalise the first letter of each word without touching '200ml' etc."""
    return " ".join(w[:1].upper() + w[1:] for w in str(s or "").split())


def short(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1].rstrip() + "\u2026"


def parse_promotion(details, current):
    """Parse 'Was KES 164.00 (12.2% Off)' -> {original, saved, pct}."""
    out = {"original": None, "saved": 0.0, "pct": None}
    if not details:
        return out
    m = re.search(r"Was\s*(?:KES|KSh)?\s*([\d,]+\.?\d*)", details, re.IGNORECASE)
    p = re.search(r"\(?\s*([\d.]+)\s*%\s*Off", details, re.IGNORECASE)
    original = parse_amount(m.group(1)) if m else None
    pct = float(p.group(1)) if p else None
    if original and original > 0:
        if current and 0 < current < original:
            saved = original - current
        elif pct:
            saved = original * pct / 100
        else:
            saved = 0.0
        out["original"] = original
        out["saved"] = saved
        out["pct"] = int(round(saved / original * 100)) if saved else None
    elif pct:
        out["pct"] = int(round(pct))
    return out


# ---------------------------------------------------------------------------
# Store registry (codes, colours, consistent ordering)
# ---------------------------------------------------------------------------

def chain_of(name):
    return (str(name or "").split(" - ")[0].strip()) or "Store"


def chain_key(name):
    return chain_of(name).lower()


def store_code(chain):
    k = chain.lower()
    if k in _KNOWN_CODES:
        return _KNOWN_CODES[k]
    words = re.findall(r"[A-Za-z0-9]+", chain)
    if len(words) >= 2:
        return "".join(w[0] for w in words[:3]).upper()
    return (words[0][:3] if words else "STR").upper()


class StoreRegistry:
    def __init__(self, store_names):
        firsts, seen = [], set()
        for n in store_names:
            k = chain_key(n)
            if k not in seen:
                seen.add(k)
                firsts.append(n)
        theme_idx, used = {}, set()
        for n in firsts:
            k = chain_key(n)
            if k in _PREFERRED_THEME:
                theme_idx[k] = _PREFERRED_THEME[k]
                used.add(_PREFERRED_THEME[k])
        nxt = 0
        for n in firsts:
            k = chain_key(n)
            if k in theme_idx:
                continue
            while nxt in used and len(used) < len(STORE_THEMES):
                nxt += 1
            idx = nxt % len(STORE_THEMES)
            used.add(idx)
            theme_idx[k] = idx
            nxt += 1
        ordered = sorted(
            enumerate(firsts),
            key=lambda t: (_PREFERRED_THEME.get(chain_key(t[1]), 99), t[0]),
        )
        self._info, self._rank, self.chains = {}, {}, []
        for r, (_, n) in enumerate(ordered):
            k = chain_key(n)
            info = dict(name=chain_of(n), code=store_code(chain_of(n)), theme=STORE_THEMES[theme_idx[k]])
            self._info[k] = info
            self._rank[k] = r
            self.chains.append(info)

    def info(self, store_name):
        k = chain_key(store_name)
        if k not in self._info:
            return dict(name=chain_of(store_name), code=store_code(chain_of(store_name)), theme=STORE_THEMES[3])
        return self._info[k]

    def rank(self, store_name):
        return self._rank.get(chain_key(store_name), 99)


# ---------------------------------------------------------------------------
# Drawing primitives (all coordinates in logical px)
# ---------------------------------------------------------------------------

class Painter:
    def __init__(self, img, pad=0):
        self.img = img
        self.d = ImageDraw.Draw(img)
        self.o = u(pad)

    def _v(self, v):
        return u(v) + self.o

    def rrect(self, x0, y0, x1, y1, r, fill=None, outline=None, width=0):
        self.d.rounded_rectangle(
            [self._v(x0), self._v(y0), self._v(x1) - 1, self._v(y1) - 1],
            radius=u(r), fill=fill, outline=outline,
            width=max(u(width), 1) if outline else 0,
        )

    def ellipse(self, x0, y0, x1, y1, fill):
        self.d.ellipse([self._v(x0), self._v(y0), self._v(x1) - 1, self._v(y1) - 1], fill=fill)

    def line(self, pts, fill, width=1):
        self.d.line([(self._v(x), self._v(y)) for x, y in pts], fill=fill,
                    width=max(u(width), 1), joint="curve")

    def polygon(self, pts, fill):
        self.d.polygon([(self._v(x), self._v(y)) for x, y in pts], fill=fill)

    def text(self, x, y, s, f, fill, anchor="lm"):
        self.d.text((self._v(x), self._v(y)), str(s), font=f, fill=fill, anchor=anchor)


class Block:
    """A rendered chunk of the page. `left`/`h` are the visible logical box."""
    def __init__(self, img, pad, left, h):
        self.img, self.pad, self.left, self.h = img, pad, left, h


def new_card(inner_h, *, w=CARD_W, radius=16, fill=WHITE, border=None, border_w=1.5, shadow=None):
    pad = SHADOW_PAD
    size = (u(w + 2 * pad), u(inner_h + 2 * pad))
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    if shadow:
        color, alpha, dy, blur = shadow
        layer = Image.new("RGBA", size, tuple(color) + (0,))
        ImageDraw.Draw(layer).rounded_rectangle(
            [u(pad), u(pad + dy), u(pad + w) - 1, u(pad + inner_h + dy) - 1],
            radius=u(radius), fill=tuple(color) + (int(255 * alpha),),
        )
        layer = layer.filter(ImageFilter.GaussianBlur(u(blur)))
        img = Image.alpha_composite(img, layer)
    p = Painter(img, pad)
    p.rrect(0, 0, w, inner_h, radius, fill=fill, outline=border, width=border_w)
    return Block(img, pad, MARGIN, inner_h), p


def icon_arrow_down(p, cx, cy, color):
    p.line([(cx, cy - 5), (cx, cy + 3)], color, 1.6)
    p.polygon([(cx - 4, cy + 0.5), (cx + 4, cy + 0.5), (cx, cy + 5)], color)


def icon_star(p, cx, cy, color, R=6.0, r=2.6):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    p.polygon(pts, color)


def icon_box(p, cx, cy, color):
    p.rrect(cx - 5, cy - 5, cx + 5, cy + 5, 2, outline=color, width=1.5)
    p.line([(cx - 5, cy - 1), (cx + 5, cy - 1)], color, 1.5)


def icon_check(p, cx, cy, color, s=1.0):
    p.line([(cx - 3.5 * s, cy + 0.2 * s), (cx - 1 * s, cy + 3 * s), (cx + 3.7 * s, cy - 2.8 * s)], color, 1.7)


def icon_bars(p, x, cy, color):
    for i, h in enumerate((5, 9, 13)):
        bx = x + i * 5
        p.rrect(bx, cy + 6.5 - h, bx + 3, cy + 6.5, 1, fill=color)


# ---------------------------------------------------------------------------
# Chips
# ---------------------------------------------------------------------------

CHIP_H = 22


def _chip_font(bold):
    return font("label_bold" if bold else "label_semi", 10.5)


def chip(segs, bg, fg, code=None, code_bg=None):
    if isinstance(segs, str):
        segs = [(segs, False)]
    return dict(segs=segs, bg=bg, fg=fg, code=code, code_bg=code_bg)


def chip_width(ch):
    w = 16
    if ch["code"]:
        w += tw(ch["code"], font("label_bold", 8.5)) + 8 + 5
    return w + sum(tw(s, _chip_font(b)) for s, b in ch["segs"])


def draw_chip(p, x, y, ch):
    w = chip_width(ch)
    p.rrect(x, y, x + w, y + CHIP_H, CHIP_H / 2, fill=ch["bg"])
    cx = x + 8
    if ch["code"]:
        cf = font("label_bold", 8.5)
        cw = tw(ch["code"], cf) + 8
        p.rrect(cx, y + 4, cx + cw, y + CHIP_H - 4, 4, fill=ch["code_bg"])
        p.text(cx + cw / 2, y + CHIP_H / 2, ch["code"], cf, WHITE, "mm")
        cx += cw + 5
    for s, b in ch["segs"]:
        f = _chip_font(b)
        p.text(cx, y + CHIP_H / 2, s, f, ch["fg"])
        cx += tw(s, f)


def flow(chips, max_w, gap=6):
    pos, x, y = [], 0, 0
    for ch in chips:
        w = chip_width(ch)
        if x > 0 and x + w > max_w:
            x, y = 0, y + CHIP_H + gap
        pos.append((x, y))
        x += w + gap
    return pos, ((y + CHIP_H) if chips else 0)


def legend_chips(reg):
    return [chip(i["name"], i["theme"]["pill_bg"], i["theme"]["pill_fg"],
                 code=i["code"], code_bg=i["theme"]["accent"]) for i in reg.chains]


# ---------------------------------------------------------------------------
# Page-level blocks
# ---------------------------------------------------------------------------

def build_topbar(chip_text):
    h = 36
    img = Image.new("RGBA", (u(LOGICAL_W), u(h)), (0, 0, 0, 0))
    p = Painter(img, 0)
    p.rrect(MARGIN, 4, MARGIN + 28, 32, 8, fill=PRIMARY_CONT)
    p.text(MARGIN + 14, 18, BRAND_NAME[:1].upper(), font("label_bold", 16), WHITE, "mm")
    p.text(MARGIN + 36, 18, BRAND_NAME, font("label_bold", 18), PRIMARY)
    if chip_text:
        ch = chip(ellipsize(chip_text, _chip_font(False), 170), SURFACE_HIGH, ON_SURFACE_VAR)
        draw_chip(p, LOGICAL_W - MARGIN - chip_width(ch), 7, ch)
    return Block(img, 0, 0, h)


def build_footer(text):
    h = 28
    img = Image.new("RGBA", (u(LOGICAL_W), u(h)), (0, 0, 0, 0))
    p = Painter(img, 0)
    f = font("body", 12)
    total = 16 + 6 + tw(text, f)
    x = (LOGICAL_W - total) / 2
    p.ellipse(x, h / 2 - 8, x + 16, h / 2 + 8, fill=SECONDARY)
    icon_check(p, x + 8, h / 2, WHITE, 0.95)
    p.text(x + 22, h / 2, text, f, ON_SURFACE_VAR)
    return Block(img, 0, 0, h)


def build_message_card(text):
    pad = 16
    f = font("body", 13)
    lines = wrap_lines(text, f, CARD_W - 2 * pad, 4)
    block, p = new_card(2 * pad + len(lines) * 18, shadow=SHADOW_SM)
    for i, l in enumerate(lines):
        p.text(pad, pad + 9 + i * 18, l, f, ON_SURFACE_VAR)
    return block


def build_header_card(title, subtitle, badges, legend):
    pad = 12
    inner = CARD_W - 2 * pad
    tf = font("body_bold", 22)
    sf = font("label_bold", 9.5)
    status_w = 16 + 6 + 4 + tw(STATUS_LABEL, sf)
    lines = wrap_lines(title, tf, inner - status_w - 8, 2)

    y = pad
    title_y = y
    y += 28 * len(lines) + 2
    sub_y = y
    y += 16
    b_pos, b_h = flow(badges, inner)
    b_y = l_y = 0
    if badges:
        y += 8
        b_y = y
        y += b_h
    l_pos, l_h = flow(legend, inner)
    if legend:
        y += 8
        l_y = y
        y += l_h
    block, p = new_card(y + pad, shadow=SHADOW_SM)

    for i, line in enumerate(lines):
        p.text(pad, title_y + 14 + i * 28, line, tf, ON_SURFACE)
    # status pill (top right, aligned with first title line)
    px1 = CARD_W - pad
    py = title_y + 14 - 10
    p.rrect(px1 - status_w, py, px1, py + 20, 10, fill=SECONDARY_FIXED)
    p.ellipse(px1 - status_w + 8, py + 7, px1 - status_w + 14, py + 13, fill=SECONDARY)
    p.text(px1 - status_w + 18, py + 10, STATUS_LABEL, sf, ON_SECONDARY_FIXED)

    p.text(pad, sub_y + 8, ellipsize(subtitle, font("body", 12), inner), font("body", 12), ON_SURFACE_VAR)
    for ch, (x, yy) in zip(badges, b_pos):
        draw_chip(p, pad + x, b_y + yy, ch)
    for ch, (x, yy) in zip(legend, l_pos):
        draw_chip(p, pad + x, l_y + yy, ch)
    return block


# ---------------------------------------------------------------------------
# Product card (brand card from the HTML): price grid per store
# ---------------------------------------------------------------------------

def make_cell(store_name, price_value, offer=False, promotion_details=None):
    price = price_value if (price_value and price_value > 0) else None
    promo = parse_promotion(promotion_details, price) if promotion_details else \
        {"original": None, "saved": 0.0, "pct": None}
    return dict(store=store_name or "Unknown", price=price, offer=bool(offer) and price is not None,
                original=promo["original"], saved=promo["saved"], pct=promo["pct"])


def _has_was(c):
    return bool(c["offer"] and c["original"] and c["price"] and c["original"] > c["price"])


def _tag_text(c, max_w):
    if not c["offer"]:
        return None
    if c["saved"] > 0:
        tf = font("label_bold", 8)
        options = []
        if c["pct"]:
            options.append(f"SAVE {CURRENCY} {c['saved']:,.0f} (-{c['pct']}%)")
        options += [f"SAVE {CURRENCY} {c['saved']:,.0f}", "SAVE"]
        for t in options:
            if tw(t, tf) + 10 <= max_w:
                return t
    return "OFFER"


def _cell_content_h(c, best):
    h = 12 + (24 if best else 20)
    if c["offer"]:
        h += 18
    if _has_was(c):
        h += 14
    return h


def _draw_cell(p, x, y, w, h, c, best, reg):
    info = reg.info(c["store"])
    if best:
        p.rrect(x, y, x + w, y + h, 8, fill=BEST_BG, outline=BEST_BORDER, width=1.5)
    else:
        p.rrect(x, y, x + w, y + h, 8, fill=WHITE, outline=OUTLINE_SOFT, width=1)
    cy = y + (h - _cell_content_h(c, best)) / 2

    tag = _tag_text(c, w - 8)
    if tag:
        tf = font("label_bold", 8)
        tg_w = tw(tag, tf) + 10
        p.rrect(x + (w - tg_w) / 2, cy, x + (w + tg_w) / 2, cy + 14, 4, fill=ERROR)
        p.text(x + w / 2, cy + 7, tag, tf, WHITE, "mm")
        cy += 18

    cf = font("label_bold", 9)
    code = info["code"]
    code_w = tw(code, cf)
    sx = x + (w - code_w - (9 if best else 0)) / 2
    p.text(sx, cy + 6, code, cf, BEST_TEXT if best else info["theme"]["accent"])
    if best:
        p.ellipse(sx + code_w + 3, cy + 3, sx + code_w + 9, cy + 9, fill=BEST_BORDER)
    cy += 12

    if c["price"] is None:
        txt, f, col = "N/A", font("label_semi", 13), ON_SURFACE_VAR
    else:
        txt = fmt_kes(c["price"])
        f = fit_font("label_bold" if best else "label_semi", 20 if best else 15, txt, w - 8, 11)
        col = BEST_TEXT if best else ON_SURFACE
    ph = 24 if best else 20
    p.text(x + w / 2, cy + ph / 2, txt, f, col, "mm")
    cy += ph

    if _has_was(c):
        wt, wf = f"{c['original']:,.0f}", font("body", 10)
        p.text(x + w / 2, cy + 7, wt, wf, ON_SURFACE_VAR, "mm")
        ww = tw(wt, wf)
        p.line([(x + w / 2 - ww / 2, cy + 7), (x + w / 2 + ww / 2, cy + 7)], ON_SURFACE_VAR, 1)


def build_product_card(card, reg):
    pad = 12
    inner = CARD_W - 2 * pad
    tile = 48
    tf, sf = font("body_semi", 16), font("body", 12)
    text_x = pad + tile + 10
    text_w = inner - tile - 10
    t_lines = wrap_lines(display_name(card["title"]), tf, text_w, 2)
    sub = ellipsize(card["subtitle"], sf, text_w)
    text_h = len(t_lines) * 20 + 2 + 16
    top_h = max(tile, text_h)

    grid_w = inner - 8
    layouts, total_rows_h = [], 0
    for row in card["rows"]:
        cells = sorted(row["cells"], key=lambda c: (reg.rank(c["store"]), c["store"]))
        if not cells:
            continue
        priced = [c["price"] for c in cells if c["price"]]
        best_val = min(priced) if len(priced) >= 2 and min(priced) < max(priced) else None
        cols = min(len(cells), 3)
        cw = (grid_w - 4 * (cols - 1)) / cols
        grid_rows = [cells[i:i + cols] for i in range(0, len(cells), cols)]
        row_hs = [max(_cell_content_h(c, best_val is not None and c["price"] == best_val) for c in gr) + 12
                  for gr in grid_rows]
        cont_h = 4 + 18 + 4 + sum(row_hs) + 4 * (len(row_hs) - 1) + 4
        best_cells = [c for c in cells if best_val is not None and c["price"] == best_val]
        layouts.append(dict(label=row["label"] or "Price by store", cells=cells, best_val=best_val,
                            cw=cw, grid_rows=grid_rows, row_hs=row_hs, cont_h=cont_h,
                            best_chain=chain_of(best_cells[0]["store"]) if len(best_cells) == 1 else None))
        total_rows_h += cont_h
    H = pad + top_h + (12 if layouts else 0) + total_rows_h + 8 * max(len(layouts) - 1, 0) + pad

    block, p = new_card(H, border=mix(WHITE, PRIMARY_CONT, 0.14), border_w=1.5, shadow=glow(PRIMARY_CONT))

    # identity row
    ty = pad + (top_h - tile) / 2
    p.rrect(pad, ty, pad + tile, ty + tile, 12, fill=SURFACE_LOW)
    initial = next((ch for ch in card["title"] if ch.isalnum()), "?").upper()
    p.text(pad + tile / 2, ty + tile / 2, initial, font("label_bold", 20), PRIMARY, "mm")
    y0 = pad + (top_h - text_h) / 2
    for i, line in enumerate(t_lines):
        p.text(text_x, y0 + 10 + i * 20, line, tf, ON_SURFACE)
    p.text(text_x, y0 + len(t_lines) * 20 + 2 + 8, sub, sf, ON_SURFACE_VAR)

    # per-size rows
    y = pad + top_h + 12
    for rl in layouts:
        p.rrect(pad, y, pad + inner, y + rl["cont_h"], 12, fill=ROW_BG)
        hy = y + 4 + 9
        p.text(pad + 8, hy, rl["label"], font("label_semi", 12), ON_SURFACE)
        if rl["best_chain"]:
            p.text(pad + inner - 8, hy, f"Best at {rl['best_chain']}", font("label_bold", 10), SECONDARY, "rm")
        gy = y + 4 + 18 + 4
        for gr, rh in zip(rl["grid_rows"], rl["row_hs"]):
            for i, c in enumerate(gr):
                best = rl["best_val"] is not None and c["price"] == rl["best_val"]
                _draw_cell(p, pad + 4 + i * (rl["cw"] + 4), gy, rl["cw"], rh, c, best, reg)
            gy += rh + 4
        y += rl["cont_h"] + 8
    return block


# ---------------------------------------------------------------------------
# Summary card
# ---------------------------------------------------------------------------

def _draw_rich(p, x, y, segs, max_w, size=12):
    fr, fb = font("body", size), font("body_bold", size)
    fo = lambda b: fb if b else fr
    total = sum(tw(s, fo(b)) for s, b in segs)
    if total > max_w:
        rest = total - tw(segs[0][0], fo(segs[0][1]))
        segs = [(ellipsize(segs[0][0], fo(segs[0][1]), max(max_w - rest, 40)), segs[0][1])] + list(segs[1:])
    cx = x
    for s, b in segs:
        p.text(cx, y, s, fo(b), ON_SURFACE if b else ON_SURFACE_VAR)
        cx += tw(s, fo(b))


def build_summary_card(cards, reg):
    entries = [(card, row, c) for card in cards for row in card["rows"] for c in row["cells"] if c["price"]]
    if len(entries) < 2:
        return None

    def name_of(card, row, n=24):
        label = f" {row['label']}" if row["label"] else ""
        return short(display_name(card["title"]), n) + label

    bullets = []
    card, row, c = min(entries, key=lambda e: e[2]["price"])
    bullets.append(("arrow", SECONDARY_CONT, "Lowest Price",
                    [(name_of(card, row), True), (" at ", False), (chain_of(c["store"]), False),
                     (" for ", False), (fmt_kes(c["price"]), True)]))
    discounts = [e for e in entries if e[2]["saved"] > 0]
    if discounts:
        card, row, c = max(discounts, key=lambda e: e[2]["saved"])
        bullets.append(("star", TERTIARY_FIXED, "Top Discount",
                        [(name_of(card, row), True), (" at ", False), (chain_of(c["store"]), False),
                         (" - Save ", False), (fmt_kes(c["saved"]), True), (f" (Pay {fmt_kes(c['price'])})", False)]))
    best_gap = None
    for card in cards:
        for row in card["rows"]:
            pc = [c for c in row["cells"] if c["price"]]
            if len(pc) >= 2:
                lo, hi = min(pc, key=lambda c: c["price"]), max(pc, key=lambda c: c["price"])
                gap = hi["price"] - lo["price"]
                if gap > 0 and (best_gap is None or gap > best_gap[0]):
                    best_gap = (gap, card, row, lo)
    if best_gap:
        gap, card, row, lo = best_gap
        bullets.append(("box", PRIMARY_FIXED, "Biggest Price Gap",
                        [(name_of(card, row), True), (" is ", False), (fmt_kes(gap), True),
                         (" cheaper at ", False), (chain_of(lo["store"]), False)]))

    prices = [e[2]["price"] for e in entries]
    show_range = min(prices) < max(prices)

    pad = 12
    inner = CARD_W - 2 * pad
    H = pad + 24 + 8 + len(bullets) * 40 + 4 * (len(bullets) - 1) + ((4 + 20) if show_range else 0) + pad
    block, p = new_card(H, fill=SUMMARY_BG, shadow=SHADOW_SM)

    icon_bars(p, pad, pad + 12 - 6.5, PRIMARY)
    p.text(pad + 24, pad + 12, "QUICK SHOPPING SUMMARY", font("label_bold", 11.5), PRIMARY)
    pf = font("label_bold", 9)
    pill_t = "SAVER HACKS"
    pw = tw(pill_t, pf) + 16
    p.rrect(pad + inner - pw, pad + 4, pad + inner, pad + 20, 8, fill=PRIMARY)
    p.text(pad + inner - pw / 2, pad + 12, pill_t, pf, WHITE, "mm")

    y = pad + 24 + 8
    icons = {"arrow": (icon_arrow_down, ON_SECONDARY_FIXED), "star": (icon_star, TERTIARY), "box": (icon_box, PRIMARY)}
    for kind, bg, title, segs in bullets:
        p.rrect(pad, y, pad + inner, y + 40, 12, fill=WHITE)
        cx, cy = pad + 4 + 12, y + 20
        p.ellipse(cx - 12, cy - 12, cx + 12, cy + 12, fill=bg)
        fn, col = icons[kind]
        fn(p, cx, cy, col)
        tx = pad + 4 + 24 + 8
        p.text(tx, y + 12, title, font("label_semi", 12), ON_SURFACE)
        _draw_rich(p, tx, y + 28, segs, inner - (tx - pad) - 6)
        y += 44
    if show_range:
        p.text(pad + 4, y + 10, "Price variation across stores:", font("body", 12), ON_SURFACE_VAR)
        rng = f"{fmt_kes(min(prices))} \u2013 {max(prices):,.0f}"
        p.text(pad + inner - 4, y + 10, rng, font("label_bold", 12), PRIMARY, "rm")
    return block


# ---------------------------------------------------------------------------
# Basket (shopping list) cards
# ---------------------------------------------------------------------------

def build_store_card(store, rank, n_total, reg):
    pad = 12
    inner = CARD_W - 2 * pad
    info = reg.info(store["name"])
    best = rank == 0
    name_f, sub_f = font("body_semi", 15), font("body", 11)
    total_txt = fmt_kes(store["total"]) if store["total"] > 0 else "N/A"
    tot_f = font("label_bold", 20)
    tot_w = tw(total_txt, tot_f)
    lines = wrap_lines(display_name(store["name"]), name_f, inner - 40 - 10 - max(tot_w, 72) - 8, 2)
    count = store.get("product_count")
    sub = f"{count}/{n_total} items found" if (count is not None and n_total) else None
    top_h = max(40, len(lines) * 18 + (15 if sub else 0), 24 + (22 if best else 0))

    name_w = inner - 16 - 96 - 8
    nf = font("body_semi", 12)
    rows = []
    for it in store["items"]:
        raw = it.get("price")
        pv = None if raw is None or str(raw).strip().upper() == "N/A" else (parse_amount(raw) or None)
        nl = wrap_lines(display_name(it.get("name", "Unknown")), nf, name_w, 2)
        offer = bool(it.get("offer")) and pv is not None
        promo = parse_promotion(it.get("promotion_details"), pv) if offer else None
        saved = promo["saved"] if promo else 0
        was = promo["original"] if (promo and promo["original"] and pv and promo["original"] > pv) else None
        tag = (f"SAVE {CURRENCY} {saved:,.0f}" if saved > 0 else "OFFER") if offer else None
        right_h = 18 + (18 if tag else 0) + (14 if was else 0)
        rows.append(dict(lines=nl, pv=pv, tag=tag, was=was, right_h=right_h,
                         h=max(len(nl) * 16, right_h) + 12))
    if not rows:
        rows = [dict(empty=True, h=32)]
    cont_h = sum(r["h"] for r in rows) + 4
    H = pad + top_h + 10 + cont_h + pad

    border = BEST_BORDER if best else mix(WHITE, PRIMARY_CONT, 0.14)
    block, p = new_card(H, border=border, border_w=1.5,
                        shadow=glow(BEST_BORDER if best else PRIMARY_CONT, 0.18 if best else 0.10))

    acc = info["theme"]["accent"]
    p.rrect(pad, pad, pad + 40, pad + 40, 10, fill=acc)
    p.text(pad + 20, pad + 20, info["code"], font("label_bold", 12), WHITE, "mm")
    ly = pad + (top_h - (len(lines) * 18 + (15 if sub else 0))) / 2
    for i, line in enumerate(lines):
        p.text(pad + 50, ly + 9 + i * 18, line, name_f, ON_SURFACE)
    if sub:
        p.text(pad + 50, ly + len(lines) * 18 + 7, sub, sub_f, ON_SURFACE_VAR)
    rx = pad + inner
    ry = pad + (top_h - (24 + (22 if best else 0))) / 2
    p.text(rx, ry + 12, total_txt, tot_f, BEST_TEXT if best else ON_SURFACE, "rm")
    if best:
        bf = font("label_bold", 9)
        bt = "BEST PRICE"
        bw = tw(bt, bf) + 14
        p.rrect(rx - bw, ry + 28, rx, ry + 44, 8, fill=BEST_BORDER)
        p.text(rx - bw / 2, ry + 36, bt, bf, WHITE, "mm")

    cy0 = pad + top_h + 10
    p.rrect(pad, cy0, pad + inner, cy0 + cont_h, 12, fill=ROW_BG)
    y = cy0 + 2
    xr = pad + inner - 8
    for i, r in enumerate(rows):
        if r.get("empty"):
            p.text(pad + 10, y + 16, "No products available", font("body", 12), ON_SURFACE_VAR)
        else:
            ny = y + (r["h"] - len(r["lines"]) * 16) / 2
            muted = r["pv"] is None
            for j, line in enumerate(r["lines"]):
                p.text(pad + 10, ny + 8 + j * 16, line, nf, ON_SURFACE_VAR if muted else ON_SURFACE)
            sy = y + (r["h"] - r["right_h"]) / 2
            if r["tag"]:
                tf = font("label_bold", 8)
                tgw = tw(r["tag"], tf) + 10
                p.rrect(xr - tgw, sy, xr, sy + 14, 4, fill=ERROR)
                p.text(xr - tgw / 2, sy + 7, r["tag"], tf, WHITE, "mm")
                sy += 18
            ptxt = fmt_kes(r["pv"])
            p.text(xr, sy + 9, ptxt, font("label_semi", 14), ON_SURFACE_VAR if muted else ON_SURFACE, "rm")
            sy += 18
            if r["was"]:
                wt, wf = f"{r['was']:,.0f}", font("body", 10)
                p.text(xr, sy + 7, wt, wf, ON_SURFACE_VAR, "rm")
                ww = tw(wt, wf)
                p.line([(xr - ww, sy + 7), (xr, sy + 7)], ON_SURFACE_VAR, 1)
        y += r["h"]
        if i < len(rows) - 1:
            p.line([(pad + 8, y), (pad + inner - 8, y)], mix(WHITE, OUTLINE_VAR, 0.5), 1)
    return block


def build_reco_card(recommendation, savings):
    pad = 12
    inner = CARD_W - 2 * pad
    rf, sf = font("body_semi", 13), font("label_semi", 12)
    r_lines = wrap_lines(recommendation or "Best combination found", rf, inner, 3)
    s_lines = wrap_lines(savings, sf, inner, 2) if savings else []
    H = pad + 24 + 6 + len(r_lines) * 18 + ((4 + len(s_lines) * 16) if s_lines else 0) + pad
    block, p = new_card(H, fill=SUMMARY_BG, shadow=SHADOW_SM)
    p.ellipse(pad, pad, pad + 24, pad + 24, fill=SECONDARY_CONT)
    icon_star(p, pad + 12, pad + 12, ON_SECONDARY_FIXED)
    p.text(pad + 32, pad + 12, "BEST BASKET", font("label_bold", 11.5), PRIMARY)
    y = pad + 24 + 6
    for i, l in enumerate(r_lines):
        p.text(pad, y + 9 + i * 18, l, rf, ON_SURFACE)
    y += len(r_lines) * 18 + 4
    for i, l in enumerate(s_lines):
        p.text(pad, y + 8 + i * 16, l, sf, SECONDARY)
    return block


# ---------------------------------------------------------------------------
# Assembly / output
# ---------------------------------------------------------------------------

def assemble(blocks, label):
    top, bottom = 12, 16
    total = top + sum(b.h for b in blocks) + GAP * (len(blocks) - 1) + bottom
    canvas = Image.new("RGB", (u(LOGICAL_W), u(total)), SURFACE)
    y = top
    for b in blocks:
        canvas.paste(b.img, (u(b.left) - u(b.pad), u(y) - u(b.pad)), b.img)
        y += b.h + GAP
    out_w = LOGICAL_W * OUT_SCALE
    out_h = int(round(total * OUT_SCALE))
    if out_w + out_h > MAX_SIDE_SUM:          # keep Telegram happy on very long baskets
        k = MAX_SIDE_SUM / (out_w + out_h)
        out_w, out_h = int(out_w * k), int(out_h * k)
    return _finalize_image(canvas.resize((out_w, out_h), Image.LANCZOS), label)


def _finalize_image(img: Image.Image, label: str) -> bytes:
    """Encode to PNG with palette reduction + optimization, log final size."""
    quantized = img.convert("P", palette=Image.ADAPTIVE, colors=256)
    buf = BytesIO()
    quantized.save(buf, format="PNG", optimize=True)
    result = buf.getvalue()
    logger.info(f"Generated {label} image: {len(result) / 1024:.1f} KB ({img.width}x{img.height})")
    return result


# ---------------------------------------------------------------------------
# Data -> cards
# ---------------------------------------------------------------------------

def _cells_from_stores(stores):
    return [make_cell(s.get("name"), parse_amount(s.get("price", 0)), s.get("offer"), s.get("promotion_details"))
            for s in stores or []]


def _options_to_cards(options):
    cards = []
    for opt in options:
        if opt.get("sizes"):
            rows = [dict(label=sz.get("label", ""), cells=_cells_from_stores(sz.get("stores")))
                    for sz in opt["sizes"]]
        elif opt.get("stores"):
            rows = [dict(label=opt.get("size", ""), cells=_cells_from_stores(opt["stores"]))]
        else:
            price = opt.get("price_value") or parse_amount(opt.get("price_label", 0))
            rows = [dict(label=opt.get("size", ""),
                         cells=[make_cell(opt.get("store_name"), price, opt.get("offer"), opt.get("promotion_details"))])]
        rows = [r for r in rows if r["cells"]]
        n_stores = len({chain_key(c["store"]) for r in rows for c in r["cells"] if c["price"]})
        subtitle = opt.get("subtitle") or (f"{n_stores} store{'s' if n_stores != 1 else ''} compared" if n_stores else "No price data")
        cards.append(dict(title=opt.get("brand") or opt.get("name", "Unknown"), subtitle=subtitle, rows=rows))

    def min_price(card):
        ps = [c["price"] for r in card["rows"] for c in r["cells"] if c["price"]]
        return min(ps) if ps else float("inf")

    return sorted(cards, key=min_price)


def _page_title(query):
    q = (query or "").strip()
    return f"{display_name(q)} Price Comparison" if (q and len(q) <= 16) else "Price Comparison"


def _render_comparison_page(cards, *, query, date_str, location, eyebrow, empty_text, label):
    reg = StoreRegistry([c["store"] for card in cards for row in card["rows"] for c in row["cells"]])
    n_cards, n_stores = len(cards), len(reg.chains)
    subtitle = f"{n_cards} product{'s' if n_cards != 1 else ''} \u2022 {n_stores} store{'s' if n_stores != 1 else ''}"
    badges = []
    if query:
        badges.append(chip([("Query: ", False), (ellipsize(f'"{query}"', _chip_font(True), 230), True)],
                           PRIMARY_FIXED, ON_PRIMARY_FIXED))
    badges.append(chip(f"Verified {date_str}", SURFACE_HIGH, ON_SURFACE_VAR))
    if location:
        badges.append(chip(location, SURFACE_CONT, ON_SURFACE_VAR))

    blocks = [build_topbar(eyebrow),
              build_header_card(_page_title(query), subtitle, badges, legend_chips(reg))]
    if cards:
        blocks += [build_product_card(c, reg) for c in cards]
        summary = build_summary_card(cards, reg)
        if summary:
            blocks.append(summary)
    else:
        blocks.append(build_message_card(empty_text))
    blocks.append(build_footer(FOOTER_NOTE))
    return assemble(blocks, label)


# ---------------------------------------------------------------------------
# Public generators
# ---------------------------------------------------------------------------

def generate_product_options_image(data: dict) -> bytes:
    """
    data keys: query_text, options (list of {name, price_label, price_value,
    store_name, offer, promotion_details?}), date

    Optional per-option keys that unlock the richer layout:
      stores:  [{name, price, offer, promotion_details?}]  -> one price cell per store
      sizes:   [{label, stores:[...]}]                      -> one row per size (like the HTML)
      brand, subtitle, size                                 -> card title / subtitle / row label
    """
    return _render_comparison_page(
        _options_to_cards(data.get("options", [])),
        query=data.get("query_text", ""),
        date_str=data.get("date", datetime.now().strftime("%Y-%m-%d")),
        location=data.get("location"),
        eyebrow="PRODUCT OPTIONS",
        empty_text="No matching products found.",
        label="product_options",
    )


def generate_single_product_image(data: dict) -> bytes:
    """data keys: product_name, stores (list of {name, price, offer}), date, location (optional)"""
    name = data.get("product_name", "Unknown Product")
    cells = _cells_from_stores(data.get("stores", []))
    cards = [dict(title=name, subtitle=f"{len(cells)} store{'s' if len(cells) != 1 else ''} compared",
                  rows=[dict(label="", cells=cells)])] if cells else []
    return _render_comparison_page(
        cards,
        query=name,
        date_str=data.get("date", datetime.now().strftime("%Y-%m-%d")),
        location=data.get("location"),
        eyebrow="SINGLE PRODUCT",
        empty_text="No price data available yet.",
        label="single_product",
    )


def generate_shopping_list_image(data: dict) -> bytes:
    """
    data keys: stores (list of {name, total, items, product_count?}), recommendation,
    savings, date, item_count
    """
    date_str = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    item_count = data.get("item_count")
    stores = [dict(name=s.get("name", "Unknown"), total=parse_amount(s.get("total", 0)),
                   items=s.get("items") or [], product_count=s.get("product_count"))
              for s in data.get("stores", [])]
    n_total = item_count or max((len(s["items"]) for s in stores), default=0)
    reg = StoreRegistry([s["name"] for s in stores])

    if stores:
        n = len(stores)
        subtitle = (f"{item_count} item{'s' if item_count != 1 else ''} \u2022 " if item_count else "") + \
                   f"{n} store{'s' if n != 1 else ''} compared"
    else:
        subtitle = "Basket comparison"
    badges = [chip(f"Verified {date_str}", SURFACE_HIGH, ON_SURFACE_VAR)]
    if item_count:
        badges.append(chip([(str(item_count), True), (" items", False)], PRIMARY_FIXED, ON_PRIMARY_FIXED))

    blocks = [build_topbar("SHOPPING LIST"),
              build_header_card("Basket Comparison", subtitle, badges, legend_chips(reg))]
    blocks += [build_store_card(s, i, n_total, reg) for i, s in enumerate(stores)]
    recommendation, savings = data.get("recommendation", ""), data.get("savings", "")
    if recommendation or savings:
        blocks.append(build_reco_card(recommendation, savings))
    elif not stores:
        blocks.append(build_message_card("No basket data available yet."))
    blocks.append(build_footer(FOOTER_NOTE))
    return assemble(blocks, "shopping_list")