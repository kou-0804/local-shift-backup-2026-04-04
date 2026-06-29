"""Per-master validators. Each rule raises ``ValidationError`` (field + JP message).

Rules mirror spec §9 / the masters map: tech_id T+3桁 + unique; gender ∈ {男,女};
experience_years int ≥ 0; night_ok/oncall_ok ∈ {○,×}; status ∈ {在籍,退職}; skill
rank ∈ {A,B,C,D,-}; year_month YYYY/MM zero-padded; full-width-space name join;
section-B 場所コード references section-A; 夜勤回数 合計 == sum; training names resolve.
"""
import re

TECH_ID_RE = re.compile(r"^T\d{3}$")
YEAR_MONTH_RE = re.compile(r"^\d{4}/(0[1-9]|1[0-2])$")
SKILL_RANKS = {"A", "B", "C", "D", "-"}
GENDERS = {"男", "女"}
MARKS = {"○", "×"}
STATUSES = {"在籍", "退職"}
WEEKDAYS = {"月", "火", "水", "木", "金", "土", "日", "水金", "-"}
WEEKS = {"1", "2", "3", "4", "5", "-"}


class ValidationError(Exception):
    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.message = message
        self.field = field


def _clean(s: str) -> str:
    return (s or "").replace(" ", "").replace("　", "")


def validate_tech_id(tech_id: str):
    if not TECH_ID_RE.match(tech_id or ""):
        raise ValidationError(f"技師IDは T+3桁 形式が必要です: {tech_id!r}", "tech_id")


def validate_tech_id_unique(existing, tech_id: str):
    if tech_id in existing:
        raise ValidationError(f"技師ID {tech_id} は既に存在します（重複不可）", "tech_id")


def validate_skill_rank(rank: str):
    if rank not in SKILL_RANKS:
        raise ValidationError(
            f"スキルランクは {{A,B,C,D,-}} のいずれかが必要です: {rank!r}", "rank")


def validate_year_month(ym: str):
    if not YEAR_MONTH_RE.match(ym or ""):
        raise ValidationError(
            f"年月は YYYY/MM（ゼロ埋め）形式が必要です: {ym!r}", "year_month")


def validate_name_join(name: str, known_names):
    """Exact (space-sensitive) membership — 全角/半角スペースの取り違えを弾く。"""
    if name not in known_names:
        raise ValidationError(
            f"氏名 {name!r} がマスタの氏名集合に一致しません"
            "（全角・半角スペースの違いに注意）", "name")


def validate_pb_location_ref(code: str, location_codes):
    if code not in location_codes:
        raise ValidationError(
            f"場所コード {code!r} はセクションAの勤務場所に存在しません", "loc_code")


def validate_night_quota_total(rows_sum: int, declared_total: int):
    if rows_sum != declared_total:
        raise ValidationError(
            f"夜勤回数の合計 {declared_total} が各人合計 {rows_sum} と一致しません", "合計")


def validate_training_names(names, staff_names):
    missing = []
    cleaned = [_clean(s) for s in staff_names]
    for n in names:
        c = _clean(n)
        if not c or not any(c in s or s in c for s in cleaned):
            missing.append(n)
    if missing:
        raise ValidationError(
            f"育成/指導者名が技師マスタに解決できません: {missing}", "names")


def _validate_experience(exp):
    if isinstance(exp, bool):
        raise ValidationError("経験年数は0以上の整数が必要です", "experience_years")
    try:
        ival = int(exp)
    except (TypeError, ValueError):
        raise ValidationError("経験年数は0以上の整数が必要です", "experience_years")
    if ival < 0:
        raise ValidationError("経験年数は0以上の整数が必要です", "experience_years")


def validate_staff_row(row: dict, existing_ids=None):
    validate_tech_id(row.get("tech_id"))
    if existing_ids is not None:
        validate_tech_id_unique(existing_ids, row.get("tech_id"))
    if row.get("gender") not in GENDERS:
        raise ValidationError(f"性別は {{男,女}} のいずれか: {row.get('gender')!r}", "gender")
    _validate_experience(row.get("experience_years"))
    if row.get("night_ok") not in MARKS:
        raise ValidationError("夜勤可否は ○ または ×", "night_ok")
    if row.get("status") not in STATUSES:
        raise ValidationError("在籍状況は 在籍 または 退職", "status")
    if row.get("oncall_ok") not in MARKS:
        raise ValidationError("拘束可否は ○ または ×", "oncall_ok")


def validate_special_rule_row(row: dict):
    if row.get("weekday") not in WEEKDAYS:
        raise ValidationError(
            f"対象曜日は {{月..日,水金,-}} のいずれか: {row.get('weekday')!r}", "weekday")
    if row.get("week") not in WEEKS:
        raise ValidationError(
            f"対象週は {{1..5,-}} のいずれか: {row.get('week')!r}", "week")
    rc = row.get("required_count")
    if rc not in (None, "", "-"):
        try:
            int(rc)
        except (TypeError, ValueError):
            raise ValidationError("必要人数は整数が必要です", "required_count")
