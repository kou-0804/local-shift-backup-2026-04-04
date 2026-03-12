
import sys
from unittest.mock import MagicMock

# Mock openpyxl to avoid import error
sys.modules['openpyxl'] = MagicMock()
sys.modules['openpyxl.styles'] = MagicMock()
sys.modules['openpyxl.utils'] = MagicMock()

# Add project root to path
sys.path.append('/Users/kohei/Desktop/local-shift ver1')

from shift_scheduler.src.excel_generator import ExcelGenerator
from shift_scheduler.src.models.staff import Staff, Gender

def test_17_gyo_reflection():
    print("Testing 17業 Reflection...")
    
    # Mock Data
    staff = Staff(id='T001', name='Test Staff', gender=Gender.MALE, experience_years=10, 
                  can_night_shift=True, status='在籍')
    
    day = 1
    # User requested '17業'
    requests = {day: {'T001': '17業'}}
    
    # Scheduler assigned 'MRI'
    day_assignments = {day: {'病院MR': ['T001']}}
    
    night_assignments = {}
    
    # Instantiate Generator
    # Note: We only need _get_assignment_text, so we mock other init args
    generator = ExcelGenerator(
        year=2025, month=12,
        technicians=[staff],
        night_assignments=night_assignments,
        day_assignments=day_assignments,
        requests=requests,
        name_mapper={}
    )
    
    # Test _get_assignment_text
    result = generator._get_assignment_text('T001', day)
    print(f"Result for '17業' + '病院MR': '{result}'")
    
    if '17業' in result and '病院MR' in result:
        print("PASS: 17業 is reflected.")
    else:
        print("FAIL: 17業 is missing from output.")

def test_17_kyu_reflection():
    print("\nTesting 17休 Reflection...")
    
    # Mock Data
    staff = Staff(id='T002', name='Test Staff 2', gender=Gender.MALE, experience_years=10, 
                  can_night_shift=True, status='在籍')
    
    day = 2
    requests = {day: {'T002': '17休'}}
    day_assignments = {day: {'CT': ['T002']}}
    night_assignments = {}
    
    generator = ExcelGenerator(
        year=2025, month=12,
        technicians=[staff],
        night_assignments=night_assignments,
        day_assignments=day_assignments,
        requests=requests,
        name_mapper={}
    )
    
    result = generator._get_assignment_text('T002', day)
    print(f"Result for '17休' + 'CT': '{result}'")
    
    if '17休' in result and 'CT' in result:
        print("PASS: 17休 is reflected.")
    else:
        print("FAIL: 17休 is missing from output.")

if __name__ == "__main__":
    test_17_gyo_reflection()
    test_17_kyu_reflection()
