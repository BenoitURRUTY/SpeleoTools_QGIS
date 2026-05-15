# -*- coding: utf-8 -*-
"""
SpeleoTools — Point d'entrée du plugin QGIS.

Au chargement, vérifie automatiquement que les dépendances Python
nécessaires sont installées et propose de les installer si ce n'est pas le cas.
"""


def classFactory(iface):
    # ── Vérification des dépendances au premier démarrage ───────────
    try:
        from .install_dependencies import check_and_install
        check_and_install(
            parent_widget=iface.mainWindow(),
            silent_if_ok=True          # pas de popup si tout est déjà OK
        )
    except Exception as e:
        # Ne jamais bloquer le chargement du plugin sur une erreur du checker
        import traceback
        print(f"[SpeleoTools] Avertissement vérification dépendances : {e}")
        traceback.print_exc()

    # ── Chargement normal du plugin ──────────────────────────────────
    from .speleo_tools import SpeleoTools
    return SpeleoTools(iface)
