import ezdxf
import pandas as pd

class DXFHandler:
    def __init__(self, file_path):
        self.file_path = file_path
        self.doc = ezdxf.read_file(file_path)

    def extract_data_from_dxf(self):
        """Extracts geometric data and texts from the DXF file."""
        geo_data = []
        text_data = []
        
        msp = self.doc.modelspace()
        # Iterate over all entities in modelspace
        for entity in msp:
            if entity.dxftype() in ['LINE', 'CIRCLE', 'ARC']:
                geo_data.append(self._extract_geometric_data(entity))
            
            elif entity.dxftype() == 'INSERT':
                self._extract_block_attributes(entity, text_data)

            elif entity.dxftype() == 'TEXT':
                text_data.append({
                    'ID': self._get_entity_id(entity),
                    'EntityType': 'TEXT',
                    'Layer': entity.dxf.layer,
                    'Color': entity.dxf.color,
                    'Text': entity.dxf.text,
                    'InsertX': entity.dxf.insert.x,
                    'InsertY': entity.dxf.insert.y,
                    'InsertZ': entity.dxf.insert.z,
                    'Rotation': entity.dxf.rotation,
                    'BlockName': None
                })
        
        geo_df = pd.DataFrame(geo_data)
        text_df = pd.DataFrame(text_data)
        
        return geo_df, text_df

    def _extract_geometric_data(self, entity):
        """Extracts geometric data from an entity."""
        if entity.dxftype() == 'LINE':
            return {
                'ID': entity.dxf.handle,
                'EntityType': 'LINE',
                'Layer': entity.dxf.layer,
                'Color': entity.dxf.color,
                'StartX': entity.dxf.start.x,
                'StartY': entity.dxf.start.y,
                'EndX': entity.dxf.end.x,
                'EndY': entity.dxf.end.y
            }
        elif entity.dxftype() == 'CIRCLE':
            return {
                'ID': entity.dxf.handle,
                'EntityType': 'CIRCLE',
                'Layer': entity.dxf.layer,
                'Color': entity.dxf.color,
                'CenterX': entity.dxf.center.x,
                'CenterY': entity.dxf.center.y,
                'Radius': entity.dxf.radius
            }
        elif entity.dxftype() == 'ARC':
            return {
                'ID': entity.dxf.handle,
                'EntityType': 'ARC',
                'Layer': entity.dxf.layer,
                'Color': entity.dxf.color,
                'CenterX': entity.dxf.center.x,
                'CenterY': entity.dxf.center.y,
                'Radius': entity.dxf.radius,
                'StartAngle': entity.dxf.start_angle,
                'EndAngle': entity.dxf.end_angle
            }

    def _extract_block_attributes(self, entity, text_data):
        """Extracts attributes from a block reference (INSERT)."""
        if entity.attribs:
            insert_point = entity.dxf.insert
            for attrib in entity.attribs:
                text_data.append({
                    'ID': attrib.dxf.handle,
                    'EntityType': 'TEXT_FROM_ATTRIBUTE',
                    'Layer': attrib.dxf.layer,
                    'Color': attrib.dxf.color,
                    'Text': attrib.dxf.text,
                    'InsertX': insert_point.x,
                    'InsertY': insert_point.y,
                    'InsertZ': insert_point.z,
                    'Rotation': attrib.dxf.rotation,
                    'BlockName': f"{entity.dxf.name} [{attrib.dxf.tag}]"
                })

    def _get_entity_id(self, entity):
        """Returns the ID of an entity (handle)."""
        return entity.dxf.handle