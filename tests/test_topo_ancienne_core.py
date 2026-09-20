import math, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import topo_ancienne_core as c

def close(a, b, tol=1e-6):
    return abs(a - b) <= tol

def test_two_points_roundtrip():
    t = c.Similarity.from_two_points((10, 20), (110, 20), (1000, 5000), (1000, 5100))
    # 100 px vers la droite -> 100 m vers le nord : échelle 1, rotation +90°
    assert close(t.scale, 1.0) and close(t.rotation_deg, 90.0)
    x, y = t.apply_pixel(10, 120)       # 100 px vers le bas
    assert close(x, 1100) and close(y, 5000)
    col, row = t.inverse_to_pixel(x, y)
    assert close(col, 10) and close(row, 120)

def test_geotransform_consistent():
    t = c.Similarity.from_two_points((0, 0), (200, 50), (500, 700), (900, 650))
    gt = t.geotransform()
    for col, row in [(0, 0), (37, 91), (200, 50)]:
        x = gt[0] + col * gt[1] + row * gt[2]
        y = gt[3] + col * gt[4] + row * gt[5]
        xe, ye = t.apply_pixel(col, row)
        assert close(x, xe) and close(y, ye)

def test_least_squares_exact():
    t0 = c.Similarity.from_rotation_scale(33, 0.05, (0, 0), (900000, 6400000))
    pix = [(0, 0), (1000, 0), (500, 800), (30, 1200)]
    xys = [t0.apply_pixel(*p) for p in pix]
    t, res = c.Similarity.from_least_squares(pix, xys)
    assert max(res) < 1e-6 and close(t.scale, 0.05) and close(t.rotation_deg, 33)

def test_scale_north():
    # flèche dessinée vers le haut, nord magnétique = -2° ; 10 m = 200 px
    t = c.plan_calibration_scale_north((100, 100), (1000, 2000), (0, 500), (200, 500), 10.0,
                                       (50, 50), (50, 10), north_azimuth=-2.0)
    assert close(t.scale, 0.05)
    x, y = t.apply_pixel(100, 0)        # 100 px au-dessus de l'entrée = 5 m direction flèche
    az = math.degrees(math.atan2(x - 1000, y - 2000)) % 360
    assert close(az, 358.0) and close(math.hypot(x - 1000, y - 2000), 5.0)
    assert t.apply_pixel(100, 100) == (1000, 2000) or close(t.apply_pixel(100, 100)[0], 1000)

def test_section_tilted_scan():
    # barre inclinée de 5° dans le scan -> redressée
    ang = math.radians(5)
    p1 = (100, 400)
    p2 = (100 + 200 * math.cos(ang), 400 - 200 * math.sin(ang))
    t = c.section_calibration((100, 400), (0.0, 1500.0), p1, p2, 20.0)
    X, Z = t.apply_pixel(*p2)
    assert close(X, 20.0) and close(Z, 1500.0)
    # clic inverse de la barre : même résultat
    t2 = c.section_calibration((100, 400), (0.0, 1500.0), p2, p1, 20.0)
    assert close(t2.apply_pixel(*p2)[1], 1500.0)

def _gallery():
    # galerie E-O puis puits : plan (x,y), coupe développée (X,Z)
    plan = [(0, 0), (10, 0), (20, 0), (30, 0), (30.5, 0), (40, 0)]
    coupe = [(0, 1000), (10, 998), (20, 990), (30, 990), (30.5, 960), (40, 955)]
    return plan, coupe

def test_developpee_order_and_pit():
    plan, coupe = _gallery()
    r = c.compute_altitudes(plan, [], coupe, [], mode="developpee", pair_by_order=True)
    assert [x["source"] for x in r] == ["coupe"] * 6
    assert [round(x["z"], 3) for x in r] == [1000, 998, 990, 990, 960, 955]

def test_developpee_partial_coupe_interpolation():
    plan, _ = _gallery()
    # coupe ne couvre que 0..20 m : au-delà, extrapolation à pente constante
    coupe = [(0, 1000), (20, 990)]
    r = c.compute_altitudes(plan, ["E", "", "B", "", "", ""], coupe, ["E", "B"])
    assert close(r[1]["z"], 995) and r[1]["source"] == "coupe"
    assert r[3]["source"] == "extrap" and close(r[3]["z"], 985)

def test_plan_cote_priority_and_interp():
    plan = [(0, 0), (10, 0), (20, 0), (30, 0)]
    r = c.compute_altitudes(plan, [], [], [], plan_z=[1200, None, None, 1170])
    assert [x["source"] for x in r] == ["plan", "interp", "interp", "plan"]
    assert close(r[1]["z"], 1190) and close(r[2]["z"], 1180)

def test_plan_vs_coupe_gap():
    plan = [(0, 0), (10, 0)]
    r = c.compute_altitudes(plan, ["A", "B"], [(0, 500), (10, 490)], ["A", "B"],
                            plan_z=[None, 491.0])
    assert r[1]["source"] == "plan" and close(r[1]["dz_plan_coupe"], 1.0)

def test_projetee_with_names_and_fit():
    # galerie en L : 20 m vers l'est puis 20 m vers le nord ; coupe projetée α=0
    # -> axe horizontal orienté à 90° (est). La partie nord est vue de face.
    plan = [(0, 0), (10, 0), (20, 0), (20, 10), (20, 20)]
    names = ["0", "1", "2", "3", "4"]
    coupe = [(0, 100), (10, 95), (20, 90), (20, 85), (20, 80)]
    r = c.compute_altitudes(plan, names, coupe, names, mode="projetee",
                            section_azimuth=0.0)
    assert [round(x["z"], 3) for x in r] == [100, 95, 90, 85, 80]

def test_projetee_unnamed_middle_station():
    plan = [(0, 0), (5, 0), (10, 0)]
    coupe = [(0, 100), (10, 90)]
    r = c.compute_altitudes(plan, ["a", "", "b"], coupe, ["a", "b"], mode="projetee",
                            section_azimuth=0.0)
    assert r[1]["source"] == "coupe" and close(r[1]["z"], 95)

def test_projetee_inverted_axis_warns():
    msgs = []
    plan = [(0, 0), (10, 0)]
    coupe = [(0, 100), (-10, 90)]
    c.compute_altitudes(plan, ["a", "b"], coupe, ["a", "b"], mode="projetee",
                        log=msgs.append)
    assert any("Inverser" in m for m in msgs)

def test_junction_and_default():
    r = c.compute_altitudes([(0, 0), (5, 0)], ["P5", "Q1"], [], [], fixed_z={"P5": 777})
    assert r[0]["source"] == "jonction" and r[1]["source"] == "extrap" and close(r[1]["z"], 777)
    r = c.compute_altitudes([(0, 0), (5, 0)], [], [], [], default_z=1000)
    assert r[0]["source"] == "defaut" and close(r[1]["z"], 1000)

def test_therion_export():
    br = [[dict(nom="E", x=0, y=0, z=10, source="coupe"),
           dict(nom="1", x=3, y=4, z=8, source="interp")]]
    txt = c.therion_centreline("Grotte test", br, "EPSG:2154")
    assert "data cartesian from to easting northing altitude" in txt
    assert "fix E 0.000 0.000 10.000" in txt and "3.000     4.000    -2.000" in txt
    l3, h, az, cl = c.shot_measures((0, 0, 10), (3, 4, 8))
    assert close(h, 5) and close(az, math.degrees(math.atan2(3, 4))) and cl < 0

def test_therion_metadata():
    br = [[dict(nom="E", x=0, y=0, z=10), dict(nom="1", x=1, y=0, z=10)]]
    txt = c.therion_centreline("g", br, "EPSG:2154", date="1972-08-15",
                               team=["J. Dupont", " "], header=["Source : bulletin"])
    assert "date 1972.08.15" in txt and 'team "J. Dupont"' in txt
    assert txt.count("team") == 1 and "# Source : bulletin" in txt
    assert c.therion_date("été 1972") is None and c.therion_date("1972") == "1972"

def test_station_names():
    assert c.therion_station_name("12 bis", "x") == "12_bis"
    assert c.therion_station_name("0@castor.amont", "x") == "0@castor.amont"
    assert c.therion_station_name(None, "B1_0") == "B1_0"

def test_north_arrow_azimuth():
    assert c.north_arrow_azimuth(c.NORD_GRILLE, 2.5, -3) == 0.0
    assert close(c.north_arrow_azimuth(c.NORD_GEO, 2.5, -3), -2.5)
    assert close(c.north_arrow_azimuth(c.NORD_MAGNETIQUE, 2.5, -3), -5.5)
    try:
        c.north_arrow_azimuth("autre")
    except ValueError:
        pass
    else:
        assert False

def test_therion_normal_style():
    br = [[dict(nom="A", x=0, y=0, z=0, source="coupe"),
           dict(nom="B", x=0, y=10, z=0, source="coupe")]]
    txt = c.therion_centreline("g", br, "EPSG:2154", style="normal", convergence=2.5)
    assert "data normal from to length compass clino" in txt
    assert "declination 0.0 degrees" in txt
    ligne = [l for l in txt.split("\n") if l.strip().startswith("A ")][0]
    champs = ligne.split()
    assert close(float(champs[2]), 10.0) and close(float(champs[3]), 2.5)

def test_compare_to_reference():
    stations = [dict(nom="1", x=0, y=0, z=100, source="coupe"),
                dict(nom="2", x=3, y=4, z=95, source="interp"),
                dict(nom="3", x=0, y=0, z=0, source="extrap")]
    ref = {"1": (0, 0, 100), "2": (0, 0, 100)}
    couples, stats = c.compare_to_reference(stations, ref)
    assert [x["nom"] for x in couples] == ["1", "2"]
    assert close(couples[1]["d2d"], 5.0) and close(couples[1]["dz"], -5.0)
    assert stats["n"] == 2 and close(stats["max_2d"], 5.0)
    assert close(stats["rms_2d"], math.sqrt(25 / 2))
    assert c.compare_to_reference(stations, {})[1] == {"n": 0}
