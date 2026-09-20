# SpeleoTools — Plugin QGIS pour la Spéléologie

Plugin QGIS complet pour l'analyse, la visualisation et la cartographie de données spéléologiques. SpeleoTools intègre des outils avancés pour l'import de données Therion, l'analyse de MNT, le calcul d'épaisseur de roche et la détection de dolines.

---

## 📋 Table des matières

- [Description](#description)
- [Fonctionnalités](#fonctionnalités)
- [Prérequis](#prérequis)
- [Installation](#installation)
  - [Méthode 1 : Installation manuelle](#méthode-1--installation-manuelle)
- [Utilisation](#utilisation)
  - [Onglet 1 : Import Therion](#onglet-1--import-therion)
  - [Onglet 2 : Épaisseur de roche](#onglet-2--épaisseur-de-roche)
  - [Onglet 3 : Profils topographiques](#onglet-3--profils-topographiques)
  - [Onglet 4 : Analyse MNT et Dolines](#onglet-4--analyse-mnt-et-dolines)
  - [Onglet 6 : Topo ancienne](#onglet-6--topo-ancienne)
- [Structure du projet](#structure-du-projet)
- [Auteur](#auteur)
- [Licence](#licence)
- [Contributions](#contributions)

---

## 📖 Notice

La documentation complète est dans [`docs/`](docs/) : une fiche par outil, chacune avec
une **notice d'utilisation** et une partie **méthode** qui détaille le calcul réellement
effectué (formules, paramètres, algorithmes appelés).

- [Notice générale](docs/Notice.md) — installation, conventions, où est le code
- [Import Therion](docs/Import_Therion.md) · [Épaisseur de roche](docs/Epaisseur_roche.md) · [Profils](docs/Profils.md)
- [Visualisations MNT](docs/Visualisations_MNT.md) · [Dolines](docs/Dolines.md)
- [Topo ancienne](docs/Topo_ancienne.md) et son [guide de calage](docs/Calage.md)
- [Boîte à outils Processing](docs/Processing.md)

---

## Description

**SpeleoTools** est un plugin QGIS conçu pour faciliter le travail des spéléologues, topographes de cavités et géologues. Il automatise de nombreuses tâches d'analyse spatiale liées à l'exploration souterraine.

### Pourquoi SpeleoTools ?

- ✅ **Import Therion facilité** : conversion automatique SHP → GPKG avec styles
- ✅ **Calculs 3D avancés** : épaisseur de roche, profils topographiques
- ✅ **Analyse MNT** : hillshade, SVF, VAT pour la prospection
- ✅ **Détection de dolines** : identification automatique des dépressions
- ✅ **Topographies anciennes** : calage plan + coupe, retracé de la polygonale, reconstruction 3D

---

## Fonctionnalités

### 🗺️ Import Therion
basé sur le script développé par Xavier Robert : https://github.com/robertxa/pyThGIS

- Import des exports Therion (Shapefile) → GeoPackage
- Conversion automatique des couches 2D et 3D :
  - **2D** : points, lignes, aires, outline
  - **3D** : stations, cheminements (shots), parois (walls)
- Application de styles prédéfinis (QML)
- Organisation en groupes hiérarchiques (2D / 3D)
- Réparation automatique des géométries invalides
- Calcul d'altitude depuis MNT pour points et stations

### 📏 Épaisseur de roche

- Calcul automatique de l'épaisseur de roche au-dessus d'une cavité
- Échantillonnage du MNT pour chaque point/sommet
- Export GeoPackage avec attributs :
  - `src_elev` : altitude de surface (MNT)
  - `cave_elev` : altitude de la cavité
  - `thickness` : épaisseur calculée (m)
  - `fid_src` : identifiant source

### 📊 Profils topographiques

Deux modes de génération de profils altimétriques. Dans les deux cas : X = distance le long du profil (m), Y = altitude extraite du MNT (m). Les couches vecteur d'entrée sont automatiquement reprojetées dans le CRS du MNT.

#### Mode 1 — Profil projeté

Coupe verticale selon un angle de projection α défini dans Therion.

**Paramètres :**
- **MNT** : raster d'élévation source
- **Couche d'emprise** : polygone ou ligne définissant la zone de la coupe — la ligne de coupe passe par le **barycentre réel** des géométries
- **Angle α** : lu automatiquement depuis un fichier `.thconfig` (`-projection [elevation XX]`) ou saisi manuellement
- **Marge emprise (%)** : agrandit la zone de découpe du MNT autour de l'emprise
- **Décalages X/Y** : shift des coordonnées pour définir une origine personnalisée

**Principe géométrique :**
- La ligne de coupe est tracée à **α + 90°** (perpendiculaire à la direction de projection Therion)
- Elle passe par le barycentre des géométries de la couche d'emprise
- Sa longueur couvre la diagonale complète de l'emprise agrandie de la marge

**Options de sortie :**
- ☑ **Sauvegarder la ligne de coupe** : exporte la ligne en GPKG et la charge dans QGIS pour vérification visuelle

**Sorties :**
```
profil_projete_aXXdeg_NomMNT.csv       # X=distance, Y=altitude
profil_projete_aXXdeg_NomMNT.gpkg      # Points profil sans CRS (coordonnées profil)
profil_projete_aXXdeg_NomMNT.png       # Graphique (si matplotlib installé)
ligne_coupe_aXXdeg_NomMNT_ligne.gpkg   # Ligne de coupe géoréférencée (optionnel)
```

#### Mode 2 — Profil développé

Profil altimétrique développé le long d'une polyligne existante.

**Paramètres :**
- **MNT** : raster d'élévation source
- **Couche polyligne** : tracé du profil (cheminement, coupe manuelle…)
- **☑ Utiliser uniquement la sélection active** : si coché, seules les entités sélectionnées dans la couche sont utilisées. Si aucune sélection active, toutes les entités sont utilisées
- **Espacement points (m)** : pas d'échantillonnage le long de la ligne
- **☑ Interpoler les valeurs NoData** : comble les trous par interpolation linéaire
- **Distance max interpolation** : limite la longueur des gaps comblés
- **Décalages X/Y** : shift des coordonnées

**Sorties :**
```
profil_dev[_sel]_NomLigne_NomMNT.csv     # X=distance cumulée, Y=altitude
profil_dev[_sel]_NomLigne_NomMNT.gpkg    # Points profil sans CRS
profil_dev[_sel]_NomLigne_NomMNT.png     # Graphique (si matplotlib installé)
```
> Le suffixe `_sel` est ajouté quand la sélection est utilisée.

**Format GPKG profil (commun aux deux modes) :**

Les GPKG de profil sont exportés **sans CRS** car leurs coordonnées sont des coordonnées de profil (X = distance, Y = altitude) et non des coordonnées géographiques. Ils sont destinés à être utilisés dans un logiciel de dessin ou de mise en page pour superposer la topographie souterraine.

Attributs : `X_dist_m`, `Y_alt_m`, `pt_index`

### 🏔️ Analyse MNT

**Produits dérivés pour la prospection spéléologique :**

- **Hillshade** : ombrage du relief (azimut et angle configurables)
- **SVF (Sky View Factor)** : facteur de visibilité du ciel
- **VAT (Variance Angular Threshold)** : variance angulaire micro-relief

### 🕳️ Détection de dolines (Onglet 4)

- Analyse automatique des dépressions fermées
- Calcul morphométrique complet :
  - Profondeur (m)
  - Surface (m²)
  - Périmètre (m)
  - Circularité (0-1)
  - Pente moyenne (°)
- Filtrage par seuils configurables
- Export vectoriel (polygones + points centraux)

### 📜 Numérisation de topographies anciennes (Onglet 6)

Les outils existants qui reconstruisent une polygonale 3D à partir d'un plan et d'une coupe (MapToDat, Topo Calc'R) laissent le calage altimétrique manuel, station par station. Cet onglet combine les deux vues automatiquement et garde la trace de l'origine de chaque altitude (voir *Synthèse topographique de grands réseaux karstiques : méthodologie et retour d'expérience du Clot d'Aspres*).

- Calage du scan du **plan** : déjà géoréférencé, 2 points connus, ou méthode « historique » (entrée + barre d'échelle + flèche nord)
- La flèche nord peut indiquer le nord de la grille, le nord géographique ou le nord magnétique : le plugin calcule la convergence des méridiens et applique la déclinaison de l'époque
- Calage du scan de la **coupe** (développée ou projetée) : barre d'échelle (redresse un scan penché, ou graduation verticale si la coupe est exagérée) + point de référence (X, Z)
- Les images sources ne sont jamais modifiées : le calage produit des VRT
- Retracé de la polygonale en polyligne sur le plan et sur la coupe (un sommet = une station, une polyligne par branche)
- Altitude de chaque station, par ordre de priorité : **jonction** > **cote lue sur le plan** > **coupe** > **interpolation à pente constante** (ou extrapolation avec la pente du dernier tronçon connu)
- Rattachement à une station existante (clic sur une couche de stations, ex. import Therion : X, Y, Z et `nom@survey`)
- Jonctions automatiques : une station non nommée posée sur une station déjà calculée est fusionnée avec elle
- Contrôle visuel sur la coupe : verticale de chaque station du plan et position 3D obtenue
- Traçabilité : chaque station garde la source de son altitude et l'écart cote plan − coupe ; fichier de métadonnées (documents sources, date, auteurs, paramètres de calage), repris en tête du `.th`
- Sorties : stations 3D, visées 3D, polygonale 3D (GPKG), CSV des visées, centerline Therion (`.th`) en coordonnées cartésiennes ou en visées normales (longueur, azimut, pente)
- Contrôle : comparaison des stations reconstruites avec un levé de référence (écarts par station, statistiques, couche de vecteurs d'écart)

---

## Prérequis

### Logiciels

- **QGIS 3.10+** ([télécharger](https://qgis.org/)) — rien d'autre n'est indispensable :
  l'import Therion n'utilise plus geopandas ni pandas, seulement QGIS et GDAL.

### Selon les fonctions utilisées

| Complément | Nécessaire pour | Sans lui |
| --- | --- | --- |
| [rvt-py](https://pypi.org/project/rvt-py/) (`pip install rvt-py`) | SVF, ouverture, SLRM, VAT | Ombrage et pente restent disponibles via GDAL |
| [SAGA](https://www.sigterritoires.fr/index.php/comment-integrer-saga-a-qgis-a-partir-de-la-version-3-30/) ou GRASS | Détection de dolines (comblement des dépressions) | Message explicite, le reste fonctionne |
| scipy | Lissage du VAT | VAT non lissé |
| matplotlib | Graphiques PNG des profils | CSV et GPKG produits quand même |

Le plugin vérifie ces compléments au démarrage et propose de les installer ; tout est
optionnel sauf numpy, fourni avec QGIS.

---

## Boîte à outils Processing

Les traitements sont aussi publiés comme algorithmes QGIS, dans le groupe
**SpeleoTools** de la boîte à outils. Ils s'utilisent alors en traitement par lot,
dans les modèles graphiques, depuis la console ou avec `qgis_process`, et
s'exécutent en tâche de fond (barre de progression et bouton Annuler) :

| Algorithme | Identifiant |
| --- | --- |
| Épaisseur de roche | `speleotools:epaisseurroche` |
| Visualisations MNT (prospection) | `speleotools:visualisationsmnt` |
| Détection de dolines | `speleotools:dolines` |
| Profil développé le long d'une polyligne | `speleotools:profildeveloppe` |
| Draper une polyligne sur le MNT (3D) | `speleotools:drapagemnt` |

```python
processing.run("speleotools:epaisseurroche",
               {"DEM": mnt, "CAVITE": cavite, "DEDUP": True,
                "OUTPUT": "TEMPORARY_OUTPUT"})
```

---

## Installation

### Méthode 1 : Installation manuelle

**1. Télécharger le plugin**

Téléchargez le ZIP et décompressez-le.

**2. Activer le plugin dans QGIS**

- Ouvrez QGIS
- `Extensions` → `Installer/Gérer les extensions`
- Onglet `Installer une extension à partir d'un zip`

---

### Import Therion

Convertit les exports Therion (Shapefile) en GeoPackage avec styles.

#### Prérequis

Exporter votre topographie depuis Therion en format **Shapefile** 2D (plan) et 3D (model) dans un même et unique dossier.

#### Utilisation

**1. Chemins des données**

- **Dossier SHP Therion** : chemin vers le dossier contenant les `.shp`
- **Dossier sortie GPKG** : où sauvegarder les GeoPackage

**2. Styles (optionnel)**

Le plugin pré-remplit automatiquement les chemins vers les fichiers `.qml` du dossier `styles_therion/`.

Vous pouvez personnaliser chaque style :
- Aires 2D
- Lignes 2D
- Points 2D
- Outline 2D
- Cheminements 3D
- Stations 3D
- Parois 3D

**3. Options**

- ☑ **Réparer les géométries** : corrige automatiquement les géométries invalides
- ☑ **Calculer altitude depuis MNT** : ajoute l'altitude Z aux points/stations
- ☑ **Grouper les couches** : organise en groupes 2D/3D (nom personnalisable)

**4. Lancer l'import**

Cliquez sur **"Importer Therion"**

Le plugin :
1. ✅ Lit les fichiers SHP
2. ✅ Répare les géométries si demandé
3. ✅ Fusionne les lignes/aires par type
4. ✅ Calcule les altitudes depuis le MNT
5. ✅ Convertit en GPKG
6. ✅ Applique les styles
7. ✅ Ajoute les couches à QGIS

**Résultat :**

```
Outputs/
├── areas2dMasked.gpkg     # Aires 2D découpées sur l'outline
├── lines2dMasked.gpkg     # Lignes 2D découpées sur l'outline
├── points2dAlt.gpkg       # Points 2D avec altitude
├── outline2d.gpkg         # Contour 2D
├── shots3d.gpkg           # Cheminements 3D
├── stations3dAlt.gpkg     # Stations 3D avec altitude
└── walls3d.shp            # Parois 3D (maillage — pas de conversion GPKG)
```

Les couches sont organisées dans un groupe QGIS :

```
📁 Ma Grotte
  📁 2D
    • Points 2D
    • Lignes 2D
    • Aires 2D
    • Outline 2D
  📁 3D
    • Stations 3D
    • Cheminements 3D
    • Parois 3D
```

---

### Onglet 2 : Épaisseur de roche

Calcule l'épaisseur de roche au-dessus d'une cavité.

#### Utilisation

**1. Sélectionner les couches**

- **MNT (DEM)** : modèle numérique de terrain (surface)
- **Couche cavité** : géométrie 3D de la cavité (points, lignes)

**2. Fichier de sortie (optionnel)**

- Chemin du GeoPackage de sortie
- Si vide : couche mémoire temporaire

**3. Nom de la couche**

Nom de la couche de sortie (défaut : "Thickness")

**4. Lancer le calcul**

Cliquez sur **"Calculer épaisseur"**

**Résultat :**

Une couche de points avec :
- `src_elev` : altitude de surface (m)
- `cave_elev` : altitude de la cavité (m)
- `thickness` : épaisseur de roche (m)
- `fid_src` : ID de l'entité source

---

### Onglet 3 : Profils topographiques

Voir la section [Profils topographiques](#-profils-topographiques) dans les fonctionnalités pour le détail complet des paramètres et sorties.

**Dossier de sortie commun** : sélectionnez un dossier via le bouton 📂. Si laissé vide, les fichiers sont écrits dans le dossier temporaire système.

---

### Analyse MNT (Prospection)

Génère des produits dérivés pour faciliter la détection d'indices karstiques.

**1. Sélectionner le MNT**

**2. Dossier de sortie**

Où sauvegarder les rasters générés.

**3. Choisir les analyses**

- ☑ **Hillshade** : ombrage du relief
  - Azimut : 315° (NW)
  - Altitude : 45°

- ☑ **SVF (Sky View Factor)** : visibilité du ciel (détecte dolines)
  - Directions : 16
  - Rayon : 10 pixels

- ☑ **VAT (Variance Angular Threshold)** : variance micro-relief
  - Lissage : 5

- ☑ **Hillshade + VAT** : combinaison optimale

**4. Lancer l'analyse**

Cliquez sur **"Analyser MNT"**

**Résultat :**

```
Outputs/
├── NomMNT_hillshade.tif
├── NomMNT_svf.tif
├── NomMNT_vat.tif
└── NomMNT_multidh.tif
```

**Utilisation :**

- **SVF** : zones sombres = dépressions potentielles (dolines)
- **VAT** : variations micro-topographiques
- **Hillshade + VAT** : meilleur contraste pour prospection

### Détection de dolines

Identifie automatiquement les dépressions fermées.

**1. Sélectionner le MNT**

**2. Dossier de sortie**

**3. Paramètres de détection**

- **Profondeur min** : 2m (défaut)
- **Surface min** : 100m² (défaut)
- **Circularité min** : 0.3 (défaut, 0=linéaire, 1=cercle)

**4. Lancer la détection**

Cliquez sur **"Détecter dolines"**

**Algorithme :**

1. Remplissage des dépressions (`Fill Sinks`)
2. Soustraction : MNT rempli - MNT original = profondeur
3. Vectorisation des dépressions
4. Calcul des attributs morphométriques
5. Filtrage par seuils

**Résultat :**

- `dolines_polygones.gpkg` : contours des dolines
- `dolines_points.gpkg` : points centraux

**Attributs :**

- `profondeur` : profondeur max (m)
- `surface` : aire (m²)
- `perimetre` : périmètre (m)
- `circularite` : 4π × surface / périmètre² (0-1)
- `pente_moy` : pente moyenne (°)

**Symbologie automatique :**

- Taille proportionnelle à la profondeur
- Couleur selon la circularité

---

### Onglet 6 : Topo ancienne

Reconstruit une polygonale 3D à partir du plan et de la coupe scannés d'une topographie ancienne.

**0. Cavité** — nom (fichiers, groupes QGIS, survey Therion), date et auteurs du levé d'origine (`date` / `team` Therion), références des documents numérisés, dossier de sortie (par défaut `SpeleoTools_<nom>/` à côté du scan du plan). Ces informations sont conservées dans les métadonnées : les documents d'origine en sont souvent dépourvus.

**① Plan**

1. Choisir le scan puis **Charger** : un scan non géoréférencé s'affiche en coordonnées image.
2. Choisir la méthode de calage :
   - **Déjà géoréférencé** : rien à faire (le scan est chargé tel quel).
   - **2 points connus** : cliquer chaque point sur le scan (🎯) et saisir ses coordonnées.
   - **Entrée + échelle + nord** : cliquer l'entrée, les 2 extrémités de la barre d'échelle, puis la base et la pointe de la flèche nord. Saisir X/Y de l'entrée et la longueur de la barre, puis indiquer **ce que représente la flèche** et cliquer **🧭 Calculer** :

     | La flèche indique | Azimut appliqué |
     | --- | --- |
     | le nord de la grille | `0` |
     | le nord géographique | `−γ` |
     | le nord magnétique | `D − γ` |

     γ est la convergence des méridiens, calculée par le plugin à la position de l'entrée (quel que soit le SCR) ; `D` est la déclinaison à la date du levé, à saisir — le [calculateur du NCEI](https://www.ngdc.noaa.gov/geomag/calculators/magcalc.shtml) couvre 1590-2029.
3. **Station de rattachement** : nom donné à la 1re station du tracé. **📍 Station existante** : cliquer sur un point d'une couche de stations (ex. `Stations 3D` de l'import Therion) récupère X, Y, Z et le nom (`nom@survey`). Dans ce cas, le `.th` n'écrit pas de `fix` : la reconstruction se raccorde à la cavité existante.
4. **Caler le plan** → `plan_<nom>_cale.vrt` (échelle et rotation dans le journal).

Clic droit pendant une saisie : annuler.

**② Coupe**

1. Charger le scan de la coupe (affiché à gauche du plan tant qu'il n'est pas calé).
2. Type : **développée** (abscisse = longueur horizontale cumulée) ou **projetée** (azimut α, même convention que Therion `-projection [elevation α]`, axe horizontal orienté à α + 90°).
3. Cliquer la barre d'échelle (si elle est horizontale, elle sert aussi à redresser le scan ; décocher la case pour utiliser une graduation verticale d'altitudes, indispensable si la coupe a une exagération verticale), puis le point de référence et saisir son X et son Z (l'altitude de l'entrée, en général ; ce champ suit l'altitude de l'entrée tant qu'on ne le modifie pas).
4. **Caler la coupe** : la coupe calée s'affiche **sous le plan** (environ 10 km plus bas) : `X affiché = X + X entrée`, `Y affiché = Z + Y entrée − 10 000`. Les boutons 🔍 Plan / 🔍 Coupe passent de l'un à l'autre.

**③ Tracé**

1. **Tracer sur le plan** : l'outil d'ajout de ligne de QGIS s'active dans `<nom>_numerisation.gpkg|trace_plan`. Un clic par station, clic droit pour finir une branche. Le champ `branche` s'incrémente tout seul.
2. **Tracer sur la coupe** : même chose, en suivant les **mêmes numéros de branche**.
3. **Terminer le tracé** : enregistre et génère `stations_plan` / `stations_coupe` (un point par sommet).
4. **Tables des stations** : renseigner
   - `nom` : un nom identique sur le plan et sur la coupe **apparie** les deux stations. C'est indispensable en haut et en bas des puits, car en plan les deux sont presque au même endroit.
   - `z_plan` : les cotes d'altitude écrites sur le plan.

   Si un tracé est modifié, **Mettre à jour les stations** conserve les noms et les cotes déjà saisis.

📖 **[docs/Calage.md](docs/Calage.md)** détaille chaque méthode de calage : ce qu'elle exige du document, les budgets d'erreur (pointé, longueur de la flèche, orientation), le choix du nord, les coupes sans barre d'échelle ou avec exagération verticale, et les contrôles à faire après calage.

**⑤ Contrôle**

Choisir une couche de stations d'un levé fiable et cliquer **📏 Comparer les stations
reconstruites** : les stations de même nom sont appariées, et le plugin produit les
écarts par station (`<nom>_ecarts_reference.csv`), une couche de vecteurs d'écart et,
dans le journal, la moyenne, le maximum et le RMS en plan comme en altitude. C'est la
figure de contrôle d'une reconstruction.

**④ Calcul**

Pour chaque branche (dans l'ordre des numéros) :

1. **Appariement** plan ↔ coupe par noms. S'il n'y a aucun nom commun et que le nombre de sommets est le même, l'appariement se fait par ordre. Sinon, seules les deux entrées sont appariées.
2. **Abscisse** de chaque station sur la coupe :
   - coupe développée : longueur cumulée, recalée par morceaux entre stations appariées ;
   - coupe projetée : projection sur l'axe de coupe, ajustée par moindres carrés sur les stations appariées. Un coefficient négatif ou une échelle incohérente est signalé dans le journal.
3. **Lecture de Z sur la ligne de coupe**, entre les deux stations appariées qui encadrent la station. Pour lever l'ambiguïté des verticales, on prend la position dont l'avancement le long du tracé est le plus proche de celui du plan.
4. **Jonctions** : une station sans nom située à moins de la tolérance « Jonction auto » (10 cm par défaut) d'une station déjà calculée prend son nom et son altitude. L'accrochage (snapping) de QGIS pendant le tracé rend ces jonctions exactes.
5. **Fusion des sources** : jonction (station du même nom déjà calculée dans une branche précédente) > `z_plan` > coupe.
6. Stations restées **sans altitude** : interpolation linéaire en fonction de la distance horizontale (pente constante) entre les stations connues voisines. Au-delà de la dernière station connue, extrapolation avec la pente du dernier tronçon connu.

**Sorties :**

```
SpeleoTools_<nom>/
├── <nom>_numerisation.gpkg   # trace_plan, trace_coupe, stations_plan, stations_coupe
├── plan_<scan>_cale.vrt      # plan calé
├── coupe_<scan>_calee.vrt    # coupe calée (repère X/Z décalé)
├── <nom>_topo3d.gpkg         # stations_3d (PointZ), visees_3d, polygonale_3d (LineStringZ)
├── <nom>_visees_3d.csv       # de ; vers ; longueur ; azimut ; pente ; z ; sources
├── <nom>_ancienne.th         # centerline Therion (métadonnées, date, team, data cartesian, fix)
└── <nom>_metadonnees.txt     # documents, date, auteurs, calages, origine des altitudes
```

Si l'option est cochée, le groupe **contrôle coupe** superpose à la coupe calée la verticale de chaque station du plan et le point 3D obtenu, coloré selon sa source. On voit ainsi immédiatement si la reconstruction suit le dessin d'origine.

`stations_3d` contient `source_z` (plan / jonction / coupe / interp / extrap / defaut), `z_plan`, `z_coupe` et `dz_plan_coupe`. La symbologie colore les stations selon la source de leur altitude. Les couches 3D peuvent être passées directement à l'onglet **Épaisseur de roche**.

---

## Structure du projet

```
SpeleoTools/
│
├── __init__.py                  # Point d'entrée du plugin
├── speleo_tools.py              # Classe principale et interface
├── speleo_utils.py              # Fonctions utilitaires
├── speleo_dialog.ui             # Interface Qt Designer
├── install_dependencies.py      # Gestionnaire de dépendances
├── docs/                        # Notice : une fiche par outil (usage + méthode)
│   ├── Notice.md                # Sommaire, installation, conventions
│   ├── Import_Therion.md
│   ├── Epaisseur_roche.md
│   ├── Profils.md
│   ├── Visualisations_MNT.md
│   ├── Dolines.md
│   ├── Topo_ancienne.md
│   ├── Calage.md                # Méthodes de calage plan / coupe en détail
│   └── Processing.md
│
├── speleo_compat.py             # Compatibilité QGIS 3/4 (QVariant ↔ QMetaType)
├── speleo_provider.py           # Algorithmes Processing
├── topo_ancienne_core.py        # Topo ancienne : calculs (sans QGIS, testable)
├── topo_ancienne_tab.py         # Topo ancienne : logique de l'onglet
│
├── tests/
│   ├── test_topo_ancienne_core.py   # pytest (hors QGIS)
│   ├── run_qgis_integration.py      # topo ancienne, de bout en bout dans QGIS
│   └── run_qgis_plugin_tests.py     # épaisseur, profils, Therion, Processing
│
├── CHANGELOG.md                 # Journal des versions
├── LICENSE                      # CC BY-NC-SA 4.0
│
├── metadata.txt                 # Métadonnées QGIS
├── icon.png                     # Icône du plugin
│
├── styles_therion/              # Styles QML Therion
│   ├── Style_Area2D.qml
│   ├── Style_Ligne2D.qml
│   ├── Style_Point2D.qml
│   ├── Style_Outline2D.qml
│   ├── Style_Shots3D.qml
│   ├── Style_Stations3D.qml
│   └── Style_Wall3D.qml
│
└── README.md                    # Ce fichier
```

---

## Auteur

**Benoît Urruty**

- Scripts Python pour QGIS
- Interface graphique Qt
- Algorithmes d'analyse MNT et karstologie
- Intégration Therion

---

## Licence

### Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)

Ce projet est sous licence **CC BY-NC-SA 4.0**.

![CC BY-NC-SA 4.0](https://licensebuttons.net/l/by-nc-sa/4.0/88x31.png)

#### Vous êtes autorisé à :

- **Partager** — copier, distribuer et communiquer le matériel par tous moyens et sous tous formats
- **Adapter** — remixer, transformer et créer à partir du matériel

#### Selon les conditions suivantes :

- **Attribution** — Vous devez créditer l'œuvre, intégrer un lien vers la licence et indiquer si des modifications ont été effectuées.
- **Pas d'Utilisation Commerciale** — Vous n'êtes pas autorisé à faire un usage commercial de cette œuvre.
- **Partage dans les Mêmes Conditions** — Toute œuvre dérivée doit être diffusée sous la même licence.

#### Texte complet de la licence :
[https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.fr](https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.fr)

#### Résumé de la licence :
[https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.fr)

---

## Source

Robert X. (2025), pyThGIS, a Python code to clean the shp Therion output. DOI:10.5281/zenodo.15078040

---

## Contributions

Les contributions sont les bienvenues !

**Types de contributions :**

- 🐛 Rapporter des bugs
- 💡 Suggérer des fonctionnalités
- 📝 Améliorer la documentation
- 🔧 Corriger des bugs
- ✨ Ajouter des fonctionnalités

---

**Bonne cartographie ! 🗺️🔦**
