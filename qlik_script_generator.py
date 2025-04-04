import yaml
import os
from pathlib import Path

def generate_das_qvs(
    script_path: Path,
    schema_path: Path
) -> None:
    """
    Generates Qlik Sense QVS scripts based on a YAML schema file.

    This function reads a YAML schema file to generate QVS scripts for loading data
    into Qlik Sense. It processes each table in the schema, constructing scripts
    that set up variables, define hash tables, check for existing QVD targets,
    load new data, calculate hash values, and store the data into QVD files.
    The function also adds comments based on field descriptions and logs the process.

    Steps:
    1. Reads the YAML schema to extract table and column definitions.
    2. Generates QVS scripts for each table, including variable setup, hash table
       definitions, data loading with incremental values, and storage operations.
    3. Writes the constructed QVS scripts to an output file.

    Output:
        Generates a QVS script file at the defined output path.
    """

    # Paths
    output_path = script_path / "data_according_to_system.qvs"
    
    # Read the YAML schema file
    with open(schema_path, 'r') as f:
        schema_data = yaml.safe_load(f)
    
    # Begin constructing the output
    output = []
    
    # Add header trace
    output.append("Trace")
    output.append("===============================================================")
    output.append("    DATA ACCORDING TO SYSTEM")
    output.append("    Script generated by Qlik Script Generator")
    output.append("===============================================================")
    output.append(";")
    
    # Process each table in the schema
    if 'tables' in schema_data:
        for table_name, table_info in schema_data['tables'].items():
            # Extract entity name from table name for primary key detection
            entity_name = table_name.split('__')[-1]
            
            # Generate table script from scratch based on template format
            table_lines = []
            
            # Table header
            table_lines.append("Trace")
            table_lines.append("---------------------------------------------------------------")
            table_lines.append(f"    Extracting {table_name}")
            table_lines.append("---------------------------------------------------------------")
            table_lines.append(";")
            
            # Variables setup
            table_lines.append("Trace Setting variables...;")
            table_lines.append(f"Let val__qvd_target = '$(val__qvd_path__das)/{table_name}.qvd';")
            table_lines.append("Let val__target_qvd_exists = Not IsNull(QvdCreateTime('$(val__qvd_target)'));")
            table_lines.append("Let val__incremental_value = '1970-01-01';")
            table_lines.append("")
            
            # Hash table definition
            table_lines.append("Trace Define hash table...;")
            table_lines.append("[processed_record_hashes]:")
            table_lines.append("Load")
            table_lines.append("    Null() As [old_record_hash]")
            table_lines.append("AutoGenerate 0")
            table_lines.append(";")
            table_lines.append("")
            
            # Check if target exists
            table_lines.append("Trace Checking if target QVD exists...;")
            table_lines.append("If $(val__target_qvd_exists) Then")
            table_lines.append("    Trace Target found, loading hashes and max incremental value...;")
            table_lines.append("")
            table_lines.append("    Concatenate([processed_record_hashes])")
            table_lines.append("    Load")
            table_lines.append("        [record_hash] As [old_record_hash]")
            table_lines.append("")
            table_lines.append("    From")
            table_lines.append("        [$(val__qvd_target)] (qvd)")
            table_lines.append("    ;")
            table_lines.append("")
            table_lines.append("    [max_incremental_value]:")
            table_lines.append("    Load")
            table_lines.append("        Date(Max(Num#([modified_date])), 'YYYY-MM-DD') As [max_incremental_value]")
            table_lines.append("    From")
            table_lines.append("        [$(val__qvd_target)] (qvd)")
            table_lines.append("    ;")
            table_lines.append("")
            table_lines.append("    Let val__incremental_value = Coalesce(Peek('max_incremental_value', -1, 'max_incremental_value'), '$(val__incremental_value)');")
            table_lines.append("    Drop Table [max_incremental_value];")
            table_lines.append("")
            table_lines.append("Else")
            table_lines.append("    Trace Target not found, starting full load...;")
            table_lines.append("")
            table_lines.append("End If")
            table_lines.append("")
            
            # Generate hash fields based on columns
            hash_fields = []
            field_load_lines = []
            field_comments = []
            
            if 'columns' in table_info:
                # Initialize field categories
                primary_keys = []
                foreign_keys = []
                regular_fields = []
                system_fields = []  # For rowguid and modified_date
                
                # Categorize fields
                for column_name, column_info in table_info['columns'].items():
                    if column_name.startswith('_dlt_'):
                        continue
                    elif column_name in ['rowguid', 'modified_date']:
                        system_fields.append((column_name, column_info))
                    elif column_name.endswith('_id') and entity_name in column_name:
                        # Primary key - if entity name is in the column name and it ends with _id
                        primary_keys.append((column_name, column_info))
                    elif column_name.endswith('_id'):
                        # Foreign key - any other column ending with _id
                        foreign_keys.append((column_name, column_info))
                    else:
                        # Regular fields - everything else
                        regular_fields.append((column_name, column_info))
                
                # Sort each category
                primary_keys.sort(key=lambda x: x[0])
                foreign_keys.sort(key=lambda x: x[0])
                regular_fields.sort(key=lambda x: x[0])
                system_fields.sort(key=lambda x: x[0])
                
                # Combine all fields in the desired order
                sorted_columns = primary_keys + foreign_keys + regular_fields + system_fields
                
                # Generate field lists
                for i, (column_name, column_info) in enumerate(sorted_columns):
                    # Add comma at the end of each line except the last one for hash fields
                    if i < len(sorted_columns) - 1:
                        hash_fields.append(f"    [{column_name}],")
                    else:
                        hash_fields.append(f"    [{column_name}]")
                    
                    # Same for field loading lines
                    if i < len(sorted_columns) - 1:
                        field_load_lines.append(f"    Text([{column_name}]) As [{column_name}],")
                    else:
                        field_load_lines.append(f"    Text([{column_name}]) As [{column_name}]")
                    
                    if 'description' in column_info:
                        # Escape single quotes in descriptions by replacing them with Chr(39)
                        desc = column_info['description']
                        desc = desc.replace("'", "$(=Chr39())")
                        field_comments.append(f"Comment Field [{column_name}] With '{desc}';")
            
            # Load new data with hash calculation
            table_lines.append("Trace Loading new data with incremental value $(val__incremental_value)...;")
            
            # Hash calculation
            table_lines.append("Set var__record_hash = Hash256(")
            table_lines.extend(hash_fields)
            table_lines.append(")")
            table_lines.append(";")
            table_lines.append("")
            
            # Table loading
            table_lines.append(f"[{table_name}]:")
            table_lines.append("Load")
            table_lines.append("    *,")
            table_lines.append("    $(var__record_hash) As [record_hash],")
            table_lines.append("    Timestamp#('$(val__utc)', 'YYYY-MM-DD hh:mm:ss.ffffff') As [record_loaded_at]")
            table_lines.append("")
            table_lines.append("Where")
            table_lines.append("    Not Exists ([old_record_hash], $(var__record_hash))")
            table_lines.append(";")
            table_lines.append("")
            
            # Field loading
            table_lines.append("Load")
            table_lines.extend(field_load_lines)
            table_lines.append("")
            table_lines.append("From")
            table_lines.append(f"    [lib://OneDrive - mattias.thalen@two.se/Qlik/Analytical Data Storage System/data/das.{table_name}.parquet] (parquet)")
            table_lines.append("")
            table_lines.append("Where")
            table_lines.append("    Date([modified_date], 'YYYY-MM-DD') >= Date#('$(val__incremental_value)', 'YYYY-MM-DD')")
            table_lines.append(";")
            table_lines.append("")
            
            # Cleanup and counting
            table_lines.append("Trace Dropping hash table...;")
            table_lines.append("Drop Table [processed_record_hashes];")
            table_lines.append("")
            table_lines.append("Trace Counting new records...;")
            table_lines.append(f"Set val__no_of_new_records = Alt(NoOfRows('{table_name}'), 0);")
            table_lines.append("")
            table_lines.append("Trace Checking if there are new records...;")
            table_lines.append("If $(val__no_of_new_records) > 0 Then")
            table_lines.append("")
            table_lines.append("    Trace Checking if target QVD exists...;")
            table_lines.append("    If $(val__target_qvd_exists) Then")
            table_lines.append("        Trace Appending previously ingested data...;")
            table_lines.append("")
            table_lines.append(f"        Concatenate([{table_name}])")
            table_lines.append("        Load * From [$(val__qvd_target)] (qvd) Where Not Exists ([record_hash]);")
            table_lines.append("")
            table_lines.append("    Else")
            table_lines.append("        Trace Target not found, skipping append...;")
            table_lines.append("")
            table_lines.append("    End If")
            table_lines.append("")
            
            # Comments
            if 'description' in table_info:
                table_lines.append("    Trace Commenting table...;")
                table_desc = table_info['description']
                table_desc = table_desc.replace("'", "$(=Chr39())")
                table_lines.append(f"    Comment Table [{table_name}] With '{table_desc}';")
                table_lines.append("")
            
            if field_comments:
                table_lines.append("    Trace Commenting fields...;")

                for comment in field_comments:
                    table_lines.append(f"    {comment}")
                
                table_lines.append("")
            
            # Storing and cleanup
            table_lines.append("    Trace Storing data...;")
            table_lines.append(f"    Store [{table_name}] Into [$(val__qvd_path__das)/{table_name}.qvd] (qvd);")
            table_lines.append("")
            table_lines.append("Else")
            table_lines.append("    Trace No new records loaded...;")
            table_lines.append("")
            table_lines.append("End If")
            table_lines.append("")
            table_lines.append("Trace Dropping table...;")
            table_lines.append(f"Drop Table [{table_name}];")
            table_lines.append("")
            table_lines.append("Trace Resetting variables...;")
            table_lines.append("Let val__qvd_target = Null();")
            table_lines.append("Let val__target_qvd_exists = Null();")
            table_lines.append("Let val__incremental_value = Null();")
            table_lines.append("Let var__record_hash = Null();")
            table_lines.append("Let val__no_of_new_records = Null();")
            table_lines.append("")
            
            # Add the table script to the output
            output.extend(table_lines)
            
    # Write the output file
    with open(output_path, 'w') as f:
        f.write('\n'.join(output))
    
    print(f"Generated QVS file at: {output_path}")

if __name__ == "__main__":
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))

    schema_path = BASE_DIR / "schemas" / "raw_schema.yaml"
    script_path = BASE_DIR / "scripts"

    generate_das_qvs(
        script_path=script_path,
        schema_path=schema_path
    )
