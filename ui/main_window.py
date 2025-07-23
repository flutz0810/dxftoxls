from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton,
                             QTableView, QFileDialog, QMessageBox, QGroupBox, QLabel,
                             QHBoxLayout, QCheckBox, QScrollArea, QSplitter, QDialog, QFormLayout, QDoubleSpinBox, QLineEdit)
from PySide6.QtCore import Slot, QTimer
import time
import pandas as pd
# Correct import for DXF
from data_handler.dxf_parser import DXFParser
from data_handler.dxf_exporter import export_dataframe_to_dxf
from geometry_store.geometry_manager import GeometryManager 
from ui.pandas_table_model import PandasTableModel 
from PySide6.QtCore import Qt
import subprocess 
import tempfile   
import os
import numpy as np 
import traceback
from ui.analysis_dialog import AnalysisDialog
from vis.Testsoftware_Visualisierung import CADViewer
# heightassignement is imported dynamically at runtime

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 1. Initialization of all member variables
        self.layer_checkboxes = []
        self.all_layer_names = []
        self.model = None
        self.text_model = None
        self.table_view = None
        self.text_table_view = None
        self.geometry_manager = GeometryManager()
        self.text_data_frame = pd.DataFrame() # text_data_frame instead of full_data_frame
        self.visualization_window = None 
        self.dxf_parser = DXFParser()


        self.setWindowTitle("DXF Data Viewer")

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        # Main layout is now horizontal
        main_layout = QHBoxLayout(main_widget)

        # --- Left column for controls (buttons and layer filter) ---
        left_column_widget = QWidget()
        left_column_layout = QVBoxLayout(left_column_widget)
        left_column_widget.setFixedWidth(300)
        main_layout.addWidget(left_column_widget)

        # Button group
        button_group = QGroupBox("Actions")
        button_layout = QVBoxLayout(button_group) # Vertical layout for buttons

        self.open_button = QPushButton("Open DXF/DWG file")
        self.open_button.setToolTip("""Opens a DXF or DWG file.
Requires the ODAFileConverter for DWG files.""")
        self.open_button.clicked.connect(self.open_file_dialog)
        button_layout.addWidget(self.open_button)

        self.analysis_button = QPushButton("Perform analysis")
        self.analysis_button.clicked.connect(self.open_analysis_dialog)
        button_layout.addWidget(self.analysis_button)

        self.z_analysis_button = QPushButton("Z-coordinate analysis")
        self.z_analysis_button.clicked.connect(self.open_z_analysis)
        self.z_analysis_button.setEnabled(False)  # Disabled until after text analysis
        self.z_analysis_button.setToolTip("Starts Z-height assignment based on the analyzed data")
        button_layout.addWidget(self.z_analysis_button)

        # --- Höhen-Schlüsselwörter Eingabefeld ---
        keywords_group = QGroupBox("Höhen-Schlüsselwörter")
        keywords_layout = QVBoxLayout(keywords_group)
        
        keywords_label = QLabel("Schlüsselwörter (komma-getrennt):")
        keywords_label.setToolTip("Geben Sie die Schlüsselwörter ein, nach denen in den Texten gesucht werden soll.\nBeispiel: OK,UK,KD,SOK,SUK")
        keywords_layout.addWidget(keywords_label)
        
        self.keywords_input = QLineEdit()
        self.keywords_input.setText("OK,UK,KD")  # Standard-Werte
        self.keywords_input.setToolTip("Standard: OK,UK,KD\nBeispiele: SOK,SUK,OH,UH")
        self.keywords_input.setPlaceholderText("z.B. OK,UK,KD,SOK,SUK")
        keywords_layout.addWidget(self.keywords_input)
        
        left_column_layout.addWidget(keywords_group)

        self.export_dxf_button = QPushButton("Export as DXF")
        self.export_dxf_button.clicked.connect(self.export_to_dxf)
        button_layout.addWidget(self.export_dxf_button)

        self.export_xlsx_button = QPushButton("Export as XLSX")
        self.export_xlsx_button.clicked.connect(self.export_to_xlsx)
        self.export_xlsx_button.setEnabled(False)
        button_layout.addWidget(self.export_xlsx_button)

        self.export_csv_button = QPushButton("Export as CSV")
        self.export_csv_button.clicked.connect(self.export_to_csv)
        self.export_csv_button.setEnabled(False)
        button_layout.addWidget(self.export_csv_button)

        self.visualization_button = QPushButton("Open visualization")
        self.visualization_button.clicked.connect(self.open_visualization)
        button_layout.addWidget(self.visualization_button)

        # --- NEW: Synchronize Z-values Button ---
        self.sync_z_button = QPushButton("Synchronize Z-values")
        self.sync_z_button.setToolTip("Synchronize Z-values for lines/arcs with identical X/Y coordinates in the filtered table.")
        self.sync_z_button.clicked.connect(self.synchronize_z_values_for_filtered_table)
        button_layout.addWidget(self.sync_z_button)
        # --- END NEW ---

        button_layout.addStretch()
        left_column_layout.addWidget(button_group)

        # --- Layer filter group ---
        layer_filter_group = QGroupBox("Layer filter")
        layer_filter_v_layout = QVBoxLayout(layer_filter_group)

        # Buttons for layer selection
        layer_buttons_layout = QHBoxLayout()
        self.select_all_layers_button = QPushButton("Select all")
        self.select_all_layers_button.clicked.connect(self.select_all_layers)
        layer_buttons_layout.addWidget(self.select_all_layers_button)

        self.deselect_all_button = QPushButton("Deselect all")
        self.deselect_all_button.clicked.connect(self.deselect_all_layers)
        layer_buttons_layout.addWidget(self.deselect_all_button)
        layer_filter_v_layout.addLayout(layer_buttons_layout)

        # Scroll area for layer checkboxes
        self.layer_filter_scroll_area = QScrollArea()
        self.layer_filter_scroll_area.setWidgetResizable(True)
        self.layer_filter_scroll_content = QWidget()
        self.layer_filter_checkboxes_layout = QVBoxLayout(self.layer_filter_scroll_content)
        self.layer_filter_scroll_area.setWidget(self.layer_filter_scroll_content)
        layer_filter_v_layout.addWidget(self.layer_filter_scroll_area)

        left_column_layout.addWidget(layer_filter_group)

        self.analysis_button.setEnabled(False)
        self.z_analysis_button.setEnabled(False)
        self.export_dxf_button.setEnabled(False)
        self.export_xlsx_button.setEnabled(False)
        self.export_csv_button.setEnabled(False)
        self.visualization_button.setEnabled(False)

        # --- Right column with splitter for the tables ---
        right_splitter = QSplitter(Qt.Vertical)
        self.table_view = QTableView()      # Upper table for geometry
        self.text_table_view = QTableView() # Lower table for texts
        
        right_splitter.addWidget(self.table_view)
        right_splitter.addWidget(self.text_table_view)
        right_splitter.setSizes([400, 200]) # Initial sizes
        
        main_layout.addWidget(right_splitter, 1) # Add splitter to main layout (takes more space)


        # 3. Initialize and assign models
        self.model = PandasTableModel(pd.DataFrame())
        self.table_view.setModel(self.model)

          
        # IMPORTANT signal connection for editing
        self.model.rowDataModified.connect(self.on_geometry_row_modified)
        
        self.text_model = PandasTableModel(pd.DataFrame())
        self.text_table_view.setModel(self.text_model)

        # 4. Initial population of the filters
        self._populate_layer_filters()

    def open_file_dialog(self):
        """Opens a file dialog to select a DXF or DWG file."""
        
        # IMPORTANT: Adjust path to ODA File Converter!
        # Example for macOS. For Windows, it would be something like "C:/Program Files/ODA/ODAFileConverter/ODAFileConverter.exe"
        oda_converter_path = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\ODA\ODA File Converter 25.11.0.lnk"

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open file",
            "",
            "CAD files (*.dxf *.dwg);;DXF files (*.dxf);;DWG files (*.dwg);;All files (*)"
        )

        if not file_path:
            return # User canceled the dialog

        # Check if a DWG file was selected
        if file_path.lower().endswith('.dwg'):
            # Check if the converter exists
            if not os.path.exists(oda_converter_path):
                QMessageBox.critical(self, "Error", f"ODA File Converter not found at:\n{oda_converter_path}\n\nPlease adjust the path in the code.")
                return

            print(f"Converting DWG: {file_path}")
            # Create temporary directory for output DXF
            with tempfile.TemporaryDirectory() as temp_dir:
                # Build command line for the converter
                # Format: ODAFileConverter <InputFolder> <OutputFolder> <OutputType> <OutputVersion> <Recurse> <Audit>
                # We use the input folder and the temporary folder
                input_folder = os.path.dirname(file_path)
                command = [
                    oda_converter_path,
                    input_folder,
                    temp_dir,
                    "ACAD2018",       # Output format
                    "DXF",
                    "0",         # Not recursive
                    "1"          # Audit (error checking)
                ]

                try:
                    # Run the converter and wait for completion
                    process = subprocess.run(command, check=True, capture_output=True, text=True, timeout=60)
                    print("ODA Converter Output:", process.stdout)
                    
                    # The converter renames the file like the original, just with .dxf
                    original_filename = os.path.basename(file_path)
                    converted_dxf_name = os.path.splitext(original_filename)[0] + ".dxf"
                    final_dxf_path = os.path.join(temp_dir, converted_dxf_name)

                    if os.path.exists(final_dxf_path):
                        # Pass the converted DXF file to the load method
                        self.load_dxf_data(final_dxf_path)
                    else:
                        QMessageBox.critical(self, "Conversion error", f"The converted DXF file was not found:\n{final_dxf_path}")

                except subprocess.CalledProcessError as e:
                    QMessageBox.critical(self, "Conversion error", f"Error executing ODA File Converter:\n{e.stderr}")
                except subprocess.TimeoutExpired:
                    QMessageBox.critical(self, "Conversion error", "The conversion took too long (timeout).")
        else:
            # If it's a DXF file, load directly
            self.load_dxf_data(file_path)

    def load_dxf_data(self, file_path: str):
        """Loads data from a DXF file and updates the UI."""
        try:
            geometry_df, text_df, all_layers = self.dxf_parser.load_dxf(file_path)
            if geometry_df is None:
                QMessageBox.critical(self, "Load error", "The DXF file could not be loaded. See console for details.")
                return

            self.text_data_frame = text_df
            self.all_layer_names = all_layers if all_layers is not None else []

            # Update GeometryManager with separate data and the complete layer list
            self.geometry_manager.process_dxf_data_frame(geometry_df, text_df, self.all_layer_names)
            self._populate_layer_filters()
            
            # Update models for the table views
            self.model.setDataframe(geometry_df)
            self.text_model.setDataframe(text_df)
            
            # Apply filter to update initial view
            self.apply_layer_filter() 

            print(f"Data from {file_path} successfully loaded and UI updated.")

            # Reset buttons as new data has been loaded
            self.analysis_button.setEnabled(True)
            self.z_analysis_button.setEnabled(False)
                
            self.export_dxf_button.setEnabled(False)
            self.export_xlsx_button.setEnabled(True)
            self.export_csv_button.setEnabled(True)
            self.visualization_button.setEnabled(False)

        except Exception as e:
            QMessageBox.critical(self, "Processing error", f"An error occurred while processing the data:\n{e}")
            # Reset UI
            self.text_data_frame = pd.DataFrame()
            self.all_layer_names = []
            self.geometry_manager.process_dxf_data_frame(pd.DataFrame(), pd.DataFrame(), [])
            self._populate_layer_filters()
            self.model.setDataframe(pd.DataFrame())

    def open_analysis_dialog(self):
        """Opens the dialog for geometry-text analysis - ONLY with filtered data."""
        if not self.geometry_manager.has_data():
            QMessageBox.warning(self, "No data", "No data loaded.")
            return

        # IMPORTANT: Use only the currently filtered layers
        selected_layers = self.get_selected_layers()
        
        if not selected_layers:
            QMessageBox.warning(self, "No layers selected", 
                              "Please select at least one layer for the analysis.")
            return

        # Get ONLY the filtered data from the GeometryManager
        geo_df = self.geometry_manager.get_filtered_data(selected_layers=selected_layers)
        
        # Also filter texts by the selected layers
        text_df = self.geometry_manager.get_text_data()
        if not text_df.empty and 'Layer' in text_df.columns:
            text_df = text_df[text_df['Layer'].isin(selected_layers)]
        
        if geo_df.empty:
            QMessageBox.warning(self, "No geometry", 
                              f"The selected layers contain no geometry.")
            return

        # Open the analysis dialog with the filtered data
        dialog = AnalysisDialog(geo_df, text_df, self)
        dialog.exec()

    def _populate_layer_filters(self):
        """Updates the layer filter checkboxes based on ALL layers of the DXF file."""
        # 1. Clear old layout
        self._clear_layout(self.layer_filter_checkboxes_layout)
        self.layer_checkboxes.clear()

        # 2. Create layer checkboxes based on the complete list
        if not self.all_layer_names:
            self.layer_filter_checkboxes_layout.addWidget(QLabel("No layers found."))
            return

        # Set of layers that actually contain geometry
        layers_with_geometry = set(self.geometry_manager.get_unique_layers())

        for layer_name in sorted(self.all_layer_names, key=str.lower):
            checkbox = QCheckBox(layer_name)
            
            # Check if the layer contains geometry
            if layer_name in layers_with_geometry:
                checkbox.setChecked(True) # Active by default
                checkbox.setStyleSheet("font-weight: bold;")
            else:
                checkbox.setChecked(False) # Inactive by default
                checkbox.setStyleSheet("color: gray;")

            checkbox.stateChanged.connect(self.apply_layer_filter)
            self.layer_filter_checkboxes_layout.addWidget(checkbox)
            self.layer_checkboxes.append(checkbox)
        
        self.layer_filter_checkboxes_layout.addStretch()

    def _clear_layout(self, layout):
        """Helper function to remove all widgets from a layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    # If it's a nested layout
                    self._clear_layout(item.layout())

    def export_to_xlsx(self):
        """Exports the currently displayed data in the main table to an XLSX file."""
        if self.model is None or self.model.rowCount() == 0:
            QMessageBox.information(self, "Export not possible", "No data available for export.")
            return

        if not self.geometry_manager.analysis_results_applied:
            QMessageBox.warning(self, "Export not possible", "Please perform the analysis first and apply the results to the main table.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export current table view as XLSX",
            "",
            "Excel files (*.xlsx);;All files (*)"
        )

        if file_path:
            if not file_path.lower().endswith('.xlsx'):
                file_path += '.xlsx'
            
            try:
                # Get the DataFrame directly from the model
                current_df = self.model.get_data_frame()
                
                # Export directly - Pandas can handle most data types
                current_df.to_excel(file_path, index=False, engine='openpyxl')
                
                QMessageBox.information(self, "Export successful", 
                                      f"The current view was successfully exported to\n{file_path}\n.")
                                      
            except Exception as e:
                error_msg = f"An error occurred while exporting the XLSX file:\n{str(e)}"
                QMessageBox.critical(self, "Export error", error_msg)

    def export_to_dxf(self):
        """Exports the currently filtered and processed data."""
        if self.model is None or self.model.rowCount() == 0:
            QMessageBox.information(self, "Export not possible", "No data available for export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export filtered data as DXF",
            "",
            "DXF files (*.dxf);;All files (*)"
        )

        if file_path:
            if not file_path.lower().endswith('.dxf'):
                file_path += '.dxf'
            
            # Export the currently displayed (filtered) data
            current_df = self.model.get_data_frame()
            
            selected_layers = self.get_selected_layers()
            layer_info = f" (Layer: {', '.join(selected_layers)})" if selected_layers else ""
            
            success, message = export_dataframe_to_dxf(file_path, current_df)

            if success:
                QMessageBox.information(self, "Export successful", 
                                      f"{message}{layer_info}")
            else:
                QMessageBox.critical(self, "Export error", message)

    def get_selected_layers(self):
        """Returns a list of the selected layer names."""
        selected = []
        for checkbox in self.layer_checkboxes:
            if checkbox.isChecked():
                selected.append(checkbox.text())
        return selected

    def refresh_main_table_with_analysis(self):
        """Updates the main table after applying the analysis results."""
        try:
            # Remember scroll position
            scroll_position = self.table_view.verticalScrollBar().value()
            
            # Get filtered data with new analysis columns
            selected_layers = self.get_selected_layers()
            enhanced_df = self.geometry_manager.get_filtered_data(selected_layers=selected_layers)
            
            self.model.setDataframe(enhanced_df)
            self.table_view.resizeColumnsToContents()
            # Update buttons after analysis:
            has_associated_text = "Associated_Text" in enhanced_df.columns
            self.z_analysis_button.setEnabled(has_associated_text)
            self.export_dxf_button.setEnabled(has_associated_text)
            self.export_xlsx_button.setEnabled(has_associated_text)
            self.export_csv_button.setEnabled(has_associated_text)
            self.visualization_button.setEnabled(has_associated_text)
            
            # Restore scroll position
            from PySide6.QtCore import QTimer
            QTimer.singleShot(10, lambda: self.table_view.verticalScrollBar().setValue(scroll_position))
            
            print(f"DEBUG: Main table updated with analysis results. {len(enhanced_df)} rows displayed.")
            print("Z-analysis button activated.")
            
        except Exception as e:
            print(f"DEBUG: Error updating main table: {e}")

    def apply_layer_filter(self):
        """Filters the geometry and text table by the selected layers."""
        if not self.geometry_manager.has_data():
            print("Filtering aborted: No data loaded.")
            return

        # Remember scroll positions to avoid jumps
        scroll_pos_geo = self.table_view.verticalScrollBar().value()
        scroll_pos_text = self.text_table_view.verticalScrollBar().value()

        selected_layers = self.get_selected_layers()
        print(f"DEBUG: Filtering by layers: {selected_layers}")

        # Filter geometry data
        geo_filtered_df = self.geometry_manager.get_filtered_data(selected_layers=selected_layers)
        self.model.setDataframe(geo_filtered_df)

        # Filter text data
        text_df = self.geometry_manager.get_text_data()
        if not text_df.empty and 'Layer' in text_df.columns:
            if selected_layers:
                text_filtered_df = text_df[text_df['Layer'].isin(selected_layers)]
            else:
                # If no layers are selected, show empty table
                text_filtered_df = pd.DataFrame(columns=text_df.columns)
        else:
            text_filtered_df = text_df # Show all texts if no layer info is available

        self.text_model.setDataframe(text_filtered_df)

        # UI updates after a short delay to give repainting time
        from PySide6.QtCore import QTimer
        QTimer.singleShot(10, lambda: self.table_view.verticalScrollBar().setValue(scroll_pos_geo))
        QTimer.singleShot(10, lambda: self.text_table_view.verticalScrollBar().setValue(scroll_pos_text))
        
        self.table_view.resizeColumnsToContents()
        self.text_table_view.resizeColumnsToContents()
        analysis_status = "with analysis results" if self.geometry_manager.analysis_results_applied else "without analysis"
        print(f"Filter applied. {len(geo_filtered_df)} geometries and {len(text_filtered_df)} texts displayed ({analysis_status}).")
        has_associated_text = "Associated_Text" in geo_filtered_df.columns
        self.visualization_button.setEnabled(has_associated_text)

    def deselect_all_layers(self):
        """Removes the checks from all layer checkboxes."""
        # Block signals to prevent the table from being redrawn for each change
        for checkbox in self.layer_checkboxes:
            checkbox.blockSignals(True)

        for checkbox in self.layer_checkboxes:
            checkbox.setChecked(False)

        # Release signals
        for checkbox in self.layer_checkboxes:
            checkbox.blockSignals(False)
        
        # Apply filter once at the end manually
        self.apply_layer_filter()

    def select_all_layers(self):
        """Sets the checks on all layer checkboxes."""
        # Block signals to prevent the table from being redrawn for each change
        for checkbox in self.layer_checkboxes:
            checkbox.blockSignals(True)

        for checkbox in self.layer_checkboxes:
            checkbox.setChecked(True)

        # Release signals
        for checkbox in self.layer_checkboxes:
            checkbox.blockSignals(False)
        
        # Apply filter once at the end manually
        self.apply_layer_filter()

    def on_geometry_row_modified(self, row_index, updated_data):
        """
        Wird aufgerufen, wenn eine Zeile in der Geometrie-Tabelle geändert wird.
        Verwendet die ID, um die korrekte Zeile im GeometryManager zu aktualisieren,
        auch wenn die Ansicht gefiltert ist.
        """
        # 1. Hole die ID der geänderten Zeile aus dem (gefilterten) Model
        current_df = self.model.get_data_frame()
        if row_index >= len(current_df):
            print(f"DEBUG: Ungültiger Zeilenindex {row_index} in on_geometry_row_modified.")
            return

        if 'ID' not in current_df.columns:
            print("DEBUG: ID-Spalte nicht im Modell gefunden.")
            return
        entity_id = current_df.iloc[row_index]['ID']
        print(f"DEBUG: Zeile {row_index} (ID: {entity_id}) wird geändert: {updated_data}")

        # 2. Rufe die ID-basierte Update-Methode im GeometryManager auf
        success, updated_row_series = self.geometry_manager.update_geometry_by_id(entity_id, updated_data)

        # 3. Aktualisiere die Zeile im UI-Modell mit den komplett neu berechneten Daten
        if success and updated_row_series is not None:
            # KORREKTUR: Der 'row_index', den wir vom Signal erhalten haben, ist der korrekte
            # positionsbasierte Index für die aktuelle (gefilterte) Ansicht. Wir verwenden diesen direkt.
            self.model.update_row_from_series(row_index, updated_row_series)
            print(f"DEBUG: Zeile mit ID {entity_id} (Position {row_index}) erfolgreich aktualisiert und Ansicht erneuert.")
        else:
            print(f"DEBUG: Fehler beim Aktualisieren der Zeile mit ID {entity_id}")



    def export_to_csv(self):
        """Exports the currently displayed data in the main table to a CSV file."""
        if self.model is None or self.model.rowCount() == 0:
            QMessageBox.information(self, "Export not possible", "No data available for export.")
            return

        if not self.geometry_manager.analysis_results_applied:
            QMessageBox.warning(self, "Export not possible", "Please perform the analysis first and apply the results to the main table.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export current table view as CSV",
            "",
            "CSV files (*.csv);;All files (*)"
        )

        if file_path:
            if not file_path.lower().endswith('.csv'):
                file_path += '.csv'
            
            try:
                # Get the DataFrame directly from the model
                current_df = self.model.get_data_frame()
                
                # Basic data cleaning for CSV
                df_to_export = current_df.copy()
                df_to_export.replace([np.inf, -np.inf], np.nan, inplace=True)
                
                # Export as CSV with UTF-8 encoding
                df_to_export.to_csv(file_path, index=False, encoding='utf-8', sep=';')
                
                QMessageBox.information(self, "Export successful", 
                                      f"The current view was successfully exported to\n{file_path}\n.")
            except Exception as e:
                error_msg = f"An error occurred while exporting the CSV file:\n{str(e)}"
                QMessageBox.critical(self, "Export error", error_msg)

    def open_z_analysis(self):
        """Opens the Z-coordinate analysis with the current geometry data."""
        try:
            # Import the Z-height assignment tool from the ui module
            from ui.heightassignement import HeightAssignmentApp
            
            # Get the current geometry data
            current_df = self.model.get_data_frame() if self.model else pd.DataFrame()
            
            if current_df.empty:
                QMessageBox.warning(self, "No data", "No geometry data available. Please load a DXF file first.")
                return
            
            # Check if the analysis has already been performed
            if not hasattr(self, 'geometry_manager') or not self.geometry_manager.analysis_results_applied:
                QMessageBox.warning(self, "Analysis required", 
                                  "Please perform the geometry-text analysis first before starting the Z-coordinate analysis.")
                return
            
            # Hol die Schlüsselwörter aus dem Eingabefeld
            keywords_text = self.keywords_input.text().strip()
            if not keywords_text:
                keywords_text = "OK,UK,KD"  # Fallback auf Standard-Werte
            
            # Create the Z-height assignment tool as a dialog
            z_tool = HeightAssignmentApp(self)  # Parent directly in the constructor
            z_tool.setWindowTitle("Z-coordinate Analysis")
            z_tool.resize(1200, 800)
            
            # Setze die Schlüsselwörter vor dem Laden der Daten
            z_tool.set_height_keywords(keywords_text)
            
            # Transfer the data directly (without XLSX import)
            z_tool.load_dataframe_directly(current_df)
            
            # Show the tool as a dialog (just like AnalysisDialog)
            result = z_tool.exec()
            
            if result == QDialog.DialogCode.Accepted:
                # Get the processed data
                processed_data = z_tool.get_processed_data()
                
                if processed_data is not None:
                    # Integrate the Z-height data into the main table
                    self.integrate_z_height_data(processed_data)
                    QMessageBox.information(self, "Z-analysis completed", 
                                          f"Z-coordinate analysis successfully completed.\n{len(processed_data)} records processed.")
                
        except ImportError as e:
            QMessageBox.critical(self, "Import error", 
                               f"The Z-height assignment tool could not be loaded:\n{str(e)}\n\nEnsure that the 'Testsoftware_Z-Zurodnung' folder is in the correct path.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error opening Z-coordinate analysis:\n{str(e)}")
    
    def integrate_z_height_data(self, z_data):
        """Integrates the Z-height data into the main table."""
        try:
            import time
            start_time = time.time()
            print(f"DEBUG: Starting Z-data integration...")

            current_df = self.model.get_data_frame().copy()

            if 'ID' not in current_df.columns or 'ID' not in z_data.columns:
                raise ValueError("ID column missing in one of the DataFrames")

            z_columns = ['StartZ', 'EndZ', 'CenterZ']
            status_columns = [col for col in z_data.columns if col.endswith('_Status')]
            available_columns = [col for col in z_columns + status_columns if col in z_data.columns]

            if not available_columns:
                raise ValueError("No Z columns found in the data")

            updates_applied = 0
            arc_indices_to_update = []
            for _, z_row in z_data.iterrows():
                z_id = z_row['ID']
                mask = current_df['ID'] == z_id
                matching_indices = current_df.index[mask]
                if len(matching_indices) == 0:
                    print(f"WARNING: ID '{z_id}' not found in main table. Skipping row.")
                    continue
                row_idx = matching_indices[0]
                for col in available_columns:
                    if col in z_row and pd.notna(z_row[col]):
                        current_df.loc[row_idx, col] = z_row[col]
                entity_type = current_df.loc[row_idx, 'EntityType']
                if entity_type == 'ARC' and any(col in z_row and pd.notna(z_row[col]) for col in ['StartZ', 'EndZ']):
                    arc_indices_to_update.append(row_idx)
                updates_applied += 1
            # --- NEU: ARC-Parameter nach Z-Änderung neu berechnen ---
            for idx in arc_indices_to_update:
                updated_data = {
                    'StartZ': current_df.loc[idx, 'StartZ'],
                    'EndZ': current_df.loc[idx, 'EndZ']
                }
                entity_id = current_df.loc[idx, 'ID']
                success, updated_row_series = self.geometry_manager.update_geometry_by_id(entity_id, updated_data)
                
                if success and updated_row_series is not None:
                    # Schreibe die neu berechneten Werte zurück in den DataFrame, der aktualisiert wird
                    for col_name, value in updated_row_series.items():
                        if col_name in current_df.columns:
                            current_df.at[idx, col_name] = value
            
            # Aktualisiere das UI-Modell und den Master-DataFrame im GeometryManager
            self.model.updateDataFrameInPlace(current_df) # UI aktualisieren
            self.geometry_manager.update_processed_df(current_df) # Master-Daten synchronisieren
            self.table_view.resizeColumnsToContents()
            elapsed_time = time.time() - start_time
            print(f"Z-height data successfully integrated: {updates_applied}/{len(z_data)} records in {elapsed_time:.3f}s")
            
        except Exception as e:
            QMessageBox.critical(self, "Integration error", 
                               f"Error integrating Z-height data:\n{str(e)}")
            import traceback
            print(f"DEBUG: Error in Z integration: {traceback.format_exc()}")

    def open_visualization(self):
        if not self.geometry_manager.has_data():
            QMessageBox.warning(self, "Keine Daten", "Bitte laden Sie zuerst eine DXF-Datei.")
            return
            
        try:
            dxf_doc = self.dxf_parser.get_document()
            layer_list = self.geometry_manager.all_layer_names

            if dxf_doc is None:
                QMessageBox.critical(self, "Error", "The original DXF document could not be retrieved.")
                return

            if self.visualization_window is None or not self.visualization_window.isVisible():
                self.visualization_window = CADViewer()
                self.visualization_window._view.element_clicked.connect(self.select_row_by_id_and_update_viewer)
                self.visualization_window.entity_data_updated.connect(self.on_visualizer_data_updated)

            self.visualization_window.load_document_from_main_app(dxf_doc, layer_list)

            # --- HERE: Both windows side by side at half screen width ---
            screen = QApplication.primaryScreen().geometry()
            half_width = screen.width() // 2
            height = screen.height()

            # Main window on the left
            self.setGeometry(half_width, 0, half_width, height)
            # Visualization on the right
            self.visualization_window.setGeometry(0, 0, half_width, height)
            self.visualization_window.show()
            self.visualization_window.activateWindow()
            # ----------------------------------------------------------

        except Exception as e:
            QMessageBox.critical(self, "Error in visualization", f"An error occurred:\n{str(e)}")

    # MODIFIED METHOD: Now also updates the detail view in the viewer
    @Slot(str)
    def select_row_by_id_and_update_viewer(self, entity_id: str):
        # ... (Your existing logic to find the row)
        df = self.model.get_data_frame()
        matches = df.index[df['ID'] == entity_id].tolist()
        
        if matches:
            row_index = matches[0]
            # ... (Your logic to select the row in the table) ...
            
            # NEW: Send the data of this row to the viewer
            if self.visualization_window and self.visualization_window.isVisible():
                # Assumption: Your PandasTableModel has a method to get a row as dict
                row_data = self.model.get_row_as_dict(row_index) 
                self.visualization_window.display_entity_data(row_data)


    @Slot(dict)
    def on_visualizer_data_updated(self, updated_data: dict):
        """Takes over changes from the visualization and updates the table."""
        entity_id = updated_data.get('ID')
        if not entity_id:
            return

        df = self.model.get_data_frame()
        matches = df.index[df['ID'].astype(str) == str(entity_id)].tolist()
        if matches:
            row_index = matches[0]
            # Assign values with correct types
            for key, value in updated_data.items():
                if key in df.columns:
                    # Try float conversion for Z values
                    if key in ['StartZ', 'EndZ', 'CenterZ']:
                        try:
                            df.at[row_index, key] = float(value) if value != '' else None
                        except Exception:
                            df.at[row_index, key] = None
                    else:
                        df.at[row_index, key] = value
            # Update model and view
            self.model.setDataframe(df)
            self.table_view.selectRow(row_index)

    @Slot(str)
    def select_row_by_id_and_update_viewer(self, entity_id: str):
        """
        Finds an entity by its ID, activates its layer if necessary, and selects it in the table.
        """
        # 1. Always search in the full, unfiltered dataset of the GeometryManager
        full_df = self.geometry_manager.get_geo_data()
        if full_df.empty:
            return

        match_in_full_df = full_df[full_df['ID'] == entity_id]
        if match_in_full_df.empty:
            print(f"ID {entity_id} not found in the master data.")
            return

        # 2. Find the layer of the element and the associated checkbox
        entity_layer = match_in_full_df.iloc[0]['Layer']
        target_checkbox = next((cb for cb in self.layer_checkboxes if cb.text() == entity_layer), None)

        # 3. If the layer is not visible, activate it and call the function again with a delay
        if target_checkbox and not target_checkbox.isChecked():
            print(f"Layer '{entity_layer}' is not visible. It will be activated now.")
            target_checkbox.setChecked(True)  # This triggers apply_layer_filter()
            QTimer.singleShot(100, lambda: self.select_row_by_id_and_update_viewer(entity_id))
            return

        # 4. If the layer is already visible, work with the data from the current table model
        # HERE 'current_df' IS DEFINED:
        current_df = self.model.get_data_frame()
        
        # Find the position (row number) of the ID in the current (filtered) DataFrame
        matching_positions = np.where(current_df['ID'] == entity_id)[0]
        
        if matching_positions.size > 0:
            row_position = matching_positions[0]
            
            # Select the row in the table
            self.table_view.selectRow(row_position)
            self.table_view.scrollTo(self.model.index(row_position, 0), QTableView.ScrollHint.PositionAtCenter)

            # Update the detail view in the viewer
            if self.visualization_window and self.visualization_window.isVisible():
                row_data_for_vis = self.model.get_row_as_dict(row_position)
                self.visualization_window.display_entity_data(row_data_for_vis)
                
            print(f"ID '{entity_id}' selected in row {row_position}.")


    def synchronize_z_values_for_filtered_table(self):
        """
        Synchronizes Z-values for lines/arcs with identical X/Y coordinates in the currently filtered table.
        If a conflict is detected (different Z at same X/Y), a warning is shown and user can choose to overwrite.
        """
        df = self.model.get_data_frame()
        if df.empty:
            QMessageBox.information(self, "No data", "No data in the filtered table.")
            return

        # Only consider LINE and ARC
        mask = df['EntityType'].isin(['LINE', 'ARC'])
        df_lines = df[mask].copy()
        if df_lines.empty:
            QMessageBox.information(self, "No lines/arcs", "No lines or arcs in the filtered table.")
            return

        # Build mapping: (X,Y) -> [(row_idx, 'StartZ'/EndZ, value)]
        coord_map = {}
        for idx, row in df_lines.iterrows():
            for z_col, x_col, y_col in [('StartZ', 'StartX', 'StartY'), ('EndZ', 'EndX', 'EndY')]:
                x, y, z = row.get(x_col), row.get(y_col), row.get(z_col)
                if pd.notna(x) and pd.notna(y):
                    key = (round(float(x), 6), round(float(y), 6))
                    coord_map.setdefault(key, []).append((idx, z_col, z))

        # Find conflicts and candidates for synchronization
        changes = []
        conflicts = []
        for key, entries in coord_map.items():
            # Nur echte, gesetzte Z-Werte (nicht 0.0 und nicht NaN)
            z_values = [z for (_, _, z) in entries if pd.notna(z) and not np.isclose(z, 0.0, atol=1e-6)]
            if not z_values:
                continue
            z_ref = z_values[0]
            # Prüfe, ob es einen Wert gibt, der nicht gleich z_ref ist (und nicht 0.0/NaN)
            conflict = any(not np.isclose(z, z_ref, atol=1e-6) for (_, _, z) in entries if pd.notna(z) and not np.isclose(z, 0.0, atol=1e-6))
            if conflict:
                conflicts.append((key, entries))
            else:
                for idx, z_col, z in entries:
                    if pd.isna(z) or np.isclose(z, 0.0, atol=1e-6):
                        changes.append((idx, z_col, z_ref))

        if conflicts:
            msg = "Conflicting Z-values found at the following coordinates:\n"
            for key, entries in conflicts:
                msg += f"  X={key[0]}, Y={key[1]}: " + ", ".join([f"Row {idx+1} {z_col}={z}" for idx, z_col, z in entries]) + "\n"
            msg += "\nDo you want to overwrite all Z-values at these coordinates with the first value found?"
            reply = QMessageBox.question(self, "Z-value conflicts", msg, QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                for key, entries in conflicts:
                    z_ref = [z for (_, _, z) in entries if pd.notna(z)][0]
                    for idx, z_col, z in entries:
                        if pd.isna(z) or not np.isclose(z, z_ref, atol=1e-6):
                            changes.append((idx, z_col, z_ref))
            else:
                QMessageBox.information(self, "No changes", "No Z-values were changed.")
                return

        if changes:
            # Gruppiere Änderungen nach Zeilenindex, um pro Zeile nur einmal zu aktualisieren
            changes_by_id = {}
            for idx, z_col, z_ref in changes:
                entity_id = df.loc[idx, 'ID']
                if entity_id not in changes_by_id:
                    changes_by_id[entity_id] = {}
                changes_by_id[entity_id][z_col] = z_ref

            for entity_id, updated_data in changes_by_id.items():
                success, updated_row_series = self.geometry_manager.update_geometry_by_id(entity_id, updated_data)
                
                if success and updated_row_series is not None:
                    # Finde den Index der Zeile im aktuellen (möglicherweise gefilterten) DataFrame erneut
                    matches = df.index[df['ID'] == entity_id].tolist()
                    if matches:
                        view_row_index = matches[0]
                        # Aktualisiere die Zeile im UI-Modell mit den komplett neu berechneten Daten
                        for col_name, value in updated_row_series.items():
                            if col_name in df.columns:
                                df.at[view_row_index, col_name] = value
        
            self.model.updateDataFrameInPlace(df)
            QMessageBox.information(self, "Synchronization complete", f"{len(changes)} Z-values were synchronized.")
        else:
            QMessageBox.information(self, "No changes", "No Z-values needed to be synchronized.")


