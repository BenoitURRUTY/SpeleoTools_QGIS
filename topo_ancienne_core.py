# -*- coding: utf-8 -*-
"""
SpeleoTools — Numérisation de topographies anciennes : cœur de calcul.

Ce module ne dépend PAS de QGIS (Python pur + math) afin de pouvoir être
testé hors QGIS (voir tests/test_topo_ancienne_core.py).

Conventions
-----------
* Coordonnées « pixel » : (col, row) continues, origine au coin haut-gauche
  de l'image, row vers le bas.  En interne on travaille en (u, v) = (col, -row)
  pour que la similitude soit une vraie rotation (pas une symétrie).
* Plan  : coordonnées terrain (x, y) dans le SCR du projet.
* Coupe : repère (X, Z) avec X = abscisse horizontale (m), Z = altitude (m).
* Azimuts en degrés, sens horaire depuis le nord (convention topo).
"""

import math

# ═══════════════════════════════════════════════════════════════════════
#   1) CALAGE : similitude 2D (Helmert 4 paramètres)
# ═══════════════════════════════════════════════════════════════════════

class Similarity:
    """Transformation  x = a·u − b·v + tx ;  y = b·u + a·v + ty
    avec (u, v) = (col, −row).  a = s·cosφ, b = s·sinφ."""

    def __init__(self, a=1.0, b=0.0, tx=0.0, ty=0.0):
        self.a, self.b, self.tx, self.ty = float(a), float(b), float(tx), float(ty)

    # --- propriétés -----------------------------------------------------
    @property
    def scale(self):
        return math.hypot(self.a, self.b)

    @property
    def rotation_deg(self):
        """Rotation trigonométrique (anti-horaire) en degrés."""
        return math.degrees(math.atan2(self.b, self.a))

    # --- application ----------------------------------------------------
    def apply_uv(self, u, v):
        return (self.a * u - self.b * v + self.tx,
                self.b * u + self.a * v + self.ty)

    def apply_pixel(self, col, row):
        return self.apply_uv(col, -row)

    def inverse_to_pixel(self, x, y):
        s2 = self.a ** 2 + self.b ** 2
        dx, dy = x - self.tx, y - self.ty
        u = (self.a * dx + self.b * dy) / s2
        v = (-self.b * dx + self.a * dy) / s2
        return u, -v

    def geotransform(self):
        """GeoTransform GDAL (coin haut-gauche) :
        x = GT0 + col·GT1 + row·GT2 ;  y = GT3 + col·GT4 + row·GT5"""
        return (self.tx, self.a, self.b, self.ty, self.b, -self.a)

    def world_file_lines(self):
        """Contenu d'un fichier .wld (centre du pixel haut-gauche)."""
        cx, cy = self.apply_pixel(0.5, 0.5)
        return [self.a, self.b, self.b, -self.a, cx, cy]

    def __repr__(self):
        return ("Similarity(échelle=%.5f m/px, rotation=%.3f°, t=(%.3f, %.3f))"
                % (self.scale, self.rotation_deg, self.tx, self.ty))

    # --- constructeurs --------------------------------------------------
    @classmethod
    def from_rotation_scale(cls, phi_deg, scale, src_pixel, dst_xy):
        """Similitude de rotation φ (anti-horaire), échelle s, telle que
        le pixel src_pixel=(col,row) arrive en dst_xy=(x,y)."""
        phi = math.radians(phi_deg)
        a, b = scale * math.cos(phi), scale * math.sin(phi)
        t = cls(a, b, 0.0, 0.0)
        x0, y0 = t.apply_pixel(*src_pixel)
        t.tx, t.ty = dst_xy[0] - x0, dst_xy[1] - y0
        return t

    @classmethod
    def from_two_points(cls, px1, px2, xy1, xy2):
        """Calage exact sur deux points homologues (pixel → terrain)."""
        u1, v1 = px1[0], -px1[1]
        u2, v2 = px2[0], -px2[1]
        du, dv = u2 - u1, v2 - v1
        dx, dy = xy2[0] - xy1[0], xy2[1] - xy1[1]
        d2 = du * du + dv * dv
        if d2 < 1e-12:
            raise ValueError("Les deux points image sont confondus.")
        a = (du * dx + dv * dy) / d2
        b = (du * dy - dv * dx) / d2
        t = cls(a, b)
        x0, y0 = t.apply_uv(u1, v1)
        t.tx, t.ty = xy1[0] - x0, xy1[1] - y0
        return t

    @classmethod
    def from_least_squares(cls, pixels, xys):
        """Calage par moindres carrés sur ≥ 2 points. Retourne (T, résidus)."""
        n = len(pixels)
        if n < 2 or n != len(xys):
            raise ValueError("Il faut au moins 2 couples de points.")
        if n == 2:
            t = cls.from_two_points(pixels[0], pixels[1], xys[0], xys[1])
            return t, [0.0, 0.0]
        us = [p[0] for p in pixels]
        vs = [-p[1] for p in pixels]
        um, vm = sum(us) / n, sum(vs) / n
        xm = sum(q[0] for q in xys) / n
        ym = sum(q[1] for q in xys) / n
        num_a = num_b = den = 0.0
        for u, v, (x, y) in zip(us, vs, xys):
            du, dv, dx, dy = u - um, v - vm, x - xm, y - ym
            num_a += du * dx + dv * dy
            num_b += du * dy - dv * dx
            den += du * du + dv * dv
        if den < 1e-12:
            raise ValueError("Points image confondus.")
        t = cls(num_a / den, num_b / den)
        x0, y0 = t.apply_uv(um, vm)
        t.tx, t.ty = xm - x0, ym - y0
        res = []
        for p, (x, y) in zip(pixels, xys):
            xc, yc = t.apply_pixel(*p)
            res.append(math.hypot(xc - x, yc - y))
        return t, res


def pixel_azimuth(px1, px2):
    """Azimut (horaire depuis le haut de l'image) du vecteur px1 → px2."""
    du = px2[0] - px1[0]
    dv = -(px2[1] - px1[1])
    return math.degrees(math.atan2(du, dv)) % 360.0


def pixel_distance(px1, px2):
    return math.hypot(px2[0] - px1[0], px2[1] - px1[1])


def plan_calibration_scale_north(entry_px, entry_xy, scale_px1, scale_px2,
                                 scale_length, north_px1, north_px2,
                                 north_azimuth=0.0):
    """Calage « historique » d'un plan : entrée connue + barre d'échelle +
    flèche nord.

    north_azimuth : azimut RÉEL (dans le SCR du projet) vers lequel pointe
    la flèche dessinée.  Pour une flèche Nord magnétique :
        north_azimuth = déclinaison(date du levé) − convergence des méridiens.
    """
    d = pixel_distance(scale_px1, scale_px2)
    if d < 1e-9:
        raise ValueError("Barre d'échelle : les deux clics sont confondus.")
    if scale_length <= 0:
        raise ValueError("Longueur de la barre d'échelle invalide.")
    if pixel_distance(north_px1, north_px2) < 1e-9:
        raise ValueError("Flèche nord : les deux clics sont confondus.")
    s = scale_length / d
    az_px = pixel_azimuth(north_px1, north_px2)
    # azimut réel = azimut image + rot (horaire) ; φ trigo = −rot
    rot = north_azimuth - az_px
    return Similarity.from_rotation_scale(-rot, s, entry_px, entry_xy)


NORD_GRILLE, NORD_GEO, NORD_MAGNETIQUE = "grille", "geographique", "magnetique"


def north_arrow_azimuth(kind, convergence=0.0, declination=0.0):
    """Azimut, dans le SCR projeté, de la direction indiquée par la flèche
    nord d'un plan ancien.

    kind        : 'grille' (nord du quadrillage), 'geographique', 'magnetique'
    convergence : convergence des méridiens γ au point considéré (°), au sens
                  classique gisement = azimut − γ (positive à l'est du méridien
                  central d'une projection conique conforme comme le Lambert-93)
    declination : déclinaison magnétique D à la date du levé (°, est positif)

    Nord de la grille → 0 ; nord géographique → −γ ; nord magnétique → D − γ.
    """
    if kind == NORD_GRILLE:
        return 0.0
    if kind == NORD_GEO:
        return -float(convergence)
    if kind == NORD_MAGNETIQUE:
        return float(declination) - float(convergence)
    raise ValueError("Type de nord inconnu : %r" % (kind,))


def section_calibration(ref_px, ref_xz, scale_px1, scale_px2, scale_length,
                        bar_is_horizontal=True):
    """Calage d'une coupe : barre d'échelle + point de référence (X, Z).

    Si bar_is_horizontal, l'inclinaison de la barre sert à redresser un
    scan penché ; sinon on suppose le scan droit."""
    d = pixel_distance(scale_px1, scale_px2)
    if d < 1e-9:
        raise ValueError("Barre d'échelle : les deux clics sont confondus.")
    if scale_length <= 0:
        raise ValueError("Longueur de la barre d'échelle invalide.")
    s = scale_length / d
    phi = 0.0
    if bar_is_horizontal:
        du = scale_px2[0] - scale_px1[0]
        dv = -(scale_px2[1] - scale_px1[1])
        if du < 0:                       # sens du clic indifférent
            du, dv = -du, -dv
        phi = -math.degrees(math.atan2(dv, du))
    return Similarity.from_rotation_scale(phi, s, ref_px, ref_xz)


# ═══════════════════════════════════════════════════════════════════════
#   2) OUTILS GÉOMÉTRIQUES
# ═══════════════════════════════════════════════════════════════════════

def cumulative_lengths(pts):
    """Longueurs cumulées 2D le long d'une liste de (x, y)."""
    out = [0.0]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        out.append(out[-1] + math.hypot(x1 - x0, y1 - y0))
    return out


def _clean_name(n):
    if n is None:
        return ""
    s = str(n).strip()
    return "" if s.upper() in ("", "NULL", "NONE") else s


def _interp_piecewise(x, xs, ys):
    """Interpolation linéaire par morceaux ; au-delà des bornes,
    prolongement de pente 1 depuis l'ancrage le plus proche."""
    if len(xs) == 1:
        return ys[0] + (x - xs[0])
    if x <= xs[0]:
        return ys[0] + (x - xs[0])
    if x >= xs[-1]:
        return ys[-1] + (x - xs[-1])
    for k in range(len(xs) - 1):
        if xs[k] <= x <= xs[k + 1]:
            dx = xs[k + 1] - xs[k]
            if dx <= 1e-12:
                return ys[k]
            return ys[k] + (x - xs[k]) * (ys[k + 1] - ys[k]) / dx
    return ys[-1]


def _linear_fit(ts, xs):
    n = len(ts)
    tm, xm = sum(ts) / n, sum(xs) / n
    den = sum((t - tm) ** 2 for t in ts)
    if den < 1e-12:
        return None
    a = sum((t - tm) * (x - xm) for t, x in zip(ts, xs)) / den
    return a, xm - a * tm


# ═══════════════════════════════════════════════════════════════════════
#   3) APPARIEMENT PLAN ↔ COUPE ET CALCUL DES ALTITUDES
# ═══════════════════════════════════════════════════════════════════════

MODE_DEVELOPPEE = "developpee"
MODE_PROJETEE = "projetee"


def find_anchors(plan_names, coupe_names, pair_by_order=False, log=None):
    """Couples (i_plan, j_coupe).  Priorité : noms identiques ; sinon ordre
    (si demandé et même nombre de sommets) ; sinon (0, 0) (entrée).
    Les couples non monotones sont écartés."""
    log = log or (lambda m: None)
    cidx = {}
    for j, n in enumerate(coupe_names):
        n = _clean_name(n)
        if n and n not in cidx:
            cidx[n] = j
    anchors = []
    for i, n in enumerate(plan_names):
        n = _clean_name(n)
        if n and n in cidx:
            anchors.append((i, cidx[n]))

    if not anchors and pair_by_order:
        if len(plan_names) == len(coupe_names):
            anchors = [(i, i) for i in range(len(plan_names))]
            log("Appariement par ordre des sommets (%d couples)." % len(anchors))
        else:
            log("⚠ Appariement par ordre impossible : %d sommets plan / %d sommets coupe."
                % (len(plan_names), len(coupe_names)))

    if not anchors:
        anchors = [(0, 0)]
        log("Aucun nom commun : 1er sommet du plan ↔ 1er sommet de la coupe.")
    else:
        log("%d station(s) appariée(s)." % len(anchors))

    # monotonie : on garde les couples dont j croît avec i (filtre glouton)
    anchors.sort()
    kept = []
    for i, j in anchors:
        if not kept or j > kept[-1][1]:
            kept.append((i, j))
        else:
            log("⚠ Appariement %s ignoré (ordre incohérent entre plan et coupe)."
                % (_clean_name(plan_names[i]) or i))
    return kept


def _search_on_section(target_x, coupe, c_path, j_lo, j_hi, frac_plan, tol):
    """Cherche sur la coupe (sommets j_lo..j_hi) le point d'abscisse X =
    target_x dont la position curviligne relative est la plus proche de
    frac_plan (0..1).  Retourne (z, j_segment, t) ou None."""
    if j_hi <= j_lo:
        return None
    span = c_path[j_hi] - c_path[j_lo]
    best = None
    for j in range(j_lo, j_hi):
        (xa, za), (xb, zb) = coupe[j], coupe[j + 1]
        lo, hi = min(xa, xb) - tol, max(xa, xb) + tol
        if not (lo <= target_x <= hi):
            continue
        seg_len = c_path[j + 1] - c_path[j]
        if abs(xb - xa) < 1e-9:
            # segment vertical (puits) : tout le segment est candidat
            t_lo, t_hi = 0.0, 1.0
        else:
            t = (target_x - xa) / (xb - xa)
            t = min(1.0, max(0.0, t))
            t_lo = t_hi = t
        # t optimal pour rapprocher la fraction coupe de frac_plan
        if span > 1e-9 and seg_len > 1e-9:
            t_star = ((frac_plan * span) - (c_path[j] - c_path[j_lo])) / seg_len
        else:
            t_star = t_lo
        t_opt = min(t_hi, max(t_lo, t_star))
        f_c = ((c_path[j] - c_path[j_lo]) + t_opt * seg_len) / span if span > 1e-9 else 0.0
        score = abs(f_c - frac_plan)
        if best is None or score < best[0] - 1e-12:
            best = (score, za + t_opt * (zb - za), j, t_opt)
    if best is None:
        return None
    return best[1], best[2], best[3]


def compute_altitudes(plan_xy, plan_names, coupe_xz, coupe_names,
                      mode=MODE_DEVELOPPEE, section_azimuth=0.0,
                      invert_axis=False, pair_by_order=False,
                      plan_z=None, fixed_z=None, tolerance=0.5,
                      default_z=None, log=None):
    """Calcule l'altitude de chaque sommet du tracé plan.

    plan_xy      : [(x, y)]            sommets de la polygonale en plan
    plan_names   : [str]               noms des stations (peut être vide)
    coupe_xz     : [(X, Z)]            sommets de la polygonale en coupe
                                       (liste vide = pas de coupe)
    coupe_names  : [str]
    mode         : 'developpee' | 'projetee'
    section_azimuth : direction de projection α (°, comme Therion
                      « elevation α ») — l'axe horizontal de la coupe est
                      orienté à α + 90°.
    plan_z       : [z ou None]  cotes lues sur le plan
    fixed_z      : {nom: z}     altitudes imposées (jonctions déjà calculées)
    tolerance    : tolérance (m) sur l'abscisse pour accrocher la coupe
    default_z    : altitude utilisée si aucune information n'existe

    Retour : liste de dict par station :
        z, source ('plan'|'jonction'|'coupe'|'interp'|'extrap'|'defaut'|None),
        z_plan, z_coupe, dz_plan_coupe, abscisse, dist_plan
    """
    log = log or (lambda m: None)
    n = len(plan_xy)
    plan_names = list(plan_names) if plan_names else [""] * n
    plan_z = list(plan_z) if plan_z else [None] * n
    fixed_z = fixed_z or {}
    d = cumulative_lengths(plan_xy)

    out = [dict(z=None, source=None, z_plan=plan_z[i], z_coupe=None,
                dz_plan_coupe=None, abscisse=None, dist_plan=d[i])
           for i in range(n)]

    # ── altitudes issues de la coupe ─────────────────────────────────
    if coupe_xz and len(coupe_xz) >= 2:
        coupe_names = list(coupe_names) if coupe_names else [""] * len(coupe_xz)
        c_path = cumulative_lengths(coupe_xz)
        anchors = find_anchors(plan_names, coupe_names, pair_by_order, log)

        # abscisse « brute » de chaque station
        if mode == MODE_PROJETEE:
            beta = math.radians(section_azimuth + 90.0)
            sx, sy = math.sin(beta), math.cos(beta)
            x0, y0 = plan_xy[0]
            raw = [(x - x0) * sx + (y - y0) * sy for x, y in plan_xy]
            if invert_axis:
                raw = [-r for r in raw]
        else:
            raw = list(d)

        # passage abscisse brute → X coupe
        a_t = [raw[i] for i, _ in anchors]
        a_x = [coupe_xz[j][0] for _, j in anchors]
        if mode == MODE_PROJETEE:
            fit = _linear_fit(a_t, a_x) if len(anchors) >= 2 else None
            if fit is not None:
                ka, kb = fit
                log("Axe de coupe ajusté : X = %.3f·s %+.2f" % (ka, kb))
                if ka < 0:
                    log("⚠ Coefficient négatif : cochez « Inverser le sens de la coupe ».")
                if abs(abs(ka) - 1.0) > 0.15:
                    log("⚠ Échelle plan/coupe différente de %.0f %% — vérifier les calages "
                        "ou l'azimut de projection." % (abs(abs(ka) - 1.0) * 100))
                target = [ka * r + kb for r in raw]
            else:
                i0, j0 = anchors[0]
                target = [coupe_xz[j0][0] + (r - raw[i0]) for r in raw]
        else:
            # piecewise sur les ancrages (triés par distance plan)
            pairs = sorted(zip(a_t, a_x))
            xs = [p[0] for p in pairs]
            ys = [p[1] for p in pairs]
            target = [_interp_piecewise(r, xs, ys) for r in raw]
            if len(anchors) >= 2:
                ratio = ((ys[-1] - ys[0]) / (xs[-1] - xs[0])
                         if xs[-1] - xs[0] > 1e-9 else 1.0)
                log("Rapport longueur coupe / longueur plan entre ancrages : %.3f" % ratio)

        anchor_of = dict(anchors)
        for i in range(n):
            out[i]["abscisse"] = target[i]
            if i in anchor_of:
                out[i]["z_coupe"] = coupe_xz[anchor_of[i]][1]
                continue
            # ancrages encadrants
            prev = [(ia, ja) for ia, ja in anchors if ia < i]
            nxt = [(ia, ja) for ia, ja in anchors if ia > i]
            ip, jp = prev[-1] if prev else (None, 0)
            inx, jn = nxt[0] if nxt else (None, len(coupe_xz) - 1)
            if ip is not None and inx is not None and d[inx] - d[ip] > 1e-9:
                frac = (d[i] - d[ip]) / (d[inx] - d[ip])
            elif ip is not None:
                span = c_path[jn] - c_path[jp]
                frac = min(1.0, (d[i] - d[ip]) / span) if span > 1e-9 else 0.0
            elif inx is not None:
                span = c_path[jn] - c_path[jp]
                frac = max(0.0, 1.0 - (d[inx] - d[i]) / span) if span > 1e-9 else 1.0
            else:
                frac = 0.0
            hit = _search_on_section(target[i], coupe_xz, c_path, jp, jn, frac, tolerance)
            if hit is not None:
                out[i]["z_coupe"] = hit[0]

    # ── fusion des sources (priorité : jonction > plan > coupe) ────────
    for i in range(n):
        name = _clean_name(plan_names[i])
        r = out[i]
        if name and name in fixed_z and fixed_z[name] is not None:
            r["z"], r["source"] = float(fixed_z[name]), "jonction"
        elif r["z_plan"] is not None:
            r["z"], r["source"] = float(r["z_plan"]), "plan"
        elif r["z_coupe"] is not None:
            r["z"], r["source"] = float(r["z_coupe"]), "coupe"
        if r["z_plan"] is not None and r["z_coupe"] is not None:
            r["dz_plan_coupe"] = float(r["z_plan"]) - float(r["z_coupe"])

    # ── interpolation / extrapolation à pente constante ────────────────
    known = [i for i in range(n) if out[i]["z"] is not None]
    if not known:
        if default_z is None:
            log("⚠ Aucune altitude disponible (ni coupe, ni cote plan).")
            return out
        out[0]["z"], out[0]["source"] = float(default_z), "defaut"
        known = [0]
        log("⚠ Aucune altitude : 1re station fixée à %.2f m." % default_z)

    for i in range(n):
        if out[i]["z"] is not None:
            continue
        prev = [k for k in known if k < i]
        nxt = [k for k in known if k > i]
        if prev and nxt:
            a, b = prev[-1], nxt[0]
            span = d[b] - d[a]
            t = (d[i] - d[a]) / span if span > 1e-9 else 0.5
            out[i]["z"] = out[a]["z"] + t * (out[b]["z"] - out[a]["z"])
            out[i]["source"] = "interp"
        else:
            # extrapolation avec la pente du tronçon connu le plus proche
            if prev:
                a = prev[-1]
                b = prev[-2] if len(prev) >= 2 else None
            else:
                a = nxt[0]
                b = nxt[1] if len(nxt) >= 2 else None
            slope = 0.0
            if b is not None and abs(d[a] - d[b]) > 1e-9:
                slope = (out[a]["z"] - out[b]["z"]) / (d[a] - d[b])
            out[i]["z"] = out[a]["z"] + slope * (d[i] - d[a])
            out[i]["source"] = "extrap"
    return out


# ═══════════════════════════════════════════════════════════════════════
#   4) VISÉES ET EXPORT THERION
# ═══════════════════════════════════════════════════════════════════════

def shot_measures(p1, p2):
    """(longueur 3D, longueur horizontale, azimut °, pente °) entre deux
    points (x, y, z)."""
    dx, dy, dz = p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2]
    h = math.hypot(dx, dy)
    l3 = math.sqrt(h * h + dz * dz)
    az = math.degrees(math.atan2(dx, dy)) % 360.0
    clino = math.degrees(math.atan2(dz, h)) if l3 > 0 else 0.0
    return l3, h, az, clino


def therion_station_name(name, fallback):
    import re
    s = _clean_name(name) or fallback
    head, sep, tail = s.partition("@")          # station@survey (autre cavité)
    head = re.sub(r"[^A-Za-z0-9_\-]", "_", head)
    tail = re.sub(r"[^A-Za-z0-9_\-.]", "_", tail)
    s = head + (sep + tail if tail else "")
    return s or fallback


def therion_date(text):
    """Date Therion (AAAA[.MM[.JJ]]) ou None si le texte n'est pas conforme."""
    import re
    t = (text or "").strip().replace("-", ".").replace("/", ".")
    return t if re.fullmatch(r"\d{4}(\.\d{2}(\.\d{2})?)?", t) else None


def compare_to_reference(stations, reference):
    """Compare des stations reconstruites à un levé de référence.

    stations  : [{nom, x, y, z, source}]
    reference : {nom: (x, y, z)}  (z facultatif → None)
    Retour : (couples, stats) où couples est une liste de dict
    {nom, dx, dy, dz, d2d, d3d, source} et stats un résumé
    {n, moy_2d, max_2d, rms_2d, moy_dz, max_dz, rms_3d}."""
    couples = []
    for s in stations:
        ref = reference.get(s["nom"])
        if ref is None:
            continue
        dx, dy = s["x"] - ref[0], s["y"] - ref[1]
        dz = None if (len(ref) < 3 or ref[2] is None) else s["z"] - ref[2]
        d2d = math.hypot(dx, dy)
        couples.append(dict(nom=s["nom"], dx=dx, dy=dy, dz=dz, d2d=d2d,
                            d3d=None if dz is None else math.sqrt(d2d ** 2 + dz ** 2),
                            source=s.get("source")))
    if not couples:
        return couples, {"n": 0}
    d2 = [c["d2d"] for c in couples]
    dzs = [c["dz"] for c in couples if c["dz"] is not None]
    d3 = [c["d3d"] for c in couples if c["d3d"] is not None]
    stats = {
        "n": len(couples),
        "moy_2d": sum(d2) / len(d2),
        "max_2d": max(d2),
        "rms_2d": math.sqrt(sum(d * d for d in d2) / len(d2)),
    }
    if dzs:
        stats.update({
            "n_z": len(dzs),
            "moy_dz": sum(dzs) / len(dzs),
            "max_dz": max(dzs, key=abs),
            "rms_3d": math.sqrt(sum(d * d for d in d3) / len(d3)),
        })
    return couples, stats


def therion_centreline(survey_name, branches, crs_authid=None, title=None,
                       fix_first=True, date=None, team=None, header=None,
                       style="cartesian", convergence=0.0):
    """Construit le texte d'un fichier .th.

    branches : liste de listes de stations (dict nom, x, y, z, source).
    Les données sont écrites en style « cartesian » (dx, dy, dz) pour
    éviter toute ambiguïté de déclinaison magnétique.
    date     : date du levé d'origine (écrite si au format Therion)
    team     : liste de noms (topographes d'origine)
    header   : lignes de métadonnées écrites en commentaire
    style    : 'cartesian' (dx, dy, dz — aucune ambiguïté de déclinaison) ou
               'normal' (longueur, azimut, pente : spéléométrie lisible)
    convergence : convergence des méridiens γ (°), utilisée en style 'normal'
               pour convertir les gisements en azimuts vrais (azimut = G + γ),
               le fichier déclarant alors « declination 0 »"""
    sname = therion_station_name(survey_name, "topo_ancienne")
    lines = ["encoding utf-8",
             "# Généré par SpeleoTools — numérisation de topographie ancienne"]
    lines += ["# " + h for h in (header or [])]
    lines += ['survey %s -title "%s"' % (sname, (title or survey_name).replace('"', "'")),
              "",
              "  centreline"]
    d = therion_date(date)
    if d:
        lines.append("    date %s" % d)
    for person in team or []:
        person = person.strip().replace('"', "'")
        if person:
            lines.append('    team "%s"' % person)
    if crs_authid:
        lines.append("    cs %s" % crs_authid)
    first = None
    for br in branches:
        if br:
            first = br[0]
            break
    if fix_first and first is not None and crs_authid:
        lines.append("    fix %s %.3f %.3f %.3f" % (first["nom"], first["x"], first["y"], first["z"]))
    if style == "normal":
        lines.append("    # azimuts rapportés au nord géographique "
                     "(gisement + convergence %.3f°)" % convergence)
        lines.append("    declination 0.0 degrees")
        lines.append("    data normal from to length compass clino")
    else:
        lines.append("    data cartesian from to easting northing altitude")
    for bi, br in enumerate(branches):
        if len(br) < 2:
            continue
        lines.append("    # branche %d" % (bi + 1))
        for a, b in zip(br[:-1], br[1:]):
            origine = "   # z: %s → %s" % (a.get("source") or "?", b.get("source") or "?")
            if style == "normal":
                l3, _h, az, clino = shot_measures((a["x"], a["y"], a["z"]),
                                                  (b["x"], b["y"], b["z"]))
                lines.append("    %-10s %-10s %9.3f %9.2f %8.2f%s"
                             % (a["nom"], b["nom"], l3,
                                (az + convergence) % 360.0, clino, origine))
            else:
                lines.append("    %-10s %-10s %9.3f %9.3f %9.3f%s"
                             % (a["nom"], b["nom"], b["x"] - a["x"], b["y"] - a["y"],
                                b["z"] - a["z"], origine))
    lines += ["  endcentreline", "", "endsurvey", ""]
    return "\n".join(lines)
