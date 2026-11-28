"""C1c Calibre oracle fixtures: device-recognition rules of the NSPL DRC deck.

Groups: 14.PL2PR (poly2 resistor), 15.CAP (PIP capacitor), 16.PNP / 17.NPN (BJT),
19.IO (ESD I/O transistor), 20.LU (ESD latch-up guard rings), 22.PNW / 23.NPW (diodes).

Format follows scripts/asic/drc_cases.py of the team-05 repository:
dict(rule, label, shapes, fail, hierarchy, dbu, raises); shapes are
[gds_layer, [x1, y1, x2, y2]] boxes in um on datatype 0.  `fail` is our hypothesis
for the TARGET rule only; Calibre decides.  Other rules are expected to fire too.

Every device is built by a parametric builder starting from a minimal valid device
whose dimensions sit exactly on the source values (PDF v1.1 tables + deck bodies);
each fixture perturbs one dimension.  Internally all geometry is integer nm on a
10 nm grid (grid 0.01 um, dbu 0.001).

cases()            -> list of fixture dicts (drc_cases.py format)
cases_with_meta()  -> list of (case, meta) with meta = {rationale, deck_line, family}
"""

# GDS layer numbers from the deck LAYER statements (lines 205-260).
NWELL, ACT, POLY1, POLY2, NSD, PSD, NHRI, PHRI = 2, 11, 12, 13, 14, 15, 20, 21
CONT, MET1, RES, ESD, CAP, BJT, DIODE, ESDD, LVSD = 31, 32, 51, 52, 53, 56, 57, 59, 60

# Rule body start lines (verification/asic/drc-rules.json source_line).
DECK_LINE = {
    '14.PL2PR.W': 1143, '14.PL2PR.L': 1148, '14.PL2PR.S1': 1159, '14.PL2PR.S2': 1166,
    '14.PL2PR.E1': 1174, '14.PL2PR.E2': 1180, '14.PL2PR.bad1': 1186, '14.PL2PR.bad2': 1193,
    '14.PL2PR.bad3': 1198, '14.PL2PR.bad4': 1203,
    '15.CAP.W2': 1216, '15.CAP.S1': 1224, '15.CAP.S2': 1230, '15.CAP.S3': 1236,
    '15.CAP.S4': 1242, '15.CAP.S5': 1248, '15.CAP.E1': 1254, '15.CAP.E2': 1259,
    '15.CAP.E3': 1264, '15.CAP.bad1': 1269, '15.CAP.bad2': 1274, '15.CAP.bad3': 1280,
    '15.CAP.bad4': 1286, '15.CAP.bad5': 1293,
    '16.PNP.W1': 1302, '16.PNP.W2': 1307, '16.PNP.S': 1313, '16.PNP.E1': 1319,
    '16.PNP.E2': 1327, '16.PNP.E3': 1335, '16.PNP.E4': 1344,
    '17.NPN.W1': 1358, '17.NPN.W2': 1363, '17.NPN.S': 1369, '17.NPN.E1': 1375,
    '17.NPN.E2': 1383, '17.NPN.E3': 1391, '17.NPN.E4': 1401,
    '19.IO.W1': 1419, '19.IO.W2': 1428, '19.IO.W4': 1442, '19.IO.S1': 1449,
    '19.IO.S2': 1455, '19.IO.S3': 1461, '19.IO.E1': 1468, '19.IO.E2': 1476,
    '20.LU.W1': 1486, '20.LU.W2': 1491, '20.LU.S1': 1496, '20.LU.S2': 1503,
    '20.LU.S3': 1509, '20.LU.S4': 1514, '20.LU.E1': 1520, '20.LU.E2': 1525,
    '22.PNW.W1': 1534, '22.PNW.W2': 1542, '22.PNW.S': 1548, '22.PNW.E1': 1554,
    '22.PNW.E2': 1563, '22.PNW.bad1': 1572,
    '23.NPW.W1': 1580, '23.NPW.W2': 1588, '23.NPW.S': 1594, '23.NPW.E': 1600,
}


def nm(v):
    """um -> integer nm; refuses values that are not on the 10 nm grid."""
    value = int(round(v * 1000))
    if value % 10:
        raise ValueError(f'off-grid value {v}')
    return value


def um(v):
    return round(v / 1000, 3)


def box(layer, x1, y1, x2, y2):
    """Box from nm integers."""
    if not (x1 < x2 and y1 < y2):
        raise ValueError(f'degenerate box {layer} {(x1, y1, x2, y2)}')
    for v in (x1, y1, x2, y2):
        if v % 10:
            raise ValueError(f'off-grid coordinate {v} nm')
    return [layer, [um(x1), um(y1), um(x2), um(y2)]]


def grow(b, l, bo=None, r=None, t=None):
    """Grow box b=(x1,y1,x2,y2) by l (or per side l,bo,r,t); negative shrinks."""
    bo = l if bo is None else bo
    r = l if r is None else r
    t = l if t is None else t
    return (b[0] - l, b[1] - bo, b[2] + r, b[3] + t)


def rect(layer, b):
    return box(layer, *b)


def ring(layer, inner, outer):
    """Donut as four abutting boxes; Calibre merges a layer before HOLES/DONUT."""
    ox1, oy1, ox2, oy2 = outer
    ix1, iy1, ix2, iy2 = inner
    return [box(layer, ox1, oy1, ox2, iy1), box(layer, ox1, iy2, ox2, oy2),
            box(layer, ox1, iy1, ix1, iy2), box(layer, ix2, iy1, ox2, iy2)]


def f10(v):
    """Floor to the 10 nm grid."""
    return v - (v % 10)


def contact(x, y, m1=True):
    """0.6 um contact at lower-left (x, y) nm, with a 0.6 um MET1 enclosure pad."""
    shapes = [box(CONT, x, y, x + 600, y + 600)]
    if m1:
        shapes.append(box(MET1, x - 600, y - 600, x + 1200, y + 1200))
    return shapes


def bbox(shapes):
    xs1 = min(s[1][0] for s in shapes); ys1 = min(s[1][1] for s in shapes)
    xs2 = max(s[1][2] for s in shapes); ys2 = max(s[1][3] for s in shapes)
    return (nm(xs1), nm(ys1), nm(xs2), nm(ys2))


# --------------------------------------------------------------------------
# 14.PL2PR  poly2 resistor (p2res / p2hres)
# --------------------------------------------------------------------------
def p2res(W=2, L=5, ncont=1, s=0.6, e2l=0.5, e2r=0.5, gap=0.0, lvsd_ext=0.5,
          res_m=(1.5, 1.5, 1.5, 1.5), hres=False, phri=(1, 1, 1, 1), ox=0, oy=0,
          lvsd=True, res=True):
    """Resistor body along x.  POLY2 y in [oy, oy+W]; LVSD cuts the body between the
    two contact columns (length L) and overhangs the poly2 sides by lvsd_ext so that
    14.PL2PR.L edge set B is non-empty.  RES encloses all poly2 (14.PL2PR.bad1)."""
    W, L, s, e2l, e2r, gap, ext = map(nm, (W, L, s, e2l, e2r, gap, lvsd_ext))
    ox, oy = nm(ox), nm(oy)
    cl = ox + e2l
    lv1 = cl + 600 + gap
    lv2 = lv1 + L
    cr = lv2 + gap
    p2 = (ox, oy, cr + 600 + e2r, oy + W)
    stack = ncont * 600 + (ncont - 1) * s
    y0 = oy + f10((W - stack) // 2)
    shapes = [rect(POLY2, p2)]
    if lvsd:
        shapes.append(box(LVSD, lv1, oy - ext, lv2, oy + W + ext))
    rb = grow(p2, *map(nm, res_m))
    if res:
        shapes.append(rect(RES, rb))
    if hres:
        shapes.append(rect(PHRI, grow(p2, *map(nm, phri))))
    for cx in (cl, cr):
        ys = [y0 + k * (600 + s) for k in range(ncont)]
        for y in ys:
            shapes.append(box(CONT, cx, y, cx + 600, y + 600))
        shapes.append(box(MET1, cx - 600, ys[0] - 600, cx + 1200, ys[-1] + 1200))
    return shapes, dict(p2=p2, res=rb, lvsd=(lv1, lv2))


# --------------------------------------------------------------------------
# 15.CAP  PIP capacitor
# --------------------------------------------------------------------------
def pipcap(p2w=2.6, p2h=2.6, e3=(1, 1, 1), s1=1.0, e1=1.0, c2l=None, c2b=None,
           lvsd_h=0.2, lvsd_y=None, lvsd_in=(0, 0), lvsd_out=(0, 0, 0),
           cap_m=0.2, ox=0, oy=0, poly1=True, poly2=True, cap=True, lvsd=True):
    """POLY1 bottom plate, POLY2 top plate (inside POLY1 by e3 on left/bottom/top),
    contact on POLY2 (enclosure 1.0 = 15.CAP.E2), contact on POLY1 right of POLY2 at
    s1 (15.CAP.S1) with POLY1 enclosure e1 (15.CAP.E1).  LVSD is a 0.2 um strip along
    the POLY2 top edge spanning the full POLY2 width (15.CAP.bad3/bad4/bad5; LVS uses
    W = area(LVSD)/0.2).  CAP and NSD = POLY1 grown by cap_m (LVS PIPCAP = NSD AND CAP)."""
    p2w, p2h, s1, e1, lh, cap_m = map(nm, (p2w, p2h, s1, e1, lvsd_h, cap_m))
    e3l, e3b, e3t = map(nm, e3)
    ox, oy = nm(ox), nm(oy)
    p2 = (ox + e3l, oy + e3b, ox + e3l + p2w, oy + e3b + p2h)
    cx2 = p2[0] + (nm(c2l) if c2l is not None else f10((p2w - 600) // 2))
    cy = p2[1] + (nm(c2b) if c2b is not None else f10((p2h - 600) // 2))
    cx1 = p2[2] + s1
    p1 = (ox, oy, cx1 + 600 + e1, p2[3] + e3t)
    shapes = []
    if poly1:
        shapes.append(rect(POLY1, p1))
        shapes += contact(cx1, cy)
    if poly2:
        shapes.append(rect(POLY2, p2))
        shapes += contact(cx2, cy)
    if lvsd:
        il, ir = map(nm, lvsd_in)
        xl, xr, xt = map(nm, lvsd_out)
        ly1 = p2[3] - lh if lvsd_y is None else oy + nm(lvsd_y)
        ly2 = (p2[3] + xt) if lvsd_y is None else ly1 + lh
        shapes.append(box(LVSD, p2[0] + il - xl, ly1, p2[2] - ir + xr, ly2))
    cb = grow(p1 if poly1 else p2, cap_m)
    if cap:
        shapes.append(rect(CAP, cb))
        shapes.append(rect(NSD, cb))
    return shapes, dict(p1=p1, p2=p2, cap=cb)


# --------------------------------------------------------------------------
# 16.PNP / 17.NPN  vertical BJTs (concentric donuts)
# --------------------------------------------------------------------------
def pnp(ew=2, eh=2, b=(4.5, 4.5, 4.5, 4.5), a2b=2, c2=2, c1=4.5, a2c=2, c3=4.5,
        c4e=1, c4b=(1, 1), c4c=(1, 1), ox=0, oy=0, bjt=True, collector=True):
    """PNP: P+ emitter / N+ base ring in NWELL / P+ collector ring in PWELL(PSUB);
    NWELL = base outer + c2 (16.PNP.E2 exact), collector inner = NWELL + c1 (E1 min),
    BJT = collector outer + c3 (E3 exact).  Implants enclose each ACT by c4 (E4)."""
    ew, eh, a2b, c2, c1, a2c, c3, c4e = map(nm, (ew, eh, a2b, c2, c1, a2c, c3, c4e))
    bl, bb, br, bt = map(nm, b)
    ox, oy = nm(ox), nm(oy)
    E = (ox, oy, ox + ew, oy + eh)
    Bi = grow(E, bl, bb, br, bt)
    Bo = grow(Bi, a2b)
    NW = grow(Bo, c2)
    Ci = grow(NW, c1)
    Co = grow(Ci, a2c)
    BJ = grow(Co, c3)
    yc = oy + f10((eh - 600) // 2)
    shapes = [rect(ACT, E), rect(PSD, grow(E, c4e))]
    shapes += contact(ox + f10((ew - 600) // 2), yc)
    shapes += ring(ACT, Bi, Bo)
    shapes += ring(NSD, grow(Bi, -nm(c4b[0])), grow(Bo, nm(c4b[1])))
    shapes += contact(Bo[0] + f10((a2b - 600) // 2), yc)
    shapes.append(rect(NWELL, NW))
    if collector:
        shapes += ring(ACT, Ci, Co)
        shapes += ring(PSD, grow(Ci, -nm(c4c[0])), grow(Co, nm(c4c[1])))
        shapes += contact(Co[0] + f10((a2c - 600) // 2), yc)
    if bjt:
        shapes.append(rect(BJT, BJ))
    return shapes, dict(E=E, Bi=Bi, Bo=Bo, NW=NW, Ci=Ci, Co=Co, BJT=BJ)


def npn(ew=2, eh=2, b=(4.5, 4.5, 4.5, 4.5), a2b=2, c2=2, c1i=4.5, a2c=2, c1o=4.5,
        c3=1, c4e=1, c4b=(1, 1), c4c=(1, 1), ox=0, oy=0, bjt=True):
    """NPN: N+ emitter / P+ base ring in the PWELL hole of an NWELL ring / N+ collector
    ring in the NWELL.  NWELL inner edge = base outer + c2 (17.NPN.E2 exact); collector
    at >= 4.5 from both NPN_WELL pieces (E1: inner base PWELL and outer BJT-PWELL ring);
    BJT encloses NWELL by c3 (E3 >= 1)."""
    ew, eh, a2b, c2, c1i, a2c, c1o, c3, c4e = map(nm, (ew, eh, a2b, c2, c1i, a2c, c1o, c3, c4e))
    bl, bb, br, bt = map(nm, b)
    ox, oy = nm(ox), nm(oy)
    E = (ox, oy, ox + ew, oy + eh)
    Bi = grow(E, bl, bb, br, bt)
    Bo = grow(Bi, a2b)
    NWi = grow(Bo, c2)
    Ci = grow(NWi, c1i)
    Co = grow(Ci, a2c)
    NWo = grow(Co, c1o)
    BJ = grow(NWo, c3)
    yc = oy + f10((eh - 600) // 2)
    shapes = [rect(ACT, E), rect(NSD, grow(E, c4e))]
    shapes += contact(ox + f10((ew - 600) // 2), yc)
    shapes += ring(ACT, Bi, Bo)
    shapes += ring(PSD, grow(Bi, -nm(c4b[0])), grow(Bo, nm(c4b[1])))
    shapes += contact(Bo[0] + f10((a2b - 600) // 2), yc)
    shapes += ring(NWELL, NWi, NWo)
    shapes += ring(ACT, Ci, Co)
    shapes += ring(NSD, grow(Ci, -nm(c4c[0])), grow(Co, nm(c4c[1])))
    shapes += contact(Co[0] + f10((a2c - 600) // 2), yc)
    if bjt:
        shapes.append(rect(BJT, BJ))
    return shapes, dict(E=E, Bi=Bi, Bo=Bo, NWi=NWi, Ci=Ci, Co=Co, NWo=NWo, BJT=BJ)


# --------------------------------------------------------------------------
# 19.IO  multi-finger ESD transistor
# --------------------------------------------------------------------------
def esd_mos(nf=12, W=60, L=1.2, src=2.6, drn=8.6, e1x=1.0, cy0=1.0, cs=0.8, m1d=6.0,
            imp=1.0, ptype=False, esd=True, esdd=True, ox=0, oy=0, esd_margin=3.0):
    """S G D G S ... finger device inside an ESD marker.  Inner source width src gives
    SCGS=(src-0.6)/2 (19.IO.S2), drain width drn gives DCGS=(drn-0.6)/2 (19.IO.S1);
    outer S/D regions put the contact e1x from the ACT edge (19.IO.E1).  Contact
    columns start cy0 above ACT with spacing cs (19.IO.S3).  Drain MET1 is m1d wide
    (19.IO.W4).  NSD (PSD for ptype) encloses ACT by imp (19.IO.E2).  ESDD covers each
    drain.  Gates are joined by a POLY1 bar above ACT with one contact."""
    W, L, src, drn, e1x, cy0, cs, m1d, imp, mg = map(nm, (W, L, src, drn, e1x, cy0, cs, m1d, imp, esd_margin))
    ox, oy = nm(ox), nm(oy)
    sp_s, sp_d = (src - 600) // 2, (drn - 600) // 2
    regions = []  # (x1, x2, kind, contact_x)
    x = ox
    first_w = e1x + 600 + sp_s
    regions.append((x, x + first_w, 'S', x + e1x))
    x += first_w
    gates = []
    for i in range(nf):
        gates.append((x, x + L))
        x += L
        kind = 'D' if i % 2 == 0 else 'S'
        sp = sp_d if kind == 'D' else sp_s
        if i == nf - 1:
            w = sp + 600 + e1x
            regions.append((x, x + w, kind, x + sp))
        else:
            w = drn if kind == 'D' else src
            regions.append((x, x + w, kind, x + f10((w - 600) // 2)))
        x += w
    act = (ox, oy, x, oy + W)
    shapes = [rect(ACT, act), rect(PSD if ptype else NSD, grow(act, imp))]
    ys = []
    y = oy + cy0
    while y + 600 <= oy + W - 1000 or not ys:
        ys.append(y)
        y += 600 + cs
    for x1, x2, kind, cx in regions:
        for y in ys:
            shapes.append(box(CONT, cx, y, cx + 600, y + 600))
        if kind == 'D':
            left = cx + 300 - f10(m1d // 2)
            shapes.append(box(MET1, left, ys[0] - 600, left + m1d, ys[-1] + 1200))
            if esdd:
                shapes.append(box(ESDD, x1, oy, x2, oy + W))
        else:
            shapes.append(box(MET1, cx - 600, ys[0] - 600, cx + 1200, ys[-1] + 1200))
    for g1, g2 in gates:
        shapes.append(box(POLY1, g1, oy - 1000, g2, oy + W + 1000))
    bar = (gates[0][0], oy + W + 1000, gates[-1][1], oy + W + 3000)
    shapes.append(rect(POLY1, bar))
    pcx = f10((bar[0] + bar[2]) // 2)
    shapes += contact(pcx, oy + W + 1700)
    if ptype:
        shapes.append(rect(NWELL, grow(act, 2000)))
    if esd:
        shapes.append(rect(ESD, grow(bbox(shapes), mg)))
    return shapes, dict(act=act, regions=regions, ys=ys)


# --------------------------------------------------------------------------
# 20.LU  ESD latch-up structure (bars, all inside one ESD marker)
# --------------------------------------------------------------------------
def lu(H=60, g3=2, e2=2, s1=5, wNG=10, wPD=10, s2=5, e1=(2, 2), wND=10, s2r=5,
       wPG=10, g4=2, esd=True):
    """Left to right: PMOS ESD finger (PA) and N+ guard ring (NG) in NWELL_p;
    P+ dummy collector (PD); N+ dummy collector (ND) in its own NWELL_dc; P+ guard
    ring (PG); NMOS ESD finger (NA).  Taps are bars H tall so their width is the
    x dimension.  Spacing parameters map to 20.LU rules:
    g3: PA..NG (S3), e2: NG..NWELL_p edge (E2), s1: NG..PD (S1),
    s2: PD..NWELL_dc (S2), e1: ND enclosure by NWELL_dc left/right (E1, W1),
    s2r: NWELL_dc..PG (S2), g4: PG..NA (S4), wPD/wND/wNG/wPG: tap widths (W2)."""
    H, g3, e2, s1, wNG, wPD, s2, wND, s2r, wPG, g4 = map(nm, (H, g3, e2, s1, wNG, wPD, s2, wND, s2r, wPG, g4))
    e1l, e1r = map(nm, e1)
    shapes = []

    def mos(x0, ptype, gate_left=True):
        """Single 1.2 um finger, 2.6 source / 8.6 drain, contacts at SCGS 1 / DCGS 4."""
        a = (x0, 0, x0 + 12400, H)
        if gate_left:   # S on the left
            g = (x0 + 2600, x0 + 3800); sc = x0 + 1000; dc = x0 + 7800; d = (x0 + 3800, x0 + 12400)
        else:           # D on the left
            g = (x0 + 8600, x0 + 9800); sc = x0 + 10800; dc = x0 + 4000; d = (x0, x0 + 8600)
        out = [rect(ACT, a), box(POLY1, g[0], -1000, g[1], H + 1000),
               box(POLY1, g[0] - 600, -3600, g[1] + 600, -1000)]
        out += contact(g[0] + 300, -2900)
        yc = f10((H - 600) // 2)
        out += [box(CONT, sc, yc, sc + 600, yc + 600), box(MET1, sc - 600, yc - 600, sc + 1200, yc + 1200),
                box(CONT, dc, yc, dc + 600, yc + 600), box(MET1, dc + 300 - 3000, yc - 600, dc + 300 + 3000, yc + 1200),
                box(ESDD, d[0], 0, d[1], H)]
        return a, out

    def tap(x0, w, layer_imp):
        a = (x0, 0, x0 + w, H)
        yc = f10((H - 600) // 2)
        out = [rect(ACT, a)] + contact(x0 + f10((w - 600) // 2), yc)
        return a, out

    # PMOS + N+ guard ring in NWELL_p
    PA, s = mos(0, True)
    shapes += s
    NG, s = tap(PA[2] + g3, wNG, NSD)
    shapes += s
    mid = PA[2] + f10(g3 // 2) if g3 < 2000 else None
    shapes.append(box(PSD, -1000, -1000, mid if mid else PA[2] + 1000, H + 1000))
    shapes.append(box(NSD, mid if mid else NG[0] - 1000, -1000, NG[2] + 1000, H + 1000))
    NWp = (-2000, -2000, NG[2] + e2, H + 2000)
    shapes.append(rect(NWELL, NWp))
    # P+ dummy collector
    PD, s = tap(NG[2] + s1, wPD, PSD)
    shapes += s
    shapes.append(box(PSD, PD[0] - 1000, -1000, PD[2] + 1000, H + 1000))
    # N+ dummy collector in NWELL_dc
    nx1 = PD[2] + s2
    ND, s = tap(nx1 + e1l, wND, NSD)
    shapes += s
    shapes.append(box(NSD, ND[0] - min(1000, e1l), -1000, ND[2] + min(1000, e1r), H + 1000))
    NWd = (nx1, -2000, ND[2] + e1r, H + 2000)
    shapes.append(rect(NWELL, NWd))
    # P+ guard ring + NMOS
    PG, s = tap(NWd[2] + s2r, wPG, PSD)
    shapes += s
    NA, s = mos(PG[2] + g4, False, gate_left=True)
    shapes += s
    mid = PG[2] + f10(g4 // 2) if g4 < 2000 else None
    shapes.append(box(PSD, PG[0] - 1000, -1000, mid if mid else PG[2] + 1000, H + 1000))
    shapes.append(box(NSD, mid if mid else NA[0] - 1000, -1000, NA[2] + 1000, H + 1000))
    if esd:
        shapes.append(rect(ESD, grow(bbox(shapes), 3000)))
    return shapes, dict(PA=PA, NG=NG, NWp=NWp, PD=PD, ND=ND, NWd=NWd, PG=PG, NA=NA)


# --------------------------------------------------------------------------
# 22.PNW / 23.NPW  diodes
# --------------------------------------------------------------------------
def pnw(aw=2, ah=2, b=(4.5, 4.5, 4.5, 4.5), a2=2, c1=2, c2a=1, c2n=(1, 1),
        diode=(0, 0, 0, 0), ox=0, oy=0, marker=True):
    """P+ anode in NWELL, N+ cathode ring; NWELL = ring outer + c1 (22.PNW.E1 exact);
    DIODE coincides with NWELL (22.PNW.bad1; `diode` grows it per side);
    PSD/NSD = ACT +/- 1 exactly (22.PNW.E2).  LVSD 0.2 strip on the anode top (LVS W)."""
    aw, ah, a2, c1, c2a = map(nm, (aw, ah, a2, c1, c2a))
    bl, bb, br, bt = map(nm, b)
    ox, oy = nm(ox), nm(oy)
    A = (ox, oy, ox + aw, oy + ah)
    Ki = grow(A, bl, bb, br, bt)
    Ko = grow(Ki, a2)
    NW = grow(Ko, c1)
    yc = oy + f10((ah - 600) // 2)
    shapes = [rect(ACT, A), rect(PSD, grow(A, c2a)), box(LVSD, A[0], A[3] - 200, A[2], A[3])]
    shapes += contact(ox + f10((aw - 600) // 2), yc)
    shapes += ring(ACT, Ki, Ko)
    shapes += ring(NSD, grow(Ki, -nm(c2n[0])), grow(Ko, nm(c2n[1])))
    shapes += contact(Ko[0] + f10((a2 - 600) // 2), yc)
    shapes.append(rect(NWELL, NW))
    if marker:
        shapes.append(rect(DIODE, grow(NW, *map(nm, diode))))
    return shapes, dict(A=A, Ki=Ki, Ko=Ko, NW=NW)


def npw(cw=2, ch=2, b=(4.5, 4.5, 4.5, 4.5), a2=2, c1n=1, c1p=(1, 1), dm=2, ox=0, oy=0,
        marker=True):
    """N+ cathode in PWELL(PSUB), P+ anode ring; implants = ACT +/- 1 exactly (23.NPW.E);
    DIODE = ring outer + dm (no deck constraint).  LVSD 0.2 strip on the cathode top."""
    cw, ch, a2, c1n, dm = map(nm, (cw, ch, a2, c1n, dm))
    bl, bb, br, bt = map(nm, b)
    ox, oy = nm(ox), nm(oy)
    C = (ox, oy, ox + cw, oy + ch)
    Ki = grow(C, bl, bb, br, bt)
    Ko = grow(Ki, a2)
    yc = oy + f10((ch - 600) // 2)
    shapes = [rect(ACT, C), rect(NSD, grow(C, c1n)), box(LVSD, C[0], C[3] - 200, C[2], C[3])]
    shapes += contact(ox + f10((cw - 600) // 2), yc)
    shapes += ring(ACT, Ki, Ko)
    shapes += ring(PSD, grow(Ki, -nm(c1p[0])), grow(Ko, nm(c1p[1])))
    shapes += contact(Ko[0] + f10((a2 - 600) // 2), yc)
    if marker:
        shapes.append(rect(DIODE, grow(Ko, dm)))
    return shapes, dict(C=C, Ki=Ki, Ko=Ko)


# --------------------------------------------------------------------------
def cases_with_meta():
    out = []

    def emit(rule, label, shapes, fail, why, hierarchy=False, family=None):
        if rule not in DECK_LINE:
            raise ValueError('unknown rule ' + rule)
        case = dict(rule=rule, label=label, shapes=shapes, fail=fail,
                    hierarchy=hierarchy, dbu=.001, raises=False)
        out.append((case, dict(rationale=why, deck_line=DECK_LINE[rule],
                               family=family or rule.split('.')[1])))

    # ---------------- 14.PL2PR ----------------
    R = '14.PL2PR.'
    base = 'p2res W=2 L=5 1 contact/head, contact abuts LVSD, PL2 enc 0.5, RES enc 1.5'
    for W, f in [(2, False), (1.99, True), (2.01, False), (1.5, True)]:
        emit(R + 'W', f'width-{W}', p2res(W=W)[0], f,
             f'WITH WIDTH PPRES < 2 (PPRES = POLY2 AND LVSD AND RES); body width {W}. {base}')
    emit(R + 'W', 'width-1.99-child-rotated', p2res(W=1.99)[0], True,
         'same as width-1.99 inside rotated/mirrored leaf/middle hierarchy', hierarchy=True)
    for L, f in [(4, False), (3.99, True), (4.01, False), (2, True)]:
        emit(R + 'L', f'length-{L}', p2res(L=L)[0], f,
             f'INT F < 4.0 between the PPRES edges coincident with LVSD (body cut ends); LVSD length {L}. '
             'LVSD overhangs POLY2 sides by 0.5 so edge set B (PPRES edges not coincident-inside LVSD) is non-empty.')
    emit(R + 'L', 'length-3-lvsd-flush-width', p2res(L=3, lvsd_ext=0)[0], False,
         'HYPOTHESIS PROBE: LVSD exactly as wide as POLY2 -> every PPRES edge is COIN INSIDE LVSD, '
         'B empty, E (WITH EDGE D B) empty, so the deck body cannot flag even L=3. Expect 0 if read correctly.')
    for s, f in [(0.6, False), (0.59, True), (0.61, False), (0.3, True)]:
        emit(R + 'S1', f'cont-space-{s}', p2res(W=3, ncont=2, s=s)[0], f,
             f'EXT (POLY2_ON_CONT AND RES-with-LVSD) < 0.6; two contacts per head (W=3) spaced {s}.')
    for g, f in [(0, False), (0.01, True), (-0.01, True), (0.5, True)]:
        emit(R + 'S2', f'cont-to-lvsd-{g}', p2res(gap=g)[0], f,
             f'contact must abut LVSD: errors are CONT AND LVSD (overlap) and CONT without an edge '
             f'COIN with LVSD; gap {g} (negative = overlap).')
    for d, f in [(1.0, False), (0.99, True), (1.01, False), (0.5, True)]:
        emit(R + 'E1', f'phri-enc-{d}', p2res(hres=True, phri=(d, d, d, d))[0], f,
             f'ENC (POLY2 AND RES AND PHRI) PHRI < 1.0; p2hres with PHRI enclosing all POLY2 by {d} '
             '(14.PL2PR.bad1 line 2 requires HR poly2 inside PHRI).')
    for e, f in [(0.5, False), (0.49, True), (0.51, False), (0.2, True)]:
        emit(R + 'E2', f'cont-enc-{e}', p2res(e2l=e, e2r=e)[0], f,
             f'ENC CONT POLY2_RES < 0.5 for resistors with PRES_DEF; head end enclosure {e} '
             '(side enclosure 0.7).')
    emit(R + 'bad1', 'res-covers-poly2', p2res()[0], False, 'RES encloses all POLY2 by 1.5.')
    emit(R + 'bad1', 'res-edge-coincident', p2res(res_m=(0, 1.5, 0, 1.5))[0], False,
         'RES left/right edges coincide with POLY2 head ends: (POLY2 INTERACT A) NOT RES empty.')
    emit(R + 'bad1', 'poly2-0.01-outside-res', p2res(res_m=(-0.01, 1.5, 1.5, 1.5))[0], True,
         'RES left edge 0.01 inside POLY2 end -> 0.01 sliver of resistor POLY2 outside RES.')
    s, g = p2res()
    p2 = g['p2']
    s = s + [box(POLY2, p2[2], p2[1], p2[2] + 6000, p2[1] + 1600)]
    s += contact(p2[2] + 4700, p2[1] + 500)
    emit(R + 'bad1', 'poly2-interconnect-leaves-res', s, True,
         'POLY2 wire continues out of RES from the right head (same polygon) -> part NOT RES.')
    emit(R + 'bad1', 'hres-phri-misses-head', p2res(hres=True, phri=(-0.01, 1, 1, 1))[0], True,
         'second line: (POLY2 INTERACT (A AND PHRI)) NOT PHRI; PHRI left edge 0.01 inside POLY2. '
         'Also probes whether 14.PL2PR.E1 measures the coincident AA/PHRI cut edge.')
    emit(R + 'bad1', 'no-lvsd-not-a-resistor', p2res(lvsd=False, res_m=(-0.3, 1.5, 1.5, 1.5))[0], False,
         'RECOGNITION PROBE: no LVSD -> PPRES/POLY2_RES empty -> A empty even though POLY2 leaves RES.')

    def res_with(layer, y1, y2, lvsd=True, x1=2.0, x2=4.0):
        s, g = p2res(lvsd=lvsd)
        return s + [box(layer, nm(x1), nm(y1), nm(x2), nm(y2))]
    # RES bottom edge at y=-1.5 (POLY2 y 0..2, LVSD -0.5..2.5)
    for rule, layer, name in [('bad2', POLY1, 'POLY1'), ('bad3', ACT, 'ACT')]:
        emit(R + rule, f'{name.lower()}-inside-res', res_with(layer, -1.4, -0.9), True,
             f'{name} AND (RES INTERACT PRES_DEF): {name} box inside the resistor RES margin.')
        emit(R + rule, f'{name.lower()}-abuts-res', res_with(layer, -2.5, -1.5), False,
             f'{name} touches RES bottom edge from outside: AND is empty.')
        emit(R + rule, f'{name.lower()}-0.01-into-res', res_with(layer, -2.49, -1.49), True,
             f'{name} overlaps RES by 0.01.')
        if rule == 'bad2':
            emit(R + rule, 'poly1-in-res-without-lvsd', res_with(layer, -1.4, -0.9, lvsd=False), False,
                 'RECOGNITION PROBE: RES has no LVSD inside -> no PRES_DEF -> not a resistor RES.')
    emit(R + 'bad4', 'nsd-abuts-res', res_with(NSD, -2.5, -1.5), False,
         '(PSD OR NSD) AND RES: NSD touches RES from outside.')
    emit(R + 'bad4', 'nsd-0.01-into-res', res_with(NSD, -2.49, -1.49), True, 'NSD overlaps RES by 0.01.')
    emit(R + 'bad4', 'psd-0.01-into-res', res_with(PSD, -2.49, -1.49), True, 'PSD overlaps RES by 0.01.')
    s, g = p2res()
    emit(R + 'bad4', 'nsd-covers-resistor', s + [rect(NSD, g['res'])], True,
         'NSD over the whole RES (device table lists NSD=1 for Poly2 Res; deck body flags any implant in RES).')

    # ---------------- 15.CAP ----------------
    C = '15.CAP.'
    cb = 'pipcap POLY2 2.6x2.6 inside POLY1 4.6 high by 1.0, contacts enc 1.0, POLY1 contact S1=1.0, LVSD 0.2 top strip'
    for w, h, f, lab in [(2.6, 2.6, False, 'min-2.6'), (2.59, 2.6, True, 'min-2.59'), (2.61, 2.6, False, 'min-2.61'),
                         (2.6, 50, False, 'max-length-50'), (2.6, 50.01, True, 'max-length-50.01'),
                         (50.01, 50.01, True, 'max-width-50.01')]:
        emit(C + 'W2', lab, pipcap(p2w=w, p2h=h)[0], f,
             f'INT POLY2_CAP < 2.6 | WITH WIDTH POLY2_CAP > 50 | LENGTH POLY2_CAP > 50; POLY2 {w}x{h}. '
             'Width 2.59 necessarily also breaks 15.CAP.E2 (contact 0.6 + 2x1.0).')
    for s1, f in [(1.0, False), (0.99, True), (1.01, False), (0.5, True)]:
        emit(C + 'S1', f'poly1-cont-to-poly2-{s1}', pipcap(s1=s1)[0], f,
             f'EXT POLY2_CAP (POLY1_ON_CONT AND CAP) < 1; POLY1 contact {s1} from POLY2 (MET1 pads may hit 8.MET1.S1 below 1.0).')

    def cap_plus(extra, **kw):
        s, g = pipcap(**kw)
        return s + extra, g
    # Second structures below the capacitor: POLY2 bottom y=1, POLY1 bottom y=0, CAP bottom y=-0.2.
    for gap, f in [(2.0, False), (1.99, True), (2.01, False), (1.5, True)]:
        r, _ = p2res(ox=-1.5, oy=1 - gap - 2, res_m=(0.3, 0.3, 0.3, 0.1), lvsd_ext=0.05)
        emit(C + 'S2', f'cap-poly2-to-res-poly2-{gap}', cap_plus(r)[0], f,
             f'EXT POLY2_CAP POLY2_RES < 2; p2res body below the capacitor, POLY2-POLY2 gap {gap}; '
             'RES kept off CAP and off cap POLY1.')
    for gap, f in [(2.0, False), (1.99, True), (2.01, False), (1.5, True)]:
        y2 = nm(1 - gap)
        wire = [box(POLY2, -2000, y2 - 1600, 4600, y2)] + contact(-1500, y2 - 1100)
        emit(C + 'S3', f'cap-poly2-to-poly2-wire-{gap}', cap_plus(wire)[0], f,
             f'EXT POLY2_CAP (POLY2 NOT (RES OR CAP)) < 2; interconnect POLY2 wire below, gap {gap}, outside CAP.')
    for gap, f in [(1.0, False), (0.99, True), (1.01, False), (0.5, True)]:
        y2 = nm(-gap)
        wire = [box(POLY1, -2000, y2 - 1600, 6200, y2)] + contact(-1500, y2 - 1100)
        emit(C + 'S4', f'cap-poly1-to-poly1-wire-{gap}', cap_plus(wire)[0], f,
             f'EXT POLY1_CAP ((POLY1 NOT CAP) NOT ESD) < 1; interconnect POLY1 wire below, gap {gap}.')
    wire = [box(POLY1, -2000, -2100, 6200, -500)] + contact(-1500, -1600)
    emit(C + 'S4', 'esd-marked-wire-0.5-excluded', cap_plus(wire + [box(ESD, -2500, -2700, 6700, -300)])[0], False,
         'EXCLUSION PROBE: same 0.5 gap but the wire is under ESD -> removed from POLY1_EXT.')
    for gap, f in [(1.0, False), (0.99, True), (1.01, False), (0.5, True)]:
        s1, g1 = pipcap()
        s2, g2 = pipcap(ox=um(g1['p1'][2]) + gap)
        both = (g1['cap'][0], g1['cap'][1], g2['cap'][2], g2['cap'][3])
        emit(C + 'S5', f'cap-to-cap-{gap}', s1 + s2 + [rect(CAP, both), rect(NSD, both)], f,
             f'EXT POLY1_CAP < 1.0; two capacitors side by side under one CAP/NSD, POLY1-POLY1 gap {gap}.')
    for e, f in [(1.0, False), (0.99, True), (1.01, False)]:
        emit(C + 'E1', f'poly1-enc-cont-{e}', pipcap(e1=e)[0], f,
             f'ENC CONT POLY1_CAP < 1; POLY1 right edge {e} beyond the POLY1 contact.')
    for c, f in [(1.0, False), (0.99, True), (0.8, True)]:
        emit(C + 'E2', f'poly2-enc-cont-{c}', pipcap(c2l=c)[0], f,
             f'ENC CONT POLY2_CAP < 1; POLY2 contact left enclosure {c} (other side 2.0-{c}).')
    for e, f in [(1.0, False), (0.99, True), (1.01, False)]:
        emit(C + 'E3', f'poly1-enc-poly2-{e}', pipcap(e3=(e, 1, 1))[0], f,
             f'ENC POLY2_CAP POLY1_CAP < 1; POLY1 left extension beyond POLY2 {e}.')
    emit(C + 'E3', 'poly1-enc-poly2-0.99-child-rotated', pipcap(e3=(0.99, 1, 1))[0], True,
         'hierarchical copy of poly1-enc-poly2-0.99', hierarchy=True)
    for gap, f in [(None, True), (0, True), (0.01, False)]:
        s, g = pipcap()
        cbx = g['cap']
        if gap is None:
            a = [box(ACT, 1500, 1500, 2500, 2500)]
            lab, why = 'act-under-cap', 'ACT under the capacitor plates.'
        else:
            x = cbx[2] + nm(gap)
            a = [box(ACT, x, 1000, x + 2000, 3000)]
            lab = f'act-{gap}-from-cap'
            why = ('ACT touches CAP edge: INTERACT counts touching (hypothesis)' if gap == 0
                   else 'ACT 0.01 outside CAP: no interaction')
        emit(C + 'bad1', lab, s + a, f, 'INTERACT CAP ACT. ' + why)
    emit(C + 'bad2', 'poly1-and-poly2', pipcap()[0], False, 'valid capacitor: POLY1_CAP interacts POLY2_CAP.')
    emit(C + 'bad2', 'poly1-only', pipcap(poly2=False, lvsd=False)[0], True, 'CAP with POLY1 only.')
    emit(C + 'bad2', 'poly2-only', pipcap(poly1=False)[0], True, 'CAP with POLY2 only (no bottom plate).')
    # POLY2 beside POLY1 (not over it), touching or 0.01 apart, both inside one CAP.
    for gap, f in [(0, False), (0.01, True)]:
        p1 = [box(POLY1, 0, 0, 4600, 4600)] + contact(2000, 2000)
        x = 4600 + nm(gap)
        p2 = [box(POLY2, x, 1000, x + 2600, 3600), box(LVSD, x, 3400, x + 2600, 3600)] + contact(x + 1000, 2000)
        cbx = (-200, -200, x + 2800, 4800)
        emit(C + 'bad2', f'poly2-beside-poly1-gap-{gap}', p1 + p2 + [rect(CAP, cbx), rect(NSD, cbx)], f,
             'NOT INTERACT POLY2_CAP POLY1_CAP: touching counts as interaction (hypothesis), 0.01 gap does not.')
    for h, f in [(0.2, False), (0.19, True), (0.21, True)]:
        emit(C + 'bad3', f'lvsd-{h}', pipcap(lvsd_h=h)[0], f,
             f'exact 0.2: SIZE PL2_CAP_LVSD BY 0.1 UNDEROVER outputs LVSD wider than 0.2, '
             f'INT < 0.2 flags narrower; LVSD strip height {h}.')
    emit(C + 'bad4', 'lvsd-full-width-top', pipcap()[0], False,
         'LVSD spans POLY2 corner to corner on the top edge: coincident edges all end at 90-degree corners.')
    emit(C + 'bad4', 'lvsd-inset-both-sides', pipcap(lvsd_in=(0.01, 0.01))[0], True,
         'LVSD 0.01 short of both POLY2 sides: coincident top-edge piece has no 90-degree endpoint -> B -> TOUCH EDGE LVSD.')
    emit(C + 'bad4', 'lvsd-mid-strip', pipcap(lvsd_y=1.2)[0], True,
         'full-width LVSD strip across the POLY2 middle: coincident side pieces end mid-edge (hypothesis: flagged).')
    emit(C + 'bad4', 'lvsd-inset-one-side', pipcap(lvsd_in=(0.01, 0))[0], False,
         'HYPOTHESIS PROBE: inset on one side only keeps a 90-degree endpoint on every coincident piece; '
         'CONVEX EDGE ANGLE1 != 90 ANGLE2 != 90 should not select it although the text says "same width".')
    emit(C + 'bad5', 'lvsd-inside-poly2', pipcap()[0], False, '(LVSD INTERACT PL2_CAP_LVSD) NOT POLY2_CAP empty.')
    emit(C + 'bad5', 'lvsd-0.01-over-top', pipcap(lvsd_out=(0, 0, 0.01))[0], True,
         'LVSD (0.2 inside + 0.01 outside) crosses the POLY2 top edge; the AND part stays 0.2 for bad3.')
    emit(C + 'bad5', 'lvsd-0.01-over-side', pipcap(lvsd_out=(0, 0.01, 0))[0], True,
         'LVSD overhangs the POLY2 right side by 0.01.')

    # ---------------- 16.PNP / 17.NPN ----------------
    for fam, build, rp in [('PNP', pnp, '16.PNP.'), ('NPN', npn, '17.NPN.')]:
        dev = f'{fam} 2x2 emitter, b=4.5, rings 2.0, implants +1.0'
        for (w, h), f in [((2, 2), False), ((5, 5), False), ((10, 10), False), ((1.99, 1.99), True),
                          ((2.01, 2.01), True), ((9.99, 9.99), True), ((2, 5), True)]:
            emit(rp + 'W1', f'emitter-{w}x{h}', build(ew=w, eh=h)[0], f,
                 f'{fam}_E NOT (RECTANGLE ==2/5/10 square); emitter {w}x{h}.')
        for kw, lab, f in [({}, 'rings-2.0', False), (dict(a2b=1.99), 'base-1.99', True),
                           (dict(a2b=2.01), 'base-2.01', True), (dict(a2c=1.99), 'collector-1.99', True),
                           (dict(a2c=2.01), 'collector-2.01', True)]:
            emit(rp + 'W2', lab, build(**kw)[0], f,
                 'exact 2.0: INT (C OR B) < 2 and WITH WIDTH (C OR B) > 2 on the base/collector rings.')
        for b, lab, f in [((4.5,) * 4, '4.5', False), ((4.49,) * 4, '4.49', True), ((4.51,) * 4, '4.51', True),
                          ((4.49, 4.5, 4.51, 4.5), 'off-centre-0.01', True)]:
            emit(rp + 'S', f'emitter-base-{lab}', build(b=b)[0], f,
                 'exact 4.5: emitter edges not COIN INSIDE the EXT ==4.5 OPPOSITE edge set are output.')
        emit(rp + 'S', 'emitter-base-4.49-child-rotated', build(b=(4.49,) * 4)[0], True,
             'hierarchical copy of emitter-base-4.49', hierarchy=True)
        if fam == 'PNP':
            for c1, f in [(4.5, False), (4.49, True), (4.51, False), (3.0, True)]:
                emit(rp + 'E1', f'collector-to-nwell-{c1}', pnp(c1=c1)[0], f,
                     f'EXT PNP_C PNP_WELL < 4.5 (min only since 2025-03-10; PDF says =4.5); spacing {c1}.')
            for kw, lab, f in [(dict(c2=1.99), 'nwell-1.99', True), (dict(c2=2.01), 'nwell-2.01', True),
                               ({}, 'nwell-2.0', False)]:
                emit(rp + 'E2', lab, pnp(**kw)[0], f,
                     'exact: (SIZE PNP_B BY 2, filled) edges must be COIN with PNP_PWELL (= NWELL edge).')
            for c3, f in [(4.5, False), (4.49, True), (4.51, True), (6.0, True)]:
                emit(rp + 'E3', f'bjt-{c3}', pnp(c3=c3)[0], f,
                     f'exact per body (PDF: >=4.5): SIZE PNP_C BY 4.5 filled XOR BJT; BJT at {c3} from collector.')
        else:
            for kw, lab, f in [(dict(c1i=4.5, c1o=4.5), 'collector-4.5-both', False),
                               (dict(c1i=4.49), 'collector-to-base-pwell-4.49', True),
                               (dict(c1o=4.49), 'collector-to-outer-pwell-4.49', True),
                               (dict(c1i=4.51, c1o=4.51), 'collector-4.51-both', False),
                               (dict(c1i=3.0), 'collector-to-base-pwell-3.0', True)]:
                emit(rp + 'E1', lab, npn(**kw)[0], f,
                     'EXT NPN_C NPN_WELL < 4.5 (min only since 2025-03-10). NPN_WELL = BJT AND PWELL is both '
                     'the base PWELL hole and the BJT ring outside NWELL, so both sides are measured.')
            for kw, lab, f in [(dict(c2=1.99), 'pwell-1.99', True), (dict(c2=2.01), 'pwell-2.01', True),
                               ({}, 'pwell-2.0', False)]:
                emit(rp + 'E2', lab, npn(**kw)[0], f,
                     'exact: (SIZE NPN_B BY 2, filled) edges must be COIN with NPN_C_WELL (NWELL inner edge).')
            emit(rp + 'E2', 'pwell-1.99-child-rotated', npn(c2=1.99)[0], True,
                 'hierarchical copy of pwell-1.99', hierarchy=True)
            for c3, f in [(1.0, False), (0.99, True), (1.01, False), (0.5, True)]:
                emit(rp + 'E3', f'bjt-enc-nwell-{c3}', npn(c3=c3)[0], f,
                     f'ENC NPN_C_WELL BJT < 1.0; BJT beyond NWELL outer edge {c3}.')
        imp_e, imp_b, imp_c = ('PSD', 'NSD', 'PSD') if fam == 'PNP' else ('NSD', 'PSD', 'NSD')
        for kw, lab, f in [({}, 'all-1.0', False), (dict(c4e=0.99), f'emitter-{imp_e}-0.99', True),
                           (dict(c4b=(0.99, 1)), f'base-{imp_b}-inner-0.99', True),
                           (dict(c4b=(1, 0.99)), f'base-{imp_b}-outer-0.99', True),
                           (dict(c4c=(0.99, 1)), f'collector-{imp_c}-inner-0.99', True),
                           (dict(c4e=1.5), f'emitter-{imp_e}-1.5', False)]:
            emit(rp + 'E4', lab, build(**kw)[0], f,
                 'ENC (E/B/C) by the implant piece interacting it < 1.0.')

    # PNP / NPN arrays and the 2025-03-10 E1 revision
    def pnp_array(c1=4.5, gap=None):
        s1, g1 = pnp(c1=c1, bjt=False)
        Co = g1['Co']
        if gap is None:   # shared collector bar
            dx = Co[2] - Co[0] - 2000
        else:
            dx = Co[2] - Co[0] + nm(gap)
        s2, g2 = pnp(c1=c1, bjt=False, ox=um(dx))
        bj = (g1['BJT'][0], g1['BJT'][1], g2['BJT'][2], g2['BJT'][3])
        return s1 + s2 + [rect(BJT, bj)]
    emit('16.PNP.E1', 'array-shared-collector-4.5', pnp_array(), False,
         'BJT ARRAY: two PNPs share one collector bar (merged collector with two holes), one BJT box. '
         '2025-03-10 revision excluded array patterns; min spacing 4.5 kept -> expect 0.')
    emit('16.PNP.E1', 'array-separate-collectors-gap-3', pnp_array(gap=3), False,
         'BJT ARRAY: separate collector rings 3.0 apart inside one BJT box: the PWELL span between NWELLs '
         'is 4.5+2+3+2+4.5 = 16 (> 11, would have hit the commented-out WITH WIDTH > 11 form) -> expect 0.')
    emit('16.PNP.E1', 'array-shared-collector-4.49', pnp_array(c1=4.49), True,
         'BJT ARRAY with collector 4.49 from both NWELLs: the min check still applies.')

    def npn_array(c1=4.5):
        s1, g1 = npn(c1i=c1, c1o=c1, bjt=False)
        Co = g1['Co']
        dx = Co[2] - Co[0] - 2000
        s2, g2 = npn(c1i=c1, c1o=c1, bjt=False, ox=um(dx))
        bj = (g1['BJT'][0], g1['BJT'][1], g2['BJT'][2], g2['BJT'][3])
        return s1 + s2 + [rect(BJT, bj)]
    emit('17.NPN.E1', 'array-shared-collector-4.5', npn_array(), False,
         'BJT ARRAY: two NPNs share one collector bar and merged NWELL rings, one BJT box -> expect 0.')
    emit('17.NPN.E1', 'array-shared-collector-4.49', npn_array(4.49), True,
         'BJT ARRAY with collector 4.49 from the PWELL pieces.')
    emit('16.PNP.S', 'no-bjt-marker-4.0', pnp(b=(4,) * 4, bjt=False)[0], False,
         'RECOGNITION PROBE: without BJT no PNP_E exists, so a 4.0 spacing is not checked.')
    emit('17.NPN.S', 'no-bjt-marker-4.0', npn(b=(4,) * 4, bjt=False)[0], False,
         'RECOGNITION PROBE: without BJT no NPN_E exists.')

    # ---------------- 19.IO ----------------
    I = '19.IO.'
    for nf, W, f, lab in [(12, 60, False, '12x60-720'), (11, 65.45, True, '11x65.45-719.95'),
                          (11, 65.46, False, '11x65.46-720.06'), (2, 60, True, '2x60-120')]:
        emit(I + 'W1', lab, esd_mos(nf=nf, W=W)[0], f,
             f'DFM PROPERTY sum(gate side edges)/2 per ESD active < 720; {nf} fingers x {W}.')
    s1, g1 = esd_mos(nf=6, esd=False)
    s2, _ = esd_mos(nf=6, esd=False, ox=um(g1['act'][2]) + 10)
    emit(I + 'W1', 'two-actives-6x60-each', s1 + s2 + [rect(ESD, grow(bbox(s1 + s2), 3000))], True,
         'total 720 split over two separate ESD actives -> each TR_ACT polygon sums 360.')
    for nf, W, f, lab in [(12, 60, False, '60'), (13, 59.99, True, '59.99'), (12, 60.01, False, '60.01'),
                          (24, 30, True, '30')]:
        emit(I + 'W2', f'unit-finger-{lab}', esd_mos(nf=nf, W=W)[0], f,
             f'S/D pieces (PEACT OR NEACT) NOT POLY1 without an edge >= 60; {nf} fingers x {W} '
             '(finger count keeps total W >= 720).')
    for m, f in [(6.0, False), (5.99, True), (6.01, False), (3.0, True)]:
        emit(I + 'W4', f'drain-met1-{m}', esd_mos(m1d=m)[0], f,
             f'INT (MET1 INTERACT drain contacts) < 6; drain MET1 strip width {m}.')
    for d, f in [(8.6, False), (8.58, True), (8.62, False), (6.6, True)]:
        emit(I + 'S1', f'dcgs-{round((d - 0.6) / 2, 2)}', esd_mos(drn=d)[0], f,
             f'EXT ESD_GATE (CONT AND ESD_D) < 4; drain width {d}, contact centred.')
    emit(I + 'S1', 'dcgs-3.99-child-rotated', esd_mos(drn=8.58)[0], True,
         'hierarchical copy of dcgs-3.99', hierarchy=True)
    emit(I + 'S1', 'no-esdd-dcgs-3.0', esd_mos(drn=6.6, esdd=False)[0], False,
         'RECOGNITION PROBE: without ESDD there is no ESD_D, so drain contacts are not checked by S1 '
         '(they become ESD_S contacts for S2, which they pass).')
    for sw, f in [(2.6, False), (2.58, True), (2.62, False), (1.6, True)]:
        emit(I + 'S2', f'scgs-{round((sw - 0.6) / 2, 2)}', esd_mos(src=sw)[0], f,
             f'EXT (CONT AND ESD_S) ESD_GATE < 1; source width {sw}, contact centred (outer sources too).')
    for c, f in [(0.8, False), (0.79, True), (0.81, False), (0.6, True)]:
        emit(I + 'S3', f'cont-space-{c}', esd_mos(cs=c)[0], f, f'EXT (CONT AND ESD) < 0.8; column spacing {c}.')
    for kw, lab, f in [({}, 'cont-enc-1.0', False), (dict(cy0=0.99), 'cont-enc-bottom-0.99', True),
                       (dict(e1x=0.99), 'cont-enc-outer-side-0.99', True), (dict(cy0=1.01), 'cont-enc-bottom-1.01', False)]:
        emit(I + 'E1', lab, esd_mos(**kw)[0], f,
             'ENC (contacts inside the ESD transistor ACT) EACT < 1.0.')
    for kw, lab, f in [({}, 'nsd-1.0', False), (dict(imp=0.99), 'nsd-0.99', True), (dict(imp=1.01), 'nsd-1.01', False),
                       (dict(ptype=True), 'psd-1.0-pmos', False), (dict(ptype=True, imp=0.99), 'psd-0.99-pmos', True)]:
        emit(I + 'E2', lab, esd_mos(**kw)[0], f, 'ENC ESD_ACT NSD/PSD < 1.0.')
    emit(I + 'E2', 'no-esd-marker-nsd-0.5', esd_mos(imp=0.5, esd=False)[0], False,
         'RECOGNITION PROBE: without the ESD marker ESD_ACT is empty.')

    # ---------------- 20.LU ----------------
    U = '20.LU.'
    for e, lab, f in [((2, 2), '14.0', False), ((1, 1), '12.0', False), ((1, 0.99), '11.99', True),
                      ((1, 1.01), '12.01', False), ((0.5, 0.5), '11.0', True)]:
        emit(U + 'W1', f'nwell-{lab}', lu(e1=e)[0], f,
             f'WITH WIDTH ESD_TAP_NWELL < 12; dummy-collector NWELL width {lab} around a 10 um N+ tap '
             '(enclosure < 2 also fires 20.LU.E1/E2 by construction).')
    for kw, lab, f in [({}, 'pd-10', False), (dict(wPD=9.99), 'pd-9.99', True), (dict(wPD=10.01), 'pd-10.01', False),
                       (dict(wPD=5), 'pd-5', True), (dict(wND=9.99), 'nd-9.99', True)]:
        emit(U + 'W2', lab, lu(**kw)[0], f, 'WITH WIDTH ESD_TAP_ACT < 10 (all taps in ESD).')
    emit(U + 'W2', 'no-esd-marker-pd-5', lu(wPD=5, esd=False)[0], False,
         'RECOGNITION PROBE: without ESD no ESD_TAP_ACT.')
    for v, f in [(5, False), (4.99, True), (5.01, False), (3, True)]:
        emit(U + 'S1', f'guard-to-dummy-{v}', lu(s1=v)[0], f,
             f'EXT ESD_TAP_PACT (N+ tap in the PMOS NWELL) < 5; P+ dummy collector {v} from the N+ guard ring.')
    emit(U + 'S1', 'guard-to-dummy-4.99-child-rotated', lu(s1=4.99)[0], True,
         'hierarchical copy of guard-to-dummy-4.99', hierarchy=True)
    for kw, lab, f in [({}, 'left-5', False), (dict(s2=4.99), 'left-4.99', True), (dict(s2=5.01), 'left-5.01', False),
                       (dict(s2=3), 'left-3', True), (dict(s2r=4.99), 'right-4.99', True)]:
        emit(U + 'S2', lab, lu(**kw)[0], f,
             'EXT ESD_TAP_PACT (gate-free ESD tap NWELL) < 5; P+ tap to dummy-collector NWELL.')
    for v, f in [(1, False), (0.99, True), (1.01, False), (0.5, True)]:
        emit(U + 'S3', f'p-act-to-n-guard-{v}', lu(g3=v)[0], f,
             f'EXT PEACT ESD_TAP_NACT < 1; PMOS ACT to N+ guard ring {v} (implants meet midway; 19.IO.E2 also fires).')
    for v, f in [(1, False), (0.99, True), (1.01, False), (0.5, True)]:
        emit(U + 'S4', f'n-act-to-p-guard-{v}', lu(g4=v)[0], f,
             f'EXT NEACT ESD_TAP_PACT < 1; NMOS ACT to P+ guard ring {v}.')
    for v, f in [(2, False), (1.99, True), (2.01, False), (1, True)]:
        emit(U + 'E1', f'dummy-collector-enc-{v}', lu(e1=(v, v))[0], f,
             f'ENC ESD_TAP_NACT ESD_TAP_NWELL < 2; N+ dummy collector NWELL enclosure {v} (left/right).')
    for v, f in [(2, False), (1.99, True), (2.01, False), (1, True)]:
        emit(U + 'E2', f'guard-ring-enc-{v}', lu(e2=v)[0], f,
             f'same body as E1; N+ guard ring enclosure by the PMOS NWELL right edge {v}.')

    # ---------------- 22.PNW ----------------
    P = '22.PNW.'
    for (w, h), f in [((2, 2), False), ((20, 20), False), ((2, 20), False), ((10, 10), False),
                      ((1.99, 10), True), ((20.01, 10), True), ((1, 1), True), ((25, 25), True)]:
        emit(P + 'W1', f'anode-{w}x{h}', pnw(aw=w, ah=h)[0], f,
             f'LENGTH NWDIO_PANO < 2 or > 20; anode {w}x{h}.')
    for a2, f in [(2, False), (1.99, True), (2.01, True)]:
        emit(P + 'W2', f'cathode-{a2}', pnw(a2=a2)[0], f, 'exact 2.0 N+ ring width.')
    for b, lab, f in [((4.5,) * 4, '4.5', False), ((4.49,) * 4, '4.49', True), ((4.51,) * 4, '4.51', True),
                      ((4.49, 4.5, 4.51, 4.5), 'off-centre-0.01', True)]:
        emit(P + 'S', f'anode-cathode-{lab}', pnw(b=b)[0], f, 'exact 4.5 (EXT ==4.5 OPPOSITE edge cover).')
    for c1, f in [(2, False), (1.99, True), (2.01, True)]:
        emit(P + 'E1', f'nwell-{c1}', pnw(c1=c1)[0], f,
             'exact: (SIZE cathode BY 2, filled) edges must be COIN with NWELL AND DIODE (DIODE follows NWELL).')
    emit(P + 'E1', 'nwell-1.99-child-rotated', pnw(c1=1.99)[0], True, 'hierarchical copy of nwell-1.99',
         hierarchy=True)
    for kw, lab, f in [({}, 'implants-1.0', False), (dict(c2a=0.99), 'psd-0.99', True), (dict(c2a=1.01), 'psd-1.01', True),
                       (dict(c2n=(1, 1.01)), 'nsd-outer-1.01', True), (dict(c2n=(0.99, 1)), 'nsd-inner-0.99', True)]:
        emit(P + 'E2', lab, pnw(**kw)[0], f, 'exact: SIZE (DIODE_ACT AND NWELL) BY 1 edges must be COIN with implants.')
    for d, lab, f in [((0, 0, 0, 0), 'diode-equals-nwell', False), ((0.01, 0.01, 0.01, 0.01), 'diode-0.01-larger', True),
                      ((-0.01, 0, 0, 0), 'diode-0.01-short-left', True)]:
        emit(P + 'bad1', lab, pnw(diode=d)[0], f, 'NWELL edges (interacting DIODE) not COIN with DIODE edges.')

    # ---------------- 23.NPW ----------------
    N = '23.NPW.'
    for (w, h), f in [((2, 2), False), ((20, 20), False), ((2, 20), False), ((10, 10), False),
                      ((1.99, 10), True), ((20.01, 10), True), ((1, 1), True), ((25, 25), True)]:
        emit(N + 'W1', f'cathode-{w}x{h}', npw(cw=w, ch=h)[0], f, f'LENGTH PWDIO_NANO < 2 or > 20; cathode {w}x{h}.')
    emit(N + 'W1', 'no-diode-marker-1x1', npw(cw=1, ch=1, marker=False)[0], False,
         'RECOGNITION PROBE: without DIODE there is no PWDIO_NANO.')
    for a2, f in [(2, False), (1.99, True), (2.01, True)]:
        emit(N + 'W2', f'anode-{a2}', npw(a2=a2)[0], f, 'exact 2.0 P+ ring width.')
    for b, lab, f in [((4.5,) * 4, '4.5', False), ((4.49,) * 4, '4.49', True), ((4.51,) * 4, '4.51', True),
                      ((4.49, 4.5, 4.51, 4.5), 'off-centre-0.01', True)]:
        emit(N + 'S', f'cathode-anode-{lab}', npw(b=b)[0], f, 'exact 4.5 (EXT ==4.5 OPPOSITE edge cover).')
    emit(N + 'S', 'cathode-anode-4.49-child-rotated', npw(b=(4.49,) * 4)[0], True,
         'hierarchical copy of cathode-anode-4.49', hierarchy=True)
    for kw, lab, f in [({}, 'implants-1.0', False), (dict(c1n=0.99), 'nsd-0.99', True), (dict(c1n=1.01), 'nsd-1.01', True),
                       (dict(c1p=(1, 1.01)), 'psd-outer-1.01', True), (dict(c1p=(0.99, 1)), 'psd-inner-0.99', True)]:
        emit(N + 'E', lab, npw(**kw)[0], f, 'exact: SIZE (DIODE_ACT NOT NWELL) BY 1 edges must be COIN with implants.')

    labels = set()
    for case, _ in out:
        key = (case['rule'], case['label'])
        if key in labels:
            raise ValueError('duplicate label %s %s' % key)
        labels.add(key)
    return out


def cases():
    return [case for case, _ in cases_with_meta()]


if __name__ == '__main__':
    import collections
    items = cases_with_meta()
    by_rule = collections.Counter(c['rule'] for c, _ in items)
    missing = sorted(set(DECK_LINE) - set(by_rule))
    print(len(items), 'fixtures,', len(by_rule), 'rules; missing:', missing)
    for rule in DECK_LINE:
        fs = [c['fail'] for c, _ in items if c['rule'] == rule]
        if fs and (all(fs) or not any(fs)):
            print('one-sided:', rule)
