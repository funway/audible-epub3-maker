import pytest

test_data = [
    {
        "note": "基本英文句子，带空格，包括问号和感叹号",
        "text_input": "Hello, world! How are you? I'm fine.",
        "expected_outputs": [
            "Hello,",
            " world!",
            " How are you?",
            " I'm fine."
        ]
    },
    {
        "note": "英文数字和缩写，不应分句",
        "text_input": "The answer is: 0.99! This is great. The price is $12.50. What about U.S. GDP. Dr. Smith said so.",
        "expected_outputs": [
            "The answer is: 0.99!",
            " This is great.",
            " The price is $12.50.",
            " What about U.S.",
            " GDP.",
            " Dr. Smith said so."
        ]
    },
    {
        "note": "连续重复的英文标点，应算作一个分句点",
        "text_input": "Are you kidding???? No way!!! This is true.",
        "expected_outputs": [
            "Are you kidding????",
            " No way!!!",
            " This is true."
        ]
    },
    {
        "note": "中文基本句子，带各种全角标点",
        "text_input": "你好吗？我很好，谢谢。你呢？这是一个测试！",
        "expected_outputs": [
            "你好吗？",
            "我很好，",
            "谢谢。",
            "你呢？",
            "这是一个测试！"
        ]
    },
    {
        "note": "中文连续重复标点",
        "text_input": "太棒了！！！真的吗？？？是的。",
        "expected_outputs": [
            "太棒了！！！",
            "真的吗？？？",
            "是的。"
        ]
    },
    {
        "note": "中英文混合句子，标点符号混合",
        "text_input": "Hello, 世界！How are you？这是一个混合句。v1.2.3发布了！",
        "expected_outputs": [
            "Hello,",
            " 世界！",
            "How are you？",
            "这是一个混合句。",
            "v1.2.3发布了！"
        ]
    },
    {
        "note": "句子开头或结尾是标点，或只有标点",
        "text_input": "！这是一个开头。中间句子。结尾。",
        "expected_outputs": [
            "！",
            "这是一个开头。",
            "中间句子。",
            "结尾。"
        ]
    },
    {
        "note": "纯标点符号，带空格",
        "text_input": "  .?!   。？！  ",
        "expected_outputs": [
            "  .?!",
            "   。？！",
            "  "
        ]
    },
    {
        "note": "没有分隔符的纯文本",
        "text_input": "This is a single sentence with no punctuation at the end",
        "expected_outputs": [
            "This is a single sentence with no punctuation at the end"
        ]
    },
    {
        "note": "空字符串或仅包含空白字符",
        "text_input": "   ",
        "expected_outputs": ["   "]
    },
    {
        "note": "英文标点后没有空格，也要分句",
        "text_input": "Hello!No space.Are you fine?",
        "expected_outputs": [
            "Hello!",
            "No space.",
            "Are you fine?"
        ]
    },
    {
        "note": "英文标点后有多个空格",
        "text_input": "First sentence.  Second sentence!   Third sentence?",
        "expected_outputs": [
            "First sentence.",
            "  Second sentence!",
            "   Third sentence?"
        ]
    },
    {
        "note": "带半角中文标点的情况", # 你的分句函数需要能识别半角中文标点
        "text_input": "你好吗?我很好,谢谢.你呢?这是一个测试!",
        "expected_outputs": [
            "你好吗?",
            "我很好,",
            "谢谢.",
            "你呢?",
            "这是一个测试!"
        ]
    },
    {
        "note": "特殊情况：缩写点在句尾，但不是文末",
        "text_input": "It's from U.S. We don't like it.",
        "expected_outputs": [
            "It's from U.S.",
            " We don't like it."
        ]
    },
    {
        "note": "特殊情况：只包含数字和点的字符串，不应分句",
        "text_input": "1.2.3.4.5",
        "expected_outputs": [
            "1.2.3.4.5"
        ]
    },
    {
        "note": "句子中包含对白和引号",
        "text_input": '他说："你好！" 我回答：\'Fine, thank you!\'',
        "expected_outputs": [
            '他说："你好！"',
            " 我回答：'Fine,",
            " thank you!'"
        ]
    },
    {
        "note": "存在换行符号",
        "text_input": "第一句。\n第二句！! \n 第三句？",
        "expected_outputs": [
            "第一句。",
            "\n第二句！!",
            " \n 第三句？"
        ]
    },
]

@pytest.mark.parametrize("test_case", test_data)
def test_segment_text_by_re(test_case):
    from audible_epub3_gen.utils.text_parser import segment_text_by_re

    text = test_case["text_input"]
    expected_output = test_case["expected_outputs"]
    note = test_case["note"]

    print(f"\n--- 测试用例: {note} ---")
    print(f"输入文本: \n'{text}'")

    sentences = segment_text_by_re(text)
    
    print(f"实际输出: \n{sentences}")
    print(f"期望输出: \n{expected_output}")

    assert sentences == expected_output, f"测试失败 (Note: {note})"


# 测试点号替换的用例
test_data = [
    {
        "note": "替换数字序列中的点",
        "text_input": "The version is 1.2.3 and the price is 3.14.",
        "expected_output": "The version is 1_DOT_2_DOT_3 and the price is 3_DOT_14."
    },
    {
        "note": "替换缩写中的点",
        "text_input": "Dr. Smith and Mr. Wang are here. Call U.S. office.",
        "expected_output": "Dr_DOT_ Smith and Mr_DOT_ Wang are here. Call U_DOT_S_DOT_ office."
    },
    {
        "note": "替换多个缩写和数字序列中的点",
        "text_input": "Dr. Smith went to the lab at 3.14 PM. Mr. Wang said the project version is 1.2.3.",
        "expected_output": "Dr_DOT_ Smith went to the lab at 3_DOT_14 PM. Mr_DOT_ Wang said the project version is 1_DOT_2_DOT_3."
    },
    {
        "note": "缩写点在句尾",
        "text_input": "It's from U.S. Mr. Wang doesn't like it.",
        "expected_output": "It's from U_DOT_S. Mr_DOT_ Wang doesn't like it."
    },
    {
        "note": "没有点的纯文本",
        "text_input": "This is a test without any dots.",
        "expected_output": "This is a test without any dots."
    },
    {
        "note": "空字符串",
        "text_input": "",
        "expected_output": ""
    },
    {
        "note": "仅包含空白字符",
        "text_input": "   ",
        "expected_output": "   "
    }   
]

@pytest.mark.parametrize("test_case", test_data)
def test_replace_non_terminal_dot(test_case):
    from audible_epub3_gen.utils.text_parser import replace_non_terminal_dot, restore_non_terminal_dot
    
    text = test_case["text_input"]
    expected_output = test_case["expected_output"]
    note = test_case["note"]
    
    print(f"\n--- 测试用例: {note} ---")
    print(f"输入文本: \n'{text}'")
    
    modified_text = replace_non_terminal_dot(text)
    print(f"实际输出: \n'{modified_text}'")
    print(f"期望输出: \n'{expected_output}'")
    assert modified_text == expected_output, f"替换失败 (Note: {note})"
    
    restored_text = restore_non_terminal_dot(modified_text)
    print(f"还原后的文本: \n'{restored_text}'") 
    assert restored_text == text, f"还原失败 (Note: {note})"


def test_is_readable():
    from audible_epub3_gen.utils.text_parser import is_readable
    assert is_readable("Hello, world!") is True
    assert is_readable("你好，世界！") is True
    assert is_readable("Test\nSecond line") is True
    assert is_readable("  !6 ") is True

    assert is_readable("   ") is False
    assert is_readable("") is False
    assert is_readable("\n\t") is False
    assert is_readable("...") is False