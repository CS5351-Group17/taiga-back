import sys
import importlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ================== 📁 路径配置区 (已根据你的路径修改) ==================

# 1. 业务模块的文件名 (不带 .py 后缀)
# 注意：根据你提供的路径，文件名是 doubai_ai.py
TARGET_MODULE_NAME = "doubai_ai"

# 2. 业务代码所在的文件夹 (相对于当前测试文件的路径)
#    tests/unit/  --> ../  --> tests/
#    tests/       --> ../  --> taiga-back/ (项目根目录)
#    taiga-back/  --> taiga/
REL_PATH_TO_SRC = "../../taiga"

# ================== 🛠️ 自动路径注入逻辑 ==================

# 获取当前测试文件 (test_doubao_ai.py) 的绝对路径
current_test_path = Path(__file__).resolve().parent

# 计算业务代码目录 (/Users/.../taiga) 的绝对路径
source_dir = (current_test_path / REL_PATH_TO_SRC).resolve()

# 将业务目录加入 Python 搜索路径，确保能 import doubai_ai
if str(source_dir) not in sys.path:
    sys.path.insert(0, str(source_dir))


# ================== 🧪 测试辅助功能 ==================

@pytest.fixture
def mock_deps():
    """
    Mock 外部依赖，防止业务代码 import 时产生副作用 (读文件/联网)。
    """
    with patch("dotenv.dotenv_values") as mock_dotenv, \
            patch("openai.OpenAI") as mock_openai_cls, \
            patch("pathlib.Path.exists") as mock_path_exists:
        # 默认行为：假装环境一切正常
        mock_path_exists.return_value = True
        mock_dotenv.return_value = {"ARK_API_KEY": "sk-mock-default"}

        yield mock_dotenv, mock_openai_cls, mock_path_exists


def reload_target_module():
    """
    强制重载目标模块。
    用于在不同测试用例中重置全局变量 (client, cfg 等) 的状态。
    """
    if TARGET_MODULE_NAME in sys.modules:
        return importlib.reload(sys.modules[TARGET_MODULE_NAME])
    else:
        return importlib.import_module(TARGET_MODULE_NAME)


# ================== ✅ 测试用例 ==================

def test_path_setup():
    """TC00: 验证路径配置是否正确"""
    # 如果这里报错，说明路径算错了
    err_msg = f"无法定位业务代码，请检查路径: {source_dir}"
    assert source_dir.exists(), err_msg
    assert (source_dir / f"{TARGET_MODULE_NAME}.py").exists(), f"找不到 {TARGET_MODULE_NAME}.py"


def test_load_env_file_not_found():
    """TC01: .env 不存在 -> FileNotFoundError"""
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError) as exc:
            reload_target_module()
    assert "未找到" in str(exc.value)


def test_init_runtime_error_no_key():
    """TC02: .env 无 Key -> RuntimeError"""
    with patch("pathlib.Path.exists", return_value=True), \
            patch("dotenv.dotenv_values", return_value={}):
        with pytest.raises(RuntimeError) as exc:
            reload_target_module()
    assert "请在 .env 中设置" in str(exc.value)


def test_client_init_success(mock_deps):
    """TC03: 正常初始化"""
    mock_dotenv, mock_openai_cls, _ = mock_deps

    mock_dotenv.return_value = {
        "ARK_API_KEY": "sk-real-key",
        "ARK_BASE_URL": "https://api.ark.volces.com"
    }

    module = reload_target_module()

    # 验证 OpenAI 初始化
    mock_openai_cls.assert_called_once()
    kwargs = mock_openai_cls.call_args[1]
    assert kwargs["api_key"] == "sk-real-key"
    assert module.client is not None


def test_ask_once_normal(mock_deps):
    """TC04: 正常对话"""
    _, mock_openai_cls, _ = mock_deps

    # Mock 响应结构
    mock_instance = mock_openai_cls.return_value
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = "Testing Response"
    mock_instance.chat.completions.create.return_value = mock_resp

    module = reload_target_module()

    res = module.ask_once("Q", "Prompt")
    assert res == "Testing Response"


def test_ask_once_api_error(mock_deps, capsys):
    """TC05: API 结构异常"""
    _, mock_openai_cls, _ = mock_deps

    # 模拟崩溃
    mock_instance = mock_openai_cls.return_value
    mock_instance.chat.completions.create.return_value = object()

    module = reload_target_module()

    res = module.ask_once("Q", "Prompt")
    captured = capsys.readouterr()

    assert res == ""
    assert "warn: API 返回结构异常" in captured.out