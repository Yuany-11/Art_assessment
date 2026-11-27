"""按 2022 版艺术课标与人音版 / 人美版教材目录，重建 1~9 年级章节与单元练习。

参考来源（公开教材目录与课标解读）：
- 教育部《义务教育艺术课程标准（2022 年版）》：音乐、美术按“欣赏、表现、
  创造、联系”四类艺术实践组织学习任务，1~2 年级为唱游·音乐 / 造型·美术。
- 人音版小学音乐 2024 新版及 2011 课标版单元目录。
- 人美版小学、初中美术教材单元 / 课题目录。

本命令做三件事：
1. 把旧的通用章节合并为“拓展类”；
2. 按年级建立教材单元章节，写入学习目标、重点作品、核心概念与课堂任务；
3. 为每个单元生成 7~9 道单选、3 道多选、12 道判断、1 道实践题，
   共 23~25 道与本章知识点直接相关的练习；填空题已整体下线，
   随机练习从客观题中抽取 10 道。

命令幂等：重复执行只刷新本命令生成的单元章节和单元同步练习题目。
"""
from __future__ import annotations

import random

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.exams.management.commands.seed_grade_question_bank import (
    ART_CHAPTERS,
    ART_GRADES,
    GRADE_DIFFICULTY,
    GRADE_NAMES,
    MUSIC_CHAPTERS,
    MUSIC_GRADES,
    ART_CREATOR_FALLBACK,
    ART_COUNTRY_FALLBACK,
    ART_GENRE_FALLBACK,
    ART_MEDIUM_FALLBACK,
    ART_NOTE_FALLBACK,
    ART_PERIOD_FALLBACK,
    MUSIC_COUNTRY_FALLBACK,
    MUSIC_CREATOR_FALLBACK,
    MUSIC_GENRE_FALLBACK,
    MUSIC_MEDIUM_FALLBACK,
    MUSIC_NOTE_FALLBACK,
    MUSIC_PERIOD_FALLBACK,
    _genre_conflicts,
    _medium_conflicts,
    _statements,
    _unique,
)
from apps.qbank.models import Chapter, Course, Question, QuestionOption
from apps.qbank.stem_cleaner import clean_stem
from common.enums import (
    QuestionStatus,
    QuestionType,
    Role,
    ScoringMode,
    Subject,
)

MUSIC = Subject.MUSIC
ART = Subject.ART
KEYS = "ABCDEF"
GENERIC_CHAPTERS = set(MUSIC_CHAPTERS) | set(ART_CHAPTERS)
REVIEW_CHAPTER = "拓展类"

UNITS = {
    MUSIC: {
        1: [
            ("好朋友", "用歌声认识新朋友，学习正确的歌唱姿势，感受二拍子的欢快情绪。"),
            ("祖国您好", "学唱国歌与爱国歌曲，认识音的强弱，体会庄严与亲切的情感。"),
            ("快乐的一天", "在唱游中表现一天的生活，认识 X XX 节奏，体验二拍子律动。"),
            ("可爱的动物", "聆听描写动物的音乐，分辨音的长短与乐器音色，用动作表现形象。"),
            ("爱劳动", "演唱劳动歌曲，认识音的高低，体会劳动节奏与协作精神。"),
            ("过新年", "感受节日音乐的热闹气氛，认识锣鼓镲，参与情境表演。"),
        ],
        2: [
            ("幸福的歌", "感受不同民族的幸福生活，用欢快自然的声音演唱。"),
            ("童趣", "在游戏与律动中体验音乐，分辨速度、力度的变化。"),
            ("跳起舞", "感受二拍子、三拍子舞曲，随音乐做简单的舞蹈动作。"),
            ("咯咯哒", "聆听描写小动物的音乐，模仿叫声、动作与节奏。"),
            ("大海的歌", "感受海洋题材音乐，体验连贯与跳跃的旋律。"),
            ("新年好", "了解中外新年音乐，参与打击乐与情境表演。"),
        ],
        3: [
            ("我们多么幸福", "学习发声练习与唱名，认识 mp、mf，用自然的声音演唱。"),
            ("劳动的歌", "了解劳动号子与衬词，感受四二拍的劳动节奏。"),
            ("丰收歌舞", "感受丰收主题的歌舞音乐，体验民族音乐风格。"),
            ("我爱妈妈", "用深情的声音演唱亲情歌曲，学习力度变化。"),
            ("钟声", "聆听钟声主题音乐，分辨音色与和声。"),
            ("四季童趣", "感受四季变化的音乐形象，学习旋律的走向。"),
        ],
        4: [
            ("歌唱祖国", "用歌声表达爱国情感，了解进行曲的速度与节拍。"),
            ("乡音乡情", "聆听各地民歌，感受方言、衬词与地方风格。"),
            ("快乐校园", "表现校园生活，认识变奏与常见速度术语。"),
            ("甜梦", "感受摇篮曲、夜曲的安静情绪，学习连贯的歌唱。"),
            ("水上的歌", "聆听船歌与水上题材作品，体验三拍子的摇曳感。"),
            ("跳起来", "感受舞曲节奏，分辨二拍子与三拍子的不同律动。"),
        ],
        5: [
            ("朝夕", "感受清晨与夜晚的音乐形象，认识 6/8 拍与旋律走向。"),
            ("红色印记", "聆听革命历史题材作品，认识切分音与男低音。"),
            ("美丽乡村", "感受乡村题材音乐，认识唢呐与朝鲜族音乐。"),
            ("快乐少年", "了解莫扎特与西洋管弦乐队，体验少年题材作品。"),
            ("远山的歌", "聆听山歌，感受高亢自由的旋律与地方风格。"),
            ("冬雪", "感受冬雪题材音乐，认识音程与和声的色彩。"),
        ],
        6: [
            ("芬芳茉莉", "比较不同地区的《茉莉花》，感受民歌的流传与变化。"),
            ("悠扬民歌", "聆听各地民歌，认识山歌、小调、号子的体裁特点。"),
            ("美丽童话", "感受童话题材音乐，分辨角色主题与乐器音色。"),
            ("京腔京韵", "了解京剧行当、唱腔与锣鼓，体验戏歌的韵味。"),
            ("赞美的心", "演唱赞美祖国、赞美生活的歌曲，学习合唱的声部配合。"),
            ("两岸情深", "聆听两岸题材作品，感受同根同源的文化情感。"),
        ],
        7: [
            ("歌唱祖国", "演唱爱国歌曲，了解进行曲、颂歌的体裁与演唱形式。"),
            ("缤纷舞曲", "感受圆舞曲、波尔卡等舞曲体裁，体验三拍子律动。"),
            ("草原牧歌", "聆听蒙古族、藏族等草原音乐，认识长调与马头琴。"),
            ("欧洲风情", "欣赏欧洲民歌与艺术歌曲，了解不同国家的音乐风格。"),
            ("劳动的歌", "聆听劳动号子，感受领唱与和唱相结合的劳动节奏。"),
        ],
        8: [
            ("七子之歌", "聆听表现家国情怀的作品，理解音乐与时代的关系。"),
            ("多彩音乐剧", "了解音乐剧的歌唱、舞蹈、戏剧综合表现形式。"),
            ("雪域天音", "聆听藏族音乐，认识藏族民歌、歌舞与乐器。"),
            ("音诗音画", "欣赏交响音诗、音画，感受音乐描绘画面与意境的方式。"),
            ("国乐飘香", "认识民族管弦乐与经典国乐作品，分辨民族乐器音色。"),
        ],
        9: [
            ("流行乐风", "了解流行音乐的常见体裁与乐队编制，分析其音乐特征。"),
            ("魅力歌剧", "认识歌剧的序曲、咏叹调、宣叙调与合唱。"),
            ("西南情韵", "聆听西南地区民族音乐，感受多声部民歌与歌舞音乐。"),
            ("经典交响", "欣赏交响曲的乐章结构，认识奏鸣曲式与配器。"),
            ("曲苑寻珍", "了解曲艺音乐的种类与说唱特点，感受地方曲种魅力。"),
        ],
    },
    ART: {
        1: [
            ("我是校园小主人", "观察校园环境，用点、线、形和色彩表现自己与新朋友。"),
            ("我与美丽大自然", "感受大自然中的形状、色彩与肌理，进行造型游戏。"),
            ("我是生活小达人", "观察生活用品，动手设计制作简单的生活小物件。"),
            ("我的家乡味", "了解家乡的特产、建筑与民俗，用美术形式表现家乡。"),
            ("红火中国年", "了解春节习俗，制作窗花、灯笼等节日美术作品。"),
        ],
        2: [
            ("点线面的游戏", "认识点、线、面，用大小、疏密、曲直组织画面。"),
            ("彩色的世界", "认识常见颜色，感受色彩的冷暖与搭配。"),
            ("有趣的形状", "用基本形概括物象，进行添画、拼贴与联想。"),
            ("动手做玩具", "利用纸、泥、废旧材料制作简单的玩具。"),
            ("节日里的美术", "了解节日装饰，设计制作贺卡与小挂饰。"),
        ],
        3: [
            ("色彩滴染", "体验色彩滴染与染纸，感受色彩渗化的偶然效果。"),
            ("水墨游戏", "认识毛笔、宣纸与墨色变化，进行水墨游戏。"),
            ("巧用对称形", "理解对称与均衡，用折剪、拼贴设计对称纹样。"),
            ("故事乐园", "为故事画插图或连环画，学习画面叙事。"),
            ("新年贺卡", "了解贺卡的形式与祝福语，设计制作新年贺卡。"),
        ],
        4: [
            ("人物与生活", "观察人物特征与生活场景，学习人物画与场景表现。"),
            ("科学与幻想", "结合科学想象进行创意绘画，表现未来世界。"),
            ("中国画入门", "认识中国画工具，学习荷花、青蛙等写意画法。"),
            ("浮雕与手工", "了解浮雕的凹凸造型，用纸、泥等材料制作浮雕。"),
            ("手绘导游图", "学习地图与导览图设计，安排画面信息与路线。"),
        ],
        5: [
            ("包装与设计", "了解包装的功能与美感，设计易碎品包装和糕点盒。"),
            ("超现实艺术", "欣赏达利等超现实主义作品，理解想象与梦境的表现。"),
            ("家具设计", "观察椅子的结构与功能，设计实用美观的家具。"),
            ("版画与拼贴", "体验实物版画与拼贴，学习肌理与构成的组合。"),
            ("京剧与民间美术", "了解京剧脸谱、门神等民间美术，感受传统造型色彩。"),
        ],
        6: [
            ("动漫形象", "学习动漫人物的夸张、变形与个性表现。"),
            ("民间美术", "欣赏皮影、风筝、泥塑，了解民间美术的造型与色彩。"),
            ("装饰色彩", "认识色彩纯度与装饰色彩，进行夸张、概括的配色。"),
            ("中国画", "学习水仙、梅花、山水等题材的笔墨表现。"),
            ("设计与世界遗产", "了解藏书票、仿生设计与世界遗产，完成设计作品。"),
        ],
        7: [
            ("美术世界与线条", "认识美术的门类与造型元素，学习手绘线条的表达。"),
            ("色彩与生活", "学习色彩基础知识，用色彩表现生活与情感。"),
            ("漫画与吉祥物", "学习漫画造型与吉祥物设计，理解夸张与象征。"),
            ("设计与展示", "学习艺术节策划、面具与展示设计，体验综合设计。"),
            ("生肖的联想", "观察十二生肖的造型特点，用夸张、拟人和联想的方法设计生肖形象。"),
        ],
        8: [
            ("美术与文化", "理解美术是文化的造型载体，欣赏中国画与书法。"),
            ("色彩表达", "学习装饰色彩与色彩情感，用色彩表达主题。"),
            ("中国山水画", "学习山水画的笔墨、构图与意境，欣赏名家作品。"),
            ("纸造型与家居设计", "用纸板进行立体造型，设计家具与理想家居。"),
            ("中国画的形式美", "从笔墨、章法、题款等方面欣赏中国画，理解诗书画印结合的形式美。"),
        ],
        9: [
            ("形式美与速写", "学习形式美法则、线条表现与速写方法。"),
            ("工笔与黑白装饰", "学习工笔花卉与黑白装饰画，理解疏密与节奏。"),
            ("民间美术", "走进民间美术，学习民间色彩搭配与工艺品制作。"),
            ("戏曲与工艺", "了解戏曲美术与工艺美术，完成综合欣赏与设计。"),
            ("明暗与立体的表现", "学习明暗层次与透视规律，用素描或色彩表现物体的体积与空间。"),
        ],
    },
}


def _split_rows(rows, count):
    """把作品或概念尽量均匀地分到各单元。"""
    result = [[] for _ in range(count)]
    for index, row in enumerate(rows):
        result[index % count].append(row)
    return result


def _options(correct, pool, seed, count=4):
    wrongs = [text for text in _unique(pool) if text and text != correct][: count - 1]
    if len(wrongs) < count - 1:
        return None
    texts = [correct, *wrongs]
    random.Random(seed).shuffle(texts)
    pairs = [(KEYS[index], text) for index, text in enumerate(texts)]
    answer = next(key for key, text in pairs if text == correct)
    return pairs, answer


def _multi_options(correct, wrongs, seed):
    correct = _unique(correct)
    wrongs = [text for text in _unique(wrongs) if text not in correct][:2]
    if len(correct) < 2 or len(wrongs) < 2:
        return None
    texts = [*correct[:3], *wrongs]
    random.Random(seed).shuffle(texts)
    pairs = [(KEYS[index], text) for index, text in enumerate(texts)]
    correct_set = set(correct)
    answer = [key for key, text in pairs if text in correct_set]
    if len(answer) < 2:
        return None
    return pairs, answer


def _build_specs(grade, subject, unit_name, focus, works, terms, all_data):
    subject_label = "音乐" if subject == MUSIC else "美术"
    all_works = all_data["works"]
    all_terms = all_data["terms"]
    creators = [row[1] for row in all_works if row[1]]
    countries = [row[2] for row in all_works]
    periods = [row[3] for row in all_works]
    genres = [row[4] for row in all_works]
    media = [row[5] for row in all_works]
    notes = [row[6] for row in all_works]
    definitions = [row[1] for row in all_terms]
    fallbacks = (
        {
            "creator": MUSIC_CREATOR_FALLBACK,
            "country": MUSIC_COUNTRY_FALLBACK,
            "period": MUSIC_PERIOD_FALLBACK,
            "genre": MUSIC_GENRE_FALLBACK,
            "medium": MUSIC_MEDIUM_FALLBACK,
            "note": MUSIC_NOTE_FALLBACK,
        }
        if subject == MUSIC
        else {
            "creator": ART_CREATOR_FALLBACK,
            "country": ART_COUNTRY_FALLBACK,
            "period": ART_PERIOD_FALLBACK,
            "genre": ART_GENRE_FALLBACK,
            "medium": ART_MEDIUM_FALLBACK,
            "note": ART_NOTE_FALLBACK,
        }
    )
    singles = []
    seen = set()

    def add_single(stem, correct, pool, explanation, conflict=None):
        if stem in seen:
            return
        pairs = _options(str(correct), pool, f"{subject}-{grade}-{unit_name}-{stem}")
        if pairs is None:
            return
        options, answer = pairs
        seen.add(stem)
        singles.append({
            "type": QuestionType.SINGLE_CHOICE,
            "stem": stem,
            "options": options,
            "answer": {"value": answer},
            "analysis": f"正确答案为 {answer}。{explanation}",
            "score": 2,
            "mode": ScoringMode.AUTO,
        })

    creator_label = "曲作者" if subject == MUSIC else "作者"
    angle_builders = []
    for work in works:
        title, creator, country, period, genre, medium, note = work
        if creator:
            angle_builders.append((
                f"《{title}》的{creator_label}是？",
            creator,
            creators + fallbacks["creator"],
            f"《{title}》由{creator}创作。",
                None,
            ))
        angle_builders.append((
            f"《{title}》属于哪种{subject_label}体裁或门类？" if subject == MUSIC
            else f"《{title}》属于哪种美术门类？",
            genre,
            genres + fallbacks["genre"],
            f"《{title}》属于{genre}。",
            _genre_conflicts,
        ))
        angle_builders.append((
            f"《{title}》通常采用哪种表演形式？" if subject == MUSIC
            else f"《{title}》主要使用什么材料或技法？",
            medium,
            media + fallbacks["medium"],
            f"《{title}》常以{medium}形式呈现。",
            _medium_conflicts,
        ))
        angle_builders.append((
            f"《{title}》来自哪个国家或地区？",
            country,
            countries + fallbacks["country"],
            f"《{title}》属于{country}的{subject_label}作品。",
            None,
        ))
        angle_builders.append((
            f"《{title}》形成或创作于哪个时期？",
            period,
            periods + fallbacks["period"],
            f"《{title}》属于{period}时期。",
            None,
        ))
        angle_builders.append((
            f"《{title}》的音乐情绪更接近哪一项？" if subject == MUSIC
            else f"《{title}》的画面特点更接近哪一项？",
            note,
            notes + fallbacks["note"],
            f"《{title}》的整体特点是“{note}”。",
            None,
        ))

    for stem, correct, pool, explanation, conflict in angle_builders:
        if len(singles) >= 6:
            break
        if conflict:
            pool = [item for item in pool if not conflict(str(correct), str(item))]
        add_single(stem, correct, pool, explanation)

    # 概念题只用本单元自己的核心概念，避免不同单元出现同一道题。
    categories = _unique([row[2] for row in all_terms])
    for term, definition, category in terms:
        if len(singles) >= 10:
            break
        add_single(
            f"“{term}”的含义是？",
            definition,
            definitions,
            f"“{term}”指{definition}。",
        )
        add_single(
            f"下列对“{term}”的解释，正确的是？",
            definition,
            definitions,
            f"“{term}”指{definition}。",
        )
        add_single(
            f"“{term}”属于下列哪一类概念？",
            category,
            categories,
            f"“{term}”属于{category}类概念。",
        )

    multis = []
    work_statements_source = works or all_works[:1]
    for work in work_statements_source[:3]:
        true_statements, false_statements = _statements(work, all_works)
        pairs = _multi_options(true_statements[:2], false_statements, f"{subject}-{grade}-{unit_name}-{work[0]}")
        if pairs:
            options, answer = pairs
            multis.append({
                "type": QuestionType.MULTIPLE_CHOICE,
                "stem": f"关于《{work[0]}》，下列说法正确的有？",
                "options": options,
                "answer": {"values": answer},
                "analysis": f"正确选项为 {'、'.join(answer)}。应结合作品名称、作者、国家、体裁和表现形式综合判断。",
                "score": 3,
                "mode": ScoringMode.AUTO,
            })
        if len(multis) >= 2:
            break

    # 只搭配本单元核心概念与一个相邻概念，保证各单元的题不重复。
    companion = next(
        (row for row in all_terms if row[0] != terms[0][0]), None
    ) if terms else None
    picked = [row for row in [*(terms[:1]), companion] if row]
    if len(picked) >= 2:
        correct_defs = [f"{term}：{definition}" for term, definition, _ in picked]
        wrong_defs = [
            f"{term}：{definition}"
            for term, definition, _ in all_terms
            if term not in {row[0] for row in picked}
        ][:2]
        pairs = _multi_options(correct_defs, wrong_defs, f"{subject}-{grade}-{unit_name}-terms")
        if pairs:
            options, answer = pairs
            multis.append({
                "type": QuestionType.MULTIPLE_CHOICE,
                "stem": f"下列概念与解释对应正确的有？（{GRADE_NAMES[grade]}年级·{unit_name}）",
                "options": options,
                "answer": {"values": answer},
                "analysis": f"正确选项为 {'、'.join(answer)}。注意区分相近概念。",
                "score": 3,
                "mode": ScoringMode.AUTO,
            })

    # 多选不足 3 道时，用本单元作品再补一组对应关系题。
    if len(multis) < 3 and works:
        work = works[-1]
        correct = [f"《{work[0]}》属于{work[4]}", f"《{work[0]}》来自{work[2]}"]
        wrong = []
        for other in all_works:
            if other[0] == work[0]:
                continue
            if other[4] != work[4]:
                wrong.append(f"《{work[0]}》属于{other[4]}")
            if other[2] != work[2]:
                wrong.append(f"《{work[0]}》来自{other[2]}")
        pairs = _multi_options(correct, wrong, f"{subject}-{grade}-{unit_name}-extra")
        if pairs:
            options, answer = pairs
            multis.append({
                "type": QuestionType.MULTIPLE_CHOICE,
                "stem": f"关于本单元作品《{work[0]}》，下列说法正确的有？",
                "options": options,
                "answer": {"values": answer},
                "analysis": f"正确选项为 {'、'.join(answer)}。",
                "score": 3,
                "mode": ScoringMode.AUTO,
            })

    # 保证每个单元都有 3 道多选题，随机练习才能稳定组成 6+3+1。
    if len(multis) < 3 and len(picked) >= 2:
        correct_defs = [f"{term}：{definition}" for term, definition, _ in picked]
        wrong_defs = [
            f"{term}：{definition}"
            for term, definition, _ in all_terms
            if term not in {row[0] for row in picked}
        ][:2]
        pairs = _multi_options(
            correct_defs, wrong_defs, f"{subject}-{grade}-{unit_name}-fallback-terms"
        )
        if pairs:
            options, answer = pairs
            multis.append({
                "type": QuestionType.MULTIPLE_CHOICE,
                "stem": f"下列{subject_label}概念与解释对应正确的有？（{GRADE_NAMES[grade]}年级·{unit_name}）",
                "options": options,
                "answer": {"values": answer},
                "analysis": f"正确选项为 {'、'.join(answer)}。",
                "score": 3,
                "mode": ScoringMode.AUTO,
            })

    if len(multis) < 3 and len(all_works) >= 2:
        first, second = all_works[0], all_works[1]
        correct = [
            f"《{first[0]}》属于{first[4]}",
            f"《{second[0]}》来自{second[2]}",
        ]
        wrong = [
            f"《{first[0]}》来自{second[2]}",
            f"《{second[0]}》属于{first[4]}",
        ]
        pairs = _multi_options(
            correct, wrong, f"{subject}-{grade}-{unit_name}-fallback-works"
        )
        if pairs:
            options, answer = pairs
            multis.append({
                "type": QuestionType.MULTIPLE_CHOICE,
                "stem": f"关于{GRADE_NAMES[grade]}年级{unit_name}单元的《{first[0]}》《{second[0]}》，下列说法正确的有？",
                "options": options,
                "answer": {"values": answer},
                "analysis": f"正确选项为 {'、'.join(answer)}。",
                "score": 3,
                "mode": ScoringMode.AUTO,
            })

    # 判断题：围绕本单元重点作品与核心概念，正误交替，每个单元 8 道。
    tf_candidates = []
    tf_seen = set()

    def add_tf(statement, value, explanation):
        if not statement:
            return
        stem = f"判断：{statement}。"
        if stem in tf_seen:
            return
        tf_seen.add(stem)
        tf_candidates.append((stem, value, explanation))

    for work in works:
        title, _creator, _country, period, _genre, _medium, note = work
        truths, falses = _statements(work, all_works)
        for statement in truths:
            add_tf(
                statement,
                True,
                f"该说法正确，请对照《{title}》的作者、国家、体裁与表现形式。",
            )
        for statement in falses:
            add_tf(
                statement,
                False,
                f"该说法与《{title}》的实际信息不符，注意区分作者、国家、体裁与表现形式。",
            )
        add_tf(
            f"《{title}》形成或创作于{period}时期",
            True,
            f"《{title}》属于{period}时期。",
        )
        add_tf(
            f"《{title}》的整体特点是{note}",
            True,
            f"《{title}》的整体特点可概括为“{note}”。",
        )
        other_notes = _unique([
            other[6] for other in all_works
            if other[0] != title and other[6] and other[6] != note
        ])
        for wrong_note in other_notes[:2]:
            add_tf(
                f"《{title}》的整体特点是{wrong_note}",
                False,
                f"《{title}》的整体特点是“{note}”，不要与其他作品混淆。",
            )
    for term, definition, category in terms:
        add_tf(
            f"“{term}”指{definition}",
            True,
            f"“{term}”属于{category}概念，含义是{definition}。",
        )
        add_tf(
            f"“{term}”属于{category}类概念",
            True,
            f"“{term}”归入{category}类，含义是{definition}。",
        )
        wrong_definitions = []
        wrong_categories = []
        for other_term, other_definition, other_category in all_terms:
            if other_term == term:
                continue
            if other_definition != definition and other_definition not in wrong_definitions:
                wrong_definitions.append(other_definition)
            if other_category != category and other_category not in wrong_categories:
                wrong_categories.append(other_category)
        for wrong_definition in wrong_definitions[:3]:
            add_tf(
                f"“{term}”指{wrong_definition}",
                False,
                f"“{term}”的含义是{definition}，不要与相近概念混淆。",
            )
        for wrong_category in wrong_categories[:1]:
            add_tf(
                f"“{term}”属于{wrong_category}类概念",
                False,
                f"“{term}”归入{category}类，而不是{wrong_category}类。",
            )

    true_items = [item for item in tf_candidates if item[1]]
    false_items = [item for item in tf_candidates if not item[1]]
    ordered_tf = []
    for index in range(6):
        if index < len(true_items):
            ordered_tf.append(true_items[index])
        if index < len(false_items):
            ordered_tf.append(false_items[index])
    true_false = [
        {
            "type": QuestionType.TRUE_FALSE,
            "stem": stem,
            "options": [],
            "answer": {"value": value},
            "analysis": f"该说法{'正确' if value else '错误'}。{explanation}",
            "score": 2,
            "mode": ScoringMode.AUTO,
        }
        for stem, value, explanation in ordered_tf[:12]
    ]

    practical_type = QuestionType.AUDIO_UPLOAD if subject == MUSIC else QuestionType.IMAGE_UPLOAD
    if subject == MUSIC:
        practice_stem = (
            f"请围绕{GRADE_NAMES[grade]}年级“{unit_name}”单元，选择一首课堂学过的歌曲或乐曲，"
            "完整演唱或演奏并录音上传。要求音准、节奏基本准确，能表现作品的情绪。"
        )
        rubric = "音准 25 分；节奏 25 分；音色与发声 20 分；情绪表达 20 分；完整性 10 分。"
    else:
        practice_stem = (
            f"请以{GRADE_NAMES[grade]}年级“{unit_name}”为主题完成一件美术作品（绘画、拼贴、手工均可），"
            "拍摄或扫描后上传。要求主题明确、画面完整，能运用本单元学习的造型或色彩知识。"
        )
        rubric = "主题与创意 25 分；造型与构图 25 分；色彩或材料运用 20 分；制作完整度 20 分；作品说明 10 分。"

    specs = singles[:10] + multis[:3] + true_false
    specs.append({
        "type": practical_type,
        "stem": practice_stem,
        "options": [],
        "answer": {"reference": "见评分标准"},
        "analysis": "本题为实践作品题，由教师按评分标准人工评分。",
        "score": 10,
        "mode": ScoringMode.MANUAL,
        "rubric": rubric,
    })
    return specs, creators, countries, periods, genres, media, notes


def _chapter_content(grade, subject, unit_name, focus, works, terms, related_terms=()):
    subject_label = "音乐" if subject == MUSIC else "美术"
    lines = [
        "【单元概述】",
        f"{focus}本单元是{GRADE_NAMES[grade]}年级{subject_label}课程“{unit_name}”的学习内容。",
        "",
        "【学习目标】",
        f"1. 感受“{unit_name}”单元作品的情绪、风格与文化背景；",
        "2. 掌握本单元的重点作品、核心概念和基本技能；",
        "3. 能用自己的语言描述作品，并参与演唱、演奏、绘画或制作活动。",
        "",
        "【重点作品】",
    ]
    if works:
        for title, creator, country, period, genre, medium, note in works:
            author = f"，{creator}" if creator else ""
            lines.append(
                f"· 《{title}》{author}，{country}，{period}，{genre}，"
                f"常以{medium}形式呈现，整体特点：{note}。"
            )
    else:
        lines.append("· 结合教材中的聆听与欣赏曲目开展学习。")
    lines.extend(["", "【核心概念】"])
    for term, definition, category in terms:
        lines.append(f"· {term}（{category}）：{definition}。")
    if related_terms:
        lines.append("")
        lines.append("【相关概念】")
        for term, definition, category in related_terms:
            lines.append(f"· {term}（{category}）：{definition}。")
    lines.extend(["", "【知识结构】"])
    for title, creator, country, period, genre, medium, note in works:
        author = creator or "佚名"
        lines.append(
            f"· 作品《{title}》：作者 {author}｜国家/地区 {country}｜时期 {period}"
            f"｜体裁 {genre}｜表现形式 {medium}｜特点 {note}。"
        )
    for term, definition, category in terms:
        lines.append(f"· 概念“{term}”归入“{category}”，答题时先定位类别再判断含义。")
    lines.extend([
        "",
        "【易错提醒】",
        "· 作品名称、作者、国家、时期、体裁与表现形式要一一对应，避免张冠李戴；",
    ])
    if terms and related_terms:
        first_term, second_term = terms[0][0], related_terms[0][0]
        lines.append(f"· 注意区分“{first_term}”与“{second_term}”两个相近概念，不要互换解释；")
    lines.extend([
        "· 判断题先找出说法里的关键事实（谁、哪国、什么体裁），再判断正误。",
        "",
        "【测评提示】",
        "· 判断题常考作品信息与概念解释的正误，说法中出现绝对化词语时要格外小心；",
        "· 选择题注意“最符合”“不正确”等限定词，多选题至少选择两项；",
        "· 实践题按要求提交作品，注意画面或声音的完整性与主题表达。",
        "",
        "【学习方法】",
        "· 先完整聆听或观察作品，再说出第一感受；",
        "· 抓住节奏、旋律、音色、色彩、造型等具体要素进行分析；",
        "· 把作品放到时代、地域和文化背景中理解；",
        "· 通过演唱、演奏、绘画、制作等方式表达自己的感受。",
        "",
        "【课堂任务】",
        f"围绕“{unit_name}”选择一件最喜欢的作品，用本单元学到的知识向同学介绍它，"
        "并完成本章的单元练习。",
        "",
        "【本章练习】",
        "基础练习以客观题为主：7~9 道单选题、3 道多选题、12 道判断题、"
        "1 道实践作品题；随机练习从中抽取 10 题。题库中与本章知识点相关的其他试题"
        "也会归入本章练习。",
    ])
    description = f"{GRADE_NAMES[grade]}年级{subject_label}“{unit_name}”：{focus}"
    return description, "\n".join(lines)


class Command(BaseCommand):
    help = "按课标与教材目录重建 1~9 年级单元章节，并生成与章节对应的练习"

    def add_arguments(self, parser):
        parser.add_argument("--grades", default="1-9", help="年级范围，默认 1-9")
        parser.add_argument("--subject", choices=[MUSIC, ART], help="只处理指定学科")

    @transaction.atomic
    def handle(self, *args, **options):
        grades = self._parse_grades(options["grades"])
        subjects = [options["subject"]] if options.get("subject") else [MUSIC, ART]
        admin = (
            User.objects.filter(role=Role.QUESTION_ADMIN, deleted_at__isnull=True)
            .order_by("id")
            .first()
        )
        if admin is None:
            raise CommandError("未找到题库管理员账号，请先执行 seed_demo_accounts")

        now = timezone.now()
        chapter_total = 0
        question_total = 0
        for subject in subjects:
            data_by_grade = MUSIC_GRADES if subject == MUSIC else ART_GRADES
            subject_label = "音乐" if subject == MUSIC else "美术"
            for grade in grades:
                course = (
                    Course.objects.filter(
                        subject=subject, grade=grade, deleted_at__isnull=True
                    )
                    .order_by("id")
                    .first()
                )
                if course is None:
                    self.stdout.write(
                        self.style.WARNING(f"跳过{grade}年级{subject_label}：课程不存在")
                    )
                    continue
                data = data_by_grade[grade]
                unit_rows = UNITS[subject][grade]
                all_works = data["works"]
                all_terms = data["terms"]
                # 每个单元分配不重复的重点作品与核心概念，避免不同单元生成同一道题；
                # 相关知识概念只写入章节讲解，不用于出题，避免跨单元重复。
                works_parts = [
                    [all_works[index % len(all_works)]]
                    for index in range(len(unit_rows))
                ]
                terms_parts = [
                    [all_terms[index % len(all_terms)]]
                    for index in range(len(unit_rows))
                ]
                related_terms_parts = [
                    [
                        all_terms[(index + 3) % len(all_terms)],
                        all_terms[(index + 5) % len(all_terms)],
                    ]
                    for index in range(len(unit_rows))
                ]

                review, _ = Chapter.objects.get_or_create(
                    course=course,
                    name=REVIEW_CHAPTER,
                    defaults={
                        "sort_order": 99,
                        "description": "与教材单元无直接对应关系的拓展题。",
                        "content": "【拓展说明】\n本类题目用于拓展练习，不绑定具体教材单元。",
                    },
                )
                old_chapters = list(
                    Chapter.objects.filter(course=course, name__in=GENERIC_CHAPTERS)
                )
                for old in old_chapters:
                    Question.objects.filter(chapter=old).update(chapter=review)
                    old.delete()

                for index, (unit_name, focus) in enumerate(unit_rows, start=1):
                    works = works_parts[index - 1]
                    terms = terms_parts[index - 1]
                    description, content = _chapter_content(
                        grade,
                        subject,
                        unit_name,
                        focus,
                        works,
                        terms,
                        related_terms_parts[index - 1],
                    )
                    chapter, _ = Chapter.objects.update_or_create(
                        course=course,
                        name=unit_name,
                        defaults={
                            "description": description,
                            "content": content,
                            "sort_order": index,
                        },
                    )
                    chapter_total += 1

                    Question.objects.filter(
                        chapter=chapter,
                        review_comment="课程单元同步练习，自动审核通过",
                    ).delete()
                    specs, *_ = _build_specs(
                        grade, subject, unit_name, focus, works, terms, data
                    )
                    for spec in specs:
                        stem = clean_stem(spec["stem"])
                        question = Question.objects.create(
                            subject=subject,
                            grade=grade,
                            course=course,
                            chapter=chapter,
                            type=spec["type"],
                            difficulty=GRADE_DIFFICULTY[grade],
                            stem=stem,
                            score=spec["score"],
                            answer=spec["answer"],
                            analysis=spec["analysis"],
                            rubric=spec.get("rubric"),
                            scoring_mode=spec["mode"],
                            status=QuestionStatus.APPROVED,
                            creator=admin,
                            reviewer=admin,
                            review_comment="课程单元同步练习，自动审核通过",
                            reviewed_at=now,
                        )
                        if spec["options"]:
                            QuestionOption.objects.bulk_create([
                                QuestionOption(
                                    question=question,
                                    key=key,
                                    text=text,
                                    sort_order=order,
                                )
                                for order, (key, text) in enumerate(spec["options"], start=1)
                            ])
                        question_total += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"单元章节已更新：{chapter_total} 个单元，生成 {question_total} 道章节练习"
            )
        )

    def _parse_grades(self, value):
        grades = []
        for part in str(value).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                grades.extend(range(int(start), int(end) + 1))
            else:
                grades.append(int(part))
        result = sorted({grade for grade in grades if 1 <= grade <= 9})
        if not result:
            raise CommandError("--grades 需要 1~9 之间的年级，例如 1-9 或 3,6,7,8")
        return result
