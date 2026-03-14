# 放射線技師勤務表自動作成システム 完全仕様書

**バージョン**: 2.0  
**作成日**: 2025年12月11日  
**ステータス**: 実装準備完了

---

## 目次

1. [システム概要](#1-システム概要)
2. [用語定義](#2-用語定義)
3. [入力データ仕様](#3-入力データ仕様)
4. [夜勤スケジューリング](#4-夜勤スケジューリング)
5. [日勤スケジューリング](#5-日勤スケジューリング)
6. [パワーバランス制約](#6-パワーバランス制約)
7. [特殊配置ルール](#7-特殊配置ルール)
8. [予定申請記号](#8-予定申請記号)
9. [処理フロー](#9-処理フロー)
10. [アルゴリズム詳細](#10-アルゴリズム詳細)
11. [出力仕様](#11-出力仕様)
12. [エラーハンドリング](#12-エラーハンドリング)
13. [実装ガイド](#13-実装ガイド)
14. [付録A: データモデル定義](#付録a-データモデル定義)
15. [付録B: 制約条件一覧表](#付録b-制約条件一覧表)
16. [付録C: 技師・スキルマスタ](#付録c-技師スキルマスタ)

---

## 1. システム概要

### 1.1 目的

病院放射線科における約66名の放射線技師の月次勤務表を自動作成するシステム。夜勤と日勤の両方のスケジューリングを行い、すべての制約条件を満たしながら、スタッフの希望を最大限に尊重した勤務表を生成する。

### 1.2 対象規模

| 項目 | 数値 |
|------|------|
| 技師総数 | 66名 |
| 夜勤対象者 | 約38名 |
| 勤務場所数 | 18箇所 |
| 夜勤回数/月 | 約93回（31日×3名） |
| 日勤配置/月 | 約1,500件 |

### 1.3 技術スタック

| 項目 | 技術 |
|------|------|
| 言語 | Python 3.10+ |
| 最適化エンジン | Google OR-Tools (CP-SAT Solver) |
| データ処理 | pandas, openpyxl |
| 祝日判定 | jpholiday |
| 設定管理 | YAML / JSON |

### 1.4 システム構成図

```
┌─────────────────────────────────────────────────────────────┐
│                    入力データ                                │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│ 技師マスタ   │ スキルマスタ │ 勤務場所    │ 予定申請        │
│             │             │ マスタ      │ 夜勤回数        │
└──────┬──────┴──────┬──────┴──────┬──────┴────────┬────────┘
       │              │              │                │
       ▼              ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                  データローダー                              │
│  - バリデーション                                            │
│  - データ変換                                                │
│  - 夜勤スキル自動導出                                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               夜勤スケジューラー (OR-Tools)                  │
│  - ハード制約: 人数、間隔、スキル、希望遵守                   │
│  - ソフト制約: 週分散、日祝分散                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               日勤スケジューラー (OR-Tools)                  │
│  - ハード制約: 人数、スキル、希望遵守、パワーバランス         │
│  - ソフト制約: 業務均等化、連続配置選好                      │
│  - 特殊配置ルール: 曜日別・週別ルール                        │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    出力生成                                  │
├─────────────┬─────────────┬─────────────┬─────────────────┤
│ 勤務表.xlsx │ 夜勤割当.csv │ 日勤配置.csv │ 制約チェック.txt│
└─────────────┴─────────────┴─────────────┴─────────────────┘
```

---

## 2. 用語定義

### 2.1 スキルランク

| ランク | 定義 | 判断基準 |
|--------|------|----------|
| **A** | エキスパート | 単独で全検査対応可、後輩指導可、緊急対応可 |
| **B** | 一人前 | 通常検査は単独対応可、一部指導も可能 |
| **C** | 標準 | 基本的な検査は対応可、複雑な検査は要サポート |
| **D** | 新人 | 必ず上位ランク者と組む必要あり |
| **-** | スキルなし | 当該業務への配置不可 |

### 2.2 夜勤関連用語

| 用語 | 定義 |
|------|------|
| **夜勤** | 17:00〜翌8:30の勤務。1日3名体制 |
| **夜勤明け** | 夜勤翌日。日勤配置不可（「○」記号） |
| **夜勤希望** | 特定日の夜勤を希望する申請（「夜希」記号） |
| **夜勤間隔** | 連続する夜勤間の日数。最低3日以上必要 |
| **夜勤MR** | 夜勤時のMRI対応スキル |
| **夜勤アンギオ** | 夜勤時の血管造影対応スキル |
| **夜勤心カテ** | 夜勤時の心臓カテーテル対応スキル |

### 2.3 日勤関連用語

| 用語 | 定義 |
|------|------|
| **日勤** | 8:30〜17:00の通常勤務 |
| **パワーバランス** | 各勤務場所における経験者配置の要件 |
| **特殊配置ルール** | 特定曜日・特定週に適用される追加ルール |
| **必要人数** | 各勤務場所・曜日ごとに必要な配置人数 |

### 2.4 週・曜日の定義

| 用語 | 定義 |
|------|------|
| **第N週** | 月の第N番目のその曜日（例：第1金曜日 = 月の最初の金曜日） |
| **平日** | 月曜日〜金曜日（祝日を除く） |
| **土曜** | 土曜日（祝日と重なっても土曜扱い） |
| **日祝** | 日曜日および国民の祝日 |

---

## 3. 入力データ仕様

### 3.1 ファイル構成

```
data/
├── 技師マスタ.csv              # 技師の基本情報
├── スキルマスタ.csv            # 技師×勤務場所のスキルマトリクス
├── 勤務場所マスタ.csv          # 勤務場所の定義と必要人数
├── 特殊配置ルール.csv          # 曜日別・週別の特殊ルール
├── 予定申請_YYYYMM.csv         # 月別の予定申請
└── 夜勤回数_YYYYMM.csv         # 月別の夜勤回数指定
```

### 3.2 技師マスタ

**ファイル名**: `技師マスタ.csv`

| 列名 | 型 | 必須 | 説明 | 例 |
|------|-----|------|------|-----|
| 技師ID | string | ○ | 一意識別子（T001形式） | T001 |
| 氏名 | string | ○ | フルネーム | 加藤　光久 |
| 性別 | string | ○ | 男/女 | 男 |
| 経験年数 | int | ○ | 勤続年数 | 30 |
| 夜勤可否 | string | ○ | ○=可能、×=不可 | ○ |
| 在籍状況 | string | ○ | 在籍/休職/退職 | 在籍 |
| 備考 | string | - | 補足情報 | 管理職 |

**データサンプル（66名分）**:
```csv
技師ID,氏名,性別,経験年数,夜勤可否,在籍状況,備考
T001,加藤　光久,男,30,×,在籍,管理職
T002,石川　和弥,男,30,○,在籍,
T003,矢野　昌男,男,30,×,在籍,MRI専門
...
T066,遠藤　健太郎,男,20,×,在籍,館山
```

### 3.3 スキルマスタ

**ファイル名**: `スキルマスタ.csv`

技師ID × 勤務場所のマトリクス形式。各セルにスキルランク（A/B/C/D/-）を記載。

| 列名 | 説明 |
|------|------|
| 技師ID | 技師の一意識別子 |
| 病院MR | 病院MRIのスキルランク |
| クMR | クリニックMRIのスキルランク |
| CT | CTのスキルランク |
| 病CT | 病院CTのスキルランク |
| ア | アンギオのスキルランク |
| 心 | 心カテのスキルランク |
| ク | クリニック一般のスキルランク |
| ポ | ポータブルのスキルランク |
| 精 | 病院TV（精密）のスキルランク |
| MG | マンモグラフィのスキルランク |
| DR | クリニックTVのスキルランク |
| HB | HBのスキルランク |
| OP | OPのスキルランク |
| PICC | PICCのスキルランク |
| 入 | 病院一般（入院受付）のスキルランク |
| 出 | 日祝日出勤のスキルランク |
| 超遅 | 超遅番のスキルランク |

**データサンプル**:
```csv
技師ID,病院MR,クMR,CT,病CT,ア,心,ク,ポ,精,MG,DR,HB,OP,PICC,入,出,超遅
T001,-,-,B,C,-,-,-,-,-,-,-,-,-,-,-,-,-
T002,B,B,A,-,-,-,B,-,A,-,A,-,-,-,-,-,-
T009,-,-,B,A,A,A,B,-,-,-,-,B,-,-,-,-,-
...
```

### 3.4 勤務場所マスタ

**ファイル名**: `勤務場所マスタ.csv`

**シート1: 勤務場所定義**

| 列名 | 型 | 必須 | 説明 |
|------|-----|------|------|
| 場所コード | string | ○ | 一意識別子 |
| 場所名 | string | ○ | 表示名 |
| カテゴリ | string | ○ | 分類（MRI/CT/IVR/一般/TV/特殊/時間帯/事務） |
| 月〜日 | int | ○ | 各曜日の必要人数 |
| 性別制約 | string | ○ | なし/女性のみ |
| 表示順 | int | ○ | 勤務表での表示順 |
| 有効 | string | ○ | ○=有効、×=無効 |

**勤務場所一覧（18箇所）**:

| 場所コード | 場所名 | カテゴリ | 月 | 火 | 水 | 木 | 金 | 土 | 日 | 性別制約 |
|------------|--------|----------|-----|-----|-----|-----|-----|-----|-----|----------|
| 病院MR | 病院MRI | MRI | 3 | 3 | 3 | 3 | 3 | 3 | 0 | なし |
| クMR | クリニックMRI | MRI | 5 | 5 | 5 | 5 | 5 | 3 | 0 | なし |
| CT | CT | CT | 4 | 4 | 4 | 4 | 4 | 3 | 0 | なし |
| 病CT | 病院CT | CT | 6 | 6 | 6 | 6 | 6 | 3 | 0 | なし |
| ア | アンギオ | IVR | 1 | 2 | 1 | 2 | 1 | 0 | 0 | なし |
| 心 | 心カテ | IVR | 1 | 1 | 1 | 1 | 1 | 1 | 0 | なし |
| ク | クリニック一般 | 一般 | 6 | 6 | 6 | 6 | 6 | 4 | 0 | なし |
| ポ | ポータブル | 一般 | 2 | 2 | 2 | 2 | 2 | 2 | 0 | なし |
| 精 | 病院TV | TV | 1 | 1 | 1 | 1 | 1 | 1 | 0 | なし |
| MG | マンモグラフィ | 女性限定 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 女性のみ |
| DR | クリニックTV | TV | 1 | 1 | 1 | 1 | 1 | 1 | 0 | なし |
| HB | HB | IVR | 1 | 1 | 1 | 2 | 1 | 0 | 0 | なし |
| OP | OP | 一般 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | なし |
| 入 | 病院一般 | 一般 | 2 | 2 | 2 | 2 | 2 | 2 | 0 | なし |
| 出 | 日祝日出勤 | 特殊 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | なし |
| 超遅 | 超遅番 | 時間帯 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | なし |
| M遅 | MRI遅番 | 時間帯 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | なし |
| 勤務表作成 | 勤務表作成 | 事務 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | なし |

### 3.5 予定申請

**ファイル名**: `予定申請_YYYYMM.csv`

| 列名 | 型 | 必須 | 説明 | 例 |
|------|-----|------|------|-----|
| 技師ID | string | ○ | 申請者 | T002 |
| 日付 | date | ○ | 対象日（YYYY-MM-DD形式） | 2025-12-01 |
| 記号 | string | ○ | 申請種別の記号 | ★ |
| 備考 | string | - | 補足情報 | 結婚式 |

### 3.6 夜勤回数

**ファイル名**: `夜勤回数_YYYYMM.csv`

| 列名 | 型 | 必須 | 説明 | 例 |
|------|-----|------|------|-----|
| 技師ID | string | ○ | 対象技師 | T002 |
| 回数 | int | ○ | 月間夜勤回数 | 3 |

**制約**: 全技師の回数合計 = 対象月の日数 × 3

---

## 4. 夜勤スケジューリング

### 4.1 夜勤の基本構成

1日の夜勤は**3名体制**で、以下の役割を担当：

| 役割 | 必要スキル | 担当業務 |
|------|------------|----------|
| MR担当 | 夜勤MR可 | 緊急MRI検査 |
| アンギオ担当 | 夜勤アンギオ可 | 緊急血管造影 |
| 心カテ担当 | 夜勤心カテ可 | 緊急心臓カテーテル |

### 4.2 夜勤スキルの自動導出

日勤スキルから夜勤スキルを自動導出：

```python
def derive_night_skills(staff_id: str, day_skills: dict) -> dict:
    """日勤スキルから夜勤スキルを導出"""
    night_skills = {
        'night_mr': False,
        'night_angio': False,
        'night_cath': False
    }
    
    # 夜勤MR: 病院MR または クMR が B以上
    if day_skills.get('病院MR') in ['A', 'B'] or day_skills.get('クMR') in ['A', 'B']:
        night_skills['night_mr'] = True
    
    # 夜勤アンギオ: ア が B以上
    if day_skills.get('ア') in ['A', 'B']:
        night_skills['night_angio'] = True
    
    # 夜勤心カテ: 心 が B以上
    if day_skills.get('心') in ['A', 'B']:
        night_skills['night_cath'] = True
    
    return night_skills
```

### 4.3 夜勤ハード制約

| 制約ID | 制約名 | 内容 | 違反時 |
|--------|--------|------|--------|
| NH-01 | 人数制約 | 毎日必ず3名を配置 | 解なし |
| NH-02 | 回数遵守 | 各技師の月間夜勤回数を厳守 | 解なし |
| NH-03 | 間隔制約 | 夜勤間隔は最低3日以上 | 解なし |
| NH-04 | 夜勤希望 | 「夜希」記号の日は必ず夜勤に配置 | 解なし |
| NH-05 | 休み遵守 | 休み記号の日は夜勤不可、前日夜勤も不可 | 解なし |
| NH-06 | スキル制約 | 3名でMR/アンギオ/心カテ全スキルをカバー | 解なし |
| NH-07 | 特殊記号 | 特殊記号（17業、講、会議等）の日は夜勤不可 | 解なし |

### 4.4 夜勤ソフト制約

| 制約ID | 制約名 | 内容 | 重み |
|--------|--------|------|------|
| NS-01 | 週分散 | 同一週に複数夜勤を避ける | 50000 |
| NS-02 | 日祝分散 | 日祝の夜勤回数を**極力均等化**（Hard制約＋回数に応じた増分ペナルティ） | 最大 |
| NS-03 | 土曜分散 | 土曜夜勤を技師間で均等化 | 50 |
| NS-04 | 回数目標 | 各技師の月間夜勤回数の目標（ハード制約NH-02を緩和しソフト化） | 1000000 |
| NS-05 | 夜勤間隔 | 夜勤間隔3日以上を推奨、短期連続・月跨ぎの連続を避ける | 10000〜 |
| NS-06 | 若手のみ禁止 | 技師歴3年以内の若手のみの夜勤3名構成を避ける | 5000 |
| NS-07 | 明け日祝均等化 | 夜勤明けが日祝日に当たる回数を**極力均等化**（Hard制約＋増分ペナルティ） | 最大 |

### 4.5 夜勤スキル制約の詳細

3名の夜勤者で以下のスキルを**必ずカバー**する必要がある：

```
夜勤3名 ⊇ {夜勤MR可能者 ≥ 1名} ∩ {夜勤アンギオ可能者 ≥ 1名} ∩ {夜勤心カテ可能者 ≥ 1名}
```

**注意**: 1人が複数スキルを持つことがあるため、3名全員が異なる役割を担当するとは限らない。

---

## 5. 日勤スケジューリング

### 5.1 日勤ハード制約

| 制約ID | 制約名 | 内容 | 違反時 |
|--------|--------|------|--------|
| DH-01 | 単一配置 | 1人1日1場所のみ配置 | 解なし |
| DH-02 | スキル必須 | 配置場所のスキルを持つ者のみ配置可 | 解なし |
| DH-03 | 必要人数 | 各場所の必要人数を満たす | 解なし |
| DH-04 | 休み遵守 | 休み記号の日は日勤配置不可 | 解なし |
| DH-05 | 夜勤明け | 前日夜勤者は日勤配置不可 | 解なし |
| DH-06 | 性別制約 | MG（マンモ）は女性のみ配置可 | 解なし |
| DH-07 | 特殊記号 | 特殊記号に応じた配置場所制限 | 解なし |
| DH-08 | 当日夜勤 | 当日夜勤者は日勤配置可能（17時まで） | - |
| DH-09 | 6連勤禁止 | **絶対に6連勤を超えない（7日目は必ず「休」となる）**<br>日勤だけでなく「夜勤(夜希含む)」「明け(○)」「指定業務(講,会議,業配など)」すべてを勤務日（稼働日）として連続カウントし、向こう数日間の確定済み勤務状況（先読み機能）を考慮して7連勤が不可避になる前に強制休を挿入する。 | 解なし |
| DH-10 | 超遅明け | 超遅番の翌日は「早番・通常日勤」への配置不可 | 解なし |

### 5.2 日勤ソフト制約

| 制約ID | 制約名 | 内容 | 重み |
|--------|--------|------|------|
| DS-01 | 業務均等化 | 各技師の業務量を均等化 | 50 |
| DS-02 | 連続配置 | 同一場所への連続配置を選好 | 10 |
| DS-03 | 希望配置 | 技師の希望場所を考慮 | 5 |

---

## 6. パワーバランス制約

### 6.1 パワーバランスの定義

各勤務場所において、適切な経験バランスを確保するための制約。

### 6.2 基本パワーバランス設定

| 場所コード | 必要人数 | Aランク最低 | Bランク最低 | CD上限 | D単独禁止 |
|------------|----------|-------------|-------------|--------|-----------|
| 病院MR | 3 | 1 | 2 | - | ○ |
| クMR | 5 | 2 | 3 | - | ○ |
| CT | 4 | 1 | - | - | ○ |
| 病CT | 6 | 2 | 1 | 3 | ○ |
| ア | 1-2 | - | 1 | - | ○ |
| 心 | 1 | - | 1 | - | ○ |
| ク | 6 | 3 | - | - | ○ |
| ポ | 2 | - | 1 | - | ○ |
| 精 | 1 | - | 1 | - | × |

### 6.3 パワーバランス制約の数式化

**制約PB-01: 最低ランク人数制約**
```
∀場所 l, ∀ランク r:
  Σ(配置された技師のうちランクr以上の人数) ≥ 最低人数[l][r]
```

**制約PB-02: CD上限制約**
```
∀場所 l where CD上限が定義:
  Σ(配置された技師のうちCまたはDランクの人数) ≤ CD上限[l]
```

**制約PB-03: D単独禁止制約**
```
∀場所 l where D単独禁止=○:
  配置人数 ≥ 2 の場合、Dランクのみの配置は不可
```

**制約PB-04: ポータブルD組み合わせ禁止**
```
場所「ポ」において:
  2名配置時、両者ともDランクは不可
  → (staff1.rank == 'D' ∧ staff2.rank == 'D') = False
```

**制約PB-05: CT（クリニック）CD組み合わせ禁止**
```
場所「CT」において:
  Aランク1名以上 かつ C・Dランクのみでの組み合わせ禁止
  → 配置者にA or B が最低1名含まれる
```

**制約PB-06: クリニック系（ク + ク遅 + MG）の女性配置制約**
```
クリニックエリアにおいて:
  常時: 女性3人以上、金曜日: 女性4人以上を配置する。
  ※ 水曜日は別枠の「業配」に配置された女性スタッフもこの人数枠に加算（補填）される。
  → Σ(「ク」「ク遅」「MG」の女性) ≥ (必要人数 - 水曜業配の女性数)
```

**制約PB-07: クリニック一般（ク）経験年数制約**
```
場所「ク」において:
  配置人数のうち、経験年数6年以上のベテランが最低1人以上含まれる
  ※ 水曜日に「業配」の女性で経験年数6年以上の者がいる場合、その人物でこのベテラン条件を満たしたとみなす。
  → Σ(配置された技師のうち経験年数≥6の人数) ≥ 1 （水曜業配にベテランがいる場合はスキップ可）
```

---

## 7. 特殊配置ルール

### 7.1 曜日別特殊ルール

#### 7.1.1 アンギオ（ア）

| 曜日 | 人数 | ランク条件 | 備考 |
|------|------|------------|------|
| 火曜 | 2 | **Aランク2名** | 治療日のため |
| 木曜 | 2 | ランク不問 | - |
| 月水金 | 1 | B以上1名 | - |
| 土日 | 0 | - | 配置なし |

```python
def get_angio_constraint(weekday: int, week_of_month: int) -> dict:
    """アンギオの曜日別制約を取得"""
    if weekday == 1:  # 火曜日
        return {'total': 2, 'min_A': 2, 'min_B': 0}
    elif weekday == 3:  # 木曜日
        return {'total': 2, 'min_A': 0, 'min_B': 0}
    elif weekday in [0, 2, 4]:  # 月水金
        return {'total': 1, 'min_A': 0, 'min_B': 1}
    else:  # 土日
        return {'total': 0, 'min_A': 0, 'min_B': 0}
```

#### 7.1.2 HB

| 条件 | 人数 | ランク条件 | 備考 |
|------|------|------------|------|
| 第1金曜日 | 2 | **Aランク2名** | - |
| 第4木曜日 | 3 | **Aランク3名** | - |
| 通常木曜日 | 2 | 通常ルール | - |
| その他 | 1 | 通常ルール | - |

```python
def get_hb_constraint(weekday: int, week_of_month: int) -> dict:
    """HBの曜日・週別制約を取得"""
    if weekday == 4 and week_of_month == 1:  # 第1金曜日
        return {'total': 2, 'min_A': 2}
    elif weekday == 3 and week_of_month == 4:  # 第4木曜日
        return {'total': 3, 'min_A': 3}
    elif weekday == 3:  # 通常木曜日
        return {'total': 2, 'min_A': 0}
    else:
        return {'total': 1, 'min_A': 0}
```

#### 7.1.3 OP

| 条件 | 人数 | 選出元 | 備考 |
|------|------|--------|------|
| 第1金曜日 | 1 | **HBのAランク** | TAVI検査対応 |
| その他 | 1 | OP有スキル者 | - |

```python
def get_op_constraint(weekday: int, week_of_month: int) -> dict:
    """OPの曜日・週別制約を取得"""
    if weekday == 4 and week_of_month == 1:  # 第1金曜日
        return {
            'total': 1,
            'source': 'HB',  # HBスキル保有者から選出
            'source_rank': 'A'  # HBがAランクの人
        }
    else:
        return {'total': 1, 'source': 'OP'}
```

#### 7.1.4 精（病院TV）

| 条件 | 人数 | ランク条件 | 備考 |
|------|------|------------|------|
| 水曜・金曜 | 1 | **Aランクのみ** | 特殊検査対応 |
| その他 | 1 | B以上 | - |

```python
def get_sei_constraint(weekday: int) -> dict:
    """精の曜日別制約を取得"""
    if weekday in [2, 4]:  # 水曜・金曜
        return {'total': 1, 'rank_only': 'A'}  # Aランク限定
    else:
        return {'total': 1, 'min_B': 1}
```

### 7.2 特殊配置ルール一覧表

| ルールID | 場所 | 条件 | 人数 | ランク条件 | 選出元 |
|----------|------|------|------|------------|--------|
| SR-01 | ア | 火曜 | 2 | A×2名 | - |
| SR-02 | ア | 木曜 | 2 | 不問 | - |
| SR-03 | HB | 第1金曜 | 2 | A×2名 | - |
| SR-04 | HB | 第4木曜 | 3 | A×3名 | - |
| SR-05 | OP | 第1金曜 | 1 | - | HBのA |
| SR-06 | 精 | 水金 | 1 | Aのみ | - |
| SR-07 | ポ | 全日 | 2 | D×D禁止 | - |
| SR-08 | 病CT | 全日 | 6 | A≥2, B≥1 | - |
| SR-09 | CT | 全日 | 4 | A≥1, CD単独禁止 | - |

### 7.3 週番号の計算

```python
def get_week_of_month(date: datetime.date) -> int:
    """月内での週番号を取得（第N曜日のN）"""
    day = date.day
    return (day - 1) // 7 + 1

# 例: 2025年12月
# 12/5（金）→ 第1金曜日 (week_of_month = 1)
# 12/25（木）→ 第4木曜日 (week_of_month = 4)
```

---

## 8. 予定申請記号

### 8.1 記号定義一覧

| 記号 | 種別 | 意味 | 夜勤 | 前日夜勤 | 日勤配置 |
|------|------|------|------|----------|----------|
| ★ | 休み | 有給休暇 | × | × | × |
| ★連 | 休み | 連続有給 | × | × | × |
| ☆ | 休み | 指定休・代休 | × | × | × |
| ☆小 | 休み | 小田病院バイト | × | × | × |
| ☆デ | 休み | デンタルバイト | × | × | × |
| ◆ | 休み | 有給休暇 | × | × | × |
| ○ | 明け | 夜勤明け | × | × | × |
| 夜希 | 夜希 | 夜勤希望 | **必須** | - | 可 |
| 17業 | その他 | 17時以降業務なし | ○ | ○ | 遅番・超遅以外 |
| 17休 | その他 | 17時以降休み | ○ | ○ | 遅番・超遅以外 |
| 講 | その他 | 講演 | × | × | 講 |
| 出/講 | その他 | 出張講演 | × | × | 出/講 |
| 出 | その他 | 出張 | × | × | 出 |
| 出/☆ | その他 | 出張+休み | × | × | × |
| 会議 | その他 | 会議 | × | × | 会議 |
| 全会 | その他 | 全体会 | × | × | 全会 |
| 業配 | その他 | 業務配置 | × | × | 業配 |
| 業出 | その他 | 業務出張 | × | × | 業出 |
| 勤 | その他 | 勤務表作成 | ○ | ○ | 勤務表作成 |
| 研(聴) | その他 | 研修聴講（院外） | × | × | × |
| 出/(役) | その他 | 出張(役員) | × | × | × |
| 研(座) | その他 | 研修(座長) | × | × | × |
| 退職 | 管理 | 退職予定 | × | × | × |

### 8.2 記号処理ロジック

```python
class SymbolProcessor:
    # 休み系記号（夜勤不可、前日夜勤不可、日勤不可）
    HOLIDAY_SYMBOLS = {'★', '★連', '☆', '☆小', '☆デ', '◆', '○', '出/☆', '研(聴)', '退職'}
    
    # 夜勤希望記号
    NIGHT_REQUEST_SYMBOLS = {'夜希'}
    
    # 夜勤可能だが日勤制限ありの記号
    PARTIAL_SYMBOLS = {'17業', '17休'}
    
    # 特殊配置記号（日勤は指定場所のみ）
    SPECIAL_PLACEMENT_SYMBOLS = {
        '講': '講',
        '出/講': '出/講',
        '出': '出',
        '会議': '会議',
        '全会': '全会',
        '業配': '業配',
        '業出': '業出',
        '勤': '勤務表作成'
    }
    
    def can_night_shift(self, symbol: str) -> bool:
        """夜勤可能かどうか"""
        if symbol in self.HOLIDAY_SYMBOLS:
            return False
        if symbol in self.SPECIAL_PLACEMENT_SYMBOLS:
            return False
        return True
    
    def can_day_shift(self, symbol: str, location: str) -> bool:
        """日勤配置可能かどうか"""
        if symbol in self.HOLIDAY_SYMBOLS:
            return False
        if symbol in self.PARTIAL_SYMBOLS:
            # 遅番・超遅以外は可
            return location not in ['超遅']
        if symbol in self.SPECIAL_PLACEMENT_SYMBOLS:
            return location == self.SPECIAL_PLACEMENT_SYMBOLS[symbol]
        return True
    
    def is_night_request(self, symbol: str) -> bool:
        """夜勤希望かどうか"""
        return symbol in self.NIGHT_REQUEST_SYMBOLS
```

---

## 9. 処理フロー

### 9.1 全体処理フロー

```
┌────────────────────────────────────────────────────────────┐
│ 1. 初期化                                                   │
│    - 設定ファイル読み込み                                    │
│    - 対象月の日付リスト生成                                  │
│    - 祝日判定                                               │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 2. データ読み込み                                           │
│    - 技師マスタ読み込み                                      │
│    - スキルマスタ読み込み                                    │
│    - 勤務場所マスタ読み込み                                  │
│    - 予定申請読み込み                                        │
│    - 夜勤回数読み込み                                        │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 3. データ検証                                               │
│    - 必須データの存在確認                                    │
│    - データ整合性チェック                                    │
│    - 夜勤回数合計の検証                                      │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 4. 夜勤スキル導出                                           │
│    - 日勤スキルから夜勤スキルを自動計算                      │
│    - 夜勤可能者リストの生成                                  │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 5. 夜勤スケジューリング                                     │
│    - 夜勤希望日の確定                                        │
│    - 夜勤不可日の特定                                        │
│    - OR-Toolsモデル構築                                      │
│    - 制約追加（ハード制約 → ソフト制約）                     │
│    - 求解                                                   │
│    - 役割割当（MR/アンギオ/心カテ）                          │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 6. 日勤スケジューリング                                     │
│    - 日付ごとにループ:                                       │
│      - 曜日タイプ判定                                        │
│      - 特殊配置ルール適用                                    │
│      - 配置可能者リスト生成                                  │
│      - 必要人数決定                                          │
│      - OR-Toolsモデル構築                                    │
│      - パワーバランス制約追加                                │
│      - 求解                                                 │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 7. 結果検証                                                 │
│    - ハード制約チェック                                      │
│    - ソフト制約チェック                                      │
│    - 統計情報計算                                            │
└────────────────────────┬───────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────┐
│ 8. 出力生成                                                 │
│    - 勤務表Excel生成                                         │
│    - 夜勤割当CSV生成                                         │
│    - 日勤配置CSV生成                                         │
│    - 制約チェックレポート生成                                │
└────────────────────────────────────────────────────────────┘
```

### 9.2 夜勤スケジューリング詳細フロー

```python
def schedule_night_shifts(month: str, staff_list: List[Staff], 
                          night_quotas: Dict[str, int],
                          requests: List[Request]) -> List[NightAssignment]:
    """夜勤スケジューリングのメイン処理"""
    
    # 1. 日付リスト生成
    dates = generate_dates(month)
    
    # 2. 夜勤可能者のフィルタリング
    night_capable = [s for s in staff_list if s.can_night_shift]
    
    # 3. 各技師の夜勤不可日・希望日を特定
    unavailable_days = {}  # {staff_id: [date1, date2, ...]}
    request_days = {}      # {staff_id: [date1, date2, ...]}
    
    for req in requests:
        if req.symbol in HOLIDAY_SYMBOLS:
            unavailable_days.setdefault(req.staff_id, []).append(req.date)
            # 前日も夜勤不可
            prev_day = req.date - timedelta(days=1)
            unavailable_days.setdefault(req.staff_id, []).append(prev_day)
        elif req.symbol == '夜希':
            request_days.setdefault(req.staff_id, []).append(req.date)
    
    # 4. OR-Toolsモデル構築
    model = cp_model.CpModel()
    
    # 決定変数: x[staff_id][date] = 1 if 夜勤配置
    x = {}
    for s in night_capable:
        for d in dates:
            x[s.id, d] = model.NewBoolVar(f'night_{s.id}_{d}')
    
    # 5. ハード制約追加
    add_night_hard_constraints(model, x, dates, night_capable, 
                               night_quotas, unavailable_days, request_days)
    
    # 6. ソフト制約追加（目的関数）
    objective_terms = add_night_soft_constraints(model, x, dates, night_capable)
    model.Minimize(sum(objective_terms))
    
    # 7. 求解
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 300
    status = solver.Solve(model)
    
    # 8. 結果抽出
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return extract_night_assignments(solver, x, dates, night_capable)
    else:
        raise SchedulingError("夜勤スケジュールが見つかりません")
```

### 9.3 日勤スケジューリング詳細フロー

```python
def schedule_day_shifts(date: datetime.date, 
                        staff_list: List[Staff],
                        locations: List[Location],
                        night_assignments: List[NightAssignment],
                        requests: List[Request],
                        skills: SkillMatrix) -> List[DayAssignment]:
    """特定日の日勤スケジューリング"""
    
    # 1. 曜日タイプ判定
    day_type = get_day_type(date)  # 'weekday', 'saturday', 'sunday_holiday'
    weekday = date.weekday()
    week_of_month = get_week_of_month(date)
    
    # 2. 配置不可者の特定
    unavailable = set()
    
    # 前日夜勤者
    prev_night = get_night_staff(night_assignments, date - timedelta(days=1))
    unavailable.update(prev_night)
    
    # 休み申請者
    for req in requests:
        if req.date == date and req.symbol in HOLIDAY_SYMBOLS:
            unavailable.add(req.staff_id)
    
    # 3. 特殊記号による固定配置
    fixed_placements = {}
    for req in requests:
        if req.date == date and req.symbol in SPECIAL_PLACEMENT_SYMBOLS:
            location = SPECIAL_PLACEMENT_SYMBOLS[req.symbol]
            fixed_placements[req.staff_id] = location
    
    # 4. OR-Toolsモデル構築
    model = cp_model.CpModel()
    
    # 決定変数: y[staff_id][location] = 1 if 配置
    y = {}
    available_staff = [s for s in staff_list if s.id not in unavailable]
    
    for s in available_staff:
        for loc in locations:
            if can_assign(s, loc, date, skills):
                y[s.id, loc.code] = model.NewBoolVar(f'day_{s.id}_{loc.code}')
    
    # 5. ハード制約追加
    add_day_hard_constraints(model, y, date, available_staff, locations, 
                             skills, fixed_placements, weekday, week_of_month)
    
    # 6. パワーバランス制約追加
    add_power_balance_constraints(model, y, date, available_staff, 
                                  locations, skills, weekday, week_of_month)
    
    # 7. 特殊配置ルール適用
    add_special_rules(model, y, date, available_staff, locations, 
                      skills, weekday, week_of_month)
    
    # 8. ソフト制約追加
    objective_terms = add_day_soft_constraints(model, y, available_staff, locations)
    model.Minimize(sum(objective_terms))
    
    # 9. 求解
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    # 10. 結果抽出
    if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return extract_day_assignments(solver, y, date, available_staff, locations)
    else:
        raise SchedulingError(f"{date}の日勤スケジュールが見つかりません")
```

---

## 10. アルゴリズム詳細

### 10.1 夜勤スケジューラー（OR-Tools CP-SAT）

#### 10.1.1 決定変数

```python
# x[s, d] ∈ {0, 1}: 技師sが日付dに夜勤かどうか
x = {}
for s in night_capable_staff:
    for d in dates:
        x[s.id, d] = model.NewBoolVar(f'night_{s.id}_{d}')
```

#### 10.1.2 ハード制約の実装

```python
def add_night_hard_constraints(model, x, dates, staff, quotas, unavailable, requests):
    """夜勤ハード制約の追加"""
    
    # NH-01: 毎日3名配置
    for d in dates:
        model.Add(sum(x[s.id, d] for s in staff) == 3)
    
    # NH-02: 月間回数遵守
    for s in staff:
        model.Add(sum(x[s.id, d] for d in dates) == quotas[s.id])
    
    # NH-03: 夜勤間隔3日以上
    for s in staff:
        for i, d in enumerate(dates):
            if i + 3 < len(dates):
                # d, d+1, d+2 の3日間で最大1回
                window = [dates[i], dates[i+1], dates[i+2]]
                model.Add(sum(x[s.id, w] for w in window) <= 1)
    
    # NH-04: 夜勤希望100%遵守
    for s in staff:
        if s.id in requests:
            for d in requests[s.id]:
                model.Add(x[s.id, d] == 1)
    
    # NH-05: 休み希望完全遵守（その日と前日夜勤不可）
    for s in staff:
        if s.id in unavailable:
            for d in unavailable[s.id]:
                if (s.id, d) in x:
                    model.Add(x[s.id, d] == 0)
    
    # NH-06: スキル制約（3名でMR/アンギオ/心カテをカバー）
    for d in dates:
        # MR対応可能者が1名以上
        mr_capable = [s for s in staff if s.night_mr]
        model.Add(sum(x[s.id, d] for s in mr_capable) >= 1)
        
        # アンギオ対応可能者が1名以上
        angio_capable = [s for s in staff if s.night_angio]
        model.Add(sum(x[s.id, d] for s in angio_capable) >= 1)
        
        # 心カテ対応可能者が1名以上
        cath_capable = [s for s in staff if s.night_cath]
        model.Add(sum(x[s.id, d] for s in cath_capable) >= 1)
```

#### 10.1.3 ソフト制約の実装

```python
def add_night_soft_constraints(model, x, dates, staff):
    """夜勤ソフト制約の追加（目的関数への項）"""
    penalties = []
    
    # NS-01: 週分散（同一週に複数夜勤を避ける）
    WEIGHT_WEEK = 100
    for s in staff:
        weeks = group_dates_by_week(dates)
        for week_dates in weeks.values():
            if len(week_dates) > 1:
                # 週内で2回以上の夜勤にペナルティ
                week_sum = sum(x[s.id, d] for d in week_dates)
                penalty = model.NewIntVar(0, 10, f'week_penalty_{s.id}_{week_dates[0]}')
                model.Add(penalty >= week_sum - 1)
                penalties.append(penalty * WEIGHT_WEEK)
    
    # NS-02: 日祝分散
    WEIGHT_HOLIDAY = 50
    sunday_holidays = [d for d in dates if is_sunday_or_holiday(d)]
    if sunday_holidays:
        avg = len(sunday_holidays) * 3 // len(staff)
        for s in staff:
            holiday_count = sum(x[s.id, d] for d in sunday_holidays)
            deviation = model.NewIntVar(0, 10, f'holiday_dev_{s.id}')
            model.Add(deviation >= holiday_count - avg)
            model.Add(deviation >= avg - holiday_count)
            penalties.append(deviation * WEIGHT_HOLIDAY)
    
    return penalties
```

### 10.2 日勤スケジューラー（OR-Tools CP-SAT）

#### 10.2.1 決定変数

```python
# y[s, l] ∈ {0, 1}: 技師sが場所lに配置されるかどうか
y = {}
for s in available_staff:
    for loc in locations:
        if has_skill(s, loc):
            y[s.id, loc.code] = model.NewBoolVar(f'day_{s.id}_{loc.code}')
```

#### 10.2.2 ハード制約の実装

```python
def add_day_hard_constraints(model, y, date, staff, locations, skills, 
                              fixed, weekday, week_of_month):
    """日勤ハード制約の追加"""
    
    # DH-01: 1人1場所のみ
    for s in staff:
        assigned_locs = [loc for loc in locations if (s.id, loc.code) in y]
        model.Add(sum(y[s.id, loc.code] for loc in assigned_locs) <= 1)
    
    # DH-03: 必要人数
    for loc in locations:
        required = get_required_count(loc, weekday, week_of_month)
        if required > 0:
            capable = [s for s in staff if (s.id, loc.code) in y]
            model.Add(sum(y[s.id, loc.code] for s in capable) == required)
    
    # DH-06: MG女性限定
    mg_loc = get_location('MG')
    if mg_loc:
        for s in staff:
            if s.gender == '男' and (s.id, 'MG') in y:
                model.Add(y[s.id, 'MG'] == 0)
    
    # 固定配置の適用
    for staff_id, loc_code in fixed.items():
        if (staff_id, loc_code) in y:
            model.Add(y[staff_id, loc_code] == 1)
```

#### 10.2.3 パワーバランス制約の実装

```python
def add_power_balance_constraints(model, y, date, staff, locations, 
                                   skills, weekday, week_of_month):
    """パワーバランス制約の追加"""
    
    for loc in locations:
        capable = [s for s in staff if (s.id, loc.code) in y]
        if not capable:
            continue
        
        # PB-01: 最低ランク人数
        pb_rules = get_power_balance_rules(loc.code)
        for rule in pb_rules:
            min_rank = rule['min_rank']
            min_count = rule['min_count']
            qualified = [s for s in capable 
                        if get_rank(skills, s.id, loc.code) >= min_rank]
            if qualified:
                model.Add(sum(y[s.id, loc.code] for s in qualified) >= min_count)
        
        # PB-02: CD上限（病CTの場合）
        if loc.code == '病CT':
            cd_staff = [s for s in capable 
                       if get_rank(skills, s.id, loc.code) in ['C', 'D']]
            if cd_staff:
                model.Add(sum(y[s.id, loc.code] for s in cd_staff) <= 3)
        
        # PB-04: ポータブルD×D禁止
        if loc.code == 'ポ':
            d_staff = [s for s in capable 
                      if get_rank(skills, s.id, loc.code) == 'D']
            if len(d_staff) >= 2:
                # D同士の組み合わせ禁止
                model.Add(sum(y[s.id, loc.code] for s in d_staff) <= 1)
        
        # PB-05: CT CD単独禁止
        if loc.code == 'CT':
            ab_staff = [s for s in capable 
                       if get_rank(skills, s.id, loc.code) in ['A', 'B']]
            if ab_staff:
                # A or B が最低1名
                model.Add(sum(y[s.id, loc.code] for s in ab_staff) >= 1)
```

#### 10.2.4 特殊配置ルールの実装

```python
def add_special_rules(model, y, date, staff, locations, skills, weekday, week_of_month):
    """特殊配置ルールの追加"""
    
    # SR-01: アンギオ火曜日 → Aランク2名
    if weekday == 1:  # 火曜日
        angio_loc = get_location('ア')
        a_rank_staff = [s for s in staff 
                       if (s.id, 'ア') in y and 
                          get_rank(skills, s.id, 'ア') == 'A']
        if a_rank_staff:
            model.Add(sum(y[s.id, 'ア'] for s in a_rank_staff) >= 2)
    
    # SR-03: HB第1金曜日 → Aランク2名
    if weekday == 4 and week_of_month == 1:
        hb_loc = get_location('HB')
        a_rank_staff = [s for s in staff 
                       if (s.id, 'HB') in y and 
                          get_rank(skills, s.id, 'HB') == 'A']
        if a_rank_staff:
            model.Add(sum(y[s.id, 'HB'] for s in a_rank_staff) >= 2)
    
    # SR-04: HB第4木曜日 → Aランク3名
    if weekday == 3 and week_of_month == 4:
        hb_loc = get_location('HB')
        a_rank_staff = [s for s in staff 
                       if (s.id, 'HB') in y and 
                          get_rank(skills, s.id, 'HB') == 'A']
        if a_rank_staff:
            model.Add(sum(y[s.id, 'HB'] for s in a_rank_staff) >= 3)
    
    # SR-05: OP第1金曜日 → HBのAランクから選出
    if weekday == 4 and week_of_month == 1:
        hb_a_staff = [s for s in staff 
                     if get_rank(skills, s.id, 'HB') == 'A' and 
                        (s.id, 'OP') in y]
        if hb_a_staff:
            # OPにはHBのAランク者を配置
            model.Add(sum(y[s.id, 'OP'] for s in hb_a_staff) == 1)
            # HBのAランク以外はOP配置不可
            for s in staff:
                if (s.id, 'OP') in y and s not in hb_a_staff:
                    model.Add(y[s.id, 'OP'] == 0)
    
    # SR-06: 精（病院TV）水金 → Aランクのみ
    if weekday in [2, 4]:  # 水曜・金曜
        sei_loc = get_location('精')
        non_a_staff = [s for s in staff 
                      if (s.id, '精') in y and 
                         get_rank(skills, s.id, '精') != 'A']
        for s in non_a_staff:
            model.Add(y[s.id, '精'] == 0)
```

---

## 11. 出力仕様

### 11.1 勤務表Excel

**ファイル名**: `勤務表_YYYYMM.xlsx`

**シート1: 勤務表**

| 形式 | 技師（行）× 日付（列）のマトリクス |
|------|-----------------------------------|
| セル内容 | 配置場所コード or 記号 |

**セル色分け**:
| 色 | 意味 |
|-----|------|
| 黄色 | 夜勤 |
| 水色 | 休み（★☆◆） |
| 緑色 | 特殊記号（17業、講、会議等） |
| オレンジ | 夜勤希望 |
| 灰色 | 夜勤明け |

**シート2: 夜勤表**

| 列 | 内容 |
|-----|------|
| 日付 | YYYY-MM-DD |
| 曜日 | 月〜日 |
| 夜勤者1 | 氏名（役割） |
| 夜勤者2 | 氏名（役割） |
| 夜勤者3 | 氏名（役割） |

**シート3: 統計**

| 項目 | 内容 |
|------|------|
| 技師別夜勤回数 | 各技師の夜勤回数 |
| 技師別日勤回数 | 各技師の日勤回数（場所別） |
| 場所別配置回数 | 各場所への延べ配置人数 |
| 制約充足率 | ハード制約/ソフト制約の充足状況 |

### 11.2 夜勤割当CSV

**ファイル名**: `夜勤割当_YYYYMM.csv`

```csv
日付,曜日,技師1_ID,技師1_氏名,技師1_役割,技師2_ID,技師2_氏名,技師2_役割,技師3_ID,技師3_氏名,技師3_役割
2025-12-01,月,T009,佐藤　和彦,MR,T015,池谷　尚人,アンギオ,T020,清水　万慈,心カテ
...
```

### 11.3 日勤配置CSV

**ファイル名**: `日勤配置_YYYYMM.csv`

```csv
日付,曜日,場所コード,配置人数,技師1_ID,技師1_氏名,技師2_ID,技師2_氏名,...
2025-12-01,月,病院MR,3,T004,関　悟,T006,加藤　義明,T007,福田　学
2025-12-01,月,クMR,5,T003,矢野　昌男,T011,渡邉　一博,...
...
```

### 11.4 制約チェックレポート

**ファイル名**: `制約チェック_YYYYMM.txt`

```
=== 放射線技師勤務表 制約チェックレポート ===
対象月: 2025年12月
生成日時: 2025-12-11 10:30:00

【ハード制約チェック】
NH-01 人数制約: ✓ OK (31日すべて3名配置)
NH-02 回数遵守: ✓ OK (全38名の回数一致)
NH-03 間隔制約: ✓ OK (違反なし)
NH-04 夜勤希望: ✓ OK (15件すべて反映)
NH-05 休み遵守: ✓ OK (違反なし)
NH-06 スキル制約: ✓ OK (全日スキルカバー)

DH-01 単一配置: ✓ OK
DH-02 スキル必須: ✓ OK
DH-03 必要人数: ✓ OK
DH-04 休み遵守: ✓ OK
DH-05 夜勤明け: ✓ OK
DH-06 性別制約: ✓ OK

【ソフト制約チェック】
NS-01 週分散: 違反3件（軽微）
NS-02 日祝分散: 標準偏差 0.8
DS-01 業務均等化: 標準偏差 2.3

【特殊配置ルールチェック】
SR-01 ア火曜Aランク2名: ✓ OK (4日すべて)
SR-03 HB第1金曜Aランク2名: ✓ OK
SR-04 HB第4木曜Aランク3名: ✓ OK
SR-05 OP第1金曜HB-A選出: ✓ OK
SR-06 精水金Aランク: ✓ OK

【統計情報】
総配置数: 1,523件
夜勤延べ人数: 93人
日勤延べ人数: 1,430人
平均日勤回数: 21.7回/人
```

---

## 12. エラーハンドリング

### 12.1 エラーコード一覧

| コード | カテゴリ | 説明 | 対処法 |
|--------|----------|------|--------|
| E001 | データ | 技師マスタが見つからない | ファイルパス確認 |
| E002 | データ | スキルマスタが見つからない | ファイルパス確認 |
| E003 | データ | 夜勤回数合計が日数×3と不一致 | 回数調整 |
| E004 | データ | 技師IDの重複 | マスタ修正 |
| E005 | データ | 無効なスキルランク | A/B/C/D/-のみ許可 |
| E010 | 夜勤 | 夜勤スケジュール不能 | 制約緩和 |
| E011 | 夜勤 | 夜勤希望が実現不可能 | 希望調整 |
| E020 | 日勤 | 日勤スケジュール不能 | 制約緩和 |
| E021 | 日勤 | 必要人数不足 | スキル確認 |

### 12.2 制約緩和プロセス

夜勤スケジュールが見つからない場合の緩和順序：

```python
def solve_with_relaxation(model, x, dates, staff):
    """制約緩和付き求解"""
    
    relaxation_steps = [
        ('週分散', relax_week_distribution),
        ('日祝分散', relax_holiday_distribution),
        ('夜勤間隔', relax_night_interval),  # 3日→2日
    ]
    
    for step_name, relax_func in relaxation_steps:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 60
        status = solver.Solve(model)
        
        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return solver, status
        
        print(f"制約緩和: {step_name}")
        relax_func(model, x, dates, staff)
    
    raise SchedulingError("制約緩和後も解が見つかりません")
```

---

## 13. 実装ガイド

### 13.1 ディレクトリ構成

```
shift_scheduler/
├── main.py                 # エントリーポイント
├── config.py               # 設定管理
├── requirements.txt        # 依存パッケージ
├── data/                   # 入力データ
│   ├── 技師マスタ.csv
│   ├── スキルマスタ.csv
│   ├── 勤務場所マスタ.csv
│   ├── 特殊配置ルール.csv
│   ├── 予定申請_202512.csv
│   └── 夜勤回数_202512.csv
├── output/                 # 出力先
├── src/
│   ├── __init__.py
│   ├── models/             # データモデル
│   │   ├── __init__.py
│   │   ├── staff.py
│   │   ├── location.py
│   │   ├── skill.py
│   │   └── request.py
│   ├── loaders/            # データローダー
│   │   ├── __init__.py
│   │   ├── staff_loader.py
│   │   ├── skill_loader.py
│   │   └── request_loader.py
│   ├── schedulers/         # スケジューラー
│   │   ├── __init__.py
│   │   ├── night_scheduler.py
│   │   └── day_scheduler.py
│   ├── constraints/        # 制約定義
│   │   ├── __init__.py
│   │   ├── night_constraints.py
│   │   ├── day_constraints.py
│   │   └── special_rules.py
│   ├── validators/         # 検証
│   │   ├── __init__.py
│   │   └── constraint_checker.py
│   └── exporters/          # 出力
│       ├── __init__.py
│       ├── excel_exporter.py
│       └── csv_exporter.py
└── tests/                  # テスト
    ├── __init__.py
    ├── test_night_scheduler.py
    └── test_day_scheduler.py
```

### 13.2 依存パッケージ

**requirements.txt**:
```
ortools>=9.7.0
pandas>=2.0.0
openpyxl>=3.1.0
jpholiday>=0.1.8
pyyaml>=6.0
pytest>=7.0.0
```

### 13.3 実行コマンド

```bash
# 環境構築
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 実行
python main.py --month 2025-12

# オプション
python main.py --month 2025-12 --debug          # デバッグモード
python main.py --month 2025-12 --output ./out   # 出力先指定
python main.py --month 2025-12 --timeout 600    # タイムアウト指定
```

### 13.4 設定ファイル

**config.yaml**:
```yaml
# パス設定
data_dir: ./data
output_dir: ./output

# ソルバー設定
solver:
  timeout_seconds: 300
  num_workers: 4

# 夜勤設定
night_shift:
  staff_count: 3
  min_interval_days: 3
  
# ソフト制約重み
weights:
  week_distribution: 100
  holiday_distribution: 50
  saturday_distribution: 50
  workload_balance: 50
  consecutive_placement: 10

# 出力設定
output:
  excel_enabled: true
  csv_enabled: true
  report_enabled: true
```

---

## 付録A: データモデル定義

### A.1 Enumeration

```python
from enum import Enum

class SkillRank(Enum):
    """スキルランク"""
    A = 4  # エキスパート
    B = 3  # 一人前
    C = 2  # 標準
    D = 1  # 新人
    NONE = 0  # スキルなし
    
    @classmethod
    def from_string(cls, s: str) -> 'SkillRank':
        mapping = {'A': cls.A, 'B': cls.B, 'C': cls.C, 'D': cls.D, '-': cls.NONE}
        return mapping.get(s, cls.NONE)
    
    def __ge__(self, other):
        return self.value >= other.value

class Gender(Enum):
    """性別"""
    MALE = '男'
    FEMALE = '女'

class DayType(Enum):
    """曜日タイプ"""
    WEEKDAY = 'weekday'
    SATURDAY = 'saturday'
    SUNDAY_HOLIDAY = 'sunday_holiday'
```

### A.2 データクラス

```python
from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Dict

@dataclass
class Staff:
    """技師"""
    id: str
    name: str
    gender: Gender
    experience_years: int
    can_night_shift: bool
    status: str
    note: str = ""
    
    # 夜勤スキル（導出値）
    night_mr: bool = False
    night_angio: bool = False
    night_cath: bool = False

@dataclass
class Location:
    """勤務場所"""
    code: str
    name: str
    category: str
    required_count: Dict[int, int]  # {weekday: count}
    gender_constraint: Optional[str]
    display_order: int
    is_active: bool

@dataclass
class SkillEntry:
    """スキルエントリ"""
    staff_id: str
    location_code: str
    rank: SkillRank

@dataclass
class PowerBalanceRule:
    """パワーバランスルール"""
    location_code: str
    min_rank: SkillRank
    min_count: int
    cd_limit: Optional[int]
    no_d_alone: bool

@dataclass
class SpecialRule:
    """特殊配置ルール"""
    rule_id: str
    location_code: str
    weekday: Optional[int]  # None = 全日
    week_of_month: Optional[int]  # None = 毎週
    total_count: int
    min_rank: Optional[SkillRank]
    min_rank_count: int
    source_location: Optional[str]  # 選出元の場所
    source_rank: Optional[SkillRank]  # 選出元のランク条件

@dataclass
class Request:
    """予定申請"""
    staff_id: str
    date: date
    symbol: str
    note: str = ""

@dataclass
class NightQuota:
    """夜勤回数"""
    staff_id: str
    count: int

@dataclass
class NightAssignment:
    """夜勤割当結果"""
    date: date
    staff_id: str
    role: str  # 'MR', 'アンギオ', '心カテ'

@dataclass
class DayAssignment:
    """日勤配置結果"""
    date: date
    location_code: str
    staff_id: str
    rank: SkillRank
```

---

## 付録B: 制約条件一覧表

### B.1 夜勤制約

| ID | 種別 | 制約名 | 数式表現 | 重み |
|----|------|--------|----------|------|
| NH-01 | ハード | 人数制約 | Σx[s,d] = 3, ∀d | - |
| NH-02 | ハード | 回数遵守 | Σx[s,d] = quota[s], ∀s | - |
| NH-03 | ハード | 間隔制約 | x[s,d] + x[s,d+1] + x[s,d+2] ≤ 1 | - |
| NH-04 | ハード | 夜勤希望 | x[s,d] = 1 if request[s,d] | - |
| NH-05 | ハード | 休み遵守 | x[s,d] = 0 if holiday[s,d] | - |
| NH-06 | ハード | スキル制約 | Σx[s,d] ≥ 1, ∀skill | - |
| NS-01 | ソフト | 週分散 | min Σpenalty_week | 100 |
| NS-02 | ソフト | 日祝分散 | min Σdeviation_holiday | 50 |
| NS-03 | ソフト | 土曜分散 | min Σdeviation_saturday | 50 |

### B.2 日勤制約

| ID | 種別 | 制約名 | 数式表現 | 重み |
|----|------|--------|----------|------|
| DH-01 | ハード | 単一配置 | Σy[s,l] ≤ 1, ∀s | - |
| DH-02 | ハード | スキル必須 | y[s,l] = 0 if skill[s,l] = NONE | - |
| DH-03 | ハード | 必要人数 | Σy[s,l] = required[l,weekday] | - |
| DH-04 | ハード | 休み遵守 | y[s,l] = 0 if holiday[s] | - |
| DH-05 | ハード | 夜勤明け | y[s,l] = 0 if night[s,d-1] | - |
| DH-06 | ハード | 性別制約 | y[s,'MG'] = 0 if s.gender = MALE | - |
| PB-01 | ハード | 最低ランク | Σy[s,l] ≥ min_count, rank[s,l] ≥ min_rank | - |
| PB-02 | ハード | CD上限 | Σy[s,l] ≤ limit, rank[s,l] ∈ {C,D} | - |
| DS-01 | ソフト | 業務均等化 | min Σdeviation_workload | 50 |
| DS-02 | ソフト | 連続配置 | max Σconsecutive_bonus | 10 |

---

## 付録C: 技師・スキルマスタ

### C.1 技師マスタ（66名）

| ID | 氏名 | 性別 | 経験 | 夜勤 | 備考 |
|----|------|------|------|------|------|
| T001 | 加藤　光久 | 男 | 30 | × | 管理職 |
| T002 | 石川　和弥 | 男 | 30 | ○ | |
| T003 | 矢野　昌男 | 男 | 30 | × | MRI専門 |
| T004 | 関　悟 | 男 | 30 | × | MRI専門 |
| T005 | 里見　力 | 男 | 25 | × | 治療 |
| T006 | 加藤　義明 | 男 | 25 | × | MRI専門 |
| T007 | 福田　学 | 男 | 25 | × | |
| T008 | 河西　佐和子 | 女 | 25 | × | |
| T009 | 佐藤　和彦 | 男 | 25 | ○ | |
| T010 | 川向　克茂 | 男 | 20 | × | |
| T011 | 渡邉　一博 | 男 | 20 | × | |
| T012 | 須田　章則 | 男 | 18 | ○ | |
| T013 | 永井　基博 | 男 | 18 | ○ | |
| T014 | 小野　雄一朗 | 男 | 15 | ○ | |
| T015 | 池谷　尚人 | 男 | 15 | ○ | |
| T016 | 下田　あず沙 | 女 | 13 | × | |
| T017 | 白倉　知明 | 男 | 12 | ○ | |
| T018 | 増田　翔太 | 男 | 11 | ○ | |
| T019 | 小川　龍史 | 男 | 10 | ○ | |
| T020 | 清水　万慈 | 女 | 10 | ○ | |
| T021 | 橋本　圭市 | 男 | 8 | ○ | |
| T022 | 原田　勝人 | 男 | 8 | ○ | |
| T023 | 箕輪　綱平 | 男 | 8 | ○ | |
| T024 | 石井　哲也 | 男 | 7 | ○ | |
| T025 | 森　拓磨 | 男 | 6 | ○ | |
| T026 | 川名　佑樹 | 男 | 5 | ○ | |
| T027 | 大島　七泉 | 男 | 4 | ○ | |
| T028 | 児玉　勇輝 | 男 | 4 | ○ | |
| T029 | 佐藤　海夢 | 男 | 4 | ○ | |
| T030 | 祝部　琉海 | 女 | 4 | ○ | |
| T031 | 嶋田　帆波 | 女 | 4 | × | |
| T032 | 細谷　祐太 | 男 | 4 | ○ | |
| T033 | 大村　直輝 | 男 | 4 | ○ | |
| T034 | 星　和馬 | 男 | 4 | ○ | |
| T035 | 細谷　菜々 | 女 | 3 | ○ | |
| T036 | 良本　彩華 | 女 | 3 | ○ | |
| T037 | 松井　芙美佳 | 女 | 3 | ○ | |
| T038 | 飯塚　陽人 | 男 | 3 | ○ | |
| T039 | 斎藤　来夢 | 男 | 3 | ○ | |
| T040 | 宮野　拓也 | 男 | 3 | ○ | |
| T041 | 塚田　敦弥 | 男 | 3 | × | |
| T042 | 平野　迅人 | 男 | 2 | ○ | |
| T043 | 田﨑　来実 | 女 | 2 | ○ | |
| T044 | 平野　裕理 | 女 | 2 | ○ | |
| T045 | 堺　結尋 | 男 | 2 | ○ | |
| T046 | 大浦　駿介 | 男 | 2 | ○ | |
| T047 | 鈴木　りんか | 女 | 2 | ○ | |
| T048 | 髙谷　ひな | 女 | 2 | ○ | |
| T049 | 野口　愛里彩 | 女 | 1 | × | 新人 |
| T050 | 谷　雄貴 | 男 | 1 | × | 新人 |
| T051 | 中村　友海 | 女 | 1 | × | 新人 |
| T052 | 藤井　華帆 | 女 | 1 | × | 新人 |
| T053 | 牧　智史 | 男 | 1 | × | 新人 |
| T054 | 小出　眞也 | 男 | 20 | × | 核医学 |
| T055 | 畠山　秀人 | 男 | 20 | × | 核医学 |
| T056 | 友邉　和哉 | 男 | 14 | ○ | 核医学 |
| T057 | 池田　侑斗 | 男 | 2 | × | 核医学 |
| T058 | 植野　俊 | 男 | 1 | × | 核医学 |
| T059 | 高重　光博 | 男 | 20 | × | 治療 |
| T060 | 苅込　真子 | 女 | 20 | × | 治療 |
| T061 | 松本　梓 | 女 | 15 | ○ | 治療 |
| T062 | 棚町　麻耶 | 女 | 3 | × | 治療 |
| T063 | 佐藤　正哉 | 男 | 4 | × | 治療 |
| T064 | 荒井　美桜 | 女 | 2 | × | 治療 |
| T065 | 今溝　愛海 | 女 | 1 | × | 治療 |
| T066 | 遠藤　健太郎 | 男 | 20 | × | 館山 |

### C.2 夜勤対象者（38名）

夜勤可否=○ の技師：
T002, T009, T012, T013, T014, T015, T017, T018, T019, T020, 
T021, T022, T023, T024, T025, T026, T027, T028, T029, T030, 
T032, T033, T034, T035, T036, T037, T038, T039, T040, T042, 
T043, T044, T045, T046, T047, T048, T056, T061

---

## 改訂履歴

| バージョン | 日付 | 変更内容 |
|------------|------|----------|
| 1.0 | 2025-12-10 | 初版作成 |
| 2.0 | 2025-12-11 | 特殊配置ルール詳細化、パワーバランス追加、Numbersデータ反映 |
| 2.1 | 2026-01-14 | 月跨ぎの夜勤間隔調整ルールの実装を反映 |
| 2.2 | 2026-01-20 | 予定申請の記号追加（出/(役)、研(座)等）、6連勤禁止、超遅明けルールの追加 |
| 2.3 | 2026-02-12 | 「M遅」シフトの追加（それに伴うクMRの月〜木配置数減）、日祝と明休日祝の夜勤回数均等化（ハード制約＋増分ペナルティ）の実装を反映 |

---

**文書終了**
