import pandas as pd

excel_path = 'P:/Adam/Code/GrainBids/Ontario_CashBids_2026-04-10.xlsx'

excel = pd.ExcelFile(excel_path)
print('Sheets:', excel.sheet_names)
for sheet in excel.sheet_names:
    df = pd.read_excel(excel_path, sheet_name=sheet)
    print(f'\nSheet: {sheet}')
    print('Columns:', list(df.columns))
    print('Sample row:', df.head(1).to_dict(orient='records'))
