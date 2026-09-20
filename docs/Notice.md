# SpeleoTools — notice d'utilisation

Notice complète du plugin, outil par outil. Chaque fiche comporte deux parties :
une **notice d'utilisation** (ce qu'il faut fournir, où cliquer, ce qui sort) et une
partie **méthode** qui détaille le calcul réellement effectué — formules, valeurs par
défaut, algorithmes appelés — pour qu'aucun résultat ne sorte d'une boîte noire.

## Les fiches

| Outil | Fiche |
| --- | --- |
| Import des exports Therion | [Import_Therion.md](Import_Therion.md) |
| Épaisseur de roche | [Epaisseur_roche.md](Epaisseur_roche.md) |
| Profils topographiques (projeté, développé) | [Profils.md](Profils.md) |
| Visualisations MNT (prospection) | [Visualisations_MNT.md](Visualisations_MNT.md) |
| Détection de dolines | [Dolines.md](Dolines.md) |
| Topo ancienne (plan + coupe → 3D) | [Topo_ancienne.md](Topo_ancienne.md) |
| — calage des scans (guide détaillé) | [Calage.md](Calage.md) |
| Boîte à outils Processing | [Processing.md](Processing.md) |

---

## 1. Installation et compléments

Le plugin s'installe depuis le ZIP : `Extensions → Installer/Gérer les extensions →
Installer depuis un ZIP`. Il ouvre une fenêtre à onglets (icône dans la barre d'outils
ou menu `Extensions → SpeleoTools`) et ajoute un groupe **SpeleoTools** à la boîte à
outils de traitement.

Seul **numpy** est nécessaire, et il est fourni avec QGIS. Les autres paquets sont
optionnels ; le plugin les vérifie au démarrage et propose de les installer
(`Extensions → SpeleoTools → Vérifier les dépendances`) :

| Complément | Sert à | Sans lui |
| --- | --- | --- |
| rvt-py | SVF, ouverture, SLRM, VAT | ombrage et pente restent calculés par GDAL |
| SAGA ou GRASS | comblement des dépressions (dolines) | message explicite, le reste fonctionne |
| scipy | lissage du VAT | VAT non lissé |
| matplotlib | graphiques PNG des profils | CSV et GPKG produits quand même |

L'installation se fait dans l'interpréteur Python de QGIS
(`python -m pip install <paquet>`), ce qui peut demander de redémarrer QGIS.

## 2. Conventions communes

**Systèmes de coordonnées.** Le plugin travaille dans le SCR du projet et reprojette
ce qui doit l'être : la couche cavité vers le MNT pour l'épaisseur, la polyligne vers
le MNT pour les profils, la couche de référence vers le projet pour la comparaison.
Les reprojections sont écrites dans le journal. Un MNT en coordonnées géographiques
(degrés) reste déconseillé : les distances horizontales n'y sont pas métriques.

**Altitudes.** Une altitude peut venir de trois endroits : la coordonnée Z de la
géométrie, un champ d'attribut (`elev`, `z`, `alt`, `altitude`, `depth`, `_ALT`), ou un
échantillonnage du MNT. Chaque outil dit lequel il utilise, et dans quel ordre.

**Échantillonnage d'un raster.** Toujours au plus proche voisin, par
`QgsRasterDataProvider.sample()` : la valeur rendue est celle du pixel contenant le
point, sans interpolation bilinéaire. Un NoData ou un NaN renvoie « pas de valeur » et
n'est jamais confondu avec un zéro.

**Journal.** Chaque onglet a sa fenêtre noire de journal : paramètres retenus, nombre
d'entités traitées, avertissements, chemins des fichiers écrits. C'est la première
chose à lire quand un résultat surprend. Les messages plus techniques vont dans
`Vue → Panneaux → Messages du journal`, onglet *SpeleoTools* ou *Speleo*.

**Fichiers de sortie.** Quand un dossier de sortie est laissé vide, les fichiers vont
dans le dossier temporaire du système et disparaissent au redémarrage. Les couches
écrites sur disque sont rechargées depuis le disque, pour que ce qui est affiché soit
exactement ce qui a été écrit.

**Ce que le plugin ne fait pas.** Il ne compense pas les bouclages (c'est le travail
de Therion ou de Survex), ne corrige pas les erreurs de levé, et ne remplace pas le
Géoréférenceur de QGIS pour les documents déformés.

## 3. Où est le code

La notice renvoie aux fonctions réelles ; le code est lisible et commenté.

| Fichier | Contenu |
| --- | --- |
| `speleo_tools.py` | fenêtre à onglets, enchaînement des traitements, profils, import Therion |
| `speleo_utils.py` | calculs sans interface : épaisseur, échantillonnage, visualisations MNT, dolines |
| `topo_ancienne_core.py` | calculs de la topo ancienne (sans QGIS, donc testables seuls) |
| `topo_ancienne_tab.py` | onglet topo ancienne : clics, couches, sorties |
| `speleo_provider.py` | algorithmes de la boîte à outils Processing |
| `speleo_compat.py` | compatibilité QGIS 3 / QGIS 4 pour les types de champs |
| `tests/` | `pytest` hors QGIS + deux scripts de bout en bout dans QGIS |

Les tests servent aussi de documentation exécutable : ils montrent, sur des données
fabriquées dont on connaît la réponse, ce que chaque fonction est censée rendre.
