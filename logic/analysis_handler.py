import pandas as pd
import numpy as np
from scipy.spatial import cKDTree

class AnalysisHandler:
    """
    Performs geometric analyses to associate text entities with geometric objects.
    Uses a k-d tree for efficient spatial search.
    """


    def analyze_text_geometry_proximity(self, geo_df: pd.DataFrame, text_df: pd.DataFrame, radius: float):
        """
        Hauptmethode für die Geometrie-Text-Analyse.
        
        Args:
            geo_df: DataFrame mit Geometrie-Daten
            text_df: DataFrame mit Text-Daten  
            radius: Suchradius für die Zuordnung
            
        Returns:
            DataFrame mit Zuordnungen zwischen Geometrie und Text
        """
        try:
            print(f"DEBUG AnalysisHandler: Starte Analyse mit {len(geo_df)} Geometrien und {len(text_df)} Texten")
            print(f"DEBUG AnalysisHandler: Suchradius: {radius}")
            
            if geo_df.empty or text_df.empty:
                print("DEBUG: Ein DataFrame ist leer")
                return pd.DataFrame()
            
            # Überprüfe erforderliche Spalten
            required_geo_cols = ['StartX', 'StartY', 'EndX', 'EndY', 'CenterX', 'CenterY', 'Radius']
            required_text_cols = ['InsertX', 'InsertY', 'Text']
            
            for col in required_geo_cols:
                if col not in geo_df.columns:
                    print(f"DEBUG: Fehlende Geometrie-Spalte: {col}")
                    
            for col in required_text_cols:
                if col not in text_df.columns:
                    print(f"DEBUG: Fehlende Text-Spalte: {col}")
            
            # Verwende die bestehende find_associations-Methode
            result_df = self.find_associations(
                geo_df=geo_df,
                text_df=text_df,
                search_radius=radius,
                line_offset=radius  # Für Linien verwenden wir den gleichen Radius
            )
            
            print(f"DEBUG AnalysisHandler: Analyse abgeschlossen. {len(result_df)} Zuordnungen gefunden.")
            return result_df
            
        except Exception as e:
            print(f"DEBUG AnalysisHandler Fehler: {e}")
            raise e

    def find_associations(self, geo_df: pd.DataFrame, text_df: pd.DataFrame, search_radius: float, line_offset: float):
        """
        Findet Zuordnungen zwischen Geometrie- und Text-Entitäten.
        Suche erfolgt nur in der X-Y-Ebene (Z-Koordinaten werden ignoriert).
        """
        if geo_df.empty or text_df.empty:
            return pd.DataFrame()
        
        associations = []
        
        # Text-Positionen für k-d-Baum vorbereiten (nur X,Y - Z wird ignoriert)
        text_positions = np.column_stack([
            text_df['InsertX'].astype(float),
            text_df['InsertY'].astype(float)
        ])
        
        # k-d-Baum für 2D-Suche erstellen
        text_tree = cKDTree(text_positions)
        
        for geo_idx, geo_row in geo_df.iterrows():
            geo_type = geo_row['EntityType'].upper()
            
            found_matches = []

            if geo_type == 'CIRCLE':
                # Kreismittelpunkt (nur X,Y)
                center = np.array([geo_row['CenterX'], geo_row['CenterY']])
                radius = geo_row['Radius']
                
                # Suche in erweitertem Radius
                query_radius = radius + search_radius
                indices = text_tree.query_ball_point(center, r=query_radius)
                
                for text_idx in indices:
                    # 2D-Distanz berechnen
                    text_pos_2d = text_positions[text_idx]
                    dist_to_center = np.linalg.norm(text_pos_2d - center)
                    
                    # Abstand zum Kreisrand
                    dist = abs(dist_to_center - radius)
                    
                    if dist <= search_radius:
                        text = text_df.iat[text_idx, text_df.columns.get_loc('Text')]
                        blockname = text_df.iat[text_idx, text_df.columns.get_loc('BlockName')]
                        text_with_coords = f"{text} [{text_pos_2d[0]:.2f}, {text_pos_2d[1]:.2f}]"
                        found_matches.append({'text': text_with_coords, 'blockname': blockname, 'distance': dist})
                        
            elif geo_type == 'ARC':
                # Arc-Mittelpunkt (nur X,Y)
                center = np.array([geo_row['CenterX'], geo_row['CenterY']])
                radius = geo_row['Radius']
                
                query_radius = radius + search_radius
                indices = text_tree.query_ball_point(center, r=query_radius)
                
                for text_idx in indices:
                    text_pos_2d = text_positions[text_idx]
                    dist_to_center = np.linalg.norm(text_pos_2d - center)
                    dist = abs(dist_to_center - radius)
                    
                    if dist <= search_radius:
                        text = text_df.iat[text_idx, text_df.columns.get_loc('Text')]
                        blockname = text_df.iat[text_idx, text_df.columns.get_loc('BlockName')]
                        text_with_coords = f"{text} [{text_pos_2d[0]:.2f}, {text_pos_2d[1]:.2f}]"
                        found_matches.append({'text': text_with_coords, 'blockname': blockname, 'distance': dist})
                        
            elif geo_type == 'LINE':
                # Linienpunkte (nur X,Y)
                p_start = np.array([geo_row['StartX'], geo_row['StartY']])
                p_end = np.array([geo_row['EndX'], geo_row['EndY']])
                line_midpoint = (p_start + p_end) / 2
                line_length = np.linalg.norm(p_start - p_end)
                
                query_radius = (line_length / 2) + line_offset
                indices = text_tree.query_ball_point(line_midpoint, r=query_radius)
                
                for text_idx in indices:
                    # 2D-Abstand zur Linie berechnen
                    text_pos_2d = text_positions[text_idx]
                    dist = self._point_to_line_segment_dist_2d(text_pos_2d, p_start, p_end)
                    
                    if dist <= line_offset:
                        text = text_df.iat[text_idx, text_df.columns.get_loc('Text')]
                        blockname = text_df.iat[text_idx, text_df.columns.get_loc('BlockName')]
                        text_with_coords = f"{text} [{text_pos_2d[0]:.2f}, {text_pos_2d[1]:.2f}]"
                        found_matches.append({'text': text_with_coords, 'blockname': blockname, 'distance': dist})
            
            # Zuordnung hinzufügen, wenn gefunden
            if found_matches:
                # Nach Distanz sortieren, um die kleinste für die Ausgabe zu erhalten
                found_matches.sort(key=lambda x: x['distance'])
                
                min_distance = found_matches[0]['distance']
                
                # Eindeutige Texte und Blocknamen sammeln
                unique_texts = sorted(list(set(match['text'] for match in found_matches)))
                unique_blocknames = sorted(list(set(str(match['blockname']) for match in found_matches if pd.notna(match['blockname']))))

                all_texts = "; ".join(unique_texts)
                all_blocknames = "; ".join(unique_blocknames)

                associations.append({
                    'GeometryID': geo_row['ID'],
                    'GeometryType': geo_type,
                    'GeometryLayer': geo_row['Layer'],
                    'AssociatedText': all_texts,
                    'TextBlockName': all_blocknames,
                    'Distance': round(min_distance, 4)
                })
        
        return pd.DataFrame(associations)

    def _point_to_line_segment_dist_2d(self, p, a, b):
        """Berechnet den 2D-Abstand von einem Punkt zu einem Liniensegment."""
        # Konvertiere zu 2D-Arrays falls nötig
        p = np.array(p[:2]) if len(p) > 2 else np.array(p)
        a = np.array(a[:2]) if len(a) > 2 else np.array(a)
        b = np.array(b[:2]) if len(b) > 2 else np.array(b)
        
        if np.array_equal(a, b):
            return np.linalg.norm(p - a)
        
        line_vec = b - a
        p_vec = p - a
        line_len_sq = np.dot(line_vec, line_vec)
        
        t = np.dot(p_vec, line_vec) / line_len_sq
        t = np.clip(t, 0.0, 1.0)
        
        nearest_point = a + t * line_vec
        return np.linalg.norm(p - nearest_point)