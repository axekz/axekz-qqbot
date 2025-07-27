import math
import random
from datetime import datetime, timedelta

from nonebot.adapters.onebot.v11 import MessageEvent, Message, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import on_command
from sqlmodel import select

from .general import bind_steamid
from ..core import get_bank, BANK_QID
from ..core.db.deps import SessionDep
from ..core.db.models import Sign, CoinTransaction, TransactionType
from ..core.db.models import User, Allowance
from ..core.utils.command_helper import CommandData

sign = on_command('签到', aliases={'qd', 'sign'})
allowance = on_command('低保', aliases={'db'})
give = on_command('give', aliases={'gv', '赠送'})
daily_task = on_command('每日任务', aliases={'daily_task', 'mrrw'})


@give.handle()
async def _(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await give.send(cd.error, at_sender=True)
    if not cd.user2:
        return await give.send('未指定目标用户', at_sender=True)

    if cd.args:
        try:
            amount = int(cd.args[0])
            if amount < 1 and cd.user1.qid != '986668919':
                return await give.send("投入不能小于1", at_sender=True)
        except ValueError:
            return await give.send("投入输入格式不正确", at_sender=True)
    else:
        amount = 20

    # 计算 1% 税，至少为 1 硬币
    tax = math.ceil(amount * 0.01)
    amount_after_tax = amount - tax

    if cd.user1.coins < amount:
        return await give.send(f"余额不足 你有: {cd.user1.coins} 需要 {amount}", at_sender=True)

    cd.user1.coins -= amount
    cd.user2.coins += amount_after_tax
    bank = get_bank()
    bank.coins += tax

    session.add_all([cd.user1, cd.user2, bank])

    # 添加交易记录
    session.add_all([
        CoinTransaction(
            user_id=cd.user1.qid,
            amount=-amount,
            type=TransactionType.GIVE,
            description=f"转账给 {cd.user2.nickname}（含税）"
        ),
        CoinTransaction(
            user_id=cd.user2.qid,
            amount=amount_after_tax,
            type=TransactionType.GIVE,
            description=f"收到来自 {cd.user1.nickname} 的转账（税后）"
        ),
        CoinTransaction(
            user_id="bank",
            amount=tax,
            type=TransactionType.GIVE,
            description=f"转账税收来自 {cd.user1.nickname}"
        )
    ])

    session.commit()
    session.refresh(cd.user1)
    session.refresh(cd.user2)

    return await give.send(
        f"赠送给 {cd.user2.nickname} {amount_after_tax} 硬币成功（原始 {amount}，税收 {tax}）\n"
        f"对方余额 {cd.user2.coins}(+{amount_after_tax})\n"
        f"你的余额 {cd.user1.coins}(-{amount})",
        at_sender=True
    )


@sign.handle()
async def _(event: GroupMessageEvent, session: SessionDep):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    today = datetime.now().date()
    sign_in_today = session.exec(
        select(Sign).where(
            Sign.qid == user_id,
            Sign.signed_at >= today,
            Sign.signed_at < today + timedelta(days=1)
        )
    ).first()

    if sign_in_today:
        return await sign.finish(f"今天已经签到过了，请明天再来！\n余额: {user.coins}")

    # 获取硬币最多的用户（硬币 > 100）
    top_users = session.exec(
        select(User)
        .where(User.qid != BANK_QID, User.coins >= 100)
        .order_by(User.coins.desc())
        .limit(3)
    ).all()

    if not top_users:
        return await sign.finish("今天没有资本家可以签到吸血了")

    weights = [3, 2, 1][:len(top_users)]
    giver = random.choices(top_users, weights=weights, k=1)[0]

    # 正态分布获取硬币数（默认 20±5）
    earned_coins = round(random.gauss(20, 5))
    earned_coins = max(1, earned_coins)

    # 秘密群组双倍奖励
    if event.group_id == 1044299554:
        earned_coins *= 2

    # 硬币转移
    giver.coins -= earned_coins
    user.coins += earned_coins

    session.add_all([
        CoinTransaction(
            user_id=giver.qid,
            amount=-earned_coins,
            type=TransactionType.SIGN,
            description=f"签到被 {user.nickname} 薅走"
        ),
        CoinTransaction(
            user_id=user.qid,
            amount=earned_coins,
            type=TransactionType.SIGN,
            description=f"签到从 {giver.nickname} 薅得"
        )
    ])

    # 写入签到记录
    new_sign = Sign(qid=user_id, earned_coins=earned_coins)

    session.add(new_sign)
    session.add(giver)
    session.add(user)
    session.commit()
    session.refresh(user)
    session.refresh(giver)

    await sign.send(
        f'签到成功，从 {giver.nickname} 身上薅了 {earned_coins} 硬币！\n'
        f'当前余额：{user.coins} 对方剩余：{giver.coins}'
    )


# @allowance.handle()
# async def _(event: MessageEvent, session: SessionDep):
#     await allowance.finish('该功能已停用')
#     user_id = event.get_user_id()
#     user: User | None = session.get(User, user_id)
#     if not user:
#         user = await bind_steamid(event, session)
#
#     # Check if the user has 0 coins
#     if user.coins >= 10:
#         return await allowance.finish("只有余额小于10的用户可以领取低保")
#
#     # Check if the user has signed today
#     today = datetime.now().date()
#     sign_in_today = session.exec(
#         select(Sign).where(
#             Sign.qid == user_id,
#             Sign.signed_at >= today,
#             Sign.signed_at < today + timedelta(days=1)
#         )
#     ).first()
#     if not sign_in_today:
#         return await allowance.finish(f"今天你还未签到, 请签到后再尝试领取\n余额: {user.coins}")
#
#     # Check if the user has already received allowance 3 times today
#     allowance_count_today = session.exec(
#         select(Allowance).where(
#             Allowance.receiver_qid == user_id,
#             Allowance.date >= today,
#             Allowance.date < today + timedelta(days=1)
#         )
#     ).all()
#
#     if len(allowance_count_today) >= 3:
#         return await allowance.finish("今天已经领取了3次低保，无法再领取")
#
#     # Get the top 3 users with the most coins (with coins > 100)
#     top_users = session.exec(
#         select(User)
#         .where(User.qid != BANK_QID, User.coins >= 100)
#         .order_by(User.coins.desc())
#         .limit(3)
#     ).all()
#     print(top_users)
#     if not top_users:
#         return await allowance.finish("没有资本家可以抢劫了")
#
#     # Randomly choose one user as the giver
#     giver = random.choice(top_users)
#
#     # 5% possibility that earned coins will be 5% of giver's coins
#     # if random.random() <= 0.05:
#     #     earned_coins = round(0.05 * giver.coins)
#     # else:
#     # Give random coins based on normal distribution
#     earned_coins = round(random.gauss(20, 5))
#     earned_coins = 1 if earned_coins < 1 else earned_coins
#
#     # Update the giver and receiver's coins
#     giver.coins -= earned_coins
#     user.coins += earned_coins
#
#     # Store the transaction in the Allowance table
#     new_allowance = Allowance(
#         giver_qid=giver.qid,
#         receiver_qid=user.qid,
#         amount=earned_coins,
#         date=datetime.now()
#     )
#
#     session.add(new_allowance)
#     session.add(giver)
#     session.add(user)
#     session.commit()
#     session.refresh(giver)
#     session.refresh(user)
#
#     await allowance.send(f'低保领取成功, 获得 {earned_coins} 硬币\n当前余额：{user.coins} 今天还可以领取 {len(allowance_count_today) + 1}/3 次\n来自用户: {giver.nickname} {giver.coins} (-{earned_coins})')

    
# @daily_task.handle()
# async def _(event: MessageEvent, session: SessionDep):
#     await daily_task.finish('该功能暂不可用')
#     user_id = event.user_id
#     user: User | None = session.get(User, user_id)
#     if not user:
#         user = await bind_steamid(event, session)
#     # Check if the user already has tasks
#     query = select(DailyTask).where(DailyTask.user_id == user_id)
#     result = session.execute(query)
#     tasks: list[DailyTask] | None = result.scalars().all()
#
#     if not tasks:
#         # No tasks found, create a new task for the user
#         daily_online_task = DailyTask(
#             user_id=str(user_id),
#             task_type=TaskTypeEnum.DAILY_ONLINE,  # You can set the task type here
#             bonus=20
#         )
#
#         daily_map_pb_finish = DailyTask(
#             user_id=str(user_id),
#             task_type=TaskTypeEnum.DAILY_MAP_PB,
#             mode=user.mode,
#             bonus=50
#         )
#
#         tasks.append(daily_online_task)
#         tasks.append(daily_map_pb_finish)
#         session.add_all(tasks)
#         session.commit()
#         session.refresh(daily_online_task)
#         session.refresh(daily_map_pb_finish)
#         return await daily_task.send('每日任务领取成功')
#
#     else:
#         unfinished_tasks = [task for task in tasks if not task.finished_at]
#         if not unfinished_tasks:
#             return await daily_task.send("你已完成所有每日任务，请明天再来领取新的任务。")
#
#         for task in unfinished_tasks:
#             if task.task_type == TaskTypeEnum.DAILY_ONLINE:
#                 online_data = await api_get('/players/playtime', params={'steamid': user.steamid})
#                 if online_data and 'lastseen' in online_data:
#                     last_seen_str = online_data['lastseen']
#                     last_seen_datetime = datetime.fromisoformat(last_seen_str)
#
#                     # Check if the date part of lastseen is today's date
#                     if last_seen_datetime.date() == datetime.today().date():
#                         # Mark the task as completed
#                         task.finished_at = datetime.now()
#                         user.coins += task.bonus
#                         session.add(task)
#                         session.add(user)
#                         session.commit()
#                         session.refresh(user)
#
#                         return await daily_task.send(f'每日登陆任务已完成, 获得 {task.bonus}, 余额 {user.coins}')
#
#             elif task.task_type == TaskTypeEnum.DAILY_MAP_PB:
#                 player_recent_data = await fetch_personal_recent(user.steamid, mode=task.mode)
#                 print(player_recent_data)
#                 if player_recent_data and player_recent_data['server_id'] == 1683:
#                     player_recent_datetime = datetime.fromisoformat(player_recent_data['created_on'])
#
#                     if player_recent_datetime.date() == datetime.today().date():
#                         # Mark the task as completed
#                         task.finished_at = datetime.now()
#                         user.coins += task.bonus
#                         session.add(task)
#                         session.add(user)
#                         session.commit()
#                         session.refresh(user)
#                         return await daily_task.send(f'每日地图完成任务已完成, 获得 {task.bonus}, 余额 {user.coins}')
#
#         # Send a message with the status of unfinished tasks
#
#         unfinished_task_descriptions = "\n".join(
#             [f"任务: {task.task_type} 奖励 {task.bonus} 硬币 - 未完成" for task in unfinished_tasks])
#
#         await daily_task.send(f"您有以下未完成的任务:\n{unfinished_task_descriptions}")

