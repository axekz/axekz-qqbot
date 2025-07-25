from pathlib import Path

import nonebot
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="axekz",
    description="axekz 服务器插件",
    usage="",
    config=Config,
)


axekz_config = get_plugin_config(Config)

API_BASE = axekz_config.api_base

sub_plugins = nonebot.load_plugins(
    str(Path(__file__).parent.joinpath("plugins").resolve())
)
