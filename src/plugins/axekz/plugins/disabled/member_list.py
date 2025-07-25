import json

from nonebot import logger
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot

ml = on_command('ml')


# @ml.handle()
async def _(bot: Bot):
    logger.info("Writing member list")
    members = await bot.get_group_member_list(group_id=681119576)
    qid_list = "\n".join([str(member['user_id']) for member in members])
    await ml.send(qid_list)

    with open("members.json", "w", encoding='utf-8') as f:
        json.dump(members, f, indent=4)
