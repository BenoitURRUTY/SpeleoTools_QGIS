# Topo ancienne — du plan et de la coupe à la polygonale 3D

Reconstruit une polygonale tridimensionnelle à partir des seuls documents graphiques
d'une topographie ancienne : un plan et une coupe scannés.

Les outils existants qui font cela (MapToDat, Topo Calc'R) laissent le calage
altimétrique manuel, station par station. Ici, la coupe est retracée une fois, et
l'altitude de chaque station en est déduite automatiquement, avec la trace de son
origine.

Le **calage des scans** a son propre guide, plus détaillé : [Calage.md](Calage.md).
La présente fiche décrit l'enchaînement complet et la méthode de reconstruction.

---

## Notice d'utilisation

### Cavité

- **Nom** : sert à nommer les fichiers, les groupes de couches et le survey Therion.
- **Date** et **auteurs du levé d'origine**, **documents sources** : métadonnées,
  écrites dans un fichier à part et en tête du `.th`. Les topographies anciennes en
  manquent presque toujours ; c'est l'occasion de ne pas reproduire le problème.
- **Dossier de sortie** : par défaut `SpeleoTools_<nom>/` à côté du scan du plan.

### ① Plan

Charger le scan, choisir la méthode de calage (déjà géoréférencé, deux points connus,
ou entrée + barre d'échelle + flèche nord), indiquer le type de nord et caler.
Le **rattachement** permet de partir d'une station existante : un clic sur une couche
de points récupère X, Y, Z et le nom `station@survey`.

Tous les détails, les budgets d'erreur et le choix du nord : [Calage.md](Calage.md).

### ② Coupe

Charger le scan, choisir **développée** ou **projetée** (azimut α), cliquer la barre
d'échelle puis le point de référence, et caler. La coupe calée s'affiche sous le
plan ; les boutons 🔍 passent de l'une à l'autre.

### ③ Tracé

1. **Tracer sur le plan** : l'outil de ligne de QGIS s'active sur la couche
   `trace_plan`. Un clic par station, clic droit pour finir une branche. Le champ
   `branche` s'incrémente automatiquement.
2. **Tracer sur la coupe** : même chose, avec les **mêmes numéros de branche**.
3. **Terminer le tracé** : enregistre et génère les couches de stations.
4. **Tables des stations** : renseigner
   - `nom` : un nom identique sur le plan et sur la coupe apparie les deux stations —
     indispensable en haut et en bas des puits ;
   - `z_plan` : les cotes d'altitude écrites sur le plan.
5. Après modification d'un tracé, **Mettre à jour les stations** conserve les noms et
   les cotes déjà saisis.

### ④ Calcul

Régler la tolérance d'abscisse, la distance de jonction automatique, le style du
fichier Therion, puis **Calculer la polygonale 3D**.

### ⑤ Contrôle

Choisir une couche de stations d'un levé fiable et **Comparer** : écarts par station,
statistiques, couche de vecteurs d'écart.

### Ce qui sort

```
SpeleoTools_<nom>/
├── <nom>_numerisation.gpkg   # trace_plan, trace_coupe, stations_plan, stations_coupe
├── plan_<scan>_cale.vrt      # plan calé (l'image source n'est pas modifiée)
├── coupe_<scan>_calee.vrt    # coupe calée
├── <nom>_topo3d.gpkg         # stations_3d, visees_3d, polygonale_3d
├── <nom>_visees_3d.csv       # de ; vers ; longueur ; azimut ; pente ; z ; sources
├── <nom>_ancienne.th         # centerline Therion
├── <nom>_metadonnees.txt     # documents, date, auteurs, calages, origine des altitudes
└── <nom>_ecarts_reference.csv  # après une comparaison
```

Dans `stations_3d`, le champ `source_z` dit d'où vient chaque altitude, et la
symbologie colore les stations en conséquence.

---

## Méthode

Les calculs sont dans `topo_ancienne_core.py`, volontairement séparé de QGIS pour
être testable seul ; `topo_ancienne_tab.py` s'occupe des couches et des clics.

### 1. Repères et calage

Le plan est calé par une **similitude** (échelle, rotation, translation) écrite dans
un VRT ; la coupe l'est dans un repère (X = abscisse horizontale, Z = altitude),
affiché décalé de 10 km sous le plan pour cohabiter dans le même canevas. Le détail —
formules, méthodes, erreurs — est dans [Calage.md](Calage.md).

### 2. Lecture des tracés

Chaque polyligne est lue branche par branche (`_ta_line_vertices()`), ses sommets
concaténés dans l'ordre du tracé. Les stations générées reprennent ce même ordre
(`branche`, `ordre`), ce qui permet de retrouver les noms et les cotes saisis après
une modification du tracé : la correspondance se fait d'abord par **position**
(tolérance de 1 % de la longueur moyenne des tronçons, au moins 5 cm), puis par
`branche`/`ordre`, avec priorité à la même branche pour ne pas confondre deux
stations superposées à une jonction.

### 3. Appariement plan ↔ coupe

`find_anchors()` construit la liste des couples (station du plan, sommet de la coupe) :

1. **par nom** : tout nom non vide présent des deux côtés ;
2. sinon, **par ordre** si l'option est cochée et que les deux tracés ont le même
   nombre de sommets ;
3. sinon, un seul couple : premier sommet du plan ↔ premier sommet de la coupe.

Les couples dont l'ordre est incohérent (un ancrage plus loin sur le plan mais plus
tôt sur la coupe) sont écartés, avec un avertissement : ils casseraient la logique
d'avancement commune aux deux dessins.

### 4. Abscisse de chaque station

Chaque station du plan reçoit une abscisse « brute » :

- **coupe développée** : la distance horizontale cumulée depuis le début de la
  branche ;
- **coupe projetée** : la projection sur l'axe de coupe, orienté à α + 90°, soit
  `s = (x − x₀)·sin(α+90°) + (y − y₀)·cos(α+90°)`, éventuellement inversée si la case
  est cochée.

Cette abscisse est ensuite transposée dans le repère de la coupe :

- en **développée**, par une fonction affine par morceaux entre les ancrages triés
  (au-delà du dernier ancrage, prolongement de pente 1) : cela absorbe un dessin dont
  l'échelle horizontale n'est pas exactement celle du plan ;
- en **projetée**, par un **ajustement linéaire aux moindres carrés** `X = a·s + b` sur
  les ancrages. Le journal affiche `a` : négatif, il signale une coupe vue de l'autre
  côté ; loin de ±1, un problème d'échelle ou d'azimut de projection.

### 5. Lecture de l'altitude sur la coupe

Pour une station non appariée, `_search_on_section()` cherche, **entre les deux
ancrages qui l'encadrent**, un point de la polyligne de coupe dont l'abscisse vaut la
valeur cible, tolérance comprise. Restreindre la recherche à cet intervalle évite de
sauter dans une partie du dessin qui correspond à une autre galerie.

Plusieurs candidats sont possibles — une coupe repasse souvent à la même abscisse. Le
choix se fait sur **l'avancement relatif** : la fraction de chemin parcourue le long
de la coupe entre les deux ancrages est comparée à la fraction parcourue sur le plan,
et le candidat le plus proche l'emporte. Les segments verticaux (puits) sont traités
comme des candidats continus : n'importe quel point du segment convient
géométriquement, on retient celui dont l'avancement colle le mieux.

C'est la limite connue de la méthode : en plan, le haut et le bas d'un puits sont
presque au même endroit, donc l'avancement ne les distingue pas. D'où la consigne de
**nommer ces deux stations** sur les deux dessins.

### 6. Fusion des sources d'altitude

Pour chaque station, dans l'ordre :

1. **jonction** — une station de même nom déjà calculée dans une branche précédente,
   ou située à moins de la tolérance de jonction automatique (10 cm par défaut) d'une
   station déjà placée ;
2. **plan** — la cote `z_plan` écrite sur le document ;
3. **coupe** — la valeur lue au point trouvé à l'étape 5.

Quand une station a les deux dernières, l'écart est conservé dans `dz_plan_coupe` et
le journal en donne la moyenne et le maximum : c'est une mesure directe de la
cohérence interne du document.

### 7. Interpolation à pente constante

Les stations sans altitude sont comblées en fonction de la **distance horizontale
cumulée** :

- entre deux stations connues, interpolation linéaire — la galerie est supposée de
  pente constante entre elles ;
- au-delà de la dernière station connue, prolongement avec la **pente du dernier
  tronçon connu** ; s'il n'y en a qu'une, l'altitude est reportée telle quelle.

Ces stations sont marquées `interp` ou `extrap`, jamais confondues avec une lecture.

### 8. Visées et export

`shot_measures()` calcule, pour chaque couple de stations successives, la longueur 3D,
la longueur horizontale, l'azimut (`atan2(dx, dy)`, horaire depuis le nord de la
grille) et la pente (`atan2(dz, longueur horizontale)`).

Le fichier Therion s'écrit au choix :

- **cartésien** : `data cartesian from to easting northing altitude`, différences de
  coordonnées. Aucune ambiguïté de déclinaison : c'est le style par défaut ;
- **normal** : `data normal from to length compass clino`. Les azimuts calculés sont
  des **gisements** (rapportés au nord de la grille) ; ils sont convertis en azimuts
  géographiques en ajoutant la convergence des méridiens, et le fichier déclare
  `declination 0.0 degrees` pour que Therion ne les corrige pas une seconde fois.

La première station est fixée (`fix`) avec le SCR du projet, sauf si son nom contient
`@` : elle appartient alors à une autre cavité déjà saisie, dont la position fait foi.

### 9. Contrôle par rapport à un levé de référence

`compare_to_reference()` apparie par **nom** les stations reconstruites et celles
d'un levé fiable (les jonctions ne sont comptées qu'une fois), puis calcule par
station `dx`, `dy`, `dz`, l'écart planimétrique `d2d` et l'écart total `d3d`, et en
tire moyenne, maximum et RMS. La couche produite dessine un vecteur de la station de
référence vers la station reconstruite : la direction des vecteurs est parlante, un
décalage systématique n'ayant pas la même cause qu'une rotation ou qu'une dilatation.

### Ce que vaut le résultat

Une reconstruction reste une **donnée de substitution** : la géométrie générale peut
être excellente, mais les valeurs spéléométriques (longueurs de visées, dénivelés de
détail) sont dégradées, et le fichier de métadonnées le dit explicitement. Les
altitudes marquées `interp` ou `extrap` ne sont pas des mesures : ce sont des
hypothèses de pente constante, à traiter comme telles dans toute analyse.
