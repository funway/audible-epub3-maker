import pytest
from audible_epub3_gen import config

def test_config_reads_env(monkeypatch):
    # 模拟系统环境变量
    monkeypatch.setenv("AZURE_TTS_KEY", "fake_key")
    monkeypatch.setenv("AZURE_TTS_REGION", "westus")

    # 重新加载 config 模块
    # 有时需要强制 reload，否则之前 import 的值不会更新
    import importlib
    importlib.reload(config)

    assert config.AZURE_TTS_KEY == "fake_key"
    assert config.AZURE_TTS_REGION == "westus"
