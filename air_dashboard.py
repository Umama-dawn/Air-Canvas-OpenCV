import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import cv2
import mediapipe as mp
import numpy as np
import math
import random
import time
import pyautogui

W, H = 1280, 720
TOP_BAR_H = 80
LEFT_BAR_W = 140

COLORS = [
    (0, 0, 255), (0, 255, 0), (255, 0, 0),
    (0, 255, 255), (255, 0, 255), (255, 255, 0),
    (0, 165, 255), (128, 0, 128), (255, 255, 255),
]
BRUSH_SIZES = [4, 8, 14, 20]
MODES = ["Whiteboard", "Shapes", "Game", "Robotics", "Mouse"]
SHAPES = ["Free", "Line", "Rect", "Circle", "Star"]

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.6, min_tracking_confidence=0.6)
mp_draw = mp.solutions.drawing_utils


def open_camera(max_tries=4):
    backends = [("DSHOW", cv2.CAP_DSHOW), ("MSMF", cv2.CAP_MSMF), ("ANY", cv2.CAP_ANY)]
    for attempt in range(max_tries):
        for idx in range(3):
            for name, backend in backends:
                print(f"Try {attempt+1}: idx={idx}, backend={name}...")
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, H)
                    for _ in range(6):
                        ret, _ = cap.read()
                        if ret:
                            print(f"[OK] Camera: idx={idx}, backend={name}")
                            return cap
                    cap.release()
                else:
                    cap.release()
        time.sleep(1)
    return None


cap = open_camera()
if cap is None:
    print("Camera not found.")
    exit()

print("\n=== READY ===")
print("HAATH SE:")
print("  Index finger only  -> Draw")
print("  Fist (2 sec hold)  -> Clear")
print("  Index+Middle hold  -> Menu click")
print("KEYBOARD SE (Air Canvas window active rakho!):")
print("  1-9  = Color")
print("  Q W E R = Brush size")
print("  T    = Whiteboard mode")
print("  Y    = Shapes mode")
print("  U    = Game mode")
print("  I    = Robotics mode")
print("  O    = Mouse mode")
print("  F    = Circle shape")
print("  G    = Rect shape")
print("  H    = Line shape")
print("  J    = Star shape")
print("  C    = Clear")
print("  Z    = Undo")
print("  S    = Save")
print("  ESC  = Exit")
print("=============\n")

mode = "Whiteboard"
shape_mode = "Free"
color_idx = 0
brush_idx = 2
canvas = np.zeros((H, W, 3), dtype=np.uint8)
undo_stack = []

last_pos = None
fist_hold_start = 0
fist_active = False
fist_cleared = False
pinch_prev = False

game_balls = []
game_score = 0
game_lives = 5
robot_angle = 0
robot_grip = 0


def finger_states(lm):
    tips = [8, 12, 16, 20]
    pips = [6, 10, 14, 18]
    return [1 if lm[t].y < lm[p].y else 0 for t, p in zip(tips, pips)]


def pinch_dist(lm):
    return math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y)


def is_fist(lm):
    return sum(finger_states(lm)) == 0


def draw_ui(frame):
    cv2.rectangle(frame, (0, 0), (W, TOP_BAR_H), (30, 30, 30), -1)
    btn_w = W // len(MODES)
    mode_keys = ["T", "Y", "U", "I", "O"]
    for i, m in enumerate(MODES):
        x1 = i * btn_w
        x2 = (i + 1) * btn_w
        col = (0, 150, 200) if m == mode else (70, 70, 70)
        cv2.rectangle(frame, (x1 + 4, 6), (x2 - 4, TOP_BAR_H - 6), col, -1)
        cv2.putText(frame, f"[{mode_keys[i]}] {m}", (x1 + 15, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

    cv2.rectangle(frame, (0, TOP_BAR_H), (LEFT_BAR_W, H), (25, 25, 25), -1)
    cw = (LEFT_BAR_W - 20) // 2
    ch = 50
    for i, c in enumerate(COLORS):
        col = i % 2
        row = i // 2
        x1 = 8 + col * (cw + 4)
        y1 = TOP_BAR_H + 10 + row * (ch + 6)
        cv2.rectangle(frame, (x1, y1), (x1 + cw, y1 + ch), c, -1)
        border = 5 if i == color_idx else 1
        bcol = (0, 255, 0) if i == color_idx else (255, 255, 255)
        cv2.rectangle(frame, (x1, y1), (x1 + cw, y1 + ch), bcol, border)
        cv2.putText(frame, str(i + 1), (x1 + 5, y1 + 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    base_y = TOP_BAR_H + 10 + 5 * (ch + 6) + 15
    cv2.putText(frame, "SIZE (Q W E R)", (5, base_y - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
    for i, s in enumerate(BRUSH_SIZES):
        y1 = base_y + i * 42
        col = (0, 200, 255) if i == brush_idx else (70, 70, 70)
        cv2.rectangle(frame, (10, y1), (LEFT_BAR_W - 10, y1 + 36), col, -1)
        cv2.circle(frame, (LEFT_BAR_W // 2, y1 + 18), s + 2, (255, 255, 255), -1)

    if mode == "Shapes":
        sx = LEFT_BAR_W + 15
        shape_keys = ["", "H", "G", "F", "J"]
        for i, s in enumerate(SHAPES):
            x1 = sx + i * 145
            col = (0, 180, 0) if s == shape_mode else (70, 70, 70)
            cv2.rectangle(frame, (x1, TOP_BAR_H + 10), (x1 + 135, TOP_BAR_H + 60), col, -1)
            label = f"[{shape_keys[i]}] {s}" if shape_keys[i] else s
            cv2.putText(frame, label, (x1 + 10, TOP_BAR_H + 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.rectangle(frame, (0, H - 40), (W, H), (20, 20, 20), -1)
    info = f"Mode: {mode}  |  Color #{color_idx+1}  |  Fist clear (2s)"
    if mode == "Game":
        info = f"Score: {game_score}  Lives: {game_lives}"
    if mode == "Robotics":
        info = f"Angle: {robot_angle}  Grip: {'CLOSED' if robot_grip else 'OPEN'}"
    cv2.putText(frame, info, (LEFT_BAR_W + 15, H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1)


def do_whiteboard(ix, iy, states):
    global last_pos
    if states[0] == 1 and states[1] == 0 and states[2] == 0:
        if last_pos is None:
            undo_stack.append(canvas.copy())
            if len(undo_stack) > 15:
                undo_stack.pop(0)
            last_pos = (ix, iy)
        cv2.line(canvas, last_pos, (ix, iy), COLORS[color_idx], BRUSH_SIZES[brush_idx])
        last_pos = (ix, iy)
    else:
        last_pos = None


def do_shapes(ix, iy, states):
    global last_pos
    if states[0] == 1 and states[1] == 0:
        if last_pos is None:
            undo_stack.append(canvas.copy())
            if len(undo_stack) > 15:
                undo_stack.pop(0)
            last_pos = (ix, iy)
    elif last_pos is not None and states[0] == 0:
        x1, y1 = last_pos
        c = COLORS[color_idx]
        s = BRUSH_SIZES[brush_idx]
        if shape_mode == "Line":
            cv2.line(canvas, (x1, y1), (ix, iy), c, s)
        elif shape_mode == "Rect":
            cv2.rectangle(canvas, (x1, y1), (ix, iy), c, s)
        elif shape_mode == "Circle":
            r = int(math.hypot(ix - x1, iy - y1))
            cv2.circle(canvas, (x1, y1), r, c, s)
        elif shape_mode == "Star":
            r = int(math.hypot(ix - x1, iy - y1))
            pts = []
            for i in range(10):
                ang = math.pi / 2 + i * math.pi / 5
                rr = r if i % 2 == 0 else r // 2
                pts.append([int(x1 + rr * math.cos(ang)), int(y1 + rr * math.sin(ang))])
            cv2.polylines(canvas, [np.array(pts)], True, c, s)
        last_pos = None


def do_game(frame, ix, iy):
    global game_balls, game_score, game_lives
    if random.random() < 0.025:
        game_balls.append({
            "x": random.randint(LEFT_BAR_W + 50, W - 50), "y": -20,
            "vy": random.uniform(2.5, 6), "r": random.randint(18, 32),
            "color": random.choice([(0, 100, 255), (0, 255, 100), (255, 100, 100), (200, 200, 0)])
        })
    new_balls = []
    for b in game_balls:
        b["y"] += b["vy"]
        if math.hypot(b["x"] - ix, b["y"] - iy) < b["r"] + 30:
            game_score += 1
            continue
        if b["y"] > H:
            game_lives -= 1
            continue
        new_balls.append(b)
    game_balls = new_balls
    for b in game_balls:
        cv2.circle(frame, (int(b["x"]), int(b["y"])), b["r"], b["color"], -1)
        cv2.circle(frame, (int(b["x"]), int(b["y"])), b["r"], (255, 255, 255), 2)


def do_robotics(frame, lm):
    global robot_angle, robot_grip
    cx, cy = W // 2 + 100, H // 2
    robot_angle = int(math.degrees(math.atan2(lm[8].y - lm[0].y, lm[8].x - lm[0].x)))
    robot_grip = 1 if pinch_dist(lm) < 0.08 else 0
    cv2.circle(frame, (cx, cy), 30, (100, 100, 100), -1)
    cv2.circle(frame, (cx, cy), 30, (255, 255, 255), 2)
    ex = int(cx + 150 * math.cos(math.radians(robot_angle)))
    ey = int(cy + 150 * math.sin(math.radians(robot_angle)))
    cv2.line(frame, (cx, cy), (ex, ey), (0, 200, 255), 12)
    off = 25 if robot_grip else 10
    for sign in [-1, 1]:
        gx = int(ex + off * math.cos(math.radians(robot_angle + 90 * sign)))
        gy = int(ey + off * math.sin(math.radians(robot_angle + 90 * sign)))
        cv2.line(frame, (ex, ey), (gx, gy), (0, 255, 255), 6)


def do_mouse(ix, iy, lm):
    global pinch_prev
    sw, sh = pyautogui.size()
    pyautogui.moveTo(int(ix / W * sw), int(iy / H * sh), duration=0.03)
    pinch = pinch_dist(lm) < 0.08
    if pinch and not pinch_prev:
        pyautogui.click()
    pinch_prev = pinch


prev_time = time.time()
fps = 0

while True:
    ret, frame = cap.read()
    if not ret:
        time.sleep(0.05)
        continue
    frame = cv2.flip(frame, 1)
    frame = cv2.resize(frame, (W, H))
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = hands.process(rgb)

    ix, iy = -1, -1
    lm = None
    states = [0, 0, 0, 0]

    if results.multi_hand_landmarks:
        hl = results.multi_hand_landmarks[0]
        lm = hl.landmark
        ix = int(lm[8].x * W)
        iy = int(lm[8].y * H)
        states = finger_states(lm)
        mp_draw.draw_landmarks(frame, hl, mp_hands.HAND_CONNECTIONS,
                               mp_draw.DrawingSpec(color=(0, 255, 0), thickness=2),
                               mp_draw.DrawingSpec(color=(255, 255, 255), thickness=2))

    # Mode actions
    if mode == "Whiteboard" and lm:
        do_whiteboard(ix, iy, states)
    elif mode == "Shapes" and lm:
        do_shapes(ix, iy, states)
    elif mode == "Game":
        if ix > LEFT_BAR_W and lm:
            do_game(frame, ix, iy)
        canvas = np.zeros_like(canvas)
    elif mode == "Robotics" and lm:
        do_robotics(frame, lm)
        canvas = np.zeros_like(canvas)
    elif mode == "Mouse" and lm:
        do_mouse(ix, iy, lm)
        canvas = np.zeros_like(canvas)

    # Fist clear (2 sec hold) — FIXED: only clears once per fist hold
    if lm and is_fist(lm) and mode in ("Whiteboard", "Shapes"):
        if not fist_active:
            fist_active = True
            fist_hold_start = time.time()
            fist_cleared = False
        elif not fist_cleared and time.time() - fist_hold_start > 2.0:
            undo_stack.append(canvas.copy())
            if len(undo_stack) > 15:
                undo_stack.pop(0)
            canvas = np.zeros_like(canvas)
            fist_cleared = True
            print("Canvas cleared!")
        # progress bar
        if not fist_cleared:
            prog = min(1.0, (time.time() - fist_hold_start) / 2.0)
            cv2.rectangle(frame, (W // 2 - 150, 100), (W // 2 + 150, 130), (50, 50, 50), -1)
            cv2.rectangle(frame, (W // 2 - 150, 100),
                          (W // 2 - 150 + int(300 * prog), 130), (0, 255, 0), -1)
            cv2.putText(frame, "FIST - keep closed...", (W // 2 - 140, 122),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    else:
        fist_active = False
        fist_cleared = False

    # Overlay
    gray = cv2.cvtColor(canvas, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    mask_inv = cv2.bitwise_not(mask)
    frame_bg = cv2.bitwise_and(frame, frame, mask=mask_inv)
    canvas_fg = cv2.bitwise_and(canvas, canvas, mask=mask)
    final = cv2.add(frame_bg, canvas_fg)
    draw_ui(final)

    now = time.time()
    fps = 0.9 * fps + 0.1 * (1 / max(now - prev_time, 1e-5))
    prev_time = now
    cv2.putText(final, f"FPS {int(fps)}", (W - 110, H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (150, 150, 150), 1)

    cv2.imshow("Air Canvas Dashboard", final)

    key = cv2.waitKey(1) & 0xFF
    if key == 27:
        break
    elif key == ord('1'):
        color_idx = 0
    elif key == ord('2'):
        color_idx = 1
    elif key == ord('3'):
        color_idx = 2
    elif key == ord('4'):
        color_idx = 3
    elif key == ord('5'):
        color_idx = 4
    elif key == ord('6'):
        color_idx = 5
    elif key == ord('7'):
        color_idx = 6
    elif key == ord('8'):
        color_idx = 7
    elif key == ord('9'):
        color_idx = 8
    elif key == ord('q'):
        brush_idx = 0
    elif key == ord('w'):
        brush_idx = 1
    elif key == ord('e'):
        brush_idx = 2
    elif key == ord('r'):
        brush_idx = 3
    elif key == ord('t'):
        mode = "Whiteboard"
    elif key == ord('y'):
        mode = "Shapes"
    elif key == ord('u'):
        mode = "Game"
        game_score = 0
        game_lives = 5
    elif key == ord('i'):
        mode = "Robotics"
    elif key == ord('o'):
        mode = "Mouse"
    elif key == ord('f'):
        shape_mode = "Circle"
    elif key == ord('g'):
        shape_mode = "Rect"
    elif key == ord('h'):
        shape_mode = "Line"
    elif key == ord('j'):
        shape_mode = "Star"
    elif key == ord('c'):
        canvas = np.zeros_like(canvas)
        print("Cleared")
    elif key == ord('z'):
        if undo_stack:
            canvas = undo_stack.pop()
    elif key == ord('s'):
        fn = f"drawing_{int(time.time())}.png"
        cv2.imwrite(fn, canvas)
        print(f"Saved: {fn}")

cap.release()
cv2.destroyAllWindows()