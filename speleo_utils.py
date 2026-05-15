from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFields, QgsField, QgsFeature,
    QgsGeometry, QgsPointXY, QgsPoint, QgsDistanceArea, QgsMessageLog, Qgis,QgsWkbTypes,QgsVectorFileWriter,QgsApplication,QgsRasterLayer,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem)
from PyQt5.QtCore import QVariant
from qgis.PyQt.QtCore import QMetaType

import processing
from processing.core.Processing import Processing
import os
import tempfile

# ensure processing is initialized
Processing.initialize()


import math
# ---------- UTILITAIRES ----------
def sample_raster_at_point(raster_layer, qgs_point):
    from qgis.core import QgsPointXY, QgsCoordinateTransform, QgsProject
    
    # convert 3D point en 2D
    point_xy = QgsPointXY(qgs_point.x(), qgs_point.y())
    
    # transformation CRS si nécessaire
    if raster_layer.crs() != QgsProject.instance().crs():
        transform = QgsCoordinateTransform(QgsProject.instance().crs(), raster_layer.crs(), QgsProject.instance())
        point_xy = transform.transform(point_xy)
    
    val, ok = raster_layer.dataProvider().sample(point_xy, 1)
    if ok:
        return float(val)
    else:
        return None


def layer_feature_elevation(feat):
    """
    Retourne une altitude pour une feature vectorielle :
    - si géométrie Z : retourne la Z minimale des sommets (ou moyenne)
    - sinon cherche un champ commun ('elev','z','alt','altitude')
    - si rien, retourne None
    """
    geom = feat.geometry()
    # si géométrie avec Z
    if geom.isMultipart():
        parts = geom.asMultiPolyline() if geom.type() == QgsWkbTypes.LineGeometry else None
    # On essaye d'extraire z depuis les vertices
    try:
        # récupère tous les vertices z si présents
        zs = []
        for p in geom.vertices():
            if p.z() is not None:
                zs.append(p.z())
        if zs:
            return float(min(zs))  # on prend min (profondeur)
    except Exception:
        pass

    # sinon check champs usuels
    for fld in ('elev', 'z', 'alt', 'altitude', 'depth'):
        if fld in [f.name().lower() for f in feat.fields()]:
            try:
                return float(feat.attribute(fld))
            except Exception:
                pass

    return None

# ---------- 1) ÉPAISSEUR ----------
def compute_thickness(dem_layer, cave_layer, out_path=None, layer_name="Thickness"):
    """
    Échantillonne le DEM pour chaque sommet de la couche cave_layer,
    récupère l'altitude de la cavité (géométrie z ou champ), calcule
    surface_elev - cave_elev et renvoie une couche mémoire contenant
    des points avec l'attribut 'thickness'.
    Si out_path (chemin .gpkg) fourni, sauvegarde la couche.
    """
    # Préparation couche sortie (points)
    fields = QgsFields()
    fields.append(QgsField("src_elev", QVariant.Double))
    fields.append(QgsField("cave_elev", QVariant.Double))
    fields.append(QgsField("thickness", QVariant.Double))
    fields.append(QgsField("fid_src", QVariant.Int))

    mem_layer = QgsVectorLayer("Point?crs=" + dem_layer.crs().authid(), "thickness_points", "memory")
    mem_dp = mem_layer.dataProvider()
    mem_dp.addAttributes(fields)
    mem_layer.updateFields()

    da = QgsDistanceArea()
    features_added = 0

    # Ensemble pour stocker les points déjà ajoutés (arrondis à 10 cm)
    added_points = set()

    for feat in cave_layer.getFeatures():
        geom = feat.geometry()
        geom_type = QgsWkbTypes.geometryType(geom.wkbType())

        if geom_type == QgsWkbTypes.PointGeometry:
            pts = [QgsPointXY(geom.asPoint())]
        elif geom_type == QgsWkbTypes.LineGeometry:
            pts = [QgsPointXY(v) for v in geom.vertices()]
        else:
            continue  # ignorer autres types

        # Boucle principale sur les vertices
        for p in pts:
            # Arrondir les coordonnées à 10 cm (0.1 m)
            x_rounded = round(p.x(), 2)
            y_rounded = round(p.y(), 2)

            # Si le point arrondi existe déjà, ignorer
            if (x_rounded, y_rounded) in added_points:
                continue

            # Ajouter le point arrondi à l'ensemble
            added_points.add((x_rounded, y_rounded))

            # Calcul thickness
            surf_elev = sample_raster_at_point(dem_layer, QgsPointXY(p.x(), p.y()))
            try:
                cave_elev = float(p.z()) if p.z() is not None else None
            except Exception:
                cave_elev = None

            if cave_elev is None:
                cave_elev = layer_feature_elevation(feat)
            if surf_elev is None or cave_elev is None:
                continue

            thickness = surf_elev - cave_elev
            new_feat = QgsFeature()
            new_feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(p.x(), p.y())))
            new_feat.setFields(mem_layer.fields())
            new_feat['src_elev'] = surf_elev
            new_feat['cave_elev'] = cave_elev
            new_feat['thickness'] = thickness
            new_feat['fid_src'] = feat.id()
            mem_dp.addFeatures([new_feat])
            features_added += 1

    mem_layer.updateExtents()

    # Sauvegarde si demandé
    if out_path:
        try:
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = layer_name
            options.fileEncoding = "UTF-8"
            options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
            options.sourceCrs = mem_layer.crs()

            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                mem_layer,
                out_path,
                QgsProject.instance().transformContext(),
                options
            )

            if error[0] == QgsVectorFileWriter.NoError:
                QgsMessageLog.logMessage(
                    f"Couche sauvegardée avec succès : {out_path}",
                    "SpeleoTools",
                    Qgis.Info
                )

                saved_layer = QgsVectorLayer(
                    out_path,
                    f"{layer_name}_saved",
                    "ogr"
                )

                if saved_layer.isValid():
                    QgsProject.instance().addMapLayer(saved_layer)
                    QgsMessageLog.logMessage(
                        "Couche sauvegardée chargée dans le projet QGIS.",
                        "SpeleoTools",
                        Qgis.Info
                    )
                else:
                    QgsMessageLog.logMessage(
                        f"Erreur : Impossible de charger la couche sauvegardée depuis {out_path}.",
                        "SpeleoTools",
                        Qgis.Critical
                    )
            else:
                QgsMessageLog.logMessage(
                    f"Erreur lors de la sauvegarde : {error[1]}",
                    "SpeleoTools",
                    Qgis.Critical
                )

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Exception lors de la sauvegarde : {str(e)}",
                "SpeleoTools",
                Qgis.Critical
            )
    else:
        QgsProject.instance().addMapLayer(mem_layer)
        QgsMessageLog.logMessage(
            "Couche mémoire ajoutée au projet (non sauvegardée).",
            "SpeleoTools",
            Qgis.Info
        )
    return mem_layer


# ---------- 2) PROFIL (version améliorée) ----------

def transform_point_to_dem_crs(point_xy, line_crs, dem_crs, proj):
    """Transforme un point du CRS de la ligne vers le CRS du MNT.
    Retourne un QgsPointXY dans le CRS du DEM."""
    if line_crs != dem_crs:
        xform = QgsCoordinateTransform(line_crs, dem_crs, proj)
        pt = xform.transform(point_xy)
        return QgsPointXY(pt.x(), pt.y())
    return QgsPointXY(point_xy.x(), point_xy.y())

def sample_dem_at_point(dem_layer, point_xy):
    """Échantillonne le MNT au point donné.
    ATTENTION : point_xy doit être dans le CRS du DEM (QgsPointXY)."""
    dp = dem_layer.dataProvider()
    # Convertir en point adapté
    sample_point = QgsPointXY(point_xy.x(), point_xy.y())
    # Essayer dataProvider.sample (si disponible)
    try:
        samp = dp.sample(sample_point, 1)
    except Exception:
        samp = None

    # si sample a renvoyé quelque chose d'utilisable
    if samp is not None:
        # dp.sample peut renvoyer tuple (val, ok) ou simplement la valeur
        if isinstance(samp, (tuple, list)):
            val = samp[0] if samp else None
            ok = samp[1] if len(samp) > 1 else True
            try:
                return float(val) if ok and val is not None and not math.isnan(float(val)) else None
            except Exception:
                return None
        else:
            try:
                return float(samp) if samp is not None and not math.isnan(float(samp)) else None
            except Exception:
                return None

    # fallback : utiliser identify (plus lent mais parfois nécessaire)
    try:
        ident = dp.identify(sample_point, dp.IdentifyFormatValue)
        if ident.isValid():
            results = list(ident.results().values())
            if results:
                val = results[0]
                try:
                    return float(val) if val is not None and not math.isnan(float(val)) else None
                except Exception:
                    return None
    except Exception:
        pass

    return None


def interpolate_z_values(z_list, sample_points, spacing, max_gap_distance):
    """Interpole les valeurs Z manquantes entre deux points valides.
    Renvoie une liste de segments; chaque segment est une liste de QgsPoint (avec Z)."""
    points_3d_segments = []
    i = 0
    n = len(z_list)
    while i < n:
        if z_list[i] is not None:
            seg = [QgsPoint(sample_points[i].x(), sample_points[i].y(), z_list[i])]
            i += 1
            while i < n and z_list[i] is not None:
                seg.append(QgsPoint(sample_points[i].x(), sample_points[i].y(), z_list[i]))
                i += 1
            points_3d_segments.append(seg)
        else:
            j = i + 1
            while j < n and z_list[j] is None:
                j += 1
            if j < n:
                prev_idx = i - 1
                next_idx = j
                if prev_idx >= 0 and z_list[prev_idx] is not None:
                    hole_len = calculate_hole_length(sample_points, prev_idx, next_idx, spacing)
                    if max_gap_distance is None or hole_len <= max_gap_distance:
                        interp_pts = create_interpolated_points(z_list, sample_points, prev_idx, next_idx)
                        if points_3d_segments and is_continuous(points_3d_segments[-1], sample_points[prev_idx]):
                            points_3d_segments[-1].extend(interp_pts)
                        else:
                            segstart = QgsPoint(sample_points[prev_idx].x(), sample_points[prev_idx].y(), z_list[prev_idx])
                            seg = [segstart] + interp_pts
                            points_3d_segments.append(seg)
                        i = next_idx
                        continue
            i = j
    return points_3d_segments


def calculate_hole_length(sample_points, prev_idx, next_idx, spacing):
    """Calcule la longueur d'un trou entre deux points."""
    if spacing and spacing > 0:
        return (next_idx - prev_idx) * spacing
    else:
        return sum(math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                   for p1, p2 in zip(sample_points[prev_idx:next_idx], sample_points[prev_idx+1:next_idx]))


def create_interpolated_points(z_list, sample_points, prev_idx, next_idx):
    """Crée des points interpolés entre deux indices (exclut les extrémités)."""
    z0 = z_list[prev_idx]
    z1 = z_list[next_idx]
    steps = next_idx - prev_idx
    return [QgsPoint(sample_points[prev_idx + step].x(),
                     sample_points[prev_idx + step].y(),
                     z0 + (step / float(steps)) * (z1 - z0))
            for step in range(1, steps)]


def is_continuous(segment, point):
    """Vérifie si un segment se termine au point donné (tolérance pour floats)."""
    return (math.isclose(segment[-1].x(), point.x(), abs_tol=1e-6) and
            math.isclose(segment[-1].y(), point.y(), abs_tol=1e-6))


def create_profile_from_line(dem_layer, line_layer, spacing=None, output_path=None, interp=True, max_gap_distance=None, add_to_project=True):
    """Crée un profil 3D (LineStringZ) à partir d'une polyligne 2D/3D."""
    proj = QgsProject.instance()
    dem_crs = dem_layer.crs()
    line_crs = line_layer.crs()
    need_transform = (dem_crs != line_crs)

    # on met la couche de sortie dans le CRS du DEM pour garder cohérence Z+XY
    crs_authid = dem_crs.authid()
    geom_type = f"LineStringZ?crs={crs_authid}"
    out_layer = QgsVectorLayer(geom_type, "profiles", "memory")
    pr = out_layer.dataProvider()
    fields = QgsFields()
    fields.append(QgsField("orig_id", QMetaType.Type.Int))
    fields.append(QgsField("length_m", QMetaType.Type.Double))

    # fields.append(QgsField("orig_id", QVariant.Int))
    # fields.append(QgsField("length_m", QVariant.Double))
    pr.addAttributes(fields)
    out_layer.updateFields()
    # distance calculator (utile si spacing non fourni)
    d_area = QgsDistanceArea()
    if hasattr(proj, "transformContext"):
        d_area.setSourceCrs(dem_crs, proj.transformContext())
    else:
        d_area.setSourceCrs(dem_crs)
    # itérer features
    for feat in line_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue

        # si besoin, on travaille sur une copie transformée dans le CRS du DEM
        geom_dem = QgsGeometry(geom)  # copie
        if need_transform:
            try:
                xform = QgsCoordinateTransform(line_crs, dem_crs, proj)
                geom_dem.transform(xform)
            except Exception as e:
                print(f"Erreur de transformation pour feature {feat.id()}: {e}")
                continue

        # gérer multipart ou singlepart
        if geom_dem.isMultipart():
            raw_parts = geom_dem.asMultiPolyline()
        else:
            raw_parts = [geom_dem.asPolyline()]

        # pour chaque partie
        for raw_part in raw_parts:
            if not raw_part:
                continue

            # Normaliser tous les points en QgsPointXY (dans le CRS du DEM maintenant)
            part_xy = [QgsPointXY(p.x(), p.y()) for p in raw_part]

            # construire une geometry 2D pour interpolation (fromPolylineXY)
            line_geom = QgsGeometry.fromPolylineXY(part_xy)

            # longueur de la partie
            length = line_geom.length()

            # déterminer points d'échantillonnage (liste de QgsPointXY)
            sample_points = []
            if spacing is None or spacing <= 0:
                # utiliser les sommets
                sample_points = part_xy[:]
            else:
                # échantillonnage régulier le long de la ligne (0..length)
                dist = 0.0
                while dist <= length + 1e-9:
                    interp_geom = line_geom.interpolate(dist)
                    if interp_geom is None or interp_geom.isEmpty():
                        break
                    p = interp_geom.asPoint()
                    sample_points.append(QgsPointXY(p.x(), p.y()))
                    dist += spacing
                # s'assurer d'avoir le dernier point exact
                end_p = line_geom.interpolate(length).asPoint()
                lastxy = QgsPointXY(end_p.x(), end_p.y())
                if (not sample_points) or (not math.isclose(sample_points[-1].x(), lastxy.x(), abs_tol=1e-6) or
                                           not math.isclose(sample_points[-1].y(), lastxy.y(), abs_tol=1e-6)):
                    sample_points.append(lastxy)

            if not sample_points:
                continue

            # échantillonner DEM pour chaque sample point (point déjà en CRS DEM)
            z_list = []
            for pxy in sample_points:
                z = sample_dem_at_point(dem_layer, pxy)
                z_list.append(z)

            points_3d_segments = []
            cur_seg = []
            for idx, z in enumerate(z_list):
                if z is None:
                    if len(cur_seg) >= 2:
                        points_3d_segments.append(cur_seg)
                    cur_seg = []
                else:
                    cur_seg.append(QgsPoint(sample_points[idx].x(), sample_points[idx].y(), z))
            if len(cur_seg) >= 2:
                points_3d_segments.append(cur_seg)

            # créer features de sortie pour chaque segment
            feats_to_add = []
            for seg in points_3d_segments:
                if len(seg) < 2:
                    continue
                feat_out = QgsFeature(out_layer.fields())
                # seg est une liste de QgsPoint (avec Z) -> fromPolyline crée LineStringZ si points ont Z
                feat_geom = QgsGeometry.fromPolyline(seg)
                feat_out.setGeometry(feat_geom)
                feat_out.setAttribute("orig_id", int(feat.id()))
                feat_out.setAttribute("length_m", float(feat_geom.length()))
                feats_to_add.append(feat_out)

            if feats_to_add:
                pr.addFeatures(feats_to_add)

    out_layer.updateExtents()

    # sauvegarder si demandé (ex: shapefile)
    if output_path:
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "ESRI Shapefile"
        options.fileEncoding = "UTF-8"
        error = QgsVectorFileWriter.writeAsVectorFormatV3(
            out_layer, output_path,
            QgsProject.instance().transformContext(),
            options
        )
        if error[0] == QgsVectorFileWriter.NoError:
            disk_layer = QgsVectorLayer(output_path, "profiles_saved", "ogr")
            if disk_layer.isValid():
                out_layer = disk_layer

    if add_to_project:
        QgsProject.instance().addMapLayer(out_layer)

    return out_layer

# ---------- 3) Traitement MNT ----------
"""
Module contenant fonctions de traitement des MNT pour le plugin QGIS.
Fonctions exposées :
- hillshade(dem_layer, out_path=None, params..., context=None, feedback=None)
- multidirectional_hillshade(dem_layer, out_path=None, azimuths=None, context=None, feedback=None)
- slope(dem_layer, out_path=None, params..., context=None, feedback=None)
- vat(dem_layer, out_path=None, window_size=5, context=None, feedback=None)

Chaque fonction tente de choisir automatiquement un algorithme de processing disponible
(GDAL / SAGA / GRASS) et renvoie le chemin du raster de sortie (ou None en cas d'erreur).
"""



def _available_algorithms():
    """Renvoie l'ensemble des ids d'algorithmes disponibles."""
    return {alg.id() for alg in QgsApplication.processingRegistry().algorithms()}


def _choose_alg(possible_ids):
    """Choisit le premier algorithme disponible dans possible_ids."""
    avail = _available_algorithms()
    for pid in possible_ids:
        if pid in avail:
            return pid
    return None


def _layer_input(layer):
    """Accepte soit un QgsRasterLayer soit un nom (str) et renvoie l'identifiant attendu par processing."""
    from qgis.core import QgsRasterLayer
    if isinstance(layer, str):
        return layer
    elif isinstance(layer, QgsRasterLayer):
        return layer.dataProvider().dataSourceUri()
    else:
        return layer
    
class SafeFeedback:
    """Wrapper pour feedback afin d'éviter les erreurs si feedback=None"""
    def __init__(self, fb=None):
        self.fb = fb

    def pushInfo(self, msg):
        if self.fb:
            self.fb.pushInfo(str(msg))
        else:
            print("[INFO]", msg)

    def reportError(self, msg):
        if self.fb and hasattr(self.fb, "reportError"):
            self.fb.reportError(str(msg))
        else:
            print("[ERROR]", msg)

# ═══════════════════════════════════════════════════════════════════════
#   VISUALISATIONS MNT — rvt.vis en priorité, fallback GDAL/processing
# ═══════════════════════════════════════════════════════════════════════

def _rvt_available():
    """True si le package rvt-py est importable."""
    try:
        import rvt.vis
        return True
    except ImportError:
        return False


def _read_dem_as_array(dem_layer):
    """Lit un QgsRasterLayer → (arr_2d, res_x, res_y, no_data) via GDAL."""
    from osgeo import gdal
    import numpy as np
    src = dem_layer.dataProvider().dataSourceUri()
    ds = gdal.Open(src, gdal.GA_ReadOnly)
    if ds is None:
        raise IOError(f"GDAL ne peut pas ouvrir : {src}")
    band = ds.GetRasterBand(1)
    arr  = band.ReadAsArray().astype(float)
    nd   = band.GetNoDataValue()
    gt   = ds.GetGeoTransform()
    rx, ry = abs(gt[1]), abs(gt[5])
    ds = None
    if nd is not None:
        import numpy as np
        arr[arr == nd] = float('nan')
    return arr, rx, ry, nd


def _save_array_as_geotiff(arr, dem_layer, out_path, nodata_val=None):
    """Sauvegarde numpy 2D en GeoTIFF calqué sur le DEM source."""
    from osgeo import gdal
    import numpy as np
    src = dem_layer.dataProvider().dataSourceUri()
    src_ds = gdal.Open(src, gdal.GA_ReadOnly)
    rows, cols = arr.shape
    drv = gdal.GetDriverByName("GTiff")
    out_ds = drv.Create(out_path, cols, rows, 1, gdal.GDT_Float32,
                        options=["COMPRESS=LZW", "TILED=YES"])
    out_ds.SetGeoTransform(src_ds.GetGeoTransform())
    out_ds.SetProjection(src_ds.GetProjection())
    nd_val = float(nodata_val) if nodata_val is not None else -9999.0
    b = out_ds.GetRasterBand(1)
    b.SetNoDataValue(nd_val)
    b.WriteArray(np.where(np.isnan(arr), nd_val, arr).astype(np.float32))
    b.FlushCache()
    out_ds = None
    src_ds = None
    return out_path



def _src_name(dem_layer):
    """Retourne un nom de fichier sûr basé sur le dataSourceUri du DEM."""
    import unicodedata, re
    raw = os.path.splitext(
        os.path.basename(dem_layer.dataProvider().dataSourceUri()))[0]
    # Normaliser accents → ASCII
    raw = unicodedata.normalize('NFKD', raw).encode('ascii', 'ignore').decode('ascii')
    # Remplacer tout caractère non alphanumérique par underscore
    safe = re.sub(r'[^A-Za-z0-9\-]', '_', raw)
    # Réduire les underscores consécutifs
    safe = re.sub(r'_+', '_', safe).strip('_')
    return safe or "dem"


def _layer_name_from_path(out_path):
    """Extrait un nom d'affichage propre depuis un chemin de fichier."""
    return os.path.splitext(os.path.basename(out_path))[0]


def _add_to_mnt_group(path, name, dem_crs, add_to_project=True):
    """Charge un GeoTIFF dans QGIS sous le groupe 'Traitement MNT'.
    'name' est utilisé comme nom d'affichage dans le panneau des couches."""
    if not path or not os.path.exists(path):
        return None
    rl = QgsRasterLayer(path, name, "gdal")
    if not rl.isValid():
        return None
    rl.setCrs(dem_crs)
    QgsProject.instance().addMapLayer(rl, False)
    if add_to_project:
        root = QgsProject.instance().layerTreeRoot()
        grp  = root.findGroup("Traitement MNT") or root.addGroup("Traitement MNT")
        grp.addLayer(rl)
    return rl


# ── Hillshade ────────────────────────────────────────────────────────
def hillshade(dem_layer, out_path=None, zfactor=1.0, azimuth=315.0, altitude=35.0,
              context=None, feedback=None, addProject=True):
    """Ombrage solaire simple. Priorité : rvt.vis → GDAL."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return None

    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    out_path = out_path or os.path.join(tempfile.gettempdir(), f"hs_{name}.tif")

    if _rvt_available():
        try:
            import rvt.vis
            arr, rx, ry, nd = _read_dem_as_array(dem_layer)
            result = rvt.vis.hillshade(dem=arr, resolution_x=rx, resolution_y=ry,
                sun_azimuth=float(azimuth), sun_elevation=float(altitude),
                ve_factor=float(zfactor), no_data=nd)
            _save_array_as_geotiff(result, dem_layer, out_path)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            fb.pushInfo(f"Hillshade RVT → {out_path}")
            return out_path
        except Exception as e:
            fb.reportError(f"rvt.vis.hillshade : {e} — fallback GDAL")

    alg = _choose_alg(["gdal:hillshade"])
    if alg:
        try:
            processing.run(alg, {
                "INPUT": dem_layer.dataProvider().dataSourceUri(), "BAND": 1,
                "Z_FACTOR": float(zfactor), "AZIMUTH": float(azimuth),
                "ALTITUDE": float(altitude), "COMPUTE_EDGES": True,
                "OUTPUT": out_path}, context=context, feedback=feedback)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            return out_path
        except Exception as e:
            fb.reportError(f"GDAL hillshade : {e}")
    return None


# ── Hillshade multidirectionnel ──────────────────────────────────────
def multidirectional_hillshade(dem_layer, out_path=None, nr_directions=16,
                                sun_elevation=35, zfactor=1.0,
                                context=None, feedback=None, addProject=True):
    """Hillshade multidirectionnel (moyenne sur N directions). rvt.vis → GDAL."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return None

    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    out_path = out_path or os.path.join(tempfile.gettempdir(), f"mhs_{name}.tif")

    if _rvt_available():
        try:
            import rvt.vis, numpy as np
            arr, rx, ry, nd = _read_dem_as_array(dem_layer)
            mhs = rvt.vis.multi_hillshade(dem=arr, resolution_x=rx, resolution_y=ry,
                nr_directions=int(nr_directions), sun_elevation=float(sun_elevation),
                ve_factor=float(zfactor), no_data=nd)
            mean = np.nanmean(mhs, axis=0) if mhs.ndim == 3 else mhs
            _save_array_as_geotiff(mean, dem_layer, out_path)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            fb.pushInfo(f"Multi-hillshade RVT ({nr_directions} dir.) → {out_path}")
            return out_path
        except Exception as e:
            fb.reportError(f"rvt.vis.multi_hillshade : {e} — fallback GDAL")

    alg = _choose_alg(["gdal:hillshade"])
    if alg:
        try:
            processing.run(alg, {
                "INPUT": dem_layer.dataProvider().dataSourceUri(), "BAND": 1,
                "Z_FACTOR": float(zfactor), "COMPUTE_EDGES": True,
                "MULTIDIRECTIONAL": True, "OUTPUT": out_path},
                context=context, feedback=feedback)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            return out_path
        except Exception as e:
            fb.reportError(f"GDAL multi-hillshade : {e}")
    return None


# ── Pente ────────────────────────────────────────────────────────────
def slope(dem_layer, out_path=None, zfactor=1.0, output_units="degree",
          context=None, feedback=None, addProject=True):
    """Pente. Priorité : rvt.vis → GDAL."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return None

    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    out_path = out_path or os.path.join(tempfile.gettempdir(), f"slope_{name}.tif")
    units    = output_units if output_units in ("degree", "percent", "radian") else "degree"

    if _rvt_available():
        try:
            import rvt.vis
            arr, rx, ry, nd = _read_dem_as_array(dem_layer)
            d = rvt.vis.slope_aspect(dem=arr, resolution_x=rx, resolution_y=ry,
                output_units=units, ve_factor=float(zfactor), no_data=nd)
            _save_array_as_geotiff(d["slope"], dem_layer, out_path)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            fb.pushInfo(f"Pente RVT ({units}) → {out_path}")
            return out_path
        except Exception as e:
            fb.reportError(f"rvt.vis.slope_aspect : {e} — fallback GDAL")

    alg = _choose_alg(["gdal:slope"])
    if alg:
        try:
            processing.run(alg, {
                "INPUT": dem_layer.dataProvider().dataSourceUri(), "BAND": 1,
                "SCALE": float(zfactor), "AS_PERCENT": (units == "percent"),
                "COMPUTE_EDGES": True, "OUTPUT": out_path},
                context=context, feedback=feedback)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            return out_path
        except Exception as e:
            fb.reportError(f"GDAL slope : {e}")
    return None


# ── Sky-View Factor + Openness ───────────────────────────────────────
def sky_view_factor(dem_layer, out_path=None, svf_n_dir=16, svf_r_max=10,
                    zfactor=1.0, compute_svf=True, compute_opns=True,
                    compute_asvf=False, context=None, feedback=None, addProject=True):
    """SVF + Openness positive via rvt.vis. Nécessite rvt-py."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return {}
    if not _rvt_available():
        fb.reportError("rvt-py non installé (pip install rvt-py)."); return {}

    import rvt.vis
    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    base_dir = out_path if (out_path and os.path.isdir(out_path)) else (
               os.path.dirname(out_path) if out_path else tempfile.gettempdir())

    try:
        arr, rx, ry, nd = _read_dem_as_array(dem_layer)
        res = (rx + ry) / 2.0
        d = rvt.vis.sky_view_factor(dem=arr, resolution=res,
            compute_svf=compute_svf, compute_opns=compute_opns,
            compute_asvf=compute_asvf, svf_n_dir=int(svf_n_dir),
            svf_r_max=int(svf_r_max), ve_factor=float(zfactor), no_data=nd)
        results = {}
        if compute_svf and d.get("svf") is not None:
            p = os.path.join(base_dir, f"SVF_{name}.tif")
            _save_array_as_geotiff(d["svf"], dem_layer, p)
            _add_to_mnt_group(p, _layer_name_from_path(p), dem_crs, addProject)
            results["svf"] = p
        if compute_opns and d.get("opns") is not None:
            p = os.path.join(base_dir, f"OpenPos_{name}.tif")
            _save_array_as_geotiff(d["opns"], dem_layer, p)
            _add_to_mnt_group(p, _layer_name_from_path(p), dem_crs, addProject)
            results["opns"] = p
        if compute_asvf and d.get("asvf") is not None:
            p = os.path.join(base_dir, f"ASVF_{name}.tif")
            _save_array_as_geotiff(d["asvf"], dem_layer, p)
            _add_to_mnt_group(p, _layer_name_from_path(p), dem_crs, addProject)
            results["asvf"] = p
        return results
    except Exception as e:
        fb.reportError(f"SVF : {e}"); return {}


# ── Ouverture négative ───────────────────────────────────────────────
def openness_negative(dem_layer, out_path=None, svf_n_dir=16, svf_r_max=10,
                       zfactor=1.0, context=None, feedback=None, addProject=True):
    """Ouverture négative (DEM inversé) via rvt.vis."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return None
    if not _rvt_available():
        fb.reportError("rvt-py non installé."); return None

    import rvt.vis
    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    out_path = out_path or os.path.join(tempfile.gettempdir(), f"OpenNeg_{name}.tif")

    try:
        arr, rx, ry, nd = _read_dem_as_array(dem_layer)
        d = rvt.vis.sky_view_factor(dem=-arr, resolution=(rx+ry)/2.0,
            compute_svf=False, compute_opns=True,
            svf_n_dir=int(svf_n_dir), svf_r_max=int(svf_r_max),
            ve_factor=float(zfactor), no_data=nd)
        if d.get("opns") is None:
            fb.reportError("Ouverture négative : résultat vide."); return None
        _save_array_as_geotiff(d["opns"], dem_layer, out_path)
        _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
        return out_path
    except Exception as e:
        fb.reportError(f"Ouverture négative : {e}"); return None


# ── SLRM ─────────────────────────────────────────────────────────────
def slrm(dem_layer, out_path=None, radius_cell=20, zfactor=1.0,
         context=None, feedback=None, addProject=True):
    """Simple Local Relief Model via rvt.vis.slrm."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return None
    if not _rvt_available():
        fb.reportError("rvt-py non installé."); return None

    import rvt.vis
    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    out_path = out_path or os.path.join(tempfile.gettempdir(), f"SLRM_{name}.tif")

    try:
        arr, rx, ry, nd = _read_dem_as_array(dem_layer)
        result = rvt.vis.slrm(dem=arr, radius_cell=int(radius_cell),
                               ve_factor=float(zfactor), no_data=nd)
        _save_array_as_geotiff(result, dem_layer, out_path)
        _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
        return out_path
    except Exception as e:
        fb.reportError(f"SLRM : {e}"); return None


# ── VAT ──────────────────────────────────────────────────────────────
def VAT(dem_layer, out_path=None, context=None, type_terrain=0,
        vat_window=5, zfactor=1.0, feedback=None, addProject=True):
    """VAT via rvt.vis (SVF 50% + hillshade 25% + pente 25%).
    Fallback automatique vers le plugin QGIS rvt:rvt_blender si rvt-py absent."""
    fb = SafeFeedback(feedback)
    if not dem_layer or not dem_layer.isValid():
        fb.reportError("MNT invalide."); return None

    dem_crs  = dem_layer.crs()
    name     = _src_name(dem_layer)
    out_path = out_path or os.path.join(tempfile.gettempdir(), f"VAT_{name}.tif")

    # ── Priorité 1 : rvt.vis (calcul numpy pur, aucun fichier intermédiaire) ──
    if _rvt_available():
        try:
            import rvt.vis, numpy as np
            arr, rx, ry, nd = _read_dem_as_array(dem_layer)
            res = (rx + ry) / 2.0

            # SVF
            d_svf = rvt.vis.sky_view_factor(dem=arr, resolution=res,
                compute_svf=True, compute_opns=False, compute_asvf=False,
                svf_n_dir=16, svf_r_max=10, ve_factor=float(zfactor), no_data=nd)
            svf_arr = d_svf.get("svf")

            # Hillshade
            hs_arr = rvt.vis.hillshade(dem=arr, resolution_x=rx, resolution_y=ry,
                sun_azimuth=315, sun_elevation=35,
                ve_factor=float(zfactor), no_data=nd)

            # Pente
            d_slp = rvt.vis.slope_aspect(dem=arr, resolution_x=rx, resolution_y=ry,
                output_units="degree", ve_factor=float(zfactor), no_data=nd)
            slp_arr = d_slp.get("slope")

            if svf_arr is None or slp_arr is None:
                raise ValueError("SVF ou pente vides.")

            def _norm(a):
                mn, mx = np.nanmin(a), np.nanmax(a)
                return (a - mn) / (mx - mn + 1e-10) if mx > mn else np.zeros_like(a)

            vat = 0.50 * _norm(svf_arr) + 0.25 * _norm(hs_arr) + 0.25 * _norm(slp_arr)

            if vat_window and int(vat_window) > 1:
                try:
                    from scipy.ndimage import uniform_filter
                    vat = uniform_filter(vat, size=int(vat_window))
                except ImportError:
                    pass  # scipy absent : pas de lissage

            _save_array_as_geotiff(vat, dem_layer, out_path)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            fb.pushInfo(f"VAT RVT → {out_path}")
            return out_path

        except Exception as e:
            fb.reportError(f"rvt VAT : {e} — tentative plugin QGIS RVT")

    # ── Fallback : plugin QGIS rvt:rvt_blender ──────────────────────
    alg = _choose_alg(["rvt:rvt_blender"])
    if alg:
        try:
            processing.run(alg, {
                "INPUT": dem_layer.dataProvider().dataSourceUri(),
                "BLEND_COMBINATION": 0, "TERRAIN_TYPE": int(type_terrain),
                "SAVE_AS_8BIT": False, "OUTPUT": out_path},
                context=context, feedback=feedback)
            _add_to_mnt_group(out_path, _layer_name_from_path(out_path), dem_crs, addProject)
            return out_path
        except Exception as e:
            fb.reportError(f"Plugin RVT blender : {e}")

    fb.reportError("VAT impossible : rvt-py non installé et plugin QGIS RVT absent.")
    return None


# ---------- 4) PROSPECTION Auto ----------

"""
Collection de fonctions pour détecter des dolines (sinkholes) dans QGIS.
Usage:
- import find_dolines
- find_dolines.main_find_dolines(dem_layer, out_folder=None, params={})

Ce fichier contient des fonctions indépendantes pour chaque étape :
 1) comblement des sinks (SAGA XXL Wang & Liu)
 2) calcul du raster `sink = filled_dem - dem`
 3) vectorisation des zones de sink > seuil
 4) suppression des petites entités (option)
 5) clustering DBSCAN sur les centroïdes (optionnel)
 6) géométrie d'emprise minimale + suppression de la plus grande
 7) statistiques zonales (z_min, z_max, z_mean, z_median)
 8) centroids (barycentres) avec attributs

Remarques:
- Les sorties intermédiaires sont créées en mémoire (TEMPORARY_OUTPUT) sauf si out_folder est fourni.
- Le code utilise processing.run ; il doit être exécuté dans l'environnement QGIS (console Python ou plugin).
"""

from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry
import processing
import uuid


def _temp_path(name_prefix):
    return 'memory:' + name_prefix + '_' + str(uuid.uuid4())


def fill_sinks(dem_layer, minslope=0.1, filled_output=None):
    """Etape 1 : remplit les sinks avec SAGA (sagang:fillsinksxxlwangliu)
    dem_layer : QgsRasterLayer ou chemin
    minslope : float
    retourne : chemin/objet du raster rempli
    """
    if filled_output is None:
        filled_output = _temp_path('filled')
    params = {
        'ELEV': dem_layer,
        'FILLED': filled_output,
        'MINSLOPE': minslope,
    }
    res = processing.run('sagang:fillsinksxxlwangliu', params)
    return res['FILLED']


def compute_sink_raster(dem_layer, filled_dem, threshold=1.0, sink_output=None):
    """Etape 2 : sink = filled_dem - dem_layer (GDAL Raster calculator)
    Retourne un raster (path or memory id)
    """
    if sink_output is None:
        sink_output = 'TEMPORARY_OUTPUT'

    # gdal:rastercalculator requiert des noms de couche A,B,... on utilisera A-B

    # Valeur temporaire pour NoData
    sentinel = -9999.0

    # Étape 1 : calculer (A - B), mais remplacer les valeurs <= threshold par sentinel
    expr = f"(A - B) - ((A - B) <= {threshold}) * ((A - B) - {float(sentinel)})"

    res = processing.run(
        "gdal:rastercalculator",
        {
            'INPUT_A': filled_dem,
            'BAND_A': 1,
            'INPUT_B': dem_layer,
            'BAND_B': 1,
            'FORMULA': expr,
            'NO_DATA': sentinel,
            'RTYPE': 5,  # Float32
            'OPTIONS': '',
            'OUTPUT': sink_output
        }
    )


    return res.get('OUTPUT') or res.get('RESULT')


def vectorize_sinks(sink_raster, vector_output=None):
    """Etape 3 : polygonize les pixels 
    Retourne une couche vectorielle (polygons)
    """
    if vector_output is None:
        vector_output = 'TEMPORARY_OUTPUT'
    # polygonize
    poly_params = {
        'INPUT_RASTER': sink_raster,
        'RASTER_BAND': 1,
        'FIELD_NAME': 'VALUE',
        'OUTPUT': vector_output
    }
    res = processing.run('native:pixelstopoints', poly_params)

    out_path = res.get('OUTPUT')
    return res['OUTPUT']


def dbscan_partition(point_layer, eps=1.0, min_size=5, field_name='CLUSTER_ID', vector_output=None):
    """Etape 5 : partitionnement DBSCAN sur une couche de points
    retourne la couche annotée avec field_name (et size field)
    """
    if vector_output is None:
        vector_output = 'TEMPORARY_OUTPUT'
    params = {
        'INPUT': point_layer,
        'EPS': eps,
        'MIN_SIZE': min_size,
        'FIELD_NAME': field_name,
        'SIZE_FIELD_NAME': 'CLUSTER_SIZE',
        'OUTPUT': vector_output
    }
    res = processing.run('native:dbscanclustering', params)
    return res['OUTPUT']


def minimum_bounding_geometry(polygons_layer, field='CLUSTER_ID', keep_largest=False, vector_output=None):
    """Etape 6 : calcule l'emprise minimale pour chaque cluster et retire la plus grande (si demandé)
    Retourne la couche de polygones filtrée
    """
    if vector_output is None:
        vector_output = 'TEMPORARY_OUTPUT'
    res = processing.run('qgis:minimumboundinggeometry', {'INPUT': polygons_layer, 'FIELD': field, 'TYPE': 3, 'OUTPUT': vector_output})
    mbg = res['OUTPUT']

    if not keep_largest:
        vl = mbg
        if isinstance(mbg, str):
            vl = QgsVectorLayer(mbg, 'mbg', 'ogr')
        max_area = 0
        max_fid = None
        for feat in vl.getFeatures():
            a = feat.geometry().area()
            if a > max_area:
                max_area = a
                max_fid = feat.id()
        if max_fid is not None:
            expr = f"$id != {max_fid}"
            res2 = processing.run(
                'native:extractbyexpression',
                {'INPUT': vl, 'EXPRESSION': expr, 'OUTPUT': vector_output}
            )
            return res2['OUTPUT']
        return vl
    return mbg


def zonal_statistics(polygons_layer, dem_layer, stats_prefix='dz_', stats=[2,3,5,6], vector_output=None):
    """Etape 7 : calcule des statistiques zonales (z_min, z_max, z_mean, z_median)
    Ajoute les champs sur la couche polygons_layer et retourne la couche.
    """
    if vector_output is None:
        vector_output = 'TEMPORARY_OUTPUT'
    params = {
        'INPUT': polygons_layer,
        'INPUT_RASTER': dem_layer,
        'COLUMN_PREFIX': stats_prefix,
        'STATISTICS':stats,
        'OUTPUT': vector_output
    }

    res = processing.run('native:zonalstatisticsfb', params)

    return res.get('OUTPUT', polygons_layer)


def extract_centroids_with_stats(polygons_layer, vector_output=None):
    """Etape 8 : créé la couche de centroïdes et copie les champs statistiques
    Retourne la couche point (centroides) avec les attributs présents dans polygons_layer
    """
    if vector_output is None:
        vector_output = 'TEMPORARY_OUTPUT'
    cents = processing.run('native:centroids', {'INPUT': polygons_layer, 'ALL_PARTS': False, 'OUTPUT': vector_output})
    return cents['OUTPUT']


def cleanup_layers(layers_list):
    """Supprime les couches temporaires de la légende (si elles ont été ajoutées)
    layers_list: liste d'objets ou ids
    """
    proj = QgsProject.instance()
    for l in layers_list:
        try:
            if isinstance(l, str):
                # attempt to find layer by id or path
                layer = proj.mapLayersByName(l)
                if layer:
                    proj.removeMapLayer(layer[0])
            else:
                proj.removeMapLayer(l.id())
        except Exception:
            pass


