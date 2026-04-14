import pandas as pd
from app.normalize import normalize_for_db
from app.excel_to_db import STANDARD_COLUMNS


def test_normalize_basic():
    data = {
        'Location': ['Loc A'],
        'Name': ['Corn'],
        'Delivery': ['Jan 2027'],
        'Futures Month': ['May 2026'],
        'Futures Price': ['450'],
        'Basis': ['+5'],
        'Bushel Cash Price': ['$4.50'],
        'MT Cash Price': ['165.00'],
        'Source': ['TestSource'],
    }
    df = pd.DataFrame(data)
    out = normalize_for_db(df)
    # Ensure all STANDARD_COLUMNS are present
    for c in STANDARD_COLUMNS:
        assert c in out.columns
    # Plus source_sheet
    assert 'source_sheet' in out.columns
    # Check data mapping
    assert out.loc[0, 'location'] != ''
    assert out.loc[0, 'commodity'] != ''
