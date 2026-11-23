"""Build the LZU local-unit seed from official LZU inventories.

Sources are recorded per entry. College-level names that the official page only
mentions as a count are deliberately not invented; unnamed units stay out until
the college publishes a name list.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "src" / "litradar" / "data" / "lzu_units_seed.json"

VERIFIED = "2026-11-23"
UNIT = "兰州大学"
UNIT_ALIASES = ["兰州大学", "兰大", "LZU", "Lanzhou University"]
ROR = "https://ror.org/01mkqqe32"

HUMANITIES_SRC = "https://www.lzu.edu.cn/kxyj/kypt1/rwsklzdyjjd.htm"
NATURAL_SRC = "https://kyy.lzu.edu.cn/keyanyuan/upload/files/20211209/f7fcac56070943589ba1a8acd711b79f.pdf"
OLD_TEACH_SRC = "https://oldwww.lzu.edu.cn/static/jxdw/"
MARX_SRC = "https://marx.lzu.edu.cn/xygk/xyjj.htm"
MARX_PLATFORM_SRC = "https://marx.lzu.edu.cn/info/1111/2020.htm"
PHIL_SRC = "https://zheshexi.lzu.edu.cn/kexueyanjiu/yanjiupingtai/2021/0602/175293.html"
PHIL_ORG_SRC = "https://zheshexi.lzu.edu.cn/xueyuangaikuang/zuzhijigou/jiaoxuekeyan/index.html"
LIT_SRC = "https://chinese.lzu.edu.cn/bumengaikuang/yanjiusuoshezhi/2013/1230/107689.html"
LIT_CENTER_SRC = "https://jwc.lzu.edu.cn/jiaowufuwu/lddkxkkt/2024/1127/289459.html"
JOUR_SRC = "https://xwxy.lzu.edu.cn/kexueyanjiu/yanjiupingtai/index.html"
HIST_SRC = "https://baike.baidu.com/item/兰州大学历史文化学院"
ECON_SRC = "http://jjxy.lzu.edu.cn:80/hdmbi/bas/col.php?sn=xyjj"
MATH_SRC = "https://math.lzu.edu.cn/kxyj/yjs.htm"
MAT_SRC = "https://mat.lzu.edu.cn/page/cid/39.html"
NUCLEAR_SRC = "https://snst.lzu.edu.cn/ceshiyemian/index.html"
VET_SRC = "https://vet.lzu.edu.cn/jigoushezhi/xisuoshezhi/"
INFO_SRC = "https://xxxy.lzu.edu.cn/xueyuangaikuang/xueyuanjianjie/"
CIVIL_SRC = "https://gxy.lzu.edu.cn/xueyuanjieshao/zuzhijiegou/2012/0510/106051.html"
ATMOS_SRC = "https://atmos.lzu.edu.cn/html/dqxy/lddqxy/xueyuangk/xueyuanjj/1826530480951934978.html"
LAW_SRC = "https://oldwww.lzu.edu.cn/static/jxdw/"
FOREIGN_SRC = "https://oldwww.lzu.edu.cn/static/jxdw/"
ART_SRC = "https://oldwww.lzu.edu.cn/static/jxdw/"
PHARM_SRC = "http://yxy.lzu.edu.cn/"
BASICMED_SRC = "https://jchyxy.lzu.edu.cn/kexueyanjiu/keyanjigou/index.html"
SPH_SRC = "https://sph.lzu.edu.cn/xueyuangaikuang/xueyuanjianjie/"
STOM_SRC = "https://kqyxy.lzu.edu.cn/xueyuangaikuang/xueyuanyiyuangaikuang/index.html"
NURSING_SRC = "https://ldyxy.lzu.edu.cn/hdupf/fil/202308/202308231692767648703085.pdf"
FIRST_HOSP_SRC = "https://www.lzdxdyyy.com/Web/Ldyy/OrganizationUnit"
SPORT_SRC = "https://oldwww.lzu.edu.cn/static/jxdw/"

DEPTS = {
    "马克思主义学院": ["马院", "兰大马院"],
    "哲学社会学院": ["哲社院", "哲学社会学院"],
    "经济学院": ["经院", "兰大经院"],
    "法学院": ["法学", "兰大法学院"],
    "政治与国际关系学院": ["政国院", "政治国关", "政治与国际关系学院"],
    "文学院": ["文院", "兰大文学院"],
    "外国语学院": ["外语院", "外院"],
    "新闻与传播学院": ["新传院", "新闻院"],
    "历史文化学院": ["历史院", "历文院"],
    "管理学院": ["管院", "兰大管院"],
    "艺术学院": ["艺术院"],
    "数学与统计学院": ["数统院", "数学院"],
    "物理科学与技术学院": ["物理院", "物理学院"],
    "化学化工学院": ["化学院", "化工院"],
    "资源环境学院": ["资环院", "资源环境"],
    "大气科学学院": ["大气院", "大气科学"],
    "地质科学与矿产资源学院": ["地矿院", "地质学院"],
    "生命科学学院": ["生科院", "生命学院"],
    "土木工程与力学学院": ["土木院", "工学院"],
    "材料与能源学院": ["材能院", "材料院"],
    "信息科学与工程学院": ["信息院", "信工院"],
    "核科学与技术学院": ["核学院", "核科学"],
    "草地农业科技学院": ["草科院", "草业学院"],
    "生态学院": ["生态院"],
    "动物医学与生物安全学院": ["动医院", "动医学院"],
    "基础医学院": ["基医院", "基础医学"],
    "口腔医学院": ["口腔院", "口腔医院"],
    "公共卫生学院": ["公卫院", "公卫"],
    "药学院": ["药院"],
    "护理学院": ["护理院"],
    "第一临床医学院": ["第一医院", "兰大一院"],
    "第二临床医学院": ["第二医院", "兰大二院"],
    "体育学院": ["体育部"],
    "高等教育研究院": ["高教院", "高教所"],
    "校级科研机构": ["校级", "学校", "兰大校级"],
    "图书馆": ["兰大图书馆"],
    "应用技术研究院": ["应用院"],
}
CODES = {
    "马克思主义学院": "marx",
    "哲学社会学院": "phil",
    "经济学院": "econ",
    "法学院": "law",
    "政治与国际关系学院": "polit",
    "文学院": "lit",
    "外国语学院": "fl",
    "新闻与传播学院": "jour",
    "历史文化学院": "hist",
    "管理学院": "mgmt",
    "艺术学院": "art",
    "数学与统计学院": "math",
    "物理科学与技术学院": "phys",
    "化学化工学院": "chem",
    "资源环境学院": "res",
    "大气科学学院": "atmos",
    "地质科学与矿产资源学院": "geo",
    "生命科学学院": "life",
    "土木工程与力学学院": "civil",
    "材料与能源学院": "mat",
    "信息科学与工程学院": "info",
    "核科学与技术学院": "nuc",
    "草地农业科技学院": "caoye",
    "生态学院": "eco",
    "动物医学与生物安全学院": "vet",
    "基础医学院": "med",
    "口腔医学院": "stom",
    "公共卫生学院": "sph",
    "药学院": "pharm",
    "护理学院": "nurse",
    "第一临床医学院": "h1",
    "第二临床医学院": "h2",
    "体育学院": "sport",
    "高等教育研究院": "hed",
    "校级科研机构": "uni",
    "图书馆": "lib",
    "应用技术研究院": "app",
}


def type_of(name: str) -> tuple[str, str]:
    if "实验室" in name:
        return "lab", "实验室"
    if "研究院" in name:
        return "institute", "研究院"
    if "研究所" in name:
        return "institute", "研究所"
    if "研究中心" in name or name.endswith("中心"):
        return "center", "研究中心"
    if "基地" in name or "平台" in name:
        return "platform", "平台"
    if "智库" in name:
        return "think_tank", "智库"
    if "团队" in name:
        return "team", "研究团队"
    return "research_unit", "科研单元"


def norm(name: str) -> str:
    value = re.sub(r"\s+", "", name)
    value = value.replace("—", "-").replace("－", "-")
    value = re.sub(r"^兰州大学[-—]?", "", value)
    return value


def short_name(name: str) -> str:
    value = name.replace("兰州大学", "")
    value = re.sub(r"（[^）]*）", "", value)
    value = value.strip("-— ")
    return value[:18]


seed = json.loads(SEED.read_text(encoding="utf-8"))
existing = {norm(item["name"]): item for item in seed}
added: list[dict] = []
seen: dict[str, dict] = {}


def add(
    name: str,
    dept: str,
    *,
    leader: str = "",
    source: str,
    authority: str,
    level: str,
    note: str = "",
    aliases: list[str] | None = None,
    source_label: str = "兰大官网核验档",
):
    key = norm(name)
    if key in existing:
        return
    if key in seen:
        item = seen[key]
        if not item.get("leader") and leader:
            item["leader"] = leader
        return
    code = CODES.get(dept, "unit")
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    type_key, type_label = type_of(name)
    item = {
        "institution": UNIT,
        "department": dept,
        "unit_ror": ROR,
        "parent_id": f"lzu-{code}",
        "platform": "",
        "source": source,
        "source_kind": "cn_local",
        "source_label": source_label,
        "verified": VERIFIED,
        "id": f"lzu-{code}-{digest}",
        "name": name,
        "short": short_name(name),
        "type": type_key,
        "type_label": type_label,
        "aliases": list(dict.fromkeys(aliases or [name.replace("兰州大学", ""), short_name(name)])),
        "directions": [],
        "leader": leader,
        "members": [],
        "note": note,
        "unit": UNIT,
        "country": "CN",
        "country_name": "中国",
        "region": "甘肃",
        "unit_aliases": UNIT_ALIASES,
        "department_aliases": DEPTS.get(dept, [dept]),
        "school_code": "10730",
        "province": "甘肃",
        "authority": authority,
        "level": level,
    }
    added.append(item)
    seen[key] = item


# 1) School-level humanities research bases (official page, 37 unique after
#    dropping two duplicate rows and two museum entries).
for name, dept, leader in [
    ("敦煌学研究所", "历史文化学院", ""),
    ("西北少数民族研究中心", "历史文化学院", ""),
    ("中国边疆安全研究中心", "历史文化学院", ""),
    ("中亚研究所", "政治与国际关系学院", ""),
    ("阿富汗研究中心", "政治与国际关系学院", ""),
    ("印度研究中心", "政治与国际关系学院", ""),
    ("格鲁吉亚研究中心", "政治与国际关系学院", ""),
    ("意大利研究中心", "政治与国际关系学院", ""),
    ("高校思想政治工作创新发展中心（兰州大学）", "马克思主义学院", "安俊堂"),
    ("国家语言文字推广基地（兰州大学）", "文学院", ""),
    ("西北“花儿”传承基地", "艺术学院", ""),
    ("欧盟研究中心", "历史文化学院", ""),
    ("中国民族地区残疾人事业发展研究中心", "历史文化学院", ""),
    ("中国梦研究中心", "马克思主义学院", ""),
    ("老龄科研基地", "哲学社会学院", "周亚平"),
    ("丝绸之路经济带建设研究中心", "经济学院", ""),
    ("中国西部循环经济研究中心", "经济学院", ""),
    ("社会与发展研究评价中心", "哲学社会学院", "陈文江"),
    ("西部地区区域经济发展与区域政策研究中心", "经济学院", ""),
    ("中国政府绩效管理研究中心", "管理学院", "包国宪"),
    ("思想政治教育理论与实践创新研究中心", "马克思主义学院", "宫长瑞"),
    ("生态文明建设研究与评估中心", "哲学社会学院", ""),
    ("社会舆论调查与舆情研判中心", "新闻与传播学院", ""),
    ("高校思想政治教育舆情与对策研究中心", "马克思主义学院", "李东坡"),
    ("县域经济发展研究院（乡村振兴战略研究院）", "经济学院", ""),
    ("学科发展与评价研究中心", "高等教育研究院", ""),
    ("社区发展与反贫困智库", "哲学社会学院", "陈文江"),
    ("考古与文化遗产研究院", "历史文化学院", ""),
    ("一带一路多语言研究中心", "外国语学院", ""),
    ("黄河国家文化公园研究院", "文学院", ""),
    ("中国-中亚大数据研究院", "政治与国际关系学院", ""),
    ("敦煌文化产业研究院", "历史文化学院", ""),
    ("宗教文化研究中心", "哲学社会学院", "陈声柏"),
    ("一带一路研究中心", "校级科研机构", ""),
    ("铸牢中华民族共同体意识研究基地", "历史文化学院", ""),
]:
    add(name, dept, leader=leader, source=HUMANITIES_SRC, authority="校级官网", level="校级",
        note="兰州大学人文社科重点研究基地公开清单；负责人为空表示原页未列，不猜。")

# 2) School-level natural-science non-entity institutions (official 2021 PDF).
NATURAL = [
    ("皮肤病研究所", "第二临床医学院", "骆志成"),
    ("神经病学研究所", "第二临床医学院", "潘亚文"),
    ("传染病研究所", "第一临床医学院", "毛小荣"),
    ("内分泌研究所", "第一临床医学院", "汤旭磊"),
    ("城市规划设计研究院", "资源环境学院", "陈怀录"),
    ("国土资源研究所", "地质科学与矿产资源学院", "汤中立、张铭杰"),
    ("生物化工及环境技术研究所", "化学化工学院", "周林成"),
    ("心智健康工程研究中心", "信息科学与工程学院", "胡斌"),
    ("文物保护研究中心", "土木工程与力学学院", "谌文武"),
    ("清洁生产研究中心", "资源环境学院", "张有贤"),
    ("生殖健康与出生缺陷研究中心", "基础医学院", "程宁"),
    ("肿瘤防治研究中心", "公共卫生学院", "白亚娜"),
    ("医学遗传学中心", "基础医学院", "谢小冬"),
    ("西部环境与社会发展中心", "资源环境学院", "丁文广"),
    ("结核病研究中心", "基础医学院", "张颖、祝秉东"),
    ("分布式与嵌入式系统实验室", "信息科学与工程学院", "周庆国"),
    ("青藏高原生态系统管理国际中心", "生命科学学院", "龙瑞军"),
    ("冰川与沙漠研究中心", "资源环境学院", "王乃昂"),
    ("环境遥感与地质灾害研究中心", "地质科学与矿产资源学院", "孟兴民"),
    ("生物无机研究所", "化学化工学院", "汪宝堆"),
    ("兰州大学—翰宇药业多肽药物联合开放实验室", "基础医学院", "王锐"),
    ("旅游规划设计研究院", "资源环境学院", "陈兴鹏"),
    ("石油天然气资源中心", "地质科学与矿产资源学院", "张同伟"),
    ("西北土壤与地下水污染防控修复技术研究中心", "资源环境学院", "南忠仁"),
    ("城乡建设研究中心", "资源环境学院", "张子龙"),
    ("理论物理交流平台", "物理科学与技术学院", "黄亮"),
    ("旱区流域科学与水资源研究中心", "资源环境学院", "贺缠生"),
    ("营养与健康研究中心", "公共卫生学院", "王玉"),
    ("甘肃省信息安全等级保护测评中心", "信息科学与工程学院", "马志新"),
    ("生物医学纳米技术研究中心", "基础医学院", "景涛"),
    ("职业卫生检测评价研究中心", "公共卫生学院", "刘兴荣"),
    ("应用技术研究院", "应用技术研究院", "张有贤"),
    ("西域生态-文化研究中心", "生命科学学院", "杜国祯"),
    ("生物•医药知识产权研究中心", "生命科学学院", "李红玉"),
    ("两岸光电材料及器件研发与技术转移中心", "物理科学与技术学院", "王育华"),
    ("大数据研究中心", "数学与统计学院", "李周平"),
    ("菊芋研究中心", "生命科学学院", "赵长明"),
    ("国际人类基因变异组计划中国区兰州大学基因组医学实验室", "基础医学院", "谢小冬"),
    ("益生菌与生物饲料研究中心", "生命科学学院", "郭旭生"),
    ("兰州大学-甘肃天润玫瑰研究院", "生命科学学院", "李红玉"),
    ("司法鉴定所", "基础医学院", "李敏、张煦、杨爱军"),
    ("冰冻圈科学研究中心", "资源环境学院", "张廷军、王澄海、梁天刚"),
    ("西北及中亚环境考古中心", "资源环境学院", "董广辉、张东菊"),
    ("绿色陇药资源开发研究中心", "生命科学学院", "邵宝平"),
    ("网络空间安全研究院", "信息科学与工程学院", "李廉、马志新、杨裔"),
    ("引力研究中心", "物理科学与技术学院", "刘玉孝"),
    ("脑机应用军民协同创新中心", "信息科学与工程学院", "胡斌"),
    ("祁连山研究院", "资源环境学院", "勾晓华"),
    ("知识产权信息中心", "图书馆", "田中禾"),
    ("未来计算研究院", "信息科学与工程学院", "周睿"),
    ("党参研究院", "药学院", "胡芳弟"),
    ("健康管理中心", "第一临床医学院", "李汛"),
    ("祁连山特色资源开发利用研究中心", "药学院", "史彦斌"),
    ("循证护理中心", "护理学院", "韩琳"),
    ("融合蛋白联合研发中心", "生命科学学院", "李红玉"),
    ("绿色材料研发中心", "化学化工学院", "刘伟生"),
    ("信息无障碍研究中心", "信息科学与工程学院", "苏伟"),
    ("智慧城市联合研究中心", "信息科学与工程学院", "周庆国"),
    ("智能计算技术联合研究中心", "信息科学与工程学院", "张瑞生"),
    ("胶原蛋白联合研究中心", "化学化工学院", "肖建喜"),
    ("人工智能联合实验室", "信息科学与工程学院", "许存禄、苏伟"),
    ("传感器联合研究院", "物理科学与技术学院", "罗洪刚"),
    ("先进催化中心", "化学化工学院", "李灿"),
    ("地球系统模式发展研究中心", "大气科学学院", "王澄海"),
    ("石油化工农药化工联合实验室", "化学化工学院", "梁永民"),
    ("肠道菌群与精准营养研究中心", "生命科学学院", "张春江"),
    ("大数据联合研究中心", "数学与统计学院", "邓伟华、袁盛乾"),
    ("草食畜遗传改良与生态养殖研究中心", "草地农业科技学院", "李发弟"),
    ("消化系肿瘤防治与转化医学工程创新中心", "第一临床医学院", "李玉民"),
    ("湍流-颗粒研究中心", "土木工程与力学学院", "郑晓静"),
    ("脑健康工程研究院", "信息科学与工程学院", "胡斌"),
    ("超导力学研究院", "土木工程与力学学院", "周又和"),
    ("生态环境规划研究院", "资源环境学院", "王博"),
    ("上海研究院", "物理科学与技术学院", "史慧刚"),
    ("深圳交叉研究院", "管理学院", "何欣"),
    ("化工环保产业联合实验室", "资源环境学院", "朱浩"),
    ("核燃料循环与核技术应用联合实验室", "国家核产业研究院", "吴王锁"),
    ("天然药物研究中心", "药学院", "陈朋"),
    ("合成生物学创新联合研究中心", "生命科学学院", "李祥锴"),
    ("先进核能技术及产业联合研究中心", "国家核产业研究院", "邵剑雄"),
    ("隆基未来技术研究院", "材料与能源学院", "李振国、栗军帅、闻震利"),
    ("微生物技术研究院", "药学院", "陈朋、王一青"),
]
for name, dept, leader in NATURAL:
    add(name, dept, leader=leader, source=NATURAL_SRC, authority="校级官网（2021 清单）", level="校级",
        note="兰州大学非实体性科研机构 2021 年公开清单；名称和负责人按原表录入，使用前注意学校后续调整。")

# 3) Marxism College: the five institutes named in the current official
#    introduction. The page says eight; the remaining three are not named
#    publicly, so they are intentionally not invented.
for name, leader, extra_aliases in [
    ("马克思主义基本原理研究所", "", ["马原所", "马克思主义基本原理"]),
    ("马克思主义发展史研究所", "", ["马发史所", "马克思主义发展史"]),
    ("马克思主义中国化研究所", "", ["马中化所", "马克思主义中国化"]),
    ("中国近现代史基本问题研究所", "", ["近现代史所", "中国近现代史基本问题"]),
    ("思想政治教育研究所", "", ["思政所", "思想政治教育"]),
]:
    add(name, "马克思主义学院", leader=leader, source=MARX_SRC, authority="院系官网", level="院系",
        aliases=[name, *extra_aliases],
        note="学院简介称设有 8 个研究所，公开简介点名的为 5 个；其余 3 个未列名，暂不编造，待学院机构设置页公布。")

for name, leader in [
    ("全国高校思想政治理论课教师研修基地（兰州大学）", "蔡文成"),
    ("高校思想政治理论课“手拉手”集体备课中心（兰州大学—甘肃省）", "张新平"),
    ("全国高校思政课名师工作室（兰州大学）", "刘先春"),
    ("兰州大学习近平新时代中国特色社会主义思想研究中心", "蔡文成"),
    ("甘肃省廉政建设研究中心（兰州大学）", "蒙慧"),
    ("兰州大学中国特色社会主义理论体系研究中心", "安俊堂"),
    ("兰州大学新时代思想政治教育工作研究院", "王学俭"),
    ("兰州大学政治经济学基础理论研究中心", "王维平"),
    ("兰州大学廉政建设研究中心", "邢耀荣"),
    ("兰州大学中共党史党建研究院", "刘先春"),
    ("兰州大学全过程人民民主研究中心", "蔡文成"),
    ("兰州大学国防教育研究院", "李东坡"),
    ("兰州大学新时代文明实践研究中心", "张哲"),
    ("兰州大学革命文物协同创新研究中心", "崔明"),
]:
    add(name, "马克思主义学院", leader=leader, source=MARX_PLATFORM_SRC, authority="院系官网", level="院系",
        note="马克思主义学院科研平台公开页；负责人按页面所列。")

# 4) College-level institutes and centres that are explicitly named on
#    current college organisation pages.
for name, leader in [
    ("科学、技术与社会研究所（STS）", "邱德钧"),
    ("社会人类学研究所", "刘宏涛（代理）"),
    ("社会工作研究所", "钟耀林（代理）"),
]:
    add(name, "哲学社会学院", leader=leader, source=PHIL_ORG_SRC, authority="院系官网", level="院系",
        note="哲学社会学院基层组织页；负责人按页面所列。")

for name, leader in [
    ("跨文化研究中心", ""),
    ("社区健康跨学科研究中心", ""),
    ("生态文明与生态研究中心", ""),
    ("社会科学调查与数据分析中心", "周亚平（代理）"),
    ("中国西部数据中心", "唐远雄"),
]:
    add(name, "哲学社会学院", leader=leader, source=PHIL_SRC, authority="院系官网", level="院系",
        note="哲学社会学院研究平台页；负责人按页面所列。")

for name, leader in [
    ("中国现当代文学研究所", "古世仓"),
    ("中国古代文学与古典文献学研究所", "雷恩海"),
    ("汉语言文字学研究所", "敏春芳"),
    ("文艺学研究所", "张进"),
    ("比较文学与世界文学研究所", "张同胜"),
    ("戏剧影视文学研究所", "刘文江"),
    ("艺术理论与批评研究所", "王大钧"),
]:
    add(name, "文学院", leader=leader, source=LIT_SRC, authority="院系官网", level="院系",
        note="文学院研究所一览表；负责人按页面所列。")

for name in [
    "丝绸之路文化互通研究中心",
    "西部文化发展研究中心",
    "国学研究中心",
    "丝绸之路艺术研究与国际交流中心",
    "文艺评论中心",
    "语言接触研究中心",
    "纪录片研究与创作中心",
    "青少年文化研究中心",
]:
    add(name, "文学院", source=LIT_CENTER_SRC, authority="院系官网/学校教务页", level="院系",
        note="文学院公开的非实体性科研机构清单。")

for name, leader in [
    ("新闻学研究所", ""),
    ("传播学研究所", ""),
    ("公共关系与战略传播研究中心", ""),
    ("出版传媒研究中心", ""),
    ("国际传播与跨文化传播研究中心", ""),
    ("新媒体与社会治理研究中心", "李晓灵"),
]:
    add(name, "新闻与传播学院", leader=leader, source=JOUR_SRC, authority="院系官网", level="院系",
        note="新闻与传播学院机构设置页；负责人按页面所列。")

for name in [
    "中国古代史研究所", "史学理论与史学史研究所", "专门史研究所", "近代中国研究所",
    "古籍研究所", "世界历史与国际关系研究所", "考古学及博物馆学研究所", "民族学研究所",
    "马克思主义民族理论与政策研究所", "中国少数民族史研究所", "藏学研究所", "民族社会学研究所",
]:
    add(name, "历史文化学院", source=HIST_SRC, authority="公开资料（待官网核对）", level="院系",
        note="学院官网未公开完整研究所名单，按公开资料整理；使用前请以学院官网核对。")

for name in [
    "宪法与行政法研究所", "刑事法学研究所", "民商法学研究所", "经济法学研究所",
    "环境与资源法学研究所", "国际法学研究所", "法理学研究所",
]:
    add(name, "法学院", source=LAW_SRC, authority="学校教学科研页（历史汇总）", level="院系",
        note="学校教学科研页历史汇总；学院现行机构设置如调整，以学院官网为准。")

for name in ["英语语言文学研究所", "外国语言学及应用语言学研究所", "俄语语言文学研究所", "翻译研究所"]:
    add(name, "外国语学院", source=FOREIGN_SRC, authority="学校教学科研页（历史汇总）", level="院系",
        note="学校教学科研页历史汇总；学院现行机构设置如调整，以学院官网为准。")

for name in ["美术与设计研究所", "音乐研究所"]:
    add(name, "艺术学院", source=ART_SRC, authority="学校教学科研页（历史汇总）", level="院系",
        note="学校教学科研页历史汇总；学院现行机构设置如调整，以学院官网为准。")

for name in [
    "气象学研究所", "大气物理与大气环境研究所", "环境变化研究所",
    "大气遥感与辐射研究所", "环境质量评价研究中心", "气象环境与人体健康研究中心",
]:
    add(name, "大气科学学院", source=ATMOS_SRC, authority="院系官网", level="院系",
        note="大气科学学院机构设置页。")

for name in [
    "固体力学研究所", "工程力学研究所", "地质工程研究所",
    "岩土工程研究所", "结构工程研究所", "防灾减灾工程研究所",
]:
    add(name, "土木工程与力学学院", source=CIVIL_SRC, authority="院系官网", level="院系",
        note="土木工程与力学学院机构设置页。")

for name in [
    "电路与系统研究所", "信息与通信工程研究所", "光电子与电磁信息研究所",
    "计算机软件与理论研究所", "计算机应用技术研究所", "计算机系统结构研究所",
    "军民融合研究中心", "网络空间安全研究中心", "类脑计算研究中心", "数据科学研究中心",
]:
    add(name, "信息科学与工程学院", source=INFO_SRC, authority="院系官网", level="院系",
        note="信息科学与工程学院机构设置页；学院 2024 年调整后仍公开的科研机构。")

for name in ["原子核物理研究所", "放射化学与核环境研究所", "中子物理与技术研究所", "核能与核技术研究所", "辐射物理与核材料研究所"]:
    add(name, "核科学与技术学院", source=NUCLEAR_SRC, authority="院系官网", level="院系",
        note="核科学与技术学院基层组织页。")

for name in [
    "病毒学研究所", "人兽共患病研究所", "新药研究所", "动物健康与生态研究所",
    "动物免疫学研究所", "生物制品新材料研究所", "比较医学研究所",
]:
    add(name, "动物医学与生物安全学院", source=VET_SRC, authority="院系官网", level="院系",
        note="动物医学与生物安全学院机构设置页。")

for name, leader in [
    ("基础数学研究所", "罗彦锋"),
    ("应用数学研究所", "王智诚"),
    ("计算数学研究所", "邓伟华"),
    ("运筹与控制研究所", "张和平"),
    ("概率统计研究所", "李周平、赵学靖"),
]:
    add(name, "数学与统计学院", leader=leader, source=MATH_SRC, authority="院系官网", level="院系",
        note="数学与统计学院研究所页；负责人按页面所列。")

for name in [
    "现代经济研究所", "区域经济与产业发展研究所", "低碳经济与绿色发展研究所", "数字经济与金融财税研究所",
    "绿色金融发展研究院", "一带一路能源生态经济与安全中心", "现代化产业体系研究中心",
    "数量经济研究所", "西北开发综合研究所", "新结构经济学研究中心", "西北人口研究所",
    "区域金融研究院", "社区与生物多样性保护研究中心", "丝绸之路国际知识产权研究院",
]:
    add(name, "经济学院", source=ECON_SRC, authority="院系官网", level="院系",
        note="经济学院学院简介公开的基层研究所与非实体机构；与校级清单重复的已去重。")

for name in [
    "材料科学与工程研究所", "功能与环境材料研究所", "纳米科学与技术研究所",
    "材料结构与成份分析研究所", "电子材料与器件研究所", "软物质与先进功能材料研究所",
    "清洁能源材料与器件研究所",
]:
    add(name, "材料与能源学院", source=MAT_SRC, authority="院系官网", level="院系",
        note="材料与能源学院人才招聘公告公开的 7 个研究所。")

for name in [
    "流行病与卫生统计学研究所", "劳动卫生与环境卫生学研究所", "卫生毒理学研究所",
    "营养与食品卫生学研究所", "儿少卫生与妇幼保健学研究所", "社会医学与卫生事业管理研究所",
    "世界卫生组织指南实施与知识转化合作中心", "兰州大学循证社会科学研究中心",
    "“一带一路”气象与健康联合研究中心",
]:
    add(name, "公共卫生学院", source=SPH_SRC, authority="院系官网（历史页）", level="院系",
        note="公共卫生学院历史简介列出的 6 个研究所与 3 个跨学科研究机构；部分研究所后更名为学系，名称按原页保留。")

for name in [
    "口腔慢性疾病防治研究所", "口腔民族医药研究所", "口腔功能重建研究所",
    "3D 生物打印与组织重建研究所", "口腔交叉学科研究所",
]:
    add(name, "口腔医学院", source=STOM_SRC, authority="公开资料（待官网核对）", level="院系",
        note="口腔医学院官网只公开重点实验室与临床研究中心，5 个研究所名称来自公开资料；使用前请以学院官网核对。")

for name in [
    "甘肃省牙颌面重建与生物智能制造重点实验室", "甘肃省口腔疾病临床医学研究中心",
]:
    add(name, "口腔医学院", source=STOM_SRC, authority="院系官网", level="院系",
        note="口腔医学院学院简介公开的省级科研平台。")

for name in ["循证护理研究中心", "甘肃省智能康复与护理行业技术中心"]:
    add(name, "护理学院", source=NURSING_SRC, authority="院系官网/公开报告", level="院系",
        note="护理学院公开的科研平台；循证护理研究中心同时见于学院简介。")

for name in [
    "临床医学研究中心", "精准医学中心", "精准医学实验室", "出生缺陷精准防控医学平台",
    "先进粒子与核医学技术创新中心", "甘肃省肝脏修复与再生医学转化工程研究中心",
    "甘肃省临床高通量测序行业技术中心",
]:
    add(name, "第一临床医学院", source=FIRST_HOSP_SRC, authority="医院官网", level="医院",
        note="兰大一院科研平台页；附属医院大量临床科室平台未逐科展开，只收校级机构与院级科研平台。")

for name in [
    "原子核物理研究所", "放射化学与核环境研究所", "中子物理与技术研究所", "核能与核技术研究所",
    "辐射物理与核材料研究所", "核科学与技术实验教学中心", "中子应用技术教育部工程研究中心",
    "核环境安全教育部工程研究中心", "稀有同位素前沿科学中心",
]:
    add(name, "核科学与技术学院", source=NUCLEAR_SRC, authority="院系官网", level="院系",
        note="核科学与技术学院科研平台与基层组织页；教学中心与研究中心一并保留，便于按平台检索。")

for name in [
    "药物化学研究所", "天然药物化学生物学研究所", "药物分析研究所",
    "药剂学研究所", "药理学研究所", "中草药研究所",
]:
    add(name, "药学院", source=PHARM_SRC, authority="院系官网", level="院系",
        note="药学院官网“研究机构”栏；中草药研究所另见学校教学科研历史页，作为补充保留。")

for name in [
    "人体解剖学与组织胚胎学研究所（人体解剖学）",
    "人体解剖学与组织胚胎学研究所（组织胚胎学）",
    "免疫学研究所",
    "病理学研究所",
    "病理生理学研究所",
    "病原生物学研究所",
    "遗传学研究所",
    "中西医结合研究所",
    "医学生物化学与分子生物学研究所",
    "医学生理学与心理学研究所（医学生理）",
    "医学生理学与心理学研究所（医学心理）",
    "循证医学研究所",
    "药理学研究所",
    "外科手术学研究所",
    "新药设计与合成研究所",
    "神经科学研究所",
]:
    add(name, "基础医学院", source=BASICMED_SRC, authority="院系官网", level="院系",
        note="基础医学院科研机构页；学院同时保留教研室与科学研究中心两套名称。")

for name in ["西北民族体育文化研究所"]:
    add(name, "体育学院", source=SPORT_SRC, authority="学校教学科研页（历史汇总）", level="院系",
        note="学校教学科研页历史汇总；学院现行机构设置如调整，以学院官网为准。")

# 5) Political/IR named area centres not already in the school-level list.
for name in [
    "国家安全研究中心", "上海合作组织研究中心", "土库曼斯坦研究中心",
    "中亚地缘政治研究中心", "新疆稳定与发展研究中心",
]:
    add(name, "政治与国际关系学院", source=OLD_TEACH_SRC, authority="学校教学科研页（历史汇总）", level="院系",
        note="学校教学科研页历史汇总；学院现行机构设置如调整，以学院官网为准。")

# Sort new entries by department order then name; keep the existing 22 first.
dept_order = {name: i for i, name in enumerate(DEPTS)}
added.sort(key=lambda x: (dept_order.get(x["department"], 99), x["name"]))
final = seed + added
SEED.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

from collections import Counter
print("existing", len(seed), "added", len(added), "total", len(final))
print("departments", len({x["department"] for x in final}))
print("by type", Counter(x["type_label"] for x in final))
print("sample Marxism:")
for x in final:
    if x["department"] == "马克思主义学院":
        print(" ", x["name"], "|", x["leader"] or "-")
