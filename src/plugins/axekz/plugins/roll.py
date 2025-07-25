import random
from datetime import datetime, timedelta
from math import ceil
from textwrap import dedent

from nonebot import get_bot, on_command
from nonebot.adapters.onebot.v11 import Bot, MessageSegment, MessageEvent
from nonebot_plugin_apscheduler import scheduler
from sqlmodel import Session, select

from .. import axekz_config
from ..core.db import engine
from ..core.db.models import Sign, User, Roll, TransactionType, CoinTransaction


async def daily_asset_tax():
    print("开始每日资产税收...")

    with Session(engine) as session:
        users = session.exec(select(User)).all()
        tax_records = []

        for user in users:
            if user.coins < 1:
                continue

            tax_amount = ceil(user.coins / 1000)

            user.coins -= tax_amount
            tax_records.append(CoinTransaction(
                user_id=user.qid,
                amount=-tax_amount,
                type=TransactionType.TAX,
                description=f"每日资产税收: {tax_amount}"
            ))
            session.add(user)

        if tax_records:
            session.add_all(tax_records)
            session.commit()
            print(f"已成功扣除资产税，处理 {len(tax_records)} 位用户")
        else:
            print("无可扣税用户，无操作")


@scheduler.scheduled_job("cron", hour="1", minute="0", id="daily_tax")
async def run_daily_asset_tax():
    await daily_asset_tax()


# @scheduler.scheduled_job("cron", hour="0", minute="0", id="roll")
async def daily_roll():
    bot: Bot = get_bot()
    yesterday = datetime.now() - timedelta(days=1)
    start_of_yesterday = datetime(yesterday.year, yesterday.month, yesterday.day)
    end_of_yesterday = start_of_yesterday + timedelta(days=1)

    with Session(engine) as session:
        statement = select(Sign).where(
            Sign.signed_at >= start_of_yesterday,
            Sign.signed_at < end_of_yesterday
        )
        results = session.exec(statement).all()

        if not results:
            return

        total_coins = sum(sign.earned_coins for sign in results)
        signers = len(results)
        prize = int((total_coins ** 0.5) * 10)

        winner_sign = random.choice(results)
        winner: User | None = session.get(User, winner_sign.qid)

        if winner:
            winner.coins += int(prize)
            session.add(winner)

            roll = Roll(
                signers=signers,
                prize=prize,
                winner_qid=winner.qid
            )
            session.add(roll)
            session.commit()

        content = dedent(f"""
                ╔═══每日抽奖═══╗
                ║　签到自动参与
                ║　参与人数 {signers}
                ║　恭喜
                ║　{winner.qid}
                ║　{winner.nickname}
                ║　获得了 {prize} 硬币！
                ╚══════════╝
            """).strip()

        at = MessageSegment.at(winner_sign.signed_at)
        msg = at+content
        try:
            await bot.send_group_msg(
                group_id=axekz_config.group_id,
                message=msg
            )
            await bot.send_group_msg(
                group_id=axekz_config.mini_group_id,
                message=msg
            )
        except Exception as e:
            await bot.send_group_msg(
                group_id=axekz_config.group_id,
                message=content
            )
            await bot.send_group_msg(
                group_id=axekz_config.mini_group_id,
                message=content
            )
