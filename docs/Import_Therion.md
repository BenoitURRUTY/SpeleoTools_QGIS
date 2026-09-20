# Import des exports Therion

Transforme les shapefiles exportés par Therion en GeoPackages propres, stylés et
organisés dans le panneau des couches de QGIS.

Inspiré du script **pyThGIS** de Xavier Robert
(DOI : 10.5281/zenodo.15078040), réécrit ici avec les seuls outils de QGIS : depuis la
version 1.2, ni geopandas ni pandas ne sont nécessaires.

---

## Notice d'utilisation

### Préparer l'export dans Therion

Exporter la topographie en **Shapefile**, en 2D (plan) et en 3D (modèle), dans un
**même dossier**. Le plugin attend les noms de fichiers produits par Therion :

| Fichier | Rôle | Obligatoire |
| --- | --- | --- |
| `outline2d.shp` | contour de chaque scrap | oui |
| `lines2d.shp` | lignes du dessin (parois, écoulements, centerlines…) | oui |
| `areas2d.shp` | surfaces (eau, éboulis…) | non |
| `points2d.shp` | symboles ponctuels | non |
| `stations3d.shp` | stations du cheminement | non |
| `shots3d.shp` | visées | non |
| `walls3d.shp` | maillage des parois | non |

### Marche à suivre (onglet 🗺 Import Therion)

1. **Dossier SHP Therion** : le dossier d'export.
2. **Dossier sortie GPKG** : vide = sous-dossier `GPKG/` à côté de l'export.
3. **Styles** : les chemins vers les `.qml` fournis sont pré-remplis ; ils restent
   modifiables.
4. Options :
   - **Réparer les géométries** : passe chaque couche par `native:fixgeometries` ;
   - **Calculer altitude** : ajoute `_ALT`, `_EASTING`, `_NORTHING` aux points et aux
     stations ;
   - **Grouper les couches** : crée un groupe nommé, avec deux sous-groupes 2D et 3D.
5. **Importer les sorties Therion**.

### Ce qui sort

```
GPKG/
├── lines2dMasked.gpkg     # lignes découpées sur l'outline
├── areas2dMasked.gpkg     # aires découpées
├── points2dAlt.gpkg       # points + _ALT / _EASTING / _NORTHING
├── stations3dAlt.gpkg     # stations + mêmes champs
├── shots3d.gpkg           # visées
├── outline2d.gpkg         # contours
└── walls3d.shp (+ dbf, prj, shx)   # copié tel quel
```

Les couches sont chargées dans un groupe :

```
📁 Ma Grotte
  📁 2D    Points · Lignes · Aires · Outline
  📁 3D    Stations · Cheminements · Parois
```

L'ordre d'affichage est voulu : les points au-dessus, l'outline en fond.

---

## Méthode

Tout l'enchaînement est dans `run_therion_import()` (`speleo_tools.py`) et n'utilise
que des algorithmes natifs de QGIS, visibles dans la boîte à outils.

### 1. Lecture et réparation

Chaque shapefile est ouvert comme `QgsVectorLayer`. Si la réparation est demandée,
`native:fixgeometries` (méthode « structure ») produit une couche temporaire
corrigée : auto-intersections, anneaux mal orientés, doublons de sommets. Les exports
Therion en contiennent régulièrement, surtout sur les scraps complexes ; sans
réparation, les découpes échouent.

### 2. Découpe des lignes sur l'outline

C'est l'étape qui demande le plus d'explications, car elle applique une règle
métier de Therion.

**a) Ce qui ne doit jamais être découpé.** Une expression est construite d'après les
champs réellement présents dans la couche :

```
"_TYPE" IN ('centerline', 'water_flow', 'label')  OR  "_CLIP" = 'off'
```

Les centerlines traversent les scraps, les écoulements et les étiquettes aussi, et
`_CLIP = off` est la consigne explicite de Therion « ne pas rogner ». Ces entités sont
mises de côté intactes (`native:extractbyexpression`).

**b) Le reste est découpé.** `native:intersection` croise les lignes avec les
outlines, en préfixant `ol_` les champs venus de l'outline. Chaque morceau porte donc
à la fois son `_SCRAP_ID` d'origine et l'`ol__ID` du scrap qui l'a découpé.

**c) Filtre par scrap.** On ne garde que `"_SCRAP_ID" = "ol__ID"` : une paroi n'est
conservée que là où elle tombe dans **son propre** scrap, pas dans celui du voisin.
Sans ce filtre, les zones de recouvrement entre scraps produiraient des doublons.

**d) Nettoyage et fusion.** Les champs `ol_*` sont supprimés
(`native:deletecolumn`) pour retrouver le schéma d'origine, puis les deux jeux
(non découpé + découpé) sont réunis par `native:mergevectorlayers`.

Les aires suivent le même chemin, sans l'étape (a).

Si l'intersection échoue — géométries irréparables, champs absents — le journal le
dit et les entités brutes sont conservées : mieux vaut un dessin non rogné qu'un
dessin perdu.

### 3. Altitudes des points et des stations

`_therion_add_alt_fields()` recopie la couche en mémoire et ajoute trois champs
calculés depuis la **géométrie**, pas depuis un MNT :

- `_ALT` : la coordonnée Z du premier sommet, arrondie à l'entier et stockée en
  texte (le format attendu par les étiquettes Therion) ; vide si la géométrie n'est
  pas 3D ;
- `_EASTING`, `_NORTHING` : X et Y du même sommet.

Ces champs servent à étiqueter les stations et à les exploiter en tableur.

### 4. Conversion et copie

Chaque couche est écrite en GeoPackage (`QgsVectorFileWriter`, encodage UTF-8, un
fichier par couche pour rester lisible). `walls3d.shp` est **copié tel quel** avec ses
fichiers annexes : ce maillage 3D (multipatch) ne se convertit pas proprement en
GeoPackage.

### 5. Chargement et styles

Les couches sont ajoutées au projet, éventuellement dans un groupe, et reçoivent leur
style QML (`loadNamedStyle`). Comme QGIS insère chaque nouvelle couche **en haut** du
groupe, l'ajout se fait dans l'ordre inverse de l'affichage souhaité : outline,
aires, lignes, points.

### Limites

- les noms de fichiers sont ceux de Therion : un export renommé n'est pas reconnu ;
- `outline2d.shp` et `lines2d.shp` sont obligatoires ; leur absence arrête l'import ;
- la découpe suppose la présence de `_SCRAP_ID` et `_ID` ; sans eux, les lignes sont
  seulement intersectées avec l'ensemble des outlines, sans filtre par scrap ;
- l'import ne recalcule rien : il met en forme. La géométrie reste celle que Therion
  a calculée, avec ses bouclages déjà compensés.
