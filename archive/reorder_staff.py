import csv

def reorder_csv(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = list(csv.reader(f))
        
    header = reader[0]
    rows = reader[1:]
    
    # Store rows to move
    satomi_row = None
    tanamachi_row = None
    
    # Keep others
    rest_rows = []
    
    for row in rows:
        if not row or len(row) < 1:
            rest_rows.append(row)
            continue
        
        staff_id = row[0]
        if staff_id == 'T005':
            satomi_row = row
        elif staff_id == 'T062':
            tanamachi_row = row
        else:
            rest_rows.append(row)
            
    # Now find insertion points in rest_rows
    final_rows = []
    for row in rest_rows:
        final_rows.append(row)
        if not row or len(row) < 1:
            continue
            
        staff_id = row[0]
        if staff_id == 'T061' and satomi_row:
            final_rows.append(satomi_row)
        if staff_id == 'T040' and tanamachi_row:
            final_rows.append(tanamachi_row)
            
    with open(filepath, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(final_rows)

reorder_csv('/Users/kohei/Desktop/local-shift ver1/shift_scheduler/data/技師マスタ_確定版.csv')
reorder_csv('/Users/kohei/Desktop/local-shift ver1/shift_scheduler/data/スキルマスタ_確定版.csv')

print("Successfully reordered master CSV files.")
