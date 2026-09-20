# Journal des versions

## 1.2

### Ajouté

- Onglet **📜 Topo ancienne** : numérisation d'une topographie papier (plan + coupe)
  en polygonale 3D — calage des scans, retracé de la polygonale, altitude de chaque
  station (jonction › cote du plan › coupe › interpolation à pente constante),
  sorties GPKG, CSV, Therion et métadonnées.
- Notice complète dans `docs/` : une fiche par outil, avec une partie usage et une
  partie méthode (formules, paramètres et algorithmes réellement utilisés), plus le
  guide détaillé des méthodes de calage `docs/Calage.md`.
- **Fournisseur Processing** « SpeleoTools » : épaisseur de roche, visualisations MNT,
  détection de dolines, profil développé et drapage d'une polyligne sur le MNT sont
  utilisables en traitement par lot, dans les modèles et avec `qgis_process`.
- Comparaison des stations reconstruites avec un levé de référence : écarts par
  station, statistiques (moyenne, max, RMS) et couche de vecteurs d'écart.
- Export Therion au choix en coordonnées cartésiennes ou en visées normales
  (longueur, azimut, pente ; azimuts rapportés au nord géographique).
- Choix du nord de la flèche (grille, géographique, magnétique) avec calcul
  automatique de la convergence des méridiens.
- Icône du plugin, `metadata.txt` complet (dépôt QGIS), `LICENSE`, ce journal.
- Tests : `tests/test_topo_ancienne_core.py` (hors QGIS) et
  `tests/run_qgis_integration.py` (bout en bout dans QGIS).

### Corrigé

- **Épaisseur de roche** : le MNT était échantillonné en supposant la couche cavité
  dans le SCR du projet ; les points sont désormais reprojetés depuis le SCR de la
  couche, et la reprojection est signalée dans le journal.
- Le dédoublonnage des sommets se fait bien sur une grille de 10 cm (elle était de
  1 cm) et dans le SCR du MNT : en coordonnées géographiques, l'arrondi confondait
  des points distants de plusieurs kilomètres.
- Les signaux du projet sont débranchés et la fenêtre détruite au déchargement du
  plugin : plus de dialogue fantôme après un rechargement.
- Onglet Profils : le champ « Espacement » était superposé à la case
  « Utiliser la sélection » dans la grille du formulaire.
- Suppression de 330 lignes de code mort dupliqué en fin de `speleo_tools.py`.

### Changé

- **geopandas et pandas ne sont plus nécessaires** : l'import Therion utilise les
  algorithmes natifs de QGIS. Seul numpy reste requis ; rvt-py, scipy et matplotlib
  sont optionnels.
- La détection de dolines cherche l'algorithme de comblement disponible (SAGA ou
  GRASS) et affiche un message explicite s'il manque.
- Code portable Qt5/Qt6 : plus d'import direct de `PyQt5`, types de champs via
  `speleo_compat` (`QMetaType` sur QGIS ≥ 3.38, `QVariant` avant).

## 1.1

- Import Therion, profils projeté et développé, détection de dolines,
  visualisations MNT (RVT), épaisseur de roche.
