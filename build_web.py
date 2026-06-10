#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modular-Typo 조립 웹 빌더.

원리(검증 완료):
  - alphabet_structure/web project-NN.svg = 글자 한 개의 '조립 구조도'.
    각 색 도형이 한 슬롯(어느 자리에 어떤 종류의 획이 들어갈지)을 정의한다.
  - by_stroke/<획종류>/*.svg = 그 색(=획 종류)에 해당하는 실제 획.
    각 파일은 [검정 텍스처 아트] + [색 등록도형(registration shape)]으로 구성.
  - 구조도의 색 도형과, 같은 색 획 파일 안의 색 도형은 *동일한 모양*이며
    오직 '닮음변환(평행이동+회전+균등배율)'만 다르다 → 비율(가로:세로) 100% 보존.
  - 따라서 [획의 색도형 → 슬롯의 색도형] 으로 가는 닮음변환을 풀어
    그 변환을 획 SVG 전체(검정 아트 포함)에 적용하면 정확히 들어맞는다.

색상 코드는 정확히 일치해야만 매칭한다(눈대중 금지).
"""
import re, glob, os, json, math

ROOT = os.path.dirname(os.path.abspath(__file__))
STRUCT_DIR = os.path.join(ROOT, "alphabet_structure")
STROKE_DIR = os.path.join(ROOT, "by_stroke")
OUT = os.path.join(ROOT, "assemble.html")

# ── 색상 정규화 ──────────────────────────────────────────────
def norm_color(c):
    if c is None:
        return None
    c = c.strip().lower()
    if c == "red":
        return "red"                      # 작은점 등록도형(ellipse fill="red")
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        return "#" + h
    return c

# 색상 → 획종류(폴더) 매핑은 by_stroke 폴더를 스캔해서 자동 구성한다.

# ── 좌표 추출 ────────────────────────────────────────────────
NUM = re.compile(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?')

def parse_polygon_points(s):
    nums = [float(x) for x in NUM.findall(s)]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]

def parse_path_points(d):
    """path d= 의 모든 좌표를 절대좌표 점열로 환원(명령어 무시, 상대/절대 누적)."""
    pts = []
    cur = [0.0, 0.0]
    start = [0.0, 0.0]
    i = 0
    tokens = re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', d)
    cmd = None
    def readf():
        nonlocal i
        v = float(tokens[i]); i += 1; return v
    while i < len(tokens):
        t = tokens[i]
        if re.match(r'[A-Za-z]', t):
            cmd = t; i += 1
            if cmd in 'Zz':
                cur = start[:]; pts.append(tuple(cur)); continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == 'M':
            x = readf(); y = readf()
            cur = [cur[0] + x, cur[1] + y] if rel else [x, y]
            start = cur[:]; pts.append(tuple(cur)); cmd = 'l' if rel else 'L'
        elif c == 'L':
            x = readf(); y = readf()
            cur = [cur[0] + x, cur[1] + y] if rel else [x, y]; pts.append(tuple(cur))
        elif c == 'H':
            x = readf(); cur = [cur[0] + x, cur[1]] if rel else [x, cur[1]]; pts.append(tuple(cur))
        elif c == 'V':
            y = readf(); cur = [cur[0], cur[1] + y] if rel else [cur[0], y]; pts.append(tuple(cur))
        elif c == 'C':
            x1 = readf(); y1 = readf(); x2 = readf(); y2 = readf(); x = readf(); y = readf()
            base = cur if rel else [0, 0]
            for (px, py) in [(x1, y1), (x2, y2), (x, y)]:
                pts.append((base[0] + px, base[1] + py))
            cur = [base[0] + x, base[1] + y]
        elif c == 'S' or c == 'Q':
            x1 = readf(); y1 = readf(); x = readf(); y = readf()
            base = cur if rel else [0, 0]
            pts.append((base[0] + x1, base[1] + y1)); pts.append((base[0] + x, base[1] + y))
            cur = [base[0] + x, base[1] + y]
        elif c == 'T':
            x = readf(); y = readf()
            cur = [cur[0] + x, cur[1] + y] if rel else [x, y]; pts.append(tuple(cur))
        elif c == 'A':
            readf(); readf(); readf(); readf(); readf(); x = readf(); y = readf()
            cur = [cur[0] + x, cur[1] + y] if rel else [x, y]; pts.append(tuple(cur))
        else:
            i += 1
    return pts

def apply_transform_to_point(p, transform):
    """structure ellipse 에 붙은 translate()/rotate() 적용."""
    x, y = p
    # 순차 적용: SVG transform 은 왼→오른 순서로 좌표에 곱해짐(오른쪽이 먼저).
    ops = re.findall(r'(translate|rotate|scale|matrix)\s*\(([^)]*)\)', transform or "")
    for name, args in reversed(ops):
        a = [float(v) for v in NUM.findall(args)]
        if name == 'translate':
            tx = a[0]; ty = a[1] if len(a) > 1 else 0
            x, y = x + tx, y + ty
        elif name == 'rotate':
            ang = math.radians(a[0])
            if len(a) >= 3:
                cx, cy = a[1], a[2]
                x, y = x - cx, y - cy
                x, y = x * math.cos(ang) - y * math.sin(ang), x * math.sin(ang) + y * math.cos(ang)
                x, y = x + cx, y + cy
            else:
                x, y = x * math.cos(ang) - y * math.sin(ang), x * math.sin(ang) + y * math.cos(ang)
        elif name == 'scale':
            sx = a[0]; sy = a[1] if len(a) > 1 else sx
            x, y = x * sx, y * sy
    return (x, y)

def ellipse_points(cx, cy, rx, ry, transform):
    pts = []
    for k in range(16):
        a = 2 * math.pi * k / 16
        pts.append(apply_transform_to_point((cx + rx * math.cos(a), cy + ry * math.sin(a)), transform))
    return pts

def css_class_fills(svg_text):
    """<style> 안의 `.clsName { fill: #xxx }` 매핑을 추출."""
    out = {}
    for sm in re.finditer(r'<style[^>]*>(.*?)</style>', svg_text, re.S):
        body = sm.group(1)
        for rm in re.finditer(r'\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}', body):
            cls = rm.group(1)
            fm = re.search(r'fill\s*:\s*([^;}\s]+)', rm.group(2))
            if fm:
                out[cls] = fm.group(1)
    return out

def fill_of(attrs, cls_map):
    """도형의 색상: 인라인 fill= 우선, 없으면 class= 로 CSS 조회."""
    fm = re.search(r'fill="([^"]+)"', attrs)
    if fm:
        return fm.group(1)
    cm = re.search(r'class="([^"]+)"', attrs)
    if cm:
        for c in cm.group(1).split():
            if c in cls_map:
                return cls_map[c]
    return None

def shape_points(kind, attrs):
    """도형의 대표 점열 반환(절대좌표)."""
    if kind == 'polygon':
        m = re.search(r'points="([^"]+)"', attrs)
        return parse_polygon_points(m.group(1)) if m else []
    if kind == 'path':
        m = re.search(r'\bd="([^"]+)"', attrs)
        return parse_path_points(m.group(1)) if m else []
    if kind == 'ellipse':
        def g(n):
            mm = re.search(n + r'="([^"]+)"', attrs); return float(mm.group(1)) if mm else 0.0
        tr = re.search(r'transform="([^"]+)"', attrs)
        return ellipse_points(g('cx'), g('cy'), g('rx'), g('ry'), tr.group(1) if tr else None)
    return []

# ── 등록도형 → 3점 정합 디스크립터(PCA 장축 + 볼록방향) ───────────
def anchors(points):
    """
    도형의 '주축(major axis)'을 PCA로 구해 정합 기준점 3개를 만든다.
      A,B = 주축 위 투영 극값(양 끝점)  → 두께/폭에 영향받지 않는 정확한 방향
      S   = 주축에서 가장 먼 점(곡선의 볼록 꼭짓점) → 좌우 반전(키랄성) 판별
    이렇게 하면:
      - 직선 바: 주축 = 장축 → 대각선 오차(각도 미세 틀어짐) 제거
      - 반원/곡선: 양끝(현) + 볼록방향까지 일치 → 거울상 뒤집힘 방지
    반환: dict(ax,ay,bx,by,sx,sy)
    """
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    sxx = sum((p[0] - cx) ** 2 for p in points)
    syy = sum((p[1] - cy) ** 2 for p in points)
    sxy = sum((p[0] - cx) * (p[1] - cy) for p in points)
    theta = 0.5 * math.atan2(2 * sxy, sxx - syy)   # 주성분 각도
    ux, uy = math.cos(theta), math.sin(theta)      # 장축 단위벡터
    proj = lambda p: (p[0] - cx) * ux + (p[1] - cy) * uy
    A = min(points, key=proj)
    B = max(points, key=proj)
    perp = lambda p: -(p[0] - cx) * uy + (p[1] - cy) * ux
    S = max(points, key=lambda p: abs(perp(p)))     # 볼록 꼭짓점(키랄)
    return {"ax": A[0], "ay": A[1], "bx": B[0], "by": B[1], "sx": S[0], "sy": S[1]}

# ── 구조도 파싱 ──────────────────────────────────────────────
SHAPE_RE = re.compile(r'<(polygon|path|ellipse)\b([^>]*?)/?>', re.S)

def slots_of_structure(path):
    t = open(path, encoding="utf-8").read()
    cls_map = css_class_fills(t)
    vb = re.search(r'viewBox="([^"]+)"', t).group(1)
    slots = []
    allpts = []                       # 코어 컬러블럭 전체 점(자간 기준 bbox)
    bar_thick = []                    # 직선바 두께(스트로크 두께 정규화용)
    STRAIGHT_C = {"#1ca300", "#ffce00", "#c7a7f9"}
    GIYEOK = "#ff00ff"                # 기역자(ㄱ): 2개 polygon = 1획 → 합쳐서 1슬롯
    giyeok_pts = []
    for m in SHAPE_RE.finditer(t):
        kind, attrs = m.group(1), m.group(2)
        color = norm_color(fill_of(attrs, cls_map))
        pts = shape_points(kind, attrs)
        if not pts:
            continue
        allpts.extend(pts)
        if color == GIYEOK:           # 기역자 조각들은 모아서 나중에 한 슬롯으로
            giyeok_pts.extend(pts)
            continue
        slot = {"color": color}
        slot.update(anchors(pts))
        slots.append(slot)
        if color in STRAIGHT_C:        # 직선바의 수직(perp) 범위 = 실제 획 두께
            bar_thick.append(perp_extent(pts))
    if giyeok_pts:                     # 합친 기역자 = 1슬롯(ㄱ 전체로 정합)
        slot = {"color": GIYEOK}
        slot.update(anchors(giyeok_pts))
        slots.append(slot)
    xs = [p[0] for p in allpts]; ys = [p[1] for p in allpts]
    core = {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)} if allpts else None
    # 글자 대표 획두께: 직선바 두께(없으면 None → JS에서 전역 기본값 사용)
    thick = min(bar_thick) if bar_thick else None
    return vb, slots, core, thick

# 용접 제외 색: 큰반원1(파랑)은 90°스냅으로 독립 배치되며, 끝점을 용접하면
# 곡선이 옆 직선획(D의 연보라 세로)을 덮어버림 → 용접 대상에서 제외.
NO_WELD = {"#0086ff"}

def weld_vertices(slots, end_thr=26.0, seg_thr=18.0):
    """
    코어 구조상 서로 맞닿아야 할 획 끝점들을 정확히 붙인다.
      1) 끝점-끝점 용접: 가까운 끝점들을 한 점(평균)으로 모음(V·W·A·M·N 꼭짓점 등).
      2) 끝점-선분 용접: 한 획 끝점이 다른 획의 몸통 가까이면 그 선분 위로 투영(Y 같은 T자 접합).
    슬롯의 (ax,ay)/(bx,by) 를 직접 수정한다(이후 stroke 가 이 끝점에 맞춰 배치됨).
    큰반원1(NO_WELD)은 용접에서 제외(D 반원↔세로획 겹침 방지).
    """
    # 끝점 목록: (slotIndex, 'A'|'B'). 용접 제외 색은 끝점 자체를 넣지 않음.
    eps = []
    for i, s in enumerate(slots):
        if s.get('color') in NO_WELD:
            continue
        eps.append((i, 'A')); eps.append((i, 'B'))
    def get(ep):
        i, k = ep; s = slots[i]
        return (s['ax'], s['ay']) if k == 'A' else (s['bx'], s['by'])
    def setp(ep, x, y):
        i, k = ep; s = slots[i]
        if k == 'A': s['ax'], s['ay'] = x, y
        else:        s['bx'], s['by'] = x, y

    # 두 슬롯이 양 끝 모두 가까운 경우(=평행/겹침) 용접하면 한 선으로 붕괴됨 → 용접 금지.
    def collapses(i, j):
        si, sj = slots[i], slots[j]
        # i 의 양끝 ↔ j 의 양끝, 가장 가까운 대응으로 두 끝 모두 end_thr 이내면 붕괴
        a1 = (si['ax'], si['ay']); a2 = (si['bx'], si['by'])
        b1 = (sj['ax'], sj['ay']); b2 = (sj['bx'], sj['by'])
        d_straight = max(math.hypot(a1[0]-b1[0], a1[1]-b1[1]), math.hypot(a2[0]-b2[0], a2[1]-b2[1]))
        d_cross    = max(math.hypot(a1[0]-b2[0], a1[1]-b2[1]), math.hypot(a2[0]-b1[0], a2[1]-b1[1]))
        return min(d_straight, d_cross) <= end_thr

    # 1) 끝점 클러스터링(서로 다른 슬롯의 끝점만, end_thr 이내)
    parent = list(range(len(eps)))
    def find(a):
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    def union(a, b): parent[find(a)] = find(b)
    for a in range(len(eps)):
        for b in range(a + 1, len(eps)):
            if eps[a][0] == eps[b][0]:
                continue
            if collapses(eps[a][0], eps[b][0]):   # 평행/겹침 슬롯쌍은 용접 안 함(D 세로획↔반원)
                continue
            pa, pb = get(eps[a]), get(eps[b])
            if math.hypot(pa[0]-pb[0], pa[1]-pb[1]) <= end_thr:
                union(a, b)
    groups = {}
    for a in range(len(eps)):
        groups.setdefault(find(a), []).append(a)
    for members in groups.values():
        if len(members) < 2:
            continue
        # 서로 다른 슬롯이 2개 이상 모인 경우만 용접
        if len({eps[m][0] for m in members}) < 2:
            continue
        cx = sum(get(eps[m])[0] for m in members) / len(members)
        cy = sum(get(eps[m])[1] for m in members) / len(members)
        for m in members:
            setp(eps[m], cx, cy)

    # 2) 끝점-선분 용접(아직 안 붙은 끝점을 다른 획 몸통에 투영)
    for ep in eps:
        px, py = get(ep)
        best = None
        for j, s in enumerate(slots):
            if j == ep[0] or s.get('color') in NO_WELD:   # 큰반원1 몸통엔 투영 안 함
                continue
            ax, ay, bx, by = s['ax'], s['ay'], s['bx'], s['by']
            dx, dy = bx-ax, by-ay
            L2 = dx*dx + dy*dy
            if L2 == 0:
                continue
            t = ((px-ax)*dx + (py-ay)*dy) / L2
            t = max(0.0, min(1.0, t))
            qx, qy = ax + t*dx, ay + t*dy
            d = math.hypot(px-qx, py-qy)
            if d <= seg_thr and (best is None or d < best[0]):
                best = (d, qx, qy)
        if best:
            setp(ep, best[1], best[2])

def rotate_slot(s, deg):
    """슬롯(바)을 자기 중심 기준으로 deg 만큼 회전. SVG 좌표(y아래)에서
    +deg=시계, -deg=반시계. 끝점 A,B 와 볼록점 S 를 함께 회전."""
    rad = math.radians(deg)
    c, s_ = math.cos(rad), math.sin(rad)
    mx, my = (s['ax']+s['bx'])/2, (s['ay']+s['by'])/2
    def rot(x, y):
        dx, dy = x-mx, y-my
        return (mx + dx*c - dy*s_, my + dx*s_ + dy*c)
    s['ax'], s['ay'] = rot(s['ax'], s['ay'])
    s['bx'], s['by'] = rot(s['bx'], s['by'])
    if 'sx' in s:
        s['sx'], s['sy'] = rot(s['sx'], s['sy'])

def apply_letter_fix(letter, slots):
    """글자별 수동 보정.
    - F: 맨 위쪽 짧은직선(#ff97eb) 획을 반시계 3° 회전.
    - D: 큰반원1을 오른쪽으로 밀어 세로획과 겹침 방지.
    - J: 갈고리(#9500ff)를 회전·반사 없이 스케일만으로 배치(noRot)."""
    SHORT = "#ff97eb"   # 짧은직선
    if letter == "F":
        shorts = [s for s in slots if s['color'] == SHORT]
        if shorts:
            top = min(shorts, key=lambda s: (s['ay']+s['by'])/2)   # 가장 위 짧은직선
            rotate_slot(top, -3)
    elif letter == "D":
        # 큰반원1(파랑) 보울을 오른쪽으로 살짝 밀어 연보라 세로획과 겹치지 않게.
        arc = next((s for s in slots if s['color'] == "#0086ff"), None)
        if arc:
            dx = 14   # 세로획 두께(~9) + 여유
            for k in ('ax', 'bx', 'sx'):
                if k in arc:
                    arc[k] += dx
    elif letter == "J":
        # 갈고리(#9500ff)는 회전·기울기 없이 스케일만으로 배치
        for s in slots:
            if s['color'] == "#9500ff":
                s['noRot'] = True

SYMMETRIC_LETTERS = {"A", "V", "M", "W", "X"}   # 좌우대칭 글자

DIAG_COLORS = {"#1ca300", "#ffce00"}   # 대각1·대각2 (연보라는 절대 안 건드림)

def symmetrize(letter, slots):
    """대칭형 글자의 '대각1·2 짝'만 좌우대칭으로 맞춘다(연보라 등 나머지는 그대로).
    글자 세로 중심축 기준으로 대각 슬롯의 거울짝을 찾아 정확한 거울상으로 강제."""
    if letter not in SYMMETRIC_LETTERS or len(slots) < 2:
        return
    # 중심축 x = 모든 슬롯 끝점 x 의 평균(글자 전체 기준)
    xs = []
    for s in slots:
        xs += [s['ax'], s['bx']]
    cx = sum(xs) / len(xs)

    def endpoints_mirrored(a, b):
        """a 를 cx로 미러한 점집합과 b 의 끝점 거리(방향 무시 최소)."""
        amx = (2*cx-a['ax'], a['ay']); bmx = (2*cx-a['bx'], a['by'])
        bA = (b['ax'], b['ay']); bB = (b['bx'], b['by'])
        d1 = math.hypot(amx[0]-bA[0], amx[1]-bA[1]) + math.hypot(bmx[0]-bB[0], bmx[1]-bB[1])
        d2 = math.hypot(amx[0]-bB[0], amx[1]-bB[1]) + math.hypot(bmx[0]-bA[0], bmx[1]-bA[1])
        return min(d1, d2)

    used = set()
    for i in range(len(slots)):
        if i in used:
            continue
        si = slots[i]
        if si['color'] not in DIAG_COLORS:    # 대각1·2 만 대상(연보라 등 제외)
            continue
        # 거울짝(대각 색끼리) 찾기.
        best = None
        for j in range(len(slots)):
            if j == i or j in used or slots[j]['color'] not in DIAG_COLORS:
                continue
            d = endpoints_mirrored(si, slots[j])
            if best is None or d < best[0]:
                best = (d, j)
        if not best or best[0] > 36:
            continue
        j = best[1]; sj = slots[j]
        # 왼쪽 슬롯을 기준으로, 오른쪽을 '정확한 거울상'으로 강제(대칭 보장).
        li, ri = (si, sj) if (si['ax']+si['bx']) <= (sj['ax']+sj['bx']) else (sj, si)
        # ri 의 끝점이 li 미러의 어느 끝과 대응되는지 맞춰 설정
        lAm = (2*cx-li['ax'], li['ay']); lBm = (2*cx-li['bx'], li['by'])
        if (math.hypot(lAm[0]-ri['ax'], lAm[1]-ri['ay']) + math.hypot(lBm[0]-ri['bx'], lBm[1]-ri['by'])
            <= math.hypot(lAm[0]-ri['bx'], lAm[1]-ri['by']) + math.hypot(lBm[0]-ri['ax'], lBm[1]-ri['ay'])):
            ri['ax'], ri['ay'] = lAm; ri['bx'], ri['by'] = lBm
        else:
            ri['ax'], ri['ay'] = lBm; ri['bx'], ri['by'] = lAm
        if 'sx' in li and 'sx' in ri:
            ri['sx'], ri['sy'] = 2*cx-li['sx'], li['sy']
        used.add(i); used.add(j)

def perp_extent(points):
    """PCA 주축의 수직 방향 범위(=직선바의 두께)."""
    n = len(points)
    cx = sum(p[0] for p in points) / n
    cy = sum(p[1] for p in points) / n
    sxx = sum((p[0]-cx)**2 for p in points); syy = sum((p[1]-cy)**2 for p in points)
    sxy = sum((p[0]-cx)*(p[1]-cy) for p in points)
    th = 0.5*math.atan2(2*sxy, sxx-syy); ux, uy = math.cos(th), math.sin(th)
    perp = [-(p[0]-cx)*uy + (p[1]-cy)*ux for p in points]
    return max(perp) - min(perp)

# ── 획 파싱 ──────────────────────────────────────────────────
def stroke_data(path):
    t = open(path, encoding="utf-8").read()
    cls_map = css_class_fills(t)
    vb = re.search(r'viewBox="([^"]+)"', t).group(1)
    inner = re.search(r'<svg[^>]*>(.*)</svg>', t, re.S).group(1)
    # CSS 클래스 fill 을 인라인화(여러 획을 한 글자에 합칠 때 .cls-N 충돌 방지)
    inner = re.sub(r'<defs>.*?</defs>', '', inner, flags=re.S)
    def _inline_cls(mm):
        tag = mm.group(0)
        cm = re.search(r'class="([^"]+)"', tag)
        if not cm:
            return tag
        fill = None
        for c in cm.group(1).split():
            if c in cls_map:
                fill = cls_map[c]; break
        tag = re.sub(r'\s*class="[^"]+"', '', tag)
        if fill and 'fill=' not in tag:
            tag = tag[:-2] + f' fill="{fill}"' + tag[-2:] if tag.endswith('/>') else \
                  tag[:-1] + f' fill="{fill}">'
        return tag
    inner = re.sub(r'<(?:polygon|path|ellipse|rect|circle|line|g)\b[^>]*?/?>', _inline_cls, inner)
    # 색(등록) 도형 찾기: 색상이 정의된(검정/none 아닌) 첫 도형.
    # 기역자(#ff00ff)는 2개 polygon = 1획이므로 같은 색 조각을 모두 합쳐 정합.
    reg = None
    reg_color = None
    reg_pts = []
    for m in SHAPE_RE.finditer(t):
        kind, attrs = m.group(1), m.group(2)
        color = norm_color(fill_of(attrs, cls_map))
        if color is None or color in ("#000000", "black", "none"):
            continue
        pts = shape_points(kind, attrs)
        if not pts:
            continue
        if reg_color is None:
            reg_color = color
        if color == reg_color:
            reg_pts.extend(pts)
            if reg_color != "#ff00ff":   # 기역자만 여러 조각 합침, 나머진 첫 도형으로 충분
                break
    if reg_pts:
        reg = {"color": reg_color}
        reg.update(anchors(reg_pts))
        # 작은반원1·2: 그룹 내 파일마다 등록도형 방향이 제각각 → 표준 방향으로 정규화.
        # (등록도형 현을 수평·볼록을 위쪽으로 회전/반사. 텍스처 포함 전체를 <g>로 감싸 회전.)
        if reg_color in ("#00ffb0", "#ff9999"):
            inner, reg = normalize_orientation(inner, reg)
    return {"viewBox": vb, "inner": inner.strip(), "reg": reg, "cls_map": cls_map}

def normalize_orientation(inner, reg):
    """획(텍스처+등록도형)을 표준 방향으로 통째 회전/반사.
    기준: 등록도형의 현(A→B)이 수평(+x), 볼록(apex)이 +y(아래쪽, SVG기준) 향하도록.
    inner 전체를 <g transform="matrix(...)">로 감싸고 reg 좌표도 같은 변환 적용."""
    ax, ay, bx, by = reg['ax'], reg['ay'], reg['bx'], reg['by']
    sx, sy = reg['sx'], reg['sy']
    chord = math.hypot(bx-ax, by-ay) or 1
    ux, uy = (bx-ax)/chord, (by-ay)/chord            # 현 방향
    # 볼록 부호(현 왼쪽/오른쪽)
    side = -(sx-ax)*uy + (sy-ay)*ux
    sgn = 1.0 if side >= 0 else -1.0
    vx, vy = -uy*sgn, ux*sgn                          # 볼록쪽 수직축
    # 표준계: 새 x축=현(ux,uy), 새 y축=볼록(vx,vy). 이를 (1,0),(0,1)로 보내는 변환.
    # 월드→표준 회전행렬 R = [[ux,uy],[vx,vy]] (정규직교). 평행이동: A를 원점 근처로.
    # SVG matrix(a,b,c,d,e,f): x'=a x + c y + e
    a, b, c, d = ux, vx, uy, vy        # R^T 적용(행이 새 축)
    # 원점은 그대로 두고 회전만(위치는 어차피 배치 시 similarity가 다시 맞춤)
    e, f = 0.0, 0.0
    wrapped = f'<g transform="matrix({a} {b} {c} {d} {e} {f})">{inner}</g>'
    def apply(x, y):
        return (a*x + c*y + e, b*x + d*y + f)
    nax, nay = apply(ax, ay); nbx, nby = apply(bx, by); nsx, nsy = apply(sx, sy)
    nreg = dict(reg)
    nreg['ax'], nreg['ay'] = nax, nay
    nreg['bx'], nreg['by'] = nbx, nby
    nreg['sx'], nreg['sy'] = nsx, nsy
    return wrapped, nreg

# ── 메인 빌드 ────────────────────────────────────────────────
def build():
    # 1) 색상 → 획종류 폴더, 그 안의 획들
    # 제외 파일: 277/282 는 다른 파일보다 2~3배 깊은 반원이라 볼울 슬롯에 안 맞아 B를
    # 일그러뜨림 → 조립 후보에서 제외.
    EXCLUDE = {"Asset 277.svg", "Asset 282.svg"}
    strokes_by_color = {}   # color -> [strokeData,...]
    color_to_folder = {}
    for folder in sorted(os.listdir(STROKE_DIR)):
        fpath = os.path.join(STROKE_DIR, folder)
        if not os.path.isdir(fpath):
            continue
        for svg in sorted(glob.glob(os.path.join(fpath, "*.svg"))):
            if os.path.basename(svg) in EXCLUDE:
                continue
            sd = stroke_data(svg)
            sd["src"] = os.path.relpath(svg, ROOT)
            sd["emotion"] = os.path.basename(svg).split("__")[0]
            color = sd["reg"]["color"] if sd["reg"] else None
            strokes_by_color.setdefault(color, []).append(sd)
            color_to_folder[color] = folder

    # 2) 글자 구조도 (project-04..28 + 35 = A..Z)
    files = sorted(glob.glob(os.path.join(STRUCT_DIR, "web project-*.svg")),
                   key=lambda p: int(re.search(r'-(\d+)\.svg', p).group(1)))
    files = [f for f in files if os.path.getsize(f) < 3000]
    # 파일번호 → 글자 매핑(사용자 확정): 04~24=A~U, 35=V, 25~28=W,X,Y,Z
    NUM_TO_LETTER = {}
    for i, n in enumerate(range(4, 25)):      # 04..24 → A..U
        NUM_TO_LETTER[n] = "ABCDEFGHIJKLMNOPQRSTU"[i]
    NUM_TO_LETTER[35] = "V"
    NUM_TO_LETTER[25] = "W"
    NUM_TO_LETTER[26] = "X"
    NUM_TO_LETTER[27] = "Y"
    NUM_TO_LETTER[28] = "Z"
    letters = []
    for f in files:
        num = int(re.search(r'-(\d+)\.svg', f).group(1))
        letter = NUM_TO_LETTER.get(num, f"#{num}")
        vb, slots, core, thick = slots_of_structure(f)
        weld_vertices(slots)     # 코어 구조상 맞닿아야 할 획 끝점들을 정확히 붙임
        symmetrize(letter, slots)  # 대각1·2 좌우대칭(용접 후 적용 → 용접이 깨뜨린 대칭 복원)
        apply_letter_fix(letter, slots)   # 글자별 수동 보정(F 짧은직선 등)
        letters.append({
            "letter": letter,
            "file": os.path.relpath(f, ROOT),
            "viewBox": vb,
            "slots": slots,
            "core": core,            # 코어 컬러블럭 bbox(자간 기준)
            "thick": thick,          # 직선바 두께(획두께 정규화용; 곡선전용 글자는 None)
        })

    # 호환 그룹(슬롯 색 → 그 슬롯에 쓸 수 있는 획 색들). 혼용 없음.
    #   대각1(초록) 슬롯: 초록만.  대각2(노랑) 슬롯: 노랑만.  연보라 슬롯: 연보라만.
    DIAG1, DIAG2, LONG = "#1ca300", "#ffce00", "#c7a7f9"
    substitutes = {
        DIAG1: [DIAG1],
        DIAG2: [DIAG2],
        LONG:  [LONG],
    }
    # 90°스냅 적용 대상(직선바 색 전체)
    straight_colors = [DIAG1, DIAG2, LONG]
    # 곡선이지만 90°단위로만 회전시킬 색(큰반원1 = 파랑, D·U 등)
    snap90_colors = ["#0086ff"]

    data = {
        "letters": letters,
        "strokesByColor": strokes_by_color,
        "colorToFolder": color_to_folder,
        "substitutes": substitutes,
        "straightColors": straight_colors,
        "snap90Colors": snap90_colors,
    }
    write_html(data)
    # 검증 리포트
    print("=== 빌드 요약 ===")
    print(f"글자 {len(letters)}개")
    miss = []
    for L in letters:
        for s in L["slots"]:
            if s["color"] not in strokes_by_color:
                miss.append((L["letter"], s["color"]))
    if miss:
        print("⚠ 매칭 안 되는 슬롯 색상:", miss)
    else:
        print("✓ 모든 슬롯 색상이 by_stroke 폴더와 정확히 매칭됨")
    for c, folder in sorted(color_to_folder.items(), key=lambda x: str(x[1])):
        print(f"  {str(c):>8}  →  {str(folder):<10}  ({len(strokes_by_color[c])}개 후보)")
    if None in strokes_by_color:
        print("⚠ 색 등록도형을 못 찾은 획:", len(strokes_by_color[None]), "개")
    print(f"\n출력: {OUT}")

def write_html(data):
    payload = json.dumps(data, ensure_ascii=False)
    tpl = HTML_TEMPLATE.replace("/*__DATA__*/", payload)
    open(OUT, "w", encoding="utf-8").write(tpl)

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Modular Typo — 감정 조립</title>
<style>
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#fff;overflow:hidden;
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif;
    -webkit-user-select:none;user-select:none}   /* 화면 텍스트 드래그 선택 방지 */
  #txt{-webkit-user-select:text;user-select:text}  /* 입력칸은 선택 가능 */
  /* 글자: 창 전체. 내용량에 따라 유동 — 적으면 중앙, 가득차면 가장자리까지(좌상단 시작) */
  #word{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;overflow:hidden}
  .line{position:relative}
  .glyph{position:absolute;top:0}
  .glyph svg{display:block;overflow:visible}
  /* 화면 표시: 컬러 블럭 포함 모든 도형을 검정으로 (매칭 로직은 데이터 단계에서 끝나 영향 없음) */
  .glyph svg *{fill:#000 !important;stroke:none !important}
  .glyph svg [fill="none"]{fill:none !important}
  /* 글자 사이에 끼는 기본폰트 문자(숫자·기호) */
  .plain{display:inline-block;color:#000;font-weight:300;line-height:1;white-space:pre}
  /* ── 이동 가능한 frosted-glass 팝업 (공통) ── */
  .pop{position:fixed;z-index:7;border:none;border-radius:14px;
    background:rgba(86,150,225,.4);                /* 하늘색, 살짝 진하게(투명도 .4 유지) */
    backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
    box-shadow:0 6px 24px rgba(40,80,140,.16);color:#fff;overflow:hidden;
    -webkit-user-select:none;user-select:none}
  /* 상단 바: 이름 + 최소화 버튼. 아래 컨텐츠와 얇은 구분선 */
  .pop .bar{display:flex;align-items:center;justify-content:space-between;height:22px;
    padding:0 6px 0 10px;cursor:move;border-bottom:1px solid rgba(255,255,255,.28)}
  .pop .pname{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:rgba(255,255,255,.75);
    visibility:hidden;pointer-events:none}      /* 펼침 시 숨김, 최소화 시 표시 */
  .pop.collapsed .pname{visibility:visible}
  .pop .min, #emos .min{width:22px;height:22px;border:none;background:none;color:rgba(255,255,255,.85);
    font-size:24px;line-height:1;cursor:pointer;padding:0;margin-top:-3px;
    display:flex;align-items:center;justify-content:center}
  .pop .min:hover{color:#fff}
  .pop .body{padding:7px 10px 9px}
  .pop.collapsed .body, #emos.collapsed .body, #panel.collapsed .body{display:none !important}
  .pop.collapsed .bar{border-bottom:none}
  .pop.collapsed{width:auto !important}
  /* 토글 스위치(조금 크게) */
  #emos{left:24px;bottom:24px}
  #emos .body{display:flex;flex-direction:column;gap:9px}
  #emos button{display:flex;align-items:center;gap:9px;border:none;background:none;
    cursor:pointer;padding:0;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#fff}
  #emos .sw{position:relative;width:26px;height:15px;border-radius:8px;background:#fff;
    transition:background .15s,opacity .15s;flex:none}
  #emos .sw::after{content:"";position:absolute;top:2px;left:2px;width:11px;height:11px;
    border-radius:50%;background:#3f7fc8;transition:transform .15s}
  #emos button.off{color:rgba(255,255,255,.45)}
  #emos button.off .sw{background:rgba(255,255,255,.35)}
  #emos button.off .sw::after{transform:translateX(0)}
  #emos button:not(.off) .sw::after{transform:translateX(11px)}
  #emos #colorBtn{margin-bottom:8px}
  /* 텍스트 입력 팝업 */
  #panel{right:24px;bottom:24px;width:min(34vw,300px)}
  #txt{box-sizing:border-box;width:100%;height:108px;padding:0;
    border:none;outline:none;background:transparent;
    color:#fff;font-size:12px;line-height:1.5;letter-spacing:.06em;text-transform:uppercase;
    caret-color:#fff;resize:none;overflow:auto;font-family:inherit;-webkit-user-select:text;user-select:text}
  #txt::placeholder{color:rgba(255,255,255,.5)}
  /* 텍스트 창 크기조절 핸들(우측 하단) */
  #panel{position:fixed}
  #resizeHandle{position:absolute;right:3px;bottom:3px;width:14px;height:14px;cursor:nwse-resize;z-index:2;
    color:rgba(255,255,255,.7)}
  #resizeHandle svg{display:block}
  #panel.collapsed #resizeHandle{display:none}
</style>
</head>
<body>
<div id="word"></div>
<div id="emos" class="pop"><div class="bar"><span class="pname">toggles</span><button class="min" title="최소화">▴</button></div><div class="body"></div></div>
<div id="panel" class="pop"><div class="bar"><span class="pname">text</span><button class="min" title="최소화">▴</button></div><div class="body"><textarea id="txt" autocomplete="off" spellcheck="false">LOVE</textarea></div><div id="resizeHandle" title="크기조절"><svg width="14" height="14" viewBox="0 0 14 14"><path d="M13 4 L4 13 M13 9 L9 13" stroke="currentColor" stroke-width="1.3" fill="none"/></svg></div></div>

<script>
const DATA = /*__DATA__*/;
const EMO = ["anger","fear","happiness","love","lust","sadness"];
// 표시 라벨(lust→desire). 내부 키는 파일명대로 lust 유지.
const EMO_LABEL = {anger:"anger",fear:"fear",happiness:"happiness",love:"love",lust:"desire",sadness:"sadness"};
// 컬러 모드 색(감정별). desire(lust)=블랙.
const EMO_COLOR = {anger:"#d1ff3d",love:"#ffa3ff",fear:"#ff0800",happiness:"#007aff",sadness:"#a170ff",lust:"#000000"};
let colorMode = false;   // 컬러 토글 상태
const ACTIVE = new Set(EMO);   // 켜진 감정(기본 전체)

function rint(n){ return Math.floor(Math.random()*n); }

// 슬롯 색 → 후보 풀(단방향 substitutes). 대각1·2 슬롯은 직선3종, 연보라 슬롯은 연보라만.
const POOL = {};
(function(){
  const sub = DATA.substitutes || {};
  for(const c of Object.keys(DATA.strokesByColor)){
    const allow = sub[c] || [c];
    POOL[c] = allow.flatMap(k => DATA.strokesByColor[k] || []);
  }
})();

// 직선바 색(대각1·대각2·긴직선)
const STRAIGHT = new Set(DATA.straightColors||[]);
// 곡선이지만 90°단위로만 회전(큰반원1 파랑 등)
const SNAP90 = new Set(DATA.snap90Colors||[]);
// 연보라(긴직선): 무조건 90°단위 회전만. 슬롯이 90°배수에서 이 각도 이내일 때 스냅
// (W의 사선 78°은 멀어서 제외 → 사선 유지)
const LONG90 = new Set(["#c7a7f9"]);
const LONG90_DEG = 8;
// 기역자(ㄱ): 회전·반사 절대 금지, 균등 스케일+이동만(원본 방향 그대로)
const NOROT = new Set(["#ff00ff"]);

// 정합 프레임 만들기.
//  straight=true(직선바): 바는 대칭이라 볼록방향(apex)이 노이즈 → 무시하고
//    축을 결정적으로 정규화(180° 모호성 제거 + 고정 수직축). 그래야 어떤 직선획을
//    골라도 같은 프레임 → 대각 슬롯에 매번 같은 각도로 정확히 들어감.
//  straight=false(곡선/반원): apex 볼록방향으로 좌우(키랄) 결정.
function frame(r, straight){
  let ax=r.ax, ay=r.ay;
  let dx=r.bx-ax, dy=r.by-ay;
  const len=Math.hypot(dx,dy)||1;
  let ux=dx/len, uy=dy/len;                    // x축(장축)
  if(straight){
    // 축 방향 결정적 정규화: 항상 한쪽 반평면을 보게(180° 모호성 제거)
    if(uy<-1e-9 || (Math.abs(uy)<=1e-9 && ux<0)){ ux=-ux; uy=-uy; ax=r.bx; ay=r.by; }
    // 수직축 고정(apex 무시) — 바는 대칭이라 어느 쪽이든 결과 동일
    const vx=-uy, vy=ux;
    return {ax,ay,ux,uy,vx,vy,len};
  }
  // 곡선: 볼록 꼭짓점 S 쪽으로 수직축(키랄 결정)
  const side = -(r.sx-ax)*uy + (r.sy-ay)*ux;
  const sgn = side>=0 ? 1 : -1;
  const vx=-uy*sgn, vy=ux*sgn;
  return {ax,ay,ux,uy,vx,vy,len};
}

// 직선바 중심·축·길이 추출. 바는 대칭이라 축 1개로 충분.
function barAxis(r){
  const mx=(r.ax+r.bx)/2, my=(r.ay+r.by)/2;
  let dx=r.bx-r.ax, dy=r.by-r.ay;
  const len=Math.hypot(dx,dy)||1;
  return {mx,my,len,ang:Math.atan2(dy,dx)};
}

// 변환행렬: src → dst (회전+균등배율, 필요시 반사). 비율 보존.
function similarity(src, dst){
  // 기역자(ㄱ) 또는 슬롯에 noRot 지정(J의 갈고리 등): 회전·반사 금지 → 스케일+이동만.
  if(NOROT.has(dst.color) || dst.noRot){
    const Sd=Math.hypot(src.bx-src.ax, src.by-src.ay)||1;   // 소스 reg 크기(축길이)
    const Dd=Math.hypot(dst.bx-dst.ax, dst.by-dst.ay)||1;   // 슬롯 크기
    const s=Dd/Sd;                                           // 균등배율
    const smx=(src.ax+src.bx)/2, smy=(src.ay+src.by)/2;
    const dmx=(dst.ax+dst.bx)/2, dmy=(dst.ay+dst.by)/2;
    return [s, 0, 0, s, dmx - s*smx, dmy - s*smy];           // 회전 0, 반사 없음
  }
  const sStraight=STRAIGHT.has(src.color), dStraight=STRAIGHT.has(dst.color);
  if(sStraight && dStraight){
    // 직선바 ↔ 직선바.
    const S=barAxis(src), D=barAxis(dst);
    const s=D.len/S.len;
    // 연보라(긴직선): 무조건 90°단위 회전만. 단 슬롯이 90°배수에 가까울 때만 스냅
    // (W의 의도된 사선 78°은 멀어서 제외 → 원래 각도 유지).
    if(LONG90.has(dst.color)){
      const step=Math.PI/2;
      const dsnap=Math.round(D.ang/step)*step;
      if(Math.abs(((D.ang-dsnap+Math.PI)%(2*Math.PI))-Math.PI) <= LONG90_DEG*Math.PI/180){
        const ssnap=Math.round(S.ang/step)*step;        // 소스도 90°로 정렬
        const rot=dsnap - ssnap;                         // 정확히 90°배수
        const a=Math.cos(rot)*s, b=Math.sin(rot)*s, c=-Math.sin(rot)*s, d=Math.cos(rot)*s;
        const e=D.mx - (a*S.mx + c*S.my);
        const f=D.my - (b*S.mx + d*S.my);
        return [a,b,c,d,e,f];
      }
    }
    // 기본(직선바, W 사선 등): 바는 180° 대칭이라 슬롯 축에 회전 작은 쪽으로 정렬.
    let rot = D.ang - S.ang;
    rot = ((rot % Math.PI) + Math.PI*1.5) % Math.PI - Math.PI/2;
    const a=Math.cos(rot)*s, b=Math.sin(rot)*s, c=-Math.sin(rot)*s, d=Math.cos(rot)*s;
    const e=D.mx - (a*S.mx + c*S.my);
    const f=D.my - (b*S.mx + d*S.my);
    return [a,b,c,d,e,f];
  }
  // 큰반원1 등: '원본 파일을 90°단위로만 회전'해서 배치(반사는 허용 → 방향 맞춤).
  // 소스·슬롯 프레임 축을 둘 다 90°배수로 스냅 → 둘 사이 회전은 정확히 90°배수가 되고,
  // 볼록방향(키랄) 부호는 그대로 살려 곡선이 올바른 쪽으로 열리게(필요시 반사).
  if(SNAP90.has(dst.color)){
    const S=frame(src, false), D=frame(dst, false);
    const snapU=(fr)=>{
      const ang=Math.atan2(fr.uy,fr.ux);
      const sn=Math.round(ang/(Math.PI/2))*(Math.PI/2);
      const cu=Math.cos(sn), su=Math.sin(sn);
      const sgn=(fr.vx*-su + fr.vy*cu)>=0?1:-1;   // 기존 v축 부호(볼록방향) 유지
      fr.ux=cu; fr.uy=su; fr.vx=-su*sgn; fr.vy=cu*sgn;
    };
    snapU(S); snapU(D);
    const s=D.len/S.len;
    const a=s*(D.ux*S.ux + D.vx*S.vx);
    const c=s*(D.ux*S.uy + D.vx*S.vy);
    const b=s*(D.uy*S.ux + D.vy*S.vx);
    const d=s*(D.uy*S.uy + D.vy*S.vy);
    const e=D.ax - (a*S.ax + c*S.ay);
    const f=D.ay - (b*S.ax + d*S.ay);
    return [a,b,c,d,e,f];
  }
  // 그 외(곡선 포함): 3점 프레임 정합
  const S=frame(src, sStraight), D=frame(dst, dStraight);
  const s=D.len/S.len;                          // 균등배율(비율 보존)
  const a = s*(D.ux*S.ux + D.vx*S.vx);
  const c = s*(D.ux*S.uy + D.vx*S.vy);
  const b = s*(D.uy*S.ux + D.vy*S.vx);
  const d = s*(D.uy*S.uy + D.vy*S.vy);
  const e = D.ax - (a*S.ax + c*S.ay);
  const f = D.ay - (b*S.ax + d*S.ay);
  return [a,b,c,d,e,f];
}

// 글자별 획 선택을 기억(입력 중 이미 만들어진 글자는 모양 유지, 재조립 때만 새로 뽑음)
let PICKS = {};   // key -> [strokeIndex,...]
function shuffleAll(){ PICKS={}; }

const SYMMETRIC = new Set(["A","V","M","W","X"]);   // 대칭형 글자(빌드와 동일)

// 글자 SVG 생성. 검정 텍스처가 viewBox 밖으로 나가도 자르지 않음(overflow:visible).
function buildGlyphSVG(L, opt){
  const vb=L.viewBox.split(/\s+/).map(Number);
  const svgns="http://www.w3.org/2000/svg";
  const svg=document.createElementNS(svgns,"svg");
  svg.setAttribute("viewBox", L.viewBox);
  svg.style.overflow="visible";
  const key=opt.seedKey;
  const picks = PICKS[key] || (PICKS[key]=[]);

  // 대칭형 글자: 대각1(초록)을 먼저 배치하고, 대각2(노랑)는 초록 배치각의 −부호로 강제
  // → 좌우 회전각이 정확히 ±대칭. (초록 슬롯을 노랑보다 먼저 처리하도록 정렬)
  const sym = SYMMETRIC.has(L.letter);
  let green1Ang = null;
  let order = L.slots.map((s,i)=>i);
  if(sym){   // 초록(#1ca300)을 노랑(#ffce00)보다 먼저
    order.sort((i,j)=>{
      const rank=c=>c==="#1ca300"?0:(c==="#ffce00"?1:2);
      return rank(L.slots[i].color)-rank(L.slots[j].color);
    });
  }

  for(const i of order){
    const slot = L.slots[i];
    let pool = POOL[slot.color] || DATA.strokesByColor[slot.color] || [];
    // 감정 토글: 켜진 감정의 획만 사용(해당 감정에 그 획이 없으면 전체로 폴백)
    if(ACTIVE.size && ACTIVE.size<EMO.length){
      const f = pool.filter(s=>ACTIVE.has(s.emotion));
      if(f.length) pool = f;
    }
    if(!pool.length) continue;
    // 기억된 선택(src)이 현재 풀에 있으면 유지, 아니면 새로 뽑음
    let idx = pool.findIndex(s=>s.src===picks[i]);
    if(idx<0){ idx=rint(pool.length); picks[i]=pool[idx].src; }
    const stroke = pool[idx];
    if(!stroke.reg) continue;
    let M = similarity(stroke.reg, slot);
    // 대각2(노랑)는 대각1(초록) 배치각의 부호 반대(−θ)로 강제 → 좌우 회전 ±대칭.
    // (자기 stroke·중심·길이는 유지, 회전각만 초록의 거울각으로 교체)
    if(sym && slot.color==="#ffce00" && green1Ang!==null){
      const Sb=barAxis(stroke.reg), Db=barAxis(slot);
      const sc=Db.len/Sb.len;
      // 목표 배치각 = -초록배치각 (180° 등가 중 슬롯에 가까운 쪽 선택)
      let target=-green1Ang;
      // 슬롯 방향과 가장 가까운 등가각으로
      while(target-Db.ang> Math.PI/2) target-=Math.PI;
      while(target-Db.ang<-Math.PI/2) target+=Math.PI;
      const rot=target - Sb.ang;
      const a=Math.cos(rot)*sc, b=Math.sin(rot)*sc, c=-Math.sin(rot)*sc, d=Math.cos(rot)*sc;
      M=[a,b,c,d, Db.mx-(a*Sb.mx+c*Sb.my), Db.my-(b*Sb.mx+d*Sb.my)];
    }
    const g=document.createElementNS(svgns,"g");
    g.setAttribute("transform", `matrix(${M.join(" ")})`);
    g.innerHTML = stroke.inner;   // 절대좌표이므로 그대로 삽입
    // 컬러 모드: 이 획을 감정 색으로 칠함(외곽선만 fill=none 인 도형은 제외)
    if(colorMode){
      const col=EMO_COLOR[stroke.emotion]||"#000";
      for(const el of g.querySelectorAll("*")){
        if(el.getAttribute("fill")==="none") continue;
        el.style.setProperty("fill", col, "important");
      }
    }
    svg.appendChild(g);
    // 초록 배치각(렌더된 바 방향) 기억 → 노랑 대칭에 사용
    if(sym && slot.color==="#1ca300"){
      const p0x=M[0]*stroke.reg.ax+M[2]*stroke.reg.ay+M[4];
      const p0y=M[1]*stroke.reg.ax+M[3]*stroke.reg.ay+M[5];
      const p1x=M[0]*stroke.reg.bx+M[2]*stroke.reg.by+M[4];
      const p1y=M[1]*stroke.reg.bx+M[3]*stroke.reg.by+M[5];
      green1Ang = Math.atan2(p1y-p0y, p1x-p0x);
    }
  }
  return {svg, vb};
}

const TRACK_RATIO = 0.18;   // 자간 = 글자높이 비례
const LETTER_SCALE = { S: 1.1, G: 1.4, R: 1.4 };   // S 10%, R·G 더 크게(코어가 길어 보정)

const LETTER_MAP = Object.fromEntries(DATA.letters.map(L=>[L.letter,L]));
// 글자별 베이스라인 추가 하강(cap 비례, +면 아래로). 확대로 위로 떠 보이는 R·G 보정.
const LETTER_DROP = { R: 0.12, G: 0.12 };

// 한 줄 레이아웃. keyBase = 전체 텍스트에서 이 줄이 시작하는 글로벌 인덱스
// (각 글자가 줄과 무관하게 고유 키를 갖도록 → 줄바꿈으로 같은 모양 반복되는 문제 방지).
function layoutLine(txt, cap, keyBase){
  keyBase = keyBase || 0;
  const track = cap*TRACK_RATIO;
  const items=[]; let penX=0, top0=Infinity, bot1=-Infinity;
  let cTop=Infinity, cBot=-Infinity;   // 코어(글자 골격) 기준 세로 범위(텍스처 제외)
  [...txt].forEach((ch, idx)=>{
    if(ch===" "){ penX += cap*0.55; return; }
    const gkey=(keyBase+idx)+ch;       // 글로벌 위치 + 글자 = 고유 키
    const L=LETTER_MAP[ch];
    if(L && L.core){
      const mul=LETTER_SCALE[ch]||1;
      const c=L.core, coreH=c.y1-c.y0;
      const s=(cap*mul)/coreH;
      const extra=cap*(mul-1);
      const drop=(LETTER_DROP[ch]||0)*cap;     // 글자별 베이스라인 추가 하강
      const baseTop = -c.y1*s + extra/2 + drop;
      const vbH=(+L.viewBox.split(/\s+/)[3]);
      items.push({type:"glyph", L, c, s, key: gkey, x: penX - c.x0*s, top: baseTop, vbH});
      top0=Math.min(top0, baseTop);
      bot1=Math.max(bot1, baseTop + vbH*s);
      // 코어 범위: baseTop 좌표계에서 코어는 c.y0..c.y1 → baseTop + c.y0*s .. baseTop + c.y1*s
      cTop=Math.min(cTop, baseTop + c.y0*s);
      cBot=Math.max(cBot, baseTop + c.y1*s);
      penX += (c.x1-c.x0)*s + track;
    } else {
      const fpx=cap*1.0;
      const w=fpx*0.62;
      items.push({type:"plain", ch, key:gkey, x:penX, fpx, top:-fpx});
      top0=Math.min(top0, -fpx);
      bot1=Math.max(bot1, 0);
      cTop=Math.min(cTop, -fpx); cBot=Math.max(cBot, 0);
      penX += w + track;
    }
  });
  if(cTop===Infinity){ cTop=0; cBot=cap; }
  return {items, width:Math.max(0,penX-track), top0, bot1, cTop, cBot};
}

let sizeFactor = 0.33;   // 글자 크기(휠 스크롤로 조절)
function sizeScale(){ return sizeFactor; }

// 한 줄을 폭 maxW 안에 들어가도록 단어 단위로 줄바꿈(긴 단어는 글자 단위로 강제 분리).
function wrapLine(txt, cap, maxW){
  if(layoutLine(txt, cap).width <= maxW) return [txt];
  const out=[]; const words=txt.split(/(\s+)/);   // 공백 보존하며 분리
  let cur="";
  const pushWordChars=(w)=>{   // 한 단어가 통째로 폭 초과 → 글자 단위로 쪼갬
    let chunk="";
    for(const ch of w){
      const t=chunk+ch;
      if(chunk && layoutLine(t, cap).width > maxW){ out.push(chunk); chunk=ch; }
      else chunk=t;
    }
    return chunk;   // 남은 부분(다음 줄 시작에 이어붙임)
  };
  for(const tok of words){
    if(tok==="") continue;
    const trial=cur+tok;
    if(cur && layoutLine(trial, cap).width > maxW){
      out.push(cur.replace(/\s+$/,"")); cur="";   // 줄 확정(뒤 공백 제거)
      if(/^\s+$/.test(tok)) continue;             // 줄머리 공백 버림
      cur=tok;
    } else {
      cur=trial;
    }
    // 단어 하나가 그 자체로 폭 초과면 글자단위로 강제 분리
    if(layoutLine(cur, cap).width > maxW && !/\s/.test(cur)){
      cur=pushWordChars(cur);
    }
  }
  if(cur.trim()!=="") out.push(cur.replace(/\s+$/,""));
  return out.length?out:[txt];
}

function render(){
  const raw=(document.getElementById("txt").value||"").toUpperCase();
  const word=document.getElementById("word");
  word.innerHTML="";
  const rawLines=raw.split("\n");
  if(!raw.trim() && rawLines.length<=1) return;

  // 가용 폭(자동 줄바꿈 기준). 세로는 넘쳐도 자동 축소하지 않음(슬라이더=글자 크기 그대로).
  const availW=innerWidth*0.94;
  // cap = 슬라이더 값 그대로(화면 넘쳐도 그대로 크게). 가로 폭 초과만 줄바꿈으로 처리.
  const cap=Math.max(8, Math.min(innerHeight*0.94, 360)*sizeScale());

  let lines=[];
  for(const t of rawLines){ lines = lines.concat(wrapLine(t, cap, availW)); }
  const lineGap=cap*0.45;
  // keyBase 누적: 각 줄이 전체에서 시작하는 글로벌 글자 위치(같은 글자도 위치마다 고유 키)
  let kb=0;
  const lays=lines.map(t=>{ const l=layoutLine(t, cap, kb); kb+=[...t].length; return l; });
  const totalW=Math.max(1,...lays.map(l=>l.width));

  // 각 줄을 코어 상단 기준으로 쌓되, glyph 내부는 텍스처 포함 좌표라 line 은 overflow 보임.
  const stack=document.createElement("div");
  stack.style.position="relative";
  stack.style.width=totalW+"px";

  let coreCursor=0;                 // 코어 기준 누적 y
  for(const lay of lays){
    const lineCoreH=(lay.cBot-lay.cTop)||cap;
    const line=document.createElement("div"); line.className="line";
    line.style.position="absolute";
    line.style.left=((totalW-lay.width)/2)+"px";
    // 이 줄의 코어 상단(lay.cTop)을 coreCursor 에 맞춤. glyph.top 은 lay.top0 기준이므로
    // 줄 컨테이너 top = coreCursor - (lay.cTop - lay.top0) 로 보정.
    line.style.top=(coreCursor - (lay.cTop - lay.top0))+"px";
    line.style.width=lay.width+"px";
    line.style.height="0px";        // 높이 0 + overflow 보임 → 중앙정렬 박스에 영향 안 줌
    line.style.overflow="visible";
    for(const it of lay.items){
      if(it.type==="glyph"){
        const {svg, vb}=buildGlyphSVG(it.L,{seedKey:it.key});
        svg.setAttribute("width", vb[2]*it.s);
        svg.setAttribute("height", vb[3]*it.s);
        const wrap=document.createElement("div"); wrap.className="glyph";
        wrap.style.left=it.x+"px";
        wrap.style.top=(it.top - lay.top0)+"px";
        wrap.appendChild(svg);
        line.appendChild(wrap);
      } else {
        const sp=document.createElement("span"); sp.className="plain";
        sp.textContent=it.ch;
        sp.style.position="absolute";
        sp.style.left=it.x+"px";
        sp.style.top=(it.top - lay.top0)+"px";
        sp.style.fontSize=it.fpx+"px";
        line.appendChild(sp);
      }
    }
    stack.appendChild(line);
    coreCursor += lineCoreH + lineGap;
  }
  // 스택 박스 높이 = 코어 전체 높이(텍스처 제외) → flex 중앙정렬이 코어 기준으로 가운데
  stack.style.height=(coreCursor-lineGap)+"px";
  stack.style.overflow="visible";
  word.appendChild(stack);
}

function download(){
  const line=document.querySelector("#word .line");
  if(!line) return;
  const glyphs=[...line.querySelectorAll(".glyph")];
  if(!glyphs.length) return;
  // 화면 레이아웃(텍스처 넘침 포함)을 그대로 재현. 전체 bbox는 넘침까지 포함해 계산.
  let X0=Infinity,Y0=Infinity,X1=-Infinity,Y1=-Infinity, parts=[];
  for(const g of glyphs){
    const svg=g.querySelector("svg");
    const left=parseFloat(g.style.left), top=parseFloat(g.style.top);
    const w=+svg.getAttribute("width"), h=+svg.getAttribute("height");
    const vb=svg.getAttribute("viewBox");
    let bb; try{ bb=svg.getBBox(); }catch(e){ bb={x:0,y:0,width:+vb.split(/\s+/)[2],height:+vb.split(/\s+/)[3]}; }
    const vbn=vb.split(/\s+/).map(Number);
    const sx=w/vbn[2], sy=h/vbn[3];
    // 넘침 bbox(px) → 좌표계
    X0=Math.min(X0,left+(bb.x-vbn[0])*sx); Y0=Math.min(Y0,top+(bb.y-vbn[1])*sy);
    X1=Math.max(X1,left+(bb.x-vbn[0]+bb.width)*sx); Y1=Math.max(Y1,top+(bb.y-vbn[1]+bb.height)*sy);
    parts.push(`<svg x="${left}" y="${top}" width="${w}" height="${h}" viewBox="${vb}" overflow="visible">${svg.innerHTML}</svg>`);
  }
  const pad=10, W=(X1-X0)+pad*2, H=(Y1-Y0)+pad*2;
  // 화면과 동일하게 모든 도형 검정 처리(외곽선만인 fill=none 제외)
  const blackStyle=`<style>*{fill:#000}[fill="none"]{fill:none}</style>`;
  const out=`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="${X0-pad} ${Y0-pad} ${W} ${H}">${blackStyle}${parts.join("")}</svg>`;
  const blob=new Blob([out],{type:"image/svg+xml"});
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob); a.download="modular_typo.svg"; a.click();
}

// 감정/컬러 스위치 UI(팝업 .body 안에). 영어 라벨.
function buildEmos(){
  const el=document.querySelector("#emos .body"); el.innerHTML="";
  // 컬러 토글(anger 위, 같은 스위치 디자인)
  const cb=document.createElement("button");
  cb.id="colorBtn"; cb.title="컬러 표시 켜기/끄기";
  cb.innerHTML=`<span class="sw"></span>color`;
  const csync=()=>cb.classList.toggle("off", !colorMode);
  cb.onclick=()=>{ colorMode=!colorMode; csync(); render(); };
  csync(); el.appendChild(cb);
  // 감정 스위치들
  for(const e of EMO){
    const b=document.createElement("button");
    b.innerHTML=`<span class="sw"></span>${EMO_LABEL[e]}`;   // 영어 라벨(lust→desire)
    const sync=()=>b.classList.toggle("off", !ACTIVE.has(e));
    b.onclick=()=>{
      if(ACTIVE.has(e)){ if(ACTIVE.size>1) ACTIVE.delete(e); }  // 최소 1개 유지
      else ACTIVE.add(e);
      sync(); shuffleAll(); render();
    };
    sync(); el.appendChild(b);
  }
}
buildEmos();

// ── 팝업 공통: 드래그 이동 + 최소화 ──
function makePopup(id){
  const pop=document.getElementById(id);
  const bar=pop.querySelector(".bar");
  const minBtn=pop.querySelector(".min");
  // 최소화 토글
  const toggleMin=()=>{
    const c=pop.classList.toggle("collapsed");
    minBtn.textContent = c ? "▾" : "▴";   // 펼침=▴(누르면 접힘), 최소화=▾(누르면 펼침)
  };
  minBtn.addEventListener("click", e=>{ e.stopPropagation(); toggleMin(); });
  // 드래그 이동(상단 바). min 버튼 위에서 시작하면 드래그 안 함.
  bar.addEventListener("mousedown", e=>{
    if(e.target.closest(".min")) return;          // 최소화 버튼은 클릭 전용
    const r=pop.getBoundingClientRect();
    pop.style.left=r.left+"px"; pop.style.top=r.top+"px";
    pop.style.right="auto"; pop.style.bottom="auto";
    const ox=e.clientX-r.left, oy=e.clientY-r.top;
    const move=ev=>{
      const w=pop.offsetWidth, h=pop.offsetHeight;   // 팝업 전체가 화면 안에 머물게
      pop.style.left=Math.max(0,Math.min(innerWidth-w,ev.clientX-ox))+"px";
      pop.style.top=Math.max(0,Math.min(innerHeight-h,ev.clientY-oy))+"px";
    };
    const up=()=>{ removeEventListener("mousemove",move); removeEventListener("mouseup",up); };
    addEventListener("mousemove",move); addEventListener("mouseup",up);
    e.preventDefault();
  });
}
makePopup("emos"); makePopup("panel");

// 텍스트 창 크기조절(우측 하단 핸들): 패널 폭 + textarea 높이 조절
(function(){
  const pop=document.getElementById("panel");
  const handle=document.getElementById("resizeHandle");
  const ta=document.getElementById("txt");
  handle.addEventListener("mousedown", e=>{
    e.preventDefault(); e.stopPropagation();
    const r=pop.getBoundingClientRect();
    // 좌상단 고정 후 우/하로 확장
    pop.style.left=r.left+"px"; pop.style.top=r.top+"px";
    pop.style.right="auto"; pop.style.bottom="auto";
    const sx=e.clientX, sy=e.clientY, w0=r.width, h0=ta.offsetHeight;
    const maxW=innerWidth-r.left-6;                  // 화면 밖으로 안 나가게
    const move=ev=>{
      pop.style.width=Math.max(140, Math.min(maxW, w0+(ev.clientX-sx)))+"px";
      const maxH=innerHeight-pop.getBoundingClientRect().top-(pop.offsetHeight-ta.offsetHeight)-6;
      ta.style.height=Math.max(40, Math.min(maxH, h0+(ev.clientY-sy)))+"px";
    };
    const up=()=>{ removeEventListener("mousemove",move); removeEventListener("mouseup",up); };
    addEventListener("mousemove",move); addEventListener("mouseup",up);
  });
})();

const txtEl=document.getElementById("txt");
// 실시간: 입력 즉시 반영(엔터=줄바꿈)
txtEl.addEventListener("input", render);
// 마우스 휠 스크롤 → 글자 확대/축소(슬라이더 없음). 위로=확대.
addEventListener("wheel", e=>{
  if(e.target.closest("#txt")) return;             // 입력칸 안 스크롤은 제외
  e.preventDefault();
  const step=0.03;
  sizeFactor = Math.max(0.04, Math.min(1.2, sizeFactor + (e.deltaY<0 ? step : -step)));
  render();
}, {passive:false});
// 화면 크기 바뀌면 가운데 정렬 유지
addEventListener("resize", render);
// 글자 영역 클릭 → 획 다시 랜덤 조립
document.getElementById("word").addEventListener("click", ()=>{ shuffleAll(); render(); });
// 단축키: Cmd/Ctrl+S → SVG 저장, Esc → 재조립
addEventListener("keydown", e=>{
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==="s"){ e.preventDefault(); download(); }
  if(e.key==="Escape" && document.activeElement!==txtEl){ shuffleAll(); render(); }
});
txtEl.focus();
render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    build()
