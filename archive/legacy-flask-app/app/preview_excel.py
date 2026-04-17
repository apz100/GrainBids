import pandas as pd

# Load the Ontario_CashBids Excel file and print the first few rows for inspection
def preview_excel():
    df = pd.read_excel('P:/Adam/Code/GrainBidsFrankenstine/Ontario_CashBids_2026-04-10.xlsx')
    print(df.head())

if __name__ == '__main__':
    preview_excel()
