"""OECD 学科分类：Frascati Manual 2007 的 Fields of Science（FOS 2007）。

口径：6 个一级领域、42 个二级子领域，代码沿用 Frascati 的 1.1–6.5。
用途有三处，都不做硬过滤（WOS / Scopus / PubMed 都没有这个字段，硬筛会把正常文献筛没）：
1. 界面里选口径，用来限定检索词的专业义（每个子类带一组英文主题词）；
2. 规划检索式时把这组主题词交给模型，避免跨学科同形词跑偏；
3. 检索完成后按标题给结果做一次学科分布统计，看这批文献是否真落在所选口径里。

分类依据：OECD (2007), Frascati Manual 2007, §2.2 Fields of Science；
以及 OECD (2015) Frascati Manual 2015 对 FOS 的沿用（6 大类 42 子类未变）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAJOR: dict[str, str] = {
    "1": "1 自然科学",
    "2": "2 工程与技术",
    "3": "3 医学与健康科学",
    "4": "4 农业科学",
    "5": "5 社会科学",
    "6": "6 人文与艺术",
}

MAJOR_EN: dict[str, str] = {
    "1": "Natural sciences",
    "2": "Engineering and technology",
    "3": "Medical and health sciences",
    "4": "Agricultural sciences",
    "5": "Social sciences",
    "6": "Humanities and the arts",
}

# 42 个子类全部映射到内部归纳档案；映射依据是学科对象与方法，不是项目经历。
HINTS: dict[str, str] = {
    "1.1": "general", "1.2": "engineering", "1.3": "materials", "1.4": "materials",
    "1.5": "general", "1.6": "agri", "1.7": "general",
    "2.1": "engineering", "2.2": "materials", "2.3": "engineering", "2.4": "materials",
    "2.5": "materials", "2.6": "biomed", "2.7": "engineering", "2.8": "engineering",
    "2.9": "engineering", "2.10": "materials", "2.11": "engineering",
    "3.1": "biomed", "3.2": "biomed", "3.3": "biomed", "3.4": "biomed", "3.5": "biomed",
    "4.1": "agri", "4.2": "agri", "4.3": "agri", "4.4": "agri", "4.5": "agri",
    "5.1": "social", "5.2": "social", "5.3": "social", "5.4": "social", "5.5": "social",
    "5.6": "social", "5.7": "social", "5.8": "social", "5.9": "social",
    "6.1": "humanities", "6.2": "humanities", "6.3": "humanities",
    "6.4": "humanities", "6.5": "humanities",
}


@dataclass(frozen=True)
class Field:
    code: str
    label: str
    label_en: str
    keywords: tuple[str, ...] = ()
    domain_hint: str = "general"

    @property
    def major(self) -> str:
        return self.code.split(".")[0]


FIELDS: tuple[Field, ...] = (
    # 1 Natural sciences
    Field("1.1", "数学", "Mathematics",
          ("mathematics", "algebra", "geometry", "topology", "probability",
           "statistics", "numerical analysis", "optimization", "stochastic")),
    Field("1.2", "计算机与信息科学", "Computer and information sciences",
          ("computer science", "informatics", "algorithm", "machine learning",
           "artificial intelligence", "software", "database", "computer network",
           "information system", "computational complexity")),
    Field("1.3", "物理科学", "Physical sciences",
          ("physics", "condensed matter", "quantum", "optics", "thermodynamics",
           "electromagnetism", "plasma", "acoustics", "mechanics", "spectroscopy"),
          "materials"),
    Field("1.4", "化学科学", "Chemical sciences",
          ("chemistry", "organic chemistry", "inorganic chemistry", "polymer",
           "catalysis", "electrochemistry", "photochemistry", "analytical chemistry",
           "chemical synthesis", "molecular"),
          "materials"),
    Field("1.5", "地球与相关环境科学", "Earth and related environmental sciences",
          ("geology", "geophysics", "mineralogy", "meteorology", "climatology",
           "oceanography", "hydrology", "atmospheric", "soil science", "geochemistry")),
    Field("1.6", "生物科学", "Biological sciences",
          ("biology", "botany", "zoology", "microbiology", "ecology", "genetics",
           "molecular biology", "cell biology", "evolution", "taxonomy", "mycology"),
          "agri"),
    Field("1.7", "其他自然科学", "Other natural sciences",
          ("natural science", "interdisciplinary natural", "astronomy",
           "space science", "biophysics")),
    # 2 Engineering and technology
    Field("2.1", "土木工程", "Civil engineering",
          ("civil engineering", "structural engineering", "construction",
           "geotechnical", "bridge", "concrete", "urban infrastructure")),
    Field("2.2", "电气、电子与信息工程", "Electrical, electronic and information engineering",
          ("electronics", "electrical engineering", "circuit", "semiconductor device",
           "signal processing", "telecommunication", "power system", "embedded system",
           "sensor", "device"),
          "materials"),
    Field("2.3", "机械工程", "Mechanical engineering",
          ("mechanical engineering", "machine design", "robotics", "manufacturing",
           "tribology", "fluid mechanics", "heat transfer", "mechatronics")),
    Field("2.4", "化学工程", "Chemical engineering",
          ("chemical engineering", "process engineering", "reactor", "separation",
           "distillation", "polymer processing", "industrial synthesis", "scale-up"),
          "materials"),
    Field("2.5", "材料工程", "Materials engineering",
          ("materials science", "materials engineering", "thin film", "coating",
           "alloy", "ceramic", "composite", "nanomaterial", "crystal growth",
           "microstructure", "metallurgy", "memristor"),
          "materials"),
    Field("2.6", "医学工程", "Medical engineering",
          ("biomedical engineering", "medical device", "biomaterial", "prosthesis",
           "medical imaging", "tissue engineering", "biosensor")),
    Field("2.7", "环境工程", "Environmental engineering",
          ("environmental engineering", "wastewater", "pollution control",
           "remediation", "air quality", "solid waste", "water treatment")),
    Field("2.8", "环境生物技术", "Environmental biotechnology",
          ("environmental biotechnology", "bioremediation", "composting",
           "bioenergy", "microbial degradation", "waste biotreatment")),
    Field("2.9", "工业生物技术", "Industrial biotechnology",
          ("industrial biotechnology", "fermentation", "bioprocess", "enzyme",
           "metabolic engineering", "bioreactor", "strain engineering")),
    Field("2.10", "纳米技术", "Nano-technology",
          ("nanotechnology", "nanomaterial", "nanoparticle", "nanotube",
           "nanofabrication", "quantum dot", "nanoelectronics", "nanomedicine"),
          "materials"),
    Field("2.11", "其他工程与技术", "Other engineering and technologies",
          ("engineering", "technology", "systems engineering", "reliability",
           "standardization", "instrumentation")),
    # 3 Medical and health sciences
    Field("3.1", "基础医学", "Basic medicine",
          ("anatomy", "physiology", "pathology", "pharmacology", "immunology",
           "medical microbiology", "embryology", "histology"),
          "biomed"),
    Field("3.2", "临床医学", "Clinical medicine",
          ("clinical", "patient", "cohort", "randomized trial", "diagnosis",
           "therapy", "surgery", "cardiology", "oncology", "pediatrics"),
          "biomed"),
    Field("3.3", "健康科学", "Health sciences",
          ("public health", "epidemiology", "health policy", "nursing",
           "nutrition", "health care", "occupational health"),
          "biomed"),
    Field("3.4", "医学生物技术", "Medical biotechnology",
          ("medical biotechnology", "gene therapy", "vaccine", "biomarker",
           "drug delivery", "monoclonal antibody", "regenerative medicine"),
          "biomed"),
    Field("3.5", "其他医学科学", "Other medical sciences",
          ("forensic medicine", "sports medicine", "tropical medicine",
           "medical ethics", "biomedical technology"),
          "biomed"),
    # 4 Agricultural sciences
    Field("4.1", "农业、林业与渔业", "Agriculture, forestry and fisheries",
          ("agriculture", "agronomy", "crop", "soil", "forestry", "fishery",
           "irrigation", "horticulture", "plant breeding", "rhizosphere"),
          "agri"),
    Field("4.2", "畜牧与乳品科学", "Animal and dairy science",
          ("animal science", "livestock", "dairy", "poultry", "animal nutrition",
           "animal breeding", "feed", "ruminant"),
          "agri"),
    Field("4.3", "兽医科学", "Veterinary science",
          ("veterinary", "animal disease", "zoonosis", "veterinary pathology",
           "animal welfare", "vaccination of animals"),
          "agri"),
    Field("4.4", "农业生物技术", "Agricultural biotechnology",
          ("agricultural biotechnology", "transgenic plant", "plant tissue culture",
           "biofertilizer", "endophyte", "biological control", "marker-assisted selection"),
          "agri"),
    Field("4.5", "其他农业科学", "Other agricultural sciences",
          ("agricultural science", "farm management", "postharvest",
           "agricultural engineering", "rural development"),
          "agri"),
    # 5 Social sciences
    Field("5.1", "心理学", "Psychology",
          ("psychology", "cognitive", "behavioral", "psychometrics",
           "developmental psychology", "social psychology")),
    Field("5.2", "经济学与商业", "Economics and business",
          ("economics", "business", "management", "finance", "accounting",
           "marketing", "industrial organization", "econometrics")),
    Field("5.3", "教育科学", "Educational sciences",
          ("education", "pedagogy", "curriculum", "didactics",
           "educational assessment", "teacher training")),
    Field("5.4", "社会学", "Sociology",
          ("sociology", "social structure", "demography", "anthropology",
           "social inequality", "migration")),
    Field("5.5", "法学", "Law",
          ("law", "legal", "jurisprudence", "regulation", "legislation",
           "intellectual property", "criminal justice")),
    Field("5.6", "政治学", "Political science",
          ("political science", "governance", "public administration",
           "international relations", "policy analysis")),
    Field("5.7", "社会与经济地理", "Social and economic geography",
          ("human geography", "economic geography", "regional planning",
           "urban studies", "spatial analysis")),
    Field("5.8", "媒体与传播", "Media and communication",
          ("media", "communication", "journalism", "digital media",
           "communication studies")),
    Field("5.9", "其他社会科学", "Other social sciences",
          ("social science", "interdisciplinary social", "gender studies",
           "area studies")),
    # 6 Humanities and the arts
    Field("6.1", "历史与考古", "History and archaeology",
          ("history", "archaeology", "heritage", "historical archive")),
    Field("6.2", "语言与文学", "Languages and literature",
          ("linguistics", "literature", "language studies", "philology",
           "translation studies")),
    Field("6.3", "哲学、伦理与宗教", "Philosophy, ethics and religion",
          ("philosophy", "ethics", "religion", "theology", "logic")),
    Field("6.4", "艺术", "Art (arts, history of arts, performing arts, music)",
          ("art history", "performing arts", "music", "visual arts",
           "design studies", "theatre")),
    Field("6.5", "其他人文与艺术", "Other humanities",
          ("humanities", "interdisciplinary humanities", "cultural studies")),
)


def get(code: str) -> Field | None:
    for field in FIELDS:
        if field.code == code:
            return field
    return None


def label(code: str) -> str:
    field = get(code)
    return f"{field.code} {field.label}" if field else ""


def label_en(code: str) -> str:
    field = get(code)
    return f"{field.code} {field.label_en}" if field else ""


def label_full(code: str) -> str:
    """带一级领域的完整写法，写进报告用。"""
    field = get(code)
    if not field:
        return ""
    major = MAJOR.get(field.major, "")
    return f"{major} / {field.code} {field.label}（{field.label_en}）"


def domain_hint(code: str) -> str:
    """子类 → 内部归纳档案。覆盖全部 42 个子类，不按“以前做过的题”临时加。

    materials / agri / biomed / engineering / social / humanities / general
    只决定卡片字段语义与闸门口径，不改变 OECD 分类本身。
    """
    return HINTS.get(code, "general")


def search_terms(code: str) -> list[str]:
    """该子类的英文主题词，供检索式规划时限定专业义。"""
    field = get(code)
    return list(field.keywords) if field else []


def as_json() -> list[dict]:
    """给前端两级下拉用：大类 → 子类。"""
    return [
        {"code": code, "label": text, "label_en": MAJOR_EN.get(code, ""),
         "children": [{"code": f.code, "label": f"{f.code} {f.label}",
                       "label_en": f.label_en}
                      for f in FIELDS if f.major == code]}
        for code, text in MAJOR.items()
    ]


def _hit(text: str, keyword: str) -> bool:
    word = keyword.lower()
    if " " in word or "-" in word:
        return word in text
    return re.search(rf"\b{re.escape(word)}(?:s|es)?\b", text) is not None


def classify(text: str) -> list[dict]:
    """按标题/摘要里的主题词给文献打 OECD 子类标签，返回按命中数排序的前几项。

    只用词表投票，不做语义推断：命中 0 次就不给标签，不硬凑。
    """
    body = (text or "").lower()
    rows = []
    for field in FIELDS:
        hits = [k for k in field.keywords if _hit(body, k)]
        if hits:
            rows.append({"code": field.code, "label": field.label,
                         "major": field.major, "hits": len(hits),
                         "terms": hits[:4]})
    rows.sort(key=lambda r: (-r["hits"], r["code"]))
    return rows


def distribution(texts: list[str], code: str = "") -> dict:
    """统计一批文献落在哪些子类，并给出与所选口径的吻合度。"""
    counts: dict[str, int] = {}
    untagged = 0
    for text in texts:
        tags = classify(text)
        if not tags:
            untagged += 1
            continue
        top = tags[0]["code"]
        counts[top] = counts.get(top, 0) + 1
    total = len(texts)
    rows = [{"code": c, "label": label(c), "count": n}
            for c, n in sorted(counts.items(), key=lambda kv: -kv[1])]
    fit = 0
    if code and total:
        fit = round(sum(1 for text in texts
                        if any(t["code"].startswith(code) for t in classify(text)[:2])) / total, 3)
    return {"counts": rows, "untagged": untagged, "total": total,
            "selected": code, "fit": fit}


def validate(code: str) -> str:
    """规范化输入：接受 "2.5"、"2"、空值；非法值回空。"""
    code = (code or "").strip()
    if not code:
        return ""
    if code in MAJOR:
        return code
    if get(code):
        return code
    return ""
