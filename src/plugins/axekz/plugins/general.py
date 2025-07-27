from nonebot import logger
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message, Bot, GroupMessageEvent, \
    PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import on_command
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
import base64
import time

from . import BIND_PROMPT
from ..core import get_bank
from ..core.db.models import User, CoinTransaction, TransactionType
from ..core.db.deps import SessionDep
from ..core.utils.command_helper import CommandData
from ..core.utils.convertors import convert_steamid
from ..core.utils.formatters import format_kzmode
from ..core.utils.helpers import api_get

BIND_SECRET = "ChangeThisSecret!"

bind = on_command('绑定', priority=10, block=True)
mode = on_command('mode')
test = on_command('test')
add_user = on_command('adduser', permission=SUPERUSER)
info = on_command('info')
rename = on_command('rename')
special_title = on_command('title', aliases={'头衔'})
transactions = on_command("transactions", aliases={"账单", "账单记录", "硬币记录", "coinlog"})
bind_token = on_command("bind", priority=10)

RENAME_COST = 20
TITLE_COST = 100


def decode_bind_token(token: str, secret: str) -> tuple[int, int]:
    """解码游戏端生成的绑定令牌，返回 (steamid32, expiry_timestamp)"""
    raw = base64.b64decode(token)
    key = secret.encode()
    key_len = len(key)
    decrypted_bytes = bytes(raw[i] ^ key[i % key_len] for i in range(len(raw)))
    steamid_str, expiry_str = decrypted_bytes.decode().split("|", 1)
    return int(steamid_str), int(expiry_str)


@bind_token.handle()
async def handle_bind_token(bot: Bot, event: MessageEvent, session: SessionDep):
    # 如果不是私聊，则提醒用户去私聊使用
    if not isinstance(event, PrivateMessageEvent):
        try:
            await bot.delete_msg(message_id=event.message_id)
        except Exception:
            # 撤回失败时可忽略或者记录日志
            pass

    user_id = event.get_user_id()
    # 取出参数
    args = event.get_plaintext().strip().split(maxsplit=1)
    if len(args) < 2:
        return await bind_token.finish("请在 /bind 后提供绑定码，例如 /bind AbCdEfG...\n进入服务器输入 /bindqq 即可获取")

    token_arg = args[1]
    try:
        steamid32, expiry = decode_bind_token(token_arg, BIND_SECRET)
        if expiry < int(time.time()):
            return await bind_token.finish("绑定令牌已过期，请在游戏中重新生成。")
        steamid = str(steamid32)
        steamid = convert_steamid(steamid, '64')
    except Exception:
        return await bind_token.finish("绑定码格式不正确，请确认后重新发送。")

    # 查询昵称并保存用户信息
    try:
        playtime_data = await api_get("/players/playtime", {"steamid": steamid})
        nickname = playtime_data.get("name", "Unknown") if playtime_data else "Unknown"
    except Exception:
        return await bind_token.finish("未能获取玩家在服务器的信息，请尝试断开与服务器的连接后再绑定")

    user = User(qid=user_id, steamid=steamid, nickname=nickname)
    try:
        session.add(user)
        session.commit()
        session.refresh(user)
    except IntegrityError:
        return await bind_token.finish("该 QQ 已绑定过，不需要重复绑定。")

    reply = MessageSegment.reply(event.message_id)
    await bind_token.send(reply + f"绑定成功\n{user}")


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

    if user.coins < TITLE_COST:
        return await special_title.send(f"没有足够的硬币，需要 {TITLE_COST}, 你有 {user.coins}")

    title = args.extract_plain_text().strip()
    length = 18
    if len(title) > length:
        return await special_title.send(f'头衔过长，不能大于 {length} 个字符')

    user.coins -= TITLE_COST

    # 给银行转账
    bank = get_bank()
    bank.coins += TITLE_COST

    # 添加交易记录
    transaction = CoinTransaction(
        user_id=user.qid,
        amount=-TITLE_COST,
        type=TransactionType.PURCHASE,
        description=f"设置头衔为「{title}」"
    )

    session.add_all([user, bank, transaction])

    try:
        session.commit()
        session.refresh(user)
        session.refresh(bank)
    except Exception as e:
        session.rollback()
        logger.error(e)
        return await special_title.finish(repr(e))

    await bot.set_group_special_title(group_id=event.group_id, user_id=event.user_id, special_title=title)
    return await special_title.send(f'头衔 {title} 设置成功, 花费 {TITLE_COST}, 余额 {user.coins}', at_sender=True)


@rename.handle()
async def _(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)
    elif user.coins < RENAME_COST:
        return await rename.finish(f'您的余额不足\n需要: {RENAME_COST}, 您有: {user.coins}')

    name = args.extract_plain_text().strip()
    if not name:
        return await rename.finish(f'请输入昵称, 改名需花费 {RENAME_COST} 硬币')

    user.nickname = name
    user.coins -= RENAME_COST

    bank = get_bank()
    bank.coins += RENAME_COST

    # 添加交易记录
    transaction = CoinTransaction(
        user_id=user.qid,
        amount=-RENAME_COST,
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

    return await rename.finish(f'成功修改昵称为: {user.nickname}\n余额: {user.coins} (-{RENAME_COST})')


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
    except Exception:
        return await bind.finish(f"未能获取玩家在服务器的信息(你进入过本服务器吗？)")

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
