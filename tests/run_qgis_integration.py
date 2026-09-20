"""Test d'intégration de l'onglet Topo ancienne dans un QGIS sans affichage.
Usage : QT_QPA_PLATFORM=offscreen python3.12 tests/run_qgis_integration.py
"""
import math, os, shutil, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
WORK = tempfile.mkdtemp(prefix="speleo_ta_")
shutil.copytree(PLUGIN, os.path.join(WORK, "SpeleoTools"),
                ignore=shutil.ignore_patterns("__pycache__", "tests"))
sys.path.insert(0, WORK)
sys.path.insert(0, "/usr/share/qgis/python/plugins")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()
import numpy as np
from osgeo import gdal
from qgis.core import QgsProject, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
from qgis.PyQt.QtCore import Qt

QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:2154"))

# --- images synthétiques -------------------------------------------------
def make_png(path, w, h):
    drv = gdal.GetDriverByName("MEM")
    ds = drv.Create("", w, h, 1, gdal.GDT_Byte)
    ds.GetRasterBand(1).WriteArray(np.full((h, w), 230, np.uint8))
    gdal.GetDriverByName("PNG").CreateCopy(path, ds)
plan_png = os.path.join(WORK, "plan 1972.png"); make_png(plan_png, 1200, 900)
coupe_png = os.path.join(WORK, "coupe.png"); make_png(coupe_png, 1400, 600)

import SpeleoTools
from SpeleoTools.speleo_tools import SpeleoToolsDialog
# les boîtes de dialogue modales bloqueraient un test sans interface
from qgis.PyQt import QtWidgets as _W
for _m in ("information", "warning", "critical", "question"):
    setattr(_W.QMessageBox, _m, staticmethod(lambda *a, **k: _W.QMessageBox.Ok))

iface = get_iface()
dlg = SpeleoToolsDialog(None, iface=iface)
canvas = iface.mapCanvas()
canvas.setDestinationCrs(QgsProject.instance().crs())
tabs = [dlg.tabWidget.tabText(i) for i in range(dlg.tabWidget.count())]
print("Onglets :", tabs)
assert "📜 Topo ancienne" in tabs

dlg.editTaName.setText("Grotte test")
dlg.editTaOutDir.setText(os.path.join(WORK, "out"))

# --- vérité terrain ---------------------------------------------------------
E = (926000.0, 6500000.0, 1500.0)
S = 0.04                         # m/px sur le plan
DECL = -3.0                      # flèche nord magnétique : azimut réel -3°
entry_px = (300.0, 400.0)

def plan_px_to_world(col, row):
    # vecteur image (haut = direction de la flèche = azimut -3°)
    du, dv = col - entry_px[0], -(row - entry_px[1])
    phi = math.radians(-DECL)    # rotation trigo = -azimut
    x = E[0] + S * (du * math.cos(phi) - dv * math.sin(phi))
    y = E[1] + S * (du * math.sin(phi) + dv * math.cos(phi))
    return x, y

def click(role_layer_combo, pixels, button):
    """Simule des clics au pixel donné sur la couche raster active."""
    lyr = dlg.get_layer_by_combo(role_layer_combo)
    ds = gdal.Open(lyr.source()); gt = ds.GetGeoTransform(); ds = None
    button.click()
    tool = canvas.mapTool()
    assert tool is not None, "outil de clic non activé"
    for c, r in pixels:
        tool._on_click(QgsPointXY(gt[0] + c * gt[1] + r * gt[2], gt[3] + c * gt[4] + r * gt[5]), Qt.LeftButton)

# --- ① plan -----------------------------------------------------------------
dlg.editTaPlanPath.setText(plan_png)
dlg.radioTaPlanNorth.setChecked(True)
dlg._ta_load_raw("plan")
click(dlg.comboTaPlanLayer, [entry_px], dlg.btnTaPickEntry)
click(dlg.comboTaPlanLayer, [(100, 800), (600, 800)], dlg.btnTaPickScale)   # 500 px
dlg.spinTaScaleLen.setValue(20.0)                                           # = 20 m
click(dlg.comboTaPlanLayer, [(1000, 300), (1000, 100)], dlg.btnTaPickNorth) # flèche vers le haut
# rattachement : clic sur une station existante (couche de points 3D type import Therion)
ex = QgsVectorLayer("PointZ?crs=EPSG:2154&field=_NAME:string&field=_SURVEY:string", "stations3d", "memory")
fe = QgsFeature(ex.fields()); fe.setGeometry(QgsGeometry.fromWkt("PointZ (%f %f %f)" % E)); fe["_NAME"] = "0"
fe["_SURVEY"] = "castor"; ex.dataProvider().addFeatures([fe]); QgsProject.instance().addMapLayer(ex)
canvas.setExtent(ex.extent().buffered(50)); canvas.resize(800, 600); canvas.refresh()
dlg.btnTaPickExisting.click()
canvas.mapTool()._on_click(QgsPointXY(E[0] + 0.02, E[1] - 0.01), Qt.LeftButton)
assert abs(dlg.spinTaEntryX.value() - E[0]) < 1e-6 and abs(dlg.spinTaEntryZ.value() - E[2]) < 1e-6
assert dlg.editTaEntryName.text() == "0@castor", dlg.editTaEntryName.text()
print("✔ rattachement station existante")
# azimut de la flèche : nord magnétique → convergence des méridiens + déclinaison
gamma = dlg._ta_grid_convergence(E[0], E[1])
# γ = n·(λ − 3°) pour le Lambert-93 (n = 0,7256077650, IGN)
from qgis.core import QgsCoordinateTransform as _X, QgsCoordinateReferenceSystem as _C
ll = _X(QgsProject.instance().crs(), _C("EPSG:4326"), QgsProject.instance()).transform(QgsPointXY(E[0], E[1]))
assert abs(gamma - (ll.x() - 3.0) * 0.7256077650) < 0.01, (gamma, ll.x())
dlg.comboTaNorthRef.setCurrentIndex(2)
assert dlg.spinTaDecl.isEnabled()
dlg.spinTaDecl.setValue(DECL + gamma)
dlg.btnTaComputeAz.click()
assert abs(dlg.spinTaNorthAz.value() - DECL) < 1e-6, dlg.spinTaNorthAz.value()
print("✔ azimut flèche calculé : γ = %+.3f°" % gamma)
dlg.editTaDate.setText("1972-08")
dlg.editTaAuthors.setText("J. Dupont, P. Martin")
dlg.editTaSources.setText("Bulletin test p. 12")
dlg._ta_calibrate_plan()
plan_lyr = dlg.get_layer_by_combo(dlg.comboTaPlanLayer)
print("Plan :", plan_lyr.name(), plan_lyr.source())
ds = gdal.Open(plan_lyr.source()); gt = ds.GetGeoTransform(); ds = None
for c, r in [(300, 400), (900, 150), (50, 850)]:
    x = gt[0] + c * gt[1] + r * gt[2]; y = gt[3] + c * gt[4] + r * gt[5]
    xe, ye = plan_px_to_world(c, r)
    assert abs(x - xe) < 1e-6 and abs(y - ye) < 1e-6, ((x, y), (xe, ye))
print("✔ calage plan conforme")

# --- ② coupe ----------------------------------------------------------------
dlg.editTaCoupePath.setText(coupe_png)
dlg._ta_load_raw("coupe")
click(dlg.comboTaCoupeLayer, [(100, 550), (600, 550)], dlg.btnTaPickCoupeScale)
dlg.spinTaCoupeScaleLen.setValue(25.0)          # 0.05 m/px
click(dlg.comboTaCoupeLayer, [(100, 100)], dlg.btnTaPickCoupeRef)
dlg.spinTaCoupeRefX.setValue(0.0); dlg.spinTaCoupeRefZ.setValue(E[2])
dlg.radioTaDev.setChecked(True)
dlg._ta_calibrate_coupe()
ox, oy = dlg._ta_coupe_offsets()
coupe_lyr = dlg.get_layer_by_combo(dlg.comboTaCoupeLayer)
ds = gdal.Open(coupe_lyr.source()); gt = ds.GetGeoTransform(); ds = None
X = gt[0] + 600 * gt[1] + 300 * gt[2] - ox; Z = gt[3] + 600 * gt[4] + 300 * gt[5] - oy
assert abs(X - 25.0) < 1e-6 and abs(Z - (E[2] - 10.0)) < 1e-6, (X, Z)
print("✔ calage coupe conforme, décalage", ox, oy)

# --- ③ tracés (simulés) : galerie + puits, et une branche latérale -------------
truth = [  # nom, x, y, z
    ("E", E[0], E[1], E[2]), ("1", E[0] + 10, E[1], 1498.0), ("2", E[0] + 20, E[1] + 5, None),
    ("P", E[0] + 30, E[1] + 5, 1490.0), ("PB", E[0] + 30.3, E[1] + 5, 1460.0), ("5", E[0] + 40, E[1] + 5, 1455.0),
    ("6", E[0] + 55, E[1] + 5, None),
]
plan_xy = [(t[1], t[2]) for t in truth]
dcum = [0.0]
for a, b in zip(plan_xy[:-1], plan_xy[1:]):
    dcum.append(dcum[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
# coupe développée : la coupe ne va que jusqu'à la station 5 et ne représente pas la 2
coupe_idx = [0, 1, 3, 4, 5]
coupe_pts = [(dcum[i] + ox, truth[i][3] + oy) for i in coupe_idx]

dlg._ta_start_drawing("plan")
tp = dlg._ta_get_layer("trace_plan")
f = QgsFeature(tp.fields()); f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in plan_xy]))
f["branche"] = 1; tp.addFeature(f)
# branche 2 : part de la station 5 vers le nord, sans coupe
f2 = QgsFeature(tp.fields())
f2.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*plan_xy[5]), QgsPointXY(plan_xy[5][0], plan_xy[5][1] + 12),
                                           QgsPointXY(plan_xy[5][0], plan_xy[5][1] + 20)]))
f2["branche"] = 2; tp.addFeature(f2)
dlg._ta_start_drawing("coupe")
tc = dlg._ta_get_layer("trace_coupe")
f = QgsFeature(tc.fields()); f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(*p) for p in coupe_pts]))
f["branche"] = 1; tc.addFeature(f)
dlg._ta_finish_drawing()
assert not tp.isEditable() and tp.featureCount() == 2 and tc.featureCount() == 1

# --- ④ noms / cotes -----------------------------------------------------------
sp = dlg._ta_get_layer("stations_plan"); sc = dlg._ta_get_layer("stations_coupe")
assert sp.featureCount() == 10 and sc.featureCount() == 5, (sp.featureCount(), sc.featureCount())
sp.startEditing()
for ft in sp.getFeatures():
    if ft["branche"] == 1:
        sp.changeAttributeValue(ft.id(), sp.fields().indexOf("nom"), truth[ft["ordre"]][0])
    elif ft["ordre"] == 2:
        sp.changeAttributeValue(ft.id(), sp.fields().indexOf("z_plan"), 1459.0)   # cote lue sur le plan
sp.commitChanges()
sc.startEditing()
for ft in sc.getFeatures():
    sc.changeAttributeValue(ft.id(), sc.fields().indexOf("nom"), truth[coupe_idx[ft["ordre"]]][0])
sc.commitChanges()

# resynchronisation : noms conservés ?
dlg._ta_make_stations()
assert sorted(str(x["nom"]) for x in sp.getFeatures() if x["branche"] == 1) == sorted(t[0] for t in truth)

# --- ⑤ calcul -----------------------------------------------------------------
dlg._ta_run()
print(dlg.textLogTa.toPlainText())
out = os.path.join(WORK, "out", "Grotte_test_topo3d.gpkg")
st = QgsVectorLayer(out + "|layername=stations_3d", "s", "ogr")
res = {(f["branche"], f["ordre"]): f for f in st.getFeatures()}
z = lambda b, o: res[(b, o)]["z"]
src = lambda b, o: res[(b, o)]["source_z"]
assert src(1, 0) == "coupe" and abs(z(1, 0) - 1500) < 1e-6
assert src(1, 2) == "coupe"   # station non nommée sur la coupe → lue sur la ligne
expected2 = 1498 + (1490 - 1498) * (dcum[2] - dcum[1]) / (dcum[3] - dcum[1])
assert abs(z(1, 2) - expected2) < 1e-3, (z(1, 2), expected2)
assert abs(z(1, 3) - 1490) < 1e-6 and abs(z(1, 4) - 1460) < 1e-6    # haut et bas du puits
assert src(1, 6) == "extrap"
slope = (1455 - 1460) / (dcum[5] - dcum[4])
assert abs(z(1, 6) - (1455 + slope * (dcum[6] - dcum[5]))) < 1e-3
assert src(2, 0) == "jonction" and abs(z(2, 0) - 1455) < 1e-6 and res[(2, 0)]["nom"] == "5"
assert src(2, 2) == "plan" and src(2, 1) == "interp"
assert abs(z(2, 1) - (1455 + (1459 - 1455) * 12 / 20)) < 1e-6
g = res[(1, 3)].geometry().constGet()
assert abs(g.z() - 1490) < 1e-6
# --- ⑥ comparaison à un levé de référence + style Therion normal --------------
ref = QgsVectorLayer("PointZ?crs=EPSG:2154&field=_NAME:string", "levé récent", "memory")
rf = []
for nom, dx, dz in [("1", 0.4, 0.0), ("P", -0.3, 1.0), ("5", 0.0, -0.5)]:
    i = [t[0] for t in truth].index(nom)
    g = QgsFeature(ref.fields())
    g.setGeometry(QgsGeometry.fromWkt("PointZ (%f %f %f)" % (truth[i][1] + dx, truth[i][2],
                                                             res[(1, i)]["z"] + dz)))
    g["_NAME"] = nom
    rf.append(g)
ref.dataProvider().addFeatures(rf)
QgsProject.instance().addMapLayer(ref)
dlg.populate_layers()
idx = dlg.comboTaRefLayer.findData(ref.id(), Qt.UserRole)
assert idx >= 0
dlg.comboTaRefLayer.setCurrentIndex(idx)
stats = dlg._ta_compare_reference()
assert stats["n"] == 3 and abs(stats["max_2d"] - 0.4) < 1e-6, stats
assert abs(stats["moy_dz"] + 0.5 / 3) < 1e-6, stats
ecarts = open(os.path.join(WORK, "out", "Grotte_test_ecarts_reference.csv"), encoding="utf-8").read()
assert ecarts.count("\n") == 4 and "d3d_m" in ecarts
print("✔ comparaison au levé de référence :", round(stats["rms_2d"], 3), "m RMS")

dlg.comboTaThStyle.setCurrentIndex(1)          # visées normales
dlg._ta_run()
th_normal = open(os.path.join(WORK, "out", "Grotte_test_ancienne.th"), encoding="utf-8").read()
assert "data normal from to length compass clino" in th_normal
assert "declination 0.0 degrees" in th_normal
ligne = [l for l in th_normal.split("\n") if l.strip().startswith("E ")][0].split()
assert abs(float(ligne[2]) - 10.198) < 0.01, ligne      # longueur 3D E→1
print("✔ export Therion en visées normales")
dlg.comboTaThStyle.setCurrentIndex(0)
dlg._ta_run()

th = open(os.path.join(WORK, "out", "Grotte_test_ancienne.th"), encoding="utf-8").read()
assert "cs EPSG:2154" in th and "fix E" in th and "date 1972.08" in th and 'team "P. Martin"' in th
meta = open(os.path.join(WORK, "out", "Grotte_test_metadonnees.txt"), encoding="utf-8").read()
assert "entrée + échelle + nord" in meta and "Bulletin test" in meta and "coupe développée" in meta
guides = [l for l in QgsProject.instance().mapLayers().values() if l.customProperty("speleotools/ta_internal") == "guides"]
assert len(guides) == 2 and guides[0].featureCount() == 7
print(meta)
vi = QgsVectorLayer(out + "|layername=visees_3d", "v", "ogr")
assert vi.featureCount() == 6 + 2
print("✔ calcul 3D conforme —", st.featureCount(), "stations,", vi.featureCount(), "visées")
print(th)
print("Dossier de test :", WORK)

# fermeture propre (évite un crash de QGIS à la sortie)
dlg.close()
del res, st, vi, sp, sc, tp, tc, ex, dlg
QgsProject.instance().clear()
print("✔ tous les contrôles sont passés")
