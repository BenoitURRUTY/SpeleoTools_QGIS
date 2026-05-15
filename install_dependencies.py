# -*- coding: utf-8 -*-
"""
SpeleoTools — Gestionnaire automatique de dépendances Python.

Ce module est importé au démarrage du plugin (dans __init__.py).
Il vérifie que les packages requis sont installés dans l'interpréteur
Python embarqué de QGIS, et propose de les installer si ce n'est pas
le cas, via une boîte de dialogue non-bloquante.

Compatibilité : QGIS 3.10+  (Python 3.6+)
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import os
from typing import NamedTuple

# ─────────────────────────────────────────────────────────────
#  LISTE DES DÉPENDANCES
#  import_name  : nom utilisé dans import
#  pip_name     : nom du package sur PyPI (peut différer)
#  min_version  : version minimale requise (None = pas de contrainte)
#  required     : si True le plugin ne peut pas démarrer sans ce package
# ─────────────────────────────────────────────────────────────
class Dep(NamedTuple):
    import_name: str
    pip_name: str
    min_version: str | None = None
    required: bool = True
    description: str = ""


DEPENDENCIES: list[Dep] = [
    Dep("pandas",     "pandas",     "1.3",  True,
        "Manipulation de tableaux de données (import Therion)"),
    Dep("geopandas",  "geopandas",  "0.10", True,
        "Lecture/écriture de fichiers géospatiaux (import Therion)"),
    Dep("numpy",      "numpy",      "1.20", True,
        "Calculs matriciels (analyses MNT)"),
    Dep("rvt",        "rvt-py",     "2.2",  False,
        "Relief Visualization Toolbox — hillshade, SVF, VAT…\n"
        "(optionnel : fallback GDAL si absent)"),
    Dep("scipy",      "scipy",      None,   False,
        "Lissage VAT et analyses supplémentaires (optionnel)"),
]


# ─────────────────────────────────────────────────────────────
#  Vérification d'une dépendance
# ─────────────────────────────────────────────────────────────
def _check_dep(dep: Dep) -> tuple[bool, str | None]:
    """
    Retourne (ok, installed_version).
    ok=False si absent ou version insuffisante.
    """
    try:
        mod = importlib.import_module(dep.import_name)
        version = getattr(mod, "__version__", None)
        if dep.min_version and version:
            from packaging.version import Version
            try:
                if Version(version) < Version(dep.min_version):
                    return False, version   # version trop vieille
            except Exception:
                pass  # packaging indisponible → on ignore la contrainte
        return True, version
    except ImportError:
        return False, None


def _pip_install(pip_names: list[str], progress_cb=None) -> tuple[bool, str]:
    """
    Lance `pip install` via subprocess dans l'interpréteur Python de QGIS.
    Retourne (success, output_text).
    """
    python_exe = sys.executable
    cmd = [python_exe, "-m", "pip", "install", "--upgrade"] + pip_names

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,         # 5 min max
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Timeout : l'installation a dépassé 5 minutes."
    except Exception as e:
        return False, str(e)


# ─────────────────────────────────────────────────────────────
#  Point d'entrée principal
# ─────────────────────────────────────────────────────────────
def check_and_install(parent_widget=None, silent_if_ok: bool = True) -> bool:
    """
    Vérifie toutes les dépendances et propose l'installation si nécessaire.

    Args:
        parent_widget : widget QGIS parent pour les boîtes de dialogue.
        silent_if_ok  : si True, n'affiche rien quand tout est déjà installé.

    Returns:
        True  si toutes les dépendances *required* sont satisfaites.
        False sinon (le plugin peut encore démarrer en mode dégradé).
    """
    # Importer Qt seulement ici pour éviter les imports circulaires au chargement
    try:
        from qgis.PyQt import QtWidgets, QtCore
        from qgis.PyQt.QtCore import Qt
    except ImportError:
        # Hors QGIS (tests unitaires) : on ne fait que vérifier
        missing = [d for d in DEPENDENCIES if not _check_dep(d)[0] and d.required]
        return len(missing) == 0

    # ── Inventaire ──────────────────────────────────────────────────
    missing_required: list[Dep] = []
    missing_optional: list[Dep] = []
    ok_list:          list[str] = []

    for dep in DEPENDENCIES:
        ok, ver = _check_dep(dep)
        if ok:
            ok_list.append(f"✔ {dep.pip_name} {ver or ''}")
        elif dep.required:
            missing_required.append(dep)
        else:
            missing_optional.append(dep)

    # Tout est OK
    if not missing_required and not missing_optional:
        if not silent_if_ok:
            QtWidgets.QMessageBox.information(
                parent_widget, "SpeleoTools — Dépendances",
                "Toutes les dépendances sont installées :\n\n" +
                "\n".join(ok_list))
        return True

    # ── Construction du message ──────────────────────────────────────
    lines = ["<b>SpeleoTools a besoin de packages Python supplémentaires.</b><br>"]

    if missing_required:
        lines.append("<br><b style='color:#c62828'>Packages requis (manquants) :</b>")
        for d in missing_required:
            lines.append(f"• <b>{d.pip_name}</b>"
                         + (f" ≥ {d.min_version}" if d.min_version else "")
                         + f"<br>&nbsp;&nbsp;&nbsp;<i>{d.description}</i>")

    if missing_optional:
        lines.append("<br><b style='color:#e65100'>Packages optionnels (manquants) :</b>")
        for d in missing_optional:
            lines.append(f"• <b>{d.pip_name}</b>"
                         + (f" ≥ {d.min_version}" if d.min_version else "")
                         + f"<br>&nbsp;&nbsp;&nbsp;<i>{d.description}</i>")

    if ok_list:
        lines.append("<br><b style='color:#2e7d32'>Déjà installés :</b>")
        lines.append("<br>".join(ok_list))

    lines.append("<br>Voulez-vous les installer maintenant via pip ?")
    lines.append("<small><i>L'opération peut prendre 1-2 minutes selon votre connexion.</i></small>")

    msg = QtWidgets.QMessageBox(parent_widget)
    msg.setWindowTitle("SpeleoTools — Installation des dépendances")
    msg.setTextFormat(Qt.RichText)
    msg.setText("<br>".join(lines))
    msg.setIcon(QtWidgets.QMessageBox.Question)

    btn_install   = msg.addButton("📦 Installer maintenant",
                                   QtWidgets.QMessageBox.AcceptRole)
    btn_required  = msg.addButton("⚠ Installer seulement les requis",
                                   QtWidgets.QMessageBox.ActionRole)
    btn_skip      = msg.addButton("Ignorer (mode dégradé)",
                                   QtWidgets.QMessageBox.RejectRole)

    # Cacher le bouton "requis seulement" s'il n'y a pas d'optionnels
    btn_required.setVisible(bool(missing_optional))
    msg.exec_()
    clicked = msg.clickedButton()

    if clicked == btn_skip:
        return len(missing_required) == 0

    # Décider quoi installer
    to_install: list[str] = []
    if clicked == btn_install:
        to_install = [d.pip_name for d in missing_required + missing_optional]
    elif clicked == btn_required:
        to_install = [d.pip_name for d in missing_required]

    if not to_install:
        return len(missing_required) == 0

    # ── Dialog de progression ────────────────────────────────────────
    progress = QtWidgets.QProgressDialog(
        "Installation des packages…", "Annuler", 0, 0, parent_widget)
    progress.setWindowTitle("SpeleoTools — pip install")
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    progress.setMinimumWidth(420)
    progress.show()
    QtWidgets.QApplication.processEvents()

    success, output = _pip_install(to_install)

    progress.close()

    # ── Résultat ─────────────────────────────────────────────────────
    if success:
        # Recharger les modules dans la session courante
        for dep in (missing_required + missing_optional):
            if dep.pip_name in to_install:
                try:
                    importlib.import_module(dep.import_name)
                except ImportError:
                    pass  # nécessite parfois un redémarrage

        result_box = QtWidgets.QMessageBox(parent_widget)
        result_box.setWindowTitle("Installation réussie")
        result_box.setIcon(QtWidgets.QMessageBox.Information)
        result_box.setText(
            "✅ <b>Packages installés avec succès !</b><br><br>"
            "Si certains packages ne sont pas encore disponibles dans cette session, "
            "<b>redémarrez QGIS</b> pour les activer.")
        detail = QtWidgets.QTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText(output[-3000:])   # afficher les 3000 derniers chars
        detail.setMaximumHeight(200)
        result_box.layout().addWidget(detail, result_box.layout().rowCount(), 0, 1, -1)
        result_box.exec_()
        return True

    else:
        err_box = QtWidgets.QMessageBox(parent_widget)
        err_box.setWindowTitle("Erreur d'installation")
        err_box.setIcon(QtWidgets.QMessageBox.Critical)
        err_box.setText(
            "❌ <b>L'installation a échoué.</b><br><br>"
            "Essayez manuellement dans la console Python QGIS :<br>"
            f"<code>import subprocess, sys<br>"
            f"subprocess.run([sys.executable, '-m', 'pip', 'install', "
            f"{', '.join(repr(p) for p in to_install)}])</code>")
        detail = QtWidgets.QTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText(output[-3000:])
        detail.setMaximumHeight(200)
        err_box.layout().addWidget(detail, err_box.layout().rowCount(), 0, 1, -1)
        err_box.exec_()
        return len(missing_required) == 0


# ─────────────────────────────────────────────────────────────
#  Décorateur utilitaire pour les méthodes qui ont besoin d'un package
# ─────────────────────────────────────────────────────────────
def requires(*import_names):
    """
    Décorateur qui vérifie qu'un ou plusieurs packages sont disponibles
    avant d'exécuter la méthode décorée.

    Compatible avec les slots Qt : le signal clicked(bool) passe un
    argument booléen que le décorateur absorbe proprement.

    Usage :
        @requires("geopandas", "pandas")
        def run_therion_import(self): ...
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            # Qt's clicked(bool) signal passes a checked-state bool — drop it
            # so methods declared as func(self) ne reçoivent pas d'argument inattendu
            missing = []
            for name in import_names:
                try:
                    importlib.import_module(name)
                except ImportError:
                    missing.append(name)
            if missing:
                try:
                    from qgis.PyQt import QtWidgets
                    QtWidgets.QMessageBox.critical(
                        None,
                        "Dépendance manquante",
                        f"Ce bouton nécessite : {', '.join(missing)}\n\n"
                        "Allez dans Extensions → SpeleoTools → "
                        "Vérifier les dépendances.")
                except Exception:
                    print(f"[SpeleoTools] Dépendances manquantes : {missing}")
                return None
            return func(self)
        wrapper.__name__ = func.__name__
        wrapper.__doc__  = func.__doc__
        return wrapper
    return decorator
