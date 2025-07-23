import pandas as pd
import numpy as np
import PySide6.QtCore as QtCore

# import re # No longer strictly needed for parsing core attributes


class GeometryManager:
    def __init__(self):
        self.raw_entities_df = pd.DataFrame()
        self.all_entities_df = pd.DataFrame()
        # CORRECTED: All columns in the desired order
        self.display_columns_ordered = [
            'ID', 'EntityType', 'Associated_Text', 'Associated_BlockName', 'Distance', 
            'Layer', 'Color', 'StartX', 'StartY', 'StartZ', 
            'EndX', 'EndY', 'EndZ', 'CenterX', 'CenterY', 'CenterZ', 
            'Radius', 'NormalX', 'NormalY', 'NormalZ', 'StartAngle', 'EndAngle'
        ]
        self.text_df = pd.DataFrame()
        self.all_layer_names = []
        self.analysis_results_applied = False
        self.id_column_name_in_all_entities_df = 'ID'
    def has_data(self):
        """
        Checks if geometry data has been loaded.
        Returns True if the geometry DataFrame is not empty.
        """
        return self.all_entities_df is not None and not self.all_entities_df.empty


    def process_dxf_data_frame(self, geo_df: pd.DataFrame, text_df: pd.DataFrame, all_layer_names: list):
        print("--- Starte process_dxf_data_frame ---")
        
        # 1) Speicher die DataFrames intern
        self.all_entities_df = geo_df.copy() if geo_df is not None else pd.DataFrame()
        self.text_df = text_df.copy() if text_df is not None else pd.DataFrame()

        # 2) Layer aus Geometrie + Text + DXF-Layer vereinen
        unique_geo_layers = set(self.all_entities_df['Layer'].unique()) if not self.all_entities_df.empty else set()
        unique_text_layers = set(self.text_df['Layer'].unique()) if not self.text_df.empty else set()
        unique_dxf_layers = set(all_layer_names) if all_layer_names else set()

        all_collected_layers = unique_geo_layers.union(unique_text_layers).union(unique_dxf_layers)
        self.all_layer_names = sorted(list(all_collected_layers))
        
        print(f"DEBUG GM: {len(self.all_entities_df)} Geometrien und {len(self.text_df)} Texte verarbeitet.")
        print(f"DEBUG GM: {len(self.all_layer_names)} Layer insgesamt erkannt.")
        print(f"DEBUG GM: Geo-Layer: {unique_geo_layers}")
        print(f"DEBUG GM: Text-Layer: {unique_text_layers}")
        print(f"--- Beende process_dxf_data_frame. ---")
    
    
    def apply_analysis_results(self, analysis_results_df):
        """
        Wendet die Analyseergebnisse auf die Geometriedaten an.
        Fügt Associated_Text, Associated_BlockName und Distance zu allen Geometrien hinzu.
        """
        if self.all_entities_df.empty:
            print("WARNUNG: Keine Geometriedaten zum Anwenden der Analyseergebnisse.")
            # Dennoch die Spalten hinzufügen, um Konsistenz zu wahren
            self.all_entities_df['Associated_Text'] = ''
            self.all_entities_df['Associated_BlockName'] = ''
            self.all_entities_df['Distance'] = np.nan
            self.analysis_results_applied = True
            return True
        
        try:
            # Kopie der Geometriedaten erstellen
            enhanced_df = self.all_entities_df.copy()
            
            # Neue Spalten initialisieren
            enhanced_df['Associated_Text'] = ''
            enhanced_df['Associated_BlockName'] = ''
            enhanced_df['Distance'] = np.nan
            
            # Analyseergebnisse zuordnen
            if not analysis_results_df.empty:
                # Erstelle ein Dictionary für schnelle Zuordnung
                analysis_dict = {}
                for _, result_row in analysis_results_df.iterrows():
                    geo_id = result_row['GeometryID']
                    analysis_dict[geo_id] = {
                        'Associated_Text': result_row.get('AssociatedText', ''),
                        'Associated_BlockName': result_row.get('TextBlockName', ''),
                        'Distance': result_row.get('Distance', np.nan)
                    }
                
                # Zuordnungen in enhanced_df eintragen
                for idx, row in enhanced_df.iterrows():
                    geo_id = row['ID']
                    if geo_id in analysis_dict:
                        enhanced_df.at[idx, 'Associated_Text'] = analysis_dict[geo_id]['Associated_Text']
                        enhanced_df.at[idx, 'Associated_BlockName'] = analysis_dict[geo_id]['Associated_BlockName']
                        enhanced_df.at[idx, 'Distance'] = analysis_dict[geo_id]['Distance']
                
                print(f"DEBUG GM: Analyseergebnisse angewendet. {len(analysis_dict)} Zuordnungen von {len(enhanced_df)} Geometrien.")
            else:
                print("DEBUG GM: Keine Analyseergebnisse zum Anwenden.")
            
            # Enhanced DataFrame als neuen Geometrie-DataFrame setzen
            self.all_entities_df = enhanced_df
            self.analysis_results_applied = True
            
            return True
            
        except Exception as e:
            print(f"FEHLER beim Anwenden der Analyseergebnisse: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            return False

    def get_filtered_data(self, selected_layers=None, selected_entity_types=None):
        """Filtert nur Geometriedaten nach den angegebenen Layern/EntityTypes.
        Gibt ALLE Spalten zurück, bekannte zuerst, neue hinten."""
        if self.all_entities_df.empty:
            return pd.DataFrame(columns=self.display_columns_ordered)

        df_to_filter = self.all_entities_df.copy()

        # LAYER-FILTER
        if selected_layers is not None and len(selected_layers) > 0:
            df_to_filter = df_to_filter[df_to_filter['Layer'].isin(selected_layers)]

        # ENTITYTYPE-FILTER
        if selected_entity_types:
            df_to_filter = df_to_filter[df_to_filter['EntityType'].isin(selected_entity_types)]

        # Spalten sortieren: bekannte zuerst, neue hinten
        known = [col for col in self.display_columns_ordered if col in df_to_filter.columns]
        new = [col for col in df_to_filter.columns if col not in self.display_columns_ordered]
        final_cols = known + new

        return df_to_filter[final_cols].copy()

    def _get_default_all_entities_columns(self):
        """ Liefert eine Standardliste von Spaltennamen, falls der DataFrame leer ist. """
        cols = [self.displayed_id_column_name, 'EntityType', self.layer_column_name_source or 'Layer']
        geo_cols = ['StartX','StartY','StartZ','EndX','EndY','EndZ','CenterX','CenterY','CenterZ','Radius','NormalX','NormalY','NormalZ','StartAngle','EndAngle']
        for gc in geo_cols:
            if gc not in cols: cols.append(gc)
        return cols

    def set_entity_type_filter(self, types_to_show_list: list):
        self.active_entity_types = {str(t).lower().strip() for t in types_to_show_list}

    def set_layer_filter(self, layers_to_show_list: list = None):
        if layers_to_show_list is None: self.active_layers = None 
        else: self.active_layers = {str(layer).lower().strip() for layer in layers_to_show_list}
    
    def get_unique_layers(self):
        """
        Gibt eine Liste aller einzigartigen Layer-Namen aus dem geladenen DataFrame zurück.
        Diese Methode ist sicher und verändert keine Daten.
        """
        if self.all_entities_df.empty or 'Layer' not in self.all_entities_df.columns:
            return []
        return self.all_entities_df['Layer'].unique().tolist()

    def get_geo_data(self):
        """Gibt den DataFrame mit allen Geometrie-Entitäten zurück."""
        return self.all_entities_df
    
    def get_text_data(self):
        """Gibt den DataFrame mit allen Text-Entitäten zurück."""
        return self.text_df

    def get_display_df(self):
        if self.all_entities_df.empty:
            return pd.DataFrame(columns=self.display_column_order if self.display_column_order else self._get_default_all_entities_columns())

        df_to_filter = self.all_entities_df 

        # 1. Nach Entitätstyp filtern
        if 'EntityType' in df_to_filter.columns and self.active_entity_types is not None:
            mask_entity = df_to_filter['EntityType'].fillna('').astype(str).str.lower().isin(self.active_entity_types)
            df_to_filter = df_to_filter[mask_entity]
        
        # 2. Nach Layer filtern
        layer_col_for_filter = self.layer_column_name_source # Der tatsächliche Name im all_entities_df
        if layer_col_for_filter and layer_col_for_filter in df_to_filter.columns and self.active_layers is not None:
            mask_layer = df_to_filter[layer_col_for_filter].fillna('').astype(str).str.lower().isin(self.active_layers)
            df_to_filter = df_to_filter[mask_layer]
        
        # 3. Nur die definierten Anzeigespalten in der festgelegten Reihenfolge zurückgeben
        cols_for_model = self.display_column_order[:] 
        # EntityType wird für die Model-Logik benötigt, auch wenn es in der UI versteckt ist
        if 'EntityType' in self.all_entities_df.columns and 'EntityType' not in cols_for_model:
            cols_for_model.append('EntityType')
        
        final_cols_for_model = [col for col in cols_for_model if col in df_to_filter.columns]
        
        return df_to_filter[final_cols_for_model].copy() if final_cols_for_model else df_to_filter.copy()

    def update_processed_df(self, modified_view_df_part: pd.DataFrame):
        id_col_to_use = self.id_column_name_in_all_entities_df # Sollte 'ID' sein
        if not id_col_to_use: print("WARNUNG in update_processed_df: ID-Spalte für Updates nicht definiert.") ; return
        if id_col_to_use not in modified_view_df_part.columns or id_col_to_use not in self.all_entities_df.columns:
            print(f"WARNUNG in update_processed_df: ID-Spalte '{id_col_to_use}' nicht konsistent.") ; return
        if self.all_entities_df.empty: print("WARNUNG: update_processed_df - all_entities_df ist leer."); return
        try:
            # Wichtig: Stelle sicher, dass der Index des Master-DataFrames für das Update korrekt ist.
            # modified_view_df_part enthält nur einen Teil der Zeilen.
            # Wir müssen die entsprechenden Zeilen im Master-DataFrame finden und aktualisieren.
            
            # Setze den Index für beide DataFrames auf die ID-Spalte
            temp_all_entities_indexed = self.all_entities_df.set_index(id_col_to_use, drop=False)
            modified_view_indexed = modified_view_df_part.set_index(id_col_to_use, drop=False)
            
            # .update() modifiziert temp_all_entities_indexed an Ort und Stelle für übereinstimmende Indizes
            common_cols = temp_all_entities_indexed.columns.intersection(modified_view_indexed.columns)
            temp_all_entities_indexed.update(modified_view_indexed[common_cols])
            
            # Setze den Index zurück, um den ursprünglichen Zustand von all_entities_df wiederherzustellen
            self.all_entities_df = temp_all_entities_indexed.reset_index(drop=True)
            
            # print(f"GM.update_processed_df: Master-DF aktualisiert via '{id_col_to_use}'.")
        except Exception as e:
            print(f"FEHLER in update_processed_df: {e}")
    
    def update_geometry_by_id(self, entity_id: str, updated_data: dict):
        """
        Findet eine Geometrie anhand ihrer ID, aktualisiert sie mit den bereitgestellten Daten
        und berechnet abhängige Werte neu (z. B. für ARCs).
        Gibt ein Tupel zurück: (success_boolean, updated_row_as_series).
        """
        if self.all_entities_df.empty:
            return False, None

        try:
            # 1. Finde den korrekten Index im Master-DataFrame
            matching_indices = self.all_entities_df.index[self.all_entities_df['ID'] == entity_id].tolist()
            if not matching_indices:
                print(f"DEBUG: ID '{entity_id}' nicht in all_entities_df gefunden.")
            
            master_row_index = matching_indices[0]

            # 2. Aktualisiere die übergebenen Werte im Master-DataFrame
            for column, value in updated_data.items():
                if column in self.all_entities_df.columns:
                    self.all_entities_df.at[master_row_index, column] = value
            
            # 3. Hole die jetzt aktualisierte Zeile für die Neuberechnung
            current_row_data = self.all_entities_df.loc[master_row_index]
            entity_type = current_row_data.get('EntityType', '').upper()

            # 4. Spezielle Neuberechnung je nach Entitätstyp
            if entity_type == 'ARC':
                self._recalculate_arc_points(master_row_index, current_row_data)
            
            # 5. Gib die komplett aktualisierte Zeile zurück
            final_updated_row = self.all_entities_df.loc[master_row_index]
            return True, final_updated_row

        except Exception as e:
            print(f"DEBUG: Fehler beim Aktualisieren der Geometrie mit ID '{entity_id}': {e}")

            import traceback
            traceback.print_exc()
            return False, None



    def _recalculate_arc_points(self, row_index, row_data):
        """
        Berechnet abhängige Parameter für Bögen basierend auf geänderten StartZ/EndZ-Werten neu.
        """
        try:
            import math
            from ezdxf.math import Vec3, OCS

            center_x = float(row_data.get('CenterX', 0))
            center_y = float(row_data.get('CenterY', 0))
            start_x = float(row_data.get('StartX', 0))
            start_y = float(row_data.get('StartY', 0))
            end_x = float(row_data.get('EndX', 0))
            end_y = float(row_data.get('EndY', 0))

            start_z = row_data.get('StartZ')
            end_z = row_data.get('EndZ')

            if pd.notna(start_z):
                start_z = float(start_z)
            else:
                start_z = None

            if pd.notna(end_z):
                end_z = float(end_z)
            else:
                end_z = None

            # CenterZ bestimmen
            if start_z is not None and end_z is not None:
                new_center_z = (start_z + end_z) / 2.0
            elif start_z is not None:
                new_center_z = start_z
            elif end_z is not None:
                new_center_z = end_z
            else:
                old_center_z = row_data.get('CenterZ')
                new_center_z = float(old_center_z) if pd.notna(old_center_z) else 0.0

            # Radius nur berechnen, wenn beide Z-Werte vorhanden sind
            if start_z is not None and end_z is not None:
                actual_start_z = start_z
                actual_end_z = end_z
                p_start = Vec3(start_x, start_y, actual_start_z)
                p_end = Vec3(end_x, end_y, actual_end_z)
                center = Vec3(center_x, center_y, new_center_z)
                new_radius = (p_start - center).magnitude

                v_center_to_start = p_start - center
                v_center_to_end = p_end - center
                new_normal = v_center_to_start.cross(v_center_to_end)
                magnitude = new_normal.magnitude
                if magnitude < 1e-9:
                    print(f"WARNUNG: Bogen-Punkte kollinear für Zeile {row_index}")
                    return
                new_normal = new_normal.normalize()

                ocs = OCS(new_normal)
                ocs_start_vec = ocs.from_wcs(v_center_to_start)
                ocs_end_vec = ocs.from_wcs(v_center_to_end)
                new_start_angle = math.degrees(math.atan2(ocs_start_vec.y, ocs_start_vec.x))
                new_end_angle = math.degrees(math.atan2(ocs_end_vec.y, ocs_end_vec.x))
                if new_start_angle < 0: new_start_angle += 360
                if new_end_angle < 0: new_end_angle += 360

                self.all_entities_df.at[row_index, 'Radius'] = new_radius
                self.all_entities_df.at[row_index, 'NormalX'] = new_normal.x
                self.all_entities_df.at[row_index, 'NormalY'] = new_normal.y
                self.all_entities_df.at[row_index, 'NormalZ'] = new_normal.z
                self.all_entities_df.at[row_index, 'StartAngle'] = new_start_angle
                self.all_entities_df.at[row_index, 'EndAngle'] = new_end_angle
                print(f"DEBUG: Bogen-Parameter neu berechnet für Zeile {row_index}: R={new_radius:.4f}, CZ={new_center_z:.4f}")
            else:
                # Nur ein Z-Wert vorhanden: CenterZ übernehmen, Radius bleibt wie im Original oder wird auf NaN gesetzt
                self.all_entities_df.at[row_index, 'Radius'] = np.nan
                self.all_entities_df.at[row_index, 'NormalX'] = np.nan
                self.all_entities_df.at[row_index, 'NormalY'] = np.nan
                self.all_entities_df.at[row_index, 'NormalZ'] = np.nan
                self.all_entities_df.at[row_index, 'StartAngle'] = np.nan
                self.all_entities_df.at[row_index, 'EndAngle'] = np.nan
                print(f"DEBUG: Bogen-Parameter (nur CenterZ) für Zeile {row_index}: CZ={new_center_z:.4f}")

            self.all_entities_df.at[row_index, 'CenterZ'] = new_center_z

        except Exception as e:
            print(f"DEBUG: Fehler beim Neuberechnen der Bogen-Parameter: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")

    def update_z_coordinates(self, updated_df):
        """Aktualisiert die Z-Koordinaten und berechnet ARC-Parameter neu."""
        try:
            print("DEBUG GM: Starte Z-Koordinaten-Update...")
            
            # Merge die Z-Koordinaten basierend auf der ID
            if 'ID' not in self.all_entities_df.columns or 'ID' not in updated_df.columns:
                raise ValueError("Beide DataFrames müssen ID-Spalten haben")
            
            # Spalten, die aktualisiert werden sollen
            z_columns = ['StartZ', 'EndZ', 'CenterZ']
            status_columns = [col for col in updated_df.columns if col.endswith('_Status')]
            update_columns = z_columns + status_columns
            
            # Filtere nur verfügbare Spalten
            available_columns = [col for col in update_columns if col in updated_df.columns]
            
            if not available_columns:
                print("DEBUG GM: Keine Z-Spalten zum Update gefunden")
                return
            
            # Aktualisiere Zeile für Zeile basierend auf ID
            updates_applied = 0
            arcs_to_recalculate = []
            
            for _, updated_row in updated_df.iterrows():
                updated_id = updated_row['ID']
                
                # Finde entsprechende Zeile in all_entities_df
                mask = self.all_entities_df['ID'] == updated_id
                matching_indices = self.all_entities_df.index[mask]
                
                if len(matching_indices) == 0:
                    print(f"WARNING: ID '{updated_id}' not found in all_entities_df. Skipping row.")
                    continue
                idx = matching_indices[0]  # Nimm die erste Übereinstimmung
                
                # Aktualisiere verfügbare Spalten
                for col in available_columns:
                    if col in updated_row and pd.notna(updated_row[col]):
                        old_value = self.all_entities_df.at[idx, col] if col in self.all_entities_df.columns else "N/A"
                        self.all_entities_df.at[idx, col] = updated_row[col]
                        print(f"DEBUG GM: ID {updated_id}, {col}: {old_value} -> {updated_row[col]}")
                
                # Prüfe, ob es sich um einen ARC handelt
                if self.all_entities_df.at[idx, 'EntityType'] == 'ARC':
                    # Prüfe, ob StartZ oder EndZ definiert sind
                    has_start_z = pd.notna(self.all_entities_df.at[idx, 'StartZ'])
                    has_end_z = pd.notna(self.all_entities_df.at[idx, 'EndZ'])
                    
                    if has_start_z or has_end_z:
                        arcs_to_recalculate.append(idx)
                
                updates_applied += 1
            
            # Berechne ARC-Parameter neu
            for idx in arcs_to_recalculate:
                arc_row = self.all_entities_df.iloc[idx]
                self._recalculate_arc_points(idx, arc_row)
            
            print(f"DEBUG GM: {updates_applied} Zeilen aktualisiert, {len(arcs_to_recalculate)} ARC-Parameter neu berechnet")
            
        except Exception as e:
            print(f"DEBUG GM: Fehler beim Z-Koordinaten-Update: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
            
    def get_updated_dataframe(self):
        """Gibt den aktuellen DataFrame mit allen Änderungen zurück."""
        return self.all_entities_df.copy()

    def on_geometry_row_modified(self, row_index, updated_data):
        success = self.geometry_manager.update_geometry_row(row_index, updated_data)
        if success:
            updated_row = self.geometry_manager.all_entities_df.iloc[row_index]
            for col in updated_row.index:
                self.model._data_frame.at[row_index, col] = updated_row[col]
            top_left = self.model.index(row_index, 0)
            bottom_right = self.model.index(row_index, self.model.columnCount() - 1)
            self.model.dataChanged.emit(top_left, bottom_right, [QtCore.Qt.DisplayRole])

