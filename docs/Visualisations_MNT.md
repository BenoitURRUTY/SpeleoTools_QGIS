# Visualisations MNT (prospection)

Produit, à partir d'un MNT LiDAR, les images de relief qui font ressortir les indices
karstiques : dépressions, entrées effondrées, ruptures de pente, micro-relief masqué
par la végétation sur les photographies aériennes.

---

## Notice d'utilisation

### Ce qu'il faut

Un MNT (modèle numérique de **terrain**, sol nu — pas un MNS). Les visualisations de
prospection n'ont d'intérêt qu'en haute résolution : 1 m ou mieux. En France, les
dalles LiDAR HD de l'IGN conviennent.

### Marche à suivre (onglet 🌄 Traitement MNT)

1. **MNT** et **dossier de sortie**.
2. Cocher les produits voulus et régler leurs paramètres :
   - **Ombrage** : azimut (315° par défaut) et élévation du soleil (35°) ;
   - **Ombrage multidirectionnel** : nombre de directions (16) ;
   - **Pente** : unités (degrés, pourcent, radians) ;
   - **SVF** et **ouverture** : rayon en **pixels** (10) et nombre de directions (16) ;
   - **SLRM** : rayon de lissage en pixels ;
   - **VAT** : taille de la fenêtre de lissage.
   - **Facteur Z** : exagération verticale appliquée avant le calcul (1 = aucune).
   - **Azimuts personnalisés** : liste séparée par des virgules, un ombrage par valeur.
3. **Analyser MNT**.

Les rasters sont écrits dans le dossier choisi et chargés dans un groupe
« Traitement MNT ». Le même travail est disponible en lot avec
`speleotools:visualisationsmnt`.

### Lire les résultats

| Produit | Ce qu'on y voit | Usage karstique |
| --- | --- | --- |
| Ombrage | relief éclairé d'une direction | lecture générale ; masque ce qui est parallèle à la lumière |
| Ombrage multidirectionnel | moyenne de plusieurs éclairages | supprime l'angle mort directionnel |
| Pente | inclinaison | ruptures de pente, bords de dolines, escarpements |
| SVF | part de ciel visible : sombre = encaissé | **dolines, entrées, gouffres** |
| Ouverture positive | ouverture vers le haut | crêtes et bosses |
| Ouverture négative | ouverture vers le bas | dépressions fermées, très lisible |
| SLRM | relief local, tendance générale retirée | micro-relief, petites formes |
| VAT | combinaison SVF + ombrage + pente | image de synthèse pour la prospection |

En pratique : commencer par le VAT ou le SVF pour repérer les candidats, confirmer
avec l'ouverture négative et la pente, puis vérifier sur l'ombrage que ce n'est pas un
artefact (talus de route, carrière, tas de bois).

---

## Méthode

### Chaîne de calcul

Tous les calculs passent par **rvt-py** (Relief Visualization Toolbox, Institut ZRC
SAZU) quand le paquet est installé. La fonction lit le MNT en tableau numpy avec GDAL
(`_read_dem_as_array()` : les NoData deviennent NaN), appelle `rvt.vis`, puis réécrit
un GeoTIFF calqué sur la géométrie du MNT source (`_save_array_as_geotiff()`,
compression LZW, NoData −9999).

Si rvt-py est absent, seuls l'**ombrage**, l'**ombrage multidirectionnel** et la
**pente** sont produits, par repli sur `gdal:hillshade` et `gdal:slope`
(avec `COMPUTE_EDGES`). Les autres produits renvoient un message explicite : ils n'ont
pas d'équivalent GDAL.

### Paramètres et unités

- **Rayon (SVF, ouverture)** : exprimé en **pixels**, pas en mètres. Sur un MNT à 1 m,
  un rayon de 10 donne un horizon de 10 m : suffisant pour des dolines de quelques
  dizaines de mètres, trop court pour de grandes dépressions. Augmenter le rayon
  augmente le temps de calcul à peu près linéairement.
- **Nombre de directions** : angles d'horizon testés autour de chaque pixel. 16 est
  un bon compromis ; 8 fait apparaître des artefacts en étoile.
- **Facteur Z** : exagération verticale appliquée avant le calcul. Utile sur un relief
  très plat, trompeur ailleurs — il accentue aussi le bruit du MNT.

### Ce que calcule chaque produit

**Ombrage** — éclairement lambertien d'une source placée à l'azimut et à l'élévation
donnés (`rvt.vis.hillshade`, ou `gdal:hillshade`). Les structures parallèles à la
direction de la lumière disparaissent : d'où l'intérêt de varier l'azimut.

**Ombrage multidirectionnel** — `rvt.vis.multi_hillshade` calcule un ombrage par
direction, et le plugin en prend la **moyenne** (`numpy.nanmean` sur l'axe des
directions) pour obtenir une image unique. Le repli GDAL utilise l'option
`MULTIDIRECTIONAL` native, dont la pondération diffère légèrement.

**Pente** — `rvt.vis.slope_aspect`, composante `slope`, dans l'unité demandée.

**SVF (Sky-View Factor)** — proportion de l'hémisphère céleste visible depuis chaque
pixel, estimée en cherchant l'angle d'horizon dans N directions jusqu'au rayon
maximal. Valeur de 0 (encaissé) à 1 (plan dégagé). Un fond de doline est sombre, une
crête est claire. Indépendant de la direction d'éclairage, contrairement à l'ombrage :
c'est ce qui en fait un bon détecteur de dépressions.

**Ouverture positive** — moyenne des angles zénithaux d'horizon ; met en avant ce qui
domine. **Ouverture négative** — exactement le même calcul appliqué au **MNT inversé**
(`dem = -arr` dans `openness_negative()`), ce qui fait ressortir les creux.

**SLRM (Simple Local Relief Model)** — `rvt.vis.slrm` : différence entre le MNT et sa
version lissée par un filtre de rayon `radius_cell`. Autrement dit, on retire la
tendance générale du relief pour ne garder que les écarts locaux. Un rayon trop grand
laisse revenir la topographie générale, un rayon trop petit ne montre que le bruit.

**VAT (Visualisation for Archaeological Topography)** — combinaison pondérée, calculée
par le plugin lui-même dans `VAT()` :

```
VAT = 0,50 × norm(SVF) + 0,25 × norm(ombrage 315°/35°) + 0,25 × norm(pente)
```

où `norm(a) = (a − min) / (max − min + 1e-10)` normalise chaque composante sur
**l'ensemble du raster** (min-max global, en ignorant les NaN). Le SVF est calculé
avec 16 directions et un rayon de 10 pixels, en dur dans cette fonction. Si la
fenêtre de lissage demandée est supérieure à 1, un filtre moyenneur
(`scipy.ndimage.uniform_filter`) est appliqué au résultat ; sans scipy, l'étape est
simplement sautée.

Deux conséquences de la normalisation globale : le rendu dépend de l'étendue traitée
(deux dalles voisines n'ont pas le même étalement de valeurs, donc pas exactement le
même contraste), et une valeur extrême isolée écrase le contraste de tout le reste —
découper les zones aberrantes améliore l'image. Si rvt-py est absent mais que le
plugin QGIS RVT est installé, le calcul est délégué à `rvt:rvt_blender`, dont la
recette interne diffère de celle ci-dessus.

### Nommage des fichiers

Le nom du MNT source est translittéré en ASCII et nettoyé (`_src_name()`), puis suffixé :
`<MNT>_hillshade.tif`, `<MNT>_multidh.tif`, `<MNT>_slope.tif`, `<MNT>_slrm.tif`,
`<MNT>_opns_neg.tif`, `<MNT>_vat.tif`, et `SVF_<MNT>.tif` / `OpenPos_<MNT>.tif` pour
les produits issus de la même fonction SVF.

### Limites

- un MNT interpolé sous forêt dense invente du micro-relief : les « dolines »
  minuscules à la limite de la résolution sont souvent des artefacts ;
- les traces d'origine humaine (chemins creux, carrières, terrassements) ressortent
  exactement comme les formes karstiques ;
- ces images servent à **orienter** la prospection, pas à conclure : toute anomalie
  demande une vérification sur le terrain.
