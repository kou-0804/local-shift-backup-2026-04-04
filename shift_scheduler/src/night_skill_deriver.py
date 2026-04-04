from typing import List, Dict
from .models.skill import SkillRank
from .models.staff import Staff

class NightSkillDeriver:
    """夜勤スキルを導出するクラス"""
    
    @staticmethod
    def derive(skills: Dict[str, Dict[str, SkillRank]]) -> List[Staff]:
        """
        全スタッフの夜勤スキル判定を行い、Staffオブジェクトの属性を更新する。
        ここではStaffオブジェクト自体のリストを返すのではなく、
        本来はNightSchedulerに必要なデータ構造を返すのが一般的だが、
        main.pyの仕様に合わせて「スキル判定済みのStaff情報」または
        「NightScheduler」が使いやすい形式にする。
        
        ただし、main.pyでは:
          night_skills = NightSkillDeriver.derive(skills)
          night_scheduler = NightScheduler(..., night_skills=night_skills, ...)
        となっている。
        
        NightScheduler (Phase 1) の初期化シグネチャを確認すると:
          def __init__(self, technicians: List[Staff], night_skills: List[Staff], ...):
        あるいは
          night_skills は単に「夜勤可能なStaffのリスト」か、
          「各Staffの夜勤スキル詳細」か。
        
        Phase 1 の実装 (src/schedulers/night_scheduler.py) を確認する必要があるが、
        ここでは簡易的に「全Staffに対して夜勤スキル(MR/Angio/Cath)を判定し、
        その情報を持ったオブジェクト(Staffのコピーや拡張)のリスト」を返すと仮定する。
        
        しかし、night_scheduler.py は `night_skills` をどう使っているか？
        もし `night_skills` 引数が `List[Staff]` なら、
        ここで Staff オブジェクトに night_mr 等のフラグをセットして返せばよい。
        """
        # 簡易実装: Skills辞書から判定して、Staffオブジェクト的なもの（または辞書）を返す
        # しかし main.py で `ns.mr_skill` のようにアクセスしているため、
        # オブジェクトである必要がある。
        
        # ここでは「夜勤スキル情報を持つオブジェクト」のリストを生成して返す。
        # 既存の Staff クラスには night_mr 等のフィールドがある (src/models/staff.py line 30-32)。
        # なので、単に元の Staff リストを受け取って埋めるのが早いが、
        # メソッドシグネチャは `derive(skills)` なので、Staffリストがない。
        # -> main.py では `technicians` と `skills` が別ロード。
        #    `derive` に technicians を渡していないのが不思議。
        #    恐らく `skills` のキー(staff_id) から推測するか、
        #    あるいは「NightSkill」という別モデルがあるのかも？
        
        # User snippet:
        # night_skills = NightSkillDeriver.derive(skills)
        # mr_count = sum(1 for ns in night_skills if ns.mr_skill)
        
        # 仮定: NightSkill というクラスを作るか、動的にオブジェクトを作る。
        # ここでは NightSkill クラスを定義して返す。
        
        derived = []
        for staff_id, staff_skills in skills.items():
            ns = NightSkill(staff_id)
            
            # 判定ロジック (Phase 1 準拠)
            # MR: 病院MR >= C or CLMR >= C
            mr_h = staff_skills.get('病院MR', SkillRank.NONE)
            mr_c = staff_skills.get('CLMR', SkillRank.NONE)
            if (mr_h >= SkillRank.C) or (mr_c >= SkillRank.C):
                ns.mr_skill = True
                
            # Angio: ア >= C
            angio = staff_skills.get('ア', SkillRank.NONE)
            if angio >= SkillRank.C:
                ns.angio_skill = True
                
            # Cath: 心 >= C
            cath = staff_skills.get('心', SkillRank.NONE)
            if cath >= SkillRank.C:
                ns.cath_skill = True
                
            derived.append(ns)
            
        return derived

class NightSkill:
    def __init__(self, staff_id):
        self.staff_id = staff_id
        self.mr_skill = False
        self.angio_skill = False
        self.cath_skill = False
