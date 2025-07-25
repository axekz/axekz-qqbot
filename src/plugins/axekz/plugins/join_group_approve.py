import asyncio
import re
from json import JSONDecodeError

import httpx
import nonebot
from nonebot import on_request
from nonebot.adapters.onebot.v11.bot import Bot
from nonebot.adapters.onebot.v11.event import GroupRequestEvent
from nonebot.adapters.onebot.v11.message import MessageSegment

from .. import axekz_config
from ..core.db.deps import SessionDep
from ..core.db.models import User

join_group = on_request(
    priority=1,
    block=True
)


def validate_steamid(steamid):
    steamid2_pattern = re.compile(r"^STEAM_[01]:[01]:\d+$")
    steamid64_pattern = re.compile(r"^7656119\d{10}$")
    if steamid2_pattern.match(steamid) or steamid64_pattern.match(steamid):
        return True
    else:
        return False


async def check_comment(comment):
    url = f'https://api.gokz.top/leaderboard/{comment}?mode=kz_timer'
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        try:
            resp = resp.json()
        except JSONDecodeError:
            return False
        if len(resp) == 0:
            return False
        else:
            return resp.get('name', False)


@join_group.handle()
async def _grh(bot: Bot, event: GroupRequestEvent, session: SessionDep):
    if event.sub_type == 'add':
        user: User | None = session.get(User, event.user_id)
        # 白名单群
        if event.group_id == axekz_config.mini_group_id:
            if not user:
                reason = f'{event.user_id} 未绑定steamid'
                # await event.reject(bot, reason=reason)
                return await join_group.finish('入群失败: ' + reason)

            if not user.is_whitelist:
                reason = f'{user.nickname}\nQQ:{event.user_id}\nsteamid: {user.steamid}\n 非白名单'
                # await event.reject(bot, reason=reason)
                return await join_group.finish('入群失败: ' + reason)

            await event.approve(bot)
            await asyncio.sleep(2)
            await bot.set_group_card(group_id=event.group_id, user_id=event.user_id, card=user.nickname)
            return await join_group.finish(
                MessageSegment.at(event.user_id) + '欢迎加入本群!')

        # 大群 绑定过steamid直接同意
        if user:
            await event.approve(bot)
            await asyncio.sleep(2)
            await bot.set_group_card(group_id=event.group_id, user_id=event.user_id, card=user.nickname)
            return

        # 验证steamid
        comment = event.comment.strip()
        steamid: str = re.findall(re.compile('答案：(.*)'), comment)[0].strip()

        # 格式不对直接拒绝
        if not validate_steamid(steamid):
            reason = '你输入的SteamID格式不正确'
            await join_group.send(f'{event.user_id} 申请入群失败\n答案: {steamid}\n原因: {reason}')
            await event.reject(bot, reason=reason)
            return
        else:
            steam_name = await check_comment(steamid)
            await event.approve(bot)
            await asyncio.sleep(2)
            await bot.set_group_card(group_id=event.group_id, user_id=event.user_id, card=steam_name)
            await join_group.send(MessageSegment.at(event.user_id) + f'欢迎 {steam_name} 加入本群\nsteamid: {steamid}')
            await join_group.send(MessageSegment.at(3889049185) + f'/kz -s {steamid}')

        # if steamid != "":
        #     if steam_name is False:
        #         reason = f'steamid: {steamid} 认证错误，未找到该steamid的玩家，请检查steamid是否正确，或是否至少上传过一张kzt全球记录'
        #         # await event.reject(bot, reason=reason)
        #         await join_group.send(f'{event.user_id} 入群申请失败\n{reason}')
        #         await join_group.send(f'/kz -s {steamid}')
        #     else:

        # else:
        #     reason = f'steamid: {steamid} 认证错误，请输入steamid'
        #     await event.reject(bot, reason=reason)
        #     await join_group.finish(f'{event.user_id} 入群申请失败\n{reason}')
