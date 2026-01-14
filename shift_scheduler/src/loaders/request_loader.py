import pandas as pd
import os
from typing import List
from datetime import datetime
from ..models.request import Request

class RequestLoader:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir

    def load(self, month: str, name_to_id: dict = None) -> List[Request]:
        """
        Load requests for a specific month (YYYY-MM).
        Expects file: 予定申請_YYYYMM.csv
        Optionally uses name_to_id map to resolve Staff IDs from Names (fixing ID mismatch).
        """
        # Remove hyphen for filename: 2025-12 -> 202512
        month_str = month.replace('-', '')
        file_name = f"予定申請_{month_str}.csv"
        file_path = os.path.join(self.base_dir, file_name)
        
        requests = []
        if not os.path.exists(file_path):
            # Try generic filename
            fallback_path = os.path.join(self.base_dir, "予定申請.csv")
            if os.path.exists(fallback_path):
                file_path = fallback_path
                print(f"Loading generic request file: {file_path}")
            else:
                print(f"Warning: Request file not found: {file_path}")
                return requests
            
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
            
            # Detect format based on columns
            if 'HolidaySymbol' in df.columns:
                print(f"Detected 'HolidaySymbol' format in {file_name}")
                for _, row in df.iterrows():
                    try:
                        # Skip empty rows (Sample Data)
                        if pd.isna(row['PPPDate']) or pd.isna(row['HolidaySymbol']) or pd.isna(row['RSName']):
                            continue
                        if 'Sample Data' in str(row['RSName']):
                            continue
                            
                        date_val = pd.to_datetime(row['PPPDate']).date()
                        
                        # Parse Staff ID from "03 Name"
                        rs_name = str(row['RSName']).strip()
                        
                        staff_id = None
                        
                        # Try Name Resolution
                        if name_to_id:
                            # Assume format "ID Name" or just "Name"
                            # Try matching name against keys?
                            # OR Extract name part
                            import re
                            # Remove leading digits and whitespace
                            name_part = re.sub(r'^[\d]+\s*', '', rs_name)
                            if name_part in name_to_id:
                                staff_id = name_to_id[name_part]
                        
                        if not staff_id:
                            # Fallback to ID parsing
                            parts = re.split(r'\s+', rs_name)
                            raw_id = parts[0] if parts else rs_name
                            
                            # Normalize ID: "03" -> "T003"
                            if raw_id.isdigit():
                                staff_id = f"T{int(raw_id):03d}"
                            else:
                                staff_id = raw_id
                        
                        requests.append(Request(
                            staff_id=staff_id,
                            date=date_val,
                            symbol=str(row['HolidaySymbol']),
                            note=""
                        ))
                    except Exception as e:
                        print(f"Error parsing row {row}: {e}")
            else:
                # Standard format
                for _, row in df.iterrows():
                    try:
                        date_val = pd.to_datetime(row['日付']).date()
                        requests.append(Request(
                            staff_id=str(row['技師ID']),
                            date=date_val,
                            symbol=str(row['記号']),
                            note=str(row['備考']) if pd.notna(row['備考']) else ""
                        ))
                    except Exception as e:
                        print(f"Error parsing request row: {e}")
                        
        except Exception as e:
            print(f"Error reading request file: {e}")
            
        return requests
