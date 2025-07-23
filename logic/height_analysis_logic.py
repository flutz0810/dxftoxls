import pandas as pd
import re
import numpy as np
from sklearn.neighbors import KNeighborsRegressor

class HeightAnalysisLogic:
    def __init__(self):
        self.model = None
        self.features = []
        self.df_processed = None # Speichert den für ML vorbereiteten DataFrame
        # Standard-Schlüsselwörter für Höhenextraktion
        self.height_keywords = ['OK', 'UK', 'KD']  # Default Werte

    def set_height_keywords(self, keywords_string):
        """
        Setzt die Schlüsselwörter für die Höhenextraktion.
        keywords_string: Komma-getrennte Liste von Schlüsselwörtern, z.B. "OK,UK,KD,SOK,SUK"
        """
        if keywords_string and keywords_string.strip():
            # Bereinige und splitte die Keywords
            keywords = [kw.strip().upper() for kw in keywords_string.split(',') if kw.strip()]
            self.height_keywords = keywords
            print(f"📋 Höhen-Schlüsselwörter gesetzt: {self.height_keywords}")
        else:
            # Fallback auf Standard-Keywords
            self.height_keywords = ['OK', 'UK', 'KD']
            print(f"📋 Standard Höhen-Schlüsselwörter verwendet: {self.height_keywords}")

    def extract_height_from_text(self, text, custom_keywords=None):
        """Extrahiert die Höhe aus dem Associated_Text mit bis zu 3 Nachkommastellen.
        Ignoriert dabei alles innerhalb von eckigen Klammern [x, y] da dies X/Y-Koordinaten sind.
        
        Args:
            text: Der zu durchsuchende Text
            custom_keywords: Liste von benutzerdefinierten Schlüsselwörtern (optional)
        """
        if pd.isna(text) or text is None:
            return None
        
        # Stelle sicher, dass text ein String ist
        text_str = str(text)
        
        # Entferne alle Inhalte innerhalb von eckigen Klammern [x, y]
        # Dies sind X/Y-Koordinaten des Textobjekts und sollen nicht als Höhe interpretiert werden
        text_cleaned = re.sub(r'\[.*?\]', '', text_str)
        
        # Verwende benutzerdefinierte Keywords oder Instanz-Keywords
        keywords = custom_keywords if custom_keywords else self.height_keywords
        
        # Suche nach verschiedenen Höhen-Mustern basierend auf den konfigurierten Schlüsselwörtern
        for keyword in keywords:
            pattern = f'{keyword}[\\s]*=([\\d]+\\.?[\\d]{{0,3}})'
            match = re.search(pattern, text_cleaned, re.IGNORECASE)
            if match:
                height = float(match.group(1))
                # Prüfe auf realistischen Höhenbereich
                if 50 <= height <= 1000:  # Erweiteter realistischer Bereich
                    return height
        
        # Auch ohne Bezeichnung - reine Zahlen in realistischem Bereich
        # Suche nach alleinstehenden Zahlen mit bis zu 3 Nachkommastellen
        number_match = re.search(r'(?<!\d)(\d{2,3}\.\d{1,3})(?!\d)', text_cleaned)
        if number_match:
            height = float(number_match.group(1))
            if 50 <= height <= 500:  # Realistischer Höhenbereich
                return height
        
        return None
    
    def extract_text_coordinates(self, text):
        """Extrahiert Koordinaten aus dem Associated_Text in eckigen Klammern [x, y]."""
        if pd.isna(text) or text is None:
            return None, None
        
        text_str = str(text)
        # Suche nach Koordinaten in eckigen Klammern, z.B. [123.45, 678.90]
        coord_match = re.search(r'\[(\d+\.?\d*),\s*(\d+\.?\d*)\]', text_str)
        if coord_match:
            return float(coord_match.group(1)), float(coord_match.group(2))
        
        return None, None
    
    def find_connected_lines_and_arcs(self, df_lines_arcs, tolerance=0.01):
        """
        Findet zusammenhängende Linien und Bögen basierend auf gemeinsamen Endpunkten.
        Optimiert für Layer-basierte Analyse.
        """
        lines = []
        
        # Erstelle optimierte Datenstruktur für diesen Layer
        for idx, row in df_lines_arcs.iterrows():
            if row['EntityType'] in ['LINE', 'ARC']:
                start_x, start_y = row['StartX'], row['StartY']
                end_x, end_y = row['EndX'], row['EndY']
                
                # Überspringe Linien/Bögen ohne gültige Koordinaten
                if pd.isna(start_x) or pd.isna(start_y) or pd.isna(end_x) or pd.isna(end_y):
                    continue
                
                lines.append({
                    'id': row['ID'],
                    'entity_type': row['EntityType'],
                    'layer': row.get('Layer', 'DEFAULT'),
                    'start': (float(start_x), float(start_y)),
                    'end': (float(end_x), float(end_y)),
                    'start_z': row.get('StartZ') if pd.notna(row.get('StartZ')) and row.get('StartZ') != 0.0 else np.nan,
                    'end_z': row.get('EndZ') if pd.notna(row.get('EndZ')) and row.get('EndZ') != 0.0 else np.nan,
                    'direct_height': row.get('Direct_Height', np.nan),
                    'text_coords': (row.get('TextX'), row.get('TextY')),
                    'associated_text': row.get('Associated_Text', ''),  # Hinzugefügt für intelligente Zuweisung
                    'row_idx': len(lines),  # Index in der lines-Liste
                    'original_idx': idx  # Behalte Original-Index für Debug
                })
        
        if not lines:
            return [], {}
        
        print(f"    🔗 Suche Verbindungen zwischen {len(lines)} Linien/Bögen im Layer...")
        
        # Baue Verbindungsgrph auf 
        connections = {}
        for i, line in enumerate(lines):
            connections[i] = []
            
            # Optimierung: Verwende räumliche Nähe für Vorfilterung
            for j, other_line in enumerate(lines[i+1:], i+1):  # Vermeide doppelte Prüfungen
                # Berechne alle möglichen Verbindungen effizient
                distances = [
                    self.point_distance(line['start'], other_line['start']),
                    self.point_distance(line['start'], other_line['end']),
                    self.point_distance(line['end'], other_line['start']),
                    self.point_distance(line['end'], other_line['end'])
                ]
                
                min_distance = min(distances)
                if min_distance <= tolerance:
                    connections[i].append(j)
                    # Bidirektionale Verbindung
                    if j not in connections:
                        connections[j] = []
                    connections[j].append(i)
        
        # Zähle gefundene Verbindungen
        total_connections = sum(len(conn) for conn in connections.values()) // 2  # Durch 2 wegen bidirektionaler Zählung
        print(f"    ✅ {total_connections} Verbindungen gefunden")
        
        return lines, connections
    
    def recalculate_arc_geometry(self, df_processed, arc_idx):
        """
        Berechnet die Bogen-Geometrie neu, wenn Start/End-Z-Werte geändert wurden.
        Für Bögen wird Center_Z ignoriert und neu berechnet, Radius und Normalvektor werden aktualisiert.
        """
        try:
            row = df_processed.loc[arc_idx]
            
            # Nur für Bögen
            if row['EntityType'] != 'ARC':
                return
            
            # Hol Start- und End-Koordinaten
            start_x, start_y, start_z = row['StartX'], row['StartY'], row['StartZ']
            end_x, end_y, end_z = row['EndX'], row['EndY'], row['EndZ']
            center_x, center_y = row['CenterX'], row['CenterY']
            
            # Überspringe wenn kritische Koordinaten fehlen
            if any(pd.isna(val) for val in [start_x, start_y, end_x, end_y, center_x, center_y]):
                return
            
            # Berechne neuen Radius (2D, da Z-Koordinaten variieren können)
            radius_start = np.sqrt((start_x - center_x)**2 + (start_y - center_y)**2)
            radius_end = np.sqrt((end_x - center_x)**2 + (end_y - center_y)**2)
            new_radius = (radius_start + radius_end) / 2  # Durchschnitt
            
            # Berechne Center_Z als Durchschnitt von Start und End
            new_center_z = None
            if pd.notna(start_z) and pd.notna(end_z):
                new_center_z = (start_z + end_z) / 2
                df_processed.loc[arc_idx, 'CenterZ'] = new_center_z
                df_processed.loc[arc_idx, 'CenterZ_Status'] = 'Berechnet'
            elif pd.notna(start_z):
                # Wenn nur Start-Z vorhanden, verwende diesen
                new_center_z = start_z
                df_processed.loc[arc_idx, 'CenterZ'] = new_center_z
                df_processed.loc[arc_idx, 'CenterZ_Status'] = 'Berechnet'
            elif pd.notna(end_z):
                # Wenn nur End-Z vorhanden, verwende diesen
                new_center_z = end_z
                df_processed.loc[arc_idx, 'CenterZ'] = new_center_z
                df_processed.loc[arc_idx, 'CenterZ_Status'] = 'Berechnet'
            
            # Aktualisiere Radius
            df_processed.loc[arc_idx, 'Radius'] = new_radius
            
            # Log-Meldung nur wenn CenterZ berechnet wurde
            if new_center_z is not None:
                print(f"    Bogen {row['ID']}: Radius={new_radius:.4f}, CenterZ={new_center_z:.4f}")
            else:
                print(f"    Bogen {row['ID']}: Radius={new_radius:.4f}, CenterZ=unverändert (keine Z-Werte)")
            
        except Exception as e:
            print(f"    Fehler bei Bogen-Neuberechnung für ID {row.get('ID', 'unknown')}: {e}")
    
    def find_connected_lines(self, df_lines, tolerance=0.01):
        """Legacy-Methode - wird durch find_connected_lines_and_arcs ersetzt."""
        return self.find_connected_lines_and_arcs(df_lines, tolerance)
    
    def point_distance(self, p1, p2):
        """Berechnet die Distanz zwischen zwei Punkten."""
        return np.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def assign_height_to_line_endpoints(self, line, text_height, text_coords):
        """Weist einer Linie die Höhe zu, basierend auf der Nähe zu den Textkoordinaten."""
        if text_coords[0] is None or text_coords[1] is None:
            # Wenn keine Textkoordinaten vorhanden, prüfe ob mehrere Texte im Associated_Text stehen
            associated_text = line.get('associated_text', '')
            if ';' in str(associated_text):
                # Mehrere Texte vorhanden - parse sie separat
                start_height, end_height = self.parse_text_elements_for_line_arc(
                    associated_text, 
                    line['start'][0], line['start'][1], 
                    line['end'][0], line['end'][1]
                )
                return start_height if start_height else text_height, end_height if end_height else text_height
            else:
                # Nur ein Text - beide Endpunkte gleich setzen
                return text_height, text_height
        
        # Berechne Distanz des Texts zu Start- und Endpunkt
        start_dist = self.point_distance((line['start'][0], line['start'][1]), text_coords)
        end_dist = self.point_distance((line['end'][0], line['end'][1]), text_coords)
        
        if start_dist <= end_dist:
            # Text ist näher am Startpunkt
            return text_height, np.nan
        else:
            # Text ist näher am Endpunkt
            return np.nan, text_height
    
    def propagate_heights_along_network(self, lines, connections):
        """
        Propagiert Höhen entlang des Liniennetzwerks.
        """
        if not lines:
            return lines
        
        max_iterations = 20  # Erhöht für komplexere Netzwerke
        tolerance = 0.01
        
        print(f"    Starte Höhenpropagation ({len(lines)} Linien)...")
        
        # Erste Phase: Text-Höhen zuweisen
        for i, line in enumerate(lines):
            if pd.notna(line['direct_height']):
                # Debug: Zeige Associated_Text für alle Linien
                if line['id'] in ['7F14', '7F0D', 'AB8']:  # Erweitere Debug
                    print(f"        🐛 DEBUG ID {line['id']}: Associated_Text = '{line.get('associated_text', 'NONE')}'")
                    print(f"        🐛 DEBUG ID {line['id']}: direct_height = {line['direct_height']}")
                    print(f"        🐛 DEBUG ID {line['id']}: text_coords = {line['text_coords']}")
                
                # Prüfe zuerst, ob mehrere Textelemente im Associated_Text vorhanden sind
                associated_text = line.get('associated_text', '')
                if ';' in str(associated_text) and associated_text:
                    # Mehrere Texte vorhanden - parse sie direkt
                    start_z, end_z = self.parse_text_elements_for_line_arc(
                        associated_text, 
                        line['start'][0], line['start'][1], 
                        line['end'][0], line['end'][1]
                    )
                    print(f"        📝 Mehrere Texte erkannt für ID {line['id']}: '{associated_text}'")
                    print(f"        📝 Zugewiesene Höhen: StartZ={start_z}, EndZ={end_z}")
                else:
                    # Nur ein Text - verwende intelligente Einzelzuweisung
                    start_z, end_z = self.assign_height_to_line_endpoints(
                        line, line['direct_height'], line['text_coords']
                    )
                
                if pd.notna(start_z):
                    line['start_z'] = start_z
                    print(f"        Text-Höhe: ID {line['id']} StartZ = {start_z}")
                
                if pd.notna(end_z):
                    line['end_z'] = end_z
                    print(f"        Text-Höhe: ID {line['id']} EndZ = {end_z}")
                    
                # Wenn beide NaN sind (sollte nicht passieren), setze beide auf direct_height
                if pd.isna(start_z) and pd.isna(end_z):
                    line['start_z'] = line['direct_height']
                    line['end_z'] = line['direct_height']
                    print(f"        Text-Höhe: ID {line['id']} StartZ = EndZ = {line['direct_height']}")
        
        # Zweite Phase: Iterative Netzwerk-Propagation
        for iteration in range(max_iterations):
            changes_made = False
            changes_this_iteration = 0
            
            for i, line in enumerate(lines):
                # Propagiere Höhen zu verbundenen Linien
                for connected_idx in connections.get(i, []):
                    if connected_idx >= len(lines):
                        continue
                        
                    connected_line = lines[connected_idx]
                    
                    # Finde gemeinsame Punkte und übertrage Höhen
                    # Start-Start Verbindung
                    if self.point_distance(line['start'], connected_line['start']) <= tolerance:
                        if pd.notna(line['start_z']) and pd.isna(connected_line['start_z']):
                            connected_line['start_z'] = line['start_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 Start→Start: ID {connected_line['id']} erhält StartZ = {line['start_z']} von ID {line['id']}")
                        elif pd.notna(connected_line['start_z']) and pd.isna(line['start_z']):
                            line['start_z'] = connected_line['start_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 Start←Start: ID {line['id']} erhält StartZ = {connected_line['start_z']} von ID {connected_line['id']}")
                    
                    # Start-End Verbindung
                    elif self.point_distance(line['start'], connected_line['end']) <= tolerance:
                        if pd.notna(line['start_z']) and pd.isna(connected_line['end_z']):
                            connected_line['end_z'] = line['start_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 Start→End: ID {connected_line['id']} erhält EndZ = {line['start_z']} von ID {line['id']}")
                        elif pd.notna(connected_line['end_z']) and pd.isna(line['start_z']):
                            line['start_z'] = connected_line['end_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 Start←End: ID {line['id']} erhält StartZ = {connected_line['end_z']} von ID {connected_line['id']}")
                    
                    # End-Start Verbindung
                    elif self.point_distance(line['end'], connected_line['start']) <= tolerance:
                        if pd.notna(line['end_z']) and pd.isna(connected_line['start_z']):
                            connected_line['start_z'] = line['end_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 End→Start: ID {connected_line['id']} erhält StartZ = {line['end_z']} von ID {line['id']}")
                        elif pd.notna(connected_line['start_z']) and pd.isna(line['end_z']):
                            line['end_z'] = connected_line['start_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 End←Start: ID {line['id']} erhält EndZ = {connected_line['start_z']} von ID {connected_line['id']}")
                    
                    # End-End Verbindung
                    elif self.point_distance(line['end'], connected_line['end']) <= tolerance:
                        if pd.notna(line['end_z']) and pd.isna(connected_line['end_z']):
                            connected_line['end_z'] = line['end_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 End→End: ID {connected_line['id']} erhält EndZ = {line['end_z']} von ID {line['id']}")
                        elif pd.notna(connected_line['end_z']) and pd.isna(line['end_z']):
                            line['end_z'] = connected_line['end_z']
                            changes_made = True
                            changes_this_iteration += 1
                            print(f"        📍 End←End: ID {line['id']} erhält EndZ = {connected_line['end_z']} von ID {connected_line['id']}")
            
            print(f"      Iteration {iteration + 1}: {changes_this_iteration} Änderungen")
            
            if not changes_made:
                print(f"   Konvergiert nach {iteration + 1} Iterationen")
                break
        
        # Dritte Phase: Lineare Interpolation für noch offene Endpunkte
        for iteration in range(3):  # Maximal 3 Iterationen für Interpolation
            changes_made = False
            
            for line in lines:
                if pd.notna(line['start_z']) and pd.isna(line['end_z']):
                    # Suche nach einer verbundenen Linie, die eine Höhe für den Endpunkt liefern kann
                    for connected_idx in connections.get(line['row_idx'], []):
                        if connected_idx >= len(lines):
                            continue
                        connected_line = lines[connected_idx]
                        
                        # Prüfe, ob eine Interpolation möglich ist
                        if (pd.notna(connected_line['start_z']) and pd.notna(connected_line['end_z'])):
                            # Bestimme, welcher Punkt der verbundenen Linie der Endpunkt unserer Linie ist
                            end_point = line['end']
                            if self.point_distance(end_point, connected_line['start']) <= tolerance:
                                line['end_z'] = connected_line['start_z']
                                changes_made = True
                                print(f"        🔗 Interpolation: ID {line['id']} EndZ = {connected_line['start_z']} (von verbundener Linie)")
                                break
                            elif self.point_distance(end_point, connected_line['end']) <= tolerance:
                                line['end_z'] = connected_line['end_z']
                                changes_made = True
                                print(f"        🔗 Interpolation: ID {line['id']} EndZ = {connected_line['end_z']} (von verbundener Linie)")
                                break
                
                elif pd.isna(line['start_z']) and pd.notna(line['end_z']):
                    # Suche nach einer verbundenen Linie, die eine Höhe für den Startpunkt liefern kann
                    for connected_idx in connections.get(line['row_idx'], []):
                        if connected_idx >= len(lines):
                            continue
                        connected_line = lines[connected_idx]
                        
                        # Prüfe, ob eine Interpolation möglich ist
                        if (pd.notna(connected_line['start_z']) and pd.notna(connected_line['end_z'])):
                            # Bestimme, welcher Punkt der verbundenen Linie der Startpunkt unserer Linie ist
                            start_point = line['start']
                            if self.point_distance(start_point, connected_line['start']) <= tolerance:
                                line['start_z'] = connected_line['start_z']
                                changes_made = True
                                print(f"        🔗 Interpolation: ID {line['id']} StartZ = {connected_line['start_z']} (von verbundener Linie)")
                                break
                            elif self.point_distance(start_point, connected_line['end']) <= tolerance:
                                line['start_z'] = connected_line['end_z']
                                changes_made = True
                                print(f"        🔗 Interpolation: ID {line['id']} StartZ = {connected_line['end_z']} (von verbundener Linie)")
                                break
            
            if not changes_made:
                break
        
        # Zähle finale Ergebnisse
        assigned_heights = sum(1 for line in lines if pd.notna(line['start_z']) or pd.notna(line['end_z']))
        print(f"    📊 {assigned_heights} von {len(lines)} Linien haben Höhen erhalten")
        
        return lines


    def prepare_data_for_line_interpolation(self, df_original):
        """
        Überarbeitete Methode mit intelligenter Text-Zuordnung.
        """
        df_processed = df_original.copy()

        # Basis-Setup (wie vorher)
        for col in ['StartZ', 'EndZ', 'CenterZ']:
            if col not in df_processed.columns:
                df_processed[col] = np.nan
            else:
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')

        # HINZUFÜGEN: Erstelle Direct_Height-Spalte aus Associated_Text
        print("📝 Extrahiere Höhen aus Associated_Text...")
        df_processed['Direct_Height'] = df_processed['Associated_Text'].apply(self.extract_height_from_text)
        df_processed['TextX'] = np.nan
        df_processed['TextY'] = np.nan

        # Extrahiere auch Text-Koordinaten
        for idx, row in df_processed.iterrows():
            if pd.notna(row['Associated_Text']):
                text_x, text_y = self.extract_text_coordinates(row['Associated_Text'])
                if text_x is not None and text_y is not None:
                    df_processed.loc[idx, 'TextX'] = text_x
                    df_processed.loc[idx, 'TextY'] = text_y


        # Erstelle Statusspalten
        df_processed['StartZ_Status'] = ''
        df_processed['EndZ_Status'] = ''
        df_processed['CenterZ_Status'] = ''

        # Markiere ursprünglich vorhandene Z-Werte (ungleich 0 und nicht NaN)
        # Aber nur wenn sie realistisch sind (zwischen 50 und 500 Meter)
        def is_realistic_height(z_value):
            if pd.isna(z_value) or z_value == 0:
                return False
            return -300 <= z_value <= 10000  # Realistischer Höhenbereich
        
        start_original = df_processed['StartZ'].apply(is_realistic_height)
        end_original = df_processed['EndZ'].apply(is_realistic_height)
        center_original = df_processed['CenterZ'].apply(is_realistic_height)
        
        df_processed.loc[start_original, 'StartZ_Status'] = 'Original'
        df_processed.loc[end_original, 'EndZ_Status'] = 'Original'
        df_processed.loc[center_original, 'CenterZ_Status'] = 'Original'
        
        # Setze unrealistische Z-Werte auf NaN
        unrealistic_start = df_processed['StartZ'].notna() & (df_processed['StartZ'] != 0) & (~start_original)
        unrealistic_end = df_processed['EndZ'].notna() & (df_processed['EndZ'] != 0) & (~end_original)
        unrealistic_center = df_processed['CenterZ'].notna() & (df_processed['CenterZ'] != 0) & (~center_original)
        
        if unrealistic_start.any():
            print(f"⚠️ {unrealistic_start.sum()} unrealistische StartZ-Werte werden ignoriert")
            df_processed.loc[unrealistic_start, 'StartZ'] = np.nan
        if unrealistic_end.any():
            print(f"⚠️ {unrealistic_end.sum()} unrealistische EndZ-Werte werden ignoriert")
            df_processed.loc[unrealistic_end, 'EndZ'] = np.nan
        if unrealistic_center.any():
            print(f"⚠️ {unrealistic_center.sum()} unrealistische CenterZ-Werte werden ignoriert")
            df_processed.loc[unrealistic_center, 'CenterZ'] = np.nan

        # Behandle Kreise separat - sie bekommen nur Text-Höhen für Center
        circle_mask = df_processed['EntityType'] == 'CIRCLE'
        circle_text_mask = circle_mask & df_processed['Direct_Height'].notna()
        df_processed.loc[circle_text_mask, 'CenterZ'] = df_processed.loc[circle_text_mask, 'Direct_Height']
        df_processed.loc[circle_text_mask, 'CenterZ_Status'] = 'Text'
        print(f"🔵 {circle_text_mask.sum()} Kreise mit Text-Höhen verarbeitet")

        # Behandle Text-Höhen für Linien und Bögen INTELLIGENT (nicht pauschal)
        line_arc_mask = df_processed['EntityType'].isin(['LINE', 'ARC'])
        line_arc_text_mask = line_arc_mask & df_processed['Direct_Height'].notna()
        
        print(f"📏 {line_arc_text_mask.sum()} Linien/Bögen mit Text-Höhen gefunden")
        
        # WICHTIG: Hier NICHT mehr die Höhen setzen - das passiert intelligent in der Propagation!
        # Wir setzen nur Debug-Ausgaben für betroffene Linien
        for idx in df_processed[line_arc_text_mask].index:
            entity_id = df_processed.loc[idx, 'ID']
            associated_text = df_processed.loc[idx, 'Associated_Text']
            if ';' in str(associated_text):
                print(f"    🎯 ID {entity_id}: Mehrere Textelemente erkannt - wird intelligent zugewiesen")
            else:
                print(f"    📍 ID {entity_id}: Einzelner Text - wird basierend auf Position zugewiesen")

        # Behandle Linien und Bögen pro Layer für Interpolation
        df_lines_arcs = df_processed[line_arc_mask].copy()
        
        if not df_lines_arcs.empty:
            # Gruppiere Linien/Bögen nach Layer
            unique_layers = df_lines_arcs['Layer'].unique()
            print(f"🔍 Verarbeite {len(unique_layers)} Layer: {list(unique_layers)}")
            
            for layer in unique_layers:
                layer_mask = df_processed['Layer'] == layer
                layer_line_arc_mask = layer_mask & line_arc_mask
                df_layer_lines = df_processed[layer_line_arc_mask].copy()
                
                if len(df_layer_lines) > 0:
                    print(f"  📋 Layer '{layer}': {len(df_layer_lines)} Linien/Bögen")
                    
                    # Führe Linienverfolgung für diesen Layer durch
                    lines, connections = self.find_connected_lines_and_arcs(df_layer_lines)
                    lines = self.propagate_heights_along_network(lines, connections)
                    
                    # Schreibe Ergebnisse für diesen Layer zurück
                    for line in lines:
                        row_idx = line['row_idx']
                        original_idx = df_layer_lines.index[row_idx]
                        
                        print(f"    🔄 Schreibe Ergebnisse für ID {line['id']}: start_z={line['start_z']}, end_z={line['end_z']}")
                        
                        # Start-Z - Verbesserte Logik mit intelligenter Überschreibung
                        if pd.notna(line['start_z']):
                            current_start_z = df_processed.loc[original_idx, 'StartZ']
                            current_start_status = df_processed.loc[original_idx, 'StartZ_Status']
                            
                            # Prüfe ob dies eine intelligente Text-Zuweisung ist (unterschiedliche Start/End-Höhen)
                            is_intelligent_assignment = (
                                pd.notna(line['start_z']) and 
                                pd.notna(line['end_z']) and 
                                line['start_z'] != line['end_z'] and
                                pd.notna(line['direct_height'])
                            )
                            
                            # Überschreibe wenn leer, 0.0, oder intelligente Zuweisung
                            should_overwrite = (
                                pd.isna(current_start_z) or 
                                current_start_z == 0.0 or 
                                current_start_status == '' or
                                is_intelligent_assignment
                            )
                            
                            if should_overwrite:
                                df_processed.loc[original_idx, 'StartZ'] = float(line['start_z'])
                                
                                # Bestimme Status basierend auf Herkunft
                                if is_intelligent_assignment:
                                    df_processed.loc[original_idx, 'StartZ_Status'] = 'Text-Intelligent'
                                elif pd.notna(line['direct_height']):
                                    df_processed.loc[original_idx, 'StartZ_Status'] = 'Text'
                                elif current_start_status == 'Original':
                                    # Behalte Original-Status
                                    pass
                                else:
                                    df_processed.loc[original_idx, 'StartZ_Status'] = 'Interpoliert'
                                
                                print(f"      ✅ StartZ gesetzt: {float(line['start_z'])} (Status: {df_processed.loc[original_idx, 'StartZ_Status']})")
                            else:
                                print(f"      ⏭️ StartZ bereits gesetzt: {current_start_z} (Status: {current_start_status})")
                        
                        # End-Z - Verbesserte Logik mit intelligenter Überschreibung
                        if pd.notna(line['end_z']):
                            current_end_z = df_processed.loc[original_idx, 'EndZ']
                            current_end_status = df_processed.loc[original_idx, 'EndZ_Status']
                            
                            # Prüfe ob dies eine intelligente Text-Zuweisung ist (unterschiedliche Start/End-Höhen)
                            is_intelligent_assignment = (
                                pd.notna(line['start_z']) and 
                                pd.notna(line['end_z']) and 
                                line['start_z'] != line['end_z'] and
                                pd.notna(line['direct_height'])
                            )
                            
                            # Überschreibe wenn leer, 0.0, oder intelligente Zuweisung
                            should_overwrite = (
                                pd.isna(current_end_z) or 
                                current_end_z == 0.0 or 
                                current_end_status == '' or
                                is_intelligent_assignment
                            )
                            
                            if should_overwrite:
                                df_processed.loc[original_idx, 'EndZ'] = float(line['end_z'])
                                
                                # Bestimme Status basierend auf Herkunft
                                if is_intelligent_assignment:
                                    df_processed.loc[original_idx, 'EndZ_Status'] = 'Text-Intelligent'
                                elif pd.notna(line['direct_height']):
                                    df_processed.loc[original_idx, 'EndZ_Status'] = 'Text'
                                elif current_end_status == 'Original':
                                    # Behalte Original-Status
                                    pass
                                else:
                                    df_processed.loc[original_idx, 'EndZ_Status'] = 'Interpoliert'
                                
                                print(f"      ✅ EndZ gesetzt: {float(line['end_z'])} (Status: {df_processed.loc[original_idx, 'EndZ_Status']})")
                            else:
                                print(f"      ⏭️ EndZ bereits gesetzt: {current_end_z} (Status: {current_end_status})")
                        
                        # Für Bögen: Geometrie neu berechnen
                        if df_processed.loc[original_idx, 'EntityType'] == 'ARC':
                            self.recalculate_arc_geometry(df_processed, original_idx)
        
        # Nach der Layer-basierten Interpolation: Koordinaten-Konsistenz sicherstellen
        df_processed = self.ensure_coordinate_consistency(df_processed)
        
        self.df_processed = df_processed
    
        return df_processed

    def train_and_predict(self, known_df, unknown_df):
        """
        Trainiert ein Modell und macht Vorhersagen.
        """
        # Sicherstellen, dass nur Features verwendet werden, die auch in known_df vorhanden sind
        current_features = [f for f in self.features if f in known_df.columns]
        
        if known_df.empty or known_df[current_features].isnull().any().any() or known_df['Direct_Height'].isnull().any():
            # Wenn keine bekannten Höhen vorhanden sind oder Trainingsdaten Lücken haben,
            # kann das Modell nicht sinnvoll trainiert werden.
            unknown_df['Predicted_Height'] = np.nan
            self.model = None # Setze Modell auf None, um anzuzeigen, dass nicht trainiert wurde
            return unknown_df

        X_train = known_df[current_features]
        y_train = known_df['Direct_Height']

        self.model = KNeighborsRegressor(n_neighbors=5)
        self.model.fit(X_train, y_train)

        if not unknown_df.empty:
            X_predict = unknown_df[current_features]
            # Sicherstellen, dass X_predict die gleichen Spalten wie X_train hat
            # und fehlende Spalten (falls durch Filterung entstanden) mit 0 oder Median füllen
            for col in current_features:
                if col not in X_predict.columns:
                    X_predict[col] = 0 # Oder füllen mit dem Median von X_train[col]
            
            predictions = self.model.predict(X_predict)
            unknown_df['Predicted_Height'] = predictions
        else:
            unknown_df['Predicted_Height'] = np.nan # Falls unknown_df leer ist

        return unknown_df
    def apply_text_assignments(self, df_processed, assignment_table):
        """
        Wendet die Text-Zuordnungen auf den DataFrame an.
        """
        for _, assignment in assignment_table.iterrows():
            entity_id = assignment['AssignedEntityID']
            assignment_type = assignment['AssignedTo']
            height = assignment['Height']
            
            # Finde entsprechende Zeile im DataFrame
            entity_rows = df_processed[df_processed['ID'] == entity_id]
            if entity_rows.empty:
                continue
                
            idx = entity_rows.index[0]
            
            # Setze Z-Wert basierend auf Zuordnungstyp
            if assignment_type == 'StartZ':
                df_processed.loc[idx, 'StartZ'] = height
                print(f"   📍 ID {entity_id}: StartZ = {height} (Text: {assignment['TextID']})")
            elif assignment_type == 'EndZ':
                df_processed.loc[idx, 'EndZ'] = height
                print(f"   📍 ID {entity_id}: EndZ = {height} (Text: {assignment['TextID']})")
            elif assignment_type == 'CenterZ':
                df_processed.loc[idx, 'CenterZ'] = height
                print(f"   📍 ID {entity_id}: CenterZ = {height} (Text: {assignment['TextID']})")
        
        return df_processed
    
    def get_text_assignment_table(self):
        """
        Gibt die Text-Zuordnungstabelle für Debugging zurück.
        """
        return getattr(self, 'text_assignment_table', pd.DataFrame())

    def update_processed_data(self, df_processed, record_id, entity_type, start_z=None, end_z=None, center_z=None):
        """
        Aktualisiert die Z-Werte im df_processed DataFrame basierend auf validierten Daten.
        Diese Methode wird von der UI aufgerufen, wenn ein Punkt manuell korrigiert wird.
        """
        # Finden des Index des zu aktualisierenden Eintrags im df_processed
        processed_row_idx = df_processed[(df_processed['ID'] == record_id) &
                                        (df_processed['EntityType'] == entity_type)].index

        if not processed_row_idx.empty:
            idx_to_update = processed_row_idx[0]
            
            # Aktualisiere Z-Werte direkt in den Hauptspalten
            if entity_type == 'LINE':
                if start_z is not None:
                    df_processed.loc[idx_to_update, 'StartZ'] = start_z
                    df_processed.loc[idx_to_update, 'StartZ_Status'] = 'Manuell'
                if end_z is not None:
                    df_processed.loc[idx_to_update, 'EndZ'] = end_z
                    df_processed.loc[idx_to_update, 'EndZ_Status'] = 'Manuell'
                    
            elif entity_type == 'ARC':
                if start_z is not None:
                    df_processed.loc[idx_to_update, 'StartZ'] = start_z
                    df_processed.loc[idx_to_update, 'StartZ_Status'] = 'Manuell'
                if end_z is not None:
                    df_processed.loc[idx_to_update, 'EndZ'] = end_z
                    df_processed.loc[idx_to_update, 'EndZ_Status'] = 'Manuell'
                # Für Bögen: Geometrie neu berechnen
                self.recalculate_arc_geometry(df_processed, idx_to_update)
                
            elif entity_type == 'CIRCLE':
                if center_z is not None:
                    df_processed.loc[idx_to_update, 'CenterZ'] = center_z
                    df_processed.loc[idx_to_update, 'CenterZ_Status'] = 'Manuell'
                    
        return df_processed
    
    def get_final_dataframe(self):
        """
        Gibt den finalen DataFrame zurück - die ursprüngliche Struktur bleibt erhalten.
        Z-Werte sind bereits direkt in den Hauptspalten (StartZ, EndZ, CenterZ).
        """
        if self.df_processed is None:
            return None
        
        # Entferne temporäre Spalten
        temp_columns = ['Direct_Height', 'TextX', 'TextY']
        df_final = self.df_processed.copy()
        
        # Entferne temporäre Spalten falls vorhanden
        for col in temp_columns:
            if col in df_final.columns:
                df_final = df_final.drop(columns=[col])
        
        return df_final
    
    def ensure_coordinate_consistency(self, df_processed, tolerance=0.01):
        """
        Stellt sicher, dass identische Koordinaten gleiche Höhen bekommen.
        """
        print(f"🔄 Stelle Koordinaten-Konsistenz sicher (Toleranz: {tolerance})...")
        
        # Sammle alle eindeutigen Koordinaten mit ihren Höhen
        coord_heights = {}  # (x, y) -> [list of heights]
        coord_to_indices = {}  # (x, y) -> [list of (idx, coord_type)]
        
        for idx, row in df_processed.iterrows():
            # Sammle Start-Koordinaten
            start_x, start_y, start_z = row.get('StartX'), row.get('StartY'), row.get('StartZ')
            if pd.notna(start_x) and pd.notna(start_y):
                coord_key = self.round_coordinate(start_x, start_y, tolerance)
                if coord_key not in coord_heights:
                    coord_heights[coord_key] = []
                    coord_to_indices[coord_key] = []
                
                if pd.notna(start_z) and start_z != 0.0:
                    coord_heights[coord_key].append(start_z)
                coord_to_indices[coord_key].append((idx, 'start'))
            
            # Sammle End-Koordinaten
            end_x, end_y, end_z = row.get('EndX'), row.get('EndY'), row.get('EndZ')
            if pd.notna(end_x) and pd.notna(end_y):
                coord_key = self.round_coordinate(end_x, end_y, tolerance)
                if coord_key not in coord_heights:
                    coord_heights[coord_key] = []
                    coord_to_indices[coord_key] = []
                
                if pd.notna(end_z) and end_z != 0.0:
                    coord_heights[coord_key].append(end_z)
                coord_to_indices[coord_key].append((idx, 'end'))
        
        # Konsistenz anwenden
        consistency_applied = 0
        for coord_key, heights in coord_heights.items():
            if len(heights) > 0:
                # Verwende die häufigste Höhe oder den Durchschnitt
                if len(set(heights)) == 1:
                    consensus_height = heights[0]
                else:
                    consensus_height = np.mean(heights)  # Durchschnitt bei unterschiedlichen Höhen
                
                # Wende Konsistenz auf alle Koordinaten mit dieser Position an
                indices_list = coord_to_indices[coord_key]
                for idx, coord_type in indices_list:
                    if coord_type == 'start':
                        current_z = df_processed.loc[idx, 'StartZ']
                        if pd.isna(current_z) or current_z == 0.0:
                            df_processed.loc[idx, 'StartZ'] = consensus_height
                            df_processed.loc[idx, 'StartZ_Status'] = 'Interpoliert'
                            consistency_applied += 1
                    elif coord_type == 'end':
                        current_z = df_processed.loc[idx, 'EndZ']
                        if pd.isna(current_z) or current_z == 0.0:
                            df_processed.loc[idx, 'EndZ'] = consensus_height
                            df_processed.loc[idx, 'EndZ_Status'] = 'Interpoliert'
                            consistency_applied += 1
        
        print(f"    ✅ {consistency_applied} Koordinaten-Konsistenzen angewendet")
        return df_processed
    
    def round_coordinate(self, x, y, tolerance):
        """Rundet Koordinaten für Konsistenz-Prüfung."""
        factor = 1.0 / tolerance
        return (round(x * factor) / factor, round(y * factor) / factor)
    
    def parse_associated_text_elements(self, df):
        """
        Parst Associated_Text und erstellt eine Tabelle mit allen Textelementen.
        Gibt einen DataFrame mit separaten Texteinträgen zurück.
        """
        text_assignments = []

        for idx, row in df.iterrows():
            associated_text = row.get('Associated_Text', '')
            if pd.isna(associated_text) or associated_text == '':
                continue

            # Parse mehrere Textelemente aus einem Associated_Text
            text_elements = self.extract_multiple_text_elements(str(associated_text))

            for i, text_element in enumerate(text_elements):
                if text_element['height'] is not None:
                    text_assignments.append({
                        'TextID': f"{row['ID']}_T{i+1}",
                        'Text': text_element['text'],
                        'Height': text_element['height'],
                        'TextX': text_element['x'],
                        'TextY': text_element['y'],
                        'SourceEntityID': row['ID'],
                        'SourceEntityType': row['EntityType'],
                        'AssignedTo': None,  # Wird später gesetzt
                        'AssignedEntityID': None,  # Wird später gesetzt
                        'Distance': None  # Wird später berechnet
                    })

        return pd.DataFrame(text_assignments)

    def extract_multiple_text_elements(self, text_str):
        """
        Extrahiert mehrere Textelemente aus einem Associated_Text String.
        Erkennt Muster wie: "OK Muffe=296.82 [-490.16, -103.18]; OK Muffe=298.26 [-485.44, -100.54]"
        """
        elements = []

        # Split by semicolon für mehrere Textelemente
        text_parts = text_str.split(';')

        for part in text_parts:
            part = part.strip()
            if not part:
                continue

            # Extrahiere Höhe
            height = self.extract_height_from_text(part)

            # Extrahiere Koordinaten
            x, y = self.extract_text_coordinates(part)

            if height is not None:
                elements.append({
                    'text': part,
                    'height': height,
                    'x': x,
                    'y': y
                })

        return elements

    def create_text_assignment_table(self, df_processed, text_df):
        """
        Erstellt eine intelligente Zuordnung zwischen Textelementen und Geometrie-Endpunkten.
        """
        assignments = []

        # Für jede Geometrie die besten Textzuordnungen finden
        for idx, row in df_processed.iterrows():
            entity_id = row['ID']
            entity_type = row['EntityType']

            if entity_type in ['LINE', 'ARC']:
                start_x, start_y = row['StartX'], row['StartY']
                end_x, end_y = row['EndX'], row['EndY']

                if pd.notna(start_x) and pd.notna(start_y) and pd.notna(end_x) and pd.notna(end_y):
                    # Finde nächsten Text für Startpunkt
                    start_assignment = self.find_nearest_text_for_point(
                        text_df, start_x, start_y, entity_id, 'StartZ'
                    )
                    if start_assignment:
                        assignments.append(start_assignment)

                    # Finde nächsten Text für Endpunkt (exclude bereits zugewiesene)
                    end_assignment = self.find_nearest_text_for_point(
                        text_df, end_x, end_y, entity_id, 'EndZ',
                        exclude_text_id=start_assignment['TextID'] if start_assignment else None
                    )
                    if end_assignment:
                        assignments.append(end_assignment)

            elif entity_type == 'CIRCLE':
                center_x, center_y = row['CenterX'], row['CenterY']

                if pd.notna(center_x) and pd.notna(center_y):
                    center_assignment = self.find_nearest_text_for_point(
                        text_df, center_x, center_y, entity_id, 'CenterZ'
                    )
                    if center_assignment:
                        assignments.append(center_assignment)

        return pd.DataFrame(assignments)

    def find_nearest_text_for_point(self, text_df, point_x, point_y, entity_id, assignment_type, exclude_text_id=None):
        """
        Findet den nächstgelegenen Text für einen bestimmten Punkt.
        """
        if text_df.empty:
            return None

        # Filter verfügbare Texte (exclude bereits zugewiesene)
        available_texts = text_df.copy()
        if exclude_text_id:
            available_texts = available_texts[available_texts['TextID'] != exclude_text_id]

        if available_texts.empty:
            return None

        # Berechne Distanzen zu allen verfügbaren Texten
        distances = []
        for _, text_row in available_texts.iterrows():
            if pd.notna(text_row['TextX']) and pd.notna(text_row['TextY']):
                dist = self.point_distance(
                    (point_x, point_y), 
                    (text_row['TextX'], text_row['TextY'])
                )
                distances.append(dist)
            else:
                distances.append(float('inf'))

        if not distances or min(distances) == float('inf'):
            return None

        # Finde nächsten Text
        min_idx = distances.index(min(distances))
        nearest_text = available_texts.iloc[min_idx]

        return {
            'TextID': nearest_text['TextID'],
            'Text': nearest_text['Text'],
            'Height': nearest_text['Height'],
            'TextX': nearest_text['TextX'],
            'TextY': nearest_text['TextY'],
            'AssignedEntityID': entity_id,
            'AssignedTo': assignment_type,
            'Distance': min(distances)
        }
    
    def parse_associated_text_elements(self, df):
        """
        Parst Associated_Text und erstellt eine Tabelle mit allen Textelementen.
        """
        text_assignments = []
        
        for idx, row in df.iterrows():
            associated_text = row.get('Associated_Text', '')
            if pd.isna(associated_text) or associated_text == '':
                continue
                
            # Parse mehrere Textelemente aus einem Associated_Text
            text_elements = self.extract_multiple_text_elements(str(associated_text))
            
            for i, text_element in enumerate(text_elements):
                if text_element['height'] is not None:
                    text_assignments.append({
                        'TextID': f"{row['ID']}_T{i+1}",
                        'Text': text_element['text'],
                        'Height': text_element['height'],
                        'TextX': text_element['x'],
                        'TextY': text_element['y'],
                        'SourceEntityID': row['ID'],
                        'SourceEntityType': row['EntityType'],
                        'AssignedTo': None,
                        'AssignedEntityID': None,
                        'Distance': None
                    })
        
        return pd.DataFrame(text_assignments)
    
    def extract_multiple_text_elements(self, text_str):
        """
        Extrahiert mehrere Textelemente aus einem Associated_Text String.
        """
        elements = []
        
        # Split by semicolon für mehrere Textelemente
        text_parts = text_str.split(';')
        
        for part in text_parts:
            part = part.strip()
            if not part:
                continue
                
            # Extrahiere Höhe
            height = self.extract_height_from_text(part)
            
            # Extrahiere Koordinaten
            x, y = self.extract_text_coordinates(part)
            
            if height is not None:
                elements.append({
                    'text': part,
                    'height': height,
                    'x': x,
                    'y': y
                })
        
        return elements
    
    def create_text_assignment_table(self, df_processed, text_df):
        """
        Erstellt eine intelligente Zuordnung zwischen Textelementen und Geometrie-Endpunkten.
        """
        assignments = []
        
        # Für jede Geometrie die besten Textzuordnungen finden
        for idx, row in df_processed.iterrows():
            entity_id = row['ID']
            entity_type = row['EntityType']
            
            if entity_type in ['LINE', 'ARC']:
                start_x, start_y = row['StartX'], row['StartY']
                end_x, end_y = row['EndX'], row['EndY']
                
                if pd.notna(start_x) and pd.notna(start_y) and pd.notna(end_x) and pd.notna(end_y):
                    # Finde nächsten Text für Startpunkt
                    start_assignment = self.find_nearest_text_for_point(
                        text_df, start_x, start_y, entity_id, 'StartZ'
                    )
                    if start_assignment:
                        assignments.append(start_assignment)
                    
                    # Finde nächsten Text für Endpunkt (exclude bereits zugewiesene)
                    end_assignment = self.find_nearest_text_for_point(
                        text_df, end_x, end_y, entity_id, 'EndZ',
                        exclude_text_id=start_assignment['TextID'] if start_assignment else None
                    )
                    if end_assignment:
                        assignments.append(end_assignment)
        
        return pd.DataFrame(assignments)
    
    def find_nearest_text_for_point(self, text_df, point_x, point_y, entity_id, assignment_type, exclude_text_id=None):
        """
        Findet den nächstgelegenen Text für einen bestimmten Punkt.
        """
        if text_df.empty:
            return None
        
        # Filter verfügbare Texte (exclude bereits zugewiesene)
        available_texts = text_df.copy()
        if exclude_text_id:
            available_texts = available_texts[available_texts['TextID'] != exclude_text_id]
        
        if available_texts.empty:
            return None
        
        # Berechne Distanzen zu allen verfügbaren Texten
        distances = []
        for _, text_row in available_texts.iterrows():
            if pd.notna(text_row['TextX']) and pd.notna(text_row['TextY']):
                dist = self.point_distance(
                    (point_x, point_y), 
                    (text_row['TextX'], text_row['TextY'])
                )
                distances.append(dist)
            else:
                distances.append(float('inf'))
        
        if not distances or min(distances) == float('inf'):
            return None
        
        # Finde nächsten Text
        min_idx = distances.index(min(distances))
        nearest_text = available_texts.iloc[min_idx]
        
        return {
            'TextID': nearest_text['TextID'],
            'Text': nearest_text['Text'],
            'Height': nearest_text['Height'],
            'TextX': nearest_text['TextX'],
            'TextY': nearest_text['TextY'],
            'AssignedEntityID': entity_id,
            'AssignedTo': assignment_type,
            'Distance': min(distances)
        }
    
    def point_distance(self, point1, point2):
        """Berechnet euklidische Distanz zwischen zwei Punkten."""
        import math
        return math.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)
    
    def parse_text_elements_for_line_arc(self, text_str, start_x, start_y, end_x, end_y):
        """
        Parst Textelemente und ordnet sie Start/End basierend auf Distanz zu.
        Falls keine Koordinaten verfügbar, nutze erste/letzte Höhe.
        """
        if pd.isna(text_str) or not text_str:
            return None, None
        
        text_elements = self.extract_multiple_text_elements(str(text_str))
        if len(text_elements) == 0:
            return None, None
        elif len(text_elements) == 1:
            # Nur ein Text - verwende für beide
            return text_elements[0]['height'], text_elements[0]['height']
        else:
            # Mehrere Texte - wähle basierend auf Distanz oder Position
            start_distances = []
            end_distances = []
            
            has_coordinates = False
            for elem in text_elements:
                if elem['x'] is not None and elem['y'] is not None:
                    has_coordinates = True
                    start_dist = self.point_distance((start_x, start_y), (elem['x'], elem['y']))
                    end_dist = self.point_distance((end_x, end_y), (elem['x'], elem['y']))
                    start_distances.append(start_dist)
                    end_distances.append(end_dist)
                else:
                    start_distances.append(float('inf'))
                    end_distances.append(float('inf'))
            
            if has_coordinates:
                # Finde besten Text für Start und End basierend auf Distanz
                start_idx = start_distances.index(min(start_distances)) if start_distances else 0
                end_idx = end_distances.index(min(end_distances)) if end_distances else 0
                
                return text_elements[start_idx]['height'], text_elements[end_idx]['height']
            else:
                # Keine Koordinaten verfügbar - verwende ersten für Start, letzten für End
                return text_elements[0]['height'], text_elements[-1]['height']