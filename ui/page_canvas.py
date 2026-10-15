from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsView


class PageCanvas(QGraphicsView):
    """Page preview with source-coordinate region selection and direct editing."""

    region_selected = Signal(int)
    region_created = Signal(object)
    region_geometry_changed = Signal(int, object)
    draw_mode_changed = Signal(bool)

    def __init__(self, scene):
        super().__init__(scene)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.display_size = (1, 1)
        self.source_size = (1, 1)
        self.regions: list[dict] = []
        self.selected_index = -1
        self.draw_mode = False
        self._draft_start: QPointF | None = None
        self._draft_rect: QRectF | None = None
        self._drag_index = -1
        self._drag_kind = ""
        self._drag_start = QPointF()
        self._drag_original: QRectF | None = None
        self._drag_preview: QRectF | None = None
        self._pan_start = None
        self._pan_scroll = (0, 0)

    def set_page_geometry(self, display_size, source_size, regions, selected_index=-1):
        self.display_size = tuple(display_size)
        self.source_size = tuple(source_size)
        self.regions = regions
        self.selected_index = selected_index
        self._drag_preview = None
        self.viewport().update()

    def set_draw_mode(self, enabled: bool):
        self.draw_mode = enabled
        self._draft_start = None
        self._draft_rect = None
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.draw_mode_changed.emit(enabled)
        self.viewport().update()

    def _display_rect(self, index: int) -> QRectF:
        x, y, width, height = self.regions[index].get("bbox", (0, 0, 0, 0))
        sx = self.display_size[0] / max(self.source_size[0], 1)
        sy = self.display_size[1] / max(self.source_size[1], 1)
        return QRectF(x * sx, y * sy, width * sx, height * sy)

    def _to_source_box(self, rect: QRectF) -> list[int]:
        rect = rect.normalized()
        sx = self.source_size[0] / max(self.display_size[0], 1)
        sy = self.source_size[1] / max(self.display_size[1], 1)
        x0 = max(0, min(self.source_size[0] - 1, round(rect.left() * sx)))
        y0 = max(0, min(self.source_size[1] - 1, round(rect.top() * sy)))
        x1 = max(x0 + 1, min(self.source_size[0], round(rect.right() * sx)))
        y1 = max(y0 + 1, min(self.source_size[1], round(rect.bottom() * sy)))
        return [x0, y0, x1 - x0, y1 - y0]

    def _hit_region(self, point: QPointF) -> int:
        for index in range(len(self.regions) - 1, -1, -1):
            if self._display_rect(index).contains(point):
                return index
        return -1

    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for index, region in enumerate(self.regions):
            box = self._drag_preview if index == self._drag_index and self._drag_preview is not None else self._display_rect(index)
            if region.get("protected"):
                color = QColor("#c084fc")
            elif region.get("confidence", 1) >= .7:
                color = QColor("#32d583")
            elif region.get("confidence", 1) >= .4:
                color = QColor("#fdb022")
            else:
                color = QColor("#ff6b6b")
            pen = QPen(color, 3 if index == self.selected_index else 2)
            if region.get("locked"):
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
            if index == self.selected_index:
                painter.setPen(QPen(QColor("#ffffff"), 1))
                painter.setBrush(color)
                painter.drawRect(QRectF(box.right() - 6, box.bottom() - 6, 10, 10))
        if self._draft_rect is not None:
            painter.setPen(QPen(QColor("#54b8ff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(84, 184, 255, 40))
            painter.drawRect(self._draft_rect)
        painter.restore()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if .15 < self.transform().m11() * factor < 8:
            self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_start = event.position().toPoint()
            self._pan_scroll = (self.horizontalScrollBar().value(), self.verticalScrollBar().value())
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        point = self.mapToScene(event.position().toPoint())
        if self.draw_mode:
            self._draft_start = point
            self._draft_rect = QRectF(point, point)
            self.viewport().update()
            event.accept()
            return

        index = self._hit_region(point)
        self.region_selected.emit(index)
        if index >= 0 and not self.regions[index].get("locked"):
            box = self._display_rect(index)
            self._drag_index = index
            self._drag_start = point
            self._drag_original = box
            handle = QPointF(box.right(), box.bottom())
            self._drag_kind = "resize" if abs(point.x() - handle.x()) < 12 and abs(point.y() - handle.y()) < 12 else "move"
        else:
            self._drag_index = -1
        event.accept()

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        if self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self.horizontalScrollBar().setValue(self._pan_scroll[0] - delta.x())
            self.verticalScrollBar().setValue(self._pan_scroll[1] - delta.y())
        elif self._draft_start is not None:
            self._draft_rect = QRectF(self._draft_start, point).normalized()
            self.viewport().update()
        elif self._drag_index >= 0 and self._drag_original is not None:
            delta = point - self._drag_start
            box = QRectF(self._drag_original)
            if self._drag_kind == "move":
                box.translate(delta)
                box.moveTo(
                    max(0, min(self.display_size[0] - box.width(), box.left())),
                    max(0, min(self.display_size[1] - box.height(), box.top())),
                )
            else:
                box.setRight(max(box.left() + 12, min(self.display_size[0], point.x())))
                box.setBottom(max(box.top() + 12, min(self.display_size[1], point.y())))
            self._drag_preview = box
            self.viewport().update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) and self._pan_start is not None:
            self._pan_start = None
            self.viewport().setCursor(Qt.CursorShape.CrossCursor if self.draw_mode else Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._draft_start is not None:
            box = self._draft_rect
            self._draft_start = None
            self._draft_rect = None
            self.set_draw_mode(False)
            if box and box.width() >= 10 and box.height() >= 8:
                self.region_created.emit(self._to_source_box(box))
            self.viewport().update()
        elif self._drag_index >= 0 and self._drag_preview is not None:
            index = self._drag_index
            new_box = self._to_source_box(self._drag_preview)
            self.region_geometry_changed.emit(index, new_box)
        self._drag_index = -1
        self._drag_kind = ""
        self._drag_original = None
        self._drag_preview = None
        self.viewport().update()
        event.accept()
