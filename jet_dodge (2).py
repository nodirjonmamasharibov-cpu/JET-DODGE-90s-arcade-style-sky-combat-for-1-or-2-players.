"""
JET DODGE  — 90s arcade-style sky combat for 1 or 2 players.

MODES
    1 PLAYER        Classic: wave through enemies, 1 life
    2 PLAYERS       Co-op or Versus: pick mode at start
    ARCADE CABINET  3 lives, respawn when boss dies, high score chase
    TUTORIAL        Optional: learn the controls (once, then optional)

1-PLAYER / 2-PLAYER
    Arrow keys      fly (solo) / Player 2
    Right Ctrl      fire gun (hold)
    Right Shift     dodge roll
    /               fire homing missile
    
    WASD            fly (Player 1 only in 2P)
    Left Ctrl       fire gun
    Left Shift      roll
    E               missile

ARCADE CABINET (3 lives mode)
    Same controls as 1P, but 3 lives. Get a fresh life every time you defeat a boss.
    Respawn at your last position when a life is lost.

PAUSE    P
QUIT     Esc during play

Setup
    pip install pygame
    python jet_dodge.py

High scores, colour preferences, and tutorial status are saved in jet_dodge_data.json.
"""

# ---------------------------------------------------------------------------
# Standard library + pygame
# ---------------------------------------------------------------------------
import array, json, math, random
from enum import Enum, auto
from pathlib import Path

import pygame

# ---------------------------------------------------------------------------
# Window / timing
# ---------------------------------------------------------------------------
W = 900
H = 650
FPS = 60

# ---------------------------------------------------------------------------
# Palette — every colour in the game lives here
# ---------------------------------------------------------------------------
BLACK       = (0,   0,   0)
DARK_BG     = (8,   6,  18)
GRID_LINE   = (22,  18,  44)
STAR_BRIGHT = (255, 255, 255)
STAR_DIM    = (140, 140, 160)

SKY_DAY_TOP    = (38, 90, 160)
SKY_DAY_BOT    = (130, 190, 230)
SKY_NIGHT_TOP  = (6,   8,  28)
SKY_NIGHT_BOT  = (22,  30,  70)
CLOUD_WHITE    = (255, 255, 255)

YELLOW      = (255, 220,  40)
ORANGE      = (255, 140,  20)
RED         = (230,  40,  40)
CYAN        = ( 60, 220, 220)
GREEN       = ( 60, 230, 100)
MAGENTA     = (255,  60, 200)
WHITE       = (255, 255, 255)
GREY        = (130, 130, 150)
DARK_GREY   = ( 40,  40,  60)

PANEL_BG    = (10,   8,  28, 200)      # SRCALPHA
PANEL_EDGE  = (80,   60, 160, 220)
HUD_TEXT    = (220, 215, 255)
HUD_DIM     = (110, 105, 150)
WARNING_CLR = (255, 200,  30)
MISSILE_CLR = (200, 240, 255)
GLOW_CLR    = ( 90, 200, 255)
SMOKE_CLR   = ( 50,  50,  62)
FLASH_CLR   = (255, 176,  58)
TRAIL_CLR   = (210, 220, 240)
SHIELD_CLR  = (100, 200, 255)
PICKUP_BORDER = (255, 255, 255)
BOSS_CLR    = (255, 200,   0)
HEALTH_BAR_BG = (80, 30, 30)
HEALTH_BAR_FG = (255, 80, 80)

# --- selectable jet colours (name: (body, canopy, glow)) ---
JET_COLOUR_OPTIONS = {
    "AZURE":   ((38,  62, 112), (190, 225, 255), ( 80, 160, 255)),
    "CRIMSON": ((140,  20,  20), (255, 180, 180), (255,  80,  80)),
    "JADE":    ((20, 100,  50), (160, 255, 200), ( 60, 240, 130)),
    "VIOLET":  ((80,  20, 140), (220, 160, 255), (180,  80, 255)),
    "GOLD":    ((120, 90,   0), (255, 230, 120), (255, 200,  40)),
    "SILVER":  ((80,  80,  90), (220, 225, 240), (200, 210, 230)),
    "EMBER":   ((150,  60,  10), (255, 200, 150), (255, 140,  40)),
    "TEAL":    ((10,  90, 100), (140, 240, 240), ( 40, 210, 210)),
}
JET_COLOUR_NAMES = list(JET_COLOUR_OPTIONS.keys())

# --- enemy colour sets per kind ---
ENEMY_COLOURS = {
    "fighter":  {"body": (190, 30, 30),  "canopy": (255, 180, 180)},
    "scout":    {"body": (200, 110, 20), "canopy": (255, 220, 160)},
    "bomber":   {"body": (100, 15, 25),  "canopy": (220, 170, 175)},
    "kamikaze": {"body": (230, 40, 100), "canopy": (255, 190, 210)},
}

# ---------------------------------------------------------------------------
# Jet shape (shared by all pilots, scaled per role)
# ---------------------------------------------------------------------------
JET_W = 44
JET_H = 48

_RIGHT_HALF = [
    (0.50, 0.00), (0.57, 0.24), (0.60, 0.45),
    (1.00, 0.75), (1.00, 0.82), (0.60, 0.72),
    (0.56, 0.86), (0.78, 0.97), (0.78, 1.00), (0.52, 0.94),
]
JET_SHAPE = _RIGHT_HALF + [(1-x, y) for x, y in reversed(_RIGHT_HALF[1:])]


def _jet_points(rect, nose_up):
    pts = []
    for fx, fy in JET_SHAPE:
        if not nose_up:
            fy = 1 - fy
        pts.append((rect.x + fx * rect.width, rect.y + fy * rect.height))
    return pts


def draw_jet(surface, rect, body, canopy, nose_up=True, flash=False, alpha=255):
    """Draw a jet silhouette with an optional hit-flash and opacity."""
    col = (255, 255, 255) if flash else body
    if alpha < 255:
        tmp = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pts_local = [( p[0]-rect.x, p[1]-rect.y) for p in _jet_points(rect, nose_up)]
        pygame.draw.polygon(tmp, (*col, alpha), pts_local)
        cy_frac = 0.36 if nose_up else 0.64
        pygame.draw.circle(tmp, (*canopy, alpha),
                           (rect.width//2, round(rect.height*cy_frac)),
                           max(2, rect.width//9))
        surface.blit(tmp, rect.topleft)
    else:
        pygame.draw.polygon(surface, col, _jet_points(rect, nose_up))
        cy = rect.y + rect.height * (0.36 if nose_up else 0.64)
        pygame.draw.circle(surface, canopy if not flash else WHITE,
                           (rect.centerx, round(cy)), max(2, rect.width//9))

# ---------------------------------------------------------------------------
# Game settings
# ---------------------------------------------------------------------------
PLAYER_SPEED    = 5
SPEED_BOOST     = 1.65

ROLL_SPEED      = 16
ROLL_DUR        = 0.18
ROLL_CD         = 2.4

MISSILE_MAX     = 3
MISSILE_RECH    = 7.0
MISSILE_SPEED   = 7.5
MISSILE_TURN    = 7.0

SHIELD_RECH     = 9.0

GUN_DELAY       = 0.22
RAPID_DELAY     = 0.09
BULLET_SPEED    = 9
BULLET_SIZE     = 8
TRACER_F        = 3

TRAIL_INTERVAL  = 0.035
TRAIL_LIFE      = 0.35

ENEMY_FIRE_MIN  = 1.5
ENEMY_FIRE_MAX  = 3.0
ENEMY_BSPEED    = 4.5
BOMBER_SPREAD   = 16        # degrees each side
HITBOX_SHRINK   = 12

KAMIKAZE_RANGE  = 260
KAMIKAZE_SPEED  = 6.5
SCOUT_REDIR_MIN = 0.25
SCOUT_REDIR_MAX = 0.6
HIT_FLASH_DUR   = 0.08

SAFE_ZONE       = 150
WARN_LEAD       = 0.55

WAVE_BASE       = 3
WAVE_MAX        = 8
WAVE_BREAK      = 2.2

PPS             = 10        # points per second alive
KILL_PTS = {"fighter":50, "scout":60, "bomber":90, "kamikaze":70}

SPEED_RAMP_SCALE  = 4000
SPEED_RAMP_CAP    = 1.6
FIRE_RAMP_SCALE   = 3000
FIRE_RAMP_CAP     = 1.8

PICKUP_SIZE       = 26
PICKUP_FALL       = 70
PICKUP_SPAWN_MIN  = 7.0
PICKUP_SPAWN_MAX  = 12.0
BUFF_DUR          = 6.0

SMOKE_LIFE        = 1.2
SMOKE_PUFFS       = 14
SMOKE_CANVAS      = 220
CRASH_PAUSE       = 0.9

SHAKE_HIT_MAG     = 4
SHAKE_HIT_DUR     = 0.12
SHAKE_DEATH_MAG   = 11
SHAKE_DEATH_DUR   = 0.3

CLOUD_CNT         = 7
CLOUD_SPEED       = 18
CLOUD_PUFFS       = 7
CLOUD_BACK_CNT    = 5
CLOUD_BACK_SCALE  = 0.45

NIGHT_THRESHOLD   = 600
NIGHT_BLEND_SPD   = 0.25

RADAR_W, RADAR_H  = 120, 88

DATA_FILE = Path(__file__).resolve().parent / "jet_dodge_data.json"
MAX_HS    = 5

DIFFICULTIES = {
    "ROOKIE":   {"speed": 0.80, "fire": 0.70, "growth": 0.6},
    "ACE":      {"speed": 1.00, "fire": 1.00, "growth": 1.0},
    "TOP GUN":  {"speed": 1.25, "fire": 1.40, "growth": 1.4},
}
DIFF_NAMES = list(DIFFICULTIES.keys())

PICKUP_KINDS = {
    "SPEED":  {"color": (80, 200, 255),  "label": "S"},
    "RAPID":  {"color": (255, 210,  60), "label": "R"},
    "SHIELD": {"color": (120, 255, 170), "label": "+"},
}

ENEMY_KINDS = {
    "fighter":  {"hp":1, "vmin":3, "vmax":6,   "scale":1.00, "shoots":True,  "bullets":1},
    "scout":    {"hp":1, "vmin":6, "vmax":9,   "scale":0.85, "shoots":False, "bullets":0},
    "bomber":   {"hp":2, "vmin":1.2,"vmax":2.2,"scale":1.35, "shoots":True,  "bullets":3},
    "kamikaze": {"hp":1, "vmin":3, "vmax":5,   "scale":0.95, "shoots":False, "bullets":0},
}

# Boss settings
BOSS_WAVE_INTERVAL = 5
BOSS_HP            = 10
BOSS_SCALE         = 1.8
BOSS_SPEED         = 2.5
BOSS_FIRE_RATE     = 0.7
BOSS_BULLET_SPEED  = 5.5

class GS(Enum):
    MENU = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()

# ---------------------------------------------------------------------------
# Persistent data (high scores + colour prefs + tutorial)
# ---------------------------------------------------------------------------
def load_data():
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
        d.setdefault("hs_1p", [])
        d.setdefault("hs_2p", [])
        d.setdefault("hs_arcade", [])
        d.setdefault("p1_colour", "AZURE")
        d.setdefault("p2_colour", "CRIMSON")
        d.setdefault("tutorial_done", False)
        d["hs_1p"] = sorted((int(s) for s in d["hs_1p"]), reverse=True)[:MAX_HS]
        d["hs_2p"] = sorted((int(s) for s in d["hs_2p"]), reverse=True)[:MAX_HS]
        d["hs_arcade"] = sorted((int(s) for s in d["hs_arcade"]), reverse=True)[:MAX_HS]
        if d["p1_colour"] not in JET_COLOUR_OPTIONS:
            d["p1_colour"] = "AZURE"
        if d["p2_colour"] not in JET_COLOUR_OPTIONS:
            d["p2_colour"] = "CRIMSON"
        return d
    except Exception:
        return {"hs_1p":[], "hs_2p":[], "hs_arcade":[], "p1_colour":"AZURE", "p2_colour":"CRIMSON", "tutorial_done":False}

def save_data(d):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(d, f)
    except OSError:
        pass

def add_score(lst, score):
    return sorted(lst + [int(score)], reverse=True)[:MAX_HS]

# ---------------------------------------------------------------------------
# Sound (synthesized — no audio files needed)
# ---------------------------------------------------------------------------
SOUND_ON = False
_SFX = {}

def _make_buf(samples):
    data = array.array("h", samples)
    freq, _, ch = pygame.mixer.get_init()
    if ch >= 2:
        st = array.array("h")
        for s in data: st.append(s); st.append(s)
        data = st
    return pygame.mixer.Sound(buffer=data.tobytes())

def _square(hz, dur, vol=0.35):
    n = int(44100 * dur)
    amp = int(32767 * vol)
    return [amp if math.sin(2*math.pi*hz*(i/44100)) >= 0 else -amp for i in range(n)]

def _noise(dur, vol=0.45):
    n = int(44100 * dur)
    amp = int(32767 * vol)
    return [int(random.uniform(-amp, amp) * (1-i/n)**2) for i in range(n)]

def init_sound():
    global SOUND_ON
    try:
        pygame.mixer.init(44100, -16, 1)
        _SFX["gun"]  = _make_buf(_square(880,  0.05, 0.25))
        _SFX["boom"] = _make_buf(_noise(0.35,  0.50))
        _SFX["hum"]  = _make_buf(_square(85,   1.00, 0.04))
        _SFX["pick"] = _make_buf(_square(1200, 0.06, 0.20))
        _SFX["roll"] = _make_buf(_square(660,  0.10, 0.18))
        SOUND_ON = True
    except Exception:
        SOUND_ON = False

def sfx(name):
    if SOUND_ON and name in _SFX:
        _SFX[name].play()

def sfx_loop(name):
    if SOUND_ON and name in _SFX:
        _SFX[name].play(loops=-1)

def sfx_stop(name):
    if SOUND_ON and name in _SFX:
        _SFX[name].stop()

# ---------------------------------------------------------------------------
# CRT / arcade post-processing surfaces (built once)
# ---------------------------------------------------------------------------
def make_crt_layers():
    """Scanlines + corner vignette composited on top of every frame."""
    scanlines = pygame.Surface((W, H), pygame.SRCALPHA)
    for y in range(0, H, 2):
        pygame.draw.line(scanlines, (0,0,0,60), (0,y), (W,y))

    vignette = pygame.Surface((W, H), pygame.SRCALPHA)
    cx, cy = W//2, H//2
    for i in range(12, 0, -1):
        r  = int(max(W,H) * i / 12)
        al = int(70 * (1 - i/12))
        pygame.draw.ellipse(vignette, (0,0,0,al), (cx-r, cy-r//2, r*2, r))

    return scanlines, vignette

# ---------------------------------------------------------------------------
# Background: sky gradient, stars, clouds
# ---------------------------------------------------------------------------
def make_sky(top, bot):
    s = pygame.Surface((W, H))
    for y in range(H):
        t = y / H
        c = [int(a + (b-a)*t) for a,b in zip(top, bot)]
        pygame.draw.line(s, c, (0,y), (W,y))
    return s

def make_stars(n=80):
    return [(random.randint(0,W), random.randint(0,int(H*0.85)),
             random.choice([1,1,1,2]), random.uniform(0.4,1.0)) for _ in range(n)]

def draw_stars(surface, stars, alpha):
    if alpha <= 0:
        return
    for sx,sy,r,bright in stars:
        c = int(255*bright*alpha)
        pygame.draw.circle(surface, (c,c,min(255,c+30)), (sx,sy), r)

def make_cloud_img(scale, alpha):
    w = int(240*scale); h = int(110*scale); pad = int(42*scale)
    img = pygame.Surface((w,h), pygame.SRCALPHA)
    for i in range(CLOUD_PUFFS):
        across = (i+0.5)/CLOUD_PUFFS
        bulge  = 1 - abs(across-0.5)*1.5
        radius = int((15+26*bulge)*scale)
        x = int(pad + across*(w-2*pad))
        y = h//2 + int(random.uniform(-9,9)*scale)
        pygame.draw.circle(img, (*CLOUD_WHITE, alpha), (x,y), radius)
    return img

class Cloud:
    def __init__(self, x, y, scale, speed, alpha):
        self.img = make_cloud_img(scale, alpha)
        self.x=x; self.y=y; self.speed=speed
    def update(self, dt):
        self.y += self.speed*dt
        if self.y > H:
            self.y = -self.img.get_height()
            self.x = random.randint(-60, W-40)
    def draw(self, s): s.blit(self.img, (self.x, self.y))

def make_clouds(n, speed_scale=1.0, alpha_scale=1.0):
    out = []
    for _ in range(n):
        sc = random.uniform(0.6,1.4)
        out.append(Cloud(random.randint(-60,W-40), random.randint(-100,H),
                         sc, CLOUD_SPEED*sc*speed_scale,
                         int((95+75*sc)*alpha_scale)))
    return out

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def norm(v):
    """Return a unit Vector2; fall back to (0,1) to avoid divide-by-zero."""
    if v.length_squared() < 1e-9:
        return pygame.Vector2(0,1)
    return v.normalize()

def dir_to(src, dst):
    return norm(pygame.Vector2(dst) - pygame.Vector2(src))

def draw_glow_circle(surface, color, center, radius, alpha=160, layers=5):
    """Cheap additive-looking glow: several circles of decreasing alpha."""
    for i in range(layers,0,-1):
        r   = int(radius * i / layers)
        al  = int(alpha  * (1 - i/layers) + 20)
        tmp = pygame.Surface((r*2,r*2), pygame.SRCALPHA)
        pygame.draw.circle(tmp, (*color, al), (r,r), r)
        surface.blit(tmp, (center[0]-r, center[1]-r), special_flags=pygame.BLEND_RGBA_ADD)

# ---------------------------------------------------------------------------
# Arcade font helpers — 90s arcade vibes with Impact, Comic Sans, Arial Black
# ---------------------------------------------------------------------------
_font_cache = {}

def arcade_font(size, style="body"):
    """Get arcade-style font. Styles: 'title' (Impact), 'body' (Comic Sans), 'mono' (Courier)."""
    key = (size, style)
    if key not in _font_cache:
        if style == "title":
            # Big bold Impact for titles — that 90s arcade marquee feel
            _font_cache[key] = pygame.font.SysFont("impact,arial black", size, bold=True)
        elif style == "mono":
            # Fixed-width for HUD numbers that need to line up
            _font_cache[key] = pygame.font.SysFont("courier new,consolas,monospace", size, bold=True)
        else:  # "body" or default
            # Comic Sans for that unmistakable 90s arcade energy
            _font_cache[key] = pygame.font.SysFont("comic sans ms,arial,verdana", size, bold=True)
    return _font_cache[key]

def txt(surface, text, size, color, center=None, topleft=None, shadow=True, style="body"):
    """Render text with arcade fonts. style: 'title' (Impact), 'body' (Comic Sans), 'mono' (Courier)."""
    f   = arcade_font(size, style=style)
    img = f.render(str(text), True, color)
    if shadow:
        sh = f.render(str(text), True, BLACK)
        if center:
            r = img.get_rect(center=center)
            surface.blit(sh, r.move(2,2))
            surface.blit(img, r)
        else:
            surface.blit(sh, (topleft[0]+2, topleft[1]+2))
            surface.blit(img, topleft)
    else:
        if center:
            surface.blit(img, img.get_rect(center=center))
        else:
            surface.blit(img, topleft)
    return img.get_rect(center=center) if center else img.get_rect(topleft=topleft)

def draw_panel(surface, rect, title=None):
    """A semi-transparent dark panel with a coloured border."""
    pan = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pan.fill(PANEL_BG)
    pygame.draw.rect(pan, PANEL_EDGE, pan.get_rect(), width=2, border_radius=6)
    surface.blit(pan, rect.topleft)
    if title:
        txt(surface, title, 16, YELLOW, center=(rect.centerx, rect.top+14), style="body")

# ---------------------------------------------------------------------------
# Explosion (smoke + fireball)
# ---------------------------------------------------------------------------
class Explosion:
    def __init__(self, center, scale=1.0):
        self.x, self.y = center
        self.age = 0.0; self.scale = scale
        self.puffs = []
        for _ in range(SMOKE_PUFFS):
            a = random.uniform(0, 2*math.pi)
            d = random.uniform(0, 12)*scale
            self.puffs.append({
                "x": math.cos(a)*d, "y": math.sin(a)*d,
                "dx": math.cos(a)*random.uniform(14,40)*scale,
                "dy": math.sin(a)*random.uniform(14,40)*scale,
                "r":  random.uniform(13,25)*scale,
            })
    def update(self, dt): self.age += dt
    def done(self): return self.age >= SMOKE_LIFE
    def draw(self, surface):
        p  = min(self.age/SMOKE_LIFE, 1.0)
        cv = max(1, int(SMOKE_CANVAS*self.scale))
        L  = pygame.Surface((cv,cv), pygame.SRCALPHA)
        m  = cv//2
        for puff in self.puffs:
            x = m + puff["x"] + puff["dx"]*self.age
            y = m + puff["y"] + puff["dy"]*self.age
            r = puff["r"]*(0.55+1.15*p)
            a = int(215*(1-p))
            pygame.draw.circle(L, (*SMOKE_CLR, a), (x,y), r)
        if p < 0.3:
            ff = 1-p/0.3
            fr = (34-20*(p/0.3))*self.scale
            pygame.draw.circle(L, (*FLASH_CLR, int(240*ff)), (m,m), fr)
        surface.blit(L, (self.x-m, self.y-m))

# ---------------------------------------------------------------------------
# Pickup
# ---------------------------------------------------------------------------
class Pickup:
    def __init__(self, kind, x):
        self.kind=kind; self.x=float(x); self.y=float(-PICKUP_SIZE)
        self.rect=pygame.Rect(0,0,PICKUP_SIZE,PICKUP_SIZE)
        self.rect.center=(round(self.x),round(self.y))
        self.bob = random.uniform(0, 2*math.pi)  # phase for vertical bobbing

    def update(self, dt):
        self.y += PICKUP_FALL*dt
        self.bob += 2.0*dt
        self.rect.center = (round(self.x), round(self.y + math.sin(self.bob)*3))

    def off_screen(self): return self.y-PICKUP_SIZE > H

    def draw(self, surface):
        info = PICKUP_KINDS[self.kind]
        cx,cy = self.rect.center
        draw_glow_circle(surface, info["color"], (cx,cy), PICKUP_SIZE//2+4, alpha=80, layers=4)
        pygame.draw.circle(surface, info["color"], (cx,cy), PICKUP_SIZE//2)
        pygame.draw.circle(surface, PICKUP_BORDER, (cx,cy), PICKUP_SIZE//2, width=2)
        txt(surface, info["label"], 18, BLACK, center=(cx,cy), shadow=False)

    def apply(self, player):
        if self.kind=="SPEED":  player.speed_timer = BUFF_DUR
        elif self.kind=="RAPID": player.rapid_timer = BUFF_DUR
        elif self.kind=="SHIELD":
            player.shield = True; player.shield_timer = 0.0

# ---------------------------------------------------------------------------
# Projectiles
# ---------------------------------------------------------------------------
class Bullet:
    def __init__(self, start, direction, speed, color, thick=4):
        self.x,self.y = float(start[0]),float(start[1])
        self.vx = direction.x*speed; self.vy = direction.y*speed
        self.color=color; self.thick=thick
        self.rect=pygame.Rect(0,0,BULLET_SIZE,BULLET_SIZE)
        self.rect.center=(round(self.x),round(self.y))
    def update(self):
        self.x+=self.vx; self.y+=self.vy
        self.rect.center=(round(self.x),round(self.y))
    def on_screen(self): return -50<self.x<W+50 and -50<self.y<H+50
    def draw(self, surface):
        tail=(self.x-self.vx*TRACER_F, self.y-self.vy*TRACER_F)
        pygame.draw.line(surface, self.color,(self.x,self.y),tail,self.thick)

class Missile:
    def __init__(self, start, direction):
        self.x,self.y=float(start[0]),float(start[1])
        self.d = pygame.Vector2(direction)
        self.rect=pygame.Rect(0,0,BULLET_SIZE,BULLET_SIZE)
        self.rect.center=(round(self.x),round(self.y))
    def update(self, dt, targets):
        # targets is a list of rects to home toward
        if targets:
            nearest = min(targets, key=lambda r: pygame.Vector2(r.center).distance_squared_to((self.x,self.y)))
            desired = dir_to((self.x,self.y), nearest.center)
            self.d = norm(self.d + desired*MISSILE_TURN*dt)
        self.x+=self.d.x*MISSILE_SPEED; self.y+=self.d.y*MISSILE_SPEED
        self.rect.center=(round(self.x),round(self.y))
    def on_screen(self): return -50<self.x<W+50 and -50<self.y<H+50
    def draw(self, surface):
        tail=(self.x-self.d.x*16, self.y-self.d.y*16)
        pygame.draw.line(surface, GLOW_CLR,(self.x,self.y),tail,6)
        pygame.draw.line(surface, MISSILE_CLR,(self.x,self.y),tail,2)
        draw_glow_circle(surface, GLOW_CLR, (int(self.x),int(self.y)), 6, alpha=100, layers=3)

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------
class Player:
    """One human pilot.  `idx` 0=P1, 1=P2.  `controls` dict maps action->key."""

    ACTIONS = ("up","down","left","right","fire","roll","missile")

    P1_KEYS = {
        "up":     pygame.K_w,      "down":  pygame.K_s,
        "left":   pygame.K_a,      "right": pygame.K_d,
        "fire":   pygame.K_LCTRL, "roll":   pygame.K_LSHIFT,
        "missile":pygame.K_e,
    }
    P2_KEYS = {
        "up":     pygame.K_UP,     "down":  pygame.K_DOWN,
        "left":   pygame.K_LEFT,   "right": pygame.K_RIGHT,
        "fire":   pygame.K_RCTRL, "roll":   pygame.K_RSHIFT,
        "missile":pygame.K_SLASH,
    }
    # In 1-player mode the solo player uses P2's keys (arrows + right modifiers)
    SOLO_KEYS = P2_KEYS

    def __init__(self, idx, colour_name, two_player):
        self.idx   = idx
        self.set_colour(colour_name)
        self.keys  = (self.P1_KEYS if idx==0 else self.P2_KEYS) if two_player else self.SOLO_KEYS

        # Start positions: P1 left-centre, P2 right-centre; solo = middle
        if two_player:
            cx = W//4 if idx==0 else 3*W//4
        else:
            cx = W//2
        self.rect = pygame.Rect(0,0,JET_W,JET_H)
        self.rect.center=(cx, H*2//3)

        self.alive  = True
        self.score  = 0.0
        self.kills  = 0

        self.gun_cd     = 0.0
        self.roll_timer = 0.0
        self.roll_cd    = 0.0
        self.shield     = True
        self.shield_timer=0.0
        self.missile_ch = MISSILE_MAX
        self.missile_timer=0.0
        self.speed_timer= 0.0
        self.rapid_timer= 0.0

        self.trail      = []
        self._trail_t   = 0.0

        # Per-player shot lists (owned here, referenced by the round)
        self.p_shots  = []
        self.missiles = []
        self.e_shots  = []   # enemy shots aimed at THIS player

    def set_colour(self, name):
        self.colour_name = name
        info = JET_COLOUR_OPTIONS[name]
        self.body, self.canopy, self.glow = info

    # -- movement & input ------------------------------------------------
    def handle_input(self, keys_held, dt, events):
        if not self.alive:
            return

        sp = PLAYER_SPEED * (SPEED_BOOST if self.speed_timer>0 else 1)
        if self.roll_timer > 0:
            sp = ROLL_SPEED

        k = self.keys
        if keys_held[k["up"]]:    self.rect.y -= sp
        if keys_held[k["down"]]:  self.rect.y += sp
        if keys_held[k["left"]]:  self.rect.x -= sp
        if keys_held[k["right"]]: self.rect.x += sp
        self.rect.clamp_ip(pygame.Rect(0,0,W,H))
        self._update_trail(dt)

        # Gun (held key)
        if keys_held[k["fire"]]:
            self._try_shoot()

        # Roll / missile on KEYDOWN events to avoid repeat-fire weirdness
        for ev in events:
            if ev.type == pygame.KEYDOWN:
                if ev.key == k["roll"]:
                    self._start_roll()
                if ev.key == k["missile"]:
                    self._fire_missile()

    def _try_shoot(self):
        if self.gun_cd > 0: return
        self.gun_cd = RAPID_DELAY if self.rapid_timer>0 else GUN_DELAY
        b = Bullet(self.nose(), pygame.Vector2(0,-1), BULLET_SPEED, self.glow)
        self.p_shots.append(b)
        sfx("gun")

    def _start_roll(self):
        if self.roll_cd>0 or self.roll_timer>0: return
        self.roll_timer=ROLL_DUR; self.roll_cd=ROLL_CD
        sfx("roll")

    def _fire_missile(self):
        if self.missile_ch<1: return
        self.missile_ch -= 1
        self.missiles.append(Missile(self.nose(), pygame.Vector2(0,-1)))

    def nose(self):
        return (self.rect.centerx, self.rect.top)

    def hitbox(self):
        return self.rect.inflate(-HITBOX_SHRINK, -HITBOX_SHRINK)

    def invincible(self):
        return self.roll_timer > 0

    def absorb(self):
        """Consume shield. Returns True if it was up."""
        if not self.shield: return False
        self.shield=False; self.shield_timer=SHIELD_RECH
        return True

    # -- per-frame timers ------------------------------------------------
    def update_timers(self, dt):
        self.gun_cd   = max(0.0, self.gun_cd - dt)
        self.roll_timer=max(0.0, self.roll_timer - dt)
        self.roll_cd  = max(0.0, self.roll_cd  - dt)
        self.speed_timer=max(0.0, self.speed_timer-dt)
        self.rapid_timer=max(0.0, self.rapid_timer-dt)

        if self.missile_ch < MISSILE_MAX:
            self.missile_timer -= dt
            if self.missile_timer <= 0:
                self.missile_ch += 1
                self.missile_timer = MISSILE_RECH

        if not self.shield:
            self.shield_timer -= dt
            if self.shield_timer <= 0:
                self.shield = True

    def _update_trail(self, dt):
        self._trail_t -= dt
        if self._trail_t <= 0:
            self._trail_t = TRAIL_INTERVAL
            self.trail.append({"x":self.rect.centerx+random.uniform(-4,4),
                                "y":self.rect.bottom-4, "age":0.0})
        for p in self.trail: p["age"]+=dt
        self.trail = [p for p in self.trail if p["age"]<TRAIL_LIFE]

    # -- drawing ---------------------------------------------------------
    def draw(self, surface, flash=False):
        if not self.alive: return
        # Roll: brief translucent ghost to signal invincibility
        alpha = 140 if self.roll_timer>0 else 255
        draw_jet(surface, self.rect, self.body, self.canopy,
                 nose_up=True, flash=flash, alpha=alpha)
        if self.shield:
            r = max(self.rect.width, self.rect.height)*0.64
            pygame.draw.circle(surface, SHIELD_CLR, self.rect.center, int(r), width=2)
            draw_glow_circle(surface, SHIELD_CLR, self.rect.center, int(r)+4, alpha=40, layers=3)

    def draw_trail(self, layer):
        for p in self.trail:
            frac = p["age"]/TRAIL_LIFE
            r    = max(1, int(7*(1-frac)))
            al   = int(160*(1-frac))
            pygame.draw.circle(layer, (*TRAIL_CLR, al), (int(p["x"]),int(p["y"])), r)

    def draw_reload_bar(self, surface):
        if not self.alive: return
        delay = RAPID_DELAY if self.rapid_timer>0 else GUN_DELAY
        frac  = 1 - self.gun_cd/delay if delay else 1
        frac  = max(0.0, min(1.0, frac))
        x,y   = self.rect.left, self.rect.bottom+5
        pygame.draw.rect(surface, DARK_GREY, (x,y,self.rect.width,4), border_radius=2)
        pygame.draw.rect(surface, self.glow,  (x,y,int(self.rect.width*frac),4), border_radius=2)

# ---------------------------------------------------------------------------
# Enemy
# ---------------------------------------------------------------------------
class Enemy:
    def __init__(self, x, y, vx, vy, kind, w, h, fire_scale):
        self.kind=kind
        info=ENEMY_KINDS[kind]
        self.rect=pygame.Rect(x,y,w,h)
        self.vx=vx; self.vy=vy
        self.fire_scale=fire_scale
        self.hp=info["hp"]
        self.shoots=info["shoots"]
        self.n_bullets=info["bullets"]
        self.reload=random.uniform(ENEMY_FIRE_MIN,ENEMY_FIRE_MAX)/fire_scale
        self.flash_t=0.0
        self.dying=False; self.death_t=0.0
        self.mode="patrol"
        self.redir_t=random.uniform(SCOUT_REDIR_MIN,SCOUT_REDIR_MAX)
        ec = ENEMY_COLOURS[kind]
        self.body=ec["body"]; self.canopy=ec["canopy"]

    def nose_up(self): return self.vy<0
    def nose(self):
        return (self.rect.centerx, self.rect.top if self.nose_up() else self.rect.bottom)

    def update(self, dt, target_centers):
        if self.dying: return
        # In 2-player mode pick the nearer living player as the aggro target
        nearest = None
        best_d  = 1e9
        for tc in target_centers:
            d = pygame.Vector2(self.rect.center).distance_squared_to(tc)
            if d < best_d: best_d=d; nearest=tc

        if self.kind=="kamikaze":
            self._kamikaze(dt, nearest)
        elif self.kind=="scout":
            self._scout(dt)
        else:
            self._bounce()

    def _bounce(self):
        self.rect.x+=self.vx; self.rect.y+=self.vy
        if self.rect.left<=0 or self.rect.right>=W:  self.vx=-self.vx
        if self.rect.top<=0  or self.rect.bottom>=H: self.vy=-self.vy
        self.rect.clamp_ip(pygame.Rect(0,0,W,H))

    def _scout(self, dt):
        self.redir_t-=dt
        if self.redir_t<=0:
            self.redir_t=random.uniform(SCOUT_REDIR_MIN,SCOUT_REDIR_MAX)
            sp=math.hypot(self.vx,self.vy)
            a=random.uniform(0,2*math.pi)
            self.vx=math.cos(a)*sp; self.vy=math.sin(a)*sp
        self._bounce()

    def _kamikaze(self, dt, target):
        if self.mode=="patrol":
            if target and math.hypot(self.rect.centerx-target[0],
                                     self.rect.centery-target[1]) <= KAMIKAZE_RANGE:
                self.mode="dive"
            self._bounce(); return
        if target:
            d=dir_to(self.rect.center, target)
            self.vx=d.x*KAMIKAZE_SPEED; self.vy=d.y*KAMIKAZE_SPEED
        self.rect.x+=self.vx; self.rect.y+=self.vy
        self.rect.clamp_ip(pygame.Rect(0,0,W,H))

    def try_shoot(self, dt, target_centers):
        if not self.shoots or self.dying: return []
        self.reload-=dt
        if self.reload>0: return []
        self.reload=random.uniform(ENEMY_FIRE_MIN,ENEMY_FIRE_MAX)/self.fire_scale
        # Aim at nearest player
        nearest=None; best_d=1e9
        for tc in target_centers:
            d=pygame.Vector2(self.rect.center).distance_squared_to(tc)
            if d<best_d: best_d=d; nearest=tc
        if nearest is None: return []
        start=self.nose(); aim=dir_to(start,nearest)
        if self.n_bullets<=1:
            return [Bullet(start,aim,ENEMY_BSPEED,(200,30,30))]
        half=self.n_bullets//2
        return [Bullet(start,aim.rotate(o*BOMBER_SPREAD),ENEMY_BSPEED,(200,30,30))
                for o in range(-half,half+1)]

    def hit(self, force=False):
        if self.dying: return
        self.flash_t=HIT_FLASH_DUR
        self.hp-=self.hp if force else 1
        if self.hp<=0:
            self.dying=True; self.death_t=HIT_FLASH_DUR

    def hitbox(self): return self.rect.inflate(-HITBOX_SHRINK,-HITBOX_SHRINK)

    def draw(self, surface):
        flash=(self.flash_t>0)
        draw_jet(surface, self.rect, self.body, self.canopy,
                 nose_up=self.nose_up(), flash=flash)

    def draw_warning(self, surface):
        if self.dying or not self.shoots or not (0<self.reload<=WARN_LEAD): return
        frac=1-self.reload/WARN_LEAD
        pulse=0.6+0.4*abs(math.sin(frac*math.pi*3))
        al=int(255*pulse)
        sz=12
        cx=self.rect.centerx
        cy=(self.rect.top-14) if self.nose_up() else (self.rect.bottom+14)
        ic=pygame.Surface((sz*2,sz*2),pygame.SRCALPHA)
        pygame.draw.polygon(ic,(*WARNING_CLR,al),[(sz,1),(1,sz*2-2),(sz*2-1,sz*2-2)])
        f=arcade_font(12); m=f.render("!",True,(40,30,0))
        ic.blit(m,m.get_rect(center=(sz,int(sz*1.2))))
        surface.blit(ic,(cx-sz,cy-sz))

# ---------------------------------------------------------------------------
# Boss
# ---------------------------------------------------------------------------
class Boss:
    """Mega jet that spawns every 5 waves, fires in 8 directions, drops pickups."""

    def __init__(self, fire_scale):
        self.rect = pygame.Rect(0, 0, int(JET_W*BOSS_SCALE), int(JET_H*BOSS_SCALE))
        self.rect.centerx = W//2
        self.rect.top = 40
        self.vx = 0
        self.vy = BOSS_SPEED
        self.hp = BOSS_HP
        self.max_hp = BOSS_HP
        self.fire_scale = fire_scale
        self.reload = 0.4 / (BOSS_FIRE_RATE * fire_scale)
        self.flash_t = 0.0
        self.dying = False
        self.death_t = 0.0

    def update(self, dt, target_centers):
        if self.dying:
            return

        # Gentle bouncing movement
        if self.rect.left <= 0 or self.rect.right >= W:
            self.vx = -self.vx
        if self.rect.top <= 40 or self.rect.bottom >= H:
            self.vy = -self.vy

        self.rect.x += self.vx
        self.rect.y += self.vy
        self.rect.clamp_ip(pygame.Rect(0, 40, W, H-40))

    def try_shoot(self, dt, target_centers):
        if self.dying:
            return []
        self.reload -= dt
        if self.reload > 0:
            return []
        self.reload = 0.4 / (BOSS_FIRE_RATE * self.fire_scale)

        # Fire in 8 directions
        start = self.rect.center
        bullets = []
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            direction = pygame.Vector2(math.cos(rad), math.sin(rad))
            bullets.append(Bullet(start, direction, BOSS_BULLET_SPEED, (255, 200, 100)))
        return bullets

    def hit(self, force=False):
        if self.dying:
            return
        self.flash_t = HIT_FLASH_DUR
        self.hp -= (self.hp if force else 1)
        if self.hp <= 0:
            self.dying = True
            self.death_t = HIT_FLASH_DUR

    def hitbox(self):
        return self.rect.inflate(-HITBOX_SHRINK, -HITBOX_SHRINK)

    def draw(self, surface):
        flash = self.flash_t > 0
        draw_jet(surface, self.rect, BOSS_CLR, (255, 255, 100), nose_up=True, flash=flash)
        # Draw health bar
        bar_w = self.rect.width
        bar_h = 6
        bar_x = self.rect.x
        bar_y = self.rect.top - 14
        pygame.draw.rect(surface, HEALTH_BAR_BG, (bar_x, bar_y, bar_w, bar_h), border_radius=2)
        frac = self.hp / self.max_hp
        pygame.draw.rect(surface, HEALTH_BAR_FG, (bar_x, bar_y, int(bar_w*frac), bar_h), border_radius=2)
        # Label
        txt(surface, "BOSS", 16, BOSS_CLR, center=(self.rect.centerx, bar_y-12), shadow=False, style="body")

# ---------------------------------------------------------------------------
# Wave / spawn helpers
# ---------------------------------------------------------------------------
def _kind_pool(wave):
    p=["fighter"]
    if wave>=2: p.append("scout")
    if wave>=3: p.append("bomber")
    if wave>=4: p.append("kamikaze")
    return p

def _wave_count(wave, diff):
    return max(1, min(int(round(WAVE_BASE + (wave-1)*diff["growth"])), WAVE_MAX))

def _ramp(score):
    sp=min(1+score/SPEED_RAMP_SCALE, SPEED_RAMP_CAP)
    fi=min(1+score/FIRE_RAMP_SCALE,  FIRE_RAMP_CAP)
    return sp,fi

def _safe_areas(players):
    return [p.rect.inflate(SAFE_ZONE,SAFE_ZONE) for p in players if p.alive]

def spawn_wave(wave, diff, players, score):
    pool=_kind_pool(wave); n=_wave_count(wave,diff)
    sp_b,fi_b=_ramp(score)
    sp_s=diff["speed"]*sp_b; fi_s=diff["fire"]*fi_b
    safes=_safe_areas(players)
    enemies=[]; att=0
    while len(enemies)<n and att<n*80:
        att+=1
        kind=random.choice(pool); info=ENEMY_KINDS[kind]
        ew=max(20,int(JET_W*info["scale"])); eh=max(20,int(JET_H*info["scale"]))
        x=random.randint(0,W-ew); y=random.randint(0,H-eh)
        spot=pygame.Rect(x,y,ew,eh)
        if any(spot.colliderect(s) for s in safes): continue
        sp=random.uniform(info["vmin"],info["vmax"])*sp_s
        vx=random.choice([-1,1])*sp; vy=random.choice([-1,1])*sp
        enemies.append(Enemy(x,y,vx,vy,kind,ew,eh,fi_s))
    return enemies

# ---------------------------------------------------------------------------
# Round (one game session, 1P or 2P)
# ---------------------------------------------------------------------------
class Round:
    def __init__(self, mode, diff_name, p1_col, p2_col, is_tutorial=False, is_arcade=False, is_versus=False):
        self.mode     = mode            # "1P" or "2P"
        self.diff     = DIFFICULTIES[diff_name]
        self.two      = (mode=="2P")
        self.is_tutorial = is_tutorial
        self.is_arcade = is_arcade
        self.is_versus = is_versus
        self.players  = [Player(0, p1_col, self.two)]
        if self.two:
            self.players.append(Player(1, p2_col, self.two))

        self.wave     = 0 if is_tutorial else 1
        self.boss     = None
        self.enemies  = [] if is_tutorial else spawn_wave(self.wave, self.diff, self.players, 0)
        if is_tutorial:
            # Single slow fighter for tutorial
            self.enemies = [Enemy(W//2, 80, 0.5, 0.5, "fighter", JET_W, JET_H, 0.3)]
        self.wave_break = 0.0

        self.all_shots     = []   # combined player + enemy shots for drawing
        self.all_missiles  = []
        self.pickups       = []
        self.explosions    = []

        self.pickup_t = random.uniform(PICKUP_SPAWN_MIN, PICKUP_SPAWN_MAX)
        self.shake_mag= 0.0; self.shake_t=0.0
        self.crash_t  = 0.0   # time since last player died
        self.over     = False

        # Arcade cabinet mode
        self.lives = 3 if is_arcade else 1
        self.respawn_point = self.players[0].rect.center if not self.two else None

    # properties for convenience
    @property
    def total_score(self):
        return sum(p.score for p in self.players)

    def shake(self, mag, dur):
        if mag >= self.shake_mag or self.shake_t<=0:
            self.shake_mag=mag; self.shake_t=dur

    def _boom(self, center, scale=1.0):
        self.explosions.append(Explosion(center,scale)); sfx("boom")

    # -- update ----------------------------------------------------------
    def update(self, dt, keys_held, events):
        if self.over:
            self.crash_t+=dt
            for e in self.explosions: e.update(dt)
            self.explosions=[e for e in self.explosions if not e.done()]
            return

        self.shake_t=max(0.0, self.shake_t-dt)
        living=[p for p in self.players if p.alive]

        # Players
        for p in living:
            p.handle_input(keys_held, dt, events)
            p.update_timers(dt)
            if not self.is_tutorial:
                p.score+=PPS*dt
            for b in p.p_shots: b.update()
            for m in p.missiles:
                tgts=[e.hitbox() for e in self.enemies if not e.dying]
                if self.boss and not self.boss.dying:
                    tgts.append(self.boss.hitbox())
                m.update(dt,tgts)
            p.p_shots=[b for b in p.p_shots if b.on_screen()]
            p.missiles=[m for m in p.missiles if m.on_screen()]

        # Enemies
        target_cs=[p.rect.center for p in living]
        for e in self.enemies:
            e.update(dt, target_cs)
            if e.flash_t>0: e.flash_t=max(0.0,e.flash_t-dt)
            for b in e.try_shoot(dt, target_cs):
                # In 2P, assign each enemy shot to the nearest living player
                if self.two and len(living)>1:
                    nearest=min(living, key=lambda p:
                        pygame.Vector2(p.rect.center).distance_squared_to(b.rect.center))
                    nearest.e_shots.append(b)
                elif living:
                    living[0].e_shots.append(b)

        # Boss
        if self.boss and not self.boss.dying:
            self.boss.update(dt, target_cs)
            if self.boss.flash_t > 0:
                self.boss.flash_t = max(0.0, self.boss.flash_t - dt)
            for b in self.boss.try_shoot(dt, target_cs):
                # Boss fires at all living players in versus mode, or nearest player
                if self.is_versus and len(living) > 0:
                    living[0].e_shots.append(b)
                elif self.two and len(living) > 1:
                    nearest = min(living, key=lambda p:
                        pygame.Vector2(p.rect.center).distance_squared_to(b.rect.center))
                    nearest.e_shots.append(b)
                elif living:
                    living[0].e_shots.append(b)

        for p in living:
            for b in p.e_shots: b.update()
            p.e_shots=[b for b in p.e_shots if b.on_screen()]

        # Resolve player-shot hits
        self._resolve_shots(living)

        # Dying enemies
        self._update_dying(dt, living)

        # Check player collisions
        for p in living:
            self._check_hit(p)

        # Pickups
        self._update_pickups(dt, living)

        # Wave progression
        self._wave_progress(dt, living)

        # Explosions
        for ex in self.explosions: ex.update(dt)
        self.explosions=[ex for ex in self.explosions if not ex.done()]

        # End conditions
        if self.is_tutorial:
            # Tutorial ends when player shoots the fighter once
            if any(len(p.p_shots) > 0 for p in self.players):
                self.over = True
        elif self.is_arcade and self.lives <= 0:
            self.over = True
        elif self.two and all(not p.alive for p in self.players):
            self.over=True
        elif not self.two and not self.players[0].alive:
            self.over=True

    def _resolve_shots(self, living):
        for p in living:
            for b in list(p.p_shots):
                for e in self.enemies:
                    if e.dying: continue
                    if b.rect.colliderect(e.hitbox()):
                        e.hit(); p.p_shots.remove(b)
                        self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR); break
            for m in list(p.missiles):
                for e in self.enemies:
                    if e.dying: continue
                    if m.rect.colliderect(e.hitbox()):
                        e.hit(force=True); p.missiles.remove(m)
                        self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR); break

        # Boss hits
        if self.boss and not self.boss.dying:
            for p in living:
                for b in list(p.p_shots):
                    if b.rect.colliderect(self.boss.hitbox()):
                        self.boss.hit(); p.p_shots.remove(b)
                        self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR); break
                for m in list(p.missiles):
                    if m.rect.colliderect(self.boss.hitbox()):
                        self.boss.hit(force=True); p.missiles.remove(m)
                        self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR); break

    def _update_dying(self, dt, living):
        done=[e for e in self.enemies if e.dying]
        for e in done:
            e.death_t-=dt
            if e.death_t<=0:
                self.enemies.remove(e)
                self._boom(e.rect.center)
                pts=KILL_PTS[e.kind]
                living=[p for p in self.players if p.alive]
                if living:
                    scorer=min(living,key=lambda p:
                        pygame.Vector2(p.rect.center).distance_squared_to(e.rect.center))
                    scorer.score+=pts; scorer.kills+=1

        # Boss death
        if self.boss and self.boss.dying:
            self.boss.death_t -= dt
            if self.boss.death_t <= 0:
                self._boom(self.boss.rect.center, 2.0)
                # Award points
                pts = 500
                living = [p for p in self.players if p.alive]
                if living:
                    scorer = min(living, key=lambda p:
                        pygame.Vector2(p.rect.center).distance_squared_to(self.boss.rect.center))
                    scorer.score += pts
                    scorer.kills += 1
                # Drop random pickup
                self.pickups.append(Pickup(random.choice(list(PICKUP_KINDS)), self.boss.rect.centerx))
                # Arcade cabinet: gain a life
                if self.is_arcade:
                    self.lives += 1
                self.boss = None

    def _check_hit(self, p):
        if not p.alive or p.invincible(): return
        hb=p.hitbox()

        # Boss collision
        if self.boss and not self.boss.dying and hb.colliderect(self.boss.hitbox()):
            if p.absorb():
                self.boss.hit(force=True)
                self._boom(p.rect.center, 0.45)
                self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR)
            else:
                self._boom(self.boss.rect.center)
                self.boss.hit(force=True)
                self._boom(p.rect.center, 1.3)
                self.shake(SHAKE_DEATH_MAG, SHAKE_DEATH_DUR)
                if self.is_arcade:
                    self.lives -= 1
                    if self.lives > 0:
                        p.alive = True
                        p.shield = True
                        p.missile_ch = MISSILE_MAX
                        p.rect.center = self.respawn_point or (W//2, H*2//3)
                        self.crash_t = 0.0
                    else:
                        p.alive = False
                else:
                    p.alive=False
                self.crash_t=0.0
                if not self.two and not self.is_arcade: self.over=True
            return

        # Enemy collision
        for e in list(self.enemies):
            if e.dying or not hb.colliderect(e.hitbox()): continue
            if p.absorb():
                e.hit(force=True); self._boom(p.rect.center,0.45)
                self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR)
            else:
                self._boom(e.rect.center); self.enemies.remove(e)
                self._boom(p.rect.center, 1.3)
                self.shake(SHAKE_DEATH_MAG, SHAKE_DEATH_DUR)
                if self.is_arcade:
                    self.lives -= 1
                    if self.lives > 0:
                        p.alive = True
                        p.shield = True
                        p.missile_ch = MISSILE_MAX
                        p.rect.center = self.respawn_point or (W//2, H*2//3)
                        self.crash_t = 0.0
                    else:
                        p.alive = False
                else:
                    p.alive=False
                self.crash_t=0.0
                if not self.two and not self.is_arcade: self.over=True
            return

        # Bullet collision
        for b in list(p.e_shots):
            if not hb.colliderect(b.rect): continue
            if p.absorb():
                p.e_shots.remove(b); self._boom(p.rect.center,0.35)
                self.shake(SHAKE_HIT_MAG, SHAKE_HIT_DUR)
            else:
                self._boom(p.rect.center,1.3)
                self.shake(SHAKE_DEATH_MAG, SHAKE_DEATH_DUR)
                if self.is_arcade:
                    self.lives -= 1
                    if self.lives > 0:
                        p.alive = True
                        p.shield = True
                        p.missile_ch = MISSILE_MAX
                        p.rect.center = self.respawn_point or (W//2, H*2//3)
                        self.crash_t = 0.0
                    else:
                        p.alive = False
                else:
                    p.alive=False
                self.crash_t=0.0
                if not self.two and not self.is_arcade: self.over=True
            return

    def _update_pickups(self, dt, living):
        self.pickup_t-=dt
        if self.pickup_t<=0 and not self.pickups and not self.is_tutorial:
            self.pickup_t=random.uniform(PICKUP_SPAWN_MIN,PICKUP_SPAWN_MAX)
            kind=random.choice(list(PICKUP_KINDS))
            self.pickups.append(Pickup(kind, random.randint(PICKUP_SIZE,W-PICKUP_SIZE)))
        for pk in self.pickups: pk.update(dt)
        self.pickups=[pk for pk in self.pickups if not pk.off_screen()]
        for pk in list(self.pickups):
            for p in living:
                if p.hitbox().colliderect(pk.rect):
                    pk.apply(p); self.pickups.remove(pk); sfx("pick"); break

    def _wave_progress(self, dt, living):
        if self.enemies or self.boss: return
        if self.is_tutorial:
            return
        if self.wave_break<=0:
            self.wave_break=WAVE_BREAK; return
        self.wave_break-=dt
        if self.wave_break<=0:
            self.wave+=1
            # Check for boss every 5 waves
            if self.wave % BOSS_WAVE_INTERVAL == 0:
                sp_b, fi_b = _ramp(self.total_score)
                fi_s = self.diff["fire"] * fi_b
                self.boss = Boss(fi_s)
            else:
                self.enemies=spawn_wave(self.wave,self.diff,self.players,self.total_score)

    # -- drawing ---------------------------------------------------------
    def draw(self, surface, effects_layer, night_blend, stars,
             day_sky, night_sky, back_clouds, front_clouds):
        # Sky
        surface.blit(day_sky,(0,0))
        if night_blend>0:
            night_sky.set_alpha(int(255*night_blend))
            surface.blit(night_sky,(0,0))
        if night_blend>0:
            draw_stars(surface, stars, night_blend)
        for c in back_clouds: c.draw(surface)
        for c in front_clouds: c.draw(surface)

        # Trails
        effects_layer.fill((0,0,0,0))
        for p in self.players: p.draw_trail(effects_layer)
        surface.blit(effects_layer,(0,0))

        # Shots + missiles
        for p in self.players:
            for b in p.p_shots: b.draw(surface)
            for b in p.e_shots: b.draw(surface)
            for m in p.missiles: m.draw(surface)

        # Pickups
        for pk in self.pickups: pk.draw(surface)

        # Enemies
        for e in self.enemies:
            e.draw(surface)
            e.draw_warning(surface)

        # Boss
        if self.boss:
            self.boss.draw(surface)

        # Players
        for p in self.players:
            p.draw(surface)
            p.draw_reload_bar(surface)

        # Explosions (on top)
        for ex in self.explosions: ex.draw(surface)

        # HUD
        self._draw_hud(surface)

    def _draw_hud(self, surface):
        if self.is_tutorial:
            txt(surface, "HOLD SPACE TO FIRE", 24, YELLOW, center=(W//2, 30), style="body")
            txt(surface, "ARROW KEYS TO MOVE", 24, YELLOW, center=(W//2, 60), style="body")
            txt(surface, "PRESS SPACE WHEN READY", 18, HUD_DIM, center=(W//2, H-30), style="body")
            return

        if self.two:
            self._draw_player_panel(surface, self.players[0], 12, 12, anchor="left")
            self._draw_player_panel(surface, self.players[1], W-12, 12, anchor="right")
            # Wave indicator centred
            txt(surface, f"WAVE {self.wave}", 24, YELLOW, center=(W//2, 18), style="title")
            if self.wave_break>0:
                txt(surface, "WAVE CLEARED", 28, GREEN, center=(W//2, 50), style="body")
        else:
            p=self.players[0]
            txt(surface, f"SCORE {int(p.score):>6}", 26, HUD_TEXT, topleft=(14,12), style="body")
            txt(surface, f"WAVE {self.wave}  KILLS {p.kills}", 18, HUD_DIM, topleft=(14,38), style="body")
            if self.is_arcade:
                txt(surface, f"LIVES {self.lives}", 18, RED, topleft=(14, 58), style="body")
            self._draw_ability_bar(surface, p, 14, H-68)
            # Radar top-right
            self._draw_radar(surface, self.players)

    def _draw_player_panel(self, surface, p, x, y, anchor):
        w,h = 210, 74
        px  = x if anchor=="left" else x-w
        draw_panel(surface, pygame.Rect(px,y,w,h))
        col = p.glow if p.alive else GREY
        label = f"P{p.idx+1} [{p.colour_name}]"
        txt(surface, label, 16, col, topleft=(px+8, y+6), style="body")
        txt(surface, f"SCORE {int(p.score):>6}", 20, HUD_TEXT if p.alive else GREY,
            topleft=(px+8, y+24), style="body")
        txt(surface, f"KILLS {p.kills}", 16, HUD_DIM, topleft=(px+8, y+46), style="body")
        # Shield / missile indicators
        sh_col = SHIELD_CLR if p.shield else DARK_GREY
        pygame.draw.circle(surface, sh_col, (px+w-28, y+20), 8)
        for i in range(MISSILE_MAX):
            mc = MISSILE_CLR if i<p.missile_ch else DARK_GREY
            pygame.draw.rect(surface, mc,
                             (px+w-22+i*10 - 14, y+40, 8, 14), border_radius=2)
        if not p.alive:
            txt(surface, "SHOT DOWN", 16, RED, center=(px+w//2, y+h//2+10), style="body")
        self._draw_radar(surface, self.players, rx=px if anchor=="right" else px+w-RADAR_W, ry=y+h+6)

    def _draw_ability_bar(self, surface, p, x, y):
        lines=[
            f"SHIELD  {'RDY' if p.shield else '...'}",
            f"MISSILE {p.missile_ch}/{MISSILE_MAX}",
            f"DASH    {'RDY' if p.roll_cd<=0 else '...'}",
        ]
        for i,line in enumerate(lines):
            txt(surface, line, 16, HUD_DIM, topleft=(x, y+i*20), style="body")

    def _draw_radar(self, surface, players, rx=None, ry=None):
        if rx is None: rx=W-RADAR_W-14
        if ry is None: ry=14
        # Draw panel (title is handled by draw_panel internally, using txt internally)
        pan = pygame.Surface((RADAR_W, RADAR_H), pygame.SRCALPHA)
        pan.fill(PANEL_BG)
        pygame.draw.rect(pan, PANEL_EDGE, pan.get_rect(), width=2, border_radius=6)
        surface.blit(pan, (rx, ry))
        txt(surface, "RADAR", 14, YELLOW, center=(rx+RADAR_W//2, ry+10), style="body")
        def rp(pos):
            return (rx+int(pos[0]/W*RADAR_W), ry+int(pos[1]/H*RADAR_H))
        for e in self.enemies:
            if not e.dying:
                pygame.draw.circle(surface, RED, rp(e.rect.center), 3)
        if self.boss and not self.boss.dying:
            pygame.draw.circle(surface, BOSS_CLR, rp(self.boss.rect.center), 4)
        for p in players:
            if p.alive:
                pygame.draw.circle(surface, p.canopy, rp(p.rect.center), 4)

# ---------------------------------------------------------------------------
# Menu system
# ---------------------------------------------------------------------------
class MenuScreen:
    """Manages all menu screens: main, options (colour picker), high scores."""

    MAIN_ITEMS   = ["1 PLAYER", "2 PLAYERS", "ARCADE CABINET", "TUTORIAL", "OPTIONS", "HIGH SCORES", "QUIT"]
    OPTION_ITEMS = ["P1 COLOUR", "P2 COLOUR", "DIFFICULTY", "BACK"]

    def __init__(self, data):
        self.data        = data
        self.screen      = "main"     # main / options / scores / mode_select
        self.cursor      = 0
        self.diff_idx    = DIFF_NAMES.index("ACE")
        self.p1_col_idx  = JET_COLOUR_NAMES.index(data["p1_colour"])
        self.p2_col_idx  = JET_COLOUR_NAMES.index(data["p2_colour"])
        self.mode_select_for = None   # "2P" or "ARCADE" or None
        self._blink      = 0.0
        self._star_anim  = 0.0
        self._particles  = [(random.randint(0,W), random.randint(0,H),
                             random.uniform(0.3,2.0)) for _ in range(60)]

    def p1_colour(self): return JET_COLOUR_NAMES[self.p1_col_idx]
    def p2_colour(self): return JET_COLOUR_NAMES[self.p2_col_idx]
    def difficulty(self): return DIFF_NAMES[self.diff_idx]

    def handle(self, events):
        """Returns ("start_1p"|"start_2p"|"start_arcade"|"start_tutorial"|"quit"|None)."""
        for ev in events:
            if ev.type != pygame.KEYDOWN: continue
            k=ev.key
            if self.screen=="main":
                if k in (pygame.K_UP,):    self.cursor=(self.cursor-1)%len(self.MAIN_ITEMS)
                if k in (pygame.K_DOWN,):  self.cursor=(self.cursor+1)%len(self.MAIN_ITEMS)
                if k in (pygame.K_RETURN, pygame.K_SPACE):
                    item=self.MAIN_ITEMS[self.cursor]
                    if item=="1 PLAYER":       return "start_1p"
                    if item=="2 PLAYERS":      self.screen="mode_select"; self.cursor=0; self.mode_select_for="2P"
                    if item=="ARCADE CABINET": return "start_arcade"
                    if item=="TUTORIAL":       return "start_tutorial"
                    if item=="OPTIONS":        self.screen="options"; self.cursor=0
                    if item=="HIGH SCORES":    self.screen="scores";  self.cursor=0
                    if item=="QUIT":           return "quit"
                if k==pygame.K_ESCAPE: return "quit"

            elif self.screen=="mode_select":
                if k in (pygame.K_UP, pygame.K_DOWN): self.cursor = 1 - self.cursor
                if k in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.cursor == 0:
                        return "start_2p_coop"
                    else:
                        return "start_2p_versus"
                if k == pygame.K_ESCAPE:
                    self.screen = "main"; self.cursor = 1

            elif self.screen=="options":
                if k==pygame.K_UP:   self.cursor=(self.cursor-1)%len(self.OPTION_ITEMS)
                if k==pygame.K_DOWN: self.cursor=(self.cursor+1)%len(self.OPTION_ITEMS)
                item=self.OPTION_ITEMS[self.cursor]
                if k in (pygame.K_LEFT,pygame.K_RIGHT):
                    d=1 if k==pygame.K_RIGHT else -1
                    if item=="P1 COLOUR":
                        self.p1_col_idx=(self.p1_col_idx+d)%len(JET_COLOUR_NAMES)
                        self.data["p1_colour"]=self.p1_colour(); save_data(self.data)
                    if item=="P2 COLOUR":
                        self.p2_col_idx=(self.p2_col_idx+d)%len(JET_COLOUR_NAMES)
                        self.data["p2_colour"]=self.p2_colour(); save_data(self.data)
                    if item=="DIFFICULTY":
                        self.diff_idx=(self.diff_idx+d)%len(DIFF_NAMES)
                if k in (pygame.K_RETURN,pygame.K_SPACE) and item=="BACK":
                    self.screen="main"
                if k==pygame.K_ESCAPE: self.screen="main"

            elif self.screen=="scores":
                if k in (pygame.K_ESCAPE,pygame.K_RETURN,pygame.K_SPACE):
                    self.screen="main"
        return None

    def update(self, dt):
        self._blink=(self._blink+dt)%1.0
        self._star_anim+=dt
        for i,(sx,sy,sp) in enumerate(self._particles):
            sy+=sp
            if sy>H: sy=-5; sx=random.randint(0,W)
            self._particles[i]=(sx,sy,sp)

    def draw(self, surface, day_sky):
        surface.blit(day_sky,(0,0))
        # Drifting star particles over the sky for the title screen
        for sx,sy,sp in self._particles:
            al=int(80+80*abs(math.sin(self._star_anim*sp)))
            pygame.draw.circle(surface,(200,200,220),(int(sx),int(sy)),1)

        if self.screen=="main":        self._draw_main(surface)
        elif self.screen=="mode_select": self._draw_mode_select(surface)
        elif self.screen=="options":   self._draw_options(surface)
        elif self.screen=="scores":    self._draw_scores(surface)

    def _draw_main(self, surface):
        # Title with glow — big bold Impact for arcade marquee feel
        cy=60
        for dx in (-2,2,0):
            col=YELLOW if dx==0 else (100,70,0)
            txt(surface,"JET  DODGE",60,col,center=(W//2+dx,cy),shadow=(dx==0), style="title")
        txt(surface,"90s ARCADE SKY COMBAT",20,ORANGE,center=(W//2,cy+48), style="body")

        # Preview of chosen colours
        pr=pygame.Rect(W//2-80, cy+65, JET_W, JET_H)
        body1,can1,_=JET_COLOUR_OPTIONS[self.p1_colour()]
        draw_jet(surface,pr,body1,can1,nose_up=True)
        txt(surface,f"P1: {self.p1_colour()}",16,HUD_DIM,
            center=(pr.centerx,pr.bottom+8), style="body")
        pr2=pygame.Rect(W//2+40,cy+65,JET_W,JET_H)
        body2,can2,_=JET_COLOUR_OPTIONS[self.p2_colour()]
        draw_jet(surface,pr2,body2,can2,nose_up=True)
        txt(surface,f"P2: {self.p2_colour()}",16,HUD_DIM,
            center=(pr2.centerx,pr2.bottom+8), style="body")

        menu_y=240
        for i,item in enumerate(self.MAIN_ITEMS):
            sel=(i==self.cursor)
            col=YELLOW if sel else HUD_TEXT
            prefix=">" if sel else " "
            blink_hide=(sel and self._blink>0.5)
            if not blink_hide:
                txt(surface, f"{prefix} {item}", 28, col, center=(W//2, menu_y+i*40), style="body")

        txt(surface,"ESC: QUIT",14,HUD_DIM,center=(W//2,H-20), style="body")
        txt(surface,f"DIFF: {self.difficulty()}",16,GREY,center=(W//2,H-38), style="body")

    def _draw_mode_select(self, surface):
        txt(surface, "2 PLAYER MODE", 44, YELLOW, center=(W//2, 70), style="title")
        modes = ["CO-OP (Share Score)", "VERSUS (Compete)"]
        for i, mode in enumerate(modes):
            sel = (i == self.cursor)
            col = YELLOW if sel else HUD_TEXT
            prefix = ">" if sel else " "
            blink_hide = (sel and self._blink > 0.5)
            if not blink_hide:
                txt(surface, f"{prefix} {mode}", 28, col, center=(W//2, 200 + i*60), style="body")
        txt(surface, "ESC to go back", 16, HUD_DIM, center=(W//2, H-30), style="body")

    def _draw_options(self, surface):
        txt(surface,"OPTIONS",44,YELLOW,center=(W//2,70), style="title")
        items=self.OPTION_ITEMS
        values=[
            f"< {self.p1_colour()} >",
            f"< {self.p2_colour()} >",
            f"< {self.difficulty()} >",
            "",
        ]
        # Colour swatches
        swatch_y=160
        for ci, cname in enumerate(JET_COLOUR_NAMES):
            b,ca,g=JET_COLOUR_OPTIONS[cname]
            sel1=(ci==self.p1_col_idx); sel2=(ci==self.p2_col_idx)
            sx=80+ci*85; sy=swatch_y
            r=pygame.Rect(sx-20,sy,JET_W,JET_H)
            draw_jet(surface,r,b,ca,nose_up=True)
            if sel1: pygame.draw.rect(surface,b,r.inflate(6,6),width=2,border_radius=3)
            if sel2: pygame.draw.rect(surface,(200,200,200),r.inflate(10,10),width=2,border_radius=3)
            txt(surface,cname[:4],11,HUD_DIM,center=(sx,sy+JET_H+10))

        menu_y=310
        for i,(item,val) in enumerate(zip(items,values)):
            sel=(i==self.cursor)
            col=YELLOW if sel else HUD_TEXT
            line=f"> {item}  {val}" if sel else f"  {item}  {val}"
            txt(surface, line, 24, col, center=(W//2, menu_y+i*46), style="body")

        txt(surface,"LEFT/RIGHT to change    ENTER to confirm",16,HUD_DIM,center=(W//2,H-24), style="body")
        # Show P1 / P2 label on the swatch row
        b1,_,__=JET_COLOUR_OPTIONS[self.p1_colour()]
        b2,_,__=JET_COLOUR_OPTIONS[self.p2_colour()]
        txt(surface,"P1",12,b1,center=(80+self.p1_col_idx*85-6,swatch_y-14),shadow=False)
        txt(surface,"P2",12,(200,200,200),center=(80+self.p2_col_idx*85+6,swatch_y-14),shadow=False)

    def _draw_scores(self, surface):
        txt(surface,"HIGH SCORES",44,YELLOW,center=(W//2,70), style="title")
        cx1=W//4; cx2=W//2; cx3=3*W//4
        txt(surface,"1 PLAYER",20,HUD_TEXT,center=(cx1,130), style="body")
        txt(surface,"2 PLAYER",20,HUD_TEXT,center=(cx2,130), style="body")
        txt(surface,"ARCADE",20,HUD_TEXT,center=(cx3,130), style="body")
        hs1=self.data["hs_1p"]; hs2=self.data["hs_2p"]; hs_arc=self.data["hs_arcade"]
        for i in range(MAX_HS):
            s1=f"{i+1}. {hs1[i]}" if i<len(hs1) else f"{i+1}. ---"
            s2=f"{i+1}. {hs2[i]}" if i<len(hs2) else f"{i+1}. ---"
            s3=f"{i+1}. {hs_arc[i]}" if i<len(hs_arc) else f"{i+1}. ---"
            txt(surface,s1,20,HUD_DIM,center=(cx1,175+i*32), style="body")
            txt(surface,s2,20,HUD_DIM,center=(cx2,175+i*32), style="body")
            txt(surface,s3,20,HUD_DIM,center=(cx3,175+i*32), style="body")
        txt(surface,"ENTER/ESC to go back",18,GREY,center=(W//2,H-28), style="body")

# ---------------------------------------------------------------------------
# Game-over / paused overlays
# ---------------------------------------------------------------------------
def draw_pause(surface, big_font):
    ov=pygame.Surface((W,H)); ov.set_alpha(140); ov.fill(BLACK); surface.blit(ov,(0,0))
    txt(surface,"PAUSED",56,YELLOW,center=(W//2,H//2-30), style="title")
    txt(surface,"P  TO RESUME",24,HUD_TEXT,center=(W//2,H//2+26), style="body")

def draw_game_over(surface, rnd, data, new_hs):
    ov=pygame.Surface((W,H)); ov.set_alpha(160); ov.fill(BLACK); surface.blit(ov,(0,0))
    txt(surface,"SHOT DOWN",56,RED,center=(W//2,90), style="title")
    if new_hs:
        txt(surface,"NEW HIGH SCORE!",28,YELLOW,center=(W//2,152), style="body")

    if rnd.two:
        # Show who won
        p1,p2=rnd.players
        winner=None
        if p1.alive and not p2.alive:   winner=p1
        elif p2.alive and not p1.alive: winner=p2
        elif int(p1.score)>int(p2.score): winner=p1
        elif int(p2.score)>int(p1.score): winner=p2
        if winner:
            txt(surface,f"P{winner.idx+1} WINS!",36,winner.glow,center=(W//2,195), style="title")
        else:
            txt(surface,"DRAW!",36,YELLOW,center=(W//2,195), style="title")
        y=240
        for p in rnd.players:
            txt(surface,
                f"P{p.idx+1} [{p.colour_name}]  SCORE {int(p.score):>6}  KILLS {p.kills}",
                20, p.glow if True else HUD_TEXT, center=(W//2,y), style="body")
            y+=34
        txt(surface,f"WAVE {rnd.wave}",20,HUD_DIM,center=(W//2,y+10), style="body")
        hs_key="hs_2p"
    elif rnd.is_arcade:
        p=rnd.players[0]
        txt(surface,
            f"SCORE {int(p.score):>6}   WAVE {rnd.wave}   KILLS {p.kills}",
            22,HUD_TEXT,center=(W//2,195), style="body")
        hs_key="hs_arcade"
    else:
        p=rnd.players[0]
        txt(surface,
            f"SCORE {int(p.score):>6}   WAVE {rnd.wave}   KILLS {p.kills}",
            22,HUD_TEXT,center=(W//2,195), style="body")
        hs_key="hs_1p"

    y_hs=340
    txt(surface,"HIGH SCORES",24,YELLOW,center=(W//2,y_hs), style="title")
    for i,s in enumerate(data[hs_key][:MAX_HS]):
        txt(surface,f"{i+1}. {s}",20,HUD_DIM,center=(W//2,y_hs+32+i*26), style="body")
    txt(surface,"R  FOR MENU   ESC  QUIT",20,HUD_DIM,center=(W//2,H-30), style="body")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    pygame.init()
    init_sound()
    screen=pygame.display.set_mode((W,H))
    pygame.display.set_caption("JET DODGE")
    clock=pygame.time.Clock()

    data=load_data()
    menu=MenuScreen(data)

    day_sky  =make_sky(SKY_DAY_TOP,  SKY_DAY_BOT)
    night_sky=make_sky(SKY_NIGHT_TOP,SKY_NIGHT_BOT)
    stars    =make_stars()
    back_c   =make_clouds(CLOUD_BACK_CNT, speed_scale=CLOUD_BACK_SCALE, alpha_scale=0.45)
    front_c  =make_clouds(CLOUD_CNT)
    scanlines,vignette=make_crt_layers()
    effects  =pygame.Surface((W,H), pygame.SRCALPHA)
    world    =pygame.Surface((W,H))

    night_blend=0.0
    state =GS.MENU
    rnd   =None
    new_hs=False
    tutorial_skipped = False

    running=True
    while running:
        dt=clock.tick(FPS)/1000
        events=pygame.event.get()

        for ev in events:
            if ev.type==pygame.QUIT:
                running=False

        # Global keys
        for ev in events:
            if ev.type==pygame.KEYDOWN:
                if ev.key==pygame.K_ESCAPE:
                    if state==GS.PLAYING: state=GS.PAUSED; sfx_stop("hum")
                    elif state==GS.PAUSED: state=GS.PLAYING; sfx_loop("hum")
                    elif state in (GS.MENU,GS.GAME_OVER): running=False
                if ev.key==pygame.K_p and state==GS.PLAYING:
                    state=GS.PAUSED; sfx_stop("hum")
                elif ev.key==pygame.K_p and state==GS.PAUSED:
                    state=GS.PLAYING; sfx_loop("hum")
                if ev.key==pygame.K_r and state==GS.GAME_OVER:
                    state=GS.MENU; sfx_stop("hum")

        # State machine
        if state==GS.MENU:
            menu.update(dt)
            action=menu.handle(events)
            if action=="start_1p":
                rnd=Round("1P", menu.difficulty(), menu.p1_colour(), menu.p2_colour())
                state=GS.PLAYING; sfx_loop("hum"); new_hs=False
            elif action=="start_2p_coop":
                rnd=Round("2P", menu.difficulty(), menu.p1_colour(), menu.p2_colour(), is_versus=False)
                state=GS.PLAYING; sfx_loop("hum"); new_hs=False
            elif action=="start_2p_versus":
                rnd=Round("2P", menu.difficulty(), menu.p1_colour(), menu.p2_colour(), is_versus=True)
                state=GS.PLAYING; sfx_loop("hum"); new_hs=False
            elif action=="start_arcade":
                rnd=Round("1P", menu.difficulty(), menu.p1_colour(), menu.p2_colour(), is_arcade=True)
                state=GS.PLAYING; sfx_loop("hum"); new_hs=False
            elif action=="start_tutorial":
                if not data["tutorial_done"]:
                    rnd=Round("1P", "ACE", menu.p1_colour(), menu.p2_colour(), is_tutorial=True)
                    state=GS.PLAYING; sfx_loop("hum"); new_hs=False
                    data["tutorial_done"]=True
                    save_data(data)
                else:
                    # Tutorial already done, offer optional replay or go back
                    tutorial_skipped = True
            elif action=="quit":
                running=False

        elif state==GS.PLAYING:
            keys_held=pygame.key.get_pressed()
            rnd.update(dt, keys_held, events)

            total=rnd.total_score
            tgt_blend=1.0 if total>=NIGHT_THRESHOLD else 0.0
            night_blend=night_blend+(tgt_blend-night_blend)*NIGHT_BLEND_SPD*dt

            for c in back_c+front_c: c.update(dt)

            if rnd.over and rnd.crash_t>=CRASH_PAUSE:
                state=GS.GAME_OVER; sfx_stop("hum")
                # Save score
                if rnd.is_arcade:
                    sc=int(rnd.players[0].score)
                    old=data["hs_arcade"]
                    data["hs_arcade"]=add_score(old,sc)
                    new_hs=(not old or sc>old[0])
                elif rnd.two:
                    best=max(int(p.score) for p in rnd.players)
                    old=data["hs_2p"]
                    data["hs_2p"]=add_score(old,best)
                    new_hs=(not old or best>old[0])
                else:
                    sc=int(rnd.players[0].score)
                    old=data["hs_1p"]
                    data["hs_1p"]=add_score(old,sc)
                    new_hs=(not old or sc>old[0])
                save_data(data)

        elif state==GS.PAUSED:
            for c in back_c+front_c: c.update(dt*0.15)

        elif state==GS.GAME_OVER:
            if rnd: rnd.update(dt, pygame.key.get_pressed(), [])
            for c in back_c+front_c: c.update(dt*0.3)

        # ---- Draw -------------------------------------------------------
        if state==GS.MENU:
            menu.draw(world, day_sky)
        elif state in (GS.PLAYING, GS.PAUSED, GS.GAME_OVER) and rnd:
            rnd.draw(world, effects, night_blend, stars,
                     day_sky, night_sky, back_c, front_c)
            if state==GS.PAUSED:
                draw_pause(world, None)
            elif state==GS.GAME_OVER and rnd.crash_t>=CRASH_PAUSE:
                draw_game_over(world, rnd, data, new_hs)

        # CRT post-processing
        world.blit(scanlines,(0,0))
        world.blit(vignette, (0,0))

        # Screen shake
        off=(0,0)
        if rnd and rnd.shake_t>0:
            rnd.shake_t=max(0.0, rnd.shake_t-dt)
            off=(random.uniform(-1,1)*rnd.shake_mag,
                 random.uniform(-1,1)*rnd.shake_mag)

        screen.fill(BLACK)
        screen.blit(world,off)
        pygame.display.flip()

    pygame.quit()

if __name__=="__main__":
    main()
git init
git add .
git commit -m "Add project files"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git pull origin main --allow-unrelated-histories
git push -u origin main