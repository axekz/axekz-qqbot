from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Message, Bot, MessageEvent
from nonebot.params import CommandArg

from src.plugins.axekz.core import get_bank
from src.plugins.axekz.core.db.deps import SessionDep
from src.plugins.axekz.core.utils.command_helper import CommandData

mute = on_command('mute', aliases={'禁言'})
kick = on_command('kick', aliases={'踢出'})
admin = on_command('admin')
group_rename = on_command('group_rename', aliases={'群名'})

ADMIN_COST = 1500
KICK_COST = 1000


@kick.handle()
async def _(bot: Bot, event: GroupMessageEvent, session: SessionDep, args: Message = CommandArg()):
    bot_info = await bot.get_group_member_info(user_id=int(bot.self_id), group_id=event.group_id, no_cache=False)
    if bot_info['role'] == 'member':
        return await admin.send('机器人在本群不是管理员，无法踢出')

    cd = CommandData(event, args)
    if cd.error:
        return await mute.send(cd.error, at_sender=True)
    if not cd.user2:
        return await mute.send("未指定成员", at_sender=True)

    # 判定余额是否充足
    target_user_info = await bot.get_group_member_info(user_id=int(cd.user2.qid), group_id=event.group_id, no_cache=False)
    if target_user_info['role'] == 'admin':
        cost = int(ADMIN_COST * 0.8)
    else:
        cost = KICK_COST

    if cd.user1.coins < cost:
        return await mute.finish(f'没有足够的斧币，需要: {cost}, 你有 {cd.user1.coins}', at_sender=True)

    cd.user1.coins -= cost

    bank = get_bank()
    bank.coins += cost

    session.add(cd.user1)
    session.add(bank)
    session.commit()
    session.refresh(cd.user1)
    session.refresh(bank)

    await bot.set_group_kick(group_id=event.group_id, user_id=int(cd.user2.qid))
    await kick.send(f'踢出 {cd.user2.nickname} 成功，余额 {cd.user1.coins}', at_sender=True)
    return None


@mute.handle()
async def _(bot: Bot, event: GroupMessageEvent, session: SessionDep, args: Message = CommandArg()):
    bot_info = await bot.get_group_member_info(user_id=int(bot.self_id), group_id=event.group_id, no_cache=False)
    if bot_info['role'] != 'admin':
        return await admin.send('机器人在本群不是管理员，无法禁言')

    reply = MessageSegment.reply(event.message_id)
    cd = CommandData(event, args)
    if cd.error:
        return await mute.send(reply + cd.error)
    if not cd.user2:
        return await mute.send(reply + "未指定成员")

    max_ban_sec = 600
    if cd.args:
        try:
            ban_seconds = int(cd.args[0])
            if ban_seconds < 1:
                return await mute.send(reply + "禁言时间不能小于 1 秒")
            if ban_seconds > max_ban_sec:
                return await mute.send(reply + f'禁言时间不能大于 {max_ban_sec} 秒')
        except ValueError:
            return await mute.send(reply + "禁言时间输入格式不正确")
    else:
        ban_seconds = 10

    cost = ban_seconds * 1
    if cd.user1.coins < cost:
        return await mute.finish(f'没有足够的斧币，需要: {cost}, 你有 {cd.user1.coins}', at_sender=True)

    bank = get_bank()
    cd.user1.coins -= cost
    bank.coins += cost
    session.add(cd.user1)
    session.add(bank)
    session.commit()
    session.refresh(cd.user1)

    await bot.set_group_ban(group_id=event.group_id, user_id=int(cd.user2.qid), duration=ban_seconds)
    await mute.finish(f'禁言成功，花费 {cost}, 剩余 {cd.user1.coins}', at_sender=True)


# @group_rename.handle()
# async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
#     group_name = args.extract_plain_text().strip()
#     await bot.set_group_name(group_id=event.group_id, group_name=group_name)


@admin.handle()
async def _(bot: Bot, event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    # bot_info = await bot.get_group_member_info(user_id=int(bot.self_id), group_id=event.group_id, no_cache=True)
    # if bot_info['role'] != 'owner':
    #     return await admin.send('机器人在本群不是群主，无法购买管理员')
    group_id = 188099455

    cd = CommandData(event, args)
    if cd.error:
        return await mute.send(cd.error, at_sender=True)
    if cd.user1.qid == '986668919':
        user_info = await bot.get_group_member_info(user_id=int(cd.user1.qid), group_id=group_id, no_cache=True)
        if user_info['role'] != 'admin':
            await bot.set_group_admin(group_id=group_id, user_id=int(cd.user1.qid), enable=True)
        else:
            await bot.set_group_admin(group_id=group_id, user_id=int(cd.user1.qid), enable=False)
    return None
    # 判定余额是否充足
    # if cd.user1.coins < ADMIN_COST:
    #     return await mute.finish(f'没有足够的斧币，需要: {ADMIN_COST}, 你有 {cd.user1.coins}', at_sender=True)
    #
    # cd.user1.coins -= ADMIN_COST
    # session.add(cd.user1)
    # session.commit()
    # session.refresh(cd.user1)
    #
    # if cd.user2:
    #     await bot.set_group_admin(group_id=event.group_id, user_id=int(cd.user2.qid), enable=False)
    #     await kick.send(f'卸载 {cd.user2.nickname} {cd.user2.qid} 的管理员成功，花费 {ADMIN_COST}，余额 {cd.user1.coins}', at_sender=True)
    # else:
    #     await bot.set_group_admin(group_id=event.group_id, user_id=int(cd.user1.qid), enable=True)
    #     await kick.send(f'购买管理员成功，花费 {ADMIN_COST}， 余额 {cd.user1.coins}', at_sender=True)
