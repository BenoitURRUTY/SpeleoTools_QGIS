"""Tests des onglets historiques et du fournisseur Processing, dans un QGIS
sans affichage.

Usage : QT_QPA_PLATFORM=offscreen python3 tests/run_qgis_plugin_tests.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
WORK = tempfile.mkdtemp(prefix="speleo_plugin_")
shutil.copytree(PLUGIN, os.path.join(WORK, "SpeleoTools"),
                ignore=shutil.ignore_patterns("__pycache__", "tests"))
sys.path.insert(0, WORK)
sys.path.insert(0, "/usr/share/qgis/python/plugins")

from qgis.testing import start_app
from qgis.testing.mocked import get_iface
app = start_app()

import numpy as np
import processing
from osgeo import gdal, ogr, osr
from processing.core.Processing import Processing
from qgis.core import (
    QgsApplication, QgsCoordinateReferenceSystem, QgsFeature, QgsGeometry,
    QgsPoint, QgsProject, QgsRasterLayer, QgsVectorLayer,
)

Processing.initialize()
QgsProject.instance().setCrs(QgsCoordinateReferenceSystem("EPSG:2154"))

import SpeleoTools
from SpeleoTools.speleo_tools import SpeleoTools as Plugin, SpeleoToolsDialog
from SpeleoTools import speleo_utils as su
from SpeleoTools.speleo_provider import SpeleoToolsProvider

# les boîtes de dialogue modales bloqueraient un test sans interface
from qgis.PyQt import QtWidgets as _W
for _m in ("information", "warning", "critical", "question"):
    setattr(_W.QMessageBox, _m, staticmethod(lambda *a, **k: _W.QMessageBox.Ok))

iface = get_iface()

# ── MNT synthétique : plan incliné z = 1000 + 0,01·(x − x0) ───────────────
X0, Y0 = 926000.0, 6500000.0
RES = 1.0
N = 200


def make_dem(path):
    cols = rows = N
    arr = np.zeros((rows, cols), dtype=np.float32)
    for c in range(cols):
        arr[:, c] = 1000.0 + 0.01 * (c * RES)
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, cols, rows, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((X0, RES, 0, Y0 + rows * RES, 0, -RES))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(2154)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(arr)
    ds = None


dem_path = os.path.join(WORK, "mnt.tif")
make_dem(dem_path)
dem = QgsRasterLayer(dem_path, "MNT", "gdal")
assert dem.isValid()
QgsProject.instance().addMapLayer(dem)


def dem_z(x):
    return 1000.0 + 0.01 * (x - X0)


# ══════════════════════════════════════════════════════════════════════
#  1) Épaisseur de roche : couche cavité dans un AUTRE SCR (bug corrigé)
# ══════════════════════════════════════════════════════════════════════
from qgis.core import QgsCoordinateTransform

to_wgs = QgsCoordinateTransform(QgsCoordinateReferenceSystem("EPSG:2154"),
                                QgsCoordinateReferenceSystem("EPSG:4326"),
                                QgsProject.instance())
cave = QgsVectorLayer("LineStringZ?crs=EPSG:4326", "cavite_wgs", "memory")
pts_l93 = [(X0 + 20, Y0 + 50, 950.0), (X0 + 60, Y0 + 50, 940.0), (X0 + 120, Y0 + 50, 930.0)]
verts = []
for x, y, z in pts_l93:
    p = to_wgs.transform(x, y)
    verts.append(QgsPoint(p.x(), p.y(), z))
f = QgsFeature()
f.setGeometry(QgsGeometry.fromPolyline(verts))
cave.dataProvider().addFeatures([f])
cave.updateExtents()
QgsProject.instance().addMapLayer(cave)

res = processing.run("speleotools:epaisseurroche",
                     {"DEM": dem, "CAVITE": cave, "DEDUP": True,
                      "OUTPUT": "TEMPORARY_OUTPUT"}) if False else None

# le fournisseur n'est pas encore enregistré : on l'ajoute comme le fait initGui
provider = SpeleoToolsProvider()
QgsApplication.processingRegistry().addProvider(provider)
algs = sorted(a.id() for a in provider.algorithms())
print("Algorithmes :", algs)
assert len(algs) == 5, algs

out = processing.run("speleotools:epaisseurroche",
                     {"DEM": dem, "CAVITE": cave, "DEDUP": True,
                      "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
feats = sorted(out.getFeatures(), key=lambda f: f["src_elev"])
assert len(feats) == 3, len(feats)
for feat, (x, y, z) in zip(feats, pts_l93):
    attendu = dem_z(x)
    assert abs(feat["src_elev"] - attendu) < 0.02, (feat["src_elev"], attendu)
    assert abs(feat["thickness"] - (attendu - z)) < 0.02
print("✔ épaisseur de roche correcte avec une couche dans un autre SCR")

# même test via la fonction du dialogue (compute_thickness)
mem = su.compute_thickness(dem, cave, out_path=None, layer_name="t")
assert mem.featureCount() == 3
print("✔ compute_thickness aligné sur l'algorithme")

# dédoublonnage à 10 cm
cave2 = QgsVectorLayer("PointZ?crs=EPSG:2154", "doublons", "memory")
fs = []
for dx in (0.0, 0.02, 0.5):          # 2 cm → même case de 10 cm, 50 cm → conservé
    g = QgsFeature()
    g.setGeometry(QgsGeometry(QgsPoint(X0 + 30 + dx, Y0 + 30, 900.0)))
    fs.append(g)
cave2.dataProvider().addFeatures(fs)
n_dedup = sum(1 for _ in su.iter_thickness_points(dem, cave2, dedup=True))
n_brut = sum(1 for _ in su.iter_thickness_points(dem, cave2, dedup=False))
assert (n_dedup, n_brut) == (2, 3), (n_dedup, n_brut)
print("✔ dédoublonnage à 10 cm")

# ══════════════════════════════════════════════════════════════════════
#  2) Profil développé et drapage
# ══════════════════════════════════════════════════════════════════════
line = QgsVectorLayer("LineString?crs=EPSG:2154", "ligne", "memory")
g = QgsFeature()
g.setGeometry(QgsGeometry.fromWkt("LineString(%f %f, %f %f)" % (X0 + 10, Y0 + 10, X0 + 110, Y0 + 10)))
line.dataProvider().addFeatures([g])
line.updateExtents()

csv_path = os.path.join(WORK, "profil.csv")
processing.run("speleotools:profildeveloppe",
               {"DEM": dem, "LIGNE": line, "PAS": 5.0, "INTERP": True, "CSV": csv_path})
rows = open(csv_path, encoding="utf-8").read().strip().split("\n")
assert rows[0] == "X_distance_m,Y_altitude_m" and len(rows) == 22, len(rows)
d_last, z_last = rows[-1].split(",")
assert abs(float(d_last) - 100.0) < 1e-6 and abs(float(z_last) - dem_z(X0 + 110)) < 0.02
print("✔ profil développé (CSV) :", len(rows) - 1, "points")

drape = processing.run("speleotools:drapagemnt",
                       {"DEM": dem, "LIGNE": line, "PAS": 10.0,
                        "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
assert drape.featureCount() == 1
geom = next(drape.getFeatures()).geometry().constGet()
zs = [p.z() for p in geom.vertices()]
assert abs(zs[0] - dem_z(X0 + 10)) < 0.02 and abs(zs[-1] - dem_z(X0 + 110)) < 0.02
print("✔ drapage 3D sur le MNT")

# ══════════════════════════════════════════════════════════════════════
#  3) Dolines : message explicite quand aucun algorithme de comblement
# ══════════════════════════════════════════════════════════════════════
alg_fill = su.fill_sinks_algorithm()
if alg_fill is None:
    try:
        processing.run("speleotools:dolines",
                       {"DEM": dem, "POLYGONES": "TEMPORARY_OUTPUT"})
    except Exception as e:
        assert "SAGA" in str(e) or "comblement" in str(e), str(e)
        print("✔ dolines : message clair en l'absence de SAGA/GRASS")
else:
    print("… SAGA/GRASS présent (%s), test du message ignoré" % alg_fill)

# ══════════════════════════════════════════════════════════════════════
#  4) Import Therion sans geopandas
# ══════════════════════════════════════════════════════════════════════
shp_dir = os.path.join(WORK, "therion")
os.makedirs(shp_dir, exist_ok=True)
srs = osr.SpatialReference()
srs.ImportFromEPSG(2154)
drv = ogr.GetDriverByName("ESRI Shapefile")


def make_shp(name, geom_type, fields, rows):
    ds = drv.CreateDataSource(os.path.join(shp_dir, name + ".shp"))
    lyr = ds.CreateLayer(name, srs, geom_type)
    for fname, ftype in fields:
        lyr.CreateField(ogr.FieldDefn(fname, ftype))
    for wkt, attrs in rows:
        feat = ogr.Feature(lyr.GetLayerDefn())
        for k, v in attrs.items():
            feat.SetField(k, v)
        feat.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        lyr.CreateFeature(feat)
    ds = None


# outline du scrap 1 : carré de 100 m
ox, oy = X0 + 10, Y0 + 10
make_shp("outline2d", ogr.wkbPolygon, [("_ID", ogr.OFTString)],
         [("POLYGON((%f %f, %f %f, %f %f, %f %f, %f %f))"
           % (ox, oy, ox + 100, oy, ox + 100, oy + 100, ox, oy + 100, ox, oy),
           {"_ID": "scrap1"})])
# lignes : une paroi dans le scrap (à découper, elle déborde), une centerline
# qui ne doit PAS être découpée, et une paroi d'un autre scrap (à écarter)
make_shp("lines2d", ogr.wkbLineString,
         [("_TYPE", ogr.OFTString), ("_CLIP", ogr.OFTString), ("_SCRAP_ID", ogr.OFTString)],
         [("LINESTRING(%f %f, %f %f)" % (ox + 20, oy + 20, ox + 200, oy + 20),
           {"_TYPE": "wall", "_CLIP": "on", "_SCRAP_ID": "scrap1"}),
          ("LINESTRING(%f %f, %f %f)" % (ox + 20, oy + 50, ox + 300, oy + 50),
           {"_TYPE": "centerline", "_CLIP": "on", "_SCRAP_ID": "scrap1"}),
          ("LINESTRING(%f %f, %f %f)" % (ox + 30, oy + 30, ox + 60, oy + 30),
           {"_TYPE": "wall", "_CLIP": "on", "_SCRAP_ID": "scrap2"})])
make_shp("points2d", ogr.wkbPoint25D, [("_NAME", ogr.OFTString)],
         [("POINT Z(%f %f 987)" % (ox + 40, oy + 40), {"_NAME": "entrance"})])
make_shp("stations3d", ogr.wkbPoint25D, [("_NAME", ogr.OFTString)],
         [("POINT Z(%f %f 912.4)" % (ox + 45, oy + 45), {"_NAME": "1.0"})])
make_shp("shots3d", ogr.wkbLineString25D, [("_SURVEY", ogr.OFTString)],
         [("LINESTRING Z(%f %f 987, %f %f 912.4)" % (ox + 40, oy + 40, ox + 45, oy + 45),
           {"_SURVEY": "test"})])

dlg = SpeleoToolsDialog(None, iface=iface)
dlg.editTherionShpPath.setText(shp_dir)
gpkg_dir = os.path.join(WORK, "therion_gpkg")
os.makedirs(gpkg_dir, exist_ok=True)
dlg.editTherionGpkgPath.setText(gpkg_dir)
dlg.chkRepairGeom.setChecked(True)
dlg.chkAddAlt.setChecked(True)
dlg.run_therion_import()
print(dlg.textLogTherion.toPlainText())

for f in ("lines2dMasked.gpkg", "points2dAlt.gpkg", "stations3dAlt.gpkg",
          "shots3d.gpkg", "outline2d.gpkg"):
    assert os.path.isfile(os.path.join(gpkg_dir, f)), f

lines_out = QgsVectorLayer(os.path.join(gpkg_dir, "lines2dMasked.gpkg"), "l", "ogr")
types = sorted(f["_TYPE"] for f in lines_out.getFeatures())
assert types == ["centerline", "wall"], types      # la paroi du scrap2 est écartée
longueurs = {f["_TYPE"]: f.geometry().length() for f in lines_out.getFeatures()}
assert abs(longueurs["wall"] - 80.0) < 0.5, longueurs   # découpée sur l'outline
assert longueurs["centerline"] > 200.0, longueurs       # jamais découpée
print("✔ import Therion : découpe sur l'outline, centerline préservée")

pts_out = QgsVectorLayer(os.path.join(gpkg_dir, "points2dAlt.gpkg"), "p", "ogr")
pf = next(pts_out.getFeatures())
assert [n for n in pts_out.fields().names() if n in ("_ALT", "_EASTING", "_NORTHING")]
assert str(pf["_ALT"]) == "987" and abs(pf["_EASTING"] - (ox + 40)) < 0.01
print("✔ altitudes ajoutées aux points (_ALT, _EASTING, _NORTHING)")

assert "geopandas" not in sys.modules and "pandas" not in sys.modules
print("✔ import réalisé sans geopandas ni pandas")

# ══════════════════════════════════════════════════════════════════════
#  5) Déchargement : signaux débranchés, fournisseur retiré
# ══════════════════════════════════════════════════════════════════════
QgsApplication.processingRegistry().removeProvider(provider)
plugin = Plugin(iface)
plugin.initGui()
assert QgsApplication.processingRegistry().providerById("speleotools") is not None
plugin.run()
d = plugin.dialog
assert d._signals_connected
plugin.unload()
assert plugin.dialog is None and not d._signals_connected
assert QgsApplication.processingRegistry().providerById("speleotools") is None
n_before = len(QgsProject.instance().mapLayers())
QgsProject.instance().addMapLayer(QgsVectorLayer("Point?crs=EPSG:2154", "après unload", "memory"))
print("✔ déchargement propre (signaux débranchés, fournisseur retiré)")

del dlg, d, plugin
QgsProject.instance().clear()
print("✔ tous les contrôles sont passés")

# QGIS plante parfois en libérant ses couches à la sortie de l'interpréteur :
# on sort proprement une fois tous les contrôles passés.
sys.stdout.flush()
os._exit(0)
