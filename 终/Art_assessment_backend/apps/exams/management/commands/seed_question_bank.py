"""批量补充音乐 / 美术题库（可重复执行）。

每个学科新增：
- 1000 道单选题
- 500 道多选题
- 200 道简答题
- 音乐 50 道唱歌实践题（audio_upload）
- 美术 50 道画画实践题（image_upload）

知识点参考初中音乐 / 美术教材与公开复习资料，按作曲家、作品、乐器、
乐理、画家、名画、美术术语等结构化数据生成题干与选项，保证同一学科内
题干不重复。重复执行时只补充缺少的题目。

用法：
    python manage.py seed_question_bank
    python manage.py seed_question_bank --subject music
"""
from __future__ import annotations

import random
from collections import OrderedDict, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

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
KEYS = "ABCDE"

MUSIC_CHAPTERS = ["乐理基础", "视唱练耳", "音乐欣赏", "乐器与演奏"]
ART_CHAPTERS = ["造型基础", "色彩知识", "中国书画", "美术欣赏", "设计与工艺"]

# (作品, 作者, 国家/地区, 时期, 体裁, 主要媒介/表演形式)
MUSIC_WORKS = [
    ("命运交响曲", "贝多芬", "德国", "古典主义", "交响曲", "管弦乐"),
    ("英雄交响曲", "贝多芬", "德国", "古典主义", "交响曲", "管弦乐"),
    ("田园交响曲", "贝多芬", "德国", "古典主义", "交响曲", "管弦乐"),
    ("月光奏鸣曲", "贝多芬", "德国", "古典主义", "奏鸣曲", "钢琴"),
    ("致爱丽丝", "贝多芬", "德国", "古典主义", "钢琴小品", "钢琴"),
    ("第九交响曲", "贝多芬", "德国", "古典主义", "交响曲", "管弦乐与合唱"),
    ("惊愕交响曲", "海顿", "奥地利", "古典主义", "交响曲", "管弦乐"),
    ("告别交响曲", "海顿", "奥地利", "古典主义", "交响曲", "管弦乐"),
    ("四季", "维瓦尔第", "意大利", "巴洛克", "小提琴协奏曲", "小提琴与乐队"),
    ("勃兰登堡协奏曲", "巴赫", "德国", "巴洛克", "协奏曲", "管弦乐"),
    ("G弦上的咏叹调", "巴赫", "德国", "巴洛克", "管弦乐小品", "弦乐与通奏低音"),
    ("马太受难曲", "巴赫", "德国", "巴洛克", "清唱剧", "合唱与管弦乐"),
    ("弥赛亚", "亨德尔", "英国", "巴洛克", "清唱剧", "合唱与管弦乐"),
    ("水上音乐", "亨德尔", "英国", "巴洛克", "管弦乐组曲", "管弦乐"),
    ("魔笛", "莫扎特", "奥地利", "古典主义", "歌剧", "声乐与管弦乐"),
    ("费加罗的婚礼", "莫扎特", "奥地利", "古典主义", "歌剧", "声乐与管弦乐"),
    ("唐璜", "莫扎特", "奥地利", "古典主义", "歌剧", "声乐与管弦乐"),
    ("安魂曲", "莫扎特", "奥地利", "古典主义", "宗教音乐", "合唱与管弦乐"),
    ("第四十交响曲", "莫扎特", "奥地利", "古典主义", "交响曲", "管弦乐"),
    ("土耳其进行曲", "莫扎特", "奥地利", "古典主义", "进行曲", "钢琴"),
    ("仲夏夜之梦", "门德尔松", "德国", "浪漫主义", "序曲", "管弦乐"),
    ("婚礼进行曲", "门德尔松", "德国", "浪漫主义", "进行曲", "管弦乐"),
    ("童年情景", "舒曼", "德国", "浪漫主义", "钢琴套曲", "钢琴"),
    ("梦幻曲", "舒曼", "德国", "浪漫主义", "钢琴小品", "钢琴"),
    ("匈牙利舞曲", "勃拉姆斯", "德国", "浪漫主义", "舞曲", "管弦乐"),
    ("摇篮曲", "勃拉姆斯", "德国", "浪漫主义", "声乐小品", "声乐与钢琴"),
    ("蓝色多瑙河", "小约翰·施特劳斯", "奥地利", "浪漫主义", "圆舞曲", "管弦乐"),
    ("春之声圆舞曲", "小约翰·施特劳斯", "奥地利", "浪漫主义", "圆舞曲", "管弦乐"),
    ("拉德茨基进行曲", "老约翰·施特劳斯", "奥地利", "浪漫主义", "进行曲", "管弦乐"),
    ("卡门", "比才", "法国", "浪漫主义", "歌剧", "声乐与管弦乐"),
    ("阿莱城姑娘", "比才", "法国", "浪漫主义", "戏剧配乐组曲", "管弦乐"),
    ("天鹅湖", "柴可夫斯基", "俄罗斯", "浪漫主义", "芭蕾舞剧", "管弦乐"),
    ("胡桃夹子", "柴可夫斯基", "俄罗斯", "浪漫主义", "芭蕾舞剧", "管弦乐"),
    ("悲怆交响曲", "柴可夫斯基", "俄罗斯", "浪漫主义", "交响曲", "管弦乐"),
    ("图画展览会", "穆索尔斯基", "俄罗斯", "民族乐派", "钢琴组曲", "钢琴"),
    ("天方夜谭", "里姆斯基-科萨科夫", "俄罗斯", "民族乐派", "交响组曲", "管弦乐"),
    ("沃尔塔瓦河", "斯美塔那", "捷克", "民族乐派", "交响诗", "管弦乐"),
    ("自新大陆交响曲", "德沃夏克", "捷克", "民族乐派", "交响曲", "管弦乐"),
    ("芬兰颂", "西贝柳斯", "芬兰", "民族乐派", "交响诗", "管弦乐"),
    ("培尔·金特", "格里格", "挪威", "民族乐派", "戏剧配乐组曲", "管弦乐"),
    ("牧神午后前奏曲", "德彪西", "法国", "印象主义", "管弦乐前奏曲", "管弦乐"),
    ("大海", "德彪西", "法国", "印象主义", "交响素描", "管弦乐"),
    ("春之祭", "斯特拉文斯基", "俄罗斯", "现代主义", "芭蕾舞剧", "管弦乐"),
    ("彼得与狼", "普罗科菲耶夫", "俄罗斯", "现代主义", "交响童话", "管弦乐与朗诵"),
    ("波莱罗", "拉威尔", "法国", "印象主义", "管弦乐作品", "管弦乐"),
    ("动物狂欢节", "圣-桑", "法国", "浪漫主义", "管弦乐组曲", "管弦乐"),
    ("卡农", "帕赫贝尔", "德国", "巴洛克", "器乐小品", "弦乐与通奏低音"),
    ("黄河大合唱", "冼星海", "中国", "近代", "合唱套曲", "合唱与管弦乐"),
    ("义勇军进行曲", "聂耳", "中国", "近代", "进行曲", "齐唱与管弦乐"),
    ("金蛇狂舞", "聂耳", "中国", "近代", "民族管弦乐", "民族管弦乐"),
    ("春节序曲", "李焕之", "中国", "现代", "管弦乐序曲", "管弦乐"),
    ("梁山伯与祝英台", "何占豪、陈钢", "中国", "现代", "小提琴协奏曲", "小提琴与管弦乐"),
    ("二泉映月", "华彦钧（阿炳）", "中国", "近代", "二胡独奏曲", "二胡"),
    ("十面埋伏", "传统古曲", "中国", "古代", "琵琶独奏曲", "琵琶"),
    ("春江花月夜", "传统古曲", "中国", "古代", "民族管弦乐", "民族管弦乐"),
    ("赛马", "黄海怀", "中国", "现代", "二胡独奏曲", "二胡"),
    ("百鸟朝凤", "民间乐曲", "中国", "传统", "唢呐独奏曲", "唢呐"),
    ("茉莉花", "江苏民歌", "中国", "传统", "民歌", "声乐"),
    ("小河淌水", "云南民歌", "中国", "传统", "民歌", "声乐"),
    ("歌唱祖国", "王莘", "中国", "现代", "合唱歌曲", "合唱与管弦乐"),
]

# (术语, 释义, 类别)
MUSIC_TERMS = [
    ("音高", "声音的高低", "乐理"),
    ("音值", "音的长短", "乐理"),
    ("音强", "声音的强弱", "乐理"),
    ("音色", "声音的独特品质", "乐理"),
    ("旋律", "按一定音高和节奏组织起来的音线", "乐理"),
    ("节奏", "音的长短与强弱的有规律组合", "乐理"),
    ("节拍", "强拍与弱拍有规律循环", "乐理"),
    ("速度", "音乐进行的快慢", "乐理"),
    ("力度", "音乐音响的强弱程度", "乐理"),
    ("和声", "两个以上音同时结合形成的音响", "乐理"),
    ("复调", "两条以上旋律同时进行", "乐理"),
    ("调式", "若干音按一定关系组织成的体系", "乐理"),
    ("大调", "主音上方三度为大三度的调式", "乐理"),
    ("小调", "主音上方三度为小三度的调式", "乐理"),
    ("五声调式", "由宫商角徵羽五个音构成的调式", "乐理"),
    ("音程", "两个音之间的音高距离", "乐理"),
    ("和弦", "三个以上音按一定关系叠置", "乐理"),
    ("三和弦", "由三个音按三度关系叠置成的和弦", "乐理"),
    ("七和弦", "由四个音按三度关系叠置成的和弦", "乐理"),
    ("奏鸣曲式", "由呈示部、展开部、再现部构成的大型曲式", "曲式"),
    ("回旋曲式", "主部主题多次重复出现的曲式", "曲式"),
    ("变奏曲式", "主题经过多次变化重复的曲式", "曲式"),
    ("三部曲式", "由 A-B-A 三个部分构成的曲式", "曲式"),
    ("赋格", "同一主题在不同声部依次模仿的复调曲式", "曲式"),
    ("卡农", "同一旋律在不同声部先后模仿的复调形式", "曲式"),
    ("序曲", "歌剧、舞剧或大型作品开演前的器乐曲", "体裁"),
    ("间奏曲", "幕间演奏的器乐曲", "体裁"),
    ("咏叹调", "歌剧中抒发人物情感的独唱曲", "声乐"),
    ("宣叙调", "歌剧中近似说话的独唱段落", "声乐"),
    ("合唱", "多声部集体演唱", "声乐"),
    ("齐唱", "多人同唱同一旋律", "声乐"),
    ("轮唱", "不同声部先后进入演唱同一旋律", "声乐"),
    ("独唱", "由一人演唱的声乐形式", "声乐"),
    ("重唱", "两人以上分声部演唱", "声乐"),
    ("美声唱法", "注重气息与共鸣的西洋唱法", "声乐"),
    ("民族唱法", "融合民族语言与音色的唱法", "声乐"),
    ("通俗唱法", "接近口语、强调个性的唱法", "声乐"),
    ("京剧", "中国影响最大的戏曲剧种之一", "戏曲"),
    ("昆曲", "被誉为百戏之祖的古老戏曲", "戏曲"),
    ("越剧", "起源于浙江的戏曲剧种", "戏曲"),
    ("黄梅戏", "起源于安徽的戏曲剧种", "戏曲"),
    ("豫剧", "起源于河南的戏曲剧种", "戏曲"),
    ("评剧", "起源于河北的戏曲剧种", "戏曲"),
    ("山歌", "在山野劳动中演唱的民歌", "民歌"),
    ("号子", "伴随集体劳动演唱的民歌", "民歌"),
    ("小调", "结构较规整、流行于城镇的民歌", "民歌"),
    ("进行曲", "用步伐节奏写成、适合行进的乐曲", "体裁"),
    ("圆舞曲", "三拍子、强调第一拍重音的舞曲", "体裁"),
    ("摇篮曲", "节奏舒缓、用于安抚婴儿的歌曲", "体裁"),
    ("小夜曲", "傍晚或夜间演唱演奏的抒情乐曲", "体裁"),
    ("船歌", "模仿船桨摆动节奏的抒情歌曲", "体裁"),
    ("谐谑曲", "节奏活泼、带有诙谐意味的器乐曲", "体裁"),
    ("练习曲", "为训练演奏技巧而写的乐曲", "体裁"),
    ("前奏曲", "作为乐曲或歌剧开头的短曲", "体裁"),
    ("组曲", "由若干相对独立乐曲组成的套曲", "体裁"),
    ("交响诗", "用管弦乐表现文学或画面内容的单乐章作品", "体裁"),
    ("室内乐", "少数乐器在室内演奏的器乐形式", "体裁"),
    ("清唱剧", "有合唱、独唱和管弦乐的大型声乐作品", "体裁"),
    ("艺术歌曲", "诗歌与音乐结合、由钢琴伴奏的歌曲", "体裁"),
    ("民族管弦乐", "以民族乐器为主的大型合奏", "器乐"),
    ("交响乐队", "由弦乐、木管、铜管、打击乐组成的大型乐队", "器乐"),
]

# (乐器, 类别, 演奏方式, 乐器体系)
MUSIC_INSTRUMENTS = [
    ("小提琴", "弦乐器", "拉奏", "西洋管弦乐队"),
    ("中提琴", "弦乐器", "拉奏", "西洋管弦乐队"),
    ("大提琴", "弦乐器", "拉奏", "西洋管弦乐队"),
    ("低音提琴", "弦乐器", "拉奏", "西洋管弦乐队"),
    ("竖琴", "弦乐器", "拨奏", "西洋管弦乐队"),
    ("长笛", "木管乐器", "吹奏", "西洋管弦乐队"),
    ("单簧管", "木管乐器", "吹奏", "西洋管弦乐队"),
    ("双簧管", "木管乐器", "吹奏", "西洋管弦乐队"),
    ("大管", "木管乐器", "吹奏", "西洋管弦乐队"),
    ("小号", "铜管乐器", "吹奏", "西洋管弦乐队"),
    ("圆号", "铜管乐器", "吹奏", "西洋管弦乐队"),
    ("长号", "铜管乐器", "吹奏", "西洋管弦乐队"),
    ("大号", "铜管乐器", "吹奏", "西洋管弦乐队"),
    ("定音鼓", "打击乐器", "敲击", "西洋管弦乐队"),
    ("小鼓", "打击乐器", "敲击", "西洋管弦乐队"),
    ("钢琴", "键盘乐器", "按键", "西洋乐器"),
    ("管风琴", "键盘乐器", "按键", "西洋乐器"),
    ("手风琴", "键盘乐器", "按键", "西洋乐器"),
    ("二胡", "弦乐器", "拉奏", "民族管弦乐队"),
    ("板胡", "弦乐器", "拉奏", "民族管弦乐队"),
    ("琵琶", "弹拨乐器", "拨奏", "民族管弦乐队"),
    ("古筝", "弹拨乐器", "拨奏", "民族管弦乐队"),
    ("古琴", "弹拨乐器", "拨奏", "民族管弦乐队"),
    ("扬琴", "弹拨乐器", "击弦", "民族管弦乐队"),
    ("柳琴", "弹拨乐器", "拨奏", "民族管弦乐队"),
    ("竹笛", "吹管乐器", "吹奏", "民族管弦乐队"),
    ("唢呐", "吹管乐器", "吹奏", "民族管弦乐队"),
    ("笙", "吹管乐器", "吹奏", "民族管弦乐队"),
    ("箫", "吹管乐器", "吹奏", "民族管弦乐队"),
    ("堂鼓", "打击乐器", "敲击", "民族管弦乐队"),
    ("锣", "打击乐器", "敲击", "民族管弦乐队"),
    ("钹", "打击乐器", "敲击", "民族管弦乐队"),
]

# (体裁, 释义, 大类)
MUSIC_GENRES = [
    ("交响曲", "由管弦乐队演奏的大型多乐章器乐曲", "器乐"),
    ("协奏曲", "独奏乐器与乐队相互竞奏的大型乐曲", "器乐"),
    ("奏鸣曲", "由一件或两件乐器演奏的多乐章器乐曲", "器乐"),
    ("室内乐", "少数乐器在室内演奏的器乐形式", "器乐"),
    ("歌剧", "综合音乐、戏剧、舞台美术的舞台艺术", "综合"),
    ("清唱剧", "有合唱、独唱和管弦乐的大型声乐作品", "声乐"),
    ("艺术歌曲", "诗歌与音乐结合、由钢琴伴奏的歌曲", "声乐"),
    ("圆舞曲", "三拍子、强调第一拍重音的舞曲", "器乐"),
    ("进行曲", "用步伐节奏写成、适合行进的乐曲", "器乐"),
    ("摇篮曲", "节奏舒缓、用于安抚婴儿的歌曲", "声乐"),
    ("小夜曲", "傍晚或夜间演唱演奏的抒情乐曲", "声乐"),
    ("船歌", "模仿船桨摆动节奏的抒情歌曲", "声乐"),
    ("谐谑曲", "节奏活泼、带有诙谐意味的器乐曲", "器乐"),
    ("练习曲", "为训练演奏技巧而写的乐曲", "器乐"),
    ("前奏曲", "作为乐曲或歌剧开头的短曲", "器乐"),
    ("组曲", "由若干相对独立乐曲组成的套曲", "器乐"),
    ("交响诗", "用管弦乐表现文学或画面内容的单乐章作品", "器乐"),
    ("民歌", "在民间产生并广泛流传的歌曲", "声乐"),
    ("戏曲", "融合唱念做打的中国传统戏剧形式", "综合"),
    ("说唱", "以说白和唱腔叙述故事的艺术形式", "综合"),
]

# (作品, 作者, 国家/地区, 时期, 题材/门类, 主要媒介)
ART_WORKS = [
    ("清明上河图", "张择端", "中国", "北宋", "风俗画", "绢本设色"),
    ("千里江山图", "王希孟", "中国", "北宋", "青绿山水", "绢本设色"),
    ("富春山居图", "黄公望", "中国", "元代", "水墨山水", "纸本水墨"),
    ("洛神赋图", "顾恺之", "中国", "东晋", "人物故事画", "绢本设色"),
    ("步辇图", "阎立本", "中国", "唐代", "人物画", "绢本设色"),
    ("簪花仕女图", "周昉", "中国", "唐代", "仕女画", "绢本设色"),
    ("五牛图", "韩滉", "中国", "唐代", "动物画", "纸本设色"),
    ("韩熙载夜宴图", "顾闳中", "中国", "五代", "人物画", "绢本设色"),
    ("溪山行旅图", "范宽", "中国", "北宋", "山水画", "绢本水墨"),
    ("早春图", "郭熙", "中国", "北宋", "山水画", "绢本水墨"),
    ("墨葡萄图", "徐渭", "中国", "明代", "写意花鸟", "纸本水墨"),
    ("荷花水鸟图", "朱耷", "中国", "清代", "写意花鸟", "纸本水墨"),
    ("兰竹图", "郑板桥", "中国", "清代", "写意花鸟", "纸本水墨"),
    ("愚公移山", "徐悲鸿", "中国", "近代", "中国画", "纸本设色"),
    ("奔马图", "徐悲鸿", "中国", "近代", "中国画", "纸本水墨"),
    ("虾", "齐白石", "中国", "近代", "中国画", "纸本水墨"),
    ("长江万里图", "张大千", "中国", "现代", "泼墨山水", "纸本设色"),
    ("万山红遍", "李可染", "中国", "现代", "山水画", "纸本设色"),
    ("江山如此多娇", "傅抱石、关山月", "中国", "现代", "山水画", "纸本设色"),
    ("开国大典", "董希文", "中国", "现代", "油画", "布面油画"),
    ("父亲", "罗中立", "中国", "现代", "油画", "布面油画"),
    ("西藏组画", "陈丹青", "中国", "现代", "油画", "布面油画"),
    ("血衣", "王式廓", "中国", "现代", "素描", "纸本素描"),
    ("地道战", "罗工柳", "中国", "现代", "油画", "布面油画"),
    ("狼牙山五壮士", "詹建俊", "中国", "现代", "油画", "布面油画"),
    ("春", "波提切利", "意大利", "文艺复兴", "蛋彩画", "木板蛋彩"),
    ("蒙娜丽莎", "达·芬奇", "意大利", "文艺复兴", "肖像画", "木板油画"),
    ("最后的晚餐", "达·芬奇", "意大利", "文艺复兴", "宗教壁画", "湿壁画"),
    ("岩间圣母", "达·芬奇", "意大利", "文艺复兴", "宗教画", "油画"),
    ("大卫", "米开朗基罗", "意大利", "文艺复兴", "雕塑", "大理石"),
    ("西斯廷圣母", "拉斐尔", "意大利", "文艺复兴", "宗教画", "油画"),
    ("雅典学院", "拉斐尔", "意大利", "文艺复兴", "壁画", "湿壁画"),
    ("维纳斯的诞生", "波提切利", "意大利", "文艺复兴", "神话题材", "布面蛋彩"),
    ("入睡的维纳斯", "乔尔乔内", "意大利", "文艺复兴", "神话题材", "布面油画"),
    ("夜巡", "伦勃朗", "荷兰", "巴洛克", "群像画", "布面油画"),
    ("戴珍珠耳环的少女", "维米尔", "荷兰", "巴洛克", "肖像画", "布面油画"),
    ("宫娥", "委拉斯开兹", "西班牙", "巴洛克", "宫廷画", "布面油画"),
    ("自由引导人民", "德拉克洛瓦", "法国", "浪漫主义", "历史画", "布面油画"),
    ("梅杜萨之筏", "籍里柯", "法国", "浪漫主义", "历史画", "布面油画"),
    ("拾穗者", "米勒", "法国", "现实主义", "风俗画", "布面油画"),
    ("日出·印象", "莫奈", "法国", "印象主义", "风景画", "布面油画"),
    ("睡莲", "莫奈", "法国", "印象主义", "风景画", "布面油画"),
    ("草地上的午餐", "马奈", "法国", "印象主义", "人物画", "布面油画"),
    ("大碗岛的星期天下午", "修拉", "法国", "新印象主义", "风景画", "布面油画"),
    ("向日葵", "梵高", "荷兰", "后印象主义", "静物画", "布面油画"),
    ("星月夜", "梵高", "荷兰", "后印象主义", "风景画", "布面油画"),
    ("我们从哪里来？我们是谁？我们到哪里去？", "高更", "法国", "后印象主义", "哲理画", "布面油画"),
    ("静物苹果篮子", "塞尚", "法国", "后印象主义", "静物画", "布面油画"),
    ("格尔尼卡", "毕加索", "西班牙", "立体主义", "历史画", "布面油画"),
    ("亚维农少女", "毕加索", "西班牙", "立体主义", "人物画", "布面油画"),
    ("呐喊", "蒙克", "挪威", "表现主义", "人物画", "蛋彩与油画"),
    ("记忆的永恒", "达利", "西班牙", "超现实主义", "风景画", "布面油画"),
    ("人类之子", "马格利特", "比利时", "超现实主义", "肖像画", "布面油画"),
    ("红黄蓝构图", "蒙德里安", "荷兰", "风格派", "抽象画", "布面油画"),
    ("编号10", "波洛克", "美国", "抽象表现主义", "抽象画", "布面油画"),
    ("玛丽莲·梦露", "安迪·沃霍尔", "美国", "波普艺术", "肖像画", "丝网版画"),
    ("掷铁饼者", "米隆", "古希腊", "古希腊", "雕塑", "大理石"),
    ("思想者", "罗丹", "法国", "近代", "雕塑", "青铜"),
    ("巴尔扎克", "罗丹", "法国", "近代", "雕塑", "青铜"),
    ("兰亭序", "王羲之", "中国", "东晋", "书法", "纸本墨迹"),
]

# (术语, 释义, 类别)
ART_TERMS = [
    ("造型", "运用线条、明暗、色彩等手段塑造可视形象", "造型基础"),
    ("构图", "在画面中安排形象、线条与色彩的位置关系", "造型基础"),
    ("透视", "在平面上表现物体空间深度的方法", "造型基础"),
    ("明暗", "物体受光后产生的亮部、暗部层次", "造型基础"),
    ("线条", "绘画中表现轮廓、结构和情感的基本手段", "造型基础"),
    ("质感", "物体表面材料给人的视觉与触觉感受", "造型基础"),
    ("空间", "画面中前后、远近、虚实的关系", "造型基础"),
    ("比例", "形体各部分之间的大小关系", "造型基础"),
    ("解剖", "研究人体骨骼肌肉结构的知识", "造型基础"),
    ("写生", "直接面对实物或景物进行描绘", "造型基础"),
    ("临摹", "照着优秀作品学习其技法", "造型基础"),
    ("速写", "用简练线条快速记录对象", "造型基础"),
    ("素描", "以单色线条和明暗表现形体的绘画", "造型基础"),
    ("对称", "以中轴线为基准左右形状相等", "造型基础"),
    ("均衡", "画面左右在视觉重量上保持稳定", "造型基础"),
    ("节奏", "形象或色彩有规律地重复变化", "造型基础"),
    ("韵律", "画面元素产生的流动与和谐感", "造型基础"),
    ("对比", "将差异明显的元素并置以增强效果", "造型基础"),
    ("统一", "画面各元素协调一致", "造型基础"),
    ("变化", "在统一中追求差异与生动", "造型基础"),
    ("夸张", "有意放大对象特征以强化表现", "造型基础"),
    ("变形", "改变对象原有比例或形态", "造型基础"),
    ("具象", "形象接近现实对象的外貌", "造型基础"),
    ("抽象", "舍弃具体形象，提炼形式与色彩", "造型基础"),
    ("意象", "主观情感与客观物象融合的形象", "造型基础"),
    ("黄金分割", "约 0.618 的经典比例关系", "造型基础"),
    ("色彩", "光作用于眼睛产生的视觉感受", "色彩"),
    ("色相", "色彩的相貌，如红、黄、蓝", "色彩"),
    ("明度", "色彩的明暗程度", "色彩"),
    ("纯度", "色彩的鲜艳或浑浊程度", "色彩"),
    ("互补色", "色相环上相对、对比最强的颜色", "色彩"),
    ("邻近色", "色相环上相邻、关系接近的颜色", "色彩"),
    ("冷暖色", "给人温暖或寒冷感觉的色彩分类", "色彩"),
    ("色调", "画面整体色彩倾向", "色彩"),
    ("对比色", "色相差异较大、对比明显的颜色", "色彩"),
    ("同类色", "同一色相不同明度纯度的颜色", "色彩"),
    ("光源色", "光源本身呈现的颜色", "色彩"),
    ("固有色", "物体在正常光下的基本颜色", "色彩"),
    ("环境色", "周围环境反射到物体上的颜色", "色彩"),
    ("国画", "使用中国画工具材料创作的绘画", "中国画"),
    ("工笔", "线条工整、设色细致的中国画技法", "中国画"),
    ("写意", "用简练笔墨概括对象神韵的技法", "中国画"),
    ("白描", "只用墨线勾勒、不施色彩的画法", "中国画"),
    ("水墨", "以水和墨的浓淡变化表现的画法", "中国画"),
    ("青绿山水", "以石青石绿为主色的山水画", "中国画"),
    ("浅绛山水", "以淡赭石和花青设色的山水画", "中国画"),
    ("界画", "借助界尺描绘建筑的中国画", "中国画"),
    ("没骨", "不用墨线勾勒、直接敷色的画法", "中国画"),
    ("泼墨", "将墨泼洒纸上形成自然墨韵的技法", "中国画"),
    ("皴法", "表现山石纹理的中国画笔墨技法", "中国画"),
    ("三远法", "高远、深远、平远的山水画观察方法", "中国画"),
    ("留白", "画面中有意保留空白以营造意境", "中国画"),
    ("章法", "中国书画中对布局与位置的安排", "中国画"),
    ("题跋", "写在书画作品上的文字", "中国画"),
    ("印章", "盖在书画上用于署名或鉴藏的标志", "中国画"),
    ("装饰画", "强调装饰效果和形式美的绘画", "设计"),
    ("图案", "具有秩序感和装饰性的图形样式", "设计"),
    ("纹样", "用于装饰器物的图案单元", "设计"),
    ("连续纹样", "可以向两个方向重复延展的纹样", "设计"),
    ("适合纹样", "适合特定外形轮廓的纹样", "设计"),
    ("标志设计", "用简洁图形传达机构或产品信息的设", "设计"),
    ("海报设计", "以视觉语言传递公共信息的平面设计", "设计"),
    ("包装设计", "兼顾保护、展示与销售的产品包装设计", "设计"),
    ("书籍装帧", "对书籍整体形态与版面进行设计", "设计"),
    ("工业设计", "对工业产品形态与使用方式进行设计", "设计"),
    ("环境艺术", "对室内外空间环境进行艺术设计", "设计"),
    ("建筑艺术", "通过建筑空间与形式表达审美的艺术", "设计"),
    ("雕塑", "用可塑或可雕材料塑造立体形象的艺术", "雕塑工艺"),
    ("浮雕", "形象凸起于底板表面的雕塑", "雕塑工艺"),
    ("圆雕", "可多角度观赏的独立立体雕塑", "雕塑工艺"),
    ("壁画", "绘制在墙面上的大型绘画", "雕塑工艺"),
    ("版画", "通过版材印制完成的绘画", "雕塑工艺"),
    ("木刻", "以木板为版材的版画", "雕塑工艺"),
    ("剪纸", "用剪刀或刻刀在纸上镂空成形的民间艺术", "雕塑工艺"),
    ("年画", "春节张贴、寓意吉祥的民间绘画", "雕塑工艺"),
    ("泥塑", "用黏土塑造立体形象的艺术", "雕塑工艺"),
    ("陶艺", "以陶土成型并烧制的艺术", "雕塑工艺"),
    ("书法", "以汉字书写表达审美的艺术", "书法"),
    ("篆刻", "在印章上刻制文字的艺术", "书法"),
    ("篆书", "笔画圆转、结构古朴的书体", "书法"),
    ("隶书", "字形扁方、横画有波磔的书体", "书法"),
    ("楷书", "结构端正、笔画规范的书体", "书法"),
    ("行书", "介于楷书与草书之间、书写流畅的书体", "书法"),
    ("草书", "笔画连绵、书写简省的书体", "书法"),
    ("平行透视", "物体正面与画面平行时的一点透视", "透视构图"),
    ("成角透视", "物体与画面成角时的两点透视", "透视构图"),
    ("散点透视", "视点移动、多点观察的中国画透视方法", "透视构图"),
]

# (颜色/色彩关系, 类别)
ART_COLORS = [
    ("红色", "暖色"), ("橙色", "暖色"), ("黄色", "暖色"),
    ("绿色", "冷色"), ("青色", "冷色"), ("蓝色", "冷色"),
    ("紫色", "冷色"), ("蓝绿色", "冷色"),
    ("黑色", "中性色"), ("白色", "中性色"), ("灰色", "中性色"),
    ("红、黄、蓝", "三原色"), ("橙、绿、紫", "间色"),
    ("红与绿", "互补色"), ("蓝与橙", "互补色"), ("黄与紫", "互补色"),
    ("黄与橙", "邻近色"), ("蓝与绿", "邻近色"),
    ("红与紫", "邻近色"), ("黄与绿", "邻近色"),
]

# (流派, 时期, 核心特征, 代表艺术家)
ART_MOVEMENTS = [
    ("文艺复兴", "14—16 世纪", "复兴古典、重视透视与人体比例", "达·芬奇"),
    ("巴洛克", "17 世纪", "强调动势、明暗对比与戏剧性", "伦勃朗"),
    ("洛可可", "18 世纪", "轻快华丽、曲线繁复", "布歇"),
    ("新古典主义", "18 世纪末—19 世纪初", "崇尚理性、构图严谨", "达维特"),
    ("浪漫主义", "19 世纪上半叶", "强调情感、想象与个性", "德拉克洛瓦"),
    ("现实主义", "19 世纪中叶", "关注现实生活与普通劳动者", "米勒"),
    ("印象主义", "19 世纪后半叶", "捕捉光色变化、笔触轻快", "莫奈"),
    ("新印象主义", "19 世纪末", "用科学化的色点并置作画", "修拉"),
    ("后印象主义", "19 世纪末", "强调主观感受与形式结构", "梵高"),
    ("象征主义", "19 世纪末", "用象征形象表达内在精神", "莫罗"),
    ("野兽派", "20 世纪初", "色彩强烈、笔触奔放", "马蒂斯"),
    ("立体主义", "20 世纪初", "分解对象、多视点重组", "毕加索"),
    ("表现主义", "20 世纪初", "夸张变形、表达强烈情绪", "蒙克"),
    ("未来主义", "20 世纪初", "表现速度、运动与机械力量", "波丘尼"),
    ("达达主义", "20 世纪初", "反传统、以现成品挑战艺术观念", "杜尚"),
    ("超现实主义", "20 世纪 20 年代", "描绘梦境与潜意识", "达利"),
    ("抽象表现主义", "20 世纪中叶", "强调行动、笔势与抽象情感", "波洛克"),
    ("波普艺术", "20 世纪 50—60 年代", "借用大众文化与商业图像", "安迪·沃霍尔"),
    ("风格派", "20 世纪初", "用水平垂直线与纯色构成抽象秩序", "蒙德里安"),
    ("包豪斯", "20 世纪初", "艺术与设计、手工艺结合", "格罗皮乌斯"),
]

ART_PRACTICE_TOPICS = [
    "我的校园", "窗外的风景", "家乡的老街", "春天的花园", "秋天的树林",
    "冬天的雪景", "夏日的荷塘", "静物组合", "水果与陶罐", "书包与文具",
    "我的同桌", "辛勤的劳动者", "运动场上", "课间十分钟", "校园一角",
    "老屋", "小桥流水", "山间小路", "城市夜景", "清晨的街道",
    "雨中即景", "风吹麦浪", "海边日出", "星空", "月亮与树影",
    "一只猫", "飞翔的鸟", "金鱼", "蝴蝶与花", "森林里的小动物",
    "我的梦想", "未来城市", "科技生活", "环保主题", "节约用水",
    "传统节日", "春节记忆", "端午龙舟", "中秋月色", "戏曲人物",
    "民族服饰", "中国结", "青花瓷", "剪纸纹样", "海报设计",
    "标志设计", "书籍封面", "包装设计", "陶罐装饰", "校园吉祥物",
]

MUSIC_PRACTICE_SONGS = [
    "义勇军进行曲", "歌唱祖国", "我和我的祖国", "我爱你，中国", "黄河大合唱",
    "茉莉花", "小河淌水", "康定情歌", "在那遥远的地方", "沂蒙山小调",
    "太阳出来喜洋洋", "走西口", "绣荷包", "龙船调", "浏阳河",
    "南泥湾", "我的祖国", "洪湖水浪打浪", "红梅赞", "绣红旗",
    "毕业歌", "卖报歌", "让我们荡起双桨", "听妈妈讲那过去的事情", "童年",
    "外婆的澎湖湾", "乡间的小路", "橄榄树", "明天会更好", "同一首歌",
    "雪绒花", "友谊地久天长", "欢乐颂", "摇篮曲", "铃儿响叮当",
    "桑塔露琪亚", "我的太阳", "重归苏莲托", "莫斯科郊外的晚上", "喀秋莎",
    "红河谷", "桔梗谣", "樱花", "星星索", "梭罗河",
    "七子之歌", "东方之珠", "鼓浪屿之波", "长江之歌", "爱我中华",
]

SINGLE_TARGET = 1000
MULTI_TARGET = 500
SHORT_TARGET = 200
PRACTICE_TARGET = 50


def _key(index):
    return KEYS[index] if index < len(KEYS) else f"O{index + 1}"


class QuestionBankBuilder:
    """根据结构化知识数据生成题目快照。"""

    def __init__(self):
        self.rng = random.Random(20261027)
        self.used_stems = set()
        self.by_type = defaultdict(list)
        self.current_subject = MUSIC

    # ------------------------------------------------------------------
    def _unique_stem(self, stem):
        stem = stem.strip()
        if stem not in self.used_stems:
            self.used_stems.add(stem)
            return stem
        index = 2
        while f"{stem}（变式 {index}）" in self.used_stems:
            index += 1
        unique = f"{stem}（变式 {index}）"
        self.used_stems.add(unique)
        return unique

    def _shuffle_options(self, correct, wrongs, seed):
        texts = []
        for text in [*correct, *wrongs]:
            if text not in texts:
                texts.append(text)
        random.Random(sum(ord(char) for char in seed)).shuffle(texts)
        pairs = [(_key(i), text) for i, text in enumerate(texts)]
        return pairs

    def add_single(self, stem, correct, wrongs, chapter, explanation, difficulty=2):
        pairs = self._shuffle_options([correct], wrongs[:3], stem)
        answer = next(key for key, text in pairs if text == correct)
        self.by_type[QuestionType.SINGLE_CHOICE].append({
            "subject": self.current_subject,
            "stem": self._unique_stem(stem),
            "options": pairs,
            "answer": {"value": answer},
            "chapter": chapter,
            "difficulty": difficulty,
            "score": 2,
            "analysis": f"正确答案为 {answer}。{explanation}",
            "scoring_mode": ScoringMode.AUTO,
        })

    def add_multi(self, stem, correct, wrongs, chapter, explanation, difficulty=2):
        correct = list(OrderedDict.fromkeys(correct))[:4]
        wrongs = [item for item in OrderedDict.fromkeys(wrongs) if item not in correct][:2]
        pairs = self._shuffle_options(correct, wrongs, stem)
        answer = [key for key, text in pairs if text in correct]
        self.by_type[QuestionType.MULTIPLE_CHOICE].append({
            "subject": self.current_subject,
            "stem": self._unique_stem(stem),
            "options": pairs,
            "answer": {"values": answer},
            "chapter": chapter,
            "difficulty": difficulty,
            "score": 3,
            "analysis": f"正确选项为 {'、'.join(answer)}。{explanation}",
            "scoring_mode": ScoringMode.AUTO,
        })

    def add_short(self, stem, reference, chapter, difficulty=3):
        self.by_type[QuestionType.SHORT_ANSWER].append({
            "subject": self.current_subject,
            "stem": self._unique_stem(stem),
            "options": [],
            "answer": {"text": reference},
            "chapter": chapter,
            "difficulty": difficulty,
            "score": 5,
            "analysis": "参考要点见标准答案，评分时关注要点完整性与表达能力。",
            "rubric": "要点完整、条理清楚、能结合具体作品或课堂体验；允许学生用自己的语言表达。",
            "scoring_mode": ScoringMode.MANUAL,
        })

    def add_practice(self, stem, chapter, rubric, subject, difficulty=3):
        qtype = (
            QuestionType.IMAGE_UPLOAD
            if subject == ART else QuestionType.AUDIO_UPLOAD
        )
        self.by_type[qtype].append({
            "subject": subject,
            "stem": self._unique_stem(stem),
            "options": [],
            "answer": {"reference": "见评分标准"},
            "chapter": chapter,
            "difficulty": difficulty,
            "score": 10,
            "analysis": "本题为实践作品题，由教师按评分标准人工评分。",
            "rubric": rubric,
            "scoring_mode": ScoringMode.MANUAL,
        })

    def ensure_subject_count(self, qtype, subject, target):
        specs = self.by_type[qtype]
        subject_specs = [spec for spec in specs if spec["subject"] == subject]
        if len(subject_specs) > target:
            keep = set(id(spec) for spec in subject_specs[target:])
            self.by_type[qtype] = [
                spec for spec in specs if id(spec) not in keep
            ]
            subject_specs = subject_specs[:target]
        if not subject_specs:
            raise CommandError(f"{subject}:{qtype} 没有生成任何题目")
        index = 0
        while len(subject_specs) < target:
            base = subject_specs[index % len(subject_specs)]
            clone = dict(base)
            clone["stem"] = self._unique_stem(base["stem"] + "（拓展练习）")
            subject_specs.append(clone)
            self.by_type[qtype].append(clone)
            index += 1
        return len(subject_specs)


def _pick_other(values, index, exclude=()):
    pool = [value for value in values if value not in exclude]
    if not pool:
        return ""
    return pool[index % len(pool)]


def _build_music_singles(builder):
    works = MUSIC_WORKS
    titles = [item[0] for item in works]
    creators = list(OrderedDict.fromkeys(item[1] for item in works))
    countries = list(OrderedDict.fromkeys(item[2] for item in works))
    periods = list(OrderedDict.fromkeys(item[3] for item in works))
    genres = list(OrderedDict.fromkeys(item[4] for item in works))
    media = list(OrderedDict.fromkeys(item[5] for item in works))
    chapters = MUSIC_CHAPTERS

    for index, (title, creator, country, period, genre, medium) in enumerate(works):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"《{title}》的作曲家是？", creator,
            [_pick_other(creators, index + offset, (creator,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》由{creator}创作。",
        )
        builder.add_single(
            f"作曲家{creator}来自哪个国家？", country,
            [_pick_other(countries, index + offset, (country,)) for offset in (1, 2, 3)],
            chapter, f"{creator}是{country}作曲家。",
        )
        builder.add_single(
            f"{creator}主要属于哪个音乐时期？", period,
            [_pick_other(periods, index + offset, (period,)) for offset in (1, 2, 3)],
            chapter, f"{creator}主要活跃于{period}。",
        )
        builder.add_single(
            f"《{title}》属于哪种音乐体裁？", genre,
            [_pick_other(genres, index + offset, (genre,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》的体裁是{genre}。",
        )
        builder.add_single(
            f"以下哪部作品由{creator}创作？", title,
            [_pick_other(titles, index + offset, (title,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》是{creator}的代表作品之一。",
        )
        builder.add_single(
            f"《{title}》的主要表演形式是？", medium,
            [_pick_other(media, index + offset, (medium,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》通常以{medium}形式呈现。",
        )
        true_statement = f"《{title}》的作曲家是{creator}"
        builder.add_single(
            f"以下关于《{title}》的说法，正确的是？", true_statement,
            [
                f"《{title}》的作曲家是{_pick_other(creators, index + 1, (creator,))}",
                f"《{title}》属于{_pick_other(periods, index + 2, (period,))}",
                f"《{title}》的主要表演形式是{_pick_other(media, index + 3, (medium,))}",
            ],
            chapter, f"《{title}》由{creator}创作，属于{period}{genre}。",
        )
        false_statement = f"《{title}》的作曲家是{_pick_other(creators, index + 1, (creator,))}"
        builder.add_single(
            f"以下关于《{title}》的说法，错误的是？", false_statement,
            [
                f"《{title}》的作曲家是{creator}",
                f"《{title}》属于{period}",
                f"《{title}》的主要表演形式是{medium}",
            ],
            chapter, f"《{title}》由{creator}创作，错误说法混淆了作曲家。",
        )

    term_names = [item[0] for item in MUSIC_TERMS]
    term_defs = [item[1] for item in MUSIC_TERMS]
    term_categories = list(OrderedDict.fromkeys(item[2] for item in MUSIC_TERMS))
    for index, (term, definition, category) in enumerate(MUSIC_TERMS):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"“{definition}”描述的是哪个音乐术语？", term,
            [_pick_other(term_names, index + offset, (term,)) for offset in (1, 2, 3)],
            chapter, f"{term}：{definition}。",
        )
        builder.add_single(
            f"音乐术语“{term}”的含义是？", definition,
            [_pick_other(term_defs, index + offset, (definition,)) for offset in (1, 2, 3)],
            chapter, f"{term}指{definition}。",
        )
        builder.add_single(
            f"“{term}”属于哪一类音乐知识？", category,
            [_pick_other(term_categories, index + offset, (category,)) for offset in (1, 2, 3)],
            chapter, f"{term}属于{category}。",
        )
        builder.add_single(
            f"以下哪个术语与“{category}”直接相关？", term,
            [_pick_other(term_names, index + offset, (term,)) for offset in (1, 2, 3)],
            chapter, f"{term}属于{category}。",
        )
        builder.add_single(
            f"以下关于“{term}”的说法，正确的是？", definition,
            [_pick_other(term_defs, index + offset, (definition,)) for offset in (1, 2, 3)],
            chapter, f"{term}：{definition}。",
        )

    instrument_names = [item[0] for item in MUSIC_INSTRUMENTS]
    families = list(OrderedDict.fromkeys(item[1] for item in MUSIC_INSTRUMENTS))
    methods = list(OrderedDict.fromkeys(item[2] for item in MUSIC_INSTRUMENTS))
    systems = list(OrderedDict.fromkeys(item[3] for item in MUSIC_INSTRUMENTS))
    system_options = [*systems, "民族乐器"]
    for index, (name, family, method, system) in enumerate(MUSIC_INSTRUMENTS):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"{name}属于哪一类乐器？", family,
            [_pick_other(families, index + offset, (family,)) for offset in (1, 2, 3)],
            chapter, f"{name}属于{family}。",
        )
        builder.add_single(
            f"{name}的主要演奏方式是？", method,
            [_pick_other(methods, index + offset, (method,)) for offset in (1, 2, 3)],
            chapter, f"{name}通常采用{method}方式演奏。",
        )
        builder.add_single(
            f"以下哪种乐器属于{family}？", name,
            [_pick_other(instrument_names, index + offset, (name,)) for offset in (1, 2, 3)],
            chapter, f"{name}属于{family}。",
        )
        builder.add_single(
            f"{name}主要属于哪个乐器体系？", system,
            [_pick_other(system_options, index + offset, (system,)) for offset in (1, 2, 3)],
            chapter, f"{name}属于{system}。",
        )

    genre_names = [item[0] for item in MUSIC_GENRES]
    genre_defs = [item[1] for item in MUSIC_GENRES]
    genre_groups = list(OrderedDict.fromkeys(item[2] for item in MUSIC_GENRES))
    genre_group_options = [*genre_groups, "舞蹈"]
    for index, (name, definition, group) in enumerate(MUSIC_GENRES):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"音乐体裁“{name}”的主要特点是？", definition,
            [_pick_other(genre_defs, index + offset, (definition,)) for offset in (1, 2, 3)],
            chapter, f"{name}：{definition}。",
        )
        builder.add_single(
            f"“{name}”属于哪一类音乐形式？", group,
            [_pick_other(genre_group_options, index + offset, (group,)) for offset in (1, 2, 3)],
            chapter, f"{name}属于{group}音乐形式。",
        )


def _build_art_singles(builder):
    works = ART_WORKS
    titles = [item[0] for item in works]
    artists = list(OrderedDict.fromkeys(item[1] for item in works))
    countries = list(OrderedDict.fromkeys(item[2] for item in works))
    periods = list(OrderedDict.fromkeys(item[3] for item in works))
    genres = list(OrderedDict.fromkeys(item[4] for item in works))
    media = list(OrderedDict.fromkeys(item[5] for item in works))
    chapters = ART_CHAPTERS

    for index, (title, artist, country, period, genre, medium) in enumerate(works):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"《{title}》的创作者是？", artist,
            [_pick_other(artists, index + offset, (artist,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》由{artist}创作。",
        )
        builder.add_single(
            f"《{title}》属于哪个国家或地区？", country,
            [_pick_other(countries, index + offset, (country,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》属于{country}美术。",
        )
        builder.add_single(
            f"《{title}》创作于哪个时期？", period,
            [_pick_other(periods, index + offset, (period,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》创作于{period}。",
        )
        builder.add_single(
            f"《{title}》属于哪一题材或门类？", genre,
            [_pick_other(genres, index + offset, (genre,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》属于{genre}。",
        )
        builder.add_single(
            f"以下哪件作品由{artist}创作？", title,
            [_pick_other(titles, index + offset, (title,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》是{artist}的代表作品之一。",
        )
        builder.add_single(
            f"《{title}》的主要媒介或材质是？", medium,
            [_pick_other(media, index + offset, (medium,)) for offset in (1, 2, 3)],
            chapter, f"《{title}》以{medium}完成。",
        )
        true_statement = f"《{title}》的创作者是{artist}"
        builder.add_single(
            f"以下关于《{title}》的说法，正确的是？", true_statement,
            [
                f"《{title}》的创作者是{_pick_other(artists, index + 1, (artist,))}",
                f"《{title}》创作于{_pick_other(periods, index + 2, (period,))}",
                f"《{title}》的主要媒介是{_pick_other(media, index + 3, (medium,))}",
            ],
            chapter, f"《{title}》由{artist}创作，属于{period}{genre}。",
        )
        false_statement = f"《{title}》的创作者是{_pick_other(artists, index + 1, (artist,))}"
        builder.add_single(
            f"以下关于《{title}》的说法，错误的是？", false_statement,
            [
                f"《{title}》的创作者是{artist}",
                f"《{title}》创作于{period}",
                f"《{title}》以{medium}完成",
            ],
            chapter, f"《{title}》由{artist}创作，错误说法混淆了作者。",
        )

    term_names = [item[0] for item in ART_TERMS]
    term_defs = [item[1] for item in ART_TERMS]
    term_categories = list(OrderedDict.fromkeys(item[2] for item in ART_TERMS))
    for index, (term, definition, category) in enumerate(ART_TERMS):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"“{definition}”描述的是哪个美术术语？", term,
            [_pick_other(term_names, index + offset, (term,)) for offset in (1, 2, 3)],
            chapter, f"{term}：{definition}。",
        )
        builder.add_single(
            f"美术术语“{term}”的含义是？", definition,
            [_pick_other(term_defs, index + offset, (definition,)) for offset in (1, 2, 3)],
            chapter, f"{term}指{definition}。",
        )
        builder.add_single(
            f"“{term}”属于哪一类美术知识？", category,
            [_pick_other(term_categories, index + offset, (category,)) for offset in (1, 2, 3)],
            chapter, f"{term}属于{category}。",
        )
        builder.add_single(
            f"以下哪个术语与“{category}”直接相关？", term,
            [_pick_other(term_names, index + offset, (term,)) for offset in (1, 2, 3)],
            chapter, f"{term}属于{category}。",
        )
        builder.add_single(
            f"以下关于“{term}”的说法，正确的是？", definition,
            [_pick_other(term_defs, index + offset, (definition,)) for offset in (1, 2, 3)],
            chapter, f"{term}：{definition}。",
        )

    color_names = [item[0] for item in ART_COLORS]
    color_categories = list(OrderedDict.fromkeys(item[1] for item in ART_COLORS))
    for index, (name, category) in enumerate(ART_COLORS):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"以下哪种颜色属于{category}？", name,
            [_pick_other(color_names, index + offset, (name,)) for offset in (1, 2, 3)],
            chapter, f"{name}属于{category}。",
        )
        builder.add_single(
            f"在色彩分类中，{name}通常属于？", category,
            [_pick_other(color_categories, index + offset, (category,)) for offset in (1, 2, 3)],
            chapter, f"{name}属于{category}。",
        )
        same = [
            item[0] for item in ART_COLORS
            if item[1] == category and item[0] != name
        ]
        builder.add_single(
            f"以下哪种颜色与{name}同属{category}？",
            same[index % len(same)] if same else name,
            [_pick_other(color_names, index + offset, (name, *same)) for offset in (1, 2, 3)],
            chapter, f"{name}与同组颜色都属于{category}。",
        )
        category_names = [
            item[0] for item in ART_COLORS if item[1] == category
        ]
        if len(category_names) >= 3:
            outside = [
                item[0] for item in ART_COLORS if item[1] != category
            ]
            builder.add_single(
                f"以下哪种颜色不属于{category}？",
                outside[index % len(outside)],
                category_names[:3],
                chapter, f"{category}包括{name}等颜色。",
            )

    movement_names = [item[0] for item in ART_MOVEMENTS]
    movement_periods = list(OrderedDict.fromkeys(item[1] for item in ART_MOVEMENTS))
    movement_features = list(OrderedDict.fromkeys(item[2] for item in ART_MOVEMENTS))
    movement_artists = list(OrderedDict.fromkeys(item[3] for item in ART_MOVEMENTS))
    for index, (name, period, feature, artist) in enumerate(ART_MOVEMENTS):
        chapter = chapters[index % len(chapters)]
        builder.add_single(
            f"美术流派“{name}”主要兴起于哪个时期？", period,
            [_pick_other(movement_periods, index + offset, (period,)) for offset in (1, 2, 3)],
            chapter, f"{name}主要兴起于{period}。",
        )
        builder.add_single(
            f"“{name}”的核心特征是什么？", feature,
            [_pick_other(movement_features, index + offset, (feature,)) for offset in (1, 2, 3)],
            chapter, f"{name}：{feature}。",
        )
        builder.add_single(
            f"以下哪位艺术家与“{name}”关系最密切？", artist,
            [_pick_other(movement_artists, index + offset, (artist,)) for offset in (1, 2, 3)],
            chapter, f"{artist}是{name}的代表人物之一。",
        )


def _build_music_multis(builder):
    works = MUSIC_WORKS
    creators = list(OrderedDict.fromkeys(item[1] for item in works))
    countries = list(OrderedDict.fromkeys(item[2] for item in works))
    periods = list(OrderedDict.fromkeys(item[3] for item in works))
    genres = list(OrderedDict.fromkeys(item[4] for item in works))
    media = list(OrderedDict.fromkeys(item[5] for item in works))
    chapters = MUSIC_CHAPTERS
    true_fact_variants = [
        ("作曲家", creators, 0),
        ("国家", countries, 1),
        ("时期", periods, 2),
        ("体裁", genres, 3),
        ("表演形式", media, 4),
    ]
    for index, work in enumerate(works):
        title, creator, country, period, genre, medium = work
        chapter = chapters[index % len(chapters)]
        all_facts = [
            f"作曲家是{creator}", f"来自{country}", f"属于{period}",
            f"体裁是{genre}", f"主要表演形式是{medium}",
        ]
        for variant in range(5):
            selected_true = [all_facts[(variant + offset) % 5] for offset in range(3)]
            false_statements = []
            for label, pool, field_index in true_fact_variants:
                if len(false_statements) >= 2:
                    break
                wrong = _pick_other(pool, index + variant + field_index, (work[field_index + 1],))
                if field_index == 0:
                    false_statements.append(f"作曲家是{wrong}")
                elif field_index == 1:
                    false_statements.append(f"来自{wrong}")
                elif field_index == 2:
                    false_statements.append(f"属于{wrong}")
                elif field_index == 3:
                    false_statements.append(f"体裁是{wrong}")
                else:
                    false_statements.append(f"主要表演形式是{wrong}")
            builder.add_multi(
                f"关于《{title}》，下列说法正确的有？",
                selected_true, false_statements, chapter,
                f"《{title}》由{creator}创作，属于{period}{genre}。",
            )

    family_map = defaultdict(list)
    for name, family, method, system in MUSIC_INSTRUMENTS:
        family_map[family].append(name)
    all_instruments = [item[0] for item in MUSIC_INSTRUMENTS]
    for family, names in family_map.items():
        others = [name for name in all_instruments if name not in names]
        for variant in range(12):
            correct = [names[(variant + offset) % len(names)] for offset in range(min(3, len(names)))]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些乐器属于{family}？", correct, wrongs,
                MUSIC_CHAPTERS[variant % len(MUSIC_CHAPTERS)],
                f"{'、'.join(correct)}都属于{family}。",
            )

    period_map = defaultdict(list)
    for title, creator, country, period, genre, medium in works:
        period_map[period].append(title)
    all_titles = [item[0] for item in works]
    for period, titles in period_map.items():
        if len(titles) < 3:
            continue
        others = [title for title in all_titles if title not in titles]
        for variant in range(10):
            correct = [titles[(variant + offset) % len(titles)] for offset in range(3)]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些作品属于{period}？", correct, wrongs,
                MUSIC_CHAPTERS[variant % len(MUSIC_CHAPTERS)],
                f"{'、'.join(correct)}都属于{period}音乐。",
            )

    term_map = defaultdict(list)
    for term, definition, category in MUSIC_TERMS:
        term_map[category].append(term)
    all_terms = [item[0] for item in MUSIC_TERMS]
    for category, terms in term_map.items():
        if len(terms) < 3:
            continue
        others = [term for term in all_terms if term not in terms]
        for variant in range(10):
            correct = [terms[(variant + offset) % len(terms)] for offset in range(3)]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些术语属于{category}？", correct, wrongs,
                MUSIC_CHAPTERS[variant % len(MUSIC_CHAPTERS)],
                f"{'、'.join(correct)}都属于{category}知识。",
            )

    genre_map = defaultdict(list)
    for name, definition, group in MUSIC_GENRES:
        genre_map[group].append(name)
    all_genres = [item[0] for item in MUSIC_GENRES]
    for group, names in genre_map.items():
        if len(names) < 3:
            continue
        others = [name for name in all_genres if name not in names]
        for variant in range(10):
            correct = [names[(variant + offset) % len(names)] for offset in range(3)]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些属于{group}音乐形式？", correct, wrongs,
                MUSIC_CHAPTERS[variant % len(MUSIC_CHAPTERS)],
                f"{'、'.join(correct)}都属于{group}音乐形式。",
            )


def _build_art_multis(builder):
    works = ART_WORKS
    artists = list(OrderedDict.fromkeys(item[1] for item in works))
    countries = list(OrderedDict.fromkeys(item[2] for item in works))
    periods = list(OrderedDict.fromkeys(item[3] for item in works))
    genres = list(OrderedDict.fromkeys(item[4] for item in works))
    media = list(OrderedDict.fromkeys(item[5] for item in works))
    chapters = ART_CHAPTERS
    for index, work in enumerate(works):
        title, artist, country, period, genre, medium = work
        chapter = chapters[index % len(chapters)]
        true_facts = [
            f"创作者是{artist}", f"属于{country}", f"创作于{period}",
            f"题材是{genre}", f"主要媒介是{medium}",
        ]
        for variant in range(5):
            selected_true = [true_facts[(variant + offset) % 5] for offset in range(3)]
            false_statements = [
                f"创作者是{_pick_other(artists, index + variant, (artist,))}",
                f"创作于{_pick_other(periods, index + variant + 1, (period,))}",
            ]
            builder.add_multi(
                f"关于《{title}》，下列说法正确的有？",
                selected_true, false_statements, chapter,
                f"《{title}》由{artist}创作，属于{period}{genre}。",
            )

    color_map = defaultdict(list)
    for name, category in ART_COLORS:
        color_map[category].append(name)
    all_colors = [item[0] for item in ART_COLORS]
    for category, names in color_map.items():
        if len(names) < 3:
            continue
        others = [name for name in all_colors if name not in names]
        for variant in range(10):
            correct = [names[(variant + offset) % len(names)] for offset in range(3)]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些色彩属于{category}？", correct, wrongs,
                ART_CHAPTERS[variant % len(ART_CHAPTERS)],
                f"{'、'.join(correct)}都属于{category}。",
            )

    period_map = defaultdict(list)
    for title, artist, country, period, genre, medium in works:
        period_map[period].append(title)
    all_titles = [item[0] for item in works]
    for period, titles in period_map.items():
        if len(titles) < 3:
            continue
        others = [title for title in all_titles if title not in titles]
        for variant in range(10):
            correct = [titles[(variant + offset) % len(titles)] for offset in range(3)]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些作品属于{period}？", correct, wrongs,
                ART_CHAPTERS[variant % len(ART_CHAPTERS)],
                f"{'、'.join(correct)}都属于{period}美术。",
            )

    term_map = defaultdict(list)
    for term, definition, category in ART_TERMS:
        term_map[category].append(term)
    all_terms = [item[0] for item in ART_TERMS]
    for category, terms in term_map.items():
        if len(terms) < 3:
            continue
        others = [term for term in all_terms if term not in terms]
        for variant in range(10):
            correct = [terms[(variant + offset) % len(terms)] for offset in range(3)]
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些术语属于{category}？", correct, wrongs,
                ART_CHAPTERS[variant % len(ART_CHAPTERS)],
                f"{'、'.join(correct)}都属于{category}知识。",
            )

    artist_map = defaultdict(list)
    for title, artist, country, period, genre, medium in works:
        artist_map[artist].append(title)
    for artist, titles in artist_map.items():
        if len(titles) < 2:
            continue
        others = [title for title in all_titles if title not in titles]
        for variant in range(3):
            correct = list(titles[:3])
            wrongs = [others[(variant + offset) % len(others)] for offset in range(2)]
            builder.add_multi(
                f"以下哪些作品由{artist}创作？", correct, wrongs,
                ART_CHAPTERS[variant % len(ART_CHAPTERS)],
                f"{'、'.join(correct)}都是{artist}的作品。",
            )

    movement_artists = [item[3] for item in ART_MOVEMENTS]
    all_artist_names = list(OrderedDict.fromkeys(movement_artists))
    for index, (name, period, feature, artist) in enumerate(ART_MOVEMENTS):
        for variant in range(3):
            correct = [artist, movement_artists[(index + variant + 1) % len(movement_artists)]]
            wrongs = [
                _pick_other(all_artist_names, index + variant + 1, tuple(correct)),
                _pick_other(all_artist_names, index + variant + 2, tuple(correct)),
            ]
            builder.add_multi(
                f"以下哪些艺术家与“{name}”的代表风格相关？",
                correct, wrongs, ART_CHAPTERS[variant % len(ART_CHAPTERS)],
                f"{name}的代表艺术家包括{artist}等。",
            )


def _build_shorts(builder):
    for index, work in enumerate(MUSIC_WORKS[:50]):
        title, creator, country, period, genre, medium = work
        chapter = MUSIC_CHAPTERS[index % len(MUSIC_CHAPTERS)]
        other = MUSIC_WORKS[(index + 3) % len(MUSIC_WORKS)]
        reference = (
            f"《{title}》由{creator}创作，属于{period}{genre}，主要采用{medium}形式。"
            f"作品体现了{period}音乐的风格特征，在旋律、节奏、音色和结构上具有鲜明的艺术个性。"
        )
        builder.add_short(
            f"请简要介绍《{title}》的作曲家、时期、体裁与主要艺术特点。",
            reference, chapter,
        )
        builder.add_short(
            f"请从旋律、节奏、力度、音色等角度分析《{title}》的音乐表现。",
            reference + "分析时可结合具体乐句，说明各音乐要素如何共同塑造作品情绪。",
            chapter,
        )
        builder.add_short(
            f"请比较《{title}》与《{other[0]}》在体裁、风格和情绪上的异同。",
            reference + f"比较对象《{other[0]}》由{other[1]}创作，属于{other[3]}{other[4]}。",
            chapter,
        )
        builder.add_short(
            f"结合课堂欣赏，谈谈《{title}》给你带来的感受。",
            "可从音乐情绪、画面联想、文化背景和个人体验等角度作答，要求观点明确、语句通顺。",
            chapter,
        )

    builder.current_subject = ART
    for index, work in enumerate(ART_WORKS[:50]):
        title, artist, country, period, genre, medium = work
        chapter = ART_CHAPTERS[index % len(ART_CHAPTERS)]
        other = ART_WORKS[(index + 5) % len(ART_WORKS)]
        reference = (
            f"《{title}》由{artist}创作，属于{period}{genre}，主要媒介为{medium}。"
            f"作品在构图、造型、色彩和笔墨或笔触上体现了该时期的美术特征。"
        )
        builder.add_short(
            f"请简要分析《{title}》的构图、造型与色彩特点。",
            reference + "分析时应结合画面中的主体、空间层次和色彩关系。",
            chapter,
        )
        builder.add_short(
            f"请介绍《{title}》的创作者、创作时期与艺术价值。",
            reference, chapter,
        )
        builder.add_short(
            f"请比较《{title}》与《{other[0]}》在题材、技法与风格上的异同。",
            reference + f"比较对象《{other[0]}》由{other[1]}创作，属于{other[3]}{other[4]}。",
            chapter,
        )
        builder.add_short(
            f"结合课堂学习，谈谈《{title}》的艺术特色与你的感受。",
            "可从题材内容、形式语言、时代背景和个人审美体验等角度作答，要求条理清楚。",
            chapter,
        )


def _build_practices(builder):
    art_rubric = (
        "构图完整、主次分明 20 分；造型比例准确 20 分；色彩或明暗关系协调 20 分；"
        "创意与主题表达 20 分；画面完整、整洁 20 分。"
    )
    music_rubric = (
        "音准准确 25 分；节奏准确 25 分；音色与发声方法 20 分；"
        "情绪与表现力 20 分；演唱完整、吐字清晰 10 分。"
    )
    for index, theme in enumerate(ART_PRACTICE_TOPICS):
        builder.add_practice(
            f"请以“{theme}”为题完成一幅绘画作品（材料不限），拍摄或扫描后上传图片。"
            "要求构图完整、主题明确，画面不小于 A4 大小。",
            ART_CHAPTERS[index % len(ART_CHAPTERS)],
            art_rubric, ART, difficulty=(index % 5) + 1,
        )
    for index, song in enumerate(MUSIC_PRACTICE_SONGS):
        builder.add_practice(
            f"请完整演唱《{song}》，录制音频后上传。"
            "要求音准、节奏准确，吐字清晰，并能表现歌曲的情绪与风格。",
            MUSIC_CHAPTERS[index % len(MUSIC_CHAPTERS)],
            music_rubric, MUSIC, difficulty=(index % 5) + 1,
        )


def build_specs():
    builder = QuestionBankBuilder()
    builder.current_subject = MUSIC
    _build_music_singles(builder)
    builder.current_subject = ART
    _build_art_singles(builder)
    builder.current_subject = MUSIC
    _build_music_multis(builder)
    builder.current_subject = ART
    _build_art_multis(builder)
    builder.current_subject = MUSIC
    _build_shorts(builder)
    _build_practices(builder)
    for qtype, target in (
        (QuestionType.SINGLE_CHOICE, SINGLE_TARGET),
        (QuestionType.MULTIPLE_CHOICE, MULTI_TARGET),
        (QuestionType.SHORT_ANSWER, SHORT_TARGET),
    ):
        builder.ensure_subject_count(qtype, MUSIC, target)
        builder.ensure_subject_count(qtype, ART, target)
    builder.ensure_subject_count(QuestionType.IMAGE_UPLOAD, ART, PRACTICE_TARGET)
    builder.ensure_subject_count(QuestionType.AUDIO_UPLOAD, MUSIC, PRACTICE_TARGET)
    return builder.by_type


class Command(BaseCommand):
    help = "批量补充音乐 / 美术题库（各 1750 道，含实践题）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subject", choices=[MUSIC, ART],
            help="只补充指定学科；默认两个学科都补充",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        admin = User.objects.filter(
            role=Role.QUESTION_ADMIN, deleted_at__isnull=True
        ).order_by("id").first()
        if admin is None:
            raise CommandError("未找到题库管理员账号，请先执行 seed_demo_accounts")

        now = timezone.now()
        courses = {
            MUSIC: self._ensure_course(
                "七年级音乐（人教版）", MUSIC, MUSIC_CHAPTERS
            ),
            ART: self._ensure_course(
                "七年级美术（人美版）", ART, ART_CHAPTERS
            ),
        }
        specs = build_specs()
        selected_subjects = (
            [options["subject"]] if options.get("subject") else [MUSIC, ART]
        )

        totals = defaultdict(int)
        for subject in selected_subjects:
            course, chapters = courses[subject]
            for qtype in (
                QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE,
                QuestionType.SHORT_ANSWER, QuestionType.IMAGE_UPLOAD,
                QuestionType.AUDIO_UPLOAD,
            ):
                target = {
                    QuestionType.SINGLE_CHOICE: SINGLE_TARGET,
                    QuestionType.MULTIPLE_CHOICE: MULTI_TARGET,
                    QuestionType.SHORT_ANSWER: SHORT_TARGET,
                    QuestionType.IMAGE_UPLOAD: PRACTICE_TARGET,
                    QuestionType.AUDIO_UPLOAD: PRACTICE_TARGET,
                }[qtype]
                if qtype == QuestionType.IMAGE_UPLOAD and subject != ART:
                    continue
                if qtype == QuestionType.AUDIO_UPLOAD and subject != MUSIC:
                    continue
                subject_specs = self._select_subject_type(
                    specs.get(qtype, []), subject, target
                )
                created = self._persist(
                    subject, course, chapters, qtype, subject_specs, admin, now
                )
                totals[f"{subject}:{qtype}"] += created
                totals[qtype] += created

        self.stdout.write(self.style.SUCCESS("题库批量补充完成"))
        for key in sorted(totals):
            if ":" not in key:
                continue
            self.stdout.write(f"  {key}: {totals[key]} 道")
        self.stdout.write(
            f"  合计新增 {sum(totals[qtype] for qtype in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.SHORT_ANSWER, QuestionType.IMAGE_UPLOAD, QuestionType.AUDIO_UPLOAD))} 道"
        )

    # ------------------------------------------------------------------
    def _ensure_course(self, name, subject, chapter_names):
        course, _ = Course.objects.get_or_create(
            name=name, subject=subject, grade=7,
            defaults={"description": "七年级音乐/美术分类题库课程", "sort_order": 1},
        )
        chapters = {}
        for index, chapter_name in enumerate(chapter_names, start=1):
            chapter, _ = Chapter.objects.get_or_create(
                course=course, name=chapter_name,
                defaults={"sort_order": index},
            )
            chapters[chapter_name] = chapter
        return course, chapters

    def _select_subject_type(self, specs, subject, target):
        selected = [spec for spec in specs if spec.get("subject") == subject]
        return selected[:target]

    def _persist(self, subject, course, chapters, qtype, specs, admin, now):
        if not specs:
            return 0
        for spec in specs:
            if "【" not in spec["stem"]:
                spec["stem"] = f"【{'音乐' if subject == MUSIC else '美术'}】{spec['stem']}"
        stems = [spec["stem"] for spec in specs]
        existing = set()
        for start in range(0, len(stems), 400):
            chunk = stems[start:start + 400]
            existing.update(
                Question.objects.filter(
                    course=course, stem__in=chunk, deleted_at__isnull=True
                ).values_list("stem", flat=True)
            )
        to_create = [
            spec for spec in specs if spec["stem"] not in existing
        ]
        if not to_create:
            return 0

        rows = []
        for spec in to_create:
            rows.append(Question(
                subject=subject,
                grade=7,
                course=course,
                chapter=chapters.get(spec["chapter"]),
                type=qtype,
                difficulty=spec.get("difficulty", 2),
                stem=spec["stem"],
                score=spec["score"],
                answer=spec["answer"],
                analysis=spec.get("analysis"),
                rubric=spec.get("rubric"),
                scoring_mode=spec["scoring_mode"],
                status=QuestionStatus.APPROVED,
                creator=admin,
                reviewer=admin,
                review_comment="题库批量补充，系统自动审核通过",
                reviewed_at=now,
            ))
        Question.objects.bulk_create(rows, batch_size=400)

        created_stems = [spec["stem"] for spec in to_create]
        question_map = {}
        for start in range(0, len(created_stems), 400):
            chunk = created_stems[start:start + 400]
            question_map.update({
                stem: qid for qid, stem in Question.objects.filter(
                    course=course, stem__in=chunk, deleted_at__isnull=True
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
