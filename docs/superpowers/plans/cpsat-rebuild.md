# CP-SAT 全体最適化 作り直し計画

## 目的（2026-06-14 確定）
- ク6回(T013小野/T025川名) を**修正**（現状5→6にハード床で強制）
- 場所別担当回数の偏り（CT/ク）を**公平化**で縮小
- 代休0・全特殊ルール維持を制約で担保

## 設計原則：ルールを全部書き直さない
1. **ルールが触る全セルを凍結 or 不変条件で保護**（列挙漏れの安全網）
   - 凍結: 夜勤/明け, FORCED申請, COND平日, LATE(遅番系), 非loc_code,
     T001病CT/CT, T072館山, MRI専従(T003/4/5)の病院MR/CLMR, PET
   - 不変条件(rank-floor): 各スロットで A数≥現状 / AB数≥現状 / D数≤現状
     → SR-01〜09b・パワーバランス(病CT A2B1CD3, ク A3, ポD単独可 等)を自動維持
     （入力が合法 ⇒ 構成を悪化させない限り壊れない）
2. **明示エンコードは月間カウント系の数件のみ**
   - ク6: T013/T025 を ク について凍結解除し、Σy[ク] ≥ 6 のハード床
   - 同日ク禁止: y[T013,d,ク] + y[T025,d,ク] ≤ 1
   - ク gender = なし（女性制約不要）
3. **代休を悪化させない**: 各人 over[sid] ≤ baseline_over[sid] のハード制約
4. **連勤≤6** ハード
5. **反映は「解からの再構築」**（前回バグの根治）
   - スロット構成員の元DayAssignmentを id() で識別して破棄
   - solver採用者で新規DayAssignmentを生成
   - 新規勤務者の旧 休/○ セルは除去（重複防止）
   - 凍結セル・他月は完全に温存
6. **採否ゲート**: status∈{OPTIMAL,FEASIBLE} かつ 個人代休非悪化を確認した時だけ
   再構築。それ以外は元の day_result_list をそのまま返す（無害フォールバック）
7. **毎回 scratch/verify_schedule.py で全ルール検算**（リグレッション検知）

## 公平化目的関数
- 対象 base: CT(=CT+病CT) と ク。超遅/ク遅=LATEで移動不可のため除外、ポ/MG小プールは後段。
- eligible(B) = 在籍・非MRI専従・Bの有資格・B保護対象外(CT→T001除外, ク→T013/T025除外)
- count[sid,B] = fixed割当 + Σ y[(sid,d,L) : fair_base(L)=B]
- excess[sid,B] ≥ count - ceil(mean_B),  mean_B = Σcount_eligible / |eligible|
- Minimize Σ excess（ピークを均す＝総数固定なので谷も持ち上がる）

## ソルバ設定（決定性）
num_workers=1, max_deterministic_time=120, random_seed=42, 全set反復をソート

## 検証手順
1. greedyのみ baseline 生成・verify（7月: 代休0, ク=5/5違反, CT幅21, ク幅8）
2. CP-SAT有効化して7月生成・verify → ク=6/6, CT幅・ク幅縮小, 代休0維持, 警告0
3. 6月でもリグレッションなしを確認
4. 決定性: 同一入力3回で同一出力
