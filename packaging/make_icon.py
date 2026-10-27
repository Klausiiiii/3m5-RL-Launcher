"""Render assets/icon.svg to icon.ico (Windows exe icon). Re-run after changing the SVG."""
import os
import sys

from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

here = os.path.dirname(os.path.abspath(__file__))
svg = os.path.join(here, '..', 'src', 'rl_launcher', 'assets', 'icon.svg')
app = QGuiApplication(sys.argv[:1])
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(0)
p = QPainter(img)
QSvgRenderer(svg).render(p)
p.end()
for name in ('icon.ico',):
    assert img.save(os.path.join(here, name)), name
