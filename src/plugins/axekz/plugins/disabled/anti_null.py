from nonebot import Bot, on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent

from src.plugins.axekz import axekz_config
from src.plugins.axekz.core.db.deps import SessionDep
from src.plugins.axekz.core.db.models import User

anti_null = on_message(priority=15)

forbidden_keywords = ['null', 'alias', 'marco', '无冲', '脚本', '...', '。。。']
whitelist = ['1662947689', '3889049185']    # 机器人白名单


async def handle_ban(bot: Bot, event: GroupMessageEvent, keyword: str):
    await anti_null.send(f'群里禁止讨论 {keyword}!', at_sender=True)
    await bot.set_group_ban(
        group_id=event.group_id, user_id=event.user_id, duration=10)


@anti_null.handle()
async def _(bot: Bot, event: GroupMessageEvent, session: SessionDep):
    if event.group_id != axekz_config.group_id:
        return
    if str(event.user_id) in whitelist:
        return
    user: User | None = session.get(User, event.user_id)
    if user and user.is_whitelist:
        return

    message = event.raw_message.lower()
    for keyword in forbidden_keywords:
        if keyword in message:
            await handle_ban(bot, event, keyword)
            await anti_null.finish()
