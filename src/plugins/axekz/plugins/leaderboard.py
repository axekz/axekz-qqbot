from decimal import Decimal

from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg
from nonebot.plugin import on_command
from sqlmodel import select, func

from ..core.db.crud import get_top_ljpk_players
from ..core.db.deps import SessionDep
from ..core.db.models import User

top_coins = on_command('top', aliases={'排行', '排行榜'})


@top_coins.handle()
async def _(session: SessionDep, args: Message = CommandArg()):
    arg = args.extract_plain_text().strip()

    if 'ljpk' in arg:
        data = await get_top_ljpk_players()
        if '-r' in arg or '--reverse' in arg:
            data = data[::-1]

        msg = "╔═══LJPK排行榜═══╗\n"
        for idx, user in enumerate(data[:10], 1):
            msg += f"{idx}. {user.nickname} | 胜率: {user.winrate}% | 总场次: {user.total_matches} | 平均距离: {user.avg_distance} | 净胜: {user.net_coins:,}\n"
        return await top_coins.send(msg)

    # 斧币排行
    limit = 10
    statement = select(User).order_by(User.coins.desc()).limit(limit)
    results = session.exec(statement).all()

    total_coins_statement = select(func.sum(User.coins))
    total_coins = session.exec(total_coins_statement).one_or_none()
    total_coins = float(total_coins) if isinstance(total_coins, Decimal) else total_coins

    if results:
        msg = f"╔═══硬币排行榜(总计: {total_coins:,})═══╗\n"
        total_top_user_coins = 0.0
        for idx, user in enumerate(results, 1):
            percentage = (user.coins / total_coins * 100) if total_coins > 0 else 0
            total_top_user_coins += user.coins
            msg += f"{idx}. {user.nickname} ({user.qid}) - {user.coins:,} ({percentage:.2f}%)\n"
        print(type(total_top_user_coins))

        total_top_percentage = total_top_user_coins / total_coins * 100
        msg += f"这 {limit} 人总共占有 {total_top_percentage:.2f}% 的财富"

    else:
        msg = "No users found."

    await top_coins.send(msg)
    return None
