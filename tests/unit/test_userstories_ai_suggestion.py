import pytest
import json
import logging
import re
from unittest.mock import MagicMock 

# 导入被测模块中的所有函数和类
# 假设您的服务文件名为 ai_service.py
from taiga.projects.userstories.services import (
    generate_single_story, 
    AIServiceError, 
    get_default_story, 
    preprocess,
    anonymize,
    clean_text
)

# ----------------------------------------------------------------------
#                         核心服务功能测试 (真实集成测试)
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "requirement, test_id",
    [
        # 案例 1: 原始案例 (包含敏感信息 PII)
        ("I'm a programmer, and I want to create a calendar. My phone is 56464564.", "PII_Input_Programmer"),
        
        # 案例 2: 复杂输入（包含 HTML 标签和链接，测试预处理）
        ("As an admin, I need a dashboard view. See details <a href='https://docs.link'>here</a>. <b>Crucial</b> to display metrics.", "HTML_Tags_And_Link_Input"),
        
        # 案例 3: 简单的用户需求，测试核心用户故事生成
        ("The customer must be able to reset their password using their email address.", "Simple_Customer_Requirement"),
        
        # 案例 4: 带有技术术语和流程的需求
        ("When the payment webhook fires, the system should log the transaction ID and update the user's subscription status.", "Technical_Webhook_Flow"),
        
        # 案例 5: 长且详细的需求
        ("We need to implement a dark mode feature for the entire application interface. This should be toggleable from the user settings page and persist across sessions. It must follow WCAG AAA contrast guidelines.", "Detailed_Feature_Request"),
    ],
    ids=lambda x: x[1] # 使用 test_id 作为 pytest 的测试名称
)
def test_generate_single_story_multiple_cases(requirement, test_id):
    """
    【集成测试】测试 generate_single_story 针对不同真实需求能否成功调用
    AI 服务，并在不使用 Mocking 的情况下返回正确的结构。
    
    此测试会发起实际的外部 API 调用。
    """
    print(f"\n--------Running Test Case: {test_id}--------")
    print("Natural language requirement: ", requirement)
    
    try:
        # 实际调用函数
        result = generate_single_story(requirement)
        print("User Story Generated from AI:\n", result)
    except AIServiceError as e:
        # 如果 AI 服务调用失败，视为配置或连接问题，测试失败
        pytest.fail(f"AI Service call failed for test '{test_id}'. Check configuration/network. Error: {e}")

    # --- 验证返回结构是否符合目标 JSON 格式 ---
    assert isinstance(result, dict), "Result must be a dictionary."
    assert "suggestion_subject" in result, "Result must contain 'suggestion_subject' key."
    assert "suggestion_description" in result, "Result must contain 'suggestion_description' key."
    assert "suggestion_tags" in result, "Result must contain 'suggestion_tags' key."
    assert isinstance(result["suggestion_tags"], list), "'suggestion_tags' value must be a list."

    # --- 验证描述是否包含用户故事格式的关键部分 (As a / I want / So that) ---
    description = result["suggestion_description"].lower()
    assert "as a" in description, "User Story description must contain 'As a' (角色)."
    assert "i want" in description, "User Story description must contain 'I want' (目标)."
    assert "so that" in description, "User Story description must contain 'So that' (价值)."
    
    # --- 验证标签数量是否在 [3, 5] 范围内 ---
    tag_count = len(result["suggestion_tags"])
    assert 3 <= tag_count <= 5, f"Tag count must be between 3 and 5, but got {tag_count}."


# ----------------------------------------------------------------------
#                      预处理辅助函数 - 增强测试
# ----------------------------------------------------------------------

@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        # 案例 1: 仅包含邮箱
        ("Please email me at support@taiga.io for details.", "Please email me at [EMAIL] for details."),
        # 案例 2: 包含多种格式的电话号码 (带空格和破折号)
        ("Call me at 138-0000-1111 or 555 1234.", "Call me at [PHONE] or [PHONE]."),
        # 案例 3: 包含身份证号的混合文本
        ("User's ID is 330101198005012345, must be secured.", "User's ID is [ID], must be secured."),
        # 案例 4: 包含敏感词组的文本 (已覆盖银行卡号)
        ("My card 6228000011112222 should be safe.", "My card [BANKCARD] should be safe."),
        # 案例 5: 不包含任何敏感信息的文本
        ("This is a clean user requirement.", "This is a clean user requirement."),
    ]
)
def test_anonymize_multiple_cases(input_text, expected_output):
    """测试 anonymize 函数处理多种敏感信息模式的能力。"""
    result = anonymize(input_text)
    print(f"\nRaw: {input_text}\nAnonymized: {result}")
    assert result == expected_output


@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        # 案例 1: 多个链接和 HTML 标签
        ("<h1>Title</h1> Check <a href='https://a.com'>Link A</a> and https://b.net.", "Title Check and"),
        # 案例 2: 仅包含额外的空格和换行符
        ("   Requirement\nwith\r\nnewlines.   ", "Requirement with newlines."),
        # 案例 3: 包含 JavaScript 脚本 (需要移除)
        ("Text before. <script>alert('xss')</script> Text after.", "Text before. Text after."),
        # 案例 4: 文本已干净 (边界情况)
        ("Clean text.", "Clean text."),
    ]
)
def test_clean_text_multiple_cases(input_text, expected_output):
    """测试 clean_text 函数移除 HTML、URL 和规范化空格的能力。"""
    result = clean_text(input_text)
    print(f"\nRaw: {input_text}\nCleaned: {result}")
    assert result == expected_output


@pytest.mark.parametrize(
    "input_text, expected_output",
    [
        # 案例 1: 包含所有元素的混合文本
        ("Call 13912345678, email user@corp.com, and check <p>this page: http://bug.com/.</p>", "Call [PHONE], email [EMAIL], and check this page:"),
        # 案例 2: 仅包含需要规范化的空格
        ("   Spaces   and   tabs\t\t\t", "Spaces and tabs"),
        # 案例 3: 包含敏感词和标签，但无链接
        ("The ID: 110101198001011234. <b>Important!</b>", "The ID: [ID]. Important!"),
        # 案例 4: 复杂输入，包含多个敏感信息
        ("My card 6228000011112222, phone 13000001111, and site https://secret.com/.", "My card [BANKCARD], phone [PHONE], and site"),
    ]
)
def test_preprocess_multiple_cases(input_text, expected_output):
    """测试整个 preprocess 管道的端到端效果。"""
    result = preprocess(input_text)
    print(f"\nRaw: {input_text}\nPreprocessed: {result}")
    assert result == expected_output
