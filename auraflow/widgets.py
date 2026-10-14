"""Native Qt painting: no remote assets, browser, or image uploads."""
import math
from PySide6.QtCore import Qt, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QIcon, QPixmap, QPainterPath, QLinearGradient
from PySide6.QtWidgets import QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QProgressBar, QPushButton
from PySide6.QtSvg import QSvgRenderer
from .gestures import CONNECTIONS

GREEN = "#69e3ff"
PATHS = {
    "Audio": '<path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
    "Display": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    "Media": '<path d="M9 18V5l11-2v13M9 9l11-2"/><ellipse cx="6" cy="18" rx="3" ry="2.5"/><ellipse cx="17" cy="16" rx="3" ry="2.5"/>',
    "Slides": '<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M12 16v5m-4 0 4-4 4 4M8 8h8m-8 4h5"/>',
    "Pointer": '<path d="m5 3 14 9-7 2-3 7z"/>',
    "Settings": '<circle cx="12" cy="12" r="3"/><path d="m10 3 4 0 1 3 3 1 3 2-1 4-2 1-1 4-3 3-4-1-1-2-4-1-2-3 1-4 2-1 1-4z"/>',
    "camera": '<rect x="2" y="6" width="14" height="12" rx="3"/><path d="m16 10 6-4v12l-6-4"/>',
    "play": '<path d="m8 4 12 8-12 8z"/>',
    "pause": '<path d="M8 5v14M16 5v14"/>',
    "next": '<path d="m4 5 10 7-10 7zM19 5v14"/>',
    "previous": '<path d="m20 5-10 7 10 7zM5 5v14"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
    "hand": '<path d="M7 12V5a2 2 0 0 1 4 0v6-8a2 2 0 0 1 4 0v8-5a2 2 0 0 1 4 0v7-3a2 2 0 0 1 4 0v5c0 6-4 8-9 8-3 0-5-2-7-5L3 13a2 2 0 0 1 3-2z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-11v1"/>',
}


def icon(name, color="#a8b2b2", size=22):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
           f'fill="none" stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
           + PATHS.get(name, PATHS["hand"]) + '</svg>')
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def label(text, role="", wrap=False):
    result = QLabel(text)
    result.setProperty("role", role)
    result.setWordWrap(wrap)
    result.setTextFormat(Qt.TextFormat.PlainText)
    return result


def button(text, symbol=None, role=""):
    result = QPushButton(text)
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    result.setProperty("role", role)
    if symbol:
        result.setIcon(icon(symbol, "#17201a" if role == "primary" else "#d1d9d6"))
        result.setIconSize(QSize(18, 18))
    return result


class Card(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(22, 20, 22, 20)
        self.box.setSpacing(12)


class LevelMeter(QWidget):
    def __init__(self,title):
        super().__init__()
        self.value=None; self.muted=False
        self.setObjectName('levelMeter')
        self.setStyleSheet('QWidget#levelMeter { background:transparent; }')
        box=QVBoxLayout(self); box.setContentsMargins(0,0,0,0); box.setSpacing(8)
        row=QHBoxLayout(); row.addWidget(label(title)); row.addStretch()
        self.readout=label('—','muted'); row.addWidget(self.readout); box.addLayout(row)
        self.track=QProgressBar(); self.track.setRange(0,100); self.track.setValue(0); self.track.setTextVisible(False)
        box.addWidget(self.track)

    def set_level(self,value):
        self.value=max(0,min(100,round(value))); self.refresh()

    def set_muted(self,muted):
        self.muted=muted; self.refresh()

    def refresh(self):
        self.readout.setText('Muted' if self.muted else '—' if self.value is None else str(self.value)+'%')
        self.track.setValue(self.value if self.value is not None else 0)


class VisionView(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.points = []
        self.hands = []
        self.demo = False
        self.show_status = True
        self.status = "A little motion. A lot of control."
        self.progress = 0
        self.hand = ""
        self.setMinimumSize(380, 300)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        clip = QPainterPath()
        clip.addRoundedRect(bounds, 14, 14)
        p.setClipPath(clip)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#102337"))
        gradient.setColorAt(1, QColor("#08121f"))
        p.fillRect(self.rect(), gradient)
        view = QRectF(0, 0, self.width(), self.height())
        if self.image is not None and not self.demo:
            size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            view = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())
            p.drawImage(view, self.image)
        else:
            p.setPen(QPen(QColor("#1c344b"), 1))
            for x in range(0, self.width(), 28):
                for y in range(0, self.height(), 28):
                    p.drawPoint(x, y)
            # Synthetic landmark illustrations preserve the camera's 4:3 geometry.
            factor = min(self.width() / 640, (self.height() - 30) / 480)
            view = QRectF((self.width() - 640 * factor) / 2, 0, 640 * factor, 480 * factor)
        for points in (self.hands or [self.points]):
            pts = [QPointF(view.x() + x * view.width(), view.y() + y * view.height()) for x, y in points]
            if pts:
                for a, b in CONNECTIONS:
                    p.setPen(QPen(QColor("#164559"), 10 if self.demo else 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(pts[a], pts[b])
                    p.setPen(QPen(QColor("#69e3ff"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(pts[a], pts[b])
                p.setPen(Qt.PenStyle.NoPen)
                for i, pt in enumerate(pts):
                    p.setBrush(QColor(GREEN if i in (4, 8, 20) else "#c0edff"))
                    p.drawEllipse(pt, 5 if i in (4, 8, 20) else 3, 5 if i in (4, 8, 20) else 3)
                p.setPen(QPen(QColor(GREEN), 2, Qt.PenStyle.DashLine))
                p.drawLine(pts[4], pts[8])
        if not any(self.hands or [self.points]) and self.image is None:
            renderer = QSvgRenderer(('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#69e3ff" stroke-width="1" stroke-linecap="round" stroke-linejoin="round">' + PATHS['hand'] + '</svg>').encode())
            renderer.render(p, QRectF(self.width() / 2 - 36, self.height() / 2 - 74, 72, 72))
            p.setFont(QFont("Segoe UI", 17, QFont.Weight.DemiBold))
            p.setPen(QColor("#e1e9dd"))
            p.drawText(QRectF(15, self.height() / 2 + 14, self.width() - 30, 35), Qt.AlignmentFlag.AlignCenter, "Opening camera…")
            p.setFont(QFont("Segoe UI", 10))
            p.setPen(QColor("#9ba99c"))
            p.drawText(QRectF(20, self.height() / 2 + 51, self.width() - 40, 50), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap,
                       "Camera opens automatically. Keep your hands in view.")
        # Viewfinder corners and honest source labels.
        p.setPen(QPen(QColor("#47849e"), 1.5))
        for x, y, sx, sy in [(18, 18, 1, 1), (self.width()-18, 18, -1, 1),
                             (18, self.height()-18, 1, -1), (self.width()-18, self.height()-18, -1, -1)]:
            p.drawLine(x, y, x + sx * 14, y)
            p.drawLine(x, y, x, y + sy * 14)
        p.setPen(QColor("#8ba3b7"))
        p.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        p.drawText(32, 36, "DEMO · SYNTHETIC HANDS" if self.demo else ("LOCAL CAMERA" if self.image is not None else "CAMERA OFF"))
        if self.show_status:
            p.setBrush(QColor(12, 19, 17, 225))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(QRectF(28, self.height() - 67, self.width() - 56, 42), 10, 10)
            p.setBrush(QColor(GREEN))
            p.drawEllipse(QPointF(46, self.height() - 46), 3, 3)
            p.setPen(QColor("#d9e3d3"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(60, self.height() - 67, self.width() - 118, 42), Qt.AlignmentFlag.AlignVCenter, self.status)
        if 0 < self.progress <= 1:
            p.setPen(QPen(QColor(GREEN), 2))
            p.drawLine(QPointF(40, self.height() - 26), QPointF(40 + (self.width() - 80) * self.progress, self.height() - 26))
        p.end()
