"""学科判定与领域档案。

同一个方向词在不同学科里含义完全不同（"neural network" 在 PMC 里多是神经科学，
在材料学里是器件阵列）。这里先用词表判定方向属于哪一类，再据此选择
检索范式、卡片字段与干扰词表，避免把农业/临床的框架硬套到材料学上。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

BASE_LABELS = {
    "design": "设计",
    "system": "系统",
    "factors": "处理因素",
    "controls": "对照",
    "sample_size": "样本量",
    "omics": "组学/检测",
    "outcomes": "结局",
    "conclusion": "结论",
    "limitations": "局限",
}

AGRI_FIELDS = {
    "design": "实验设计（盆栽/温室/田间/体外/纯干分析）",
    "system": "研究系统与材料（物种、品种、根际/叶片等）",
    "factors": "处理因素与剂量",
    "controls": "对照组设置",
    "sample_size": "样本量/重复数（n=...），没有就写 待核",
    "omics": "组学与检测层（16S/ITS/代谢组/转录组/生理指标等）",
    "outcomes": "主要结局指标",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限或设计上的明显短板",
}

MATERIALS_FIELDS = {
    "design": "研究设计（制备—表征—测试的流程；是否做到器件/阵列级验证）",
    "system": "体系与结构（材料组成、堆叠顺序、器件结构、特征尺寸）",
    "factors": "工艺与驱动参数（温度、气氛、电压/电流、脉冲宽度、退火、掺杂等）",
    "controls": "对照与基线（基线器件、商用材料、传统方案、无处理组）",
    "sample_size": "样本量（器件数、批次数、测量点数、阵列规模）",
    "omics": "表征与检测手段（XRD/TEM/SEM/EELS、I–V、EIS、AFM、光谱、电学测试等）",
    "outcomes": "性能指标（开关比、保持性、耐久、良率、准确率、能耗等）",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限或设计上的明显短板",
}

BIOMED_FIELDS = {
    "design": "研究设计（RCT/队列/横断面/动物模型/细胞实验/纯干分析）",
    "system": "研究对象（人群、动物模型、细胞系、组织）",
    "factors": "干预或暴露因素与剂量/时长",
    "controls": "对照组设置（安慰剂/空白/阳性对照）",
    "sample_size": "样本量（n=...，分组数），没有就写 待核",
    "omics": "检测层（生化指标、影像、测序、组学等）",
    "outcomes": "主要与次要结局指标",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限或设计上的明显短板",
}

GENERAL_FIELDS = {
    "design": "研究设计与方法路线（实验/仿真/观测/综述）",
    "system": "研究对象与体系",
    "factors": "自变量、处理或条件设置",
    "controls": "对照、基线或参照标准",
    "sample_size": "样本量/重复数/测量点数，没有就写 待核",
    "omics": "检测、表征或评估手段",
    "outcomes": "主要结果指标",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限或明显短板",
}

ENGINEERING_FIELDS = {
    "design": "研究设计与方案（建模/仿真/试验/原型验证）",
    "system": "研究对象与系统边界（结构、部件、流程或网络）",
    "factors": "设计变量、工况或控制参数",
    "controls": "基线方案、对照工况或行业标准",
    "sample_size": "样本量/试验次数/仿真工况数，没有就写 待核",
    "omics": "测试、表征或评价手段（台架、仿真、监测、指标计算）",
    "outcomes": "性能指标（效率、精度、寿命、能耗、可靠度等）",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限或工程适用边界",
}

SOCIAL_FIELDS = {
    "design": "研究设计（理论推演/案例/问卷/实验/二手数据）",
    "system": "研究对象与分析单元（人群、组织、市场、政策文本）",
    "factors": "核心变量、机制或政策工具",
    "controls": "对照、比较组或反事实设定",
    "sample_size": "样本量/案例数/数据年份跨度，没有就写 待核",
    "omics": "数据来源与分析方法（统计、计量、质性编码、文本分析）",
    "outcomes": "主要结果或效应量",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限（外推性、内生性、样本偏差）",
}

HUMANITIES_FIELDS = {
    "design": "研究路径（文本细读/史料考证/比较研究/阐释）",
    "system": "研究对象与材料（文本、档案、作品、语料）",
    "factors": "核心问题、概念或历史语境",
    "controls": "参照文本、版本或对照史料",
    "sample_size": "材料范围与数量（篇/卷/件/年代跨度）",
    "omics": "研究方法与证据类型（版本比对、引文、档案编号）",
    "outcomes": "主要论点与证据链",
    "conclusion": "作者的核心结论（一句话）",
    "limitations": "作者承认的局限或解释边界",
}


MATERIALS_LABELS = {**BASE_LABELS, "system": "体系与结构", "factors": "工艺参数",
                    "controls": "对照基线", "omics": "表征检测", "outcomes": "性能指标"}
BIOMED_LABELS = {**BASE_LABELS, "system": "研究对象", "omics": "检测层", "outcomes": "结局指标"}
ENGINEERING_LABELS = {**BASE_LABELS, "system": "系统与边界", "factors": "设计变量/工况",
                      "omics": "测试与评价", "outcomes": "性能指标"}
SOCIAL_LABELS = {**BASE_LABELS, "system": "研究对象/分析单元", "factors": "核心变量",
                 "omics": "数据与方法", "outcomes": "结果/效应"}
HUMANITIES_LABELS = {**BASE_LABELS, "system": "材料与文本", "factors": "核心问题/语境",
                     "omics": "证据类型", "outcomes": "论点与证据链"}


@dataclass(frozen=True)
class Domain:
    key: str
    label: str
    framework: str
    framework_hint: str
    lexicon: tuple[str, ...]
    card_fields: dict[str, str] = field(default_factory=dict)
    card_labels: dict[str, str] = field(default_factory=dict)
    analyst_role: str = ""
    anti: tuple[str, ...] = ()
    query_exclusion: str = ""
    min_score: float = 1.5
    gate: bool = True


MATERIALS = Domain(
    key="materials",
    label="材料与器件",
    framework="PSPP（Processing–Structure–Property–Performance）",
    framework_hint=("把方向拆成四格：Processing 制备工艺、Structure 组成与结构、"
                    "Property 性能指标、Performance 器件/应用级表现；填不出来的留空。"),
    lexicon=(
        "memristor", "memristive", "memristance", "rram", "reram",
        "resistive switching", "resistance switching", "perovskite",
        "semiconductor", "thin film",
        "thin-film", "nanomaterial", "nanoparticle", "catalyst", "battery",
        "electrode", "electrolyte", "alloy", "ceramic", "polymer", "graphene",
        "carbon nanotube", "2d material", "ferroelectric", "spintronic",
        "photovoltaic", "solar cell", "transistor", "wafer", "mems",
        "supercapacitor", "coating", "corrosion", "composite", "superconduct",
        "neuromorphic", "in-memory computing", "computing-in-memory",
        "in-memory", "in-sensor", "spiking neural", "synapse",
        "忆阻器", "阻变", "钙钛矿", "半导体", "薄膜", "纳米", "催化", "电池",
        "电极", "电解质", "合金", "陶瓷", "高分子", "石墨烯", "碳纳米管",
        "二维材料", "铁电", "自旋", "光伏", "太阳能电池", "晶体管", "晶圆",
        "超级电容", "涂层", "腐蚀", "复合材料", "超导", "类脑", "存算一体",
    ),
    anti=(
        "plant", "crop", "rhizosphere", "endophyte", "mycorrhiza", "cultivar",
        "greenhouse", "field trial", "seedling", "banana", "nematode",
        "fusarium", "mice", "mouse", "rat", "patient", "clinical", "tumor",
        "serum", "patients", "protein", "in vivo", "in vitro", "biological",
        "mammalian", "cell culture", "organoid",
        "盆栽", "田间", "根际", "内生真菌", "品种", "香蕉", "线虫", "小鼠",
    ),
    card_fields=MATERIALS_FIELDS,
    card_labels=MATERIALS_LABELS,
    analyst_role=("你是材料、器件与微纳电子方向的课题分析师。按"
                  "「制备—结构—性能—应用」的逻辑归纳，不要套用农业或临床实验的字段语义。"),
    query_exclusion=('"plant" OR "crop" OR "rhizosphere" OR "soil" OR "mouse" OR "mice" '
                     'OR "rat" OR "patient" OR "clinical" OR "greenhouse"'),
)

AGRI = Domain(
    key="agri",
    label="植物—微生物/农学",
    framework="PICO（Population–Intervention–Comparison–Outcome）",
    framework_hint=("把方向拆成 P 研究对象（物种/品种）、I 干预或处理、C 对照、"
                    "O 结局；没有对照的留空，这是事实，不是缺陷。"),
    lexicon=(
        "plant", "crop", "rhizosphere", "soil", "endophyte", "endophytic",
        "mycorrhiza", "cultivar", "greenhouse", "field trial", "seedling",
        "pathogen", "fungus", "fungal", "root", "forage", "pasture", "legume",
        "alfalfa", "nematode", "fusarium", "disease resistance", "inoculat",
        "植物", "作物", "牧草", "根际", "土壤", "内生真菌", "内生菌", "菌根",
        "品种", "盆栽", "田间", "温室", "种子", "根系", "病原", "真菌", "菌株",
        "接种", "连作", "抗病", "锈病", "枯萎病", "草地", "苜蓿", "棘豆",
    ),
    anti=(
        "memristor", "perovskite", "semiconductor", "wafer", "transistor",
        "battery", "electrode", "alloy", "ceramic", "catalyst", "spintronic",
        "忆阻器", "钙钛矿", "半导体", "晶圆", "晶体管", "电极", "合金",
    ),
    card_fields=AGRI_FIELDS,
    card_labels=BASE_LABELS,
    analyst_role="你是植物—微生物互作、根际微生物组与代谢组方向的课题分析师。",
    query_exclusion=('"memristor" OR "perovskite" OR "semiconductor" OR "wafer" '
                     'OR "transistor" OR "battery" OR "alloy"'),
)

BIOMED = Domain(
    key="biomed",
    label="生物医学",
    framework="PICO（Population–Intervention–Comparison–Outcome）",
    framework_hint=("把方向拆成 P 人群/模型、I 干预或暴露、C 对照、O 结局；"
                    "没有对照的留空。"),
    lexicon=(
        "patient", "patients", "clinical", "cohort", "randomized", "trial",
        "cell line", "in vitro", "in vivo", "tumor", "cancer", "immune",
        "virus", "protein", "gene expression", "drug", "inflammation",
        "disease", "serum", "biomarker", "neuron", "brain", "mice", "mouse",
        "患者", "病人", "临床", "队列", "细胞", "肿瘤", "免疫", "病毒", "蛋白",
        "基因", "药物", "炎症", "疾病", "血液", "标志物", "小鼠", "大鼠",
    ),
    anti=(
        "memristor", "perovskite", "semiconductor", "wafer", "transistor",
        "battery", "electrode", "alloy", "ceramic", "catalyst",
        "rhizosphere", "endophyte", "cultivar", "greenhouse",
        "忆阻器", "钙钛矿", "半导体", "根际", "内生真菌", "品种",
    ),
    card_fields=BIOMED_FIELDS,
    card_labels=BIOMED_LABELS,
    analyst_role="你是临床与生物医学方向的课题分析师，按循证医学的证据分级习惯归纳。",
    query_exclusion='"memristor" OR "perovskite" OR "semiconductor" OR "wafer" OR "rhizosphere"',
)

ENGINEERING = Domain(
    key="engineering",
    label="工程与技术",
    framework="RDVM（Requirement–Design–Validation–Metric）",
    framework_hint=("把方向拆成四格：R 需求/工况、D 设计与方案、V 验证方式（仿真/台架/现场）、"
                    "M 性能指标；填不出来的留空。"),
    lexicon=(
        "engineering", "design", "simulation", "model", "experiment", "prototype",
        "optimization", "control", "sensor", "system", "performance", "efficiency",
        "reliability", "testing", "fabrication", "algorithm", "network", "energy",
        "thermal", "structural", "fluid", "robot", "manufacturing", "process",
        "工程", "设计", "仿真", "建模", "试验", "优化", "控制", "传感", "系统",
        "性能", "效率", "可靠", "测试", "制造", "工艺", "结构", "流体", "热能",
    ),
    card_fields=ENGINEERING_FIELDS,
    card_labels=ENGINEERING_LABELS,
    analyst_role=("你是工程与技术方向的课题分析师。按「需求—设计—验证—指标」归纳，"
                  "不要套用农学或临床的字段语义。"),
)

SOCIAL = Domain(
    key="social",
    label="社会科学",
    framework="PMEP（Phenomenon–Mechanism–Evidence–Policy）",
    framework_hint=("把方向拆成四格：P 现象/问题、M 机制或解释、E 数据与识别策略、"
                    "P 政策/应用含义；填不出来的留空。"),
    lexicon=(),
    card_fields=SOCIAL_FIELDS,
    card_labels=SOCIAL_LABELS,
    analyst_role="你是社会科学方向的课题分析师，按现象—机制—证据—政策归纳。",
    min_score=0.0,
    gate=False,
)

HUMANITIES = Domain(
    key="humanities",
    label="人文与艺术",
    framework="TCIA（Text–Context–Interpretation–Archive）",
    framework_hint=("把方向拆成四格：T 文本/作品、C 语境、I 解释框架、A 史料/档案；"
                    "填不出来的留空。"),
    lexicon=(),
    card_fields=HUMANITIES_FIELDS,
    card_labels=HUMANITIES_LABELS,
    analyst_role="你是人文与艺术方向的课题分析师，按文本—语境—阐释—史料归纳。",
    min_score=0.0,
    gate=False,
)

GENERAL = Domain(
    key="general",
    label="通用（未识别学科）",
    framework="四要素（对象—方法—指标—条件）",
    framework_hint=("把方向拆成四格：对象（研究什么）、方法（怎么做）、"
                    "指标（看什么）、条件（什么限制）；填不出来的留空。"),
    lexicon=(),
    card_fields=GENERAL_FIELDS,
    card_labels=BASE_LABELS,
    analyst_role="你是跨学科的文献信息分析师，按「对象—方法—指标—条件」归纳，不预设学科。",
    min_score=0.0,
    gate=False,
)

DOMAINS = {"materials": MATERIALS, "agri": AGRI, "biomed": BIOMED,
           "engineering": ENGINEERING, "social": SOCIAL, "humanities": HUMANITIES,
           "general": GENERAL}


def contains(text: str, term: str) -> bool:
    """整词匹配，避免 rat 命中 integrated、plant 命中 implant 这类假阳性。

    中文词没有词边界，退化为子串匹配；英文单词允许复数后缀。
    """
    low = (text or "").lower()
    word = (term or "").lower().strip()
    if not word:
        return False
    if re.search(r"[^\x00-\x7f]", word) or " " in word or "-" in word:
        return word in low
    return re.search(rf"\b{re.escape(word)}(?:s|es)?\b", low) is not None


def hits(text: str, vocab: tuple[str, ...]) -> int:
    return sum(1 for word in vocab if contains(text, word))


def _hits(text: str, vocab: tuple[str, ...]) -> int:
    return hits(text, vocab)


def classify(direction: str) -> Domain:
    """按词表投票判定方向所属学科；判不出来就退回通用档案。"""
    text = (direction or "").lower()
    scores = {
        "materials": _hits(text, MATERIALS.lexicon),
        "agri": _hits(text, AGRI.lexicon),
        "biomed": _hits(text, BIOMED.lexicon),
    }
    best = max(scores.values())
    if best <= 0:
        return GENERAL
    winners = [k for k, v in scores.items() if v == best]
    if len(winners) > 1:
        return GENERAL
    return DOMAINS[winners[0]]


def by_key(key: str) -> Domain:
    return DOMAINS.get((key or "").lower(), GENERAL)
