"""补充四川省市州、区县和学校演示数据，可重复执行。"""
from django.core.management.base import BaseCommand

from apps.organizations.models import Organization
from common.enums import OrganizationLevel, SchoolType

PROVINCE_CODE = "510000"
PROVINCE_NAME = "四川省"

# 市州：编码采用国家标准行政区划代码。
CITIES = [
    ("510100", "成都市"),
    ("510300", "自贡市"),
    ("510400", "攀枝花市"),
    ("510500", "泸州市"),
    ("510600", "德阳市"),
    ("510700", "绵阳市"),
    ("510800", "广元市"),
    ("510900", "遂宁市"),
    ("511000", "内江市"),
    ("511100", "乐山市"),
    ("511300", "南充市"),
    ("511400", "眉山市"),
    ("511500", "宜宾市"),
    ("511600", "广安市"),
    ("511700", "达州市"),
    ("511800", "雅安市"),
    ("511900", "巴中市"),
    ("512000", "资阳市"),
    ("513200", "阿坝藏族羌族自治州"),
    ("513300", "甘孜藏族自治州"),
    ("513400", "凉山彝族自治州"),
]

DISTRICTS = {
    "510100": [
        ("510104", "锦江区"),
        ("510105", "青羊区"),
        ("510106", "金牛区"),
        ("510107", "武侯区"),
        ("510108", "成华区"),
        ("510112", "龙泉驿区"),
        ("510113", "青白江区"),
        ("510114", "新都区"),
        ("510115", "温江区"),
        ("510116", "双流区"),
        ("510124", "郫都区"),
        ("510132", "新津区"),
        ("510181", "都江堰市"),
        ("510182", "彭州市"),
        ("510183", "邛崃市"),
        ("510184", "崇州市"),
        ("510185", "简阳市"),
    ],
    "510300": [
        ("510302", "自流井区"),
        ("510303", "贡井区"),
        ("510304", "大安区"),
        ("510311", "沿滩区"),
    ],
    "510500": [
        ("510502", "江阳区"),
        ("510503", "纳溪区"),
        ("510504", "龙马潭区"),
    ],
    "510600": [
        ("510603", "旌阳区"),
        ("510604", "罗江区"),
        ("510681", "广汉市"),
        ("510682", "什邡市"),
        ("510683", "绵竹市"),
    ],
    "510700": [
        ("510703", "涪城区"),
        ("510704", "游仙区"),
        ("510705", "安州区"),
    ],
    "511100": [
        ("511102", "市中区"),
        ("511111", "沙湾区"),
        ("511112", "五通桥区"),
    ],
    "511300": [
        ("511302", "顺庆区"),
        ("511303", "高坪区"),
        ("511304", "嘉陵区"),
    ],
    "511400": [
        ("511402", "东坡区"),
        ("511403", "彭山区"),
    ],
    "511500": [
        ("511502", "翠屏区"),
        ("511503", "南溪区"),
        ("511504", "叙州区"),
    ],
    "511700": [
        ("511702", "通川区"),
        ("511703", "达川区"),
    ],
}

# 学校：挂接到对应区县，编码在区县下唯一。
SCHOOLS = {
    "510105": [
        ("510105000001", "成都市石室联合中学蜀华分校", SchoolType.MIDDLE),
        ("510105000002", "成都市泡桐树小学", SchoolType.PRIMARY),
        ("510105000003", "成都市实验小学", SchoolType.PRIMARY),
        ("510105000004", "成都市青羊实验中学", SchoolType.MIDDLE),
    ],
    "510104": [
        ("510104000001", "四川省成都市第七中学", SchoolType.HIGH),
        ("510104000002", "成都市盐道街中学", SchoolType.MIDDLE),
        ("510104000003", "成都市龙王庙正街小学", SchoolType.PRIMARY),
    ],
    "510106": [
        ("510106000001", "成都市第二十中学校", SchoolType.HIGH),
        ("510106000002", "成都市茶店子小学校", SchoolType.PRIMARY),
    ],
    "510107": [
        ("510107000001", "成都市第十二中学", SchoolType.MIDDLE),
        ("510107000002", "成都市龙江路小学", SchoolType.PRIMARY),
    ],
    "510108": [
        ("510108000001", "成都列五中学", SchoolType.MIDDLE),
        ("510108000002", "成都市成华小学校", SchoolType.PRIMARY),
    ],
    "510115": [
        ("510115000001", "成都市温江区光华实验中学校", SchoolType.MIDDLE),
        ("510115000002", "成都市温江区实验学校", SchoolType.COMBINED),
    ],
    "510181": [
        ("510181000001", "都江堰市青城山高级中学", SchoolType.HIGH),
        ("510181000002", "都江堰市北街小学", SchoolType.PRIMARY),
    ],
    "510302": [
        ("510302000001", "自贡市蜀光中学", SchoolType.HIGH),
        ("510302000002", "自贡市汇东实验学校", SchoolType.COMBINED),
    ],
    "510502": [
        ("510502000001", "四川省泸州高级中学校", SchoolType.HIGH),
        ("510502000002", "泸州市梓橦路学校", SchoolType.COMBINED),
    ],
    "510603": [
        ("510603000001", "四川省德阳中学校", SchoolType.HIGH),
        ("510603000002", "德阳市实验小学校", SchoolType.PRIMARY),
    ],
    "510681": [
        ("510681000001", "四川省广汉中学", SchoolType.HIGH),
    ],
    "510703": [
        ("510703000001", "四川省绵阳中学", SchoolType.HIGH),
        ("510703000002", "四川省绵阳南山中学", SchoolType.HIGH),
        ("510703000003", "绵阳市实验小学", SchoolType.PRIMARY),
    ],
    "511102": [
        ("511102000001", "四川省乐山第一中学校", SchoolType.HIGH),
        ("511102000002", "乐山市实验小学", SchoolType.PRIMARY),
    ],
    "511302": [
        ("511302000001", "四川省南充高级中学", SchoolType.HIGH),
        ("511302000002", "南充市五星小学", SchoolType.PRIMARY),
    ],
    "511402": [
        ("511402000001", "四川省眉山中学校", SchoolType.HIGH),
        ("511402000002", "眉山市东坡区苏南小学", SchoolType.PRIMARY),
    ],
    "511502": [
        ("511502000001", "四川省宜宾市第一中学校", SchoolType.HIGH),
        ("511502000002", "宜宾市翠屏区人民路小学校", SchoolType.PRIMARY),
    ],
    "511702": [
        ("511702000001", "四川省达州中学", SchoolType.HIGH),
        ("511702000002", "达州市通川区第一小学校", SchoolType.PRIMARY),
    ],
}


class Command(BaseCommand):
    help = "补充四川省市州、区县和学校演示数据（保留已有真实学校）"

    def handle(self, *args, **options):
        province, _ = Organization.objects.update_or_create(
            code=PROVINCE_CODE,
            parent=None,
            defaults={"level": OrganizationLevel.PROVINCE, "name": PROVINCE_NAME},
        )
        city_map = {}
        for code, name in CITIES:
            city, _ = Organization.objects.update_or_create(
                code=code,
                parent=province,
                defaults={"level": OrganizationLevel.CITY, "name": name},
            )
            city_map[code] = city

        district_map = {}
        for city_code, rows in DISTRICTS.items():
            city = city_map[city_code]
            for code, name in rows:
                district, _ = Organization.objects.update_or_create(
                    code=code,
                    parent=city,
                    defaults={"level": OrganizationLevel.DISTRICT, "name": name},
                )
                district_map[code] = district

        school_count = 0
        for district_code, rows in SCHOOLS.items():
            district = district_map[district_code]
            for code, name, school_type in rows:
                Organization.objects.update_or_create(
                    code=code,
                    parent=district,
                    defaults={
                        "level": OrganizationLevel.SCHOOL,
                        "name": name,
                        "school_type": school_type,
                    },
                )
                school_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"四川省组织数据已补齐：{len(city_map)} 个市州、"
                f"{len(district_map)} 个区县、{school_count} 所学校"
            )
        )
