"""
Simple Battle Royale (top-down) using Tkinter
Designed to run in IDLE / standard Python 3.13 (no external deps)

Save as `battle_royale.py` and run with IDLE (Run -> Run Module) or `python battle_royale.py`.

Controls:
  - WASD or Arrow keys: move
  - Mouse click: shoot toward cursor
  - P: pause/unpause

Game mechanics (simple):
  - Player vs multiple AI bots
  - Safe zone (circle) shrinks over time; outside the zone you take damage
  - Last living entity wins
  - Basic gun with cooldown, bullets as small circles

This is intentionally a small, understandable project you can expand on.
"""

import tkinter as tk
import random
import math
import time

# ---------- GAME SETTINGS ----------
WIDTH, HEIGHT = 900, 600
PLAYER_RADIUS = 10
BOT_RADIUS = 10
BULLET_RADIUS = 3
PLAYER_COLOR = "dodgerblue"
BOT_COLOR = "orange"
BULLET_COLOR = "black"
FPS = 30
MAX_BOTS = 10
BOT_SPAWN_MARGIN = 60
BULLET_SPEED = 12
PLAYER_SPEED = 5
BOT_SPEED = 3
FIRE_COOLDOWN = 0.35  # seconds
BOT_FIRE_CHANCE = 0.008  # per frame
ZONE_SHRINK_START = 8.0  # seconds before shrink begins
ZONE_SHRINK_DURATION = 60.0  # seconds over which it shrinks
INITIAL_ZONE_RADIUS = min(WIDTH, HEIGHT) * 0.45
FINAL_ZONE_RADIUS = 60
OUTSIDE_DAMAGE = 0.6  # HP lost per second outside zone
MAX_HEALTH = 100

# ---------- UTILITIES ----------

def clamp(v, a, b):
    return max(a, min(b, v))


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def normalize(vx, vy):
    mag = math.hypot(vx, vy)
    if mag == 0:
        return 0, 0
    return vx / mag, vy / mag


# ---------- ENTITY CLASSES ----------
class Bullet:
    def __init__(self, owner, x, y, vx, vy):
        self.owner = owner
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.alive = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        if self.x < -50 or self.x > WIDTH + 50 or self.y < -50 or self.y > HEIGHT + 50:
            self.alive = False


class Entity:
    def __init__(self, x, y, radius, color, speed):
        self.x = x
        self.y = y
        self.radius = radius
        self.color = color
        self.speed = speed
        self.hp = MAX_HEALTH
        self.alive = True

    def hit(self, damage):
        self.hp -= damage
        if self.hp <= 0:
            self.alive = False


class Player(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, PLAYER_RADIUS, PLAYER_COLOR, PLAYER_SPEED)
        self.last_fire = 0

    def can_fire(self):
        return (time.time() - self.last_fire) >= FIRE_COOLDOWN

    def fire(self, target_x, target_y):
        if not self.can_fire() or not self.alive:
            return None
        dx, dy = target_x - self.x, target_y - self.y
        nx, ny = normalize(dx, dy)
        vx, vy = nx * BULLET_SPEED, ny * BULLET_SPEED
        self.last_fire = time.time()
        return Bullet(self, self.x + nx * (self.radius + BULLET_RADIUS + 1), self.y + ny * (self.radius + BULLET_RADIUS + 1), vx, vy)


class Bot(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, BOT_RADIUS, BOT_COLOR, BOT_SPEED)
        self.target = None
        self.last_target_time = 0
        self.last_fire = 0

    def choose_target(self, player, bots):
        # Simple AI: target player if alive; otherwise nearest bot
        if player.alive:
            self.target = player
            return
        living = [b for b in bots if b.alive and b is not self]
        if not living:
            self.target = None
            return
        self.target = min(living, key=lambda e: distance((self.x, self.y), (e.x, e.y)))

    def update_ai(self, player, bots):
        # Choose a new random wander target occasionally
        if (time.time() - self.last_target_time) > 1.2 or self.target is None:
            self.last_target_time = time.time()
            if random.random() < 0.7 and player.alive:
                self.target = player
            else:
                # wander: random point in map
                self.target = (random.uniform(0, WIDTH), random.uniform(0, HEIGHT))

    def step(self, player, bots):
        self.update_ai(player, bots)
        tx, ty = (self.target.x, self.target.y) if isinstance(self.target, Entity) else (self.target[0], self.target[1])
        dx, dy = tx - self.x, ty - self.y
        nx, ny = normalize(dx, dy)
        # random jitter to movement
        jitter = 0.2
        self.x += (nx * self.speed) + random.uniform(-jitter, jitter)
        self.y += (ny * self.speed) + random.uniform(-jitter, jitter)
        self.x = clamp(self.x, 0, WIDTH)
        self.y = clamp(self.y, 0, HEIGHT)

    def try_fire(self, player):
        if not player.alive or not self.alive:
            return None
        if random.random() < BOT_FIRE_CHANCE:
            dx, dy = player.x - self.x, player.y - self.y
            nx, ny = normalize(dx, dy)
            vx, vy = nx * BULLET_SPEED, ny * BULLET_SPEED
            return Bullet(self, self.x + nx * (self.radius + BULLET_RADIUS + 1), self.y + ny * (self.radius + BULLET_RADIUS + 1), vx, vy)
        return None


# ---------- GAME CLASS ----------
class BattleRoyale:
    def __init__(self, master):
        self.master = master
        self.canvas = tk.Canvas(master, width=WIDTH, height=HEIGHT, bg="lightgreen")
        self.canvas.pack()

        # Entities
        self.player = Player(WIDTH / 2, HEIGHT / 2)
        self.bots = []
        self.bullets = []

        # Input state
        self.keys = set()
        self.mouse_pos = (WIDTH / 2, HEIGHT / 2)
        self.paused = False

        # Zone timing
        self.start_time = time.time()
        self.zone_center = (WIDTH / 2, HEIGHT / 2)
        self.zone_radius = INITIAL_ZONE_RADIUS

        # Bind events
        master.bind('<KeyPress>', self.on_keypress)
        master.bind('<KeyRelease>', self.on_keyrelease)
        master.bind('<Button-1>', self.on_click)
        master.bind('<Motion>', self.on_motion)

        # HUD
        self.hud_text = None

        # Start bots
        for _ in range(MAX_BOTS):
            self.spawn_bot()

        # Start update loop
        self.last_time = time.time()
        self.running = True
        self.update_loop()

    def spawn_bot(self):
        # spawn at random edge-ish position
        side = random.choice(['top', 'bottom', 'left', 'right'])
        if side == 'top':
            x = random.uniform(0 + BOT_SPAWN_MARGIN, WIDTH - BOT_SPAWN_MARGIN)
            y = random.uniform(0, BOT_SPAWN_MARGIN)
        elif side == 'bottom':
            x = random.uniform(0 + BOT_SPAWN_MARGIN, WIDTH - BOT_SPAWN_MARGIN)
            y = random.uniform(HEIGHT - BOT_SPAWN_MARGIN, HEIGHT)
        elif side == 'left':
            x = random.uniform(0, BOT_SPAWN_MARGIN)
            y = random.uniform(0 + BOT_SPAWN_MARGIN, HEIGHT - BOT_SPAWN_MARGIN)
        else:
            x = random.uniform(WIDTH - BOT_SPAWN_MARGIN, WIDTH)
            y = random.uniform(0 + BOT_SPAWN_MARGIN, HEIGHT - BOT_SPAWN_MARGIN)
        self.bots.append(Bot(x, y))

    # ---------- Input handlers ----------
    def on_keypress(self, event):
        key = event.keysym.lower()
        if key == 'p':
            self.paused = not self.paused
            return
        self.keys.add(key)

    def on_keyrelease(self, event):
        key = event.keysym.lower()
        if key in self.keys:
            self.keys.remove(key)

    def on_click(self, event):
        self.mouse_pos = (event.x, event.y)
        bullet = self.player.fire(event.x, event.y)
        if bullet:
            self.bullets.append(bullet)

    def on_motion(self, event):
        self.mouse_pos = (event.x, event.y)

    # ---------- Game logic ----------
    def update_loop(self):
        if not self.running:
            return
        now = time.time()
        dt = now - self.last_time
        self.last_time = now

        if not self.paused:
            self.update(dt)
        self.render()
        self.master.after(int(1000 / FPS), self.update_loop)

    def update(self, dt):
        # Player movement
        move_x = move_y = 0
        if 'w' in self.keys or 'up' in self.keys:
            move_y -= 1
        if 's' in self.keys or 'down' in self.keys:
            move_y += 1
        if 'a' in self.keys or 'left' in self.keys:
            move_x -= 1
        if 'd' in self.keys or 'right' in self.keys:
            move_x += 1
        nx, ny = normalize(move_x, move_y)
        self.player.x += nx * self.player.speed
        self.player.y += ny * self.player.speed
        self.player.x = clamp(self.player.x, 0, WIDTH)
        self.player.y = clamp(self.player.y, 0, HEIGHT)

        # Bots update
        for bot in self.bots:
            if not bot.alive:
                continue
            bot.step(self.player, self.bots)
            # bot shooting
            b = bot.try_fire(self.player)
            if b:
                self.bullets.append(b)

        # Bullets update
        for bullet in list(self.bullets):
            if not bullet.alive:
                self.bullets.remove(bullet)
                continue
            bullet.update()
            # check collision with player
            if bullet.owner is not self.player and self.player.alive:
                if distance((bullet.x, bullet.y), (self.player.x, self.player.y)) <= (bullet.owner.radius + self.player.radius + BULLET_RADIUS):
                    self.player.hit(18)
                    bullet.alive = False
                    continue
            # check collision with bots
            for bot in self.bots:
                if not bot.alive or bullet.owner is bot:
                    continue
                if distance((bullet.x, bullet.y), (bot.x, bot.y)) <= (BULLET_RADIUS + bot.radius):
                    bot.hit(22)
                    bullet.alive = False
                    break

        # Zone update (shrinking)
        game_elapsed = time.time() - self.start_time
        if game_elapsed < ZONE_SHRINK_START:
            self.zone_radius = INITIAL_ZONE_RADIUS
        else:
            t = clamp((game_elapsed - ZONE_SHRINK_START) / ZONE_SHRINK_DURATION, 0, 1)
            self.zone_radius = INITIAL_ZONE_RADIUS + (FINAL_ZONE_RADIUS - INITIAL_ZONE_RADIUS) * t

        # Damage outside zone
        for ent in [self.player] + self.bots:
            if not ent.alive:
                continue
            if distance((ent.x, ent.y), self.zone_center) > self.zone_radius:
                ent.hit(OUTSIDE_DAMAGE * dt * 60)  # scale by dt roughly

        # Remove dead bots occasionally
        # (keep their bodies so you can see them - but we mark alive False)

        # Win/loss conditions
        living = [e for e in ([self.player] + self.bots) if e.alive]
        if len(living) <= 1:
            self.running = False
            self.end_time = time.time()

        # Ensure at least some bots exist earlier in the game
        live_bots = sum(1 for b in self.bots if b.alive)
        if live_bots < max(2, MAX_BOTS // 3) and len(self.bots) < MAX_BOTS * 2:
            if random.random() < 0.02:
                self.spawn_bot()

    # ---------- RENDER ----------
    def render(self):
        self.canvas.delete('all')
        # draw zone (semi-opaque)
        x, y = self.zone_center
        r = self.zone_radius
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill='', outline='red', width=2)

        # bullets
        for b in self.bullets:
            if b.alive:
                self.canvas.create_oval(b.x - BULLET_RADIUS, b.y - BULLET_RADIUS, b.x + BULLET_RADIUS, b.y + BULLET_RADIUS, fill=BULLET_COLOR)

        # bots
        for bot in self.bots:
            if bot.alive:
                self.canvas.create_oval(bot.x - bot.radius, bot.y - bot.radius, bot.x + bot.radius, bot.y + bot.radius, fill=bot.color)
                # HP bar
                hpw = 20
                self.canvas.create_rectangle(bot.x - hpw / 2, bot.y - bot.radius - 8, bot.x - hpw / 2 + (hpw * (bot.hp / MAX_HEALTH)), bot.y - bot.radius - 4, fill='green')
            else:
                # dead bot marker
                self.canvas.create_line(bot.x - 8, bot.y - 8, bot.x + 8, bot.y + 8, fill='gray')
                self.canvas.create_line(bot.x - 8, bot.y + 8, bot.x + 8, bot.y - 8, fill='gray')

        # player
        if self.player.alive:
            self.canvas.create_oval(self.player.x - self.player.radius, self.player.y - self.player.radius, self.player.x + self.player.radius, self.player.y + self.player.radius, fill=self.player.color)
            # draw aiming line
            mx, my = self.mouse_pos
            self.canvas.create_line(self.player.x, self.player.y, mx, my, dash=(3, 2))
            # HP bar
            self.canvas.create_rectangle(10, 10, 210, 26, fill='black')
            self.canvas.create_rectangle(12, 12, 12 + (196 * (self.player.hp / MAX_HEALTH)), 24, fill='lime')
        else:
            self.canvas.create_text(WIDTH / 2, HEIGHT / 2 - 40, text='YOU DIED', font=('Helvetica', 32), fill='darkred')

        # HUD info
        now = time.time()
        elapsed = now - self.start_time
        info = f"Time: {int(elapsed)}s  Bots alive: {sum(1 for b in self.bots if b.alive)}  Zone: {int(self.zone_radius)}"
        if self.paused:
            info = "PAUSED - press P to resume\n" + info
        self.canvas.create_text(WIDTH - 250, 18, text=info, anchor='ne', font=('Helvetica', 12))

        if not self.running:
            winner = None
            if self.player.alive:
                winner = 'Player (You)'
            else:
                living_bots = [b for b in self.bots if b.alive]
                if living_bots:
                    winner = 'Bot'
                else:
                    winner = 'No one'
            self.canvas.create_rectangle(WIDTH / 2 - 200, HEIGHT / 2 - 80, WIDTH / 2 + 200, HEIGHT / 2 + 80, fill='white', outline='black')
            self.canvas.create_text(WIDTH / 2, HEIGHT / 2 - 20, text=f'GAME OVER', font=('Helvetica', 26), fill='black')
            self.canvas.create_text(WIDTH / 2, HEIGHT / 2 + 10, text=f'Winner: {winner}', font=('Helvetica', 18), fill='black')
            self.canvas.create_text(WIDTH / 2, HEIGHT / 2 + 40, text='Press ESC to close window or R to restart', font=('Helvetica', 12), fill='gray')

    # ---------- External controls: restart / quit ----------
    def restart(self, event=None):
        # quick restart: re-create entities
        self.player = Player(WIDTH / 2, HEIGHT / 2)
        self.bots = []
        self.bullets = []
        for _ in range(MAX_BOTS):
            self.spawn_bot()
        self.start_time = time.time()
        self.running = True
        self.paused = False
        self.last_time = time.time()


# ---------- RUN ----------
if __name__ == '__main__':
    root = tk.Tk()
    root.title('Mini Battle Royale (Tkinter)')
    game = BattleRoyale(root)

    def on_key_global(event):
        if event.keysym.lower() == 'r':
            game.restart()
        if event.keysym == 'Escape':
            root.destroy()

    root.bind('<Key>', on_key_global)
    root.mainloop()
