from textwrap import dedent

from nonebot import get_bot
from nonebot_plugin_apscheduler import scheduler

from .. import API_BASE, axekz_config
from ..core.utils.helpers import aio_get


def format_change(value):
    return f"+{value}" if value > 0 else str(value)


@scheduler.scheduled_job("cron", minute="5", hour="6", id="xxx")
async def run_every_minute():
    bot = get_bot()
    data = await aio_get(f'{API_BASE}/statistics/daily')
    today = data['today']
    alt = data['change']
    content = dedent(f"""
        {today['date']} 活跃:
        日活玩家: {today['player_count']:>4} 人 ({format_change(alt['player_count'])})
        总玩家数: {today['player_total']:>4} 人 ({format_change(alt['player_total'])})
        完成计时: {today['run_count']:>4} 次 ({format_change(alt['run_count'])})
    """).strip()
    await bot.send_group_msg(group_id=axekz_config.group_id, message=content)
