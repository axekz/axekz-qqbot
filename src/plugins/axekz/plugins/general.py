from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message, Bot, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import on_command
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from . import BIND_PROMPT
from ..core import get_bank
from ..core.db.models import User, CoinTransaction, TransactionType
from ..core.db.deps import SessionDep
from ..core.utils.command_helper import CommandData
from ..core.utils.convertors import convert_steamid
from ..core.utils.formatters import format_kzmode
from ..core.utils.helpers import api_get

bind = on_command('绑定', priority=10, block=True)
mode = on_command('mode')
test = on_command('test')
add_user = on_command('adduser', permission=SUPERUSER)
info = on_command('info')
rename = on_command('rename')
special_title = on_command('title', aliases={'头衔'})
transactions = on_command("transactions", aliases={"账单", "账单记录", "硬币记录", "coinlog"})


@transactions.handle()
async def _(event: MessageEvent, session: SessionDep, arg: Message = CommandArg()):
    user_id = event.get_user_id()
    try:
        n = int(arg.extract_plain_text().strip()) if arg.extract_plain_text().strip() else 5
        n = min(max(n, 1), 20)  # 限制范围 1~20
    except ValueError:
        return await transactions.finish("请输入有效的数字，例如：/transactions 10")

    stmt = (
        select(CoinTransaction)
        .where(CoinTransaction.user_id == user_id)
        .order_by(CoinTransaction.created_at.desc())
        .limit(n)
    )
    results = session.exec(stmt).all()

    if not results:
        return await transactions.finish("你还没有任何硬币账单记录")

    content = f"最近 {len(results)} 条账单记录：\n"
    for tx in results:
        sign = "+" if tx.amount > 0 else "-"
        content += (
            f"[{tx.created_at.strftime('%m-%d %H:%M')}] {sign}{abs(tx.amount)} | "
            f"{tx.type} | {tx.description or '无备注'}\n"
        )

    await transactions.finish(content)


@special_title.handle()
async def _(bot: Bot, event: GroupMessageEvent, session: SessionDep, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    price = 20
    if user.coins < price:
        return await special_title.send(f"没有足够的硬币，需要 {price}, 你有 {user.coins}")

    title = args.extract_plain_text().strip()
    length = 18
    if len(title) > length:
        return await special_title.send(f'头衔过长，不能大于 {length} 个字符')

    user.coins -= price
    session.add(user)
    session.commit()
    session.refresh(user)

    await bot.set_group_special_title(group_id=event.group_id, user_id=event.user_id, special_title=title)
    await special_title.send(f'头衔 {title} 设置成功, 花费 {price}, 余额 {user.coins}', at_sender=True)


@rename.handle()
async def _(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    price = 20
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)
    elif user.coins < price:
        return await rename.finish(f'您的余额不足\n需要: {price}, 您有: {user.coins}')

    name = args.extract_plain_text().strip()
    if not name:
        return await rename.finish(f'请输入昵称, 改名需花费 {price} 硬币')

    user.nickname = name
    user.coins -= price

    bank = get_bank()
    bank.coins += price

    # 添加交易记录
    transaction = CoinTransaction(
        user_id=user.qid,
        amount=-price,
        type=TransactionType.PURCHASE,
        description=f"修改昵称为「{name}」"
    )

    session.add_all([user, bank, transaction])
    try:
        session.commit()
        session.refresh(user)
        session.refresh(bank)
    except Exception as e:
        session.rollback()
        logger.error(e)
        return await rename.finish(repr(e))

    return await rename.finish(f'成功修改昵称为: {user.nickname}\n余额: {user.coins} (-{price})')


@info.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await info.send(cd.error)
    user = cd.user2 if cd.user2 else cd.user1
    return await info.send(str(user))


@add_user.handle()
async def _(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    at_msg = event.get_message().copy()
    qid = None
    for segment in at_msg:
        if segment.type == 'at':
            qid = segment.data['qq']
            break

    if steamid := args.extract_plain_text().strip():
        steamid = convert_steamid(steamid, 64)
        playtime_data = await api_get('/players/playtime', {'steamid': steamid})
        nickname = playtime_data.get('name', 'Unknown') if playtime_data else 'Unknown'

        user = User(
            qid=qid,
            steamid=steamid,
            nickname=nickname
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        await add_user.send('添加成功\n' + str(user))


@mode.handle()
async def _(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        # user = await bind_steamid(event, session)
        return

    if mode_ := args.extract_plain_text():
        try:
            mode_ = format_kzmode(mode_, 'm')
        except ValueError:
            return await mode.finish(MessageSegment.reply(event.message_id) + "模式格式不正确")
    else:
        return await mode.finish(MessageSegment.reply(event.message_id) + "你模式都不给我我怎么帮你改ヽ(ー_ー)ノ")

    user.mode = mode_
    session.add(user)
    session.commit()
    session.refresh(user)

    await mode.finish(MessageSegment.reply(event.message_id) + f"模式已更新为: {mode_}")


@bind.handle()
async def bind_steamid(event: MessageEvent, session: SessionDep):
    user_id = event.get_user_id()
    data = await api_get(f'/players/qq/{user_id}', timeout=20)
    steamid = data.get('steamid', None)
    if steamid is None:
        return await bind.finish(BIND_PROMPT)

    try:
        playtime_data = await api_get('/players/playtime', {'steamid': steamid})
        nickname = playtime_data.get('name', 'Unknown') if playtime_data else 'Unknown'
    except Exception as e:
        return await bind.finish(f"{repr(e)}未能获取玩家在服务器的信息(你进入过本服务器吗？)")

    user = User(
        qid=user_id,
        steamid=steamid,
        nickname=nickname,
    )
    try:
        session.add(user)
        session.commit()
        session.refresh(user)
    except IntegrityError as e:
        return await bind.finish(f"用户已存在")

    reply = MessageSegment.reply(event.message_id)
    await bind.send(reply + f'绑定成功\n' + str(user))

    return user
