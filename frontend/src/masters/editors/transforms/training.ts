import type { TrainingWire } from '../../types';

/** 生のDB行（GET /masters/{set}/training は ms_training の列をそのまま返す）。
 *  ids は JSON 文字列、rank_a_only は整数(0/1)。 */
export interface RawTrainingRow {
  modality: string;
  display_name?: string;
  instructor_text?: string;
  trainee_text?: string;
  instructor_ids_json?: string | null;
  trainee_ids_json?: string | null;
  rank_a_only?: number | boolean;
}

function parseIds(json: string | null | undefined): string[] {
  if (!json) return [];
  try {
    const v = JSON.parse(json);
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
}

/** 生の training 行を、エディタが扱う TrainingWire（配列＋真偽）へ変換する。
 *  `*_ids_json`（文字列）→配列、`rank_a_only`（整数）→真偽。
 *  保存時の往復用に元テキスト（権威ソース）も保持する。 */
export function parseTrainingRow(raw: RawTrainingRow): TrainingWire {
  return {
    modality: raw.modality,
    display_name: raw.display_name ?? '',
    rank_a_only: Boolean(raw.rank_a_only),
    instructor_ids: parseIds(raw.instructor_ids_json),
    trainee_ids: parseIds(raw.trainee_ids_json),
    instructor_text: raw.instructor_text ?? '',
    trainee_text: raw.trainee_text ?? '',
  };
}
