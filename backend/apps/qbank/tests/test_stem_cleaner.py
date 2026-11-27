"""题干清理规则测试。"""
from apps.qbank.stem_cleaner import clean_stem


def test_removes_grade_and_unit_prefixes():
    assert (
        clean_stem("【音乐·七年级】《中学时代》属于哪种音乐体裁？")
        == "《中学时代》属于哪种音乐体裁？"
    )
    assert (
        clean_stem("【单元练习】[七年级音乐·劳动的歌] “交响曲”的含义是？")
        == "“交响曲”的含义是？"
    )
    assert (
        clean_stem("【美术·八年级】《清明上河图》的作者是？")
        == "《清明上河图》的作者是？"
    )


def test_removes_variant_and_extension_suffixes():
    assert (
        clean_stem("作曲家贝多芬来自哪个国家？（变式 2）")
        == "作曲家贝多芬来自哪个国家？"
    )
    assert (
        clean_stem("以下哪个术语与“民歌”直接相关？(变式 10)")
        == "以下哪个术语与“民歌”直接相关？"
    )
    assert clean_stem("请演唱《龙船调》。（拓展练习）") == "请演唱《龙船调》。"


def test_clean_stem_is_idempotent_and_keeps_plain_text():
    plain = "“昆曲”属于哪一类音乐知识？"
    assert clean_stem(plain) == plain
    assert clean_stem(clean_stem("【音乐·七年级】“昆曲”属于哪一类音乐知识？")) == plain
