from rapidfuzz import fuzz

def test_fuzz():
    texts = ("多符号与空格", "this is a 中文测试", "this  is  a  中文测试!")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "partial_ratio:", fuzz.partial_ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    print(texts, "token_set_ratio:", fuzz.token_set_ratio(texts[1], texts[2]))

    texts = ("单词", "It's", "Its")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "partial_ratio:", fuzz.partial_ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    print(texts, "token_set_ratio:", fuzz.token_set_ratio(texts[1], texts[2]))

    texts = ("大小写", "apple", "Apple")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "partial_ratio:", fuzz.partial_ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    print(texts, "token_set_ratio:", fuzz.token_set_ratio(texts[1], texts[2]))

    texts = ("中文+空格", "我叫王富贵。", "我 叫 王 富贵。")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "partial_ratio:", fuzz.partial_ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    print(texts, "token_set_ratio:", fuzz.token_set_ratio(texts[1], texts[2]))

    texts = ("中文+空格", "我叫王富贵。", "我叫 王富 贵。")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "partial_ratio:", fuzz.partial_ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    print(texts, "token_set_ratio:", fuzz.token_set_ratio(texts[1], texts[2]))

    texts = ("英文无空格", "My name is Fengwei Wang.", "MynameisFengweiWang")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "partial_ratio:", fuzz.partial_ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    print(texts, "token_set_ratio:", fuzz.token_set_ratio(texts[1], texts[2]))

    # 渐进，取最大的时
    print(fuzz.token_sort_ratio("this is a 中文测试", "is  a 中文  测试"))
    print(fuzz.token_sort_ratio("this is a 中文测试", "this  is  a 中文  测"))
    print(fuzz.token_sort_ratio("this is a 中文测试", "this  is  a 中文  测试"))
    print(fuzz.token_sort_ratio("this is a 中文测试", "this  is  a 中文  测试!"))

    texts = ("渐进测试", "My name is Fengwei.", "Hello,  My  name is")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    texts = ("渐进测试", "My name is Fengwei.", "Hello, My name is Funway")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    texts = ("渐进测试", "My name is Fengwei.", "Hello, My name is Funway.")  # 命中右边界
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    texts = ("渐进测试", "My name is Fengwei.", "Hello, My name is Funway. How")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    texts = ("渐进测试", "My name is Fengwei.", "Hello, My name is Funway. How are")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))
    texts = ("渐进测试", "My name is Fengwei.", "My name is Funway.")  # 命中左边界
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    print(texts, "token_sort_ratio:", fuzz.token_sort_ratio(texts[1], texts[2]))


    texts = ("只差一个字符", "MynamesFengweiWang.", "MynameisFengweiWang.")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    texts = ("只差一个字符", "hi", "he")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    texts = ("只差一个字符", "MynamesFengweiWang. hello, howareyou.nicetomeetyou", "MynameisFengweiWang. hello, howareyou.nicetomeetyou")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))

    texts = ("测试", "hewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.", "seahewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    texts = ("测试", "hewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.", "seahewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.\"he's")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    texts = ("测试", "hewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.", "seahewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))
    texts = ("测试", "hewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.", "seahewasanoldmanwhofishedaloneinaskiffinthegulfstreamandhehadgoneeighty–fourdaysnowwithouttakingafish.")
    print(texts, "ratio:", fuzz.ratio(texts[1], texts[2]))

    pass

if __name__ == "__main__":
    # main()
    test_fuzz()