// Client mirror of the backend validation.py rules. These give instant feedback and
// gate Save; the server stays authoritative (any 422 is rendered via ValidationErrorList).
// Predicates return booleans; assert* throw ClientValidationError with a JP message that
// matches the backend wording so client and server errors read consistently.

export class ClientValidationError extends Error {
  constructor(
    public field: string,
    message: string,
  ) {
    super(message);
    this.name = 'ClientValidationError';
  }
}

const RANKS = new Set(['A', 'B', 'C', 'D', '-']);
const GENDERS = new Set(['男', '女']);
const OX = new Set(['○', '×']);
const STATUSES = new Set(['在籍', '退職']);
const WEEKDAY_TOKENS = new Set(['月', '火', '水', '木', '金', '土', '日', '水金', '-']);

/** Special-rule rank conditions the scheduler parses to NONE (dead branch, NOT enforced). */
export const UNENFORCED_RANK_CONDS = ['D同士禁止', 'CD上限', 'CD単独禁止'] as const;

export const isTechId = (s: string): boolean => /^T\d{3}$/.test(s);
export const isRank = (s: string): boolean => RANKS.has(s);
export const isGender = (s: string): boolean => GENDERS.has(s);
export const isOX = (s: string): boolean => OX.has(s);
export const isStatus = (s: string): boolean => STATUSES.has(s);

/** Zero-padded YYYY/MM only — `2026/4` silently misses the Python loader's exact match. */
export const isYearMonth = (s: string): boolean => /^\d{4}\/(0[1-9]|1[0-2])$/.test(s);

export const isWeekdayToken = (s: string): boolean => WEEKDAY_TOKENS.has(s);

export const isWeekToken = (w: number | string): boolean => {
  if (w === 'every' || w === '-') return true;
  const n = typeof w === 'number' ? w : Number(w);
  return Number.isInteger(n) && n >= 1 && n <= 5;
};

export const isUnenforcedRankCond = (c: string): boolean =>
  (UNENFORCED_RANK_CONDS as readonly string[]).includes(c);

export const isNonNegInt = (n: number): boolean => Number.isInteger(n) && n >= 0;

export function assertTechIdUnique(existing: Set<string>, techId: string): void {
  if (existing.has(techId)) {
    throw new ClientValidationError('技師ID', `技師ID ${techId} は既に存在します`);
  }
}

/** The cross-file join key is byte-sensitive: a full-width space (U+3000) is required.
 *  The backend only normalizes 　↔space as a fallback, so the UI rejects the half-width
 *  form rather than silently relying on that fallback. */
export function assertNameJoins(name: string, known: Set<string>): void {
  if (!known.has(name)) {
    throw new ClientValidationError(
      '氏名',
      `氏名「${name}」が技師マスタの結合キーと一致しません（全角スペースを確認してください）`,
    );
  }
}

export function assertPbLocationRef(code: string, sectionACodes: Set<string>): void {
  if (!sectionACodes.has(code)) {
    throw new ClientValidationError(
      '場所コード',
      `パワーバランスの場所コード「${code}」が勤務場所マスタに存在しません`,
    );
  }
}

export function assertNightTotal(entries: { count: number }[], declaredTotal: number): void {
  const sum = entries.reduce((acc, e) => acc + (e.count ?? 0), 0);
  if (sum !== declaredTotal) {
    throw new ClientValidationError(
      '合計',
      `夜勤回数の合計（${sum}）が宣言された合計（${declaredTotal}）と一致しません`,
    );
  }
}

const TRAINING_SENTINEL = 'ランクA保持者';

export function assertTrainingResolves(ids: string[], knownIds: Set<string>): void {
  for (const id of ids) {
    if (id === TRAINING_SENTINEL) continue;
    if (!knownIds.has(id)) {
      throw new ClientValidationError(
        '対象者',
        `業務拡大の対象「${id}」が技師マスタに解決できません`,
      );
    }
  }
}
