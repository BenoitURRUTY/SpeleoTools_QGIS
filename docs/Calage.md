# Caler un plan et une coupe anciens — guide détaillé

Ce document complète l'onglet **📜 Topo ancienne** de SpeleoTools
(notice générale : [Notice.md](Notice.md), fiche de l'onglet :
[Topo_ancienne.md](Topo_ancienne.md)). Il décrit ce que
fait chaque méthode de calage, ce qu'elle exige du document, la précision qu'on peut
en attendre et comment la contrôler.

---

## 1. Ce qu'est un calage dans SpeleoTools

Caler un scan, c'est trouver la transformation qui amène les pixels de l'image sur
des coordonnées réelles. SpeleoTools utilise une **similitude** (transformation de
Helmert à 4 paramètres) :

```
x =  s·cos φ · u − s·sin φ · v + tx          u = colonne du pixel
y =  s·sin φ · u + s·cos φ · v + ty          v = − ligne du pixel
```

soit **une échelle** `s` (m/pixel), **une rotation** `φ` et **une translation**
`(tx, ty)`. Conséquences pratiques :

- les angles et les formes du dessin sont conservés, l'échelle est la même dans toutes
  les directions : le document n'est pas déformé pour « coller » au terrain ;
- les défauts du support (papier dilaté, pli, photocopie de photocopie, scan non
  plan) ne sont **pas** corrigés. Ils restent dans le résultat, ce qui est honnête :
  une déformation absorbée est une erreur qu'on ne voit plus.

Le calage n'écrit jamais dans l'image d'origine : il produit un fichier **VRT** posé à
côté, qui référence le scan et porte la géotransformation. Recaler = réécrire ce VRT.

Le journal affiche après chaque calage l'échelle obtenue (m/pixel) et la rotation.
Ces valeurs sont conservées dans les métadonnées de la reconstruction.

---

## 2. Calage du plan

### 2.1 Vue d'ensemble

| Méthode | Ce qu'il faut sur le document | Ce qu'elle détermine | À utiliser quand |
| --- | --- | --- | --- |
| Déjà géoréférencé | Plusieurs amers identifiables sur le terrain | tout (selon la transformation choisie dans le Géoréférenceur) | Le document porte un quadrillage ou plusieurs points connus, ou il faut absorber des déformations |
| 2 points connus | 2 points identifiables dont on connaît X et Y | échelle + rotation + position | Deux entrées levées au GNSS, ou une entrée et un point remarquable coté |
| Entrée + échelle + nord | 1 entrée connue, une barre d'échelle, une flèche nord | échelle (barre), rotation (flèche), position (entrée) | Cas le plus courant des topos publiées : une seule entrée connue |

### 2.2 Méthode A — scan déjà géoréférencé

Le calage se fait en amont dans le **Géoréférenceur de QGIS**, puis l'onglet charge le
raster tel quel. C'est la voie à prendre si le document porte un quadrillage, un
cartouche de coordonnées ou plusieurs amers de surface (entrées, bâti, routes).

Choix de la transformation dans le Géoréférenceur :

- **Helmert** : identique à ce que fait SpeleoTools (échelle + rotation), avec autant
  de points qu'on veut et un résidu par point. C'est le choix par défaut ;
- **Polynomiale 1 (affine)** : autorise deux échelles différentes et un cisaillement.
  Utile quand le scan est anisotrope (entraînement du scanner) ou le papier dilaté
  dans un seul sens ;
- **Polynomiale 2/3, TPS** : déforment localement le document pour faire coïncider
  tous les points. À réserver aux supports réellement déformés (grande feuille pliée,
  assemblage de morceaux), en sachant que la géométrie interne du dessin n'est plus
  celle du levé : les longueurs et les angles reconstruits deviennent difficiles à
  interpréter.

Exporter en GeoTIFF, puis choisir **Déjà géoréférencé** et **Charger**.

### 2.3 Méthode B — deux points de coordonnées connues

On clique deux points sur le scan et on saisit leurs coordonnées. La similitude
passant exactement par ces deux points est calculée : elle en déduit à la fois
l'échelle et l'orientation, aucune barre d'échelle ni flèche nord n'est nécessaire.

Bons candidats : deux entrées levées au GNSS différentiel, une entrée et une borne ou
un point coté reporté sur le plan, deux angles d'un cadre de coordonnées.

**Précision.** L'orientation est fixée par la direction entre les deux points : une
erreur de pointé ε sur une base de longueur D produit une erreur angulaire d'environ
`ε / D` radians, qui se propage ensuite sur tout le réseau.

| Base entre les 2 points | Erreur de pointé | Erreur d'orientation | Écart induit à 500 m |
| --- | --- | --- | --- |
| 50 m | 0,5 m | 0,57° | 5,0 m |
| 200 m | 0,5 m | 0,14° | 1,3 m |
| 500 m | 0,5 m | 0,06° | 0,5 m |

Donc : **prendre les deux points les plus éloignés possible**, et pointer au centre du
symbole (croix, cercle d'entrée) plutôt qu'à sa périphérie.

L'échelle est également déduite de ces deux points : si le document est déformé, elle
absorbe la déformation moyenne le long de cette base. Comparer l'échelle obtenue
(journal) avec celle attendue (§ 4.1) est un bon test de cohérence.

### 2.4 Méthode C — entrée connue + barre d'échelle + flèche nord

C'est la méthode « historique », celle qui s'applique à une topo publiée dont on ne
connaît qu'une entrée.

**a) La barre d'échelle** fixe l'échelle : `s = longueur réelle / distance en pixels`.

- cliquer les deux extrémités de la barre **la plus longue** du document : l'erreur
  relative d'échelle est le rapport de l'erreur de pointé à la longueur cliquée
  (2 px d'erreur sur une barre de 100 px = 2 % ; sur 500 px = 0,4 %) ;
- cliquer le même bord des deux traits d'extrémité (les deux bords gauches, par
  exemple) et saisir la longueur correspondante ;
- ne pas se fier à une échelle écrite (« 1/500 ») sans vérifier : une réduction, une
  photocopie ou un recadrage l'invalide. La barre graphique, elle, suit le document.

**b) La flèche nord** fixe la rotation. L'erreur angulaire vaut environ
`erreur de pointé / longueur cliquée` :

| Longueur cliquée | Erreur de pointé | Erreur d'orientation |
| --- | --- | --- |
| 100 px | 2 px | 1,15° |
| 300 px | 2 px | 0,38° |
| 800 px | 2 px | 0,14° |

Et une erreur d'orientation se paie loin de l'entrée : **1° ≈ 17 m d'écart au bout
d'un kilomètre de développement**. Il vaut donc la peine de cliquer la plus longue
ligne qui matérialise le nord : hampe complète de la flèche, bord du cadre s'il est
orienté, ligne du quadrillage, et à défaut de zoomer au maximum sur les deux extrémités.

**c) Quel nord ?** C'est le choix qui se trouve juste sous la flèche dans l'onglet.
Un plan ancien est presque toujours orienté au **nord magnétique de l'époque du
levé** ; les plans plus récents, ou repris sur fond IGN, sont souvent au **nord de la
grille** (Lambert). L'onglet propose les trois cas et calcule l'azimut à saisir :

| La flèche indique | Azimut réel dans le SCR du projet |
| --- | --- |
| le nord de la grille | 0 |
| le nord géographique (vrai) | −γ |
| le nord magnétique | D − γ |

où **γ est la convergence des méridiens** au point considéré (gisement = azimut − γ)
et **D la déclinaison magnétique à la date du levé** (est positif).

Le bouton **🧭 Calculer** détermine γ numériquement à la position de l'entrée, pour
n'importe quelle projection : il transforme le point en géographiques, remonte d'un
kilomètre plein nord, reprojette, et mesure l'angle obtenu. Pour le Lambert-93, cela
revient à `γ = n·(λ − 3°)` avec `n = 0,7256077650` (exposant de la projection, calculé
depuis les paramètres IGN : parallèles 44° et 49° N, méridien 3° E, GRS80). Dans les
Alpes du Nord, γ vaut environ +2 à +2,6°.

**Trouver D.** Le calculateur du NCEI couvre 1590 à 2029 (modèle gufm1 avant 1900,
IGRF ensuite) : saisir les coordonnées de la cavité et la date du levé —
<https://www.ngdc.noaa.gov/geomag/calculators/magcalc.shtml>. Si le document indique
lui-même la déclinaison employée, c'est celle-là qu'il faut reprendre : elle décrit ce
que l'auteur a fait, pas ce que le champ magnétique valait réellement.

**Si le document ne dit pas quel nord il utilise**, chercher les indices : mention
« Nm », « Ng », « déclinaison », une double flèche (les deux nords), un cartouche
de fond IGN, un quadrillage. En dernier recours, caler avec l'hypothèse la plus
probable (nord magnétique de l'époque), puis vérifier : un écart systématique en
rotation se voit très bien en superposant une jonction connue, une autre cavité ou une
entrée levée au GNSS, et il se corrige en changeant l'azimut saisi et en recalant.

La date du levé est demandée dans la section **Cavité** : elle est conservée dans les
métadonnées et écrite dans le fichier Therion, ce qui permet à un relecteur de
retrouver la déclinaison utilisée.

---

## 3. Calage de la coupe

### 3.1 Le repère de la coupe

La coupe n'est pas géoréférencée : elle est calée dans un repère à deux axes,
**X = abscisse horizontale (m)** et **Z = altitude (m)**. Pour pouvoir la dessiner dans
le même canevas que le plan, SpeleoTools l'affiche décalée d'environ 10 km sous le
plan (`X affiché = X + X entrée`, `Y affiché = Z + Y entrée − 10 000`). Les boutons
🔍 Plan et 🔍 Coupe passent de l'une à l'autre.

**Ce qui doit être juste, c'est Z.** L'abscisse X ne sert qu'à retrouver, pour chaque
station du plan, l'endroit correspondant sur le dessin de la coupe : une erreur
d'échelle horizontale uniforme est absorbée par l'appariement des stations (ajustement
par moindres carrés en coupe projetée, recalage par morceaux entre stations appariées
en coupe développée). Le journal signale d'ailleurs l'écart d'échelle qu'il constate.

Conséquence utile : **si la coupe a une exagération verticale** (échelle verticale
différente de l'horizontale, fréquent sur les grandes cavités), il faut cliquer
l'échelle **sur la graduation verticale**, pour que les altitudes soient justes. Le
décalage horizontal qui en résulte sera rattrapé par l'appariement.

### 3.2 La barre d'échelle

- **Barre horizontale** (case « La barre est horizontale » cochée) : son inclinaison
  sert aussi à redresser un scan posé de travers. C'est le cas courant.
- **Graduation verticale d'altitudes** : décocher la case, cliquer deux graduations
  (par exemple 1 400 et 1 500) et saisir l'écart correspondant (100 m). Sans la case,
  la direction de la barre n'intervient pas : seule sa longueur compte. Le scan est
  alors supposé droit ; s'il est penché, le redresser avant (rotation dans un éditeur
  d'image, ou Géoréférenceur).
- **Aucune barre** : utiliser deux altitudes cotées sur la coupe (entrée et point bas,
  par exemple), en décochant également la case. On saisit alors la dénivelée entre les
  deux points cliqués.

### 3.3 Le point de référence

Il donne la position du repère : on clique un point du dessin et on saisit son
abscisse X et son altitude Z.

- cas normal : l'entrée, avec `X = 0` et `Z = altitude de l'entrée` (le champ suit
  automatiquement l'altitude saisie dans la section Plan tant qu'on ne le modifie pas) ;
- **coupe d'un secteur isolé, sans l'entrée** : prendre une station cotée du dessin,
  saisir son altitude et une abscisse approximative (distance cumulée estimée depuis
  l'entrée). L'abscisse n'a pas besoin d'être juste : il suffit de nommer une ou deux
  stations à l'identique sur le plan et sur la coupe pour que l'appariement recale X.

### 3.4 Coupe développée ou coupe projetée

- **Développée** : l'abscisse est la longueur horizontale cumulée le long de la
  polygonale. Les galeries sont « déroulées » ; un coude en plan ne raccourcit pas la
  coupe. C'est le cas le plus fréquent sur les topos de réseaux sinueux.
- **Projetée** : la coupe est la projection sur un plan vertical d'azimut donné. On
  saisit α avec la convention de Therion (`-projection [elevation α]`, l'axe horizontal
  de la coupe étant orienté à α + 90°), la même que l'onglet Profils.

Pour distinguer les deux : une coupe projetée superpose les galeries parallèles à
l'axe de vue et « écrase » les boucles ; une coupe développée les déroule et fait
apparaître un développement total proche de celui annoncé. Le cartouche indique
souvent « coupe développée » ou « projection selon N…° ».

Si la coupe est dessinée vue de l'autre côté, cocher **Inverser le sens** : le journal
le signale (coefficient d'ajustement négatif).

---

## 4. Contrôler un calage

### 4.1 Vérifier l'échelle annoncée par le journal

Pour un document scanné, l'échelle attendue se calcule :

```
m/pixel = dénominateur d'échelle × 0,0254 / résolution du scan (dpi)
```

Exemples : un 1/500 scanné à 300 dpi donne 0,042 m/px ; un 1/1 000 à 600 dpi donne
0,042 m/px également ; un 1/2 000 à 300 dpi, 0,169 m/px. Un écart important signale
une erreur de saisie (longueur de barre, mauvaise barre cliquée) ou un document
réduit.

### 4.2 Autres contrôles

- mesurer avec l'outil de mesure de QGIS une distance connue du document (une autre
  barre d'échelle, une longueur cotée) : l'écart relatif est l'erreur d'échelle ;
- superposer le MNT, les entrées GNSS, les cavités voisines déjà calées : un décalage
  en rotation se voit à ce que l'écart croît avec la distance à l'entrée, un décalage
  en translation à ce qu'il reste constant ;
- après le calcul, afficher les **verticales des stations sur la coupe** (option de la
  section ④) : chaque station du plan y est reportée à son abscisse, avec la position
  3D obtenue. Si les points s'écartent du dessin, c'est l'appariement plan/coupe qu'il
  faut reprendre (noms de stations), pas le calage ;
- lire dans la table `stations_3d` le champ `dz_plan_coupe` : il donne, pour les
  stations qui portent à la fois une cote du plan et une lecture sur la coupe, l'écart
  entre les deux. Le journal en affiche la moyenne et le maximum ;
- compiler le `.th` produit dans Therion et regarder les bouclages avec le reste du
  réseau : c'est le contrôle le plus sévère.

---

## 5. Limites à garder en tête

- Une reconstruction reste une **donnée de substitution** : la géométrie générale peut
  être bonne, les valeurs spéléométriques (longueurs de visées, dénivelés de détail)
  sont dégradées. Les métadonnées produites le disent explicitement.
- Les puits et les ressauts sont souvent dessinés symboliquement, pas à l'échelle :
  leurs profondeurs sur la coupe sont à prendre avec prudence, et une cote écrite sur
  le plan est plus fiable qu'une lecture graphique (c'est l'ordre de priorité appliqué
  par l'outil).
- Un dessin « développé » à main levée n'a pas d'abscisse rigoureuse : l'appariement
  par noms de stations est alors indispensable.
- La similitude ne corrige ni les plis, ni la dilatation différentielle du papier, ni
  les erreurs du levé d'origine.
- Tous les paramètres de calage (document, méthode, échelle, rotation, azimut de la
  flèche, référence de la coupe) sont écrits dans `<nom>_metadonnees.txt` et en tête du
  fichier Therion : un relecteur peut refaire le raisonnement, ce qui est exactement ce
  qui manque aux archives anciennes.
