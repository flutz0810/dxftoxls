# data_handler/dxf_parser.py
import ezdxf
import pandas as pd
import numpy as np

class DXFParser:
    """
    A class for reading and parsing DXF files,
    extracting geometry and text entities into separate DataFrames.
    """
    def __init__(self):
        self.doc = None
        self.msp = None

    def _parse_all_blocks(self):
        """Collects all TEXT entities from *all* block definitions."""
        # CHANGED: Only collects texts, skips geometry from blocks
        block_text_data = []
        
        for block_name in self.doc.blocks.block_names():
            block_def = self.doc.blocks[block_name]
            for entity in block_def:
                handle = entity.dxf.handle if hasattr(entity.dxf, 'handle') else f"BlockDef_{id(entity)}"
                
                # Only parse text, skip geometry from blocks
                text_dict = self._parse_text(entity, handle)
                if text_dict:
                    block_text_data.append(text_dict)
                    continue

                # Nested INSERTs in block definitions
                if entity.dxftype() == 'INSERT':
                    nested_block_texts = self._parse_block(entity, handle)
                    if nested_block_texts:
                        block_text_data.extend(nested_block_texts)

        return [], block_text_data  # Empty list for geometry, only return texts

    def load_dxf(self, file_path: str):
        try:
            self.doc = ezdxf.readfile(file_path)
            print(f"DXF file successfully loaded: {file_path}")
            
            # Read all layer names (regardless of geometry)
            all_layer_names = [layer.dxf.name for layer in self.doc.layers]

        except (IOError, ezdxf.DXFStructureError, Exception) as e:
            print(f"ERROR opening / reading DXF: {e}")
            return None, None, []

        # Initialize
        entities_data = []
        text_data = []

        # 1) Iterate through all layouts - only for standalone geometries and standalone texts
        for layout in self.doc.layouts:
            for entity in layout:
                handle = entity.dxf.handle if hasattr(entity.dxf, 'handle') else f"AutoGen_{id(entity)}"

                # Parse geometry (only LINE, CIRCLE, ARC from layouts, not from blocks)
                geometry_dict = self._parse_geometry(entity, handle)
                if geometry_dict:
                    entities_data.append(geometry_dict)
                    continue

                # Parse text
                text_dict = self._parse_text(entity, handle)
                if text_dict:
                    text_data.append(text_dict)
                    continue

                # Parse block references (INSERT) to extract their attributes as text
                if entity.dxftype() == 'INSERT':
                    block_texts = self._parse_block(entity, handle)
                    if block_texts:
                        text_data.extend(block_texts)

        # Build DataFrames
        geometry_df = self._build_geometry_df(entities_data)
        text_df = self._build_text_df(text_data)

        print(f"Extraction complete: {len(geometry_df)} geometries, {len(text_df)} texts.")
        return geometry_df, text_df, all_layer_names

    def _build_geometry_df(self, entities_data):
        """Creates a DataFrame from the collected geometry data."""
        if not entities_data:
            print("INFO: No supported geometries (LINE, ARC, CIRCLE) found.")
            geom_cols = [
                'ID','EntityType','Layer','Color',
                'StartX','StartY','StartZ',
                'EndX','EndY','EndZ',
                'CenterX','CenterY','CenterZ',
                'Radius','NormalX','NormalY','NormalZ',
                'StartAngle','EndAngle'
            ]
            return pd.DataFrame(columns=geom_cols)
        return pd.DataFrame(entities_data)

    def _build_text_df(self, text_data):
        """Creates a DataFrame from the collected text data (TEXT, MTEXT, Block texts)."""
        if not text_data:
            print("INFO: No supported texts found.")
            text_cols = ['ID','EntityType','Layer','InsertX','InsertY','InsertZ','Text','BlockName']
            return pd.DataFrame(columns=text_cols)
        return pd.DataFrame(text_data)

    def _create_base_dict(self, entity, handle: str):
        """Creates a base dictionary with common attributes."""
        return {
            'ID': handle,
            'EntityType': entity.dxftype(),
            'Layer': entity.dxf.layer if hasattr(entity.dxf, 'layer') else '0',
            'Color': entity.dxf.color if hasattr(entity.dxf, 'color') else 256,
        }

    def _parse_geometry(self, entity, handle: str):
        """Parses a single geometric entity and returns a data dictionary."""
        entity_type = entity.dxftype()
        if entity_type not in {'LINE', 'CIRCLE', 'ARC'}:
            return None

        data = self._create_base_dict(entity, handle)
        # Initialize all possible geometric fields with NaN
        data.update({
            'StartX': np.nan, 'StartY': np.nan, 'StartZ': np.nan, 'EndX': np.nan, 'EndY': np.nan, 'EndZ': np.nan,
            'CenterX': np.nan, 'CenterY': np.nan, 'CenterZ': np.nan, 'Radius': np.nan,
            'NormalX': np.nan, 'NormalY': np.nan, 'NormalZ': np.nan, 'StartAngle': np.nan, 'EndAngle': np.nan
        })

        if entity_type == 'LINE':
            data.update({
                'StartX': entity.dxf.start.x, 'StartY': entity.dxf.start.y, 'StartZ': entity.dxf.start.z,
                'EndX': entity.dxf.end.x, 'EndY': entity.dxf.end.y, 'EndZ': entity.dxf.end.z
            })
        elif entity_type in ('CIRCLE', 'ARC'):
            data.update({
                'CenterX': entity.dxf.center.x, 'CenterY': entity.dxf.center.y, 'CenterZ': entity.dxf.center.z,
                'Radius': entity.dxf.radius,
                'NormalX': entity.dxf.extrusion.x, 'NormalY': entity.dxf.extrusion.y, 'NormalZ': entity.dxf.extrusion.z
            })
            if entity_type == 'ARC':
                data.update({
                    'StartAngle': entity.dxf.start_angle, 'EndAngle': entity.dxf.end_angle,
                    'StartX': entity.start_point.x, 'StartY': entity.start_point.y, 'StartZ': entity.start_point.z,
                    'EndX': entity.end_point.x, 'EndY': entity.end_point.y, 'EndZ': entity.end_point.z
                })
        return data
    
    def _parse_block(self, block_entity, handle: str):
        """
        Parses a block reference (INSERT).
        Prioritizes reading attributes (ATTRIB). Each attribute is treated as a
        separate text object.
        If no attributes are present, static texts (TEXT, MTEXT)
        in the block definition are searched.
        """
        if not block_entity.is_alive or block_entity.block() is None:
            return []

        found_texts = []
        block_name = block_entity.dxf.name

        # Priority 1: Read attributes directly attached to the block reference.
        # Each attribute is treated as a separate text object.
        if block_entity.attribs:
            for attrib in block_entity.attribs:
                # Use the handle of the attribute if available, otherwise generate one.
                attrib_handle = attrib.dxf.handle if hasattr(attrib.dxf, 'handle') else f"Attrib_{handle}_{attrib.dxf.tag}"
                data = self._create_base_dict(attrib, attrib_handle)
                
                # IMPORTANT: Use the layer of the block reference (INSERT), not the attribute's own layer.
                data['Layer'] = block_entity.dxf.layer if hasattr(block_entity.dxf, 'layer') else '0'
                
                # Adjust EntityType to clarify the origin.
                data['EntityType'] = 'ATTRIB'
                
                data.update({
                    'Text': attrib.dxf.text,
                    # The insertion point of the parent block is used for each attribute.
                    'InsertX': block_entity.dxf.insert.x,
                    'InsertY': block_entity.dxf.insert.y,
                    'InsertZ': block_entity.dxf.insert.z,
                    'Rotation': attrib.dxf.rotation if hasattr(attrib.dxf, 'rotation') else 0.0,
                    # Construct block name from BlockTableRecord and attribute tag.
                    'BlockName': f"{block_name} [{attrib.dxf.tag}]"
                })
                found_texts.append(data)
            
            # Return the list of all found attribute texts.
            return found_texts

        # Priority 2 (Fallback): Read static texts from the block definition.
        for sub_entity in block_entity.block():
            if sub_entity.dxftype() in {'TEXT', 'MTEXT'}:
                # Create base dictionary with block data
                data = self._create_base_dict(block_entity, handle)
                
                text_content = ""
                if sub_entity.dxftype() == 'TEXT':
                    text_content = sub_entity.dxf.text
                elif sub_entity.dxftype() == 'MTEXT':
                    if hasattr(sub_entity, 'plain_text'):
                        text_content = sub_entity.plain_text()
                    else:
                        text_content = sub_entity.text

                # Override EntityType with that of the text element
                data['EntityType'] = f"Block-{sub_entity.dxftype()}"
                
                # Update data
                data.update({
                    'Text': text_content,
                    # As requested, the insertion point of the block is used
                    'InsertX': block_entity.dxf.insert.x,
                    'InsertY': block_entity.dxf.insert.y,
                    'InsertZ': block_entity.dxf.insert.z,
                    'Rotation': block_entity.dxf.rotation if hasattr(block_entity.dxf, 'rotation') else 0.0,
                    'BlockName': block_name
                })
                found_texts.append(data)
        
        return found_texts

    def _parse_text(self, entity, handle: str):
        """Parses a single text entity and returns a data dictionary."""
        entity_type = entity.dxftype()
        if entity_type not in {'TEXT', 'MTEXT'}:
            return None

        data = self._create_base_dict(entity, handle)
        text_content = ""
        if entity_type == 'TEXT':
            text_content = entity.dxf.text
        elif entity_type == 'MTEXT':
            # For MTEXT, the content can be complex, here the plain text is extracted
            if hasattr(entity, 'plain_text'):
                text_content = entity.plain_text()
            else:
                text_content = entity.text  # Fallback

        data.update({
            'Text': text_content,
            'InsertX': entity.dxf.insert.x, 'InsertY': entity.dxf.insert.y, 'InsertZ': entity.dxf.insert.z,
            'Rotation': entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0.0,
            'BlockName': np.nan  # No block for standalone text
        })
        return data
    
    def get_document(self):
        """
        Returns the loaded ezdxf document object.
        
        This is useful for accessing the complete document after parsing,
        without having to read it again.
        """
        return self.doc