# -*- coding: utf-8 -*-
"""
SpeleoTools — fournisseur Processing.

Expose les traitements du plugin dans la boîte à outils QGIS : ils deviennent
utilisables en traitement par lot, dans les modèles graphiques, depuis la
console et en ligne de commande (qgis_process), et s'exécutent en tâche de
fond avec une barre de progression et un bouton Annuler.
"""

import os

from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsApplication, QgsProcessingProvider, QgsProcessingAlgorithm,
    QgsProcessingException, QgsProcessingParameterRasterLayer,
    QgsProcessingParameterVectorLayer, QgsProcessingParameterFeatureSource,
    QgsProcessingParameterFeatureSink, QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean, QgsProcessingParameterEnum,
    QgsProcessingParameterFolderDestination, QgsProcessingParameterFileDestination,
    QgsProcessing, QgsFields, QgsFeature, QgsGeometry, QgsPoint, QgsPointXY,
    QgsWkbTypes, QgsCoordinateReferenceSystem,
)

from . import speleo_utils as su
from .speleo_compat import TYPE_INT, TYPE_DOUBLE, field as _field

PLUGIN_DIR = os.path.dirname(__file__)


def _icon():
    p = os.path.join(PLUGIN_DIR, "icon.png")
    return QIcon(p) if os.path.isfile(p) else QIcon()


# ═══════════════════════════════════════════════════════════════════════
#   1) Épaisseur de roche
# ═══════════════════════════════════════════════════════════════════════

class EpaisseurRocheAlgorithm(QgsProcessingAlgorithm):
    DEM = "DEM"
    CAVITE = "CAVITE"
    DEDUP = "DEDUP"
    OUTPUT = "OUTPUT"

    def name(self):
        return "epaisseurroche"

    def displayName(self):
        return "Épaisseur de roche"

    def group(self):
        return "Cavités"

    def groupId(self):
        return "cavites"

    def shortHelpString(self):
        return ("Différence entre l'altitude de surface (MNT) et l'altitude de la cavité "
                "pour chaque sommet de la couche d'entrée.\n\n"
                "La couche cavité peut être dans un autre SCR que le MNT : les points "
                "sont reprojetés avant échantillonnage. L'altitude de la cavité est lue "
                "dans la coordonnée Z des sommets, à défaut dans un champ "
                "elev / z / alt / altitude / depth.")

    def createInstance(self):
        return EpaisseurRocheAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "MNT (surface)"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.CAVITE, "Couche cavité (points ou lignes 3D)",
            [QgsProcessing.TypeVectorPoint, QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterBoolean(
            self.DEDUP, "Ignorer les sommets superposés (10 cm)", defaultValue=True))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Épaisseur", QgsProcessing.TypeVectorPoint))

    def processAlgorithm(self, parameters, context, feedback):
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        cave = self.parameterAsVectorLayer(parameters, self.CAVITE, context)
        dedup = self.parameterAsBool(parameters, self.DEDUP, context)
        if dem is None or cave is None:
            raise QgsProcessingException("MNT ou couche cavité invalide.")

        fields = QgsFields()
        for n in ("src_elev", "cave_elev", "thickness"):
            fields.append(_field(n, TYPE_DOUBLE))
        fields.append(_field("fid_src", TYPE_INT))

        sink, dest = self.parameterAsSink(
            parameters, self.OUTPUT, context, fields,
            QgsWkbTypes.Point, cave.crs() if cave.crs().isValid() else dem.crs())

        total = cave.featureCount() or 1
        n = 0
        for i, (pt, src_elev, cave_elev, thickness, fid) in enumerate(
                su.iter_thickness_points(dem, cave, dedup=dedup, feedback=feedback)):
            if feedback.isCanceled():
                break
            f = QgsFeature(fields)
            f.setGeometry(QgsGeometry.fromPointXY(pt))
            f.setAttributes([src_elev, cave_elev, thickness, fid])
            sink.addFeature(f)
            n += 1
            if i % 200 == 0:
                feedback.setProgress(min(99, 100.0 * fid / total))
        feedback.pushInfo("%d point(s) calculé(s)." % n)
        return {self.OUTPUT: dest}


# ═══════════════════════════════════════════════════════════════════════
#   2) Visualisations MNT
# ═══════════════════════════════════════════════════════════════════════

VISUS = [
    ("Ombrage (hillshade)", "hillshade"),
    ("Ombrage multidirectionnel", "multidh"),
    ("Pente", "slope"),
    ("Sky-View Factor", "svf"),
    ("Ouverture positive", "opns"),
    ("Ouverture négative", "opns_neg"),
    ("SLRM (relief local)", "slrm"),
    ("VAT (SVF + ombrage + pente)", "vat"),
]


class VisualisationsMNTAlgorithm(QgsProcessingAlgorithm):
    DEM = "DEM"
    VISUS = "VISUS"
    AZIMUT = "AZIMUT"
    ELEVATION = "ELEVATION"
    RAYON = "RAYON"
    DIRECTIONS = "DIRECTIONS"
    ZFACTOR = "ZFACTOR"
    DOSSIER = "DOSSIER"

    def name(self):
        return "visualisationsmnt"

    def displayName(self):
        return "Visualisations MNT (prospection)"

    def group(self):
        return "MNT"

    def groupId(self):
        return "mnt"

    def shortHelpString(self):
        return ("Produits dérivés du MNT pour la prospection karstique : ombrage, "
                "ombrage multidirectionnel, pente, Sky-View Factor, ouverture "
                "positive et négative, SLRM, VAT.\n\n"
                "Utilise rvt-py si le paquet est installé, sinon GDAL quand un "
                "équivalent existe. Les fichiers sont écrits dans le dossier choisi.")

    def createInstance(self):
        return VisualisationsMNTAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "MNT"))
        self.addParameter(QgsProcessingParameterEnum(
            self.VISUS, "Visualisations", options=[v[0] for v in VISUS],
            allowMultiple=True, defaultValue=[0, 7]))
        self.addParameter(QgsProcessingParameterNumber(
            self.AZIMUT, "Azimut du soleil (°)", QgsProcessingParameterNumber.Double,
            defaultValue=315.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.ELEVATION, "Élévation du soleil (°)", QgsProcessingParameterNumber.Double,
            defaultValue=35.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.RAYON, "Rayon SVF / ouverture (pixels)",
            QgsProcessingParameterNumber.Integer, defaultValue=10, minValue=1))
        self.addParameter(QgsProcessingParameterNumber(
            self.DIRECTIONS, "Nombre de directions",
            QgsProcessingParameterNumber.Integer, defaultValue=16, minValue=4))
        self.addParameter(QgsProcessingParameterNumber(
            self.ZFACTOR, "Facteur Z", QgsProcessingParameterNumber.Double,
            defaultValue=1.0))
        self.addParameter(QgsProcessingParameterFolderDestination(
            self.DOSSIER, "Dossier de sortie"))

    def processAlgorithm(self, parameters, context, feedback):
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        choix = self.parameterAsEnums(parameters, self.VISUS, context)
        out_dir = self.parameterAsString(parameters, self.DOSSIER, context)
        az = self.parameterAsDouble(parameters, self.AZIMUT, context)
        el = self.parameterAsDouble(parameters, self.ELEVATION, context)
        r = self.parameterAsInt(parameters, self.RAYON, context)
        nd = self.parameterAsInt(parameters, self.DIRECTIONS, context)
        zf = self.parameterAsDouble(parameters, self.ZFACTOR, context)
        if dem is None:
            raise QgsProcessingException("MNT invalide.")
        os.makedirs(out_dir, exist_ok=True)
        base = su._src_name(dem)

        def path(suffix):
            return os.path.join(out_dir, "%s_%s.tif" % (base, suffix))

        produced = []
        for i, idx in enumerate(choix):
            if feedback.isCanceled():
                break
            key = VISUS[idx][1]
            feedback.pushInfo("→ %s" % VISUS[idx][0])
            if key == "hillshade":
                produced.append(su.hillshade(dem, path("hillshade"), zf, az, el,
                                             feedback=feedback, addProject=False))
            elif key == "multidh":
                produced.append(su.multidirectional_hillshade(
                    dem, path("multidh"), nd, el, zf, feedback=feedback, addProject=False))
            elif key == "slope":
                produced.append(su.slope(dem, path("slope"), zf, feedback=feedback,
                                         addProject=False))
            elif key in ("svf", "opns"):
                res = su.sky_view_factor(dem, out_dir, nd, r, zf,
                                         compute_svf=(key == "svf"),
                                         compute_opns=(key == "opns"),
                                         feedback=feedback, addProject=False)
                produced += [v for v in res.values() if v]
            elif key == "opns_neg":
                produced.append(su.openness_negative(dem, path("opns_neg"), nd, r, zf,
                                                     feedback=feedback, addProject=False))
            elif key == "slrm":
                produced.append(su.slrm(dem, path("slrm"), radius_cell=20, zfactor=zf,
                                        feedback=feedback, addProject=False))
            elif key == "vat":
                produced.append(su.VAT(dem, path("vat"), zfactor=zf, feedback=feedback,
                                       addProject=False))
            feedback.setProgress(100.0 * (i + 1) / max(len(choix), 1))

        produced = [p for p in produced if p]
        if not produced:
            raise QgsProcessingException(
                "Aucune visualisation produite : installez rvt-py (pip install rvt-py) "
                "ou choisissez un produit disponible via GDAL (ombrage, pente).")
        for p in produced:
            feedback.pushInfo(p)
        return {self.DOSSIER: out_dir}


# ═══════════════════════════════════════════════════════════════════════
#   3) Détection de dolines
# ═══════════════════════════════════════════════════════════════════════

class DolinesAlgorithm(QgsProcessingAlgorithm):
    DEM = "DEM"
    MINSLOPE = "MINSLOPE"
    SEUIL = "SEUIL"
    EPS = "EPS"
    MINPTS = "MINPTS"
    POLYGONES = "POLYGONES"
    CENTROIDES = "CENTROIDES"

    def name(self):
        return "dolines"

    def displayName(self):
        return "Détection de dolines"

    def group(self):
        return "MNT"

    def groupId(self):
        return "mnt"

    def shortHelpString(self):
        return ("Détecte les dépressions fermées : comblement des cuvettes, "
                "différence avec le MNT, vectorisation au-delà du seuil, "
                "regroupement DBSCAN, emprises minimales et statistiques.\n\n"
                "Nécessite un algorithme de comblement : SAGA "
                "(sagang:fillsinksxxlwangliu) ou, à défaut, native:fillsinks / "
                "GRASS r.fill.dir.")

    def createInstance(self):
        return DolinesAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "MNT"))
        self.addParameter(QgsProcessingParameterNumber(
            self.MINSLOPE, "Pente minimale du comblement",
            QgsProcessingParameterNumber.Double, defaultValue=0.1))
        self.addParameter(QgsProcessingParameterNumber(
            self.SEUIL, "Profondeur minimale (m)",
            QgsProcessingParameterNumber.Double, defaultValue=1.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.EPS, "Distance de regroupement DBSCAN (m)",
            QgsProcessingParameterNumber.Double, defaultValue=5.0))
        self.addParameter(QgsProcessingParameterNumber(
            self.MINPTS, "Nombre minimal de pixels par doline",
            QgsProcessingParameterNumber.Integer, defaultValue=5, minValue=1))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.POLYGONES, "Dolines (emprises)", QgsProcessing.TypeVectorPolygon))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.CENTROIDES, "Dolines (centroïdes)", QgsProcessing.TypeVectorPoint,
            optional=True))

    def processAlgorithm(self, parameters, context, feedback):
        import processing
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        if dem is None:
            raise QgsProcessingException("MNT invalide.")
        alg = su.fill_sinks_algorithm()
        if alg is None:
            raise QgsProcessingException(su.FILL_SINKS_MISSING)
        feedback.pushInfo("Comblement des dépressions : %s" % alg)

        filled = su.fill_sinks(dem, self.parameterAsDouble(parameters, self.MINSLOPE, context))
        feedback.setProgress(25)
        sink_raster = su.compute_sink_raster(
            dem, filled, threshold=self.parameterAsDouble(parameters, self.SEUIL, context))
        feedback.setProgress(45)
        points = su.vectorize_sinks(sink_raster)
        feedback.setProgress(60)
        clustered = su.dbscan_partition(
            points, eps=self.parameterAsDouble(parameters, self.EPS, context),
            min_size=self.parameterAsInt(parameters, self.MINPTS, context))
        feedback.setProgress(75)
        mbg = su.minimum_bounding_geometry(clustered, field="CLUSTER_ID", keep_largest=False)
        stats = su.zonal_statistics(mbg, sink_raster, stats_prefix="Profondeur_")
        feedback.setProgress(90)

        poly_layer = su.as_layer(stats, "dolines")
        sink, dest = self.parameterAsSink(
            parameters, self.POLYGONES, context, poly_layer.fields(),
            QgsWkbTypes.Polygon, poly_layer.crs())
        for f in poly_layer.getFeatures():
            sink.addFeature(f)

        results = {self.POLYGONES: dest}
        if parameters.get(self.CENTROIDES) is not None:
            cents = su.as_layer(su.extract_centroids_with_stats(stats), "centroides")
            csink, cdest = self.parameterAsSink(
                parameters, self.CENTROIDES, context, cents.fields(),
                QgsWkbTypes.Point, cents.crs())
            for f in cents.getFeatures():
                csink.addFeature(f)
            results[self.CENTROIDES] = cdest
        feedback.setProgress(100)
        return results


# ═══════════════════════════════════════════════════════════════════════
#   4) Profil développé (CSV)
# ═══════════════════════════════════════════════════════════════════════

class ProfilDeveloppeAlgorithm(QgsProcessingAlgorithm):
    DEM = "DEM"
    LIGNE = "LIGNE"
    PAS = "PAS"
    INTERP = "INTERP"
    CSV = "CSV"

    def name(self):
        return "profildeveloppe"

    def displayName(self):
        return "Profil développé le long d'une polyligne"

    def group(self):
        return "MNT"

    def groupId(self):
        return "mnt"

    def shortHelpString(self):
        return ("Échantillonne le MNT le long d'une polyligne et écrit un CSV "
                "X = distance cumulée (m), Y = altitude (m).\n\n"
                "La polyligne est reprojetée dans le SCR du MNT si nécessaire.")

    def createInstance(self):
        return ProfilDeveloppeAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "MNT"))
        self.addParameter(QgsProcessingParameterFeatureSource(
            self.LIGNE, "Polyligne", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber(
            self.PAS, "Espacement des points (m)",
            QgsProcessingParameterNumber.Double, defaultValue=1.0, minValue=0.01))
        self.addParameter(QgsProcessingParameterBoolean(
            self.INTERP, "Interpoler les trous (NoData)", defaultValue=True))
        self.addParameter(QgsProcessingParameterFileDestination(
            self.CSV, "Profil (CSV)", fileFilter="CSV (*.csv)"))

    def processAlgorithm(self, parameters, context, feedback):
        import csv
        import math
        from qgis.core import QgsCoordinateTransform, QgsProject
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        source = self.parameterAsSource(parameters, self.LIGNE, context)
        pas = self.parameterAsDouble(parameters, self.PAS, context)
        interp = self.parameterAsBool(parameters, self.INTERP, context)
        out = self.parameterAsFileOutput(parameters, self.CSV, context)
        if dem is None or source is None:
            raise QgsProcessingException("MNT ou polyligne invalide.")

        xform = None
        if source.sourceCrs() != dem.crs():
            xform = QgsCoordinateTransform(source.sourceCrs(), dem.crs(),
                                           QgsProject.instance())
            feedback.pushInfo("Reprojection %s → %s" % (source.sourceCrs().authid(),
                                                        dem.crs().authid()))
        distances, elevations = [], []
        cum, prev = 0.0, None
        total = source.featureCount() or 1
        for i, feat in enumerate(source.getFeatures()):
            if feedback.isCanceled():
                break
            geom = QgsGeometry(feat.geometry())
            if geom.isEmpty():
                continue
            if xform:
                geom.transform(xform)
            parts = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for part in parts:
                for a, b in zip(part[:-1], part[1:]):
                    seg = math.hypot(b.x() - a.x(), b.y() - a.y())
                    n = max(1, int(seg / pas))
                    for k in range(n):
                        t = k / float(n)
                        p = QgsPointXY(a.x() + t * (b.x() - a.x()), a.y() + t * (b.y() - a.y()))
                        cum += 0.0 if prev is None else math.hypot(p.x() - prev.x(), p.y() - prev.y())
                        prev = p
                        z = su.sample_dem_at_point(dem, p)
                        distances.append(cum)
                        elevations.append(z)
                if part:
                    p = QgsPointXY(part[-1])
                    cum += 0.0 if prev is None else math.hypot(p.x() - prev.x(), p.y() - prev.y())
                    prev = p
                    distances.append(cum)
                    elevations.append(su.sample_dem_at_point(dem, p))
            feedback.setProgress(100.0 * (i + 1) / total)

        if not distances:
            raise QgsProcessingException("Aucun point échantillonné.")
        if interp:
            elevations = su.fill_gaps_linear(distances, elevations)
        valides = sum(1 for z in elevations if z is not None)
        feedback.pushInfo("%d points, %d valides." % (len(distances), valides))
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["X_distance_m", "Y_altitude_m"])
            for d, z in zip(distances, elevations):
                w.writerow([round(d, 3), "" if z is None else round(z, 3)])
        return {self.CSV: out}


# ═══════════════════════════════════════════════════════════════════════
#   5) Drapage d'une polyligne sur le MNT
# ═══════════════════════════════════════════════════════════════════════

class DrapageAlgorithm(QgsProcessingAlgorithm):
    DEM = "DEM"
    LIGNE = "LIGNE"
    PAS = "PAS"
    OUTPUT = "OUTPUT"

    def name(self):
        return "drapagemnt"

    def displayName(self):
        return "Draper une polyligne sur le MNT (3D)"

    def group(self):
        return "MNT"

    def groupId(self):
        return "mnt"

    def shortHelpString(self):
        return ("Densifie la polyligne et lui donne l'altitude du MNT : sortie "
                "LineStringZ, utilisable pour l'épaisseur de roche ou la 3D.\n\n"
                "Les tronçons sans donnée (NoData) sont coupés.")

    def createInstance(self):
        return DrapageAlgorithm()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterRasterLayer(self.DEM, "MNT"))
        self.addParameter(QgsProcessingParameterVectorLayer(
            self.LIGNE, "Polyligne", [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterNumber(
            self.PAS, "Espacement des points (m, 0 = sommets seuls)",
            QgsProcessingParameterNumber.Double, defaultValue=0.0, minValue=0.0))
        self.addParameter(QgsProcessingParameterFeatureSink(
            self.OUTPUT, "Polyligne 3D", QgsProcessing.TypeVectorLine))

    def processAlgorithm(self, parameters, context, feedback):
        dem = self.parameterAsRasterLayer(parameters, self.DEM, context)
        ligne = self.parameterAsVectorLayer(parameters, self.LIGNE, context)
        pas = self.parameterAsDouble(parameters, self.PAS, context)
        if dem is None or ligne is None:
            raise QgsProcessingException("MNT ou polyligne invalide.")
        tmp = su.create_profile_from_line(dem, ligne, spacing=pas or None,
                                          add_to_project=False)
        sink, dest = self.parameterAsSink(parameters, self.OUTPUT, context,
                                          tmp.fields(), QgsWkbTypes.LineStringZ,
                                          dem.crs())
        n = 0
        for f in tmp.getFeatures():
            sink.addFeature(f)
            n += 1
        feedback.pushInfo("%d tronçon(s) 3D." % n)
        return {self.OUTPUT: dest}


# ═══════════════════════════════════════════════════════════════════════
#   Fournisseur
# ═══════════════════════════════════════════════════════════════════════

class SpeleoToolsProvider(QgsProcessingProvider):

    def loadAlgorithms(self):
        for alg in (EpaisseurRocheAlgorithm(), VisualisationsMNTAlgorithm(),
                    DolinesAlgorithm(), ProfilDeveloppeAlgorithm(), DrapageAlgorithm()):
            self.addAlgorithm(alg)

    def id(self):
        return "speleotools"

    def name(self):
        return "SpeleoTools"

    def longName(self):
        return "SpeleoTools — outils spéléologiques"

    def icon(self):
        return _icon()
