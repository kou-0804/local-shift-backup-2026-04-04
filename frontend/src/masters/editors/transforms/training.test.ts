import { describe, it, expect } from 'vitest';
import { parseTrainingRow } from './training';

describe('parseTrainingRow', () => {
  it('parses *_ids_json strings into arrays and rank_a_only int into boolean', () => {
    const w = parseTrainingRow({
      modality: '病院MR',
      display_name: '(MR)',
      instructor_text: 'ランクA保持者',
      trainee_text: '平野裕, 星',
      instructor_ids_json: '[]',
      trainee_ids_json: '["T044","T033"]',
      rank_a_only: 1,
    });
    expect(w.rank_a_only).toBe(true);
    expect(w.instructor_ids).toEqual([]);
    expect(w.trainee_ids).toEqual(['T044', 'T033']);
    expect(w.instructor_text).toBe('ランクA保持者');
    expect(w.trainee_text).toBe('平野裕, 星');
  });

  it('tolerates missing/blank/garbage json without crashing', () => {
    const w = parseTrainingRow({ modality: 'ア' });
    expect(w.instructor_ids).toEqual([]);
    expect(w.trainee_ids).toEqual([]);
    expect(w.rank_a_only).toBe(false);
    expect(w.display_name).toBe('');
    const g = parseTrainingRow({ modality: '心', trainee_ids_json: 'not-json' });
    expect(g.trainee_ids).toEqual([]);
  });
});
