from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton,
                             QTableView, QFileDialog, QMessageBox, QGroupBox, QLabel,
                             QHBoxLayout, QCheckBox, QScrollArea, QSplitter, QDialog, QFormLayout, QDoubleSpinBox)
import pandas as pd
import numpy as np 
from logic.analysis_handler import AnalysisHandler
from ui.pandas_table_model import PandasTableModel
from PySide6.QtCore import Qt, Signal



class AnalysisDialog(QDialog):
    """A dialog for entering analysis parameters and displaying the results."""
    def __init__(self, geo_df, text_df, parent=None):
        super().__init__(parent)
        self.geo_df = geo_df
        self.text_df = text_df
        self.analysis_handler = AnalysisHandler()
        self.result_df = pd.DataFrame()
        self.parent_window = parent  # Reference to MainWindow

        # Debug: Check the columns of the DataFrames
        print(f"DEBUG: Geometry DataFrame columns: {list(self.geo_df.columns) if not self.geo_df.empty else 'Empty'}")
        print(f"DEBUG: Text DataFrame columns: {list(self.text_df.columns) if not self.text_df.empty else 'Empty'}")

        self.setWindowTitle("Geometry-Text Analysis")
        self.setMinimumSize(1000, 700)
        
        layout = QVBoxLayout(self)
        
        # Parameter input
        form_layout = QFormLayout()
        self.radius_input = QDoubleSpinBox()
        self.radius_input.setRange(0, 10000)
        self.radius_input.setValue(0.5)
        self.radius_input.setSuffix(" units")
        form_layout.addRow("Search radius (circles/arcs):", self.radius_input)
        
        self.line_offset_input = QDoubleSpinBox()
        self.line_offset_input.setRange(0, 10000)
        self.line_offset_input.setValue(0.5)
        self.line_offset_input.setSuffix(" units")
        form_layout.addRow("Max. distance to lines:", self.line_offset_input)
        
        # Button layout for analysis and export
        button_layout = QHBoxLayout()
        
        # Analysis button
        self.analyze_button = QPushButton("Start analysis")
        self.analyze_button.clicked.connect(self.run_analysis)
        button_layout.addWidget(self.analyze_button)
        
        # NEW button: Apply results to main table
        self.apply_to_main_button = QPushButton("Apply results to main table")
        self.apply_to_main_button.clicked.connect(self.apply_results_to_main_table)
        self.apply_to_main_button.setEnabled(False)
        button_layout.addWidget(self.apply_to_main_button)
        
        # Export button
        self.export_button = QPushButton("Export results as XLSX")
        self.export_button.clicked.connect(self.export_to_xlsx)
        self.export_button.setEnabled(False)
        button_layout.addWidget(self.export_button)
        
        form_layout.addRow(button_layout)
        layout.addLayout(form_layout)
        
        # Result table
        self.result_table = QTableView()
        self.result_model = PandasTableModel(pd.DataFrame())
        self.result_table.setModel(self.result_model)
        
        layout.addWidget(self.result_table)

    def run_analysis(self):
        """Führt die Geometrie-Text-Analyse durch."""
        try:
            radius = self.radius_input.value()
            line_offset = self.line_offset_input.value()
            
            # Überprüfe, ob die erforderlichen Spalten vorhanden sind
            required_geo_cols = ['StartX', 'StartY', 'EndX', 'EndY', 'CenterX', 'CenterY', 'Radius']
            required_text_cols = ['InsertX', 'InsertY', 'Text']
            
            missing_geo_cols = [col for col in required_geo_cols if col not in self.geo_df.columns]
            missing_text_cols = [col for col in required_text_cols if col not in self.text_df.columns]
            
            if missing_geo_cols:
                QMessageBox.warning(self, "Spalten fehlen", 
                                  f"Geometrie-DataFrame fehlen Spalten: {missing_geo_cols}")
                return
                
            if missing_text_cols:
                QMessageBox.warning(self, "Spalten fehlen", 
                                  f"Text-DataFrame fehlen Spalten: {missing_text_cols}")
                return
            
            # Führe die Analyse durch
            self.result_df = self.analysis_handler.find_associations(
                geo_df=self.geo_df,
                text_df=self.text_df,
                search_radius=radius,
                line_offset=line_offset
            )
            
            # Aktualisiere die Ergebnis-Tabelle
            self.result_model.setDataframe(self.result_df)
            self.result_table.resizeColumnsToContents()
            
            # Buttons aktivieren
            self.export_button.setEnabled(not self.result_df.empty)
            self.apply_to_main_button.setEnabled(True)  # Immer aktivieren, auch bei leeren Ergebnissen
            
            QMessageBox.information(self, "Analyse abgeschlossen", 
                                  f"Analyse abgeschlossen. {len(self.result_df)} Zuordnungen gefunden.")
            
        except Exception as e:
            QMessageBox.critical(self, "Analyse-Fehler", f"Fehler bei der Analyse:\n{str(e)}")
            print(f"DEBUG: Analyse-Fehler: {e}")
            import traceback
            print(f"DEBUG: Full traceback: {traceback.format_exc()}")

    def apply_results_to_main_table(self):
        """Wendet die Analyseergebnisse auf die Haupttabelle an."""
        try:
            if self.parent_window and hasattr(self.parent_window, 'geometry_manager'):
                # Analyseergebnisse in GeometryManager anwenden
                success = self.parent_window.geometry_manager.apply_analysis_results(self.result_df)
                
                if success:
                    # 1. Haupttabelle im MainWindow aktualisieren
                    self.parent_window.refresh_main_table_with_analysis()

                    # 2. XLSX-Export-Button im Hauptfenster aktivieren
                    self.parent_window.export_xlsx_button.setEnabled(True)
                    self.parent_window.export_csv_button.setEnabled(True)

                    QMessageBox.information(self, "Erfolg", "Die Analyseergebnisse wurden erfolgreich in die Haupttabelle übernommen.")
                    
                    # 3. Dialog schließen
                    self.accept()

                else:
                    QMessageBox.critical(self, "Fehler", "Fehler beim Anwenden der Analyseergebnisse.")
            else:
                QMessageBox.critical(self, "Fehler", "Keine Verbindung zum Hauptfenster.")
                
        except Exception as e:
            QMessageBox.critical(self, "Fehler", f"Fehler beim Übernehmen der Ergebnisse:\n{str(e)}")
            print(f"DEBUG: Fehler bei apply_results_to_main_table: {e}")

    def export_to_xlsx(self):
        """Exportiert die Analyseergebnisse in eine XLSX-Datei."""
        if self.result_df.empty:
            QMessageBox.warning(self, "Keine Daten", "Es sind keine Analyseergebnisse zum Exportieren vorhanden.")
            return
        
        try:
            # Datei-Dialog für Speicherort
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Analyseergebnisse als XLSX speichern",
                "Geometrie_Text_Analyse.xlsx",
                "Excel-Dateien (*.xlsx);;Alle Dateien (*)"
            )
            
            if not file_path:
                return  # Benutzer hat abgebrochen
            
            # Stelle sicher, dass die Datei die .xlsx-Endung hat
            if not file_path.lower().endswith('.xlsx'):
                file_path += '.xlsx'
            
            # DataFrames für Export vorbereiten (NaN und inf Werte bereinigen)
            def clean_dataframe_for_excel(df):
                """Bereinigt einen DataFrame für den Excel-Export."""
                if df.empty:
                    return df
                
                df_clean = df.copy()
                # Ersetze NaN und inf Werte mit leeren Strings oder 0
                df_clean = df_clean.replace([np.nan, np.inf, -np.inf], '')
                
                # Konvertiere alle Spalten zu Strings, um Formatierungsprobleme zu vermeiden
                for col in df_clean.columns:
                    if df_clean[col].dtype == 'object':
                        df_clean[col] = df_clean[col].astype(str)
                    elif df_clean[col].dtype in ['float64', 'float32']:
                        # Runde Dezimalzahlen auf 6 Stellen
                        df_clean[col] = df_clean[col].round(6)
                
                return df_clean
            
            # DataFrame in XLSX exportieren
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # Hauptergebnisse auf dem ersten Arbeitsblatt
                result_clean = clean_dataframe_for_excel(self.result_df)
                result_clean.to_excel(writer, sheet_name='Geometrie_Text_Zuordnungen', index=False)
                
                # Optional: Zusätzliche Arbeitsblätter mit Rohdaten
                if not self.geo_df.empty:
                    geo_clean = clean_dataframe_for_excel(self.geo_df)
                    geo_clean.to_excel(writer, sheet_name='Geometrie_Rohdaten', index=False)
                
                if not self.text_df.empty:
                    text_clean = clean_dataframe_for_excel(self.text_df)
                    text_clean.to_excel(writer, sheet_name='Text_Rohdaten', index=False)
                
                # Zusammenfassung auf einem separaten Arbeitsblatt
                try:
                    summary_data = {
                        'Statistik': [
                            'Anzahl Geometrieobjekte',
                            'Anzahl Textobjekte', 
                            'Anzahl erfolgreiche Zuordnungen',
                            'Anzahl Geometrien ohne Text',
                            'Suchradius Kreise/Arcs verwendet',
                            'Max. Abstand zu Linien verwendet'
                        ],
                        'Wert': [
                            str(len(self.geo_df)),
                            str(len(self.text_df)),
                            str(len(self.result_df)),
                            str(max(0, len(self.geo_df) - len(self.result_df))),
                            f"{self.radius_input.value():.2f} Einheiten",
                            f"{self.line_offset_input.value():.2f} Einheiten"
                        ]
                    }
                    
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name='Zusammenfassung', index=False)
                except Exception as summary_error:
                    print(f"DEBUG: Fehler bei Zusammenfassung: {summary_error}")
                    # Erstelle eine einfache Zusammenfassung ohne potentielle Problemwerte
                    simple_summary = pd.DataFrame({
                        'Info': ['Export erfolgreich abgeschlossen'],
                        'Zeitpunkt': [pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')]
                    })
                    simple_summary.to_excel(writer, sheet_name='Zusammenfassung', index=False)
            
            QMessageBox.information(self, "Export erfolgreich", 
                                  f"Die Analyseergebnisse wurden erfolgreich exportiert:\n{file_path}")
            
        except Exception as e:
            QMessageBox.critical(self, "Export-Fehler", f"Fehler beim Exportieren:\n{str(e)}")
            print(f"DEBUG: Export-Fehler: {e}")
            import traceback
            print(f"DEBUG: Traceback: {traceback.format_exc()}")

