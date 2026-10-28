"""丰富各端口的演示数据（可重复执行）。

包含：
- 音乐 / 美术课程与章节
- 100 道分类试题（96 道已审核、3 道待审核、1 道已驳回）
- 教师自动组卷生成的试卷
- 已发布测评、学生作答与教师评分、学情报告

用法：
    python manage.py seed_rich_demo
"""
import copy
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.classes.models import Class
from apps.exams.models import (
    Assessment,
    Attempt,
    AttemptAnswer,
    Certificate,
    LearningReport,
    Paper,
    Score,
)
from apps.exams.services.assessment import can_start, publish_assessment
from apps.exams.services.attempt import submit_attempt
from apps.exams.services.certificate import generate_certificates
from apps.exams.services.grading import submit_grading
from apps.exams.services.paper import create_auto_paper
from apps.files.models import FileObject
from apps.files.services import save_upload
from apps.organizations.models import Organization
from apps.qbank.models import Chapter, Course, Question, QuestionOption
from apps.qbank.services import review_question
from common.enums import (
    AttemptStatus,
    FileCategory,
    GradingStatus,
    OrganizationLevel,
    PaperStatus,
    PaperType,
    QuestionStatus,
    QuestionType,
    Role,
    ScoringMode,
    ScopeType,
    ShowAnswerMode,
    Subject,
)

MUSIC = Subject.MUSIC
ART = Subject.ART

# 课程章节
MUSIC_CHAPTERS = ["乐理基础", "视唱练耳", "音乐欣赏", "乐器与演奏"]
ART_CHAPTERS = ["造型基础", "色彩知识", "中国书画", "美术欣赏", "设计与工艺"]

MUSIC_PENDING_STEMS = {
    "调号中有一个升号时，通常对应哪个大调？",
    "练耳训练通常包括哪些内容？",
    "3/4拍属于复拍子。",
    "一个八度包含 ___ 个半音。",
}
ART_PENDING_STEMS = {
    "黄金分割比大约是多少？",
    "标志设计应遵循哪些原则？",
}


# --------------------------------------------------------------------------
# 题目构造辅助函数
# --------------------------------------------------------------------------

def _rotate(items, seed_text):
    shift = len(seed_text) % len(items)
    items = items[shift:] + items[:shift]
    return list(zip("ABCDEFG"[:len(items)], items))


def single(chapter, difficulty, stem, correct, wrongs):
    pairs = _rotate([correct, *wrongs], stem)
    return {
        "type": QuestionType.SINGLE_CHOICE, "chapter": chapter,
        "difficulty": difficulty, "stem": stem, "score": 5,
        "options": [{"key": k, "text": t} for k, t in pairs],
        "answer": {"value": next(k for k, t in pairs if t == correct)},
        "scoring_mode": ScoringMode.AUTO,
    }


def multi(chapter, difficulty, stem, correct, wrongs):
    pairs = _rotate([*correct, *wrongs], stem)
    answer = [k for k, t in pairs if t in correct]
    return {
        "type": QuestionType.MULTIPLE_CHOICE, "chapter": chapter,
        "difficulty": difficulty, "stem": stem, "score": 5,
        "options": [{"key": k, "text": t} for k, t in pairs],
        "answer": {"values": answer}, "scoring_mode": ScoringMode.AUTO,
    }


def true_false(chapter, difficulty, stem, answer):
    return {
        "type": QuestionType.TRUE_FALSE, "chapter": chapter,
        "difficulty": difficulty, "stem": stem, "score": 4,
        "answer": {"value": answer}, "scoring_mode": ScoringMode.AUTO,
    }


def fill_blank(chapter, difficulty, stem, values):
    return {
        "type": QuestionType.FILL_BLANK, "chapter": chapter,
        "difficulty": difficulty, "stem": stem, "score": 5,
        "answer": {"values": values}, "scoring_mode": ScoringMode.AUTO,
    }


def short_answer(chapter, difficulty, stem, reference):
    return {
        "type": QuestionType.SHORT_ANSWER, "chapter": chapter,
        "difficulty": difficulty, "stem": stem, "score": 10,
        "answer": {"text": reference}, "scoring_mode": ScoringMode.MANUAL,
        "rubric": "要点完整、表述清楚即可得分。",
    }


MUSIC_QUESTIONS = [
    # 单选题 22
    single("乐理基础", 1, "四分音符的时值通常等于几拍？", "一拍", ["半拍", "两拍", "四拍"]),
    single("乐理基础", 1, "五线谱由几条平行的横线组成？", "五条", ["四条", "六条", "七条"]),
    single("乐理基础", 1, "C大调的主音是哪个音？", "C", ["D", "E", "G"]),
    single("乐理基础", 2, "附点四分音符的时值等于？", "一拍半", ["一拍", "两拍", "半拍"]),
    single("乐理基础", 2, "升号（♯）的作用是？", "升高半音", ["降低半音", "升高全音", "还原音高"]),
    single("乐理基础", 2, "力度记号 f 表示？", "强", ["弱", "中强", "渐弱"]),
    single("乐理基础", 3, "三拍子的强弱规律是？", "强弱弱", ["强弱", "强强弱", "弱强弱"]),
    single("乐理基础", 3, "速度术语 Adagio 表示？", "柔板", ["快板", "急板", "行板"]),
    single("乐理基础", 3, "C到E构成什么音程？", "大三度", ["小三度", "纯四度", "大二度"]),
    single("乐理基础", 4, "调号中有一个升号时，通常对应哪个大调？", "G大调", ["C大调", "D大调", "F大调"]),
    single("视唱练耳", 1, "模唱是指？", "模仿演唱听到的旋律", ["看着乐谱默读", "自己创作旋律", "用乐器演奏"]),
    single("视唱练耳", 2, "下列哪种练习最常用于音准训练？", "音阶练习", ["默写歌词", "抄写乐谱", "欣赏交响乐"]),
    single("视唱练耳", 3, "打拍子时，强拍的手势通常向哪个方向？", "向下", ["向上", "向左", "向右"]),
    single("视唱练耳", 4, "听辨和弦性质时，主要判断什么？", "大三和弦、小三和弦等性质", ["音符的时值", "乐器的材质", "乐曲的速度"]),
    single("音乐欣赏", 1, "《义勇军进行曲》的作曲者是？", "聂耳", ["冼星海", "贺绿汀", "刘天华"]),
    single("音乐欣赏", 1, "《二泉映月》的主奏乐器是？", "二胡", ["琵琶", "古筝", "笛子"]),
    single("音乐欣赏", 2, "《黄河大合唱》的作曲者是？", "冼星海", ["聂耳", "马思聪", "黄自"]),
    single("音乐欣赏", 3, "《欢乐颂》出自贝多芬的哪部作品？", "《第九交响曲》", ["《第五交响曲》", "《第六交响曲》", "《月光奏鸣曲》"]),
    single("音乐欣赏", 3, "圆舞曲通常采用几拍子？", "三拍子", ["二拍子", "四拍子", "五拍子"]),
    single("音乐欣赏", 4, "小提琴协奏曲《梁山伯与祝英台》的曲作者是？", "何占豪、陈钢", ["冼星海、聂耳", "贺绿汀、丁善德", "刘天华、阿炳"]),
    single("乐器与演奏", 1, "小提琴属于哪一类乐器？", "弦乐器", ["木管乐器", "铜管乐器", "打击乐器"]),
    single("乐器与演奏", 2, "长笛属于哪一类乐器？", "木管乐器", ["弦乐器", "铜管乐器", "打击乐器"]),
    # 多选题 8
    multi("音乐欣赏", 3, "中国民歌的主要体裁包括哪些？", ["山歌", "小调", "劳动号子"], ["交响曲", "协奏曲"]),
    multi("音乐欣赏", 4, "中国民族五声调式的音阶包括哪些音？", ["宫", "商", "角"], ["变宫", "清角"]),
    multi("乐器与演奏", 2, "下列属于打击乐器的有？", ["定音鼓", "木琴"], ["长笛", "单簧管", "小号"]),
    multi("乐器与演奏", 2, "下列属于木管乐器的有？", ["长笛", "单簧管", "双簧管"], ["小号", "长号"]),
    multi("乐理基础", 2, "音乐的基本要素包括哪些？", ["旋律", "节奏", "和声"], ["油画", "雕塑"]),
    multi("乐理基础", 3, "下列属于单拍子的有？", ["2/4拍", "3/4拍"], ["4/4拍", "6/8拍", "5/4拍"]),
    multi("视唱练耳", 3, "练耳训练通常包括哪些内容？", ["音高听辨", "节奏听辨", "和弦听辨"], ["色彩搭配", "构图设计"]),
    multi("音乐欣赏", 3, "下列属于贝多芬作品的有？", ["《命运交响曲》", "《田园交响曲》", "《月光奏鸣曲》"], ["《天鹅湖》", "《卡门》"]),
    # 判断题 9
    true_false("乐理基础", 1, "五线谱有五条平行的横线。", True),
    true_false("乐理基础", 1, "休止符表示声音的静止。", True),
    true_false("乐理基础", 1, "4/4拍表示以四分音符为一拍，每小节四拍。", True),
    true_false("乐理基础", 2, "降号表示将音升高半音。", False),
    true_false("乐理基础", 2, "附点音符的时值等于原音符时值的一半。", False),
    true_false("乐理基础", 3, "3/4拍属于复拍子。", False),
    true_false("乐理基础", 3, "切分音会把重音移到弱拍或弱位。", True),
    true_false("视唱练耳", 2, "视唱前应先看清谱号和拍号。", True),
    true_false("音乐欣赏", 3, "《天鹅湖》是柴可夫斯基创作的芭蕾舞剧。", True),
    # 填空题 8
    fill_blank("乐理基础", 1, "2/4拍表示每小节有 ___ 拍。", ["2", "两"]),
    fill_blank("乐理基础", 1, "简谱中的“1”对应的唱名是 ___。", ["do", "哆"]),
    fill_blank("乐器与演奏", 1, "二胡通常有 ___ 根弦。", ["2", "两"]),
    fill_blank("乐理基础", 2, "力度记号 p 表示 ___。", ["弱"]),
    fill_blank("音乐欣赏", 2, "《义勇军进行曲》的作曲者是 ___。", ["聂耳"]),
    fill_blank("乐理基础", 2, "五线谱开头用来确定音高的符号叫 ___。", ["谱号"]),
    fill_blank("乐理基础", 3, "以四分音符为一拍时，附点二分音符的时值是 ___ 拍。", ["3", "三"]),
    fill_blank("乐理基础", 4, "一个八度包含 ___ 个半音。", ["12", "十二"]),
    # 简答题 8
    short_answer("乐理基础", 2, "简述节奏与节拍的区别。", "节奏是音的长短、强弱有组织的组合；节拍是固定时值的强弱规律，如2/4、3/4拍。"),
    short_answer("乐理基础", 2, "附点音符有什么作用？", "附点延长原音符时值的一半，使旋律更有推动力，也常用于强调。"),
    short_answer("乐理基础", 3, "举例说明什么是切分音。", "切分音通过改变常规强弱规律，把重音移到弱拍或弱位。例如 × ×· × 中，中间音被强调。"),
    short_answer("视唱练耳", 3, "视唱前需要做哪些准备？", "看清谱号、调号、拍号和速度，划分乐句，确定呼吸点，再轻声试唱。"),
    short_answer("视唱练耳", 3, "说说提高音准的常用方法。", "多唱音阶和音程，用钢琴等乐器辅助校音，慢速练习并录音回听，注意气息稳定。"),
    short_answer("音乐欣赏", 3, "简述《二泉映月》的音乐情绪。", "旋律委婉深沉，带有悲凉与坚韧，表达了作者坎坷的生活经历和对生活的感慨。"),
    short_answer("音乐欣赏", 3, "进行曲的节奏有什么特点？", "多使用二拍子或四拍子，节奏鲜明有力、重音清晰，适合队列行进。"),
    short_answer("乐器与演奏", 4, "简述弦乐器、管乐器、打击乐器的分类依据。", "按发声方式分类：弦振动发声为弦乐器，气流振动发声为管乐器，敲击发声为打击乐器。"),
]

ART_QUESTIONS = [
    # 单选题 16
    single("色彩知识", 1, "美术中的三原色通常指哪三种颜色？", "红、黄、蓝", ["红、绿、蓝", "橙、绿、紫", "黑、白、灰"]),
    single("色彩知识", 2, "由两种原色调配而成的颜色称为间色，三间色是？", "橙、绿、紫", ["红、黄、蓝", "黑、白、灰", "粉、棕、青"]),
    single("色彩知识", 2, "下列属于冷色的是？", "蓝色", ["红色", "橙色", "黄色"]),
    single("色彩知识", 2, "色彩的三要素是？", "色相、明度、纯度", ["红、黄、蓝", "点、线、面", "近、中、远"]),
    single("造型基础", 1, "素描主要表现物体的什么？", "形体结构与明暗关系", ["文字说明", "声音变化", "故事情节"]),
    single("造型基础", 2, "透视现象中“近大远小”体现了什么？", "空间纵深关系", ["色彩对比", "材质区别", "构图对称"]),
    single("中国书画", 1, "中国画使用的主要工具材料是？", "毛笔、墨、宣纸", ["油画笔、画布", "炭笔、素描纸", "喷枪、模板"]),
    single("中国书画", 2, "中国画按题材通常分为哪三类？", "人物、山水、花鸟", ["风景、静物、肖像", "油画、版画、雕塑", "写实、抽象、装饰"]),
    single("中国书画", 3, "工笔画的主要特点是？", "描绘精细、线条工整", ["笔触奔放、概括简练", "色彩单一、不求形似", "以拼贴为主"]),
    single("中国书画", 2, "《清明上河图》的作者是？", "张择端", ["顾恺之", "齐白石", "吴道子"]),
    single("美术欣赏", 1, "《蒙娜丽莎》的作者是？", "达·芬奇", ["梵高", "毕加索", "莫奈"]),
    single("美术欣赏", 2, "《星月夜》的作者是？", "梵高", ["莫奈", "达·芬奇", "塞尚"]),
    single("美术欣赏", 2, "剪纸属于哪一类美术？", "民间美术", ["宫廷美术", "宗教美术", "商业美术"]),
    single("设计与工艺", 3, "标志设计首先要保证的是？", "识别性", ["复杂性", "装饰性", "趣味性"]),
    single("造型基础", 3, "对称与均衡属于美术中的什么？", "构图形式", ["色彩属性", "制作工具", "绘画题材"]),
    single("造型基础", 4, "黄金分割比大约是多少？", "0.618", ["0.5", "0.75", "1.414"]),
    # 多选题 7
    multi("色彩知识", 1, "三原色包括下列哪些颜色？", ["红", "黄", "蓝"], ["绿", "紫"]),
    multi("色彩知识", 2, "色彩三要素包括？", ["色相", "明度", "纯度"], ["笔触", "构图"]),
    multi("中国书画", 2, "中国画的常见题材包括？", ["人物", "山水", "花鸟"], ["风景", "静物"]),
    multi("中国书画", 1, "中国画常用的工具材料有？", ["毛笔", "墨", "宣纸"], ["油画笔", "画布"]),
    multi("设计与工艺", 3, "设计通常需要兼顾哪些方面？", ["实用", "美观", "经济"], ["随意", "复杂", "昂贵"]),
    multi("美术欣赏", 2, "下列属于中国民间美术形式的有？", ["剪纸", "年画", "皮影"], ["油画", "水彩画"]),
    multi("色彩知识", 2, "下列属于冷色的有？", ["蓝色", "绿色", "紫色"], ["红色", "橙色"]),
    # 判断题 8
    true_false("色彩知识", 1, "三原色可以调配出其他颜色。", True),
    true_false("色彩知识", 1, "红色通常属于暖色。", True),
    true_false("中国书画", 2, "中国画只能使用墨，不能上色。", False),
    true_false("中国书画", 2, "《清明上河图》是北宋时期的作品。", True),
    true_false("造型基础", 2, "素描只能使用铅笔完成。", False),
    true_false("造型基础", 2, "透视可以让画面产生空间感。", True),
    true_false("美术欣赏", 1, "剪纸是中国民间美术的一种。", True),
    true_false("设计与工艺", 2, "标志设计越复杂越好。", False),
    # 填空题 8
    fill_blank("色彩知识", 1, "三原色是红、黄和 ___。", ["蓝"]),
    fill_blank("色彩知识", 2, "三间色是橙、绿和 ___。", ["紫"]),
    fill_blank("中国书画", 2, "《清明上河图》的作者是 ___。", ["张择端"]),
    fill_blank("美术欣赏", 1, "《蒙娜丽莎》的作者是 ___。", ["达·芬奇", "达芬奇"]),
    fill_blank("中国书画", 2, "中国画按题材分为人物、山水和 ___。", ["花鸟"]),
    fill_blank("色彩知识", 2, "色彩三要素是色相、明度和 ___。", ["纯度"]),
    fill_blank("美术欣赏", 2, "剪纸属于 ___ 美术。", ["民间"]),
    fill_blank("造型基础", 4, "黄金分割比约为 ___。", ["0.618"]),
    # 简答题 6
    short_answer("色彩知识", 2, "简述三原色与三间色的关系。", "三原色红、黄、蓝不能由其他颜色调出；两种原色相调得到橙、绿、紫三间色。"),
    short_answer("色彩知识", 3, "谈谈冷色与暖色给人的不同感受。", "冷色如蓝、绿、紫给人安静、后退的感觉；暖色如红、橙、黄给人热烈、前进的感觉。"),
    short_answer("中国书画", 3, "简述中国画与西画在工具材料上的区别。", "中国画主要用毛笔、墨和宣纸；西画常用油画笔、画布和油画颜料等。"),
    short_answer("造型基础", 3, "如何理解透视中的“近大远小”？", "物体离视点近时显得大，远时显得小，形成空间纵深和立体感。"),
    short_answer("美术欣赏", 2, "列举两种民间美术形式并说明其特点。", "剪纸造型夸张、线条流畅；年画色彩鲜明、寓意吉祥。"),
    short_answer("设计与工艺", 3, "标志设计应遵循哪些原则？", "应做到识别性强、造型简洁、风格统一、便于记忆和应用。"),
]

MUSIC_RULES = [
    {"type": QuestionType.SINGLE_CHOICE, "count": 10, "scorePerQuestion": 4},
    {"type": QuestionType.MULTIPLE_CHOICE, "count": 4, "scorePerQuestion": 4},
    {"type": QuestionType.TRUE_FALSE, "count": 4, "scorePerQuestion": 3},
    {"type": QuestionType.FILL_BLANK, "count": 4, "scorePerQuestion": 4},
    {"type": QuestionType.SHORT_ANSWER, "count": 3, "scorePerQuestion": 10},
]
ART_RULES = [
    {"type": QuestionType.SINGLE_CHOICE, "count": 8, "scorePerQuestion": 4},
    {"type": QuestionType.MULTIPLE_CHOICE, "count": 4, "scorePerQuestion": 4},
    {"type": QuestionType.TRUE_FALSE, "count": 4, "scorePerQuestion": 3},
    {"type": QuestionType.FILL_BLANK, "count": 3, "scorePerQuestion": 4},
    {"type": QuestionType.SHORT_ANSWER, "count": 2, "scorePerQuestion": 10},
]


class Command(BaseCommand):
    help = "初始化丰富的音乐/美术演示数据（题库、自动组卷、测评、作答与学情报告）"

    @transaction.atomic
    def handle(self, *args, **options):
        now = timezone.now()
        school = Organization.objects.filter(
            code="S001", deleted_at__isnull=True
        ).first()
        school2 = Organization.objects.filter(
            code="DEMO-SCHOOL", deleted_at__isnull=True
        ).first()
        if not school or not school2:
            raise CommandError("未找到演示学校，请先执行 seed_organizations 与 seed_demo")

        class1 = Class.objects.filter(school=school, class_code="DEMO-7-1").first()
        class2 = Class.objects.filter(
            school=school2, class_code="DEMO-ACC-7-1"
        ).first()
        if not class1 or not class2:
            raise CommandError("未找到演示班级，请先执行 seed_demo 与 seed_demo_accounts")

        users = {u.username: u for u in User.objects.filter(
            username__in=[
                "teacher", "teacher_music", "teacher_art", "student", "student2",
                "student_001", "student_002", "question_admin",
            ]
        )}
        missing = [
            name for name in (
                "teacher", "teacher_art", "student", "student2",
                "student_001", "student_002", "question_admin",
            ) if name not in users
        ]
        if missing:
            raise CommandError(f"缺少演示账号：{', '.join(missing)}，请先执行 seed_demo_accounts / seed_demo")

        teacher = users["teacher"]
        teacher_art = users["teacher_art"]
        admin = users["question_admin"]
        student = users["student"]
        student2 = users["student2"]
        student_a = users["student_001"]
        student_b = users["student_002"]

        music_course, music_chapters = self._catalog(
            "七年级音乐（人教版）", MUSIC, 7, MUSIC_CHAPTERS
        )
        art_course, art_chapters = self._catalog(
            "七年级美术（人美版）", ART, 7, ART_CHAPTERS
        )

        created_questions = self._seed_questions(
            admin, teacher, teacher_art,
            music_course, music_chapters, MUSIC_QUESTIONS, MUSIC_PENDING_STEMS,
            art_course, art_chapters, ART_QUESTIONS, ART_PENDING_STEMS,
        )
        self._seed_reviews(admin)

        # 教师自动组卷（同一标题可重复执行）
        music_paper_1 = self._auto_paper(
            teacher, class1, "七年级音乐·自动组卷测评卷（一）", MUSIC, music_course, MUSIC_RULES
        )
        music_paper_2 = self._auto_paper(
            teacher, class1, "七年级音乐·自动组卷测评卷（二）", MUSIC, music_course, MUSIC_RULES
        )
        music_paper_3 = self._auto_paper(
            teacher, class1, "七年级音乐·综合能力检测卷", MUSIC, music_course, MUSIC_RULES
        )
        art_paper_1 = self._auto_paper(
            teacher_art, class2, "七年级美术·自动组卷测评卷（一）", ART, art_course, ART_RULES
        )
        art_paper_2 = self._auto_paper(
            teacher_art, class2, "七年级美术·综合能力检测卷", ART, art_course, ART_RULES
        )

        # 已发布测评：两场历史测评（含作答）+ 一场正在进行
        music_a1 = self._publish(
            teacher, class1, "七年级音乐阶段测评（一）", music_paper_1,
            now - timedelta(days=60), now - timedelta(days=45),
        )
        music_a2 = self._publish(
            teacher, class1, "七年级音乐阶段测评（二）", music_paper_2,
            now - timedelta(days=20), now - timedelta(days=10),
        )
        music_a3 = self._publish(
            teacher, class1, "七年级音乐综合测评", music_paper_3,
            now - timedelta(hours=1), now + timedelta(days=10),
            attempt_limit=2,
        )
        art_a1 = self._publish(
            teacher_art, class2, "七年级美术阶段测评（一）", art_paper_1,
            now - timedelta(days=40), now - timedelta(days=25),
        )
        art_a2 = self._publish(
            teacher_art, class2, "七年级美术综合测评", art_paper_2,
            now - timedelta(hours=1), now + timedelta(days=14),
            attempt_limit=2,
        )

        # 历史答卷 + 评分（student2 的第二场保留为待评分任务）
        self._seed_attempt(teacher, music_a1, student, wrong_every=3, subjective_rate=0.6)
        self._seed_attempt(teacher, music_a2, student, wrong_every=8, subjective_rate=0.85)
        self._seed_attempt(teacher, music_a1, student2, wrong_every=4, subjective_rate=0.7)
        self._seed_attempt(
            teacher, music_a2, student2, wrong_every=5, subjective_rate=0.8,
            finalize=False,
        )
        self._seed_attempt(teacher_art, art_a1, student_a, wrong_every=3, subjective_rate=0.65)
        self._seed_attempt(teacher_art, art_a1, student_b, wrong_every=6, subjective_rate=0.9)

        # 学情报告（学生端“我的学习报告”）
        report_count = 0
        for student_obj, subject in (
            (student, MUSIC), (student2, MUSIC),
            (student_a, ART), (student_b, ART),
        ):
            if self._learning_report(student_obj, subject):
                report_count += 1

        # 演示证书：student 音乐 + student_001 美术，共两张
        cert_count = self._seed_certificates(
            teacher, teacher_art, music_a2, art_a1, student, student_a,
        )
        # 课外美术作品
        artwork_count = self._seed_artworks(student_a, student_b, student, student2)

        # 检查学生是否能开始正在进行的测评
        can_take = True
        try:
            can_start(music_a3, student)
        except Exception:
            can_take = False

        total_questions = Question.objects.filter(
            stem__in=[q["stem"] for q in MUSIC_QUESTIONS + ART_QUESTIONS]
        ).count()
        approved = Question.objects.filter(
            stem__in=[q["stem"] for q in MUSIC_QUESTIONS + ART_QUESTIONS],
            status=QuestionStatus.APPROVED,
        ).count()
        pending = Question.objects.filter(
            stem__in=[q["stem"] for q in MUSIC_QUESTIONS + ART_QUESTIONS],
            status=QuestionStatus.PENDING,
        ).count()

        self.stdout.write(self.style.SUCCESS("丰富演示数据初始化完成"))
        self.stdout.write(
            f"题库：本次新增 {created_questions} 道，当前共 {total_questions} 道"
            f"（已审核 {approved} 道，待审核 {pending} 道）"
        )
        self.stdout.write(
            f"自动组卷：5 张（音乐 3 张 / 美术 2 张）；测评：5 场"
            f"（进行中 {music_a3.id}、{art_a2.id}）"
        )
        self.stdout.write(
            f"学情报告：{report_count} 份；"
            f"学生端可作答进行中测评：{'是' if can_take else '否'}"
        )
        self.stdout.write(
            f"证书：本次新增 {cert_count} 张（student 音乐、student_001 美术）；"
            f"课外美术作品：本次新增 {artwork_count} 件"
        )
        self.stdout.write(
            "演示账号：student / student2（音乐），student_001 / student_002（美术），"
            "teacher / teacher_art；密码 Demo@123456"
        )

    # ------------------------------------------------------------------
    def _catalog(self, name, subject, grade, chapter_names):
        course, _ = Course.objects.get_or_create(
            name=name, subject=subject, grade=grade,
            defaults={"description": f"{name}演示课程"},
        )
        chapters = {}
        for index, chapter_name in enumerate(chapter_names, start=1):
            chapter, _ = Chapter.objects.get_or_create(
                course=course, name=chapter_name,
                defaults={"sort_order": index},
            )
            chapters[chapter_name] = chapter
        return course, chapters

    def _seed_questions(
        self, admin, teacher, teacher_art,
        music_course, music_chapters, music_specs, music_pending,
        art_course, art_chapters, art_specs, art_pending,
    ):
        created = 0
        created += self._create_specs(
            MUSIC, music_course, music_chapters, music_specs, music_pending, admin, teacher
        )
        created += self._create_specs(
            ART, art_course, art_chapters, art_specs, art_pending, admin, teacher_art
        )
        return created

    def _create_specs(
        self, subject, course, chapters, specs, pending_stems, admin, teacher,
    ):
        now = timezone.now()
        created = 0
        for spec in specs:
            status = (
                QuestionStatus.PENDING
                if spec["stem"] in pending_stems
                else QuestionStatus.APPROVED
            )
            creator = teacher if status == QuestionStatus.PENDING else admin
            defaults = {
                "subject": subject,
                "grade": 7,
                "course": course,
                "chapter": chapters[spec["chapter"]],
                "type": spec["type"],
                "difficulty": spec["difficulty"],
                "score": spec["score"],
                "answer": spec["answer"],
                "analysis": self._analysis(spec),
                "rubric": spec.get("rubric"),
                "scoring_mode": spec["scoring_mode"],
                "status": status,
                "creator": creator,
                "reviewer": admin if status == QuestionStatus.APPROVED else None,
                "reviewed_at": now if status == QuestionStatus.APPROVED else None,
                "review_comment": "演示数据自动审核通过" if status == QuestionStatus.APPROVED else None,
            }
            question, is_new = Question.objects.get_or_create(
                stem=spec["stem"], defaults=defaults
            )
            if not is_new:
                continue
            created += 1
            for index, option in enumerate(spec.get("options") or []):
                QuestionOption.objects.create(
                    question=question, key=option["key"], text=option["text"],
                    sort_order=index,
                )
        return created

    def _analysis(self, spec):
        qtype = spec["type"]
        answer = spec["answer"]
        if qtype in (QuestionType.SINGLE_CHOICE, QuestionType.LISTENING):
            return f"正确答案为 {answer.get('value')}。"
        if qtype == QuestionType.MULTIPLE_CHOICE:
            return f"正确选项为 {'、'.join(answer.get('values') or [])}。"
        if qtype == QuestionType.TRUE_FALSE:
            return "该说法正确。" if answer.get("value") else "该说法错误。"
        if qtype == QuestionType.FILL_BLANK:
            return f"应填写：{' / '.join(answer.get('values') or [])}。"
        return "参考要点见评分标准。"

    def _seed_reviews(self, admin):
        rules = [
            ("练耳训练通常包括哪些内容？", "approve", "分类清楚，予以通过。"),
            ("黄金分割比大约是多少？", "approve", "题目规范，予以通过。"),
            ("3/4拍属于复拍子。", "reject", "题干表述不严谨，请修改后重新提交。"),
        ]
        for stem, action, comment in rules:
            question = Question.objects.filter(
                stem=stem, status=QuestionStatus.PENDING
            ).first()
            if question is None:
                continue
            review_question(admin, question, action, comment)

    def _auto_paper(self, user, classroom, title, subject, course, rules):
        existing = Paper.objects.filter(
            creator=user, title=title, deleted_at__isnull=True
        ).first()
        if existing:
            return existing
        return create_auto_paper(user, {
            "title": title,
            "subject": subject,
            "paperType": PaperType.FORMAL,
            "grade": 7,
            "scopeType": ScopeType.CLASS,
            "scopeId": classroom.id,
            "duration": 45,
            "courseIds": [course.id],
            "rules": copy.deepcopy(rules),
            "status": PaperStatus.READY,
            "instructions": "自动组卷生成的演示试卷，请按题目要求作答。",
        })

    def _publish(self, user, classroom, title, paper, start, end, attempt_limit=1):
        existing = Assessment.objects.filter(
            title=title, publisher=user
        ).first()
        if existing:
            return existing
        return publish_assessment(user, {
            "paperId": paper.id,
            "title": title,
            "targetType": ScopeType.CLASS,
            "targetIds": [classroom.id],
            "startTime": start,
            "endTime": end,
            "attemptLimit": attempt_limit,
            "showAnswerMode": ShowAnswerMode.AFTER_END,
            "allowLateSubmit": False,
            "instructions": "演示测评，按课堂要求完成作答。",
        })

    def _seed_attempt(
        self, teacher, assessment, student, wrong_every, subjective_rate, finalize=True,
    ):
        if Attempt.objects.filter(assessment=assessment, student=student).exists():
            return None
        if not assessment.question_snapshot:
            return None
        started_at = assessment.end_time - timedelta(minutes=assessment.duration)
        attempt = Attempt.objects.create(
            assessment=assessment,
            paper=assessment.paper,
            student=student,
            attempt_no=1,
            questions_snapshot=copy.deepcopy(assessment.question_snapshot),
            status=AttemptStatus.IN_PROGRESS,
            started_at=started_at,
            deadline=assessment.end_time,
            grading_status=GradingStatus.PENDING,
        )
        rows = []
        for index, question in enumerate(assessment.question_snapshot, start=1):
            rows.append(AttemptAnswer(
                attempt=attempt,
                question_id=question["questionId"],
                order=question["order"],
                answer=self._student_answer(question, index, wrong_every),
                max_score=question.get("score", 0),
                scoring_mode=question.get("scoringMode", ScoringMode.AUTO),
            ))
        AttemptAnswer.objects.bulk_create(rows)
        submit_attempt(student, attempt, payload=None, auto=True, reason="seed_demo")
        attempt.refresh_from_db()
        if not finalize:
            return attempt
        items = [
            {
                "questionId": row.question_id,
                "score": round((row.max_score or 0) * subjective_rate, 1),
                "comment": "演示评分：要点基本完整。",
            }
            for row in attempt.answers.all()
            if row.scoring_mode != ScoringMode.AUTO
        ]
        if items and attempt.status != AttemptStatus.GRADED:
            submit_grading(teacher, attempt, {
                "items": items,
                "finalize": True,
                "reason": "演示数据自动评分",
            })
        return attempt

    def _student_answer(self, question, index, wrong_every):
        qtype = question.get("type")
        correct = question.get("answer") or {}
        wrong = wrong_every and index % wrong_every == 0
        if qtype == QuestionType.SHORT_ANSWER:
            return {"text": "结合课堂所学作答：先说明主要概念，再举一个作品或生活实例。"}
        if qtype in (QuestionType.SINGLE_CHOICE, QuestionType.LISTENING):
            value = correct.get("value")
            if wrong:
                keys = [o["key"] for o in question.get("options") or []]
                others = [k for k in keys if k != value]
                if others:
                    value = others[0]
            return {"value": value}
        if qtype == QuestionType.MULTIPLE_CHOICE:
            values = list(correct.get("values") or [])
            if wrong and len(values) > 1:
                values = values[:-1]
            elif wrong:
                values = []
            return {"values": values}
        if qtype == QuestionType.TRUE_FALSE:
            value = bool(correct.get("value"))
            return {"value": (not value) if wrong else value}
        if qtype == QuestionType.FILL_BLANK:
            values = list(correct.get("values") or [])
            return {"values": ["未掌握"] if wrong else values}
        return {}

    def _seed_certificates(self, teacher, teacher_art, music_a2, art_a1, student, student_a):
        created = 0
        for user, subject, assessment, target in (
            (teacher, MUSIC, music_a2, student),
            (teacher_art, ART, art_a1, student_a),
        ):
            if Certificate.objects.filter(
                assessment=assessment, student=target
            ).exists():
                continue
            try:
                generate_certificates(user, {
                    "assessmentId": assessment.id,
                    "subject": subject,
                    "studentIds": [target.id],
                })
            except Exception as exc:  # 证书 PDF 生成失败不影响其余演示数据
                self.stderr.write(
                    f"证书生成失败（{target.username}/{subject}）：{exc}"
                )
                continue
            if Certificate.objects.filter(
                assessment=assessment, student=target
            ).exists():
                created += 1
        return created

    ARTWORK_SPECS = [
        (0, "课外写生-校园一角.png", 11),
        (0, "水彩练习-秋日静物.png", 23),
        (1, "民间剪纸-窗花.png", 31),
        (1, "国画临摹-山水小品.png", 42),
        (2, "课外美术-色彩构成练习.png", 51),
        (2, "课外美术-人物速写.png", 62),
    ]

    def _seed_artworks(self, student_a, student_b, student, student2):
        from django.core.files.uploadedfile import SimpleUploadedFile

        students = (student_a, student_b, student, student2)
        created = 0
        for student_index, name, seed in self.ARTWORK_SPECS:
            uploader = students[student_index]
            if FileObject.objects.filter(
                category=FileCategory.STUDENT_WORK,
                uploader=uploader,
                original_name=name,
                deleted_at__isnull=True,
            ).exists():
                continue
            uploaded = SimpleUploadedFile(
                name, self._artwork_png(seed), content_type="image/png"
            )
            save_upload(
                uploaded, FileCategory.STUDENT_WORK, uploader, subject=ART
            )
            created += 1
        return created

    def _artwork_png(self, seed):
        import random
        from io import BytesIO

        from PIL import Image, ImageDraw

        palettes = [
            ((250, 214, 165), (120, 170, 200), (230, 140, 90), (80, 110, 160), (250, 240, 210)),
            ((245, 180, 110), (190, 90, 70), (250, 220, 150), (140, 60, 50), (255, 245, 220)),
            ((250, 235, 220), (200, 60, 60), (240, 180, 60), (120, 30, 40), (255, 250, 235)),
            ((238, 238, 230), (90, 100, 100), (40, 50, 60), (150, 160, 150), (250, 250, 245)),
        ]
        top, bottom, *accents = palettes[seed % len(palettes)]
        width, height = 960, 640
        rnd = random.Random(seed)
        image = Image.new("RGB", (width, height), top)
        draw = ImageDraw.Draw(image, "RGBA")
        for y in range(height):
            ratio = y / (height - 1)
            color = tuple(
                int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)
            )
            draw.line([(0, y), (width, y)], fill=color)
        for _ in range(26):
            x, y = rnd.randint(0, width), rnd.randint(0, height)
            radius = rnd.randint(18, 130)
            color = rnd.choice(accents) + (rnd.randint(45, 150),)
            draw.ellipse(
                [x - radius, y - radius, x + radius, y + radius], fill=color
            )
        for _ in range(10):
            points = [
                (rnd.randint(0, width), rnd.randint(0, height)) for _ in range(4)
            ]
            draw.line(
                points, fill=rnd.choice(accents) + (210,),
                width=rnd.randint(2, 6), joint="curve",
            )
        for _ in range(4):
            x, y = rnd.randint(0, width), rnd.randint(0, height)
            draw.rectangle(
                [x, y, x + rnd.randint(40, 200), y + rnd.randint(30, 160)],
                outline=rnd.choice(accents) + (180,), width=3,
            )
        buffer = BytesIO()
        image.save(buffer, "PNG")
        return buffer.getvalue()

    def _learning_report(self, student, subject):
        scores = list(
            Score.objects.filter(
                student=student, subject=subject, status=GradingStatus.GRADED,
                assessment__paper_type=PaperType.FORMAL,
            )
            .select_related("assessment")
            .order_by("assessment__end_time", "id")
        )
        if not scores:
            return False
        trend = [
            {
                "date": score.assessment.end_time.date().isoformat(),
                "score": round(score.total_score, 1),
            }
            for score in scores
        ]
        latest = trend[-1]["score"]
        first = trend[0]["score"]
        delta = latest - first
        if subject == MUSIC:
            strengths = ["节奏感较好", "歌曲演唱投入", "能听辨常见乐器音色"]
            weaknesses = ["识谱速度偏慢", "音准稳定性不足", "音乐术语掌握不牢"]
            suggestions = ["每天视唱 10 分钟", "用节拍器练习附点与切分节奏", "整理错题并复习乐理概念"]
            subject_name = "音乐"
        else:
            strengths = ["色彩感受敏锐", "构图意识较好", "能主动观察生活素材"]
            weaknesses = ["透视关系不够准确", "造型细节刻画不足", "美术史知识零散"]
            suggestions = ["每周完成一幅速写", "临摹优秀作品并分析构图", "建立美术史时间线笔记"]
            subject_name = "美术"
        summary = (
            f"{student.real_name}同学在{subject_name}学科最近一次测评中得分 {latest} 分，"
            f"较首次测评{'提升' if delta >= 0 else '下降'} {abs(round(delta, 1))} 分，"
            f"整体呈{'上升' if delta >= 0 else '波动'}趋势，建议继续保持练习节奏。"
        )
        raw_lines = [
            f"学情报告：{student.real_name} · {subject_name}",
            summary,
            "优势表现：" + "；".join(strengths),
            "需要加强：" + "；".join(weaknesses),
            "学习建议：" + "；".join(suggestions),
            "成绩趋势：" + "，".join(f"{p['date']} {p['score']}分" for p in trend),
        ]
        report_id = f"RPT-DEMO-{student.id}-{subject}"
        LearningReport.objects.update_or_create(
            report_id=report_id,
            defaults={
                "student": student,
                "subject": subject,
                "summary": summary,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "suggestions": suggestions,
                "score_trend": trend,
                "raw_text": "\n".join(raw_lines),
                "model_version": "demo-report-v1",
            },
        )
        return True
