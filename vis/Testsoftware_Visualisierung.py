#!/usr/bin/env python3
# Copyright (c) 2020-2023, Matthew Broadway
# License: MIT License
# mypy: ignore_errors=True
from __future__ import annotations
from typing import Iterable, Sequence, Set, Optional, Dict

import math
import os
import time
import sys

from ezdxf.addons.xqt import QtWidgets as qw, QtCore as qc, QtGui as qg
from ezdxf.addons.xqt import Slot, QAction, Signal
from PySide6.QtWidgets import (QApplication, QFileDialog, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QSplitter, QListWidget, QCheckBox, QPlainTextEdit, QLabel, QMainWindow, 
                             QGraphicsView, QGraphicsScene, QGroupBox, QFormLayout)


import ezdxf
import ezdxf.bbox
from ezdxf import recover
from ezdxf.addons import odafc
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration
from ezdxf.addons.drawing.properties import is_dark_color, LayerProperties
from ezdxf.addons.drawing.pyqt import _get_x_scale, PyQtBackend, CorrespondingDXFEntity, CorrespondingDXFParentStack
from ezdxf.audit import Auditor
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic, DXFEntity
from ezdxf.layouts import Layout
from ezdxf.lldxf.const import DXFStructureError

#Hilfsfunktion
def _entity_attribs_string(dxf_entity: DXFGraphic, indent: str = "") -> str:
    """Gibt alle DXF-Attribute eines Entities als formatierten String zurück."""
    text = ""
    if not hasattr(dxf_entity, "dxf"):
        return ""
    for key, value in dxf_entity.dxf.all_existing_dxf_attribs().items():
        text += f"{indent}- {key}: {value}\n"
    return text

class ZoomablePyQtBackend(PyQtBackend):
    def __init__(self):
        super().__init__()
        self.dxf_handle_to_graphics_items: Dict[str, list[qw.QGraphicsItem]] = {}
        self.current_dxf_entity_handle: Optional[str] = None

    def add_item(self, item: qw.QGraphicsItem):
        super().add_item(item)
        if self.current_dxf_entity_handle:
            if self.current_dxf_entity_handle not in self.dxf_handle_to_graphics_items:
                self.dxf_handle_to_graphics_items[self.current_dxf_entity_handle] = []
            self.dxf_handle_to_graphics_items[self.current_dxf_entity_handle].append(item)

    def set_entity(self, entity: DXFGraphic, properties: LayerProperties, layout: Layout):
        self.current_dxf_entity_handle = entity.dxf.handle
        super().set_entity(entity, properties, layout)

    def finalize(self):
        super().finalize()
        self.current_dxf_entity_handle = None

    def clear_mapping(self):
        self.dxf_handle_to_graphics_items.clear()


class CADGraphicsView(qw.QGraphicsView):
    closing = Signal()

    def __init__(self, *, view_buffer: float = 0.2, zoom_per_scroll_notch: float = 0.2, loading_overlay: bool = True):
        super().__init__()
        self._zoom = 1.0
        self._default_zoom = 1.0
        self._zoom_limits = (0.5, 100)
        self._zoom_per_scroll_notch = zoom_per_scroll_notch
        self._view_buffer = view_buffer
        self._loading_overlay = loading_overlay
        self._is_loading = False
        self.setTransformationAnchor(qw.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(qw.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(qc.Qt.ScrollBarAlwaysOff)
        self.setDragMode(qw.QGraphicsView.ScrollHandDrag)
        self.setFrameShape(qw.QFrame.NoFrame)
        self.setRenderHints(qg.QPainter.Antialiasing | qg.QPainter.TextAntialiasing | qg.QPainter.SmoothPixmapTransform)
        self.setScene(qw.QGraphicsScene())
        self.scale(1, -1)

    def closeEvent(self, event: qg.QCloseEvent) -> None:
        super().closeEvent(event)
        self.closing.emit()

    def begin_loading(self):
        self._is_loading = True
        self.scene().invalidate(qc.QRectF(), qw.QGraphicsScene.AllLayers)
        QApplication.processEvents()

    def end_loading(self, new_scene: qw.QGraphicsScene):
        self.setScene(new_scene)
        self._is_loading = False
        self.buffer_scene_rect()
        self.scene().invalidate(qc.QRectF(), qw.QGraphicsScene.AllLayers)

    def buffer_scene_rect(self):
        scene = self.scene()
        r = scene.sceneRect()
        if r.isNull(): return
        bx, by = (r.width() * self._view_buffer / 2, r.height() * self._view_buffer / 2)
        scene.setSceneRect(r.adjusted(-bx, -by, bx, by))

    def fit_to_scene(self):
        self.fitInView(self.sceneRect(), qc.Qt.KeepAspectRatio)
        self._default_zoom = _get_x_scale(self.transform())
        self._zoom = 1

    def zoom_to_item_rect(self, rect: qc.QRectF):
        if not rect.isNull():
            self.fitInView(rect, qc.Qt.KeepAspectRatio)
            self._zoom = _get_x_scale(self.transform()) / self._default_zoom

    def wheelEvent(self, event: qg.QWheelEvent) -> None:
        delta_notches = event.angleDelta().y() / 120
        direction = math.copysign(1, delta_notches)
        factor = (1.0 + self._zoom_per_scroll_notch * direction) ** abs(delta_notches)
        resulting_zoom = self._zoom * factor
        if self._zoom_limits[0] < resulting_zoom < self._zoom_limits[1]:
            self.scale(factor, factor)
            self._zoom *= factor
            
    def drawForeground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:
        if self._is_loading and self._loading_overlay:
            painter.save()
            painter.fillRect(rect, qg.QColor("#aa000000"))
            painter.setWorldMatrixEnabled(False)
            r = self.viewport().rect()
            painter.setBrush(qc.Qt.NoBrush)
            painter.setPen(qc.Qt.white)
            painter.drawText(r.center(), "Loading...")
            painter.restore()

class CADGraphicsViewWithOverlay(CADGraphicsView):
    mouse_moved = Signal(qc.QPointF)
    element_hovered = Signal(object, int)
    element_clicked = Signal(str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_items: list[qw.QGraphicsItem] = []
        self._selected_index = None
        self._mark_selection = True

    def clear(self):
        self._selected_items = []
        self._selected_index = None

    def begin_loading(self):
        self.clear()
        super().begin_loading()

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        pos = self.mapToScene(event.pos())
        self.mouse_moved.emit(pos)
        selected_items = [item for item in self.scene().items(pos) if item.data(CorrespondingDXFEntity) is not None]
        if selected_items != self._selected_items:
            self._selected_items = selected_items
            self._selected_index = 0 if self._selected_items else None
            self._emit_selected()

    def mouseReleaseEvent(self, event: qg.QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == qc.Qt.LeftButton and self._selected_items:
            entity = self._selected_items[self._selected_index].data(CorrespondingDXFEntity)
            if entity:
                self.element_clicked.emit(entity.dxf.handle)

    def _emit_selected(self):
        self.element_hovered.emit(self._selected_items, self._selected_index)
        self.scene().invalidate(self.sceneRect(), qw.QGraphicsScene.ForegroundLayer)
    
    def drawForeground(self, painter: qg.QPainter, rect: qc.QRectF) -> None:
        """Zeichnet eine grüne Markierung über dem ausgewählten Element."""
        super().drawForeground(painter, rect)
        if self._selected_items and self._mark_selection:
            item = self._selected_items[self._selected_index]
            r = item.sceneTransform().mapRect(item.boundingRect())
            painter.fillRect(r, qg.QColor(0, 255, 0, 100)) # Grüne, halbtransparente Füllung

class CADWidget(qw.QWidget):
    def __init__(self, view: CADGraphicsView, config: Configuration = Configuration()):
        super().__init__()
        layout = qw.QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)
        self.setLayout(layout)
        self._view = view
        self._view.closing.connect(self.close)
        self._config = config
        self._bbox_cache = ezdxf.bbox.Cache()
        self._doc: Drawing = None
        self._render_context: RenderContext = None
        self._visible_layers: set[str] = set()
        self._current_layout: str = "Model"
        self._reset_backend()

    def set_visible_layers(self, layers: Set[str]) -> None:
        """Sets the layers that should be visible and triggers a redraw."""
        self._visible_layers = layers
        self.draw_layout(self._current_layout, reset_view=False)

    def _make_render_context(self, doc: Drawing) -> RenderContext:
        """Creates the render context and sets up the layer visibility callback."""
        # This inner function will be called by the drawing frontend
        # to decide which layers are visible.
        def update_layers_state(layers: Sequence[LayerProperties]):
            if self._visible_layers:
                # This helper function from ezdxf handles setting the state
                from ezdxf.addons.drawing.properties import set_layers_state
                set_layers_state(layers, self._visible_layers, state=True)

        render_context = RenderContext(doc)
        # We tell the context to use our function to override layer properties
        render_context.set_layer_properties_override(update_layers_state)
        return render_context

    def _reset_backend(self):
        self._backend = ZoomablePyQtBackend()
        
    @property
    def doc(self) -> Drawing:
        return self._doc

    def set_document(self, document: Drawing, *, layout: str = "Model", draw: bool = True):
        self._doc = document
        self.bbox_cache = ezdxf.bbox.Cache()
        # Use the new method to create the context with the callback
        self._render_context = self._make_render_context(document)
        self._reset_backend()
        self._visible_layers = set()
        self._current_layout = "Model"  # Ensure a default is set
        if draw:
            self.draw_layout(layout)

    
    def draw_layout(self, layout_name: str, reset_view: bool = True):
        if self._doc is None: return
        self._current_layout = layout_name
        self._view.begin_loading()
        new_scene = qw.QGraphicsScene()
        self._backend.clear_mapping()
        self._backend.set_scene(new_scene)
        
        # Update the context with the current layout before drawing
        layout = self._doc.layout(layout_name)
        self._render_context.set_current_layout(layout)
        
        try:
            # The frontend will now use the override function we set up
            Frontend(ctx=self._render_context, out=self._backend, config=self._config).draw_layout(layout)
        finally:
            self._backend.finalize()
            self._view.end_loading(new_scene)
            if reset_view:
                self._view.fit_to_scene()


class CADViewer(qw.QMainWindow):
    entity_data_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._doc: Optional[Drawing] = None
        self._cad = CADWidget(CADGraphicsViewWithOverlay())
        self._view = self._cad._view
        self.mouse_pos_label = QLabel() # Wird für die Maus-Position benötigt
        self._view.element_clicked.connect(self._on_element_clicked)
        self._view.mouse_moved.connect(self._on_mouse_moved)
        self._view.element_hovered.connect(self._on_element_hovered)

        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("CAD Viewer")
        self.resize(1600, 900)
        
        # Main container
        container = QSplitter()
        self.setCentralWidget(container)
        container.addWidget(self._cad)

        # Sidebar
        self.sidebar = QSplitter(qc.Qt.Vertical)
        container.addWidget(self.sidebar)
        container.setSizes([1200, 400])

        # Layer List
        self.layers = QListWidget()
        self.sidebar.addWidget(self.layers)

    # --- NEU: Buttons für Layer-Auswahl ---
        layer_button_widget = QWidget()
        layer_button_layout = QHBoxLayout(layer_button_widget)
        self.select_all_layers_btn = QPushButton("Alle auswählen")
        self.deselect_all_layers_btn = QPushButton("Alle abwählen")
        layer_button_layout.addWidget(self.select_all_layers_btn)
        layer_button_layout.addWidget(self.deselect_all_layers_btn)
        self.sidebar.addWidget(layer_button_widget)

        self.select_all_layers_btn.clicked.connect(self._select_all_layers)
        self.deselect_all_layers_btn.clicked.connect(self._deselect_all_layers)

        # Bottom container for Info and Details
        bottom_container = QWidget()
        bottom_layout = QVBoxLayout(bottom_container)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar.addWidget(bottom_container)

        # Info Box
        self.selected_info = QPlainTextEdit()
        self.selected_info.setReadOnly(True)
        bottom_layout.addWidget(self.selected_info)
        bottom_layout.addWidget(self.mouse_pos_label)

        # Detail View for Editing
        details_group = QGroupBox("Detailansicht der Auswahl")
        details_layout = QFormLayout(details_group)
        self.detail_id = QLineEdit()
        self.detail_id.setReadOnly(True)
        self.detail_entity_type = QLineEdit()
        self.detail_entity_type.setReadOnly(True)
        self.detail_start_z = QLineEdit()
        self.detail_end_z = QLineEdit()
        self.detail_center_z = QLineEdit()
        self.detail_assoc_text = QLineEdit()
        details_layout.addRow("ID:", self.detail_id)
        details_layout.addRow("EntityType:", self.detail_entity_type)
        details_layout.addRow("StartZ:", self.detail_start_z)
        details_layout.addRow("EndZ:", self.detail_end_z)
        details_layout.addRow("CenterZ:", self.detail_center_z)
        details_layout.addRow("Associated_Text:", self.detail_assoc_text)
        self.apply_changes_button = QPushButton("Änderungen übernehmen")
        self.apply_changes_button.clicked.connect(self._apply_detail_changes)
        details_layout.addRow(self.apply_changes_button)
        bottom_layout.addWidget(details_group)

    @Slot(str)
    def _on_element_clicked(self, dxf_handle: str):
        # This signal is now connected in the main_window to trigger actions there
        pass

    @Slot(dict)
    def display_entity_data(self, data_row: dict):
        self.detail_id.setText(str(data_row.get('ID', '')))
        self.detail_entity_type.setText(str(data_row.get('EntityType', '')))
        self.detail_start_z.setText(str(data_row.get('StartZ', '')))
        self.detail_end_z.setText(str(data_row.get('EndZ', '')))
        self.detail_center_z.setText(str(data_row.get('CenterZ', '')))
        self.detail_assoc_text.setText(str(data_row.get('Associated_Text', '')))
        
    @Slot()
    def _apply_detail_changes(self):
        if not self.detail_id.text():
            QMessageBox.warning(self, "Keine Auswahl", "Es ist kein Element zur Bearbeitung ausgewählt.")
            return
        updated_data = {
            'ID': self.detail_id.text(),
            'StartZ': self.detail_start_z.text(),
            'EndZ': self.detail_end_z.text(),
            'CenterZ': self.detail_center_z.text(),
            'Associated_Text': self.detail_assoc_text.text(),
        }
        self.entity_data_updated.emit(updated_data)

    @Slot(object, int)
    def _on_element_hovered(self, elements: list[qw.QGraphicsItem], index: int):
        """Wird aufgerufen, wenn die Maus über einem Element schwebt und füllt das Info-Feld."""
        if not elements:
            text = "Kein Element ausgewählt \n \n Bitte Beachten Sie: \n 3D Geometrien wie Solid oder Surface " \
            "werden in der Ansicht nicht unterstützt und " \
            "können möglicherweise nicht korrekt angezeigt werden."
        else:
            element = elements[index]
            dxf_entity: Optional[DXFGraphic] = element.data(CorrespondingDXFEntity)
            if dxf_entity is None:
                text = "Keine Daten"
            else:
                text = f"Ausgewähltes Element: {dxf_entity}\n"
                text += f"Layer: {getattr(dxf_entity.dxf, 'layer', '')}\n\nDXF Attribute:\n"
                text += _entity_attribs_string(dxf_entity) # Verwendet die neue Helper-Funktion

                dxf_parent_stack = element.data(CorrespondingDXFParentStack)
                if dxf_parent_stack:
                    text += "\nEltern-Elemente (in Block):\n"
                    for entity in reversed(dxf_parent_stack):
                        text += f"- {entity}\n"
                        text += _entity_attribs_string(entity, indent="    ")
        self.selected_info.setPlainText(text)

    @Slot(qc.QPointF)
    def _on_mouse_moved(self, mouse_pos: qc.QPointF):
        """Aktualisiert die Anzeige der Mauskoordinaten."""
        self.mouse_pos_label.setText(f"Maus Position: {mouse_pos.x():.4f}, {mouse_pos.y():.4f}")


    def _entity_attribs_string(dxf_entity: DXFGraphic, indent: str = "") -> str:
        text = ""
        for key, value in dxf_entity.dxf.all_existing_dxf_attribs().items():
            text += f"{indent}- {key}: {value}\n"
        return text
    
    @Slot()
    def _select_all_layers(self):
        """Selects all layer checkboxes efficiently and triggers a single redraw."""
        # 1. Temporarily disable signals for each checkbox to prevent multiple redraws
        for i in range(self.layers.count()):
            checkbox = self.layers.itemWidget(self.layers.item(i))
            checkbox.blockSignals(True)

        # 2. Now, change the state of all checkboxes
        for i in range(self.layers.count()):
            checkbox = self.layers.itemWidget(self.layers.item(i))
            checkbox.setCheckState(qc.Qt.Checked)

        # 3. Re-enable signals for future user clicks
        for i in range(self.layers.count()):
            checkbox = self.layers.itemWidget(self.layers.item(i))
            checkbox.blockSignals(False)

        # 4. Manually trigger a single update at the very end
        self._layers_updated()

    @Slot()
    def _deselect_all_layers(self):
        """Deselects all layer checkboxes efficiently and triggers a single redraw."""
        # 1. Temporarily disable signals for each checkbox
        for i in range(self.layers.count()):
            checkbox = self.layers.itemWidget(self.layers.item(i))
            checkbox.blockSignals(True)

        # 2. Change the state of all checkboxes
        for i in range(self.layers.count()):
            checkbox = self.layers.itemWidget(self.layers.item(i))
            checkbox.setCheckState(qc.Qt.Unchecked)

        # 3. Re-enable signals
        for i in range(self.layers.count()):
            checkbox = self.layers.itemWidget(self.layers.item(i))
            checkbox.blockSignals(False)

        # 4. Manually trigger a single update at the very end
        self._layers_updated()

    def load_document_from_main_app(self, document: Drawing, layer_list: list[str]):
        self.set_document(document, layer_list)


    def set_document(self, document: Drawing, layer_list: list[str] | None = None):
        self._doc = document
        self._cad.set_document(document, draw=True)
        self.setWindowTitle("CAD Viewer - " + str(document.filename))
        self._populate_layer_list(layer_list)

    def _populate_layer_list(self, external_layers: list[str] | None = None):
        self.layers.blockSignals(True)
        self.layers.clear()
        layers_to_display = sorted(external_layers) if external_layers is not None else []
        for name in layers_to_display:
            item = qw.QListWidgetItem()
            self.layers.addItem(item)
            checkbox = qw.QCheckBox(name)
            checkbox.setCheckState(qc.Qt.Checked)
            checkbox.stateChanged.connect(self._layers_updated)
            self.layers.setItemWidget(item, checkbox)
        self.layers.blockSignals(False)
        self._layers_updated()

    @Slot()
    def _entity_attribs_string(entity, indent="  "):
        """Gibt alle DXF-Attribute eines Entities als formatierten String zurück."""
        if not hasattr(entity, "dxf"):
            return ""
        lines = []
        for key in entity.dxf.all_existing_dxf_attribs():
            value = getattr(entity.dxf, key, None)
            lines.append(f"{indent}{key}: {value}")
        return "\n".join(lines)
    
    @Slot()
    def _layers_updated(self):
        """
        Collects the names of all checked layers and tells the CADWidget 
        to update its view with this set of visible layers.
        """
        visible_layers = {
            self.layers.itemWidget(self.layers.item(i)).text()
            for i in range(self.layers.count())
            if self.layers.itemWidget(self.layers.item(i)).checkState() == qc.Qt.Checked
        }
        self._cad.set_visible_layers(visible_layers)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = CADViewer()
    # In standalone mode, we need a way to load a file
    file_path, _ = QFileDialog.getOpenFileName(None, "Select DXF File", "", "DXF Files (*.dxf)")
    if file_path:
        doc = ezdxf.readfile(file_path)
        viewer.load_document_from_main_app(doc, [layer.dxf.name for layer in doc.layers])
        viewer.show()
        sys.exit(app.exec())