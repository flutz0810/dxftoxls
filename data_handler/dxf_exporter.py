import ezdxf
import pandas as pd

def export_dataframe_to_dxf(file_path: str, data_frame: pd.DataFrame):
    """
    Exports entities from a DataFrame to a DXF file.
    Supports LINE, ARC, and CIRCLE (case-insensitive).
    """
    if data_frame is None or data_frame.empty:
        return False, "The DataFrame is empty. Nothing to export."

    try:
        doc = ezdxf.new()
        msp = doc.modelspace()
        entities_exported = 0

        for index, row in data_frame.iterrows():
            try:
                # Safely get and normalize EntityType
                entity_type = row.get('EntityType', '').upper()
                layer = row.get('Layer', '0')
                dxfattribs = {'layer': layer}

                if entity_type == 'LINE':
                    start = (row['StartX'], row['StartY'], row['StartZ'])
                    end = (row['EndX'], row['EndY'], row['EndZ'])
                    msp.add_line(start, end, dxfattribs=dxfattribs)
                    entities_exported += 1

                elif entity_type == 'ARC':
                    center = (row['CenterX'], row['CenterY'], row['CenterZ'])
                    radius = row['Radius']
                    start_angle = row['StartAngle']
                    end_angle = row['EndAngle']
                    normal = (row.get('NormalX', 0), row.get('NormalY', 0), row.get('NormalZ', 1))
                    dxfattribs['extrusion'] = normal
                    msp.add_arc(center=center, radius=radius, start_angle=start_angle, end_angle=end_angle, dxfattribs=dxfattribs)
                    entities_exported += 1

                elif entity_type == 'CIRCLE':
                    center = (row['CenterX'], row['CenterY'], row['CenterZ'])
                    radius = row['Radius']
                    normal = (row.get('NormalX', 0), row.get('NormalY', 0), row.get('NormalZ', 1))
                    dxfattribs['extrusion'] = normal
                    msp.add_circle(center=center, radius=radius, dxfattribs=dxfattribs)
                    entities_exported += 1

            except (KeyError, TypeError) as e:
                print(f"Skipping row {index} ({row.get('EntityType', 'N/A')}) due to error: {e}")
                continue
        
        if entities_exported == 0:
            return False, "No exportable entities (LINE, ARC, CIRCLE) found in the data."

        doc.saveas(file_path)
        return True, f"{entities_exported} entities successfully exported to {file_path}."

    except Exception as e:
        return False, f"An unexpected error occurred during DXF export: {e}"