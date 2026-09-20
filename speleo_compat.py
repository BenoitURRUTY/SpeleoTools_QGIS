# -*- coding: utf-8 -*-
"""
SpeleoTools — couche de compatibilité QGIS 3 / QGIS 4 (Qt5 / Qt6).

QGIS 3.38 a remplacé les types de champs QVariant.* par QMetaType.Type.* et
PyQt6 ne fournit plus QVariant.  Ce module expose des constantes et une
fabrique de champs qui fonctionnent dans les deux mondes :

    from .speleo_compat import TYPE_DOUBLE, field
    fields.append(field("thickness", TYPE_DOUBLE))
"""

from qgis.core import QgsField

_USE_METATYPE = False
try:                                  # QGIS >= 3.38
    from qgis.PyQt.QtCore import QMetaType
    QgsField("t", QMetaType.Type.Double)
    _USE_METATYPE = True
except Exception:                     # QGIS 3.x plus ancien
    QMetaType = None

if _USE_METATYPE:
    TYPE_INT = QMetaType.Type.Int
    TYPE_LONG = QMetaType.Type.LongLong
    TYPE_DOUBLE = QMetaType.Type.Double
    TYPE_STRING = QMetaType.Type.QString
    TYPE_BOOL = QMetaType.Type.Bool
else:
    from qgis.PyQt.QtCore import QVariant
    TYPE_INT = QVariant.Int
    TYPE_LONG = QVariant.LongLong
    TYPE_DOUBLE = QVariant.Double
    TYPE_STRING = QVariant.String
    TYPE_BOOL = QVariant.Bool


def field(name, type_, length=0, precision=0):
    """QgsField portable (QVariant ou QMetaType selon la version de QGIS)."""
    if length:
        return QgsField(name, type_, len=length, prec=precision)
    return QgsField(name, type_)
