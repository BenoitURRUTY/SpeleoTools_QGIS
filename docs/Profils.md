# Profils topographiques

Extrait le profil altimétrique de la **surface** depuis le MNT, pour l'utiliser comme
ligne de sol au-dessus d'une coupe de cavité. Deux modes :

- **profil projeté** : coupe verticale selon un angle de projection, comme une
  élévation Therion ;
- **profil développé** : profil le long d'une polyligne existante (cheminement,
  trait de coupe dessiné à la main).

Dans les deux cas : X = distance le long du profil (m), Y = altitude du MNT (m).

---

## Notice d'utilisation

### Communs aux deux modes

- **MNT de référence** : le raster échantillonné.
- **Dossier de sortie** (bouton 📂) : vide = dossier temporaire du système.
- **Décalages X / Y** : ajoutés aux coordonnées écrites, pour caler le profil sur
  l'origine d'un dessin (une coupe Therion, un cartouche Illustrator ou Inkscape).
- Les couches vecteur sont reprojetées dans le SCR du MNT avant échantillonnage.

### Mode 1 — profil projeté

1. **Couche d'emprise** : polygone ou ligne couvrant la cavité (contour Therion,
   cheminement, emprise dessinée).
2. **Angle α** : lu dans un `.thconfig` (bouton *Lire*, qui cherche
   `-projection [elevation XX]`) ou saisi à la main.
3. **Marge emprise (%)** : agrandit la zone avant de calculer la longueur de la ligne
   de coupe (20 % par défaut).
4. Cocher **Sauvegarder la ligne de coupe** pour vérifier visuellement son tracé.
5. **Générer**.

### Mode 2 — profil développé

1. **Couche polyligne** : le tracé à suivre.
2. **Utiliser uniquement la sélection** : si coché et qu'une sélection existe, seules
   les entités sélectionnées sont parcourues (sinon toutes, avec un avertissement).
3. **Espacement des points (m)** : pas d'échantillonnage.
4. **Interpoler les valeurs NoData** et **Distance max interpolation** : comblement
   des trous du MNT, limité aux lacunes plus courtes que la distance donnée.
5. **Générer**.

### Ce qui sort

```
profil_projete_aXXdeg_<MNT>.csv / .gpkg / .png
profil_dev[_sel]_<ligne>_<MNT>.csv / .gpkg / .png
ligne_coupe_aXXdeg_<MNT>_ligne.gpkg      (option du mode projeté)
```

- **CSV** : `X_distance_m`, `Y_altitude_m` (cellule vide quand l'altitude manque).
- **GPKG sans SCR** : points dont la géométrie est (distance, altitude), donc
  directement superposables à un dessin de coupe dans un logiciel de mise en page.
  Attributs `X_dist_m`, `Y_alt_m`, `pt_index`.
- **PNG** : graphique, seulement si matplotlib est installé.

Le GeoPackage est volontairement sans système de coordonnées : ses X et Y ne sont pas
des coordonnées géographiques. QGIS demandera un SCR à l'ouverture — répondre
« aucun » ou ignorer.

---

## Méthode

### Mode projeté : où passe la ligne de coupe

1. L'emprise est reprojetée dans le SCR du MNT (`native:reprojectlayer`).
2. Les géométries de l'emprise sont **fusionnées** (`combine`) et le **centroïde** de
   cette union donne le point de passage de la coupe. Ce n'est pas le centre de la
   boîte englobante : une cavité en L ne place pas sa coupe au même endroit selon
   qu'on prend l'un ou l'autre, et le centroïde suit mieux la masse du réseau. Si
   l'union échoue (géométries vides), on retombe sur le centre de la boîte élargie.
3. La boîte englobante est élargie de `marge × max(largeur, hauteur)`.
4. La ligne de coupe est tracée à l'azimut **α + 90°**, c'est-à-dire
   perpendiculairement à la direction de projection : c'est la convention de Therion,
   où `-projection [elevation α]` signifie « regarder dans la direction α ». Le
   vecteur directeur est `(sin(α+90°), cos(α+90°))`, azimut horaire depuis le nord.
5. Sa longueur est la **diagonale** de la boîte élargie, centrée sur le centroïde :
   elle traverse donc toute l'emprise quel que soit l'angle.

### Mode projeté : échantillonnage

Le pas est fixé à la **résolution moyenne du MNT**
(`(rasterUnitsPerPixelX + rasterUnitsPerPixelY) / 2`), avec au minimum 2 points :
inutile d'échantillonner plus fin que le pixel, et inutile de perdre du détail en
échantillonnant plus grossièrement. Le nombre de points est
`longueur / résolution`, et les positions sont interpolées linéairement entre les
deux extrémités.

La distance portée en X est la distance depuis le début de la ligne, pas une
projection des stations : le profil décrit la surface le long de la coupe, pas la
cavité.

### Mode développé : densification et distance cumulée

Chaque segment de la polyligne est découpé en `n = max(1, entier(longueur / pas))`
intervalles ; les points sont placés aux fractions `k/n`, et le dernier sommet de la
partie est ajouté explicitement pour ne pas perdre l'extrémité. Comme `n` est un
entier, le pas réel est légèrement inférieur au pas demandé (un segment de 7 m avec
un pas de 2 m donne 3 intervalles de 2,33 m).

La distance en X est la **distance cumulée** depuis le premier point parcouru, calculée
de proche en proche. Elle continue d'une entité à la suivante : plusieurs polylignes
sélectionnées produisent un seul profil, dans l'ordre des identifiants. C'est voulu
pour les cheminements découpés en tronçons, mais cela donne un résultat étrange si les
entités ne se suivent pas — dans ce cas, les traiter séparément.

### Comblement des NoData (mode développé)

Quand l'option est cochée, les altitudes manquantes sont interpolées linéairement
**en fonction de l'indice du point** (`numpy.interp`), donc du rang dans la série. Le
pas étant régulier, cela revient pratiquement à une interpolation en distance.

Si une distance maximale est fixée, chaque trou est mesuré par la distance entre les
deux points valides qui l'encadrent ; au-delà de la limite, le trou reste vide plutôt
que d'être comblé par une droite qui traverserait une vallée entière.

L'algorithme Processing `speleotools:profildeveloppe` utilise la même logique via
`fill_gaps_linear()`, qui interpole directement en distance.

### Ce que le profil n'est pas

- ce n'est pas une coupe de la cavité : c'est la ligne de sol, à superposer à la
  coupe produite par Therion ou par l'onglet Topo ancienne ;
- en mode projeté, la ligne passe par le centroïde : deux versants situés de part et
  d'autre du réseau ne sont pas représentés, seul le terrain le long de cette ligne
  l'est ;
- le MNT sous couvert forestier ou en falaise reste une approximation : vérifier la
  cohérence avec l'altitude des entrées mesurées au GNSS.

### Contrôles

- activer l'option **Sauvegarder la ligne de coupe** et regarder où elle passe
  réellement ;
- comparer l'altitude aux extrémités du profil avec celle d'une entrée connue ;
- compter les points valides annoncés dans le journal : un écart important avec le
  nombre total signale un MNT troué ou une emprise qui déborde de sa couverture.
