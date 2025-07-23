from PySide6.QtCore import QAbstractTableModel, Qt, Signal, QModelIndex
from PySide6.QtWidgets import QScrollArea, QWidget, QVBoxLayout
import pandas as pd
import numpy as np
import time
from ezdxf.math import OCS, Vec3

class PandasTableModel(QAbstractTableModel):
    dataFrameModifiedByModel = Signal(pd.DataFrame)
    dataFrameModifiedByModel = Signal(object)  # Existing signal
    rowDataModified = Signal(int, dict) # Signal when a row is modified

    def __init__(self, data_frame: pd.DataFrame, parent=None):
        super().__init__(parent)
        self._data_frame = data_frame.copy() if data_frame is not None else pd.DataFrame()
        self.editable_columns = ['StartZ', 'EndZ'] # Only these are primarily editable for geometry changes

        # Columns that should not be directly editable for certain entity types
        self.arc_non_editable_geometry_params = [
            'NormalX', 'NormalY', 'NormalZ', 
            'StartAngle', 'EndAngle', 
            'Radius', 
            'CenterX', 'CenterY', 'CenterZ', # CenterZ is now derived
            'StartX', 'StartY', 
            'EndX', 'EndY'      
        ]
        self.circle_non_editable_geometry_params = [
            'NormalX', 'NormalY', 'NormalZ',
            'Radius',
            'CenterX', 'CenterY', 'CenterZ' # CenterZ for circles remains not directly editable
        ]
        self.globally_non_editable_base_names = ['ID', 'EntityType'] 
        
    def get_data_frame(self):
        """Returns a reference to the internal DataFrame."""
        return self._data_frame


    def rowCount(self, parent=None): return self._data_frame.shape[0]
    def columnCount(self, parent=None): return self._data_frame.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._data_frame.empty: 
            return None
            
        if role == Qt.DisplayRole or role == Qt.EditRole:
            try:
                value = self._data_frame.iloc[index.row(), index.column()]
                if pd.isna(value) or value is None: 
                    return ""
                    
                col_name = self._data_frame.columns[index.column()]

                if col_name == 'ID':
                    try: 
                        return str(int(value))
                    except ValueError: 
                        return str(value) 
                
                # Special formatting for analysis result columns
                if col_name in ['Associated_Text', 'Associated_BlockName']:
                    return str(value) if value else ""
                
                if col_name == 'Distance':
                    if pd.isna(value) or value == '':
                        return ""
                    try:
                        return f"{float(value):.4f}"
                    except (ValueError, TypeError):
                        return str(value)
                
                if col_name in ['StartAngle', 'EndAngle'] and isinstance(value, (float, np.floating)):
                    return f"{value:.4f}" 
                
                if isinstance(value, (float, np.floating)):
                    if col_name.endswith('X') or col_name.endswith('Y') or col_name.endswith('Z') or col_name == 'Radius':
                        return f"{value:.4f}" 
                    return f"{value:.2f}" 
                    
                return str(value)
            except IndexError: 
                return None
        return None
    


    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if self._data_frame.empty: return None
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                try: return str(self._data_frame.columns[section])
                except IndexError: return None
            elif orientation == Qt.Vertical:
                try: return str(self._data_frame.index[section] + 1)
                except IndexError: return None
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role == Qt.EditRole and index.isValid():
            row = index.row()
            col = index.column()
            column_name = self._data_frame.columns[col]

            try:
                # Get the original value and data type for reference
                original_value = self._data_frame.iloc[row, col]
                original_dtype = self._data_frame[column_name].dtype

                # Convert the new value from the input
                new_value = None
                if value == "" and np.issubdtype(original_dtype, np.number):
                    # Empty input in a numeric column becomes "Not a Number"
                    new_value = np.nan
                elif np.issubdtype(original_dtype, np.number):
                    # Convert to float for all numeric columns
                    new_value = float(value)
                else:
                    # Handle as text for all other columns
                    new_value = str(value)

                # Check if the value has really changed (important for NaN values)
                if pd.isna(original_value) and pd.isna(new_value):
                    changed = False
                elif original_value == new_value:
                    changed = False
                else:
                    changed = True

                if changed:
                    # 1. Update value in the internal DataFrame of the model
                    self._data_frame.iloc[row, col] = new_value

                    # 2. Emit signal for the UI to redraw this cell
                    self.dataChanged.emit(index, index, [role])

                    # 3. Send signal to MainWindow that a row has been modified.
                    #    The MainWindow will then instruct the GeometryManager to update the data.
                    updated_data = {column_name: new_value}
                    self.rowDataModified.emit(row, updated_data)

                    return True

            except (ValueError, TypeError, IndexError) as e:
                # Catches errors, e.g. when "abc" is entered in a numeric column
                print(f"DEBUG: Error setting value '{value}' in column '{column_name}': {e}")
                return False

        return False
    
    def get_row_as_dict(self, row_index: int) -> dict:
        if 0 <= row_index < len(self._data_frame):
            return self._data_frame.iloc[row_index].to_dict()
        return {}
    
    def flags(self, index):
        """ Set the flags for the cells to make certain coordinates editable. """
        if not index.isValid():
            return Qt.NoItemFlags

        default_flags = super().flags(index)

        try:
            # First check if the 'EntityType' column exists.
            # This prevents errors when the model is used for tables without this column (e.g. text table).
            if 'EntityType' not in self._data_frame.columns:
                return default_flags

            column_name = self._data_frame.columns[index.column()]
            entity_type = self._data_frame.iloc[index.row()]['EntityType']
            
            is_editable = False
            
            # Allow editing for Associated_Text and AssociatedText
            if column_name in ['Associated_Text', 'AssociatedText']:
                is_editable = True
            elif column_name in ['Associated_BlockName', 'Distance']:
                return default_flags  # Not editable
            
            # CenterZ for circles (but NOT for arcs!)
            if column_name == 'CenterZ' and entity_type == 'CIRCLE':
                is_editable = True
                
            # StartZ and EndZ for lines and arcs
            elif column_name in ['StartZ', 'EndZ'] and entity_type in ['LINE', 'ARC']:
                is_editable = True

            if is_editable:
                return default_flags | Qt.ItemIsEditable
                
        except (IndexError, KeyError) as e:
            # These errors should now occur less frequently, but the safeguard remains.
            print(f"DEBUG flags() Error: {e}")
            pass

        return default_flags

    def updateDataFrameInPlace(self, new_dataframe):
        """Updates the entire DataFrame without complete model reset."""
        import time
        update_start = time.time()
        
        if new_dataframe.shape != self._data_frame.shape:
            print(f"DEBUG: DataFrame size changed, full reset required")
            self.setDataframe(new_dataframe)
            return
        
        # Update all data
        self._data_frame = new_dataframe.copy()
        
        # Mark all data as changed
        top_left = self.index(0, 0)
        bottom_right = self.index(self.rowCount() - 1, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])
        
        duration = time.time() - update_start
        print(f"PandasTableModel.updateDataFrameInPlace: DataFrame updated in {duration:.3f}s")

    def get_data_frame(self):
        """Returns a reference to the internal DataFrame."""
        return self._data_frame

    def setDataframe(self,data_frame:pd.DataFrame):
        t_start_set_df=time.time()
        self.beginResetModel()
        self._data_frame=data_frame.copy() if data_frame is not None else pd.DataFrame()
        self.endResetModel()
        duration=time.time()-t_start_set_df
        print(f"PandasTableModel.setDataframe: Model reset. Shape: {self._data_frame.shape} (Duration: {duration:.3f}s)")
    
    def updateColumnsInPlace(self, new_dataframe, column_names):
        """Updates only specific columns without complete model reset."""
        import time
        update_start = time.time()
        
        if new_dataframe.shape[0] != self._data_frame.shape[0]:
            print(f"DEBUG: Row count changed, full reset required")
            self.setDataframe(new_dataframe)
            return
        
        # Update only the specified columns
        for col_name in column_names:
            if col_name in new_dataframe.columns:
                if col_name not in self._data_frame.columns:
                    # New column added - requires reset
                    print(f"DEBUG: New column {col_name} found, full reset required")
                    self.setDataframe(new_dataframe)
                    return
                else:
                    # Update column
                    self._data_frame[col_name] = new_dataframe[col_name].copy()
        
        # Mark only the updated columns as changed
        if column_names:
            col_indices = [self._data_frame.columns.get_loc(col) for col in column_names if col in self._data_frame.columns]
            if col_indices:
                for col_idx in col_indices:
                    top_left = self.index(0, col_idx)
                    bottom_right = self.index(self.rowCount() - 1, col_idx)
                    self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])
        
        duration = time.time() - update_start
        print(f"PandasTableModel.updateColumnsInPlace: {len(column_names)} columns updated in {duration:.3f}s")

    def update_row_from_series(self, row_index, series_data):
        """Aktualisiert eine einzelne Zeile im Model mit Daten aus einer Pandas Series."""
        if not (0 <= row_index < self.rowCount()):
            return

        for col_name, value in series_data.items():
            if col_name in self._data_frame.columns:
                col_index = self._data_frame.columns.get_loc(col_name)
                self._data_frame.iloc[row_index, col_index] = value

        # Benachrichtige die Ansicht, dass die gesamte Zeile geändert wurde
        top_left = self.index(row_index, 0)
        bottom_right = self.index(row_index, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])