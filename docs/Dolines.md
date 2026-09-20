# Détection de dolines

Repère automatiquement les **dépressions fermées** d'un MNT et les restitue sous forme
de polygones et de points, avec leur profondeur.

---

## Notice d'utilisation

### Ce qu'il faut

- un MNT haute résolution (1 m ou mieux) ;
- un algorithme de comblement des dépressions : **SAGA** ou **GRASS**, activé dans
  `Traitement → Options → Fournisseurs`. Sans lui, le plugin l'annonce clairement et
  s'arrête ; tout le reste continue de fonctionner.

### Marche à suivre (onglet 🕳 Dolines)

1. **MNT** et **dossier de sortie** (vide = couches temporaires en mémoire).
2. **Sauvegarder les fichiers intermédiaires** : écrit le MNT comblé, le raster de
   profondeur, les points et les clusters — utile pour comprendre un résultat douteux.
3. Paramètres :
   - **Pente minimale du comblement** (0,1) : pente imposée aux surfaces comblées ;
   - **Profondeur minimale** (1 m) : seuil au-dessous duquel une cuvette est ignorée ;
   - **Distance de regroupement DBSCAN** (5 m) : distance maximale entre deux pixels
     d'une même doline ;
   - **Nombre minimal de pixels** (5) : taille minimale d'un groupe.
4. **Détecter dolines**.

### Ce qui sort

Un GeoPackage `dolines.gpkg` à deux couches (ou des couches mémoire) :

- `dolines_polygons` : emprise de chaque doline ;
- `dolines_centroids` : son centre.

Les attributs `Profondeur_*` viennent des statistiques zonales calculées sur le raster
de profondeur : moyenne, médiane, minimum et maximum. Le **maximum** est la profondeur
utile : c'est l'écart le plus grand entre le terrain et la surface de comblement.

### Régler les paramètres

- **Profondeur minimale** : 1 m garde beaucoup de bruit sur un MNT sous forêt ; 2 m
  donne une liste plus courte et plus sûre. Commencer haut, puis descendre.
- **Distance de regroupement** : au moins deux fois la taille du pixel. Trop grande,
  elle fusionne des dolines voisines en un seul objet.
- **Nombre minimal de pixels** : filtre principal contre le bruit ; sur un MNT à 1 m,
  5 pixels valent 5 m² de fond de cuvette.

---

## Méthode

La chaîne complète est dans `speleo_utils.py` (section « PROSPECTION Auto ») et
enchaîne des algorithmes standards de QGIS. Aucune étape n'est cachée : chaque
résultat intermédiaire peut être écrit sur le disque avec l'option prévue.

### 1. Comblement des dépressions

`fill_sinks()` cherche le premier algorithme disponible parmi
`sagang:fillsinksxxlwangliu`, ses variantes SAGA, puis `grass7:r.fill.dir`. SAGA
applique la méthode de **Wang & Liu** : la surface est remplie jusqu'à ce que toute
cellule ait un exutoire, avec une pente minimale imposée pour éviter les plateaux
parfaitement plats.

Le MNT comblé est donc le terrain « sans cuvettes » : une doline y devient un lac
plein, arasé au niveau de son déversoir.

### 2. Raster de profondeur

`compute_sink_raster()` calcule `comblé − original` avec `gdal:rastercalculator`, en
une seule expression :

```
(A − B) − ((A − B) <= seuil) × ((A − B) − (−9999))
```

Le terme entre parenthèses vaut 1 là où la différence est inférieure ou égale au
seuil ; ces pixels prennent alors la valeur sentinelle −9999, déclarée comme NoData.
Il ne reste donc, dans le raster produit, que les pixels **plus profonds que le
seuil**, avec leur profondeur en mètres.

### 3. Vectorisation

`vectorize_sinks()` appelle `native:pixelstopoints` : **un point par pixel** conservé,
portant sa profondeur dans le champ `VALUE`. Les NoData sont ignorés. C'est une
transformation exacte, sans simplification de contour.

### 4. Regroupement DBSCAN

`dbscan_partition()` applique `native:dbscanclustering` aux points : deux points
distants de moins de `EPS` appartiennent au même groupe, et un groupe doit contenir au
moins `MIN_SIZE` points. Les points isolés — le bruit du MNT, les pixels épars — ne
reçoivent aucun identifiant de cluster et sont écartés de la suite.

C'est ici que se joue l'essentiel du filtrage : DBSCAN ne suppose ni forme, ni nombre
de dolines.

### 5. Emprise de chaque groupe

`minimum_bounding_geometry()` appelle `qgis:minimumboundinggeometry` avec
`TYPE = 3`, soit l'**enveloppe convexe** de chaque cluster. L'emprise est donc
convexe : une doline en haricot est représentée par une forme un peu plus large que sa
véritable limite, et la surface lue sur le polygone est légèrement surestimée.

**Attention à une heuristique** : quand `keep_largest` vaut `False` — le cas par
défaut dans l'onglet — la fonction supprime le polygone de **plus grande surface**.
L'idée est d'éliminer l'amas qui couvre toute la dalle (fond de vallée, replat
mal comblé) et qui n'est pas une doline. Mais si votre zone contient une très grande
dépression légitime et rien d'autre d'aussi étendu, c'est elle qui disparaît. En cas
de doute, activer les fichiers intermédiaires et regarder la couche `clustered` avant
ce filtre, ou utiliser l'algorithme Processing, qui expose les mêmes étapes.

### 6. Statistiques et centroïdes

`zonal_statistics()` lance `native:zonalstatisticsfb` sur le **raster de profondeur**
avec les statistiques 2, 3, 5 et 6, c'est-à-dire moyenne, médiane, minimum et maximum,
préfixées `Profondeur_`. `extract_centroids_with_stats()` ajoute la couche de
centroïdes (`native:centroids`), qui hérite des mêmes attributs.

Les valeurs sont donc des **profondeurs relatives au comblement**, pas des altitudes.

### Ce que la méthode ne fait pas

- elle ne distingue pas une doline d'une mare artificielle, d'une excavation, d'une
  fosse d'extraction ou d'un artefact de MNT : le tri reste géologique, donc humain ;
- les dépressions ouvertes vers l'aval (vallées sèches, ouvalas partiellement
  drainés) ne sont pas détectées, par construction : elles ne sont pas fermées ;
- la circularité et la pente moyenne annoncées dans d'anciennes versions du README ne
  sont pas calculées par le code actuel ; les attributs réellement produits sont les
  quatre statistiques de profondeur. Elles se recalculent facilement dans QGIS à
  partir de la géométrie (`$area`, `$perimeter`, `4·π·$area/$perimeter^2`).

### Contrôles

- superposer les polygones au SVF ou à l'ouverture négative : une vraie doline y est
  nette ;
- vérifier la cohérence de `Profondeur_max` avec ce que montre le profil du terrain ;
- sur une zone connue, compter les dolines trouvées et les dolines réelles : c'est le
  seul moyen de régler les seuils pour votre MNT et votre karst.
