"""按年级补充音乐 / 美术分层题库（1~9 年级，可重复执行）。

现有 `seed_question_bank` 只生成七年级题目。本命令为每个年级单独建课、
建章节，并按年级难度补充题目：

- 1~2 年级：难度 1，以听辨、模唱、认色、造型游戏为主；
- 3~4 年级：难度 2，加入简单乐理、色彩知识与基础技法；
- 5~6 年级：难度 3，涉及民族音乐、中国书画与设计；
- 7 年级：难度 3，补充教材曲目与中外美术作品；
- 8 年级：难度 4，侧重作品分析、风格比较；
- 9 年级：难度 5，涉及音乐流派、世界美术与综合鉴赏。

每个年级、每个学科默认补充：
- 30 道单选题
- 12 道多选题
- 3 道实践作品题（音乐 audio_upload / 美术 image_upload）

题目素材参考人教版小学、初中音乐教材目录与人美版美术教材目录，
题干与选项由结构化数据生成，不直接复制教辅原题。

用法：
    python manage.py seed_grade_question_bank
    python manage.py seed_grade_question_bank --grades 1-6
    python manage.py seed_grade_question_bank --grades 3,6,7,8 --subject music
"""
from __future__ import annotations

import random
import re
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.qbank.stem_cleaner import clean_stem

from apps.accounts.models import User
from apps.qbank.models import Chapter, Course, Question, QuestionOption
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

GRADE_NAMES = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九",
}

# 每个年级对应的难度等级（1 最简单，5 最难）。
GRADE_DIFFICULTY = {
    1: 1, 2: 1,
    3: 2, 4: 2,
    5: 3, 6: 3, 7: 3,
    8: 4,
    9: 4,
}

MUSIC_CHAPTERS = ["乐理基础", "视唱练耳", "音乐欣赏", "乐器与演奏"]
ART_CHAPTERS = ["造型基础", "色彩知识", "中国书画", "美术欣赏", "设计与工艺"]

DEFAULT_TARGETS = {
    QuestionType.SINGLE_CHOICE: 30,
    QuestionType.MULTIPLE_CHOICE: 12,
    QuestionType.SHORT_ANSWER: 0,
    QuestionType.IMAGE_UPLOAD: 3,
    QuestionType.AUDIO_UPLOAD: 3,
}

# 作品字段：(曲名/画名, 作者/曲作者, 国家/地区, 时期, 体裁/画种, 表演形式/材料, 情绪或画面)
MUSIC_GRADES = {
    1: {
        "works": [
            ("布谷", None, "中国", "传统", "儿歌", "演唱", "模仿布谷鸟叫声，活泼轻快"),
            ("大雨和小雨", None, "中国", "现代", "儿童歌曲", "演唱", "用强弱对比表现雨声"),
            ("国旗国旗真美丽", None, "中国", "现代", "儿童歌曲", "演唱", "庄严亲切"),
            ("两只小象", "汪玲", "中国", "现代", "儿童歌曲", "演唱", "活泼有童趣"),
            ("小蜻蜓", "钟立民", "中国", "现代", "儿童歌曲", "演唱", "轻盈优美"),
            ("新年好", None, "英国", "传统", "儿歌", "演唱", "节日欢快"),
            ("龙咚锵", None, "中国", "现代", "儿童歌曲", "演唱", "锣鼓节奏热闹"),
            ("小青蛙找家", None, "中国", "现代", "儿童歌曲", "演唱", "跳跃活泼"),
        ],
        "terms": [
            ("音高", "声音的高低", "乐理"),
            ("音值", "音的长短", "乐理"),
            ("音强", "声音的强弱", "乐理"),
            ("音色", "声音的独特品质", "乐理"),
            ("速度", "音乐进行的快慢", "乐理"),
            ("力度", "音乐音响的强弱程度", "乐理"),
            ("拍子", "音乐中强弱拍的循环", "节拍"),
            ("节奏", "音的长短与强弱的有规律组合", "节拍"),
        ],
        "themes": ["我的校园", "春天来了", "可爱的小动物"],
    },
    2: {
        "works": [
            ("小红帽", None, "巴西", "传统", "儿歌", "演唱", "轻快叙事"),
            ("数蛤蟆", None, "中国", "传统", "民歌", "演唱", "诙谐有趣"),
            ("理发师", None, "澳大利亚", "传统", "民歌", "演唱", "劳动节奏轻快"),
            ("大头娃娃", None, "中国", "现代", "儿童歌曲", "演唱", "欢快热闹"),
            ("动物说话", None, "中国", "现代", "儿童歌曲", "演唱", "模仿动物叫声"),
            ("冬天的故事", None, "中国", "现代", "儿童歌曲", "演唱", "安静柔和"),
            ("大风车", "孟卫东", "中国", "现代", "动画歌曲", "演唱", "欢快活泼"),
            ("娃哈哈", None, "中国", "传统", "民歌", "演唱", "欢快活泼"),
        ],
        "terms": [
            ("二分音符", "唱两拍的音符", "音符"),
            ("四分音符", "唱一拍的音符", "音符"),
            ("八分音符", "唱半拍的音符", "音符"),
            ("休止符", "表示停顿的记号", "符号"),
            ("小节", "由拍号划分的音乐单位", "节拍"),
            ("小节线", "划分小节的竖线", "符号"),
            ("高音谱号", "记录较高声音的谱号", "谱号"),
            ("低音谱号", "记录较低声音的谱号", "谱号"),
        ],
        "themes": ["我的家人", "海底世界", "快乐的节日"],
    },
    3: {
        "works": [
            ("茉莉花", None, "中国", "传统", "民歌", "演唱", "婉转优美"),
            ("让我们荡起双桨", "刘炽", "中国", "现代", "儿童歌曲", "合唱", "欢快舒展"),
            ("卖报歌", "聂耳", "中国", "近代", "儿童歌曲", "演唱", "活泼中带辛酸"),
            ("春天在哪里", "潘振声", "中国", "现代", "儿童歌曲", "演唱", "活泼明亮"),
            ("每当我走过老师窗前", "董希哲", "中国", "现代", "儿童歌曲", "演唱", "深情"),
            ("铃儿响叮当", "皮尔庞特", "美国", "近代", "歌曲", "演唱", "欢快"),
            ("外婆的澎湖湾", "叶佳修", "中国台湾", "现代", "校园歌曲", "演唱", "温暖怀旧"),
            ("捉泥鳅", "侯德健", "中国台湾", "现代", "校园歌曲", "演唱", "童趣"),
        ],
        "terms": [
            ("2/4拍", "以四分音符为一拍、每小节两拍", "拍号"),
            ("3/4拍", "以四分音符为一拍、每小节三拍", "拍号"),
            ("4/4拍", "以四分音符为一拍、每小节四拍", "拍号"),
            ("附点音符", "带有附点、时值延长一半的音符", "音符"),
            ("连音线", "连接相同音高音符的弧线", "符号"),
            ("延长记号", "表示自由延长的记号", "符号"),
            ("反复记号", "表示段落重复的记号", "符号"),
            ("弱起", "乐曲从小节的弱拍开始", "节拍"),
        ],
        "themes": ["美丽的家乡", "校园一角", "四季的色彩"],
    },
    4: {
        "works": [
            ("歌唱祖国", "王莘", "中国", "现代", "合唱歌曲", "合唱", "雄壮"),
            ("小小少年", None, "德国", "现代", "影视歌曲", "演唱", "明朗"),
            ("红蜻蜓", "山田耕筰", "日本", "近代", "儿童歌曲", "演唱", "怀旧"),
            ("故乡的亲人", "福斯特", "美国", "近代", "歌曲", "演唱", "思念"),
            ("忆江南", None, "中国", "现代", "古诗词歌曲", "演唱", "清新"),
            ("唱脸谱", "姚明", "中国", "现代", "戏歌", "演唱", "京剧韵味"),
            ("男儿当自强", "黄霑", "中国香港", "现代", "影视歌曲", "演唱", "豪迈"),
            ("上去高山望平川", None, "中国", "传统", "花儿", "演唱", "高亢"),
        ],
        "terms": [
            ("音名", "用字母表示音高的名称", "乐理"),
            ("唱名", "用 do re mi 等唱出的名称", "乐理"),
            ("音程", "两个音之间的距离", "乐理"),
            ("和弦", "三个以上音同时结合", "和声"),
            ("旋律", "按一定音高和节奏组织的音线", "乐理"),
            ("和声", "两个以上音同时结合形成的音响", "和声"),
            ("调式", "按照一定关系组织起来的音阶", "乐理"),
            ("转调", "乐曲中途改变调性", "乐理"),
        ],
        "themes": ["我的好朋友", "家乡的风景", "有趣的民间艺术"],
    },
    5: {
        "works": [
            ("我的中国心", "黄霑", "中国香港", "现代", "歌曲", "演唱", "深情"),
            ("春天的故事", "王佑贵", "中国", "现代", "歌曲", "演唱", "深情"),
            ("东方之珠", "罗大佑", "中国香港", "现代", "歌曲", "演唱", "温暖"),
            ("赛马", "黄海怀", "中国", "现代", "二胡独奏曲", "二胡", "热烈奔放"),
            ("天堂", "腾格尔", "中国", "现代", "歌曲", "演唱", "辽阔"),
            ("牧歌", None, "中国", "传统", "长调", "演唱", "悠远"),
            ("渔舟唱晚", "娄树华", "中国", "现代", "古筝曲", "古筝", "宁静"),
            ("瑶族舞曲", "刘铁山、茅沅", "中国", "现代", "管弦乐", "管弦乐", "欢腾"),
        ],
        "terms": [
            ("民族管弦乐", "由民族乐器组成的大型合奏", "器乐"),
            ("西洋管弦乐", "由西洋乐器组成的大型合奏", "器乐"),
            ("吹奏乐器", "靠气流发声的乐器", "乐器"),
            ("拉弦乐器", "靠弓摩擦弦发声的乐器", "乐器"),
            ("弹拨乐器", "靠拨动弦发声的乐器", "乐器"),
            ("打击乐器", "靠敲击发声的乐器", "乐器"),
            ("独奏", "一件乐器单独演奏", "演奏形式"),
            ("合奏", "多件乐器共同演奏", "演奏形式"),
        ],
        "themes": ["美丽的校园", "低碳生活", "中国梦"],
    },
    6: {
        "works": [
            ("我的祖国", "刘炽", "中国", "现代", "合唱歌曲", "合唱", "深情"),
            ("爱我中华", "徐沛东", "中国", "现代", "歌曲", "演唱", "欢快"),
            ("友谊地久天长", None, "英国", "传统", "民歌", "合唱", "深情"),
            ("明天会更好", "罗大佑", "中国台湾", "现代", "流行歌曲", "合唱", "温暖"),
            ("关山月", None, "中国", "古代", "古琴曲", "古琴", "苍凉"),
            ("游子吟", None, "中国", "现代", "古诗词歌曲", "演唱", "深情"),
            ("阿里山的姑娘", None, "中国台湾", "传统", "民歌", "演唱", "欢快"),
            ("二泉映月", "华彦钧", "中国", "近代", "二胡曲", "二胡", "深沉"),
        ],
        "terms": [
            ("合唱", "多声部集体演唱", "声乐形式"),
            ("齐唱", "多人同唱一个声部", "声乐形式"),
            ("轮唱", "不同声部先后进入演唱同一旋律", "声乐形式"),
            ("领唱", "由一人先唱或主唱", "声乐形式"),
            ("咏叹调", "歌剧中抒情性的独唱曲", "歌剧"),
            ("宣叙调", "歌剧中近似说话的演唱", "歌剧"),
            ("序曲", "歌剧或大型作品开头的器乐曲", "体裁"),
            ("间奏曲", "幕间演奏的器乐曲", "体裁"),
        ],
        "themes": ["我的未来", "传统文化", "美丽的家乡"],
    },
    7: {
        "works": [
            ("中学时代", "戴于吾", "中国", "现代", "校园歌曲", "演唱", "青春"),
            ("飞来的花瓣", "瞿希贤", "中国", "现代", "合唱", "合唱", "深情"),
            ("校园的早晨", "谷建芬", "中国", "现代", "校园歌曲", "演唱", "清新"),
            ("西风的话", "黄自", "中国", "近代", "艺术歌曲", "演唱", "抒情"),
            ("黄河船夫曲", "冼星海", "中国", "近代", "合唱", "合唱", "雄壮"),
            ("樱花", None, "日本", "传统", "民歌", "演唱", "柔美"),
            ("渴望春天", "莫扎特", "奥地利", "古典主义", "艺术歌曲", "演唱", "明朗"),
            ("桑塔露琪亚", None, "意大利", "传统", "船歌", "演唱", "舒展"),
        ],
        "terms": [
            ("交响曲", "由管弦乐队演奏的多乐章大型作品", "体裁"),
            ("协奏曲", "独奏乐器与乐队竞奏的大型作品", "体裁"),
            ("奏鸣曲", "由几个乐章组成的器乐作品", "体裁"),
            ("室内乐", "少数乐器在室内演奏的乐曲", "体裁"),
            ("圆舞曲", "三拍子、旋转感强的舞曲", "体裁"),
            ("进行曲", "节奏方整、适合行进的乐曲", "体裁"),
            ("管弦乐队", "由多种西洋乐器组成的大型乐队", "器乐"),
            ("指挥", "统一乐队演奏速度与力度的人", "器乐"),
        ],
        "themes": ["校园生活", "青春", "家乡印象"],
    },
    8: {
        "works": [
            ("青春舞曲", "王洛宾", "中国", "现代", "民歌", "演唱", "欢快"),
            ("洪湖水，浪打浪", "张敬安、欧阳谦叔", "中国", "现代", "歌剧选曲", "演唱", "优美"),
            ("红河谷", None, "加拿大", "传统", "民歌", "演唱", "宽广"),
            ("阳关三叠", None, "中国", "古代", "古琴歌", "演唱", "苍凉"),
            ("在那遥远的地方", "王洛宾", "中国", "现代", "民歌", "演唱", "深情"),
            ("半个月亮爬上来", "王洛宾", "中国", "现代", "无伴奏合唱", "合唱", "静谧"),
            ("化蝶", "何占豪、陈钢", "中国", "现代", "小提琴协奏曲", "小提琴与乐队", "凄美"),
            ("我的未来不是梦", "翁孝良", "中国台湾", "现代", "流行歌曲", "演唱", "励志"),
        ],
        "terms": [
            ("歌剧", "综合音乐、戏剧、舞台美术的艺术形式", "戏剧音乐"),
            ("音乐剧", "融合歌唱、舞蹈、戏剧的舞台艺术", "戏剧音乐"),
            ("舞剧", "以舞蹈为主要表现手段的戏剧", "戏剧音乐"),
            ("清唱剧", "由独唱、合唱与乐队表演的大型声乐作品", "体裁"),
            ("康塔塔", "包含独唱、合唱与乐队的大型声乐作品", "体裁"),
            ("艺术歌曲", "诗歌与音乐结合、伴奏讲究的歌曲", "体裁"),
            ("民歌", "在民间广泛流传的歌曲", "民间音乐"),
            ("号子", "伴随体力劳动演唱的民歌", "民间音乐"),
        ],
        "themes": ["责任与担当", "传统文化", "美丽的自然"],
    },
    9: {
        "works": [
            ("保卫黄河", "冼星海", "中国", "近代", "合唱", "合唱", "激昂"),
            ("游击队歌", "贺绿汀", "中国", "近代", "合唱", "合唱", "机智豪迈"),
            ("中国人民解放军军歌", "郑律成", "中国", "现代", "进行曲", "合唱", "雄壮"),
            ("命运交响曲", "贝多芬", "德国", "古典主义", "交响曲", "管弦乐", "激昂"),
            ("第九交响曲", "贝多芬", "德国", "古典主义", "交响曲", "管弦乐与合唱", "宏大"),
            ("念故乡", "德沃夏克", "捷克", "民族乐派", "交响曲选段", "管弦乐", "思乡"),
            ("卡门", "比才", "法国", "浪漫主义", "歌剧", "声乐与管弦乐", "热烈"),
            ("天鹅湖", "柴可夫斯基", "俄罗斯", "浪漫主义", "芭蕾舞剧", "管弦乐", "优美"),
        ],
        "terms": [
            ("古典主义音乐", "18 世纪以海顿、莫扎特、贝多芬为代表的音乐", "流派"),
            ("浪漫主义音乐", "19 世纪强调情感与个性的音乐", "流派"),
            ("民族乐派", "19 世纪强调本民族音乐语言的流派", "流派"),
            ("印象主义音乐", "注重色彩与光影感觉的音乐", "流派"),
            ("现代主义音乐", "20 世纪突破传统的音乐", "流派"),
            ("十二音体系", "勋伯格创立的无调性作曲方法", "作曲技法"),
            ("复调", "两个以上旋律同时进行的音乐", "织体"),
            ("主调音乐", "一个主旋律加伴奏的音乐", "织体"),
        ],
        "themes": ["时代与青春", "美术与生活", "我的梦想"],
    },
}

ART_GRADES = {
    1: {
        "works": [
            ("向日葵", "梵高", "荷兰", "后印象派", "油画", "油画", "明亮的黄色花朵"),
            ("星月夜", "梵高", "荷兰", "后印象派", "油画", "油画", "旋转的星空"),
            ("蒙娜丽莎", "达·芬奇", "意大利", "文艺复兴", "肖像画", "油画", "神秘微笑"),
            ("虾", "齐白石", "中国", "现代", "中国画", "水墨", "透明灵动"),
            ("奔马", "徐悲鸿", "中国", "现代", "中国画", "水墨", "矫健有力"),
            ("清明上河图", "张择端", "中国", "北宋", "风俗画", "绢本设色", "繁华市井"),
            ("千里江山图", "王希孟", "中国", "北宋", "青绿山水", "绢本设色", "青绿壮阔"),
            ("剪纸团花", None, "中国", "传统", "剪纸", "纸", "对称吉祥"),
        ],
        "terms": [
            ("三原色", "红、黄、蓝三种不能由其他颜色调出的颜色", "色彩"),
            ("三间色", "橙、绿、紫三种由原色调配的颜色", "色彩"),
            ("线条", "绘画中表示轮廓和方向的痕迹", "造型"),
            ("形状", "物体外轮廓呈现的样子", "造型"),
            ("圆形", "到中心距离相等的封闭图形", "形状"),
            ("方形", "四条边相等、四个角是直角的图形", "形状"),
            ("三角形", "由三条边围成的图形", "形状"),
            ("对称", "图形沿一条线对折后两边重合", "形式"),
        ],
        "themes": ["我的校园", "春天来了", "可爱的小动物"],
    },
    2: {
        "works": [
            ("睡莲", "莫奈", "法国", "印象派", "油画", "油画", "光影变化"),
            ("日出·印象", "莫奈", "法国", "印象派", "油画", "油画", "晨雾港口"),
            ("舞蹈", "马蒂斯", "法国", "野兽派", "油画", "油画", "手拉手起舞"),
            ("呐喊", "蒙克", "挪威", "表现主义", "油画", "油画", "夸张不安"),
            ("记忆的永恒", "达利", "西班牙", "超现实主义", "油画", "油画", "融化的钟表"),
            ("墨竹图", "郑板桥", "中国", "清代", "中国画", "水墨", "挺拔有节"),
            ("墨葡萄图", "徐渭", "中国", "明代", "写意花鸟", "水墨", "淋漓酣畅"),
            ("捣练图", "张萱", "中国", "唐代", "仕女画", "绢本设色", "捣练劳作"),
        ],
        "terms": [
            ("暖色", "红、橙、黄等给人温暖感觉的颜色", "色彩"),
            ("冷色", "蓝、绿、紫等给人凉爽感觉的颜色", "色彩"),
            ("深浅", "同一种颜色的明暗变化", "色彩"),
            ("疏密", "线条或点排列的稀疏与紧密", "构图"),
            ("剪纸", "用剪刀或刻刀在纸上镂空造型的民间艺术", "民间美术"),
            ("团花", "折叠后剪出的四周对称图案", "民间美术"),
            ("折剪", "将纸折叠后再剪的方法", "技法"),
            ("头饰", "戴在头上的装饰品", "设计"),
        ],
        "themes": ["我的家人", "海底世界", "快乐的节日"],
    },
    3: {
        "works": [
            ("开国大典", "董希文", "中国", "现代", "油画", "油画", "庄严热烈"),
            ("父亲", "罗中立", "中国", "现代", "油画", "油画", "质朴深沉"),
            ("狼牙山五壮士", "詹建俊", "中国", "现代", "油画", "油画", "悲壮"),
            ("富春山居图", "黄公望", "中国", "元代", "山水画", "水墨", "悠远"),
            ("溪山行旅图", "范宽", "中国", "北宋", "山水画", "水墨", "雄浑"),
            ("步辇图", "阎立本", "中国", "唐代", "人物画", "绢本设色", "历史场景"),
            ("春如线", "吴冠中", "中国", "现代", "中国画", "水墨", "抽象线条"),
            ("杨柳青年画", None, "中国", "传统", "年画", "木版套色", "喜庆吉祥"),
        ],
        "terms": [
            ("色彩滴染", "让颜色在纸上自然渗化的方法", "技法"),
            ("水墨画", "用水墨在宣纸上作画的中国画形式", "中国画"),
            ("中国画", "用毛笔、墨和中国画颜料作画", "中国画"),
            ("文房四宝", "笔、墨、纸、砚", "中国画工具"),
            ("连环画", "用多幅画面连续叙述故事的绘画", "绘画"),
            ("吉祥图案", "用谐音或象征表达美好愿望的图案", "民间美术"),
            ("农民画", "农民创作、色彩鲜艳的民间绘画", "民间美术"),
            ("装饰画", "以装饰为目的、造型色彩夸张的绘画", "绘画"),
        ],
        "themes": ["美丽的家乡", "校园一角", "四季的色彩"],
    },
    4: {
        "works": [
            ("最后的晚餐", "达·芬奇", "意大利", "文艺复兴", "壁画", "湿壁画", "人物排列"),
            ("大卫", "米开朗基罗", "意大利", "文艺复兴", "雕塑", "大理石", "健美有力"),
            ("思想者", "罗丹", "法国", "近代", "雕塑", "青铜", "沉思"),
            ("维纳斯", None, "希腊", "古代", "雕塑", "大理石", "优美"),
            ("秦始皇兵马俑", None, "中国", "秦代", "雕塑", "陶", "威武"),
            ("敦煌莫高窟壁画", None, "中国", "古代", "壁画", "彩绘", "飞天"),
            ("五牛图", "韩滉", "中国", "唐代", "动物画", "纸本设色", "憨厚"),
            ("青花瓷", None, "中国", "明清", "瓷器", "瓷", "蓝白纹样"),
        ],
        "terms": [
            ("透视", "在平面上表现立体空间的方法", "造型"),
            ("视平线", "眼睛平视时看到的地平线", "透视"),
            ("消失点", "透视线汇聚的点", "透视"),
            ("写生", "直接面对实物或风景作画", "技法"),
            ("素描", "用单色线条和明暗表现对象的绘画", "绘画"),
            ("速写", "快速记录对象形态的绘画", "绘画"),
            ("暖色", "红、橙、黄等温暖感觉的颜色", "色彩"),
            ("冷色", "蓝、绿、紫等凉爽感觉的颜色", "色彩"),
        ],
        "themes": ["我的好朋友", "家乡的风景", "有趣的民间艺术"],
    },
    5: {
        "works": [
            ("兰竹图", "郑板桥", "中国", "清代", "中国画", "水墨", "清雅"),
            ("墨梅图", "王冕", "中国", "元代", "花鸟画", "水墨", "清逸"),
            ("荷花", "张大千", "中国", "现代", "中国画", "泼墨泼彩", "酣畅"),
            ("江山如此多娇", "傅抱石、关山月", "中国", "现代", "山水画", "设色", "壮阔"),
            ("九方皋", "徐悲鸿", "中国", "现代", "中国画", "水墨", "相马"),
            ("塔吉克新娘", "靳尚谊", "中国", "现代", "油画", "油画", "端庄"),
            ("格尔尼卡", "毕加索", "西班牙", "现代主义", "油画", "油画", "反战"),
            ("红黄蓝的构成", "蒙德里安", "荷兰", "风格派", "油画", "油画", "几何抽象"),
        ],
        "terms": [
            ("明度", "颜色的明暗程度", "色彩"),
            ("纯度", "颜色的鲜艳程度", "色彩"),
            ("对比色", "色相差异大、并置时对比强烈的颜色", "色彩"),
            ("邻近色", "色相接近、容易协调的颜色", "色彩"),
            ("调和色", "加入共同成分后容易和谐的颜色", "色彩"),
            ("写意", "用简练笔墨表现对象神韵的中国画技法", "中国画"),
            ("工笔", "用细致笔法层层描绘的中国画技法", "中国画"),
            ("皴法", "表现山石纹理的中国画技法", "中国画"),
        ],
        "themes": ["美丽的校园", "低碳生活", "中国梦"],
    },
    6: {
        "works": [
            ("长城", None, "中国", "古代", "建筑", "砖石", "依山蜿蜒，气势雄伟"),
            ("故宫", None, "中国", "明清", "建筑", "木结构", "中轴对称，庄严恢宏"),
            ("赵州桥", "李春", "中国", "隋代", "建筑", "石", "单孔石拱，造型优美"),
            ("埃菲尔铁塔", "埃菲尔", "法国", "近代", "建筑", "钢铁", "钢铁结构，高耸挺拔"),
            ("悉尼歌剧院", "约恩·乌松", "丹麦", "现代", "建筑", "混凝土与玻璃", "帆船造型，临海而立"),
            ("金字塔", None, "埃及", "古代", "建筑", "石", "方锥形巨石建筑，宏伟稳定"),
            ("中国结", None, "中国", "传统", "编结", "绳", "绳线回环，对称吉祥"),
            ("篆刻印章", None, "中国", "传统", "篆刻", "石", "方寸之间，朱白相映"),
        ],
        "terms": [
            ("装饰色彩", "经过概括夸张、强调装饰效果的色彩", "色彩"),
            ("民间美术", "劳动人民创造并流传的美术形式", "民间美术"),
            ("年画", "春节张贴、寓意吉祥的民间绘画", "民间美术"),
            ("雕塑", "用雕刻或塑造方法制作立体的艺术形象", "雕塑"),
            ("浮雕", "在平面上凸起形象的雕塑", "雕塑"),
            ("圆雕", "可从四面观赏的立体雕塑", "雕塑"),
            ("建筑", "供人居住和活动的空间艺术", "建筑"),
            ("篆刻", "用刻刀在石料上刻字的传统艺术", "书法篆刻"),
        ],
        "themes": ["我的未来", "传统文化", "美丽的家乡"],
    },
    7: {
        "works": [
            ("掷铁饼者", "米隆", "希腊", "古代", "雕塑", "大理石", "动感"),
            ("萨莫色雷斯的胜利女神", None, "希腊", "古代", "雕塑", "大理石", "展翅"),
            ("司母戊鼎", None, "中国", "商代", "青铜器", "青铜", "厚重"),
            ("莲鹤方壶", None, "中国", "春秋", "青铜器", "青铜", "灵动"),
            ("马踏飞燕", None, "中国", "东汉", "青铜雕塑", "青铜", "奔放"),
            ("韩熙载夜宴图", "顾闳中", "中国", "五代", "人物画", "绢本设色", "叙事"),
            ("渔庄秋霁图", "倪瓒", "中国", "元代", "山水画", "水墨", "疏淡"),
            ("泼墨仙人图", "梁楷", "中国", "南宋", "写意人物", "水墨", "简练"),
        ],
        "terms": [
            ("美术", "用视觉形象表达思想感情的艺术", "总论"),
            ("造型", "通过形状、色彩、材质塑造形象", "总论"),
            ("构图", "在画面中安排形象的位置和关系", "构图"),
            ("黄金分割", "约为 1:1.618 的经典比例", "构图"),
            ("均衡", "画面左右上下在视觉上保持平衡", "构图"),
            ("对比", "大小、虚实、冷暖等差异的并置", "构图"),
            ("节奏", "形象重复、渐变产生的韵律感", "构图"),
            ("肌理", "物体表面的纹理质感", "造型"),
        ],
        "themes": ["校园生活", "青春", "家乡印象"],
    },
    8: {
        "works": [
            ("春", "波提切利", "意大利", "文艺复兴", "油画", "蛋彩", "优美"),
            ("维纳斯的诞生", "波提切利", "意大利", "文艺复兴", "油画", "蛋彩", "贝壳"),
            ("西斯廷圣母", "拉斐尔", "意大利", "文艺复兴", "油画", "油画", "圣洁"),
            ("雅典学院", "拉斐尔", "意大利", "文艺复兴", "壁画", "湿壁画", "群像"),
            ("创世纪", "米开朗基罗", "意大利", "文艺复兴", "壁画", "湿壁画", "宏伟"),
            ("夜巡", "伦勃朗", "荷兰", "巴洛克", "油画", "油画", "光影"),
            ("戴珍珠耳环的少女", "维米尔", "荷兰", "巴洛克", "油画", "油画", "回眸"),
            ("自由引导人民", "德拉克洛瓦", "法国", "浪漫主义", "油画", "油画", "革命"),
        ],
        "terms": [
            ("山水画", "以山川自然景色为题材的中国画", "中国画"),
            ("花鸟画", "以花卉鸟虫为题材的中国画", "中国画"),
            ("人物画", "以人物为题材的中国画", "中国画"),
            ("工笔重彩", "精细描绘并施以浓重色彩的中国画", "中国画"),
            ("白描", "只用墨线勾勒不施色彩的中国画技法", "中国画"),
            ("泼墨", "墨色淋漓、笔势奔放的技法", "中国画"),
            ("书法", "用毛笔书写汉字的艺术", "书法篆刻"),
            ("篆书", "汉字古老的书体之一", "书法篆刻"),
        ],
        "themes": ["责任与担当", "传统文化", "美丽的自然"],
    },
    9: {
        "works": [
            ("亚维农少女", "毕加索", "西班牙", "现代主义", "油画", "油画", "立体主义"),
            ("百老汇爵士乐", "蒙德里安", "荷兰", "风格派", "油画", "油画", "几何"),
            ("吻", "克里姆特", "奥地利", "分离派", "油画", "油画", "金色"),
            ("构成第八号", "康定斯基", "俄罗斯", "抽象主义", "油画", "油画", "抽象"),
            ("内战的预感", "达利", "西班牙", "超现实主义", "油画", "油画", "怪诞"),
            ("玛丽莲·梦露", "安迪·沃霍尔", "美国", "波普艺术", "版画", "丝网印刷", "重复"),
            ("麦田群鸦", "梵高", "荷兰", "后印象派", "油画", "油画", "压抑"),
            ("人民英雄纪念碑浮雕", "刘开渠等", "中国", "现代", "浮雕", "石", "庄严"),
        ],
        "terms": [
            ("文艺复兴", "14~16 世纪欧洲思想文化运动", "美术史"),
            ("巴洛克", "17 世纪强调动势与光影的艺术风格", "美术史"),
            ("浪漫主义", "19 世纪强调情感与想象的艺术流派", "美术史"),
            ("现实主义", "19 世纪关注现实生活的艺术流派", "美术史"),
            ("印象派", "19 世纪注重光色瞬间印象的流派", "美术史"),
            ("后印象派", "19 世纪末强调主观表现的流派", "美术史"),
            ("立体主义", "20 世纪初把对象分解重构的流派", "美术史"),
            ("超现实主义", "20 世纪表现梦境与潜意识的流派", "美术史"),
        ],
        "themes": ["时代与青春", "美术与生活", "我的梦想"],
    },
}

MUSIC_CREATOR_FALLBACK = [
    "聂耳", "冼星海", "黄自", "刘炽", "谷建芬", "贝多芬", "莫扎特", "柴可夫斯基",
]
MUSIC_COUNTRY_FALLBACK = ["中国", "德国", "奥地利", "法国", "意大利", "俄罗斯", "美国", "日本"]
MUSIC_PERIOD_FALLBACK = ["古代", "近代", "现代", "巴洛克", "古典主义", "浪漫主义"]
MUSIC_GENRE_FALLBACK = ["民歌", "儿歌", "艺术歌曲", "合唱", "进行曲", "圆舞曲", "交响曲", "歌剧"]
MUSIC_MEDIUM_FALLBACK = ["演唱", "合唱", "钢琴", "二胡", "古筝", "管弦乐", "民族管弦乐"]
MUSIC_NOTE_FALLBACK = ["欢快活泼", "抒情优美", "雄壮有力", "安静柔和", "诙谐有趣", "热烈奔放"]
MUSIC_CATEGORY_FALLBACK = ["乐理", "节拍", "音符", "符号", "谱号", "器乐", "体裁"]
MUSIC_TERM_FALLBACK = [
    ("音高", "声音的高低"), ("节奏", "音的长短与强弱的有规律组合"),
    ("旋律", "按一定音高和节奏组织的音线"), ("和声", "两个以上音同时结合形成的音响"),
    ("力度", "音乐音响的强弱程度"), ("速度", "音乐进行的快慢"),
]

ART_CREATOR_FALLBACK = [
    "齐白石", "徐悲鸿", "张大千", "吴冠中", "梵高", "莫奈", "毕加索", "达·芬奇",
]
ART_COUNTRY_FALLBACK = ["中国", "意大利", "法国", "荷兰", "西班牙", "德国", "英国", "美国"]
ART_PERIOD_FALLBACK = ["古代", "文艺复兴", "巴洛克", "浪漫主义", "印象派", "现代"]
ART_GENRE_FALLBACK = ["油画", "中国画", "水彩画", "版画", "雕塑", "壁画", "建筑", "剪纸"]
ART_MEDIUM_FALLBACK = ["油画", "水墨", "水彩", "铅笔", "大理石", "青铜", "纸", "陶瓷"]
ART_NOTE_FALLBACK = ["色彩鲜明", "构图饱满", "笔触细腻", "气势雄浑", "气氛宁静", "形象夸张"]
ART_CATEGORY_FALLBACK = ["造型", "色彩", "构图", "中国画", "民间美术", "雕塑", "建筑"]
ART_TERM_FALLBACK = [
    ("三原色", "红、黄、蓝三种不能由其他颜色调出的颜色"),
    ("明度", "颜色的明暗程度"),
    ("构图", "在画面中安排形象的位置和关系"),
    ("工笔", "用细致笔法层层描绘的中国画技法"),
    ("篆刻", "用刻刀在石料上刻字的传统艺术"),
    ("透视", "在平面上表现立体空间的方法"),
]

CHAPTER_FOCUS = {
    MUSIC: {
        "乐理基础": "认识音符、节拍、谱号与常用音乐记号",
        "视唱练耳": "练习音准、节奏模仿与听辨",
        "音乐欣赏": "聆听中外优秀作品，学会描述情绪与画面",
        "乐器与演奏": "认识常见乐器与独奏、合奏等演奏形式",
    },
    ART: {
        "造型基础": "用线条、形状与明暗表现对象",
        "色彩知识": "认识色彩关系，学会调色与搭配",
        "中国书画": "了解毛笔、墨与宣纸，体验中国画笔墨",
        "美术欣赏": "从题材、形式与风格欣赏美术作品",
        "设计与工艺": "用纸、泥和废旧材料进行设计与制作",
    },
}

BAND_FOCUS = {
    1: "以游戏、模仿和直观感受为主",
    2: "以游戏、模仿和直观感受为主",
    3: "在观察与体验中掌握基本方法",
    4: "在观察与体验中掌握基本方法",
    5: "尝试综合运用，表达自己的感受",
    6: "尝试综合运用，表达自己的感受",
    7: "系统学习基础知识与技能",
    8: "注重作品分析、风格比较与创意表达",
    9: "注重作品分析、风格比较与创意表达",
}

# 低年级与高年级的章节重点不同，避免一年级看到“谱号、调式”等超前内容。
BAND_CHAPTER_FOCUS = {
    (MUSIC, "low"): {
        "乐理基础": "感受声音的高低、长短、强弱、快慢",
        "视唱练耳": "模唱简单旋律，模仿生活中的节奏",
        "音乐欣赏": "听辨音乐情绪，说说联想到的画面",
        "乐器与演奏": "认识常见打击乐器与课堂乐器",
    },
    (MUSIC, "high"): {
        "乐理基础": "理解调式、和声、曲式等较深入的知识",
        "视唱练耳": "进行多声部听辨与较复杂节奏练习",
        "音乐欣赏": "分析作品结构、风格与文化背景",
        "乐器与演奏": "了解管弦乐队编制与乐器音色",
    },
    (ART, "low"): {
        "造型基础": "用线条、形状画一画看到的事物",
        "色彩知识": "认识三原色与生活中的常见颜色",
        "中国书画": "认识毛笔、墨、宣纸，做水墨游戏",
        "美术欣赏": "看一看、说一说喜欢的作品",
        "设计与工艺": "用纸和废旧材料做简单手工",
    },
    (ART, "high"): {
        "造型基础": "学习比例、透视、明暗与空间表现",
        "色彩知识": "理解色彩情感、色调与配色方法",
        "中国书画": "体会山水、花鸟、书法的笔墨与章法",
        "美术欣赏": "比较中外美术流派与代表作品",
        "设计与工艺": "了解设计流程、材料与功能的关系",
    },
}


def _unique(values):
    result = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return result


SONG_GENRES = {
    "儿歌", "儿童歌曲", "歌曲", "动画歌曲", "民歌", "艺术歌曲", "流行歌曲",
    "影视歌曲", "校园歌曲", "古诗词歌曲", "戏歌", "船歌", "长调", "花儿",
    "合唱歌曲", "无伴奏合唱",
}

GENRE_GROUPS = [
    {"儿歌", "儿童歌曲", "动画歌曲"},
    {"民歌", "长调", "花儿", "船歌"},
    {"合唱", "合唱歌曲", "无伴奏合唱"},
    {"歌剧", "歌剧选曲", "芭蕾舞剧", "音乐剧"},
    {"交响曲", "交响曲选段"},
    {"进行曲", "军歌"},
    {"中国画", "山水画", "花鸟画", "人物画", "写意花鸟", "写意人物", "仕女画", "风俗画", "青绿山水"},
    {"油画", "肖像画"},
    {"雕塑", "浮雕", "圆雕", "青铜雕塑"},
    {"剪纸", "年画", "瓷器", "编结", "篆刻", "青铜器"},
]

PERIOD_GROUPS = [
    {"现代主义", "超现实主义", "立体主义", "风格派", "分离派", "抽象主义", "波普艺术", "表现主义"},
    {"现代", "现代主义"},
    {"传统", "古代"},
    {"印象派", "后印象派"},
    {"明代", "清代", "明清"},
]

CATEGORY_GROUPS = [
    {"拍号", "节拍"},
    {"音符", "符号"},
    {"器乐", "乐器"},
    {"中国画", "绘画", "民间美术"},
]

MEDIUM_GROUPS = [
    {"演唱", "合唱", "齐唱", "独唱", "无伴奏合唱"},
    {"管弦乐", "民族管弦乐"},
    {"水墨", "纸", "绢本设色", "纸本设色", "彩绘"},
    {"大理石", "石"},
    {"砖石", "石"},
]

NOTE_GROUPS = [
    {"雄伟", "宏伟", "壮阔", "雄浑", "气势雄浑"},
    {"欢快", "欢快活泼", "活泼", "活泼明亮", "轻快", "轻快叙事", "跳跃活泼", "童趣", "活泼有童趣", "节日欢快", "热闹", "欢腾"},
    {"深情", "温暖", "温暖怀旧", "抒情", "抒情优美", "优美", "柔美", "婉转优美", "清雅", "清逸", "清新", "明朗"},
    {"宁静", "安静柔和", "安静悠闲", "静谧", "悠远", "舒展", "宽广"},
    {"热烈", "热烈奔放", "激昂", "雄壮", "豪迈", "机智豪迈", "庄严", "庄严热烈", "庄严亲切", "悲壮"},
    {"深沉", "压抑", "苍凉", "凄美", "思念", "怀旧"},
]


def _in_same_group(groups, left, right):
    return any(left in group and right in group for group in groups)


def _genre_conflicts(correct, candidate):
    if correct == candidate:
        return True
    if _in_same_group(GENRE_GROUPS, correct, candidate):
        return True
    # “歌曲”是上位概念，不能作为具体歌曲体裁的干扰项。
    if candidate == "歌曲" and correct in SONG_GENRES:
        return True
    if correct == "歌曲" and candidate in SONG_GENRES:
        return True
    return False


def _period_conflicts(correct, candidate):
    return correct == candidate or _in_same_group(PERIOD_GROUPS, correct, candidate)


def _category_conflicts(correct, candidate):
    return correct == candidate or _in_same_group(CATEGORY_GROUPS, correct, candidate)


def _medium_conflicts(correct, candidate):
    if correct == candidate or _in_same_group(MEDIUM_GROUPS, correct, candidate):
        return True
    # “管弦乐与合唱”包含“管弦乐”“合唱”，不能互相作为错误选项。
    correct_parts = {part for part in re.split(r"[与、]", correct) if part}
    candidate_parts = {part for part in re.split(r"[与、]", candidate) if part}
    return bool(correct_parts & candidate_parts)


def _note_conflicts(correct, candidate):
    return correct == candidate or _in_same_group(NOTE_GROUPS, correct, candidate)


def _country_conflicts(correct, candidate):
    if correct == candidate:
        return True
    # 台湾、香港、澳门属于中国；避免把“中国”当作错误选项。
    if correct in {"中国台湾", "中国香港", "中国澳门"} and candidate == "中国":
        return True
    return False


def _others(pool, correct, fallback, count=3, conflicts=None):
    """从同类数据中取不等于正确答案的干扰项，不足时用兜底数据补齐。"""
    result = []
    for value in [*pool, *fallback]:
        text = str(value).strip() if value is not None else ""
        if not text or text in result:
            continue
        if conflicts and conflicts(str(correct).strip(), text):
            continue
        result.append(text)
        if len(result) >= count:
            break
    return result


def _option_pairs(correct, wrongs, seed, min_correct=1, max_options=6):
    texts = _unique([*correct, *wrongs])
    if len(texts) < 4 or len(texts) > max_options:
        texts = texts[:max_options]
    correct_set = {str(item).strip() for item in correct}
    if len([text for text in texts if text in correct_set]) < min_correct:
        return None
    if len(texts) < 4:
        return None
    rng = random.Random(sum(ord(char) for char in seed) + len(seed))
    rng.shuffle(texts)
    pairs = [(KEYS[index], text) for index, text in enumerate(texts)]
    answer = [key for key, text in pairs if text in correct_set]
    if len(answer) < min_correct:
        return None
    return pairs, answer


def _statements(work, works):
    """生成关于某件作品的正确说法与错误说法。"""
    title, creator, country, _period, genre, medium, _note = work
    true = []
    if creator:
        true.append(f"《{title}》的创作者是{creator}")
    true.append(f"《{title}》属于{genre}")
    true.append(f"《{title}》来自{country}")
    true.append(f"《{title}》常以{medium}形式呈现")

    false = []
    for other in works:
        if other[0] == title:
            continue
        if creator and other[1] and other[1] != creator:
            false.append(f"《{title}》的创作者是{other[1]}")
        if not _genre_conflicts(genre, other[4]):
            false.append(f"《{title}》属于{other[4]}")
        if not _country_conflicts(country, other[2]):
            false.append(f"《{title}》来自{other[2]}")
        if not _medium_conflicts(medium, other[5]):
            false.append(f"《{title}》常以{other[5]}形式呈现")
    return _unique(true), _unique(false)


class _GradeBuilder:
    def __init__(self, grade, subject, difficulty, chapters):
        self.grade = grade
        self.subject = subject
        self.difficulty = difficulty
        self.chapters = chapters
        self.specs = defaultdict(list)
        self._seen = set()
        self._chapter_index = 0

    def _next_chapter(self):
        chapter = self.chapters[self._chapter_index % len(self.chapters)]
        self._chapter_index += 1
        return chapter

    def _add(self, qtype, stem, options, answer, score, explanation, mode, rubric=None):
        full_stem = clean_stem(stem)
        key = (qtype, full_stem)
        if key in self._seen:
            return
        self._seen.add(key)
        self.specs[qtype].append({
            "subject": self.subject,
            "stem": full_stem,
            "options": options,
            "answer": answer,
            "score": score,
            "analysis": explanation,
            "rubric": rubric,
            "scoring_mode": mode,
            "difficulty": self.difficulty,
            "chapter": self._next_chapter(),
        })

    def add_single(self, stem, correct, wrongs, explanation):
        wrongs = [item for item in _unique(wrongs) if item != correct][:3]
        if len(wrongs) < 3:
            return
        pairs = _option_pairs([correct], wrongs, stem, min_correct=1, max_options=4)
        if pairs is None:
            return
        options, answer = pairs
        key = answer[0]
        self._add(
            QuestionType.SINGLE_CHOICE, stem, options, {"value": key}, 2,
            f"正确答案为 {key}。{explanation}", ScoringMode.AUTO,
        )

    def add_multi(self, stem, correct, wrongs, explanation):
        correct = _unique(correct)[:4]
        wrongs = [item for item in _unique(wrongs) if item not in correct][:2]
        if len(correct) < 2 or len(wrongs) < 1:
            return
        pairs = _option_pairs(correct, wrongs, stem, min_correct=2, max_options=6)
        if pairs is None:
            return
        options, answer = pairs
        self._add(
            QuestionType.MULTIPLE_CHOICE, stem, options, {"values": answer}, 3,
            f"正确选项为 {'、'.join(answer)}。{explanation}", ScoringMode.AUTO,
        )

    def add_short(self, stem, reference):
        self._add(
            QuestionType.SHORT_ANSWER, stem, [], {"text": reference}, 5,
            "参考要点见标准答案，评分时关注要点完整性与表达能力。",
            ScoringMode.MANUAL,
            rubric="要点完整、条理清楚、能结合具体作品或课堂体验；允许学生用自己的语言表达。",
        )

    def add_practice(self, stem, rubric):
        qtype = (
            QuestionType.AUDIO_UPLOAD if self.subject == MUSIC
            else QuestionType.IMAGE_UPLOAD
        )
        self._add(
            qtype, stem, [], {"reference": "见评分标准"}, 10,
            "本题为实践作品题，由教师按评分标准人工评分。",
            ScoringMode.MANUAL, rubric=rubric,
        )


def _build_work_singles(builder, works, fallbacks, subject_label):
    titles = [work[0] for work in works]
    creators = [work[1] for work in works if work[1]]
    countries = [work[2] for work in works]
    periods = [work[3] for work in works]
    genres = [work[4] for work in works]
    media = [work[5] for work in works]
    notes = [work[6] for work in works]

    for work in works:
        title, creator, country, period, genre, medium, note = work
        creator_label = "曲作者" if subject_label == "音乐" else "作者"
        if creator:
            builder.add_single(
                f"《{title}》的{creator_label}是？",
                creator,
                _others(creators, creator, fallbacks["creator"]),
                f"《{title}》由{creator}创作。",
            )
        builder.add_single(
            f"《{title}》属于哪种{subject_label}门类？" if subject_label == "美术"
            else f"《{title}》属于哪种音乐体裁？",
            genre,
            _others(genres, genre, fallbacks["genre"], conflicts=_genre_conflicts),
            f"《{title}》属于{genre}。",
        )
        builder.add_single(
            f"《{title}》通常采用哪种表演形式？" if subject_label == "音乐"
            else f"《{title}》主要使用什么材料或技法？",
            medium,
            _others(media, medium, fallbacks["medium"], conflicts=_medium_conflicts),
            f"《{title}》常以{medium}形式呈现。",
        )
        builder.add_single(
            f"《{title}》来自哪个国家或地区？",
            country,
            _others(countries, country, fallbacks["country"], conflicts=_country_conflicts),
            f"《{title}》属于{country}的{subject_label}。",
        )
        builder.add_single(
            f"《{title}》形成或创作于哪个时期？",
            period,
            _others(periods, period, fallbacks["period"], conflicts=_period_conflicts),
            f"《{title}》属于{period}时期。",
        )
        builder.add_single(
            f"欣赏《{title}》时，下面哪种描述最符合它的特点？",
            note,
            _others(notes, note, fallbacks["note"], conflicts=_note_conflicts),
            f"《{title}》的特点是{note}。",
        )

        same_genre = [
            other[0] for other in works
            if other[0] != title and other[4] == genre
        ]
        if same_genre:
            builder.add_single(
                f"下列作品中，与《{title}》同属“{genre}”的是？",
                same_genre[0],
                [item for item in titles if item not in same_genre and item != title],
                f"《{same_genre[0]}》与《{title}》都属于{genre}。",
            )

        true_statements, false_statements = _statements(work, works)
        if true_statements and len(false_statements) >= 3:
            builder.add_single(
                f"关于《{title}》，下列说法正确的是？",
                true_statements[0],
                false_statements[:3],
                f"《{title}》的准确信息是：{true_statements[0]}。",
            )


def _build_term_singles(builder, terms, subject_label, fallbacks):
    term_names = [term[0] for term in terms]
    definitions = [term[1] for term in terms]
    categories = [term[2] for term in terms]

    for term, definition, category in terms:
        builder.add_single(
            f"“{term}”的意思是？",
            definition,
            _others(definitions, definition, [item[1] for item in fallbacks["term"]]),
            f"{term}：{definition}。",
        )
        builder.add_single(
            f"“{definition}”描述的是哪个{subject_label}术语？",
            term,
            _others(term_names, term, [item[0] for item in fallbacks["term"]]),
            f"{definition}，这就是“{term}”。",
        )
        # 术语名与类别名相同时（如“雕塑”属于“雕塑”），不再出分类题。
        if term != category:
            builder.add_single(
                f"“{term}”属于下列哪一类？",
                category,
                _others(
                    categories, category, fallbacks["category"],
                    conflicts=_category_conflicts,
                ),
                f"{term}属于{category}。",
            )
            same_category = [
                item[0] for item in terms
                if item[0] != term and item[2] == category
            ]
            if same_category:
                builder.add_single(
                    f"下列术语中，与“{term}”同属“{category}”的是？",
                    same_category[0],
                    [item for item in term_names if item != term and item not in same_category],
                    f"“{same_category[0]}”与“{term}”都属于{category}。",
                )


def _build_work_multis(builder, works, subject_label):
    titles = [work[0] for work in works]
    by_genre = defaultdict(list)
    by_country = defaultdict(list)
    for work in works:
        by_genre[work[4]].append(work[0])
        by_country[work[2]].append(work[0])

    for genre, names in by_genre.items():
        if len(names) >= 2:
            builder.add_multi(
                f"下列作品中，属于“{genre}”的有？",
                names[:4],
                [item for item in titles if item not in names][:2],
                f"《{'》《'.join(names[:4])}》都属于{genre}。",
            )
    for country, names in by_country.items():
        if len(names) >= 2:
            builder.add_multi(
                f"下列作品中，来自{country}的有？",
                names[:4],
                [item for item in titles if item not in names][:2],
                f"《{'》《'.join(names[:4])}》都来自{country}。",
            )

    for work in works:
        title = work[0]
        true_statements, false_statements = _statements(work, works)
        if len(true_statements) >= 2 and len(false_statements) >= 2:
            builder.add_multi(
                f"关于《{title}》，下列说法正确的有？",
                true_statements[:4],
                false_statements[:2],
                f"其余说法混淆了《{title}》的作者、国家、门类或材料。",
            )
        if subject_label == "音乐":
            builder.add_multi(
                f"演唱或演奏《{title}》时，应注意的有？",
                ["音准准确", "节奏稳定", "表达作品情绪"],
                ["随意改变速度", "忽略歌词内容"],
                "演唱、演奏要在音准和节奏准确的基础上表达作品情绪。",
            )
        else:
            builder.add_multi(
                f"创作或欣赏《{title}》时，应注意的有？",
                ["构图完整", "色彩协调", "主题明确"],
                ["随意涂抹", "忽略比例"],
                "美术创作要做到构图、色彩与主题相统一。",
            )


def _build_term_multis(builder, terms, subject_label, fallback_terms):
    term_names = [term[0] for term in terms]
    by_category = defaultdict(list)
    for term, _definition, category in terms:
        by_category[category].append(term)

    for category, names in by_category.items():
        if len(names) < 2:
            continue
        wrongs = [item for item in term_names if item not in names]
        if len(wrongs) < 2:
            wrongs = [item[0] for item in fallback_terms if item[0] not in names]
        builder.add_multi(
            f"下列{subject_label}术语中，属于“{category}”的有？",
            names[:4],
            wrongs[:2],
            f"这些术语都属于{category}。",
        )


def _build_shorts(builder, data, subject_label):
    works = data["works"]
    terms = data["terms"]
    themes = data["themes"]
    w1, w2, w3 = works[0], works[1], works[2]
    term = terms[0][0]
    theme = themes[0]

    if builder.grade <= 2:
        if subject_label == "音乐":
            prompts = [
                (f"听一听《{w1[0]}》，说说歌曲的速度是快还是慢，你的心情怎样。",
                 "能说出快/慢，并用一两个词描述心情，如开心、安静、想跳舞。"),
                (f"跟着老师唱《{w2[0]}》，说说你最喜欢哪一句，为什么。",
                 "能说出喜欢的一句歌词或旋律，并简单说明理由。"),
                (f"比较《{w1[0]}》和《{w2[0]}》，哪一首更欢快？说说你的理由。",
                 "能选出更欢快的一首，并从速度、力度或情绪上说明理由。"),
                (f"用“{term}”说一说，你在歌曲里听到了什么。",
                 f"能用自己的话解释{term}，并举出歌曲中的一个例子。"),
                ("这学期你学会了哪一首歌？请写出歌名，并说说它唱了什么。",
                 "能写出完整歌名，并用一两句话概括歌曲内容。"),
            ]
        else:
            prompts = [
                (f"看一看《{w1[0]}》，说说画面里有什么，你最喜欢哪个部分。",
                 "能说出画面中的主要形象，并指出自己喜欢的部分。"),
                (f"《{w2[0]}》用了哪些颜色？给你什么感觉？",
                 "能说出两三种主要颜色，并用温暖、安静、热闹等词描述感受。"),
                (f"比较《{w1[0]}》和《{w2[0]}》，你更喜欢哪一幅？为什么？",
                 "能作出选择，并从内容、色彩或形象上说明理由。"),
                (f"用“{term}”说一说，你在画面中看到了什么。",
                 f"能用自己的话解释{term}，并在画面中指出对应的地方。"),
                ("这学期你画过什么？请说说你的画。",
                 "能说出画题、画中的主要内容和自己最满意的地方。"),
            ]
    else:
        if subject_label == "音乐":
            prompts = [
                (f"聆听《{w1[0]}》，说说它带给你的情绪感受，并描述你联想到的画面。",
                 "能从情绪（欢快、抒情、雄壮等）和画面两方面回答，感受具体。"),
                (f"演唱《{w2[0]}》时，应该注意哪些方面？请从音准、节奏、情绪中选两点说明。",
                 "能结合歌曲特点说明音准、节奏或情绪的处理方法。"),
                (f"比较《{w1[0]}》和《{w2[0]}》，说说它们在速度、情绪或表演形式上的不同。",
                 "能从速度、情绪、演唱形式等角度作比较，至少说出两点不同。"),
                (f"用“{term}”的知识，说说它在《{w3[0]}》中是怎样体现的。",
                 f"能准确解释{term}，并结合《{w3[0]}》的旋律、节奏或演奏形式举例。"),
                ("结合本年级音乐课的学习，说说你最喜欢的一首歌曲，并说明理由。",
                 "能写出歌名，从旋律、歌词、情绪或文化背景等角度说明理由。"),
            ]
        else:
            prompts = [
                (f"观察《{w1[0]}》，从内容、色彩、构图三方面说说你的感受。",
                 "能分别描述画面内容、主要色彩和构图特点，并表达自己的感受。"),
                (f"比较《{w1[0]}》和《{w2[0]}》，说说它们在题材或表现方法上的不同。",
                 "能从题材、材料、笔触或色彩等角度作比较，至少说出两点不同。"),
                (f"用“{term}”的知识，分析《{w3[0]}》的一个特点。",
                 f"能准确解释{term}，并结合《{w3[0]}》的画面举例分析。"),
                (f"如果以“{theme}”为题创作，你会怎样安排画面？请写出构思。",
                 "能说清画面主体、背景、色彩和材料，构思完整。"),
                ("说说你在本年级美术课上学到的一种技法，并描述它的步骤。",
                 "能说出技法名称，并按先后顺序描述主要步骤。"),
            ]
    for stem, reference in prompts:
        builder.add_short(stem, reference)


def _build_practices(builder, data, subject_label):
    works = data["works"]
    themes = data["themes"]
    if subject_label == "音乐":
        if builder.grade <= 2:
            rubric = (
                "音准基本准确 30 分；节奏基本稳定 30 分；吐字清楚 20 分；"
                "能表现歌曲情绪 20 分。"
            )
        elif builder.grade <= 6:
            rubric = (
                "音准准确 25 分；节奏准确 25 分；音色与发声方法 20 分；"
                "情绪与表现力 20 分；演唱完整、吐字清晰 10 分。"
            )
        else:
            rubric = (
                "音准准确 20 分；节奏准确 20 分；音色与发声方法 20 分；"
                "情绪与风格把握 25 分；演唱完整、吐字清晰 15 分。"
            )
        for work in works[:3]:
            builder.add_practice(
                f"请完整演唱《{work[0]}》，录制音频后上传。"
                "要求音准、节奏准确，吐字清晰，并能表现歌曲的情绪与风格。",
                rubric,
            )
    else:
        if builder.grade <= 2:
            rubric = (
                "构图完整 20 分；形象生动 20 分；色彩鲜明 20 分；"
                "创意与主题 20 分；画面整洁 20 分。"
            )
        elif builder.grade <= 6:
            rubric = (
                "构图完整、主次分明 20 分；造型比例准确 20 分；色彩或明暗关系协调 20 分；"
                "创意与主题表达 20 分；画面完整、整洁 20 分。"
            )
        else:
            rubric = (
                "构图完整、形式感强 20 分；造型与比例准确 20 分；色彩或明暗关系协调 20 分；"
                "创意与主题表达 25 分；画面完整、制作精良 15 分。"
            )
        for theme in themes[:3]:
            builder.add_practice(
                f"请以“{theme}”为题完成一幅绘画作品（材料不限），拍摄或扫描后上传图片。"
                "要求构图完整、主题明确，画面不小于 A4 大小。",
                rubric,
            )


def build_specs(grade, subject):
    """生成某年级、某学科的题目快照（未写库，便于测试）。"""
    if grade not in MUSIC_GRADES:
        raise ValueError(f"不支持的年级：{grade}")
    if subject == MUSIC:
        data = MUSIC_GRADES[grade]
        chapters = MUSIC_CHAPTERS
        subject_label = "音乐"
        fallbacks = {
            "creator": MUSIC_CREATOR_FALLBACK,
            "country": MUSIC_COUNTRY_FALLBACK,
            "period": MUSIC_PERIOD_FALLBACK,
            "genre": MUSIC_GENRE_FALLBACK,
            "medium": MUSIC_MEDIUM_FALLBACK,
            "note": MUSIC_NOTE_FALLBACK,
            "category": MUSIC_CATEGORY_FALLBACK,
            "term": MUSIC_TERM_FALLBACK,
        }
    elif subject == ART:
        data = ART_GRADES[grade]
        chapters = ART_CHAPTERS
        subject_label = "美术"
        fallbacks = {
            "creator": ART_CREATOR_FALLBACK,
            "country": ART_COUNTRY_FALLBACK,
            "period": ART_PERIOD_FALLBACK,
            "genre": ART_GENRE_FALLBACK,
            "medium": ART_MEDIUM_FALLBACK,
            "note": ART_NOTE_FALLBACK,
            "category": ART_CATEGORY_FALLBACK,
            "term": ART_TERM_FALLBACK,
        }
    else:
        raise ValueError(f"不支持的学科：{subject}")

    builder = _GradeBuilder(grade, subject, GRADE_DIFFICULTY[grade], chapters)
    _build_work_singles(builder, data["works"], fallbacks, subject_label)
    _build_term_singles(builder, data["terms"], subject_label, fallbacks)
    _build_work_multis(builder, data["works"], subject_label)
    _build_term_multis(
        builder, data["terms"], subject_label, fallbacks["term"],
    )
    _build_practices(builder, data, subject_label)

    rng = random.Random(f"{subject}-{grade}-20261028")
    result = {}
    for qtype, specs in builder.specs.items():
        shuffled = list(specs)
        rng.shuffle(shuffled)
        result[qtype] = shuffled
    return result


def _chapter_knowledge(grade, subject, name):
    subject_label = "音乐" if subject == MUSIC else "美术"
    band_key = "low" if grade <= 2 else "high" if grade >= 8 else "middle"
    focus = (
        BAND_CHAPTER_FOCUS.get((subject, band_key), {}).get(name)
        or CHAPTER_FOCUS[subject][name]
    )
    band = BAND_FOCUS[grade]
    description = f"{GRADE_NAMES[grade]}年级{subject_label}“{name}”：{focus}。"
    content = "\n".join([
        "【学习目标】",
        f"1. 结合{GRADE_NAMES[grade]}年级{subject_label}学习，理解“{name}”的基本知识；",
        f"2. 能在欣赏或练习中说出{name}的相关要点；",
        "3. 愿意与同学交流自己的感受和发现。",
        "",
        "【知识要点】",
        f"· 本年级{name}的学习重点是：{focus}。",
        f"· 学习方式：{band}，多听、多看、多动手，把课堂知识与生活经验联系起来。",
        f"· 评价时关注：能否准确说出关键概念，能否结合具体作品举例，能否清楚表达自己的看法。",
        "",
        "【课堂小任务】",
        f"和同桌合作，选一件本年级学过的作品，用“{name}”的知识说一说它的一个特点，并记录在课堂笔记上。",
    ])
    return description, content


def _parse_grades(value):
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


class Command(BaseCommand):
    help = "按年级补充音乐 / 美术分层题库（1~9 年级，含年级难度与实践题）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--grades", default="1-9",
            help="年级范围，默认 1-9；可写 1-6 或 3,6,7,8",
        )
        parser.add_argument(
            "--subject", choices=[MUSIC, ART],
            help="只补充指定学科；默认两个学科都补充",
        )
        parser.add_argument(
            "--single", type=int, default=DEFAULT_TARGETS[QuestionType.SINGLE_CHOICE],
            help="每个年级、每学科补充的单选题数量，默认 30",
        )
        parser.add_argument(
            "--multi", type=int, default=DEFAULT_TARGETS[QuestionType.MULTIPLE_CHOICE],
            help="每个年级、每学科补充的多选题数量，默认 12",
        )
        parser.add_argument(
            "--short", type=int, default=0,
            help="已停用：系统不再生成简答题",
        )
        parser.add_argument(
            "--practice", type=int,
            default=DEFAULT_TARGETS[QuestionType.AUDIO_UPLOAD],
            help="每个年级、每学科补充的实践题数量，默认 3",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(
            role=Role.QUESTION_ADMIN, deleted_at__isnull=True,
        ).order_by("id").first()
        if admin is None:
            raise CommandError("未找到题库管理员账号，请先执行 seed_demo_accounts")

        grades = _parse_grades(options["grades"])
        subjects = [options["subject"]] if options.get("subject") else [MUSIC, ART]
        now = timezone.now()
        targets = {
            QuestionType.SINGLE_CHOICE: max(0, options["single"]),
            QuestionType.MULTIPLE_CHOICE: max(0, options["multi"]),
            QuestionType.AUDIO_UPLOAD: max(0, options["practice"]),
            QuestionType.IMAGE_UPLOAD: max(0, options["practice"]),
        }

        totals = defaultdict(int)
        for grade in grades:
            for subject in subjects:
                course, chapters = self._ensure_course(grade, subject)
                specs = build_specs(grade, subject)
                for qtype, target in targets.items():
                    if target <= 0:
                        continue
                    if qtype == QuestionType.AUDIO_UPLOAD and subject != MUSIC:
                        continue
                    if qtype == QuestionType.IMAGE_UPLOAD and subject != ART:
                        continue
                    selected = specs.get(qtype, [])[:target]
                    if len(selected) < target:
                        self.stdout.write(self.style.WARNING(
                            f"  {GRADE_NAMES[grade]}年级"
                            f"{'音乐' if subject == MUSIC else '美术'} "
                            f"{qtype} 只生成 {len(selected)} 道（目标 {target} 道）"
                        ))
                    created = self._persist(
                        grade, subject, course, chapters, qtype, selected, admin, now,
                    )
                    totals[f"{subject}:{qtype}"] += created
                    totals[qtype] += created

        self.stdout.write(self.style.SUCCESS("各年级分层题库补充完成"))
        for grade in grades:
            self.stdout.write(
                f"  {GRADE_NAMES[grade]}年级（难度 {GRADE_DIFFICULTY[grade]}/5）"
                f"：{Question.objects.filter(grade=grade, deleted_at__isnull=True).count()} 道"
            )
        total_created = sum(
            totals[qtype] for qtype in (
                QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE,
                QuestionType.SHORT_ANSWER, QuestionType.AUDIO_UPLOAD,
                QuestionType.IMAGE_UPLOAD,
            )
        )
        self.stdout.write(f"  本次新增 {total_created} 道")

    # ------------------------------------------------------------------
    def _ensure_course(self, grade, subject):
        if subject == MUSIC:
            name = f"{GRADE_NAMES[grade]}年级音乐（人教版）"
            chapter_names = MUSIC_CHAPTERS
            subject_label = "音乐"
        else:
            name = f"{GRADE_NAMES[grade]}年级美术（人美版）"
            chapter_names = ART_CHAPTERS
            subject_label = "美术"
        course, _ = Course.objects.get_or_create(
            name=name, subject=subject, grade=grade,
            defaults={
                "description": (
                    f"{GRADE_NAMES[grade]}年级{subject_label}分层题库课程"
                    f"（难度 {GRADE_DIFFICULTY[grade]}/5）"
                ),
                "sort_order": grade * 10 + (0 if subject == MUSIC else 1),
            },
        )
        chapters = {}
        for index, chapter_name in enumerate(chapter_names, start=1):
            chapter, created = Chapter.objects.get_or_create(
                course=course, name=chapter_name,
                defaults={"sort_order": index},
            )
            description, content = _chapter_knowledge(grade, subject, chapter_name)
            # 只刷新本命令生成的章节讲解，不覆盖 seed_chapter_knowledge 的七年级正文。
            generated_by_us = (chapter.description or "").startswith(
                f"{GRADE_NAMES[grade]}年级"
            )
            if (
                created
                or not (chapter.content or "").strip()
                or generated_by_us
            ) and (chapter.description != description or chapter.content != content):
                chapter.description = description
                chapter.content = content
                chapter.save(update_fields=["description", "content", "updated_at"])
            chapters[chapter_name] = chapter
        return course, chapters

    def _persist(self, grade, subject, course, chapters, qtype, specs, admin, now):
        if not specs:
            return 0
        stems = [spec["stem"] for spec in specs]
        existing = set()
        for start in range(0, len(stems), 400):
            chunk = stems[start:start + 400]
            existing.update(
                Question.objects.filter(
                    course=course, stem__in=chunk, deleted_at__isnull=True,
                ).values_list("stem", flat=True)
            )
        to_create = [spec for spec in specs if spec["stem"] not in existing]
        if not to_create:
            return 0

        rows = []
        for spec in to_create:
            rows.append(Question(
                subject=subject,
                grade=grade,
                course=course,
                chapter=chapters.get(spec["chapter"]),
                type=qtype,
                difficulty=spec["difficulty"],
                stem=spec["stem"],
                score=spec["score"],
                answer=spec["answer"],
                analysis=spec["analysis"],
                rubric=spec.get("rubric"),
                scoring_mode=spec["scoring_mode"],
                status=QuestionStatus.APPROVED,
                creator=admin,
                reviewer=admin,
                review_comment="按年级分层补充，系统自动审核通过",
                reviewed_at=now,
            ))
        Question.objects.bulk_create(rows, batch_size=400)

        created_stems = [spec["stem"] for spec in to_create]
        question_map = {}
        for start in range(0, len(created_stems), 400):
            chunk = created_stems[start:start + 400]
            question_map.update({
                stem: qid for qid, stem in Question.objects.filter(
                    course=course, stem__in=chunk, deleted_at__isnull=True,
                ).values_list("id", "stem")
            })
        options = []
        for spec in to_create:
            question_id = question_map.get(spec["stem"])
            if not question_id:
                continue
            for index, (key, text) in enumerate(spec.get("options") or []):
                options.append(QuestionOption(
                    question_id=question_id, key=key, text=text, sort_order=index,
                ))
        QuestionOption.objects.bulk_create(options, batch_size=2000)
        return len(to_create)
