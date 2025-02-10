import base64
import pandas as pd
from io import BytesIO

def read_file(contents,filename):
    print('---read_file----')
    if contents is not None:
         # Process the uploaded file and extract data
        content_type, content_string = contents.split(',')
        decoded = base64.b64decode(content_string)
        # Read the Excel file into a pandas DataFrame, selecting the specified sheet and skipping rows
        xls = pd.ExcelFile(BytesIO(decoded))

        try:
            # Try to read the 'MasterGAP' sheet
            df = pd.read_excel(BytesIO(decoded), sheet_name='MasterGAP', header=None)
            sheet__name='MasterGAP'
            print('----MasterGAP found---')
        except ValueError:
            try: 
                
                if len(xls.sheet_names) == 1:
                
                    # If there is only one sheet, read that
                    df = pd.read_excel(BytesIO(decoded), sheet_name=xls.sheet_names[0], header=None)
                    sheet__name=xls.sheet_names[0]
                    print(f'------ df imported from the only available sheet: {xls.sheet_names[0]} ------')

            except ValueError:
                print('Sheet "MasterGAP or DSA GAP overview" not found. .')
            
            
            
        # If the specified sheet is not found, check the number of sheets
        # Find the row that contains "Crop", "Crops", or "crop"
        header_row_index = None
        for index, row in df.iterrows():
            # Convert the row to a lowercased string list, ignoring None values
            row_str_lower = ' '.join([str(cell).lower() for cell in row if cell is not None])
                
            phi_present = "phi" in row_str_lower # Check if "PHI" is present in the row
            
            crop_present = "crop" in row_str_lower or "crops" in row_str_lower # Check if either "crop" or "crops" is present in the row
            print(phi_present,crop_present)
            # If both conditions are met, this is the header row
            if phi_present and crop_present:
                header_row_index = index 
                print(f'------ Header row found at index {header_row_index} ------')
                break

        if header_row_index is None:
            print('Error: No valid column names found in the data.')
            return  # Optionally return or handle the error as needed   
            
        # Read the DataFrame starting from the header row
        df = pd.read_excel(BytesIO(decoded), sheet_name=sheet__name, skiprows=header_row_index)
        # Update the column name to replace '\n' with a space
        return df
    print('nothing yet')
    return  # Optionally return or handle the error as needed   
# Define a function to simplify crop names
def simplify_crops(crop):
    crop_list = ['Barley', 'Wheat','Cabbage','Onion','Rape']  # Uppercase sensitive
    for item in crop_list:
        if item in crop:
            return item
    return crop


def data_harmonization(df):
    print('--- data_harmonization start ---')
    rest_columns= [col for col in df.columns if col.lower() in [name.lower() for name in ['Zone','Regulatory Zone' ,
                                                                                            'Residue region','Residues region',
                                                                                            'Product\n(PLT short)','Product',
                                                                                            'Crop',
                                                                                            'applicationn timing BBCH end','application timing BBCH end','BBCH latest',
                                                                                            'Max # of applns.\n(per block)','Max total # of apps',
                                                                                            'PHI', 'PHI\n(days)',
                                                                                            'Minimum appl. interval\n(days)', 'Overall min interval\n(days)']]]

    # Select specific columns from the needed dataframe and correct column names
    cgap_df = df[rest_columns+ [col for col in df.columns if (col.startswith("Application rate") or col.startswith("Max single")) and col.endswith("(g/ha)")]]
    cgap_df.columns = cgap_df.columns.str.replace('\n', '')
    # Rename columns based on conditions
    new_columns = []
    for col in cgap_df.columns:
        if 'Zone' in col:
            new_columns.append('Regulatory Zone')
        elif 'region' in col:
            new_columns.append('Residue region')
        elif 'Product' in col:
            new_columns.append('Product')
        elif 'Crop' in col:
            new_columns.append('Crop')
        elif 'BBCH' in col:
            new_columns.append('BBCH latest')
        elif 'PHI' in col:
            new_columns.append('PHI')
        elif ('interval' in col )or ('Interval' in col):
            print('---------------')
            new_columns.append('Interval (Days)')
        elif '# of' in col:
            new_columns.append('Max # of applns')
        else:
            new_columns.append(col)  # Keep the original name if no conditions are met
    #print(new_columns)
    # Assign the new column names to the DataFrame
    cgap_df.columns = new_columns
    # Remove rows containing specific crops
    cgap_df['Crop'] = cgap_df['Crop'].fillna('') 
    cgap_df = cgap_df[~cgap_df['Crop'].str.contains('rye|triticale|spelt|oat', case=False)]
    # Apply the simplify_crops function to the 'Crop' column
    cgap_df['Crop'] = cgap_df['Crop'].apply(simplify_crops)
    #print(cgap_df['Crop'].unique())
    
    return cgap_df
    


def calculate_critical_flag(df,rate_columns,region_columns):
    # Create a unique identifier for grouping
    df['group_id'] = df[region_columns] + '_' + df['Product'] + '_' + df['Crop']
    # Function to determine critical and most critical rows
    def determine_critical(group):
        if group[rate_columns].nunique() == 1:

            # If there's only one unique max applications, keep all as critical
            group['is_critical'] = True
        else:
            try:
                #print('there is more than 1 rate: so must be more that 1 application or many application but same rate')
            # Separate the rows based on the number of applications
                max_appln = group['Max # of applns'].max()
                lower_appln = group['Max # of applns'].min()

                # Get the rows for both max and lower applications
                max_row = group[group['Max # of applns'] == max_appln]
                lower_row = group[group['Max # of applns'] == lower_appln]
            
                if max_row[rate_columns].values[0] !='-':
                    # Determine if the max row is more critical
                    if max_row[rate_columns].values[0] >= lower_row[rate_columns].values[0]:
                        max_row['is_critical'] = True
                        lower_row['is_critical'] = False
                    else:
                        max_row['is_critical'] = True
                        lower_row['is_critical'] = True
                else:
                    print('there is a  -')
            except TypeError:
                print('no rate')
                max_row['is_critical'] = False
                lower_row['is_critical'] = False                
            # Combine the results
            group = pd.concat([max_row, lower_row])

        return group

    # Apply the function to each group and create an initial DataFrame
    df = df.groupby('group_id').apply(determine_critical).reset_index(drop=True)
    try: 
        # Now determine the most critical based on Product and Regulatory Zone
        most_critical = df.groupby([region_columns, 'Crop']).agg({
            'Max # of applns': 'max',
            rate_columns: 'max'
        }).reset_index()
    except TypeError:
        print('try : no rate')
        df.drop(columns=['group_id'], inplace=True)
        return df

    # Merge back to mark the most critical
    df = df.merge(most_critical, on=[region_columns, 'Crop'], suffixes=('', '_most'))
    # Determine if a row is the most critical
    df['is_most_critical'] = (
        (df['Max # of applns'] == df['Max # of applns_most']) &
        (df[rate_columns] == df[str(rate_columns+'_most')])
    )
    # Cleanup
    df.drop(columns=['group_id'], inplace=True)
    return df


