# Boîte à outils Processing

Les traitements du plugin sont aussi publiés comme algorithmes QGIS, dans le groupe
**SpeleoTools** de la boîte à outils. Même code, même résultat que les onglets, mais
utilisable autrement.

---

## Notice d'utilisation

### Ce que cela apporte

- **traitement par lot** : clic droit sur un algorithme → *Exécuter comme processus de
  lot*, une ligne par cavité ou par dalle de MNT ;
- **modèles graphiques** : enchaîner les traitements avec ceux de QGIS, par exemple
  découper un MNT, calculer le VAT, détecter les dolines et filtrer par profondeur ;
- **console Python et `qgis_process`** : automatisation, scripts reproductibles ;
- **tâche de fond** : barre de progression et bouton Annuler, ce que les onglets n'ont
  pas ;
- **historique** : les paramètres de chaque exécution restent dans
  `Traitement → Historique`, ce qui documente le travail fait.

### Les algorithmes

| Nom | Identifiant | Entrées principales | Sortie |
| --- | --- | --- | --- |
| Épaisseur de roche | `speleotools:epaisseurroche` | MNT, couche cavité, dédoublonnage | couche de points |
| Visualisations MNT | `speleotools:visualisationsmnt` | MNT, liste de produits, paramètres | GeoTIFF dans un dossier |
| Détection de dolines | `speleotools:dolines` | MNT, seuils | polygones (+ centroïdes) |
| Profil développé | `speleotools:profildeveloppe` | MNT, polyligne, pas | CSV |
| Drapage sur le MNT | `speleotools:drapagemnt` | MNT, polyligne, pas | polyligne 3D |

Chaque algorithme affiche son aide dans le panneau de droite : elle reprend l'essentiel
de la méthode décrite dans les fiches correspondantes.

### Exemples

```python
# une cavité
processing.run("speleotools:epaisseurroche",
               {"DEM": mnt, "CAVITE": cavite, "DEDUP": True,
                "OUTPUT": "/tmp/epaisseur.gpkg"})

# profil le long de chaque cheminement d'une couche
processing.run("speleotools:profildeveloppe",
               {"DEM": mnt, "LIGNE": cheminements, "PAS": 1.0,
                "INTERP": True, "CSV": "/tmp/profil.csv"})

# préparer une couche 3D pour l'épaisseur à partir d'un tracé 2D
processing.run("speleotools:drapagemnt",
               {"DEM": mnt, "LIGNE": trace, "PAS": 5.0,
                "OUTPUT": "memory:"})
```

En ligne de commande :

```bash
qgis_process run speleotools:visualisationsmnt \
    --DEM=mnt.tif --VISUS=0,7 --DOSSIER=/data/visus
```

---

## Méthode

### Ce que fait un algorithme de plus qu'un onglet

Rien, du point de vue du calcul : les deux appellent les mêmes fonctions de
`speleo_utils.py`. Ce qui change est l'emballage.

- **Les entrées** sont déclarées en paramètres typés (`QgsProcessingParameterRasterLayer`,
  `…VectorLayer`, `…Number`, `…Enum`…). QGIS se charge de la validation, de l'interface,
  du mode lot et de la sérialisation dans un modèle.
- **Les sorties** passent par un *sink* : l'utilisateur choisit un GeoPackage, un
  shapefile, une couche mémoire ou temporaire, sans que l'algorithme ait à le savoir.
  C'est pourquoi les algorithmes n'ajoutent rien au projet de force, contrairement aux
  onglets.
- **La progression et l'annulation** utilisent l'objet `feedback` fourni par QGIS :
  les boucles longues appellent `feedback.setProgress()` et vérifient
  `feedback.isCanceled()`.
- **Les messages** partent dans `feedback.pushInfo()`, donc dans le journal
  d'exécution, et une erreur lève une `QgsProcessingException`, qui s'affiche
  proprement au lieu d'une boîte de dialogue.

### Correspondance avec les fiches

| Algorithme | Méthode détaillée dans |
| --- | --- |
| `epaisseurroche` | [Epaisseur_roche.md](Epaisseur_roche.md) |
| `visualisationsmnt` | [Visualisations_MNT.md](Visualisations_MNT.md) |
| `dolines` | [Dolines.md](Dolines.md) |
| `profildeveloppe` | [Profils.md](Profils.md), mode développé |
| `drapagemnt` | ci-dessous |

### Drapage sur le MNT

`create_profile_from_line()` (`speleo_utils.py`) densifie la polyligne au pas demandé
(ou garde ses sommets si le pas vaut 0), échantillonne le MNT à chaque point et
construit une géométrie **LineStringZ** dans le SCR du MNT.

Point important : là où le MNT n'a pas de valeur, la ligne est **coupée**. Un tronçon
n'est produit que s'il contient au moins deux points valides consécutifs, ce qui évite
de tracer une ligne 3D à travers une zone sans données. Une polyligne d'entrée peut
donc ressortir en plusieurs morceaux ; le champ `orig_id` conserve l'identifiant de
l'entité d'origine et `length_m` la longueur 3D du tronçon.

Usage courant : draper un cheminement 2D avant de le passer à l'épaisseur de roche,
ou fabriquer une ligne de sol 3D pour une vue 3D de QGIS.

### Ce qui n'est pas exposé

L'onglet **Topo ancienne** et l'**import Therion** n'ont pas d'équivalent Processing :
le premier est interactif par nature (clics de calage, tracé à la main), le second
enchaîne des algorithmes déjà tous disponibles individuellement dans la boîte à outils.
Le **profil projeté** n'y est pas non plus, sa ligne de coupe dépendant d'un choix
visuel d'emprise ; en lot, tracer les lignes de coupe voulues et utiliser le profil
développé.
