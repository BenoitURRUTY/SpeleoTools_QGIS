# -*- coding: utf-8 -*-
"""
SpeleoTools — Onglet « Topo ancienne » (numérisation de topographies
historiques : plan + coupe → polygonale 3D).

Flux de travail
---------------
1. Charger le scan du PLAN, le caler :
     - déjà géoréférencé, ou
     - 2 points connus (clic + coordonnées), ou
     - entrée connue + barre d'échelle + flèche nord (+ déclinaison).
2. Charger le scan de la COUPE (développée ou projetée), la caler :
     barre d'échelle (redresse aussi un scan penché) + point de référence
     (X, Z).  La coupe calée est affichée dans le canevas, décalée sous le
     plan : X_affiché = X + offX, Y_affiché = Z + offY.
3. Retracer la polygonale en polyligne sur le plan puis sur la coupe
   (un sommet = une station ; champ « branche » pour les ramifications).
4. Générer les stations, renseigner si besoin les noms (pour apparier
   plan ↔ coupe) et les cotes lues sur le plan (z_plan).
5. Calculer : chaque station reçoit une altitude (jonction > cote plan >
   coupe > interpolation/extrapolation à pente constante).  Sorties GPKG
   (stations 3D, visées 3D, polygonale 3D), CSV et Therion (.th).

Le calcul lui-même est dans topo_ancienne_core.py (sans dépendance QGIS).
"""

import csv
import datetime
import json
import os
import re
import unicodedata

from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    Qgis, QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsField,
    QgsGeometry, QgsPoint, QgsPointXY, QgsWkbTypes, QgsVectorFileWriter,
    QgsCoordinateTransform, QgsFeatureRequest, QgsDefaultValue,
    QgsEditFormConfig, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling,
    QgsMarkerSymbol, QgsLineSymbol, QgsCategorizedSymbolRenderer,
    QgsRendererCategory, QgsSingleSymbolRenderer, QgsRectangle,
)
from qgis.gui import QgsMapToolEmitPoint, QgsVertexMarker

from . import topo_ancienne_core as core
from .speleo_compat import TYPE_INT, TYPE_DOUBLE, TYPE_STRING, field as _field

PROP = "speleotools/ta_"          # préfixe des propriétés personnalisées
PRJ_SCOPE = "SpeleoTools"         # portée des entrées projet

SOURCE_COLORS = {
    "plan":     "#1565C0",   # cote lue sur le plan
    "jonction": "#6A1B9A",
    "coupe":    "#2E7D32",   # lue sur la coupe
    "interp":   "#EF6C00",   # interpolée à pente constante
    "extrap":   "#C62828",   # extrapolée
    "defaut":   "#000000",
}


# ═══════════════════════════════════════════════════════════════════════
#   Outil carte : collecte de N clics
# ═══════════════════════════════════════════════════════════════════════

class PointCollectorTool(QgsMapToolEmitPoint):
    """Collecte n clics sur le canevas puis appelle callback(points)."""

    def __init__(self, canvas, n_points, callback, color="#E53935"):
        super().__init__(canvas)
        self.canvas = canvas
        self.n = n_points
        self.callback = callback
        self.color = QColor(color)
        self.points = []
        self.markers = []
        self.canvasClicked.connect(self._on_click)

    def _on_click(self, point, button):
        if button == Qt.RightButton:
            self._cleanup()
            self.canvas.unsetMapTool(self)
            return
        self.points.append(QgsPointXY(point))
        m = QgsVertexMarker(self.canvas)
        m.setCenter(QgsPointXY(point))
        m.setColor(self.color)
        m.setIconType(QgsVertexMarker.ICON_CROSS)
        m.setIconSize(14)
        m.setPenWidth(2)
        self.markers.append(m)
        if len(self.points) >= self.n:
            pts = list(self.points)
            self.canvas.unsetMapTool(self)
            self.callback(pts)

    def _cleanup(self):
        for m in self.markers:
            self.canvas.scene().removeItem(m)
        self.markers = []
        self.points = []

    def deactivate(self):
        self._cleanup()
        super().deactivate()


# ═══════════════════════════════════════════════════════════════════════
#   Mixin à ajouter à SpeleoToolsDialog
# ═══════════════════════════════════════════════════════════════════════

class TopoAncienneMixin:
    """Logique de l'onglet « Topo ancienne ». Nécessite self.iface."""

    # ------------------------------------------------------------------
    #  Initialisation
    # ------------------------------------------------------------------
    def _ta_init(self):
        self._ta_tool = None
        self._ta_picks = {}          # clé → [(col,row), ...]

        # Plan
        self.btnTaBrowsePlan.clicked.connect(lambda: self._ta_browse_image(self.editTaPlanPath))
        self.btnTaLoadPlan.clicked.connect(lambda: self._ta_load_raw("plan"))
        self.radioTaPlanGeoref.toggled.connect(self._ta_toggle_plan_method)
        self.radioTaPlan2Pts.toggled.connect(self._ta_toggle_plan_method)
        self.radioTaPlanNorth.toggled.connect(self._ta_toggle_plan_method)
        self.btnTaPickP1.clicked.connect(lambda: self._ta_pick("plan", "p1", 1, self.lblTaP1Px))
        self.btnTaPickP2.clicked.connect(lambda: self._ta_pick("plan", "p2", 1, self.lblTaP2Px))
        self.btnTaPickEntry.clicked.connect(lambda: self._ta_pick("plan", "entry", 1, self.lblTaEntryPx))
        self.btnTaPickScale.clicked.connect(lambda: self._ta_pick("plan", "scale", 2, self.lblTaScalePx))
        self.btnTaPickNorth.clicked.connect(lambda: self._ta_pick("plan", "north", 2, self.lblTaNorthPx))
        self.btnTaCalibPlan.clicked.connect(self._ta_calibrate_plan)
        self.btnTaPickExisting.clicked.connect(self._ta_pick_existing_station)
        self.btnTaComputeAz.clicked.connect(self._ta_compute_north_azimuth)
        self.comboTaNorthRef.currentIndexChanged.connect(self._ta_toggle_north_ref)
        # Coupe
        self.btnTaBrowseCoupe.clicked.connect(lambda: self._ta_browse_image(self.editTaCoupePath))
        self.btnTaLoadCoupe.clicked.connect(lambda: self._ta_load_raw("coupe"))
        self.radioTaProj.toggled.connect(self._ta_toggle_coupe_mode)
        self.btnTaPickCoupeScale.clicked.connect(
            lambda: self._ta_pick("coupe", "cscale", 2, self.lblTaCoupeScalePx))
        self.btnTaPickCoupeRef.clicked.connect(
            lambda: self._ta_pick("coupe", "cref", 1, self.lblTaCoupeRefPx))
        self.btnTaCalibCoupe.clicked.connect(self._ta_calibrate_coupe)
        # Tracé
        self.btnTaDrawPlan.clicked.connect(lambda: self._ta_start_drawing("plan"))
        self.btnTaDrawCoupe.clicked.connect(lambda: self._ta_start_drawing("coupe"))
        self.btnTaFinishDraw.clicked.connect(self._ta_finish_drawing)
        self.btnTaMakeStations.clicked.connect(self._ta_make_stations)
        self.btnTaOpenTable.clicked.connect(self._ta_open_station_tables)
        self.btnTaZoomPlan.clicked.connect(lambda: self._ta_zoom("plan"))
        self.btnTaZoomCoupe.clicked.connect(lambda: self._ta_zoom("coupe"))
        # Calcul
        self.btnTaBrowseOut.clicked.connect(lambda: self._browse_dir(self.editTaOutDir))
        self.btnTaRun.clicked.connect(self._ta_run)
        self.btnTaCompare.clicked.connect(self._ta_compare_reference)

        self.spinTaEntryZ.valueChanged.connect(self._ta_sync_ref_z)
        self._ta_last_entry_z = self.spinTaEntryZ.value()

        self._ta_toggle_plan_method()
        self._ta_toggle_coupe_mode()
        self._ta_toggle_north_ref()

    def _ta_sync_ref_z(self, value):
        """L'altitude de référence de la coupe suit celle de l'entrée tant
        que l'utilisateur ne l'a pas modifiée."""
        if abs(self.spinTaCoupeRefZ.value() - self._ta_last_entry_z) < 1e-9:
            self.spinTaCoupeRefZ.setValue(value)
        self._ta_last_entry_z = value

    def _ta_combos_raster(self):
        return [self.comboTaPlanLayer, self.comboTaCoupeLayer]

    def _ta_combos_vector(self):
        return [self.comboTaPlanLine, self.comboTaCoupeLine]

    # ------------------------------------------------------------------
    #  Utilitaires
    # ------------------------------------------------------------------
    def _talog(self, msg):
        self.textLogTa.append(msg)
        QtWidgets.QApplication.processEvents()

    def _ta_msg(self, text, level=Qgis.Info, duration=6):
        try:
            self.iface.messageBar().pushMessage("Topo ancienne", text, level, duration)
        except Exception:
            pass

    @staticmethod
    def _ta_safe(name):
        s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Za-z0-9\-]+", "_", s).strip("_")
        return s or "cavite"

    def _ta_name(self):
        return self.editTaName.text().strip() or "Cavite"

    def _ta_out_dir(self):
        d = self.editTaOutDir.text().strip()
        if not d:
            src = self.editTaPlanPath.text().strip()
            d = os.path.dirname(src) if src else os.path.expanduser("~")
            d = os.path.join(d, "SpeleoTools_" + self._ta_safe(self._ta_name()))
            self.editTaOutDir.setText(d)
        os.makedirs(d, exist_ok=True)
        return d

    def _ta_gpkg(self):
        return os.path.join(self._ta_out_dir(),
                            self._ta_safe(self._ta_name()) + "_numerisation.gpkg")

    def _ta_crs(self):
        return QgsProject.instance().crs()

    def _ta_browse_image(self, line_edit):
        start = os.path.dirname(line_edit.text().strip()) or os.path.expanduser("~")
        f, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choisir un scan", start,
            "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.gif *.pdf *.vrt);;Tous (*)")
        if f:
            line_edit.setText(f)

    def _ta_set_combo_layer(self, combo, layer):
        self.populate_layers()
        idx = combo.findData(layer.id(), Qt.UserRole)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _ta_layer(self, role):
        combo = self.comboTaPlanLayer if role == "plan" else self.comboTaCoupeLayer
        lyr = self.get_layer_by_combo(combo)
        return lyr if isinstance(lyr, QgsRasterLayer) else None

    def _ta_zoom_to_layer(self, layer):
        canvas = self.iface.mapCanvas()
        ext = layer.extent()
        if layer.crs() != canvas.mapSettings().destinationCrs():
            xf = QgsCoordinateTransform(layer.crs(), canvas.mapSettings().destinationCrs(),
                                        QgsProject.instance())
            ext = xf.transformBoundingBox(ext)
        ext.scale(1.1)
        canvas.setExtent(ext)
        canvas.refresh()

    def _ta_zoom(self, role):
        lyr = self._ta_layer(role)
        line = self.get_layer_by_combo(self.comboTaPlanLine if role == "plan" else self.comboTaCoupeLine)
        target = lyr or (line if isinstance(line, QgsVectorLayer) else None)
        if target:
            self._ta_zoom_to_layer(target)

    # ------------------------------------------------------------------
    #  Rasters : chargement brut et calage (VRT, l'image source n'est
    #  jamais modifiée)
    # ------------------------------------------------------------------
    def _ta_write_vrt(self, src, vrt_path, geotransform):
        from osgeo import gdal
        if os.path.exists(vrt_path):
            self._ta_remove_layers_with_source(vrt_path)
            try:
                os.remove(vrt_path)
            except OSError:
                pass
        ds = gdal.Translate(vrt_path, src, format="VRT")
        if ds is None:
            raise IOError("GDAL ne peut pas lire l'image : %s" % src)
        ds.SetGeoTransform(tuple(geotransform))
        ds.SetProjection(self._ta_crs().toWkt())
        size = (ds.RasterXSize, ds.RasterYSize)
        ds = None   # écriture du VRT
        return size

    def _ta_remove_layers_with_source(self, path, layername=None):
        proj = QgsProject.instance()
        norm = os.path.normcase(os.path.abspath(path))
        for lyr in list(proj.mapLayers().values()):
            src = lyr.source().split("|")[0]
            try:
                same = os.path.normcase(os.path.abspath(src)) == norm
            except Exception:
                same = False
            if not same:
                continue
            if layername and ("layername=%s" % layername) not in lyr.source():
                continue
            proj.removeMapLayer(lyr.id())

    def _ta_add_raster(self, path, name, role, source_img):
        lyr = QgsRasterLayer(path, name, "gdal")
        if not lyr.isValid():
            raise IOError("Couche raster invalide : %s" % path)
        lyr.setCrs(self._ta_crs())
        lyr.setCustomProperty(PROP + "role", role)
        lyr.setCustomProperty(PROP + "source", source_img)
        proj = QgsProject.instance()
        proj.addMapLayer(lyr, False)
        root = proj.layerTreeRoot()
        grp_name = "Topo ancienne — " + self._ta_name()
        grp = root.findGroup(grp_name) or root.insertGroup(0, grp_name)
        grp.addLayer(lyr)
        return lyr

    def _ta_load_raw(self, role):
        edit = self.editTaPlanPath if role == "plan" else self.editTaCoupePath
        src = edit.text().strip()
        if not src or not os.path.isfile(src):
            QtWidgets.QMessageBox.warning(self, "Topo ancienne", "Choisissez d'abord un fichier image.")
            return
        try:
            base = self._ta_safe(os.path.splitext(os.path.basename(src))[0])
            out = self._ta_out_dir()
            if role == "plan" and self.radioTaPlanGeoref.isChecked():
                lyr = self._ta_add_raster(src, "Plan — " + base, role, src)
                lyr.setCustomProperty(PROP + "calibrated", True)
                self._talog("Plan géoréférencé chargé : %s" % src)
            else:
                from osgeo import gdal
                ds = gdal.Open(src)
                if ds is None:
                    raise IOError("GDAL ne peut pas lire : %s" % src)
                w = ds.RasterXSize
                ds = None
                # image brute en « pixels » (y = −ligne). La coupe est placée
                # à gauche du plan pour ne pas se superposer.
                x0 = 0.0 if role == "plan" else -(w + 200.0)
                vrt = os.path.join(out, "%s_%s_brut.vrt" % (role, base))
                self._ta_write_vrt(src, vrt, (x0, 1.0, 0.0, 0.0, 0.0, -1.0))
                lyr = self._ta_add_raster(vrt, "%s brut — %s" % (role.capitalize(), base), role, src)
                self._talog("%s chargé en coordonnées image (à caler) : %s"
                            % (role.capitalize(), os.path.basename(src)))
            self._ta_set_combo_layer(self.comboTaPlanLayer if role == "plan"
                                     else self.comboTaCoupeLayer, lyr)
            self._ta_zoom_to_layer(lyr)
        except Exception as e:
            self._talog("[ERREUR] %s" % e)
            QtWidgets.QMessageBox.critical(self, "Topo ancienne", str(e))

    def _ta_pixel_from_map(self, layer, map_pt):
        """Point canevas → (col, row) dans l'image source du raster."""
        from osgeo import gdal
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        pt = QgsPointXY(map_pt)
        if layer.crs() != canvas_crs:
            pt = QgsCoordinateTransform(canvas_crs, layer.crs(), QgsProject.instance()).transform(pt)
        ds = gdal.Open(layer.source())
        gt = ds.GetGeoTransform()
        ds = None
        det = gt[1] * gt[5] - gt[2] * gt[4]
        dx, dy = pt.x() - gt[0], pt.y() - gt[3]
        col = (gt[5] * dx - gt[2] * dy) / det
        row = (-gt[4] * dx + gt[1] * dy) / det
        return col, row

    def _ta_pick(self, role, key, n, label):
        layer = self._ta_layer(role)
        if layer is None:
            QtWidgets.QMessageBox.warning(self, "Topo ancienne",
                                          "Sélectionnez d'abord la couche raster du %s." % role)
            return
        hints = {
            "p1": "Cliquez sur le point 1 du plan",
            "p2": "Cliquez sur le point 2 du plan",
            "entry": "Cliquez sur l'entrée sur le plan",
            "scale": "Cliquez les 2 extrémités de la barre d'échelle du plan",
            "north": "Cliquez la BASE puis la POINTE de la flèche nord",
            "cscale": "Cliquez les 2 extrémités de la barre d'échelle de la coupe",
            "cref": "Cliquez le point de référence de la coupe (ex. entrée)",
        }

        def done(points):
            try:
                px = [self._ta_pixel_from_map(layer, p) for p in points]
            except Exception as e:
                self._talog("[ERREUR] lecture pixel : %s" % e)
                return
            self._ta_picks[key] = px
            label.setText(" · ".join("(%.0f, %.0f)" % p for p in px))
            label.setStyleSheet("color:#2E7D32;")
            if key in ("scale", "cscale"):
                d = core.pixel_distance(px[0], px[1])
                self._talog("Barre d'échelle : %.1f px" % d)
            self.show()
            self.raise_()

        self._ta_tool = PointCollectorTool(self.iface.mapCanvas(), n, done)
        self.iface.mapCanvas().setMapTool(self._ta_tool)
        self._ta_msg(hints.get(key, "Cliquez sur la carte") + " (clic droit : annuler)")

    def _ta_need(self, *keys):
        missing = [k for k in keys if k not in self._ta_picks]
        if missing:
            names = {"p1": "point 1", "p2": "point 2", "entry": "entrée",
                     "scale": "barre d'échelle", "north": "flèche nord",
                     "cscale": "barre d'échelle coupe", "cref": "point de référence coupe"}
            QtWidgets.QMessageBox.warning(
                self, "Topo ancienne", "Clics manquants : " +
                ", ".join(names.get(k, k) for k in missing))
            return False
        return True

    def _ta_toggle_plan_method(self, *args):
        self.grpTaPlan2Pts.setEnabled(self.radioTaPlan2Pts.isChecked())
        self.grpTaPlanNorth.setEnabled(self.radioTaPlanNorth.isChecked())
        self.btnTaCalibPlan.setEnabled(not self.radioTaPlanGeoref.isChecked())

    def _ta_toggle_north_ref(self, *args):
        self.spinTaDecl.setEnabled(self.comboTaNorthRef.currentIndex() == 2)

    def _ta_grid_convergence(self, x, y):
        """Convergence des méridiens γ (°) au point (x, y) du SCR du projet,
        au sens classique : gisement = azimut − γ (γ > 0 à l'est du méridien
        central). Calculée numériquement : valable pour toute projection."""
        from qgis.core import QgsCoordinateReferenceSystem
        crs = self._ta_crs()
        if not crs.isValid() or crs.isGeographic():
            return 0.0
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        to_geo = QgsCoordinateTransform(crs, wgs, QgsProject.instance())
        to_crs = QgsCoordinateTransform(wgs, crs, QgsProject.instance())
        ll = to_geo.transform(QgsPointXY(x, y))
        north = to_crs.transform(QgsPointXY(ll.x(), ll.y() + 0.01))   # ≈ 1 km plein nord
        import math as _m
        # atan2 donne le gisement du nord géographique, soit −γ
        return -_m.degrees(_m.atan2(north.x() - x, north.y() - y))

    def _ta_compute_north_azimuth(self):
        x, y = self.spinTaEntryX.value(), self.spinTaEntryY.value()
        if x == 0 and y == 0:
            plan = self._ta_layer("plan")
            if plan is not None and plan.customProperty(PROP + "calibrated"):
                c = plan.extent().center()
                x, y = c.x(), c.y()
            else:
                c = self.iface.mapCanvas().center()
                x, y = c.x(), c.y()
                self._talog("⚠ Coordonnées de l'entrée non saisies : convergence calculée "
                            "au centre de la carte (elle varie de ~1° tous les 80 km).")
        kinds = [core.NORD_GRILLE, core.NORD_GEO, core.NORD_MAGNETIQUE]
        kind = kinds[self.comboTaNorthRef.currentIndex()]
        try:
            gamma = self._ta_grid_convergence(x, y)
        except Exception as e:
            self._talog("[ERREUR] convergence des méridiens : %s" % e)
            return
        az = core.north_arrow_azimuth(kind, gamma, self.spinTaDecl.value())
        self.spinTaNorthAz.setValue(az)
        self._talog("🧭 Convergence des méridiens à l'entrée : γ = %+.3f° ; flèche « %s »"
                    "%s → azimut %+.3f°"
                    % (gamma, self.comboTaNorthRef.currentText(),
                       " ; déclinaison %+.2f°" % self.spinTaDecl.value()
                       if kind == core.NORD_MAGNETIQUE else "", az))

    def _ta_toggle_coupe_mode(self, *args):
        proj = self.radioTaProj.isChecked()
        self.spinTaAzimut.setEnabled(proj)
        self.chkTaInvert.setEnabled(proj)

    # --- métadonnées de calage (conservées dans le projet) ---------------
    def _ta_meta_key(self, what):
        return "ta/%s/%s" % (self._ta_safe(self._ta_name()), what)

    def _ta_store_meta(self, what, info):
        QgsProject.instance().writeEntry(PRJ_SCOPE, self._ta_meta_key(what),
                                         json.dumps(info, ensure_ascii=False))

    def _ta_read_meta(self, what):
        txt, ok = QgsProject.instance().readEntry(PRJ_SCOPE, self._ta_meta_key(what), "")
        try:
            return json.loads(txt) if ok and txt else None
        except ValueError:
            return None

    # --- rattachement à une station existante ----------------------------
    NAME_FIELDS = ("_NAME", "name", "nom", "NAME", "NOM", "station", "_STNAME")
    Z_FIELDS = ("z", "Z", "alt", "altitude", "_ALT", "ALT", "elev")

    def _ta_pick_existing_station(self):
        canvas = self.iface.mapCanvas()

        def done(points):
            click = points[0]
            dest = canvas.mapSettings().destinationCrs()
            tol = canvas.mapUnitsPerPixel() * 15
            best = None
            for lyr in QgsProject.instance().mapLayers().values():
                if (not isinstance(lyr, QgsVectorLayer)
                        or lyr.geometryType() != QgsWkbTypes.PointGeometry):
                    continue
                if lyr.customProperty(PROP + "internal"):
                    continue
                to_l = QgsCoordinateTransform(dest, lyr.crs(), QgsProject.instance())
                to_p = QgsCoordinateTransform(lyr.crs(), self._ta_crs(), QgsProject.instance())
                to_c = QgsCoordinateTransform(lyr.crs(), dest, QgsProject.instance())
                rect = to_l.transformBoundingBox(QgsRectangle(click.x() - tol, click.y() - tol,
                                                              click.x() + tol, click.y() + tol))
                for f in lyr.getFeatures(QgsFeatureRequest().setFilterRect(rect)):
                    g = f.geometry()
                    if g.isEmpty():
                        continue
                    pc = to_c.transform(QgsPointXY(g.asPoint()))
                    d = pc.distance(click)
                    if best is None or d < best[0]:
                        best = (d, lyr, f, to_p)
            if best is None:
                self._ta_msg("Aucun point trouvé sous le clic.", Qgis.Warning)
                return
            _, lyr, f, to_p = best
            v = next(f.geometry().vertices())
            xy = to_p.transform(QgsPointXY(v.x(), v.y()))
            z = v.z() if v.is3D() else None
            names = [n for n in self.NAME_FIELDS if lyr.fields().indexOf(n) >= 0]
            zf = [n for n in self.Z_FIELDS if lyr.fields().indexOf(n) >= 0]
            if (z is None or z != z) and zf:
                try:
                    z = float(f[zf[0]])
                except (TypeError, ValueError):
                    z = None
            self.spinTaEntryX.setValue(xy.x())
            self.spinTaEntryY.setValue(xy.y())
            if z is not None and z == z:
                self.spinTaEntryZ.setValue(z)
            if names and f[names[0]] not in (None, ""):
                nm = str(f[names[0]])
                sv = lyr.fields().indexOf("_SURVEY")
                if sv >= 0 and f[sv] not in (None, "") and "@" not in nm:
                    nm = "%s@%s" % (nm, f[sv])
                self.editTaEntryName.setText(nm)
            self._talog("📍 Rattachement : %s (%s) → X=%.2f Y=%.2f Z=%s"
                        % (self.editTaEntryName.text() or "?", lyr.name(), xy.x(), xy.y(),
                           "%.2f" % z if z is not None and z == z else "inconnu"))
            self.show()

        self._ta_tool = PointCollectorTool(canvas, 1, done, "#6A1B9A")
        canvas.setMapTool(self._ta_tool)
        self._ta_msg("Cliquez sur la station existante de rattachement (couche de points).")

    def _ta_calibrate_plan(self):
        layer = self._ta_layer("plan")
        if layer is None:
            QtWidgets.QMessageBox.warning(self, "Topo ancienne", "Aucune couche plan sélectionnée.")
            return
        src = layer.customProperty(PROP + "source") or layer.source()
        lid, lsrc = layer.id(), layer.source()
        try:
            if self.radioTaPlan2Pts.isChecked():
                if not self._ta_need("p1", "p2"):
                    return
                T = core.Similarity.from_two_points(
                    self._ta_picks["p1"][0], self._ta_picks["p2"][0],
                    (self.spinTaP1X.value(), self.spinTaP1Y.value()),
                    (self.spinTaP2X.value(), self.spinTaP2Y.value()))
            else:
                if not self._ta_need("entry", "scale", "north"):
                    return
                sc, no = self._ta_picks["scale"], self._ta_picks["north"]
                T = core.plan_calibration_scale_north(
                    self._ta_picks["entry"][0],
                    (self.spinTaEntryX.value(), self.spinTaEntryY.value()),
                    sc[0], sc[1], self.spinTaScaleLen.value(),
                    no[0], no[1], self.spinTaNorthAz.value())
            base = self._ta_safe(os.path.splitext(os.path.basename(src))[0])
            vrt = os.path.join(self._ta_out_dir(), "plan_%s_cale.vrt" % base)
            self._ta_write_vrt(src, vrt, T.geotransform())
            proj = QgsProject.instance()
            if lsrc != src and proj.mapLayer(lid) is not None:
                proj.removeMapLayer(lid)
            lyr = self._ta_add_raster(vrt, "Plan calé — " + base, "plan", src)
            lyr.setCustomProperty(PROP + "calibrated", True)
            self._ta_set_combo_layer(self.comboTaPlanLayer, lyr)
            self._ta_zoom_to_layer(lyr)
            self._ta_store_meta("calage_plan", dict(
                document=src, methode=("2 points" if self.radioTaPlan2Pts.isChecked()
                                       else "entrée + échelle + nord"),
                m_par_pixel=round(T.scale, 6), rotation_deg=round(T.rotation_deg, 4),
                azimut_fleche_deg=(self.spinTaNorthAz.value()
                                   if self.radioTaPlanNorth.isChecked() else None),
                entree=[self.spinTaEntryX.value(), self.spinTaEntryY.value()]))
            self._talog("✔ Plan calé : %.4f m/pixel (si scan à 300 dpi : échelle ≈ 1/%.0f), rotation %.2f°"
                        % (T.scale, T.scale / 0.0254 * 300, T.rotation_deg))
            self._talog("  → %s" % vrt)
        except Exception as e:
            self._talog("[ERREUR] calage plan : %s" % e)
            QtWidgets.QMessageBox.critical(self, "Calage plan", str(e))

    # --- décalage d'affichage de la coupe --------------------------------
    def _ta_coupe_offsets(self, create=False):
        proj = QgsProject.instance()
        key = "ta/%s/coupe_off" % self._ta_safe(self._ta_name())
        ox, ok1 = proj.readDoubleEntry(PRJ_SCOPE, key + "_x", 0.0)
        oy, ok2 = proj.readDoubleEntry(PRJ_SCOPE, key + "_y", 0.0)
        if ok1 and ok2:
            return ox, oy
        if not create:
            return None
        ex, ey = self.spinTaEntryX.value(), self.spinTaEntryY.value()
        if ex == 0 and ey == 0:
            plan = self._ta_layer("plan")
            if plan is not None and plan.customProperty(PROP + "calibrated"):
                c = plan.extent().center()
                ex, ey = c.x(), c.y()
        ox = float(round(ex))
        oy = float(round(ey)) - 10000.0   # la coupe s'affiche ~10 km sous le plan
        proj.writeEntryDouble(PRJ_SCOPE, key + "_x", ox)
        proj.writeEntryDouble(PRJ_SCOPE, key + "_y", oy)
        return ox, oy

    def _ta_calibrate_coupe(self):
        layer = self._ta_layer("coupe")
        if layer is None:
            QtWidgets.QMessageBox.warning(self, "Topo ancienne", "Aucune couche coupe sélectionnée.")
            return
        if not self._ta_need("cscale", "cref"):
            return
        src = layer.customProperty(PROP + "source") or layer.source()
        lid, lsrc = layer.id(), layer.source()
        try:
            ox, oy = self._ta_coupe_offsets(create=True)
            sc = self._ta_picks["cscale"]
            X_ref, Z_ref = self.spinTaCoupeRefX.value(), self.spinTaCoupeRefZ.value()
            T = core.section_calibration(self._ta_picks["cref"][0], (X_ref + ox, Z_ref + oy),
                                         sc[0], sc[1], self.spinTaCoupeScaleLen.value(),
                                         self.chkTaBarHoriz.isChecked())
            base = self._ta_safe(os.path.splitext(os.path.basename(src))[0])
            vrt = os.path.join(self._ta_out_dir(), "coupe_%s_calee.vrt" % base)
            self._ta_write_vrt(src, vrt, T.geotransform())
            proj = QgsProject.instance()
            if lsrc != src and proj.mapLayer(lid) is not None:
                proj.removeMapLayer(lid)
            lyr = self._ta_add_raster(vrt, "Coupe calée — " + base, "coupe", src)
            lyr.setCustomProperty(PROP + "calibrated", True)
            self._ta_set_combo_layer(self.comboTaCoupeLayer, lyr)
            self._ta_zoom_to_layer(lyr)
            self._ta_store_meta("calage_coupe", dict(
                document=src, m_par_pixel=round(T.scale, 6),
                redressement_deg=round(T.rotation_deg, 4),
                reference=[X_ref, Z_ref]))
            self._talog("✔ Coupe calée : %.4f m/pixel, redressement %.2f°" % (T.scale, T.rotation_deg))
            self._talog("  Affichage : X + %.0f, Z + %.0f (repère coupe décalé sous le plan)" % (ox, oy))
        except Exception as e:
            self._talog("[ERREUR] calage coupe : %s" % e)
            QtWidgets.QMessageBox.critical(self, "Calage coupe", str(e))

    # ------------------------------------------------------------------
    #  Couches de tracé et de stations (GeoPackage de numérisation)
    # ------------------------------------------------------------------
    FIELDS = {
        "trace_plan":     [("branche", TYPE_INT, 0)],
        "trace_coupe":    [("branche", TYPE_INT, 0)],
        "stations_plan":  [("branche", TYPE_INT, 0), ("ordre", TYPE_INT, 0),
                           ("nom", TYPE_STRING, 30), ("z_plan", TYPE_DOUBLE, 0)],
        "stations_coupe": [("branche", TYPE_INT, 0), ("ordre", TYPE_INT, 0),
                           ("nom", TYPE_STRING, 30)],
    }

    def _ta_find_loaded(self, gpkg, layername):
        norm = os.path.normcase(os.path.abspath(gpkg))
        for lyr in QgsProject.instance().mapLayers().values():
            if not isinstance(lyr, QgsVectorLayer):
                continue
            parts = lyr.source().split("|")
            try:
                same = os.path.normcase(os.path.abspath(parts[0])) == norm
            except Exception:
                same = False
            if same and any(p == "layername=" + layername for p in parts[1:]):
                return lyr
        return None

    def _ta_write_layer(self, mem, gpkg, layername):
        opts = QgsVectorFileWriter.SaveVectorOptions()
        opts.driverName = "GPKG"
        opts.fileEncoding = "UTF-8"
        opts.layerName = layername
        opts.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteLayer
                                     if os.path.exists(gpkg)
                                     else QgsVectorFileWriter.CreateOrOverwriteFile)
        res = QgsVectorFileWriter.writeAsVectorFormatV3(
            mem, gpkg, QgsProject.instance().transformContext(), opts)
        if res[0] != QgsVectorFileWriter.NoError:
            raise IOError("Écriture %s impossible : %s" % (layername, res[1]))

    def _ta_memory_layer(self, geom, name, fields):
        crs = self._ta_crs()
        lyr = QgsVectorLayer(geom + "?crs=" + (crs.authid() or ""), name, "memory")
        if not crs.authid():
            lyr.setCrs(crs)
        lyr.dataProvider().addAttributes(
            [_field(n, t, l) for n, t, l in fields])
        lyr.updateFields()
        return lyr

    def _ta_load_gpkg_layer(self, gpkg, layername, display, group=None):
        lyr = QgsVectorLayer("%s|layername=%s" % (gpkg, layername), display, "ogr")
        if not lyr.isValid():
            raise IOError("Couche invalide : %s|%s" % (gpkg, layername))
        proj = QgsProject.instance()
        proj.addMapLayer(lyr, False)
        root = proj.layerTreeRoot()
        grp_name = group or ("Topo ancienne — " + self._ta_name())
        grp = root.findGroup(grp_name) or root.insertGroup(0, grp_name)
        grp.insertLayer(0, lyr)
        return lyr

    def _ta_get_layer(self, layername, create=True):
        gpkg = self._ta_gpkg()
        lyr = self._ta_find_loaded(gpkg, layername)
        if lyr is not None:
            return lyr
        exists = False
        if os.path.exists(gpkg):
            test = QgsVectorLayer("%s|layername=%s" % (gpkg, layername), "t", "ogr")
            exists = test.isValid()
        if not exists:
            if not create:
                return None
            geom = "LineString" if layername.startswith("trace") else "Point"
            mem = self._ta_memory_layer(geom, layername, self.FIELDS[layername])
            self._ta_write_layer(mem, gpkg, layername)
        displays = {"trace_plan": "Tracé plan", "trace_coupe": "Tracé coupe",
                    "stations_plan": "Stations plan", "stations_coupe": "Stations coupe"}
        lyr = self._ta_load_gpkg_layer(gpkg, layername, displays[layername])
        self._ta_style_digit_layer(lyr, layername)
        return lyr

    def _ta_style_digit_layer(self, lyr, layername):
        try:
            if layername.startswith("trace"):
                color = "#E53935" if layername.endswith("plan") else "#1E88E5"
                sym = QgsLineSymbol.createSimple({"color": color, "width": "0.6"})
                lyr.setRenderer(QgsSingleSymbolRenderer(sym))
                idx = lyr.fields().indexOf("branche")
                lyr.setDefaultValueDefinition(
                    idx, QgsDefaultValue('coalesce(maximum("branche"), 0) + 1'))
                cfg = lyr.editFormConfig()
                cfg.setSuppress(QgsEditFormConfig.SuppressOn)
                lyr.setEditFormConfig(cfg)
            else:
                color = "#E53935" if layername.endswith("plan") else "#1E88E5"
                sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": "white",
                                                    "outline_color": color, "size": "2.2"})
                lyr.setRenderer(QgsSingleSymbolRenderer(sym))
                pal = QgsPalLayerSettings()
                pal.isExpression = True
                pal.fieldName = ('coalesce("nom", "branche" || \'.\' || "ordre")'
                                 + (' || if("z_plan" is not null, \' (\' || "z_plan" || \')\', \'\')'
                                    if layername.endswith("plan") else ""))
                pal.enabled = True
                lyr.setLabeling(QgsVectorLayerSimpleLabeling(pal))
                lyr.setLabelsEnabled(True)
            lyr.triggerRepaint()
        except Exception as e:
            self._talog("⚠ style %s : %s" % (layername, e))

    # --- tracé -------------------------------------------------------------
    def _ta_start_drawing(self, role):
        if role == "coupe" and self._ta_coupe_offsets() is None:
            QtWidgets.QMessageBox.warning(self, "Topo ancienne",
                                          "Calez d'abord la coupe avant de la tracer.")
            return
        try:
            lyr = self._ta_get_layer("trace_" + role)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Topo ancienne", str(e))
            return
        self._ta_set_combo_layer(self.comboTaPlanLine if role == "plan" else self.comboTaCoupeLine, lyr)
        self._ta_zoom(role)
        self.iface.setActiveLayer(lyr)
        if not lyr.isEditable():
            lyr.startEditing()
        self.iface.actionAddFeature().trigger()
        self._ta_msg("Tracez la polygonale du %s : un clic par station, clic droit pour finir la "
                     "branche. Puis « Terminer le tracé »." % role, duration=10)
        self._talog("✏ Tracé %s en cours (couche « %s »). Une polyligne par branche ; "
                    "le champ « branche » s'incrémente automatiquement." % (role, lyr.name()))

    def _ta_finish_drawing(self):
        n = 0
        for name in ("trace_plan", "trace_coupe"):
            lyr = self._ta_get_layer(name, create=False)
            if lyr is not None and lyr.isEditable():
                if not lyr.commitChanges():
                    self._talog("⚠ Enregistrement %s : %s" % (name, "; ".join(lyr.commitErrors())))
                else:
                    n += 1
        self.iface.actionPan().trigger()
        self._talog("✔ Tracé(s) enregistré(s) (%d couche(s))." % n)
        self._ta_make_stations()

    # --- stations ------------------------------------------------------------
    def _ta_line_vertices(self, layer):
        """{branche: [QgsPointXY]} (le multipart est concaténé)."""
        out = {}
        crs = self._ta_crs()
        xf = (QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
              if layer.crs() != crs else None)
        req = QgsFeatureRequest()
        fid_order = sorted(layer.getFeatures(req), key=lambda f: f.id())
        auto = 1
        for f in fid_order:
            g = QgsGeometry(f.geometry())
            if g.isEmpty():
                continue
            if xf:
                g.transform(xf)
            parts = g.asMultiPolyline() if g.isMultipart() else [g.asPolyline()]
            pts = [QgsPointXY(p) for part in parts for p in part]
            idx = layer.fields().indexOf("branche")
            b = f[idx] if idx >= 0 else None
            try:
                b = int(b)
            except (TypeError, ValueError):
                b = None
            if b is None:
                while auto in out:
                    auto += 1
                b = auto
            if b in out:
                self._talog("⚠ Branche %s en double dans « %s » : sommets ajoutés à la suite."
                            % (b, layer.name()))
                out[b].extend(pts)
            else:
                out[b] = pts
        return out

    def _ta_sync_stations(self, role):
        """Crée / met à jour la couche stations à partir du tracé, en
        conservant noms et cotes (par position, sinon par branche/ordre)."""
        line = self.get_layer_by_combo(self.comboTaPlanLine if role == "plan" else self.comboTaCoupeLine)
        if not isinstance(line, QgsVectorLayer) or line.geometryType() != QgsWkbTypes.LineGeometry:
            line = self._ta_get_layer("trace_" + role, create=False)
        if line is None:
            return None, {}
        verts = self._ta_line_vertices(line)
        st = self._ta_get_layer("stations_" + role)
        if st.isEditable():
            st.commitChanges()

        old = []
        for f in st.getFeatures():
            p = f.geometry().asPoint()
            old.append(dict(x=p.x(), y=p.y(), b=f["branche"], o=f["ordre"],
                            nom=f["nom"], z=f["z_plan"] if role == "plan" else None))
        # tolérance = 1 % de la longueur moyenne des tronçons (min. 5 cm)
        lens = []
        for pts in verts.values():
            lens += [pts[i].distance(pts[i + 1]) for i in range(len(pts) - 1)]
        tol = max(0.05, 0.01 * (sum(lens) / len(lens))) if lens else 0.05

        def pick_old(b, o, p):
            # position d'abord (même branche prioritaire : les jonctions
            # superposent des sommets de branches différentes)
            best, bkey = None, None
            for r in old:
                d = ((r["x"] - p.x()) ** 2 + (r["y"] - p.y()) ** 2) ** 0.5
                if d > tol:
                    continue
                key = (r["b"] != b, r["o"] != o, d)
                if bkey is None or key < bkey:
                    best, bkey = r, key
            if best is None:
                for r in old:
                    if r["b"] == b and r["o"] == o:
                        return r
            return best

        feats = []
        for b in sorted(verts):
            for o, p in enumerate(verts[b]):
                r = pick_old(b, o, p)
                f = QgsFeature(st.fields())
                f.setGeometry(QgsGeometry.fromPointXY(p))
                f["branche"] = b
                f["ordre"] = o
                f["nom"] = r["nom"] if r else None
                if role == "plan":
                    f["z_plan"] = r["z"] if r else None
                feats.append(f)
        st.startEditing()
        st.deleteFeatures([f.id() for f in st.getFeatures()])
        st.addFeatures(feats)
        st.commitChanges()
        st.triggerRepaint()
        return st, verts

    def _ta_make_stations(self):
        try:
            nb = {}
            for role in ("plan", "coupe"):
                st, verts = self._ta_sync_stations(role)
                if st is not None:
                    nb[role] = sum(len(v) for v in verts.values())
            self._talog("Stations : " + ", ".join("%s = %d" % kv for kv in nb.items()) +
                        ". Renseignez « nom » (appariement plan↔coupe) et « z_plan » "
                        "(cotes lues sur le plan) dans les tables attributaires.")
        except Exception as e:
            self._talog("[ERREUR] stations : %s" % e)

    def _ta_open_station_tables(self):
        for role in ("plan", "coupe"):
            lyr = self._ta_get_layer("stations_" + role, create=False)
            if lyr is not None:
                self.iface.showAttributeTable(lyr)

    def _ta_read_stations(self, role):
        st = self._ta_get_layer("stations_" + role, create=False)
        out = {}
        if st is None:
            return out
        for f in st.getFeatures():
            b, o = f["branche"], f["ordre"]
            nom = f["nom"]
            nom = None if (nom is None or (hasattr(nom, "isNull") and nom.isNull())) else str(nom)
            z = None
            if role == "plan":
                z = f["z_plan"]
                try:
                    z = None if z is None or (hasattr(z, "isNull") and z.isNull()) else float(z)
                except (TypeError, ValueError):
                    z = None
            out.setdefault(int(b), {})[int(o)] = (nom, z)
        return out

    # ------------------------------------------------------------------
    #  Calcul 3D
    # ------------------------------------------------------------------
    def _ta_run(self):
        self.textLogTa.clear()
        self.progressTa.setValue(0)
        name = self._ta_name()
        self._talog("▶ Polygonale 3D — %s" % name)
        try:
            st_plan, plan_verts = self._ta_sync_stations("plan")
            if st_plan is None or not plan_verts:
                QtWidgets.QMessageBox.warning(self, "Topo ancienne",
                                              "Aucun tracé plan : tracez d'abord la polygonale.")
                return
            st_coupe, coupe_verts = self._ta_sync_stations("coupe")
            offs = self._ta_coupe_offsets()
            if coupe_verts and offs is None:
                self._talog("⚠ Coupe tracée mais non calée : ignorée.")
                coupe_verts = {}
            self.progressTa.setValue(15)

            plan_st = self._ta_read_stations("plan")
            coupe_st = self._ta_read_stations("coupe") if coupe_verts else {}
            mode = core.MODE_PROJETEE if self.radioTaProj.isChecked() else core.MODE_DEVELOPPEE
            self._talog("Mode coupe : %s%s" % (
                "projetée (α = %.1f°)" % self.spinTaAzimut.value() if mode == core.MODE_PROJETEE
                else "développée", "" if coupe_verts else " — aucune coupe tracée"))

            resolved = {}      # nom → z (jonctions)
            placed = []        # (x, y, nom) des stations déjà calculées
            join_tol = self.spinTaJoinTol.value()
            entry_name = self.editTaEntryName.text().strip()
            branches_out = []
            used_names = set()
            n_b = len(plan_verts)
            for k, b in enumerate(sorted(plan_verts)):
                pts = plan_verts[b]
                meta = plan_st.get(b, {})
                names = [meta.get(o, (None, None))[0] for o in range(len(pts))]
                zp = [meta.get(o, (None, None))[1] for o in range(len(pts))]
                if k == 0 and entry_name and not names[0]:
                    names[0] = entry_name
                    if not zp[0] and self.spinTaEntryZ.value() and not coupe_verts.get(b):
                        zp[0] = self.spinTaEntryZ.value()
                cxz, cnames = [], []
                if b in coupe_verts:
                    ox, oy = offs
                    cxz = [(p.x() - ox, p.y() - oy) for p in coupe_verts[b]]
                    cm = coupe_st.get(b, {})
                    cnames = [cm.get(o, (None, None))[0] for o in range(len(cxz))]
                self._talog("— Branche %d : %d stations plan, %d sommets coupe"
                            % (b, len(pts), len(cxz)))
                # jonctions automatiques par proximité
                for o, p in enumerate(pts):
                    if names[o] or join_tol <= 0:
                        continue
                    near = [(p.distance(QgsPointXY(x, y)), n) for x, y, n in placed]
                    near = [t for t in near if t[0] <= join_tol]
                    if near:
                        names[o] = min(near)[1]
                        self._talog("   ↔ Jonction automatique : sommet %d.%d = station %s (%.2f m)"
                                    % (b, o, names[o], min(near)[0]))
                res = core.compute_altitudes(
                    [(p.x(), p.y()) for p in pts], names, cxz, cnames,
                    mode=mode, section_azimuth=self.spinTaAzimut.value(),
                    invert_axis=self.chkTaInvert.isChecked(),
                    pair_by_order=self.chkTaPairOrder.isChecked(),
                    plan_z=zp, fixed_z=resolved, tolerance=self.spinTaTol.value(),
                    default_z=self.spinTaEntryZ.value() if k == 0 else None,
                    log=lambda m: self._talog("   " + m))
                if all(r["z"] is None for r in res):
                    self._talog("   ⚠ Branche %d sans altitude (pas de jonction nommée ?) — ignorée." % b)
                    continue
                stations = []
                for o, (p, r) in enumerate(zip(pts, res)):
                    nom = core.therion_station_name(names[o], "B%d_%d" % (b, o))
                    if not names[o] and nom in used_names:
                        nom = "%s_%d" % (nom, k)
                    used_names.add(nom)
                    resolved.setdefault(names[o] or nom, r["z"])
                    placed.append((p.x(), p.y(), names[o] or nom))
                    stations.append(dict(branche=b, ordre=o, nom=nom, x=p.x(), y=p.y(), **r))
                counts = {}
                for s in stations:
                    counts[s["source"]] = counts.get(s["source"], 0) + 1
                self._talog("   Sources Z : " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
                gaps = [s["dz_plan_coupe"] for s in stations if s["dz_plan_coupe"] is not None]
                if gaps:
                    self._talog("   Écart cote plan − coupe : moy %.2f m, max |%.2f| m (n=%d)"
                                % (sum(gaps) / len(gaps), max(abs(g) for g in gaps), len(gaps)))
                branches_out.append(stations)
                self.progressTa.setValue(15 + int(55 * (k + 1) / n_b))

            if not branches_out:
                raise ValueError("Aucune altitude calculée.")
            self._ta_write_outputs(branches_out, offs if coupe_verts else None)
            self.progressTa.setValue(100)
            self._talog("✅ Terminé.")
        except Exception as e:
            import traceback
            self._talog("[ERREUR] %s" % e)
            self._talog(traceback.format_exc())
            QtWidgets.QMessageBox.critical(self, "Topo ancienne", str(e))

    def _ta_draw_section_guides(self, branches, offs):
        """Contrôle visuel sur la coupe calée : verticale de chaque station
        du plan (à son abscisse de coupe) et position 3D obtenue."""
        proj = QgsProject.instance()
        for lyr in list(proj.mapLayers().values()):
            if lyr.customProperty(PROP + "internal") == "guides":
                proj.removeMapLayer(lyr.id())
        ox, oy = offs
        sts = [s for br in branches for s in br if s.get("abscisse") is not None]
        if not sts:
            return
        zs = [s["z"] for s in sts]
        z0, z1 = min(zs) - 10.0, max(zs) + 10.0
        lines = self._ta_memory_layer("LineString", "Verticales stations (coupe)",
                                      [("nom", TYPE_STRING, 30), ("source_z", TYPE_STRING, 10)])
        pts = self._ta_memory_layer("Point", "Stations 3D sur la coupe",
                                    [("nom", TYPE_STRING, 30), ("source_z", TYPE_STRING, 10)])
        lf, pf = [], []
        for s in sts:
            X = s["abscisse"] + ox
            f = QgsFeature(lines.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY([QgsPointXY(X, z0 + oy), QgsPointXY(X, z1 + oy)]))
            f.setAttributes([s["nom"], s["source"]])
            lf.append(f)
            g = QgsFeature(pts.fields())
            g.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(X, s["z"] + oy)))
            g.setAttributes([s["nom"], s["source"]])
            pf.append(g)
        lines.dataProvider().addFeatures(lf)
        pts.dataProvider().addFeatures(pf)
        lines.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
            {"color": "#9E9E9E", "width": "0.2", "line_style": "dash"})))
        cats = [QgsRendererCategory(src, QgsMarkerSymbol.createSimple(
                    {"name": "circle", "color": col, "outline_color": "white", "size": "2.4"}), src)
                for src, col in SOURCE_COLORS.items()]
        pts.setRenderer(QgsCategorizedSymbolRenderer("source_z", cats))
        pal = QgsPalLayerSettings()
        pal.fieldName = "nom"
        pal.enabled = True
        pts.setLabeling(QgsVectorLayerSimpleLabeling(pal))
        pts.setLabelsEnabled(True)
        grp_name = "Topo ancienne — %s — contrôle coupe" % self._ta_name()
        root = proj.layerTreeRoot()
        grp = root.findGroup(grp_name) or root.insertGroup(0, grp_name)
        for lyr in (lines, pts):
            lyr.setCustomProperty(PROP + "internal", "guides")
            proj.addMapLayer(lyr, False)
            grp.insertLayer(0, lyr)
        self._talog("Contrôle coupe : %d verticales de stations affichées (couches mémoire)." % len(sts))

    def _ta_metadata_lines(self, branches):
        counts = {}
        for br in branches:
            for s in br:
                counts[s["source"]] = counts.get(s["source"], 0) + 1
        gaps = [s["dz_plan_coupe"] for br in branches for s in br if s["dz_plan_coupe"] is not None]
        cp, cc = self._ta_read_meta("calage_plan"), self._ta_read_meta("calage_coupe")
        mode = ("projetée, α = %.1f°%s" % (self.spinTaAzimut.value(),
                                           " (sens inversé)" if self.chkTaInvert.isChecked() else "")
                if self.radioTaProj.isChecked() else "développée")
        L = ["Cavité : %s" % self._ta_name(),
             "Date du levé d'origine : %s" % (self.editTaDate.text().strip() or "inconnue"),
             "Auteurs du levé d'origine : %s" % (self.editTaAuthors.text().strip() or "inconnus"),
             "Documents sources : %s" % (self.editTaSources.text().strip() or "non renseignés"),
             "Type de donnée : squelette reconstruit à partir de documents graphiques "
             "(spéléométrie dégradée)",
             "Numérisation : SpeleoTools (QGIS), %s" % datetime.date.today().isoformat(),
             "SCR : %s" % (self._ta_crs().authid() or self._ta_crs().description()),
             "Rattachement : %s X=%.2f Y=%.2f Z=%.2f" % (
                 branches[0][0]["nom"],
                 self.spinTaEntryX.value(), self.spinTaEntryY.value(), self.spinTaEntryZ.value())]
        if cp:
            L.append("Calage plan : %s — %s ; %.4f m/px ; rotation %.2f°%s" % (
                os.path.basename(cp.get("document", "?")), cp.get("methode"),
                cp.get("m_par_pixel", 0), cp.get("rotation_deg", 0),
                "" if cp.get("azimut_fleche_deg") is None
                else " ; azimut flèche nord %.2f°" % cp["azimut_fleche_deg"]))
        else:
            L.append("Calage plan : scan déjà géoréférencé (hors SpeleoTools)")
        if cc:
            L.append("Calage coupe : %s — coupe %s ; %.4f m/px ; redressement %.2f° ; réf. X=%.2f Z=%.2f" % (
                os.path.basename(cc.get("document", "?")), mode, cc.get("m_par_pixel", 0),
                cc.get("redressement_deg", 0), cc["reference"][0], cc["reference"][1]))
        else:
            L.append("Calage coupe : aucune coupe utilisée")
        L.append("Origine des altitudes : " + ", ".join(
            "%s=%d" % kv for kv in sorted(counts.items())))
        if gaps:
            L.append("Écart cote plan − coupe : moy %.2f m, max |%.2f| m (n=%d)" % (
                sum(gaps) / len(gaps), max(abs(g) for g in gaps), len(gaps)))
        return L

    def _ta_compare_reference(self):
        """Compare les stations reconstruites à un levé fiable (figure de
        contrôle : écarts par station homologue)."""
        ref = self.get_layer_by_combo(self.comboTaRefLayer)
        if not isinstance(ref, QgsVectorLayer) or ref.geometryType() != QgsWkbTypes.PointGeometry:
            QtWidgets.QMessageBox.warning(self, "Topo ancienne",
                                          "Choisissez une couche de points de référence.")
            return
        out_dir = self._ta_out_dir()
        safe = self._ta_safe(self._ta_name())
        gpkg = os.path.join(out_dir, safe + "_topo3d.gpkg")
        st = (self._ta_find_loaded(gpkg, "stations_3d")
              or QgsVectorLayer("%s|layername=stations_3d" % gpkg, "stations_3d", "ogr"))
        if not st.isValid() or st.featureCount() == 0:
            QtWidgets.QMessageBox.warning(self, "Topo ancienne",
                                          "Lancez d'abord le calcul de la polygonale 3D.")
            return

        # une station de jonction apparaît dans deux branches : on ne la compte
        # qu'une fois
        stations, vus = [], set()
        for f in st.getFeatures():
            nom = str(f["nom"])
            if nom in vus:
                continue
            vus.add(nom)
            stations.append(dict(nom=nom, x=float(f["x"]), y=float(f["y"]),
                                 z=float(f["z"]), source=f["source_z"]))

        # dictionnaire des stations de référence (nom → x, y, z)
        names = [n for n in self.NAME_FIELDS if ref.fields().indexOf(n) >= 0]
        if not names:
            QtWidgets.QMessageBox.warning(
                self, "Topo ancienne",
                "La couche de référence n'a aucun champ de nom reconnu (%s)."
                % ", ".join(self.NAME_FIELDS))
            return
        zf = [n for n in self.Z_FIELDS if ref.fields().indexOf(n) >= 0]
        sv = ref.fields().indexOf("_SURVEY")
        xf = (QgsCoordinateTransform(ref.crs(), self._ta_crs(), QgsProject.instance())
              if ref.crs() != self._ta_crs() else None)
        reference = {}
        for f in ref.getFeatures():
            nom = f[names[0]]
            if nom is None or str(nom) == "":
                continue
            nom = str(nom)
            g = f.geometry()
            if g.isEmpty():
                continue
            v = next(g.vertices())
            p = QgsPointXY(v.x(), v.y())
            if xf:
                p = xf.transform(p)
            z = v.z() if v.is3D() else None
            if (z is None or z != z) and zf:
                try:
                    z = float(f[zf[0]])
                except (TypeError, ValueError):
                    z = None
            reference[nom] = (p.x(), p.y(), z)
            if sv >= 0 and f[sv] not in (None, ""):
                reference["%s@%s" % (nom, f[sv])] = (p.x(), p.y(), z)

        couples, stats = core.compare_to_reference(stations, reference)
        if not couples:
            self._talog("⚠ Aucune station homologue : les noms doivent être identiques "
                        "dans les deux couches (%d stations, %d références)."
                        % (len(stations), len(reference)))
            QtWidgets.QMessageBox.information(
                self, "Topo ancienne",
                "Aucune station de même nom dans les deux couches.")
            return

        self._talog("📏 Comparaison avec « %s » : %d station(s) homologue(s)"
                    % (ref.name(), stats["n"]))
        self._talog("   Écart planimétrique : moyenne %.2f m, max %.2f m, RMS %.2f m"
                    % (stats["moy_2d"], stats["max_2d"], stats["rms_2d"]))
        if "moy_dz" in stats:
            self._talog("   Écart altimétrique : moyenne %+.2f m, max %+.2f m (n=%d) ; "
                        "RMS 3D %.2f m" % (stats["moy_dz"], stats["max_dz"],
                                           stats["n_z"], stats["rms_3d"]))

        # CSV
        csv_path = os.path.join(out_dir, safe + "_ecarts_reference.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["nom", "source_z", "dx_m", "dy_m", "dz_m", "d2d_m", "d3d_m"])
            for c in couples:
                w.writerow([c["nom"], c["source"], round(c["dx"], 3), round(c["dy"], 3),
                            "" if c["dz"] is None else round(c["dz"], 3),
                            round(c["d2d"], 3),
                            "" if c["d3d"] is None else round(c["d3d"], 3)])
        self._talog("   CSV : %s" % csv_path)

        # couche de vecteurs d'écart
        proj = QgsProject.instance()
        for lyr in list(proj.mapLayers().values()):
            if lyr.customProperty(PROP + "internal") == "ecarts":
                proj.removeMapLayer(lyr.id())
        vec = self._ta_memory_layer("LineString", "Écarts / référence", [
            ("nom", TYPE_STRING, 30), ("source_z", TYPE_STRING, 10),
            ("dx", TYPE_DOUBLE, 0), ("dy", TYPE_DOUBLE, 0), ("dz", TYPE_DOUBLE, 0),
            ("d2d", TYPE_DOUBLE, 0), ("d3d", TYPE_DOUBLE, 0)])
        feats = []
        index = {s["nom"]: s for s in stations}
        for c in couples:
            s = index[c["nom"]]
            r = reference[c["nom"]]
            f = QgsFeature(vec.fields())
            f.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(r[0], r[1]), QgsPointXY(s["x"], s["y"])]))
            f.setAttributes([c["nom"], c["source"], round(c["dx"], 3), round(c["dy"], 3),
                             None if c["dz"] is None else round(c["dz"], 3),
                             round(c["d2d"], 3),
                             None if c["d3d"] is None else round(c["d3d"], 3)])
            feats.append(f)
        vec.dataProvider().addFeatures(feats)
        vec.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple(
            {"color": "#C62828", "width": "0.6"})))
        vec.setCustomProperty(PROP + "internal", "ecarts")
        proj.addMapLayer(vec, False)
        root = proj.layerTreeRoot()
        grp_name = "Topo ancienne — %s — contrôle" % self._ta_name()
        grp = root.findGroup(grp_name) or root.insertGroup(0, grp_name)
        grp.insertLayer(0, vec)
        self._talog("   Couche « Écarts / référence » ajoutée (vecteur référence → reconstruction).")
        return stats

    def _ta_write_outputs(self, branches, offs=None):
        out_dir = self._ta_out_dir()
        safe = self._ta_safe(self._ta_name())
        gpkg = os.path.join(out_dir, safe + "_topo3d.gpkg")
        for ln in ("stations_3d", "visees_3d", "polygonale_3d"):
            self._ta_remove_layers_with_source(gpkg, ln)

        # --- stations 3D --------------------------------------------------
        st = self._ta_memory_layer("PointZ", "stations_3d", [
            ("branche", TYPE_INT, 0), ("ordre", TYPE_INT, 0),
            ("nom", TYPE_STRING, 30), ("x", TYPE_DOUBLE, 0),
            ("y", TYPE_DOUBLE, 0), ("z", TYPE_DOUBLE, 0),
            ("source_z", TYPE_STRING, 10), ("z_plan", TYPE_DOUBLE, 0),
            ("z_coupe", TYPE_DOUBLE, 0), ("dz_plan_coupe", TYPE_DOUBLE, 0),
            ("dist_plan", TYPE_DOUBLE, 0), ("abscisse_coupe", TYPE_DOUBLE, 0)])
        feats = []
        for br in branches:
            for s in br:
                f = QgsFeature(st.fields())
                f.setGeometry(QgsGeometry(QgsPoint(s["x"], s["y"], s["z"])))
                f.setAttributes([s["branche"], s["ordre"], s["nom"], round(s["x"], 3),
                                 round(s["y"], 3), round(s["z"], 3), s["source"],
                                 s["z_plan"], s["z_coupe"], s["dz_plan_coupe"],
                                 round(s["dist_plan"], 3), s["abscisse"]])
                feats.append(f)
        st.dataProvider().addFeatures(feats)
        self._ta_write_layer(st, gpkg, "stations_3d")

        # --- visées 3D + polygonale ------------------------------------------
        vi = self._ta_memory_layer("LineStringZ", "visees_3d", [
            ("branche", TYPE_INT, 0), ("de", TYPE_STRING, 30),
            ("vers", TYPE_STRING, 30), ("longueur", TYPE_DOUBLE, 0),
            ("long_horiz", TYPE_DOUBLE, 0), ("azimut", TYPE_DOUBLE, 0),
            ("pente", TYPE_DOUBLE, 0), ("source_de", TYPE_STRING, 10),
            ("source_vers", TYPE_STRING, 10)])
        po = self._ta_memory_layer("LineStringZ", "polygonale_3d", [
            ("branche", TYPE_INT, 0), ("nb_stations", TYPE_INT, 0),
            ("dev_3d", TYPE_DOUBLE, 0), ("z_min", TYPE_DOUBLE, 0),
            ("z_max", TYPE_DOUBLE, 0)])
        vfeats, pfeats, rows = [], [], []
        total = 0.0
        for br in branches:
            dev = 0.0
            for a, b in zip(br[:-1], br[1:]):
                l3, h, az, cl = core.shot_measures((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
                dev += l3
                f = QgsFeature(vi.fields())
                f.setGeometry(QgsGeometry.fromPolyline([QgsPoint(a["x"], a["y"], a["z"]),
                                                        QgsPoint(b["x"], b["y"], b["z"])]))
                f.setAttributes([a["branche"], a["nom"], b["nom"], round(l3, 2), round(h, 2),
                                 round(az, 1), round(cl, 1), a["source"], b["source"]])
                vfeats.append(f)
                rows.append([a["branche"], a["nom"], b["nom"], round(l3, 2), round(az, 1),
                             round(cl, 1), round(a["z"], 2), round(b["z"], 2),
                             a["source"], b["source"]])
            total += dev
            zs = [s["z"] for s in br]
            f = QgsFeature(po.fields())
            f.setGeometry(QgsGeometry.fromPolyline([QgsPoint(s["x"], s["y"], s["z"]) for s in br]))
            f.setAttributes([br[0]["branche"], len(br), round(dev, 2), round(min(zs), 2), round(max(zs), 2)])
            pfeats.append(f)
        vi.dataProvider().addFeatures(vfeats)
        po.dataProvider().addFeatures(pfeats)
        self._ta_write_layer(vi, gpkg, "visees_3d")
        self._ta_write_layer(po, gpkg, "polygonale_3d")

        all_z = [s["z"] for br in branches for s in br]
        self._talog("Développement 3D : %.1f m — dénivelé : %.1f m (%.1f → %.1f)"
                    % (total, max(all_z) - min(all_z), max(all_z), min(all_z)))

        # --- chargement + symbologie par source ----------------------------------
        grp = "Topo ancienne — %s — 3D" % self._ta_name()
        lp = self._ta_load_gpkg_layer(gpkg, "polygonale_3d", "Polygonale 3D", grp)
        lv = self._ta_load_gpkg_layer(gpkg, "visees_3d", "Visées 3D", grp)
        ls = self._ta_load_gpkg_layer(gpkg, "stations_3d", "Stations 3D (source Z)", grp)
        qml = os.path.join(os.path.dirname(__file__), "styles_therion", "Style_Shots3D.qml")
        if os.path.isfile(qml):
            lv.loadNamedStyle(qml)
        lp.setRenderer(QgsSingleSymbolRenderer(QgsLineSymbol.createSimple({"color": "#333333", "width": "0.4"})))
        cats = []
        for src, col in SOURCE_COLORS.items():
            sym = QgsMarkerSymbol.createSimple({"name": "circle", "color": col,
                                                "outline_color": "white", "size": "2.4"})
            cats.append(QgsRendererCategory(src, sym, src))
        ls.setRenderer(QgsCategorizedSymbolRenderer("source_z", cats))
        for lyr in (lp, lv, ls):
            lyr.triggerRepaint()
        self._talog("GPKG : %s" % gpkg)

        # --- CSV -------------------------------------------------------------
        csv_path = os.path.join(out_dir, safe + "_visees_3d.csv")
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["branche", "de", "vers", "longueur_m", "azimut_deg", "pente_deg",
                        "z_de", "z_vers", "source_z_de", "source_z_vers"])
            w.writerows(rows)
        self._talog("CSV : %s" % csv_path)

        # --- Métadonnées -------------------------------------------------------
        meta_lines = self._ta_metadata_lines(branches)
        meta_path = os.path.join(out_dir, safe + "_metadonnees.txt")
        with open(meta_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(meta_lines) + "\n")
        self._talog("Métadonnées : %s" % meta_path)

        if offs is not None and self.chkTaGuides.isChecked():
            self._ta_draw_section_guides(branches, offs)

        # --- Therion -----------------------------------------------------------
        if self.chkTaExportTh.isChecked():
            th_path = os.path.join(out_dir, safe + "_ancienne.th")
            team = [t for t in self.editTaAuthors.text().split(",") if t.strip()]
            style = "normal" if self.comboTaThStyle.currentIndex() == 1 else "cartesian"
            gamma = 0.0
            if style == "normal":
                try:
                    gamma = self._ta_grid_convergence(branches[0][0]["x"], branches[0][0]["y"])
                except Exception:
                    gamma = 0.0
                self._talog("Therion : visées normales, azimuts = gisement %+.3f° "
                            "(convergence des méridiens), declination 0." % gamma)
            txt = core.therion_centreline(safe, branches, self._ta_crs().authid() or None,
                                          title=self._ta_name(), date=self.editTaDate.text(),
                                          team=team, header=meta_lines,
                                          fix_first="@" not in branches[0][0]["nom"],
                                          style=style, convergence=gamma)
            with open(th_path, "w", encoding="utf-8") as fh:
                fh.write(txt)
            self._talog("Therion : %s" % th_path)
