
import sys
import os
sys.path.append(os.getcwd())

from shift_scheduler.src.loaders.data_loader import DataLoader
from shift_scheduler.src.models.skill import SkillRank

def test():
    loader = DataLoader("shift_scheduler/data")
    
    print("--- 1. Testing Staff Loading ---")
    staff_list, _, _, _, _, _ = loader.load_all("2026-01")
    
    shimada = next((s for s in staff_list if "嶋田" in s.name), None)
    if not shimada:
        print("FAIL: Shimada not found in staff_list")
        return
    
    print(f"SUCCESS: Found Shimada: {shimada.id} {shimada.name} (Status: {shimada.status})")
    
    print("\n--- 2. Testing Night Skill Override ---")
    print(f"Night MR: {shimada.night_mr}")
    print(f"Night Angio: {shimada.night_angio}")
    print(f"Night Cath: {shimada.night_cath}")
    
    if not (shimada.night_mr or shimada.night_angio or shimada.night_cath):
        print("FAIL: Shimada has NO night skills enabled.")
    else:
        print("SUCCESS: Shimada has night skills.")

    print("\n--- 3. Testing Night Quota Loading ---")
    name_to_id = {s.name: s.id for s in staff_list}
    quotas = loader.load_night_counts("2026-01", name_to_id)
    
    if shimada.id in quotas:
        print(f"SUCCESS: Shimada Quota = {quotas[shimada.id]}")
    else:
        print(f"FAIL: Shimada ID {shimada.id} NOT found in quotas.")
        # Debug why
        # (This relies on the debug prints I added to DataLoader in previous step, checking stdout)

if __name__ == "__main__":
    test()
