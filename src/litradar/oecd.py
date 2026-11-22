"""OECD 学科分类（Frascati Manual 2007 的 Fields of Science）。

六个大类、下设子类；只用于给检索与卡片定学科口径，不做硬过滤：
材料/器件类数据库（WOS、Scopus）本身没有这个字段，硬过滤会把正常文献筛没。
每个子类给一个内部学科档案提示，供 domain.gate 使用。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    code: str
    label: str
    domain_hint: str = "general"


MAJOR: dict[str, str] = {
    "1": "1 自然科学",
    "2": "2 工程与技术",
    "3": "3 医学与健康科学",
    "4": "4 农业科学",
    "5": "5 社会科学",
    "6": "6 人文艺术",
}

FIELDS: tuple[Field, ...] = (
    Field("1.1", "数学"),
    Field("1.2", "计算机与信息科学"),
    Field("1.3", "物理科学", "materials"),
    Field("1.4", "化学科学", "materials"),
    Field("1.5", "地球与相关环境科学"),
    Field("1.6", "生物科学", "agri"),
    Field("1.7", "其他自然科学"),
    Field("2.1", "土木工程"),
    Field("2.2", "电气、电子与信息工程", "materials"),
    Field("2.3", "机械工程"),
    Field("2.4", "化学工程", "materials"),
    Field("2.5", "材料工程", "materials"),
    Field("2.6", "医学工程"),
    Field("2.7", "环境工程"),
    Field("2.8", "环境生物技术"),
    Field("2.9", "工业生物技术"),
    Field("2.10", "纳米技术", "materials"),
    Field("2.11", "其他工程与技术"),
    Field("3.1", "基础医学", "biomed"),
    Field("3.2", "临床医学", "biomed"),
    Field("3.3", "健康科学", "biomed"),
    Field("3.4", "医学生物技术", "biomed"),
    Field("3.5", "其他医学科学", "biomed"),
    Field("4.1", "农业、林业与渔业", "agri"),
    Field("4.2", "畜牧与乳品科学", "agri"),
    Field("4.3", "兽医科学", "agri"),
    Field("4.4", "农业生物技术", "agri"),
    Field("4.5", "其他农业科学", "agri"),
    Field("5.1", "心理学"),
    Field("5.2", "经济学与商业"),
    Field("5.3", "教育科学"),
    Field("5.4", "社会学"),
    Field("5.5", "法学"),
    Field("5.6", "政治学"),
    Field("5.7", "社会与经济地理"),
    Field("5.8", "媒体与传播"),
    Field("5.9", "其他社会科学"),
    Field("6.1", "历史与考古"),
    Field("6.2", "语言与文学"),
    Field("6.3", "哲学、伦理与宗教"),
    Field("6.4", "艺术"),
    Field("6.5", "其他人文艺术"),
)


def get(code: str) -> Field | None:
    for field in FIELDS:
        if field.code == code:
            return field
    return None


def label(code: str) -> str:
    field = get(code)
    return f"{field.code} {field.label}" if field else ""


def domain_hint(code: str) -> str:
    field = get(code)
    return field.domain_hint if field else "general"


def as_json() -> list[dict]:
    """给前端下拉用：大类 → 子类。"""
    return [
        {"code": code, "label": text,
         "children": [{"code": f.code, "label": f"{f.code} {f.label}"}
                      for f in FIELDS if f.code.startswith(code + ".")]}
        for code, text in MAJOR.items()
    ]


def classify_terms(code: str) -> list[str]:
    """把子类名翻成英文检索词，仅作检索式补充提示。"""
    mapping = {
        "1.3": ["physics", "condensed matter", "device"],
        "1.4": ["chemistry", "materials chemistry"],
        "2.2": ["electronics", "device", "circuit"],
        "2.4": ["chemical engineering", "synthesis"],
        "2.5": ["materials", "thin film", "device fabrication"],
        "2.10": ["nanotechnology", "nanomaterial"],
        "1.6": ["plant", "microbiology", "ecology"],
        "4.1": ["agriculture", "crop", "soil"],
        "4.4": ["agricultural biotechnology"],
        "3.1": ["medicine", "pathology", "physiology"],
        "3.2": ["clinical", "patient", "cohort"],
    }
    return mapping.get(code, [])
