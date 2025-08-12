# file: red_packet_on_quit.py
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

from nonebot import on_notice, on_message, require, get_bot
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    GroupDecreaseNoticeEvent,
    MessageSegment,
)
from nonebot.log import logger
from nonebot_plugin_apscheduler import scheduler
from sqlmodel import Session

from src.plugins.axekz.core import get_bank, User, engine
from src.plugins.axekz.core.db.deps import SessionDep
from src.plugins.axekz.core.db.models import CoinTransaction, TransactionType

# === your project deps (adjust paths/names if different) ===


require("nonebot_plugin_apscheduler")


# ─────────────────────────────────────────────────────────────
# In-memory state
# ─────────────────────────────────────────────────────────────
@dataclass
class RedPacket:
    group_id: int
    quitter_qid: str
    coins: int
    bot_message_id: int
    created_at: datetime
    claimed: bool = False
    claimer_qid: Optional[str] = None


# Keyed by (group_id, bot_message_id)
_pending: Dict[Tuple[int, int], RedPacket] = {}

CLAIM_WINDOW_SEC = 60


# ─────────────────────────────────────────────────────────────
# Helper to finalize a packet if nobody claimed
# ─────────────────────────────────────────────────────────────
async def _finalize_if_unclaimed(group_id: int, bot_message_id: int):
    key = (group_id, bot_message_id)
    pkt = _pending.get(key)
    if not pkt or pkt.claimed:
        _pending.pop(key, None)
        return

    # get a bot to send messages
    bot: Bot = get_bot()
    if not bot:
        return

    # OPEN A REAL SESSION HERE (not SessionDep)
    with Session(engine) as session:
        quitter: User | None = session.get(User, pkt.quitter_qid)
        bank = get_bank()
        if not quitter:
            _pending.pop(key, None)
            return

        amount = min(quitter.coins, pkt.coins)
        if amount <= 0:
            _pending.pop(key, None)
            return

        quitter.coins -= amount
        bank.coins += amount

        session.add_all([
            CoinTransaction(
                user_id=quitter.qid,
                amount=-amount,
                type=TransactionType.LJPK,  # swap to RED_PACKET if you add it
                description="退群红包无人领取，转入国库"
            ),
            CoinTransaction(
                user_id="bank",
                amount=amount,
                type=TransactionType.LJPK,
                description=f"退群红包超时入库（来自 {quitter.nickname}）"
            ),
            bank,
            quitter,
        ])
        session.commit()

    try:
        await bot.send_group_msg(group_id=group_id, message=f"⏳ 无人领取，红包已入库（{amount}）")
    except Exception as e:
        logger.warning(f"[RedPacket] notify timeout failed: {e}")

    _pending.pop(key, None)


# ─────────────────────────────────────────────────────────────
# Notice: someone leaves the group
# ─────────────────────────────────────────────────────────────
leave_notice = on_notice(priority=5, block=False)


@leave_notice.handle()
async def _(bot: Bot, event: GroupDecreaseNoticeEvent, session: SessionDep):
    """
    Triggered when a user quits/is kicked from a group.
    If quitter has coins > 0, post a descriptive '抢红包' message and open a 60s claim window.
    """
    group_id = event.group_id
    quitter_qid = str(event.user_id)

    # Fetch user & coins
    user: User | None = session.get(User, quitter_qid)
    if not user or user.coins <= 0:
        return  # nothing to do

    amount = user.coins

    # Build descriptive message
    message_text = (
        f"🎉 抢红包来啦！\n"
        f"玩家 {user.nickname}（{quitter_qid}） 离开了群聊，留下了 {amount} 💰 硬币！\n\n"
        f"📜 规则：\n"
        f"1. 回复此条消息即可领取全部硬币\n"
        f"2. 仅限第一个回复的人获得\n"
        f"3. 有效时间：60 秒\n\n"
        f"🕒 超时无人领取时，硬币将自动转入中央银行"
    )

    # Post the red packet message
    try:
        resp = await bot.send_group_msg(group_id=group_id, message=message_text)
        bot_message_id = int(resp["message_id"])
    except Exception as e:
        logger.warning(f"[RedPacket] Failed to send packet msg: {e}")
        return

    pkt = RedPacket(
        group_id=group_id,
        quitter_qid=quitter_qid,
        coins=amount,
        bot_message_id=bot_message_id,
        created_at=datetime.now(),
    )
    _pending[(group_id, bot_message_id)] = pkt

    # Schedule a timeout in 60s
    run_at = datetime.now() + timedelta(seconds=CLAIM_WINDOW_SEC)
    scheduler.add_job(
        _finalize_if_unclaimed,
        "date",
        run_date=run_at,
        id=f"red_packet_timeout_{group_id}_{bot_message_id}",
        args=[group_id, bot_message_id],
        misfire_grace_time=10,
        coalesce=True,
        max_instances=1,
    )

# ─────────────────────────────────────────────────────────────
# Message: handle replies to claim the red packet
# ─────────────────────────────────────────────────────────────
claim_handler = on_message(priority=6, block=False)


@claim_handler.handle()
async def _(bot: Bot, event: GroupMessageEvent, session: SessionDep):
    """
    First user who REPLIES to the bot's '抢红包' message within 60s gets all coins.
    """
    if not event.reply:
        return

    try:
        replied_mid = int(event.reply.message_id)
    except Exception:
        return

    key = (event.group_id, replied_mid)
    pkt = _pending.get(key)
    if not pkt:
        return  # not a tracked packet

    # Check window
    if (datetime.now() - pkt.created_at).total_seconds() > CLAIM_WINDOW_SEC:
        # Let the timeout job handle it (or it's already processed)
        return

    if pkt.claimed:
        return

    # Mark claimed and transfer
    pkt.claimed = True
    pkt.claimer_qid = event.get_user_id()

    # Transfer coins: quitter -> claimer
    claimer_qid = pkt.claimer_qid
    with session as s:
        quitter: User | None = s.get(User, pkt.quitter_qid)
        claimer: User | None = s.get(User, claimer_qid)
        if not quitter or not claimer:
            pkt.claimed = False  # roll back marker, though unlikely useful now
            return

            # inside claim handler, replace the transfer section
        transfer_amount = min(quitter.coins, pkt.coins)
        if transfer_amount <= 0:
            return

        tax = math.ceil(transfer_amount * 0.30)
        net = transfer_amount - tax

        quitter.coins -= transfer_amount
        claimer.coins += net
        bank = get_bank()
        bank.coins += tax

        s.add_all([
            CoinTransaction(
                user_id=quitter.qid,
                amount=-transfer_amount,
                type=TransactionType.LJPK,  # or RED_PACKET if you have it
                description=f"退群红包被领取，转出 {transfer_amount} 给 {claimer.nickname}（含税）"
            ),
            CoinTransaction(
                user_id=claimer.qid,
                amount=net,
                type=TransactionType.LJPK,
                description=f"领取退群红包（实得 {net}，已扣遗产税 {tax}）来自 {quitter.nickname}"
            ),
            CoinTransaction(
                user_id="bank",
                amount=tax,
                type=TransactionType.LJPK,
                description=f"退群红包遗产税（来自 {quitter.nickname}）"
            ),
            quitter,
            claimer,
            bank,
        ])
        s.commit()

    # Announce winner
    try:
        await bot.send_group_msg(
            group_id=event.group_id,
            message=MessageSegment.at(
                int(claimer_qid)) + f" 抢到红包！+{net}（原额：{transfer_amount}，已扣遗产税：{tax}）"
        )
    except Exception as e:
        logger.warning(f"[RedPacket] announce claim failed: {e}")

    # Clean up state and cancel timeout job (best effort)
    _pending.pop(key, None)
    try:
        scheduler.remove_job(f"red_packet_timeout_{event.group_id}_{replied_mid}")
    except Exception:
        pass
