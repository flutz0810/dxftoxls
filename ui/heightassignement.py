import sys
import pandas as pd
import re
import numpy as np
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                               QWidget, QPushButton, QLabel, QLineEdit, QFileDialog,
                               QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor

# Import the logic class
from logic.height_analysis_logic import HeightAnalysisLogic

class HeightAssignmentApp(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Height assignment with layer-based interpolation")
        self.setGeometry(100, 100, 1400, 900)

        self.logic = HeightAnalysisLogic() # Instance of the logic class
        self.df_original = None            # Stores the initially loaded DataFrame
        self.df_processed = None           # Stores the DataFrame prepared by the logic
        self.points_to_review = pd.DataFrame() # Points to be reviewed manually
        self.current_review_idx = 0        # Index of the current point in review
        self.ml_assignment_completed = False # Flag for completed line interpolation

        self.init_ui()

    def set_height_keywords(self, keywords_string):
        """
        Setzt die Schlüsselwörter für die Höhenextraktion in der Logik.
        keywords_string: Komma-getrennte Liste von Schlüsselwörtern
        """
        if self.logic:
            self.logic.set_height_keywords(keywords_string)
            # Aktualisiere auch das UI-Label
            if hasattr(self, 'keywords_label'):
                self.keywords_label.setText(f"Keywords: {keywords_string}")
            print(f"🎯 Keywords in HeightAssignmentApp gesetzt: {keywords_string}")

    def init_ui(self):
        # For QDialog, use setLayout directly, not setCentralWidget
        main_layout = QVBoxLayout(self)

        # --- Top Controls (compact) ---
        top_layout = QHBoxLayout()
        
        self.start_ml_button = QPushButton("Start layer-based interpolation")
        self.start_ml_button.clicked.connect(self.start_ml_assignment)
        self.start_ml_button.setEnabled(True)  # Directly enabled, as data is loaded via load_dataframe_directly
        top_layout.addWidget(self.start_ml_button)

        self.finish_button = QPushButton("Save")
        self.finish_button.clicked.connect(self.finish_assignment_and_save)
        self.finish_button.setEnabled(False)
        top_layout.addWidget(self.finish_button)

        # Button for integration into main table
        self.transfer_button = QPushButton("Transfer to main table")
        self.transfer_button.clicked.connect(self.transfer_to_main_table)
        self.transfer_button.setEnabled(False)
        top_layout.addWidget(self.transfer_button)

        # Anzeige der aktuellen Keywords
        self.keywords_label = QLabel("Keywords: OK,UK,KD")
        self.keywords_label.setStyleSheet("font-weight: bold; color: #2E8B57; padding: 5px;")
        top_layout.addWidget(self.keywords_label)
        
        main_layout.addLayout(top_layout)
        
        # Compact status explanations
        status_labels = [
            ("Text", "From text"), ("Interpolated", "Calculated"), 
            ("Original", "Existing"), ("Manual", "Changed")
        ]


        # --- Table View for all data ---
        self.data_table = QTableWidget()
        main_layout.addWidget(self.data_table)

        # --- Compact status display ---
        self.status_label = QLabel("Ready for Z-height assignment.")
        self.status_label.setMaximumHeight(30)
        main_layout.addWidget(self.status_label)

    def load_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select file", "", "Excel files (*.xlsx *.xls);;All files (*)")
        if file_name:
            try:
                if file_name.endswith(('.xlsx', '.xls')):
                    self.df_original = pd.read_excel(file_name)
                else:
                    raise ValueError("Unsupported file format. Only XLSX/XLS are supported.")

                # Ensure that StartZ, EndZ, CenterZ columns exist and are numeric
                for col in ['StartZ', 'EndZ', 'CenterZ']:
                    if col not in self.df_original.columns:
                        self.df_original[col] = 0.0
                    else:
                        self.df_original[col] = pd.to_numeric(self.df_original[col], errors='coerce').fillna(0.0)

                # Ensure that Layer column exists
                if 'Layer' not in self.df_original.columns:
                    self.df_original['Layer'] = '0'
                
                # Debug: Check data structure
                print(f"Loaded data - columns: {list(self.df_original.columns)}")
                print(f"First 3 rows:")
                print(self.df_original.head(3))
                print(f"Data types:")
                print(self.df_original.dtypes)

                # Validate and clean data
                self.df_original = self.validate_and_clean_data(self.df_original)

                self.status_label.setText(f"'{file_name}' loaded successfully. {len(self.df_original)} rows.")
                self.start_ml_button.setEnabled(True)
                self.update_table_display(self.df_original)
            except Exception as e:
                QMessageBox.critical(self, "Error loading file", f"File could not be loaded:\n{e}")

    def load_dataframe_directly(self, dataframe):
        """Loads data directly from a DataFrame (for integration into main software)."""
        try:
            if dataframe is None or dataframe.empty:
                raise ValueError("The provided DataFrame is empty or None.")
            
            # Copy DataFrame
            self.df_original = dataframe.copy()
            
            # Ensure that StartZ, EndZ, CenterZ columns exist and are numeric
            for col in ['StartZ', 'EndZ', 'CenterZ']:
                if col not in self.df_original.columns:
                    self.df_original[col] = 0.0
                else:
                    self.df_original[col] = pd.to_numeric(self.df_original[col], errors='coerce').fillna(0.0)
            
            # Ensure that Layer column exists
            if 'Layer' not in self.df_original.columns:
                self.df_original['Layer'] = '0'
                
            # Debug: Check data structure
            print(f"Directly loaded data - columns: {list(self.df_original.columns)}")
            print(f"First 3 rows:")
            print(self.df_original.head(3))
            
            # Validate and clean data
            self.df_original = self.validate_and_clean_data(self.df_original)
            
            self.status_label.setText(f"{len(self.df_original)} objects loaded. Ready for Z-analysis.")
            self.update_table_display(self.df_original)
            
        except Exception as e:
            QMessageBox.critical(self, "Error loading data", f"Data could not be loaded directly:\n{e}")

    def validate_and_clean_data(self, df):
        """Validates and cleans the loaded data."""
        print("Validating and cleaning data...")
        
        # Create a copy
        df_clean = df.copy()
        
        # Ensure ID column exists - BUT KEEP ORIGINAL IDs
        if 'ID' not in df_clean.columns:
            # If no ID exists, create one
            df_clean['ID'] = range(1, len(df_clean) + 1)
            print("⚠️ No ID column found - automatically created")
        else:
            # KEEP ORIGINAL IDs (including hexadecimal)
            # Convert to string to support all ID types
            df_clean['ID'] = df_clean['ID'].astype(str)
            
            # Check for empty or NaN IDs
            empty_mask = df_clean['ID'].isin(['', 'nan', 'None']) | df_clean['ID'].isna()
            if empty_mask.any():
                print(f"⚠️ {empty_mask.sum()} empty ID values found - will be replaced by index")
                df_clean.loc[empty_mask, 'ID'] = [f"AUTO_{i}" for i in range(empty_mask.sum())]
            
            print(f"✅ {len(df_clean)} IDs retained (original format)")
        
        # Ensure EntityType exists
        if 'EntityType' not in df_clean.columns:
            df_clean['EntityType'] = 'LINE'  # Default assumption
            print("⚠️ No EntityType column found - default 'LINE' used")
        
        # Clean EntityType values
        valid_types = ['LINE', 'CIRCLE', 'ARC', 'POLYLINE', 'LWPOLYLINE']
        invalid_mask = ~df_clean['EntityType'].isin(valid_types)
        if invalid_mask.any():
            invalid_count = invalid_mask.sum()
            df_clean.loc[invalid_mask, 'EntityType'] = 'LINE'
            print(f"⚠️ {invalid_count} invalid EntityType values changed to 'LINE'")
        
        # Validate numeric columns - WITHOUT NaN→0 conversion
        numeric_cols = ['StartX', 'StartY', 'StartZ', 'EndX', 'EndY', 'EndZ', 'CenterX', 'CenterY', 'CenterZ']
        for col in numeric_cols:
            if col not in df_clean.columns:
                df_clean[col] = np.nan  # Use NaN as default, not 0
            else:
                original_values = df_clean[col].copy()
                df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')  # Keep NaN
                
                # Count converted values
                converted_count = (original_values.astype(str) != df_clean[col].astype(str)).sum()
                if converted_count > 0:
                    print(f"⚠️ {col}: {converted_count} values converted to numeric")
        
        # Clean Associated_Text
        if 'Associated_Text' not in df_clean.columns:
            df_clean['Associated_Text'] = ''
        else:
            df_clean['Associated_Text'] = df_clean['Associated_Text'].fillna('')
        
        # Clean Radius column - WITHOUT NaN→0 conversion
        if 'Radius' not in df_clean.columns:
            df_clean['Radius'] = np.nan
        else:
            df_clean['Radius'] = pd.to_numeric(df_clean['Radius'], errors='coerce')  # Keep NaN
        
        print(f"✓ Data validation complete. {len(df_clean)} rows ready.")
        return df_clean

    def start_ml_assignment(self):
        if self.df_original is None:
            QMessageBox.warning(self, "No data", "Please load a file first.")
            return

        self.status_label.setText("Starting layer-based line interpolation...")
        QApplication.processEvents()

        try:
            # New layer-based line interpolation
            self.df_processed = self.logic.prepare_data_for_line_interpolation(self.df_original)
            
            # Count results based on status columns
            text_heights = self.df_processed['Direct_Height'].notna().sum()
            interpolated_heights = (
                (self.df_processed['StartZ_Status'] == 'Interpolated').sum() +
                (self.df_processed['EndZ_Status'] == 'Interpolated').sum() +
                (self.df_processed['CenterZ_Status'] == 'Interpolated').sum()
            )
            total_objects = len(self.df_processed)
            
            # Analyze layer distribution
            line_mask = self.df_processed['EntityType'] == 'LINE'
            unique_layers = self.df_processed[line_mask]['Layer'].unique() if 'Layer' in self.df_processed.columns else ['DEFAULT']
            layer_count = len(unique_layers)
            
            # Show summary
            summary_msg = f"""Layer-based line interpolation complete:

📊 Summary:
• Total objects: {total_objects}
• Processed layers: {layer_count}
• Heights from text: {text_heights}
• Interpolated heights: {interpolated_heights}
• Circles (text only): {len(self.df_processed[self.df_processed['EntityType'] == 'CIRCLE'])}

🚀 Performance optimization:
• Layer-based analysis for better performance
• Reduced search complexity per layer
• Separate processing of connected line strings

✅ All objects have been processed!
You can now review the results or save them directly."""

            QMessageBox.information(self, "Z-analysis complete", summary_msg)
            
            # Enable buttons for next steps
            self.finish_button.setEnabled(True)
            self.transfer_button.setEnabled(True)
            self.ml_assignment_completed = True
            
            # Update table with results
            self.update_table_display(self.df_processed)
            self.status_label.setText(f"Z-analysis complete ({layer_count} layers). Ready to save or transfer.")
            
        except Exception as e:
            QMessageBox.critical(self, "Error in line interpolation", f"An error occurred:\n{str(e)}")
            self.status_label.setText("Error in line interpolation.")
            print(f"DEBUG: Error in line interpolation: {e}")
            import traceback
            traceback.print_exc()

    def start_review_process(self):
        """Starts the manual review process."""
        if not self.ml_assignment_completed:
            QMessageBox.warning(self, "Not ready", "Please perform line interpolation first.")
            return
            
        # Create list of points to review based on status columns
        self.points_to_review = self.df_processed[
            (self.df_processed['Direct_Height'].notna()) | 
            (self.df_processed['StartZ_Status'].isin(['Text', 'Interpolated'])) |
            (self.df_processed['EndZ_Status'].isin(['Text', 'Interpolated'])) |
            (self.df_processed['CenterZ_Status'].isin(['Text', 'Interpolated']))
        ].copy()
        
        if self.points_to_review.empty:
            QMessageBox.information(self, "No points", "No points available for review.")
            return

        self.current_review_idx = 0
        self.review_button.setEnabled(False)
        self.accept_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        self.reject_button.setEnabled(True)
        
        self.status_label.setText(f"Review: Point {self.current_review_idx + 1} of {len(self.points_to_review)}")
        self.display_current_review_point()

    def display_current_review_point(self):
        """Displays the current point for review."""
        if self.current_review_idx >= len(self.points_to_review):
            QMessageBox.information(self, "Review complete", "All points have been reviewed.")
            self.finish_assignment_and_save()
            return

        row = self.points_to_review.iloc[self.current_review_idx]
        
        # Basic information
        self.id_line_edit.setText(str(row['ID']))
        self.type_line_edit.setText(row['EntityType'])
        
        # Geometry coordinates - with better formatting
        def format_coord(val):
            if pd.isna(val) or val == '':
                return 'N/A'
            try:
                return f"{float(val):.2f}"
            except:
                return str(val)
        
        # Geometry coordinates - with status information
        def format_coord_with_status(val, status):
            if pd.isna(val) or val == '':
                return 'N/A'
            try:
                status_str = f" ({status})" if status and status != '' else ""
                return f"{float(val):.2f}{status_str}"
            except:
                return str(val)
        
        start_coords = f"{format_coord(row.get('StartX'))}, {format_coord(row.get('StartY'))}, {format_coord_with_status(row.get('StartZ'), row.get('StartZ_Status'))}"
        end_coords = f"{format_coord(row.get('EndX'))}, {format_coord(row.get('EndY'))}, {format_coord_with_status(row.get('EndZ'), row.get('EndZ_Status'))}"
        center_coords = f"{format_coord(row.get('CenterX'))}, {format_coord(row.get('CenterY'))}, {format_coord_with_status(row.get('CenterZ'), row.get('CenterZ_Status'))}"
        
        self.start_coords_line_edit.setText(start_coords)
        self.end_coords_line_edit.setText(end_coords)
        self.center_coords_line_edit.setText(center_coords)
        
        # Text coordinates (if available)
        if 'InsertX' in row and 'InsertY' in row:
            text_coords = f"[{format_coord(row.get('InsertX'))}, {format_coord(row.get('InsertY'))}]"
        else:
            text_coords = "Not available"
        self.text_coords_line_edit.setText(text_coords)
        
        # Associated text
        assoc_text = row.get('Associated_Text', '')
        if pd.isna(assoc_text) or assoc_text == '':
            assoc_text = 'No text'
        self.text_info_label.setText(f"Assoc. Text: {assoc_text}")
        
        # Display current heights
        current_height = 0.0
        if row['EntityType'] == 'LINE':
            if pd.notna(row.get('StartZ')):
                current_height = row.get('StartZ', 0.0)
            elif pd.notna(row.get('EndZ')):
                current_height = row.get('EndZ', 0.0)
        elif row['EntityType'] == 'ARC':
            if pd.notna(row.get('StartZ')):
                current_height = row.get('StartZ', 0.0)
            elif pd.notna(row.get('EndZ')):
                current_height = row.get('EndZ', 0.0)
        elif row['EntityType'] == 'CIRCLE':
            current_height = row.get('CenterZ', 0.0)
        
        if pd.isna(current_height):
            current_height = 0.0
        self.predicted_height_line_edit.setText(f"{current_height:.2f}")
        
        # Clear correction field
        self.correction_line_edit.clear()
        
        # Update status
        self.status_label.setText(f"Review: Point {self.current_review_idx + 1} of {len(self.points_to_review)}")

    def accept_prediction(self):
        """Accepts the prediction or correction for the current point."""
        if self.current_review_idx >= len(self.points_to_review):
            self.display_current_review_point()
            return

        row = self.points_to_review.iloc[self.current_review_idx]
        
        # Check if a correction was entered
        correction_text = self.correction_line_edit.text().strip()
        
        if correction_text:
            try:
                corrected_height = float(correction_text)
                # Set corrected height based on EntityType
                if row['EntityType'] == 'LINE':
                    self.logic.update_processed_data(self.df_processed, row['ID'], row['EntityType'], 
                                                   start_z=corrected_height, end_z=corrected_height)
                elif row['EntityType'] == 'ARC':
                    self.logic.update_processed_data(self.df_processed, row['ID'], row['EntityType'], 
                                                   start_z=corrected_height, end_z=corrected_height)
                elif row['EntityType'] == 'CIRCLE':
                    self.logic.update_processed_data(self.df_processed, row['ID'], row['EntityType'], 
                                                   center_z=corrected_height)
            except ValueError:
                QMessageBox.warning(self, "Invalid input", "Please enter a valid number or leave the field blank.")
                return
        # If no correction was entered, keep the current values

        # Move to next point
        self.current_review_idx += 1
        self.display_current_review_point()
        self.update_table_display(self.df_processed)

    def skip_prediction(self):
        """Skips the current point without changes."""
        self.current_review_idx += 1
        self.display_current_review_point()

    def reject_prediction(self):
        """Rejects the prediction and sets Z-values to 0."""
        if self.current_review_idx >= len(self.points_to_review):
            self.display_current_review_point()
            return

        row = self.points_to_review.iloc[self.current_review_idx]
        
        # Set Z-values to 0.0 based on EntityType
        if row['EntityType'] == 'LINE':
            self.logic.update_processed_data(self.df_processed, row['ID'], row['EntityType'], 
                                           start_z=0.0, end_z=0.0)
        elif row['EntityType'] == 'ARC':
            self.logic.update_processed_data(self.df_processed, row['ID'], row['EntityType'], 
                                           start_z=0.0, end_z=0.0)
        elif row['EntityType'] == 'CIRCLE':
            self.logic.update_processed_data(self.df_processed, row['ID'], row['EntityType'], 
                                           center_z=0.0)
        
        # Move to next point
        self.current_review_idx += 1
        self.display_current_review_point()
        self.update_table_display(self.df_processed)

    def finish_assignment_and_save(self):
        """Closes the assignment and saves the results."""
        self.status_label.setText("Saving results...")
        self.finish_button.setEnabled(False)
        self.transfer_button.setEnabled(False)

        # Get final DataFrame from logic
        if self.df_processed is not None:
            final_df = self.logic.get_final_dataframe()
            
            # Save dialog
            file_name, _ = QFileDialog.getSaveFileName(self, "Save results", "", "Excel files (*.xlsx);;All files (*)")
            if file_name:
                if not file_name.endswith('.xlsx'):
                    file_name += '.xlsx'
                try:
                    # Minimal export - direct DataFrame export
                    final_df.to_excel(file_name, index=False)
                    QMessageBox.information(self, "Saved successfully", f"The results have been saved successfully:\n{file_name}")
                    self.accept()  # Close dialog with OK after successful save
                except Exception as e:
                    QMessageBox.critical(self, "Save error", f"Error saving file:\n{e}")
            
            self.update_table_display(final_df)
            # Re-enable buttons after successful/canceled save
            self.finish_button.setEnabled(True)
            self.transfer_button.setEnabled(True)
        else:
            QMessageBox.warning(self, "Error", "No data available to save.")

    def update_table_display(self, df_to_display):
        """Updates the QTableWidget with the data, keeping original structure."""
        if df_to_display is None or df_to_display.empty:
            self.data_table.setRowCount(0)
            self.data_table.setColumnCount(0)
            return

        # Use the ORIGINAL column order - no restructuring
        all_columns = list(df_to_display.columns)
        
        self.data_table.setColumnCount(len(all_columns))
        self.data_table.setHorizontalHeaderLabels(all_columns)
        self.data_table.setRowCount(len(df_to_display))

        # Determine which columns are status columns
        status_columns = [col for col in all_columns if col.endswith('_Status')]
        
        # Fill the table row by row
        for row_idx in range(len(df_to_display)):
            row_data = df_to_display.iloc[row_idx]
            for col_idx, col_name in enumerate(all_columns):
                value = row_data.get(col_name, '')
                
                # Format values - keep NaN as empty
                if pd.isna(value):
                    display_value = ""
                elif isinstance(value, (int, float)):
                    # Format numeric values
                    if col_name in ['StartX', 'StartY', 'StartZ', 'EndX', 'EndY', 'EndZ', 
                                   'CenterX', 'CenterY', 'CenterZ', 'Radius', 'Direct_Height']:
                        display_value = f"{float(value):.4f}"
                    else:
                        display_value = str(value)
                else:
                    display_value = str(value)
                
                item = QTableWidgetItem(display_value)
                
                # No more color coding - status columns provide the information
                
                self.data_table.setItem(row_idx, col_idx, item)

        # Column widths adjustable
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.data_table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.data_table.setSortingEnabled(True)
        
        # Set reasonable default widths
        header = self.data_table.horizontalHeader()
        for i, col_name in enumerate(all_columns):
            if col_name == 'ID':
                header.resizeSection(i, 60)
            elif col_name == 'EntityType':
                header.resizeSection(i, 80)
            elif col_name == 'Associated_Text':
                header.resizeSection(i, 200)
            elif col_name.endswith('_Status'):
                header.resizeSection(i, 90)  # Status columns
            elif any(coord in col_name for coord in ['X', 'Y', 'Z']) or col_name in ['Radius', 'Direct_Height']:
                header.resizeSection(i, 100)
            else:
                header.resizeSection(i, 120)

    def transfer_to_main_table(self):
        """Transfers the processed data for integration into the main table."""
        if self.df_processed is not None:
            final_df = self.logic.get_final_dataframe()
            
            # Integration into the main table would take place here
            # For now, we just show a confirmation
            result = QMessageBox.question(self, "Transfer data", 
                                        f"Do you want to transfer the {len(final_df)} processed records to the main table?\n\n"
                                        "This action will update the Z-coordinates and status columns in the main table.",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            
            if result == QMessageBox.StandardButton.Yes:
                # Try to integrate into the main table via the parent window
                if self.parent() and hasattr(self.parent(), 'integrate_z_height_data'):
                    self.parent().integrate_z_height_data(final_df)
                    QMessageBox.information(self, "Successful", "The data has been successfully transferred to the main table.")
                    self.accept()  # Close dialog with OK
                else:
                    # In case parent integration is not possible
                    QMessageBox.information(self, "Data available", 
                                          "The data is processed and can be exported via 'Complete assignment & Save'.")
                    self.accept()  # Close dialog with OK
        else:
            QMessageBox.warning(self, "Error", "No data available for transfer.")

    def get_processed_data(self):
        """Returns the processed data (for external use)."""
        if self.df_processed is not None:
            return self.logic.get_final_dataframe()
        return None

    def show_text_assignment_table(self):
        """
        Zeigt die Text-Zuordnungstabelle in einem separaten Dialog.
        """
        assignment_table = self.logic.get_text_assignment_table()
        if assignment_table.empty:
            QMessageBox.information(self, "Info", "Keine Text-Zuordnungen verfügbar.")
            return

        # Erstelle separaten Dialog für Zuordnungstabelle
        dialog = QDialog(self)
        dialog.setWindowTitle("Text-Zuordnungstabelle")
        dialog.setGeometry(200, 200, 800, 600)

        layout = QVBoxLayout(dialog)
        table = QTableWidget()

        # Fülle Tabelle mit Zuordnungsdaten
        table.setRowCount(len(assignment_table))
        table.setColumnCount(len(assignment_table.columns))
        table.setHorizontalHeaderLabels(assignment_table.columns.tolist())

        for row, (_, data) in enumerate(assignment_table.iterrows()):
            for col, value in enumerate(data):
                table.setItem(row, col, QTableWidgetItem(str(value)))

        layout.addWidget(table)
        dialog.exec()
