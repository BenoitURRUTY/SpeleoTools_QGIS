# Épaisseur de roche

Calcule, pour chaque sommet d'une cavité, l'épaisseur de terrain qui la sépare de la
surface : `épaisseur = altitude du MNT − altitude de la cavité`.

Sert à repérer les zones minces (jonction possible avec la surface, risque
d'effondrement, sensibilité aux travaux ou aux pollutions de surface) et à produire
des cartes d'épaisseur le long d'un réseau.

---

## Notice d'utilisation

### Ce qu'il faut

- un **MNT** (raster d'élévation) ;
- une **couche cavité** avec une altitude : points ou polylignes, avec coordonnée Z
  (stations et cheminements issus de l'import Therion, par exemple) ou, à défaut, un
  champ d'altitude.

Les deux couches peuvent être dans des systèmes de coordonnées différents : les
points sont reprojetés vers celui du MNT avant l'échantillonnage, et la reprojection
est signalée dans le journal.

### Marche à suivre (onglet 🗻 Épaisseur roche)

1. **MNT (surface topographique)** : le raster d'élévation.
2. **Couche cavité** : la couche 3D.
3. **Fichier de sortie** (facultatif) : un GeoPackage. Laissé vide, le résultat est
   une couche mémoire, perdue à la fermeture du projet.
4. **Nom de la couche** : nom de la couche produite (`Thickness` par défaut).
5. **Calculer épaisseur**.

Pour traiter plusieurs cavités d'un coup, utiliser l'algorithme
`speleotools:epaisseurroche` de la boîte à outils en mode lot
(voir [Processing.md](Processing.md)).

### Ce qui sort

Une couche de points, un point par sommet retenu :

| Champ | Contenu |
| --- | --- |
| `src_elev` | altitude de la surface, lue dans le MNT (m) |
| `cave_elev` | altitude de la cavité (m) |
| `thickness` | `src_elev − cave_elev` (m) |
| `fid_src` | identifiant de l'entité d'origine, pour revenir à la galerie concernée |

Une valeur négative signifie que la cavité est au-dessus du MNT : altitude fausse,
MNT qui ne couvre pas la zone, ou entrée en falaise mal modélisée.

### Après le calcul

- symboliser `thickness` en dégradé, ou filtrer `thickness < 10` pour isoler les
  zones minces ;
- croiser avec les dolines : une doline au-dessus d'une épaisseur faible est un
  indice de prospection sérieux ;
- exporter en CSV pour un profil d'épaisseur le long du réseau.

---

## Méthode

### Parcours des sommets

La fonction `iter_thickness_points()` (`speleo_utils.py`) parcourt toutes les
entités de la couche cavité et, pour chacune, tous les sommets de sa géométrie
(`QgsGeometry.vertices()`). Les points sont traités comme des sommets isolés, les
polylignes comme des suites de sommets ; les polygones sont ignorés.

Aucune densification n'est faite : **l'outil ne calcule rien entre deux stations**.
Sur un cheminement dont les visées font 30 m, l'épaisseur n'est connue qu'aux deux
extrémités de chaque visée. Pour un échantillonnage régulier, densifier la couche
avant (`Traitement → Densifier par intervalle`) ou passer par
`speleotools:drapagemnt`.

### Dédoublonnage

Les topographies contiennent beaucoup de sommets superposés : fin d'une visée et
début de la suivante, stations partagées entre branches. Ils sont filtrés par une
**grille de 10 cm** : les coordonnées du point, exprimées **dans le SCR du MNT**,
sont arrondies à 0,1 m et le couple obtenu sert de clé ; un point dont la clé existe
déjà est ignoré.

Deux conséquences à connaître :

- c'est un arrondi sur grille, pas une tolérance : deux points distants de 5 cm de
  part et d'autre d'une limite de case sont conservés tous les deux ;
- l'arrondi se fait après reprojection. En coordonnées géographiques, arrondir à 0,1°
  confondrait des points distants de plusieurs kilomètres — c'était le comportement
  d'une version précédente, corrigé en 1.2.

Le dédoublonnage se désactive dans l'algorithme Processing (paramètre `DEDUP`).

### Altitude de la surface

`sample_raster_at_point()` transforme le point vers le SCR du MNT si nécessaire, puis
appelle `dataProvider().sample()` : valeur du pixel contenant le point, sans
interpolation. Un NoData ou un NaN rend `None`, et le point est alors abandonné : il
n'apparaît pas dans la sortie, plutôt que d'y figurer avec une épaisseur douteuse.

L'incertitude sur cette altitude est celle du MNT (typiquement quelques dizaines de
centimètres sur un LiDAR aéroporté, davantage sous couvert forestier dense) augmentée
de la variation du terrain à l'intérieur du pixel : sur une pente à 40° et un pixel de
1 m, deux points distants d'un pixel diffèrent déjà de 0,8 m.

### Altitude de la cavité

Dans l'ordre :

1. la coordonnée **Z du sommet**, si la géométrie est 3D et que Z n'est pas NaN ;
2. sinon, `layer_feature_elevation()` cherche un champ nommé `elev`, `z`, `alt`,
   `altitude` ou `depth` (comparaison en minuscules) et prend sa valeur ;
3. cette fonction, quand la géométrie porte plusieurs Z, retient le **minimum** des Z
   de l'entité — choix conservateur hérité de l'usage « profondeur maximale », qui ne
   joue que pour les entités sans Z par sommet.

Si aucune altitude n'est trouvée, le point est ignoré.

### Sortie

La couche produite est dans le **SCR de la couche cavité** (les points y sont
inchangés) ; seule la valeur du MNT a voyagé. Écrite en GeoPackage si un chemin est
donné, elle est ensuite rechargée depuis le disque.

### Contrôles

- comparer une poignée de valeurs avec l'outil d'identification sur le MNT ;
- vérifier que le nombre de points est cohérent avec le nombre de stations attendu :
  un nombre trop faible signale des altitudes manquantes ou un MNT qui ne couvre pas
  toute la cavité ;
- surveiller les épaisseurs négatives ou aberrantes, qui trahissent presque toujours
  un problème de référentiel altimétrique (NGF-IGN69 pour le MNT contre altitudes
  barométriques ou arbitraires pour la topo ancienne).

### Limites

- le résultat ne vaut que ce que valent le MNT et l'altitude de la cavité ; sur un
  squelette reconstruit depuis un plan ancien, l'épaisseur hérite de l'incertitude de
  la reconstruction ;
- l'épaisseur mesurée est **verticale**, pas perpendiculaire à la paroi : sous une
  falaise, la vraie distance à l'air libre peut être bien plus courte ;
- la cavité est réduite à son axe : la voûte, plus haute, est plus proche de la
  surface que la valeur calculée.
