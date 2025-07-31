import math
import random
import re
from datetime import datetime
from textwrap import dedent
from typing import Optional

from nonebot import on_message, get_bot
from nonebot.adapters.onebot.v11 import MessageSegment, MessageEvent, Message, Bot, GroupMessageEvent
from nonebot.params import CommandArg
from nonebot.plugin import on_command
from nonebot_plugin_apscheduler import scheduler
from sqlmodel import Session

from .general import bind_steamid
from ..core import get_bank
from ..core.db.crud import get_ljpk_stats
from ..core.db.deps import SessionDep
from ..core.db.models import User, LJPKRecord, CoinTransaction, TransactionType
from ..core.utils.command_helper import CommandData
from ..core.utils.helpers import api_get

lj = on_command('lj')
ljpb = on_command('ljpb')
ljpk = on_command('ljpk')
accept_game = on_message(priority=2, block=False)


class LJPKSession:
    def __init__(self, initializer_qid: str, opponent_qid: Optional[str], bet_coins: int, group_id: int):
        self.qid1: str = initializer_qid
        self.qid2: None | str = opponent_qid
        self.bet_coins: int = bet_coins
        self.group_id = group_id
        self.created_at: datetime = datetime.now()
        self.bot_message_id: Optional[int] = None  # 新增：记录机器人发送的消息 ID

    def get_users(self, session: Session) -> tuple[type[User] | None, type[User] | None]:
        user1 = session.get(User, self.qid1)
        user2 = session.get(User, self.qid2) if self.qid2 else None
        return user1, user2

    def set_opponent(self, qid: str):
        self.qid2 = qid


ljpk_sessions: list[LJPKSession] = []


async def clean_expire_session(bot: Bot, expiration_minutes: int = 2):
    global ljpk_sessions
    current_time = datetime.now()
    non_expired_sessions = []

    for session in ljpk_sessions:
        time_diff = current_time - session.created_at
        if time_diff.total_seconds() < expiration_minutes * 60:
            non_expired_sessions.append(session)
        else:
            if session.bot_message_id:
                try:
                    await bot.delete_msg(message_id=session.bot_message_id)
                except:
                    pass

    ljpk_sessions = non_expired_sessions


@scheduler.scheduled_job("interval", seconds=5)
async def auto_clean_ljpk_sessions():
    if not ljpk_sessions:
        return  # 没有 Session，直接返回避免浪费资源

    bot = get_bot()
    current_time = datetime.now()

    new_sessions = []
    for session in ljpk_sessions:
        if (current_time - session.created_at).total_seconds() < 120:
            new_sessions.append(session)
        else:
            if session.bot_message_id:
                try:
                    await bot.delete_msg(message_id=session.bot_message_id)
                except Exception:
                    pass  # 可能已被手动撤回或无权限

    ljpk_sessions[:] = new_sessions


@ljpb.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    cd = CommandData(event, args)
    if cd.error:
        return await ljpb.send(cd.error)

    user = cd.user

    params = {
        "steamid": user.steamid,
        "jump_type": 0,
        "mode": user.mode,
        'limit': 1,
        'offset': 0
    }
    data = await api_get("/gokz/jumpstats", params)
    data = data[0]

    created_datetime = datetime.strptime(data['Created'], '%Y-%m-%dT%H:%M:%S')
    content = dedent(f"""
        ID:　{user.steamid}
        昵称:　　 {data['name']}
        类型:　　 {data['JumpType']}
        模式:　　 {data['Mode']}
        距离:　　 {data['Distance']}
        板子:　　 {data['Block']}
        加速:　　 {data['Strafes']}
        同步:　　 {data['Sync']}
        地速:　　 {data['Pre']}
        空速:　　 {data['Max']}
        滞空: 　　{data['Airtime']} 秒
        {created_datetime.strftime('%Y年%m月%d日 %H:%M')}
    """).strip()

    await lj.finish(MessageSegment.reply(event.message_id) + content)


@lj.handle()
async def _(event: MessageEvent, session: SessionDep):
    await lj.finish()
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    data = await api_get('/casual/lj', {'mode': user.mode})
    content = ""
    for item in data:
        content += f"跳出了 {item['distance']} 空速: {item['max_val']} 地速: {item['pre']} {item['strafes']}次加速  {item['sync']}同步率"

    await lj.send(MessageSegment.reply(event.message_id) + content)
    file_url = f"https://r2.axekz.com/sound/silk/quake/{data[0]['color']}.silk"
    await lj.send(MessageSegment.record(file_url))


@ljpk.handle()
async def _(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    # 判定一个人同时只能开一次决斗
    await clean_expire_session(bot)

    reply = MessageSegment.reply(event.message_id)
    user_id = event.get_user_id()
    cd = CommandData(event, args)
    if cd.error:
        return await ljpk.send(reply + cd.error)

    # ljpk stats
    if cd.args and cd.args[0] == 'stats':
        stats = await get_ljpk_stats(cd.user2.qid if cd.user2 else cd.user1.qid)
        content = dedent(f"""
                =======LJPK数据=======
                玩家:　　 {cd.user2.nickname if cd.user2 else cd.user1.nickname}
                胜率:　　 {stats.winrate}%
                净胜:　　 {stats.net_coins} 硬币
                平均距离: {stats.avg_distance}
                总场次:　 {stats.total_matches}
            """).strip()
        return await ljpk.send(reply + content)

    # Check if the player already has an active session
    for session in ljpk_sessions:
        if session.user1.qid == cd.user1.qid and session.group_id == event.group_id:
            return await ljpk.send(reply + "你已经开启了一场决斗，请等待决斗结束后再发起新的决斗。")

    if cd.args:
        if cd.args[0] == 'kick':
            return await ljpk.finish("ljpk kick功能已关闭")
            # bet_coins = 0
        elif cd.args[0] == 'mute':
            bet_coins = -1
        elif cd.args[0] == 'ban':
            bet_coins = -2
        else:
            try:
                bet_coins = int(cd.args[0])
                if bet_coins < 1:
                    return await ljpk.send(reply + "投入不能小于1")
            except ValueError:
                return await ljpk.send(reply + "投入输入格式不正确")
    else:
        bet_coins = 20

    pk_session = LJPKSession(initializer_qid=cd.user1.qid, opponent_qid=cd.user2.qid if cd.user2 else None,
                             bet_coins=bet_coins, group_id=event.group_id)

    bet_comments = bet_coins
    if bet_coins == 0:
        bet_comments = '败者被踢出群'
    elif bet_coins == -1:
        bet_comments = '败者被禁言10分钟'

    msg = await ljpk.send(dedent(f"""
        玩家 {user_id} 开启了一场LJPK
        赌注: {bet_comments}
        对手: {cd.user2.nickname + ' ' + str(cd.user2.qid) if cd.user2 else '未指定'}
        回复此条信息即可开始PK
        自己回复这条消息即取消
    """).strip())

    pk_session.bot_message_id = msg.message_id
    ljpk_sessions.append(pk_session)
    return None


@accept_game.handle()
async def _(bot: Bot, event: GroupMessageEvent, session: SessionDep):
    if event.reply and event.reply.sender.user_id == int(bot.self_id):
        user_id = event.get_user_id()
        clean_expire_session()
        try:
            original_message = event.reply.message.extract_plain_text()
        except TypeError:
            return None

        match = re.search(r'玩家 (\d+) 开启了一场LJPK', original_message)
        if not match:
            return None

        initializer_id = int(match.group(1))

        for pk_session in ljpk_sessions:
            if int(pk_session.qid1) == initializer_id and pk_session.group_id == event.group_id:
                if int(pk_session.qid1) == int(user_id):
                    ljpk_sessions.remove(pk_session)
                    if pk_session.bot_message_id:
                        try:
                            await bot.delete_msg(message_id=pk_session.bot_message_id)
                        except:
                            pass
                    return await accept_game.send('已取消这场比赛', at_sender=True)

                if pk_session.qid2 is not None and int(pk_session.qid2) != int(user_id):
                    return await accept_game.send('别人跟你PK了吗你就接受', at_sender=True)

                if pk_session.qid2 is None:
                    pk_session.set_opponent(user_id)

                user1, user2 = pk_session.get_users(session)

                if not user1 or not user2:
                    return await accept_game.send("玩家数据无效，比赛无法开始")

                if user1.coins < pk_session.bet_coins:
                    return await accept_game.send(
                        f"你的对手 {user1.nickname} 没有足够的硬币:\n需要: {pk_session.bet_coins} 剩余: {user1.coins}", at_sender=True)
                if user2.coins < pk_session.bet_coins:
                    return await accept_game.send(
                        f"你 {user2.nickname} 没有足够的硬币:\n需要: {pk_session.bet_coins} 剩余: {user2.coins}", at_sender=True)

                data: list = await api_get('/casual/lj', {'mode': 'kzt', 'times': 2})
                random.shuffle(data)
                data1, data2 = data

                winner, loser = (user1, user2) if data1['distance'] > data2['distance'] else (user2, user1)

                # 免金币场（禁言/踢人）
                if pk_session.bet_coins <= 0:
                    ljpk_history = LJPKRecord(
                        qid1=user1.qid,
                        qid2=user2.qid,
                        distance1=data1['distance'],
                        distance2=data2['distance'],
                        bet_amount=pk_session.bet_coins,
                        winner_qid=winner.qid,
                        mode='kzt'
                    )
                    session.add(ljpk_history)
                    session.commit()

                    content = f'比赛开始！\n'
                    content += f'昵称 | {user1.nickname:<10} | {user2.nickname}\n'
                    content += f'距离 | {data1["distance"]} | {data2["distance"]}\n'
                    content += f'空速 | {data1["max_val"]}      | {data2["max_val"]}\n'
                    content += f'地速 | {data1["pre"]}       | {data2["pre"]}\n'
                    content += f'次数 | {data1["strafes"]:<16} | {data2["strafes"]}\n'
                    content += f'同步 | {data1["sync"]:<11} | {data2["sync"]}\n'
                    content += f'结果 | {"✅😎获胜" if winner == user1 else "❌😭失败"} | {"✅😎获胜" if winner == user2 else "❌😭失败"}\n'

                    ljpk_sessions.remove(pk_session)
                    await accept_game.send(content, at_sender=True)

                    if pk_session.bet_coins == 0:
                        await bot.set_group_kick(group_id=event.group_id, user_id=int(loser.qid))
                    elif pk_session.bet_coins == -1:
                        delta_distance = abs(float(data1["distance"]) - float(data2["distance"]))
                        total_speed_loser = float(data2["max_val"]) + float(data2["pre"])
                        taunt_messages = [
                            # 轻度调侃（数据对比）
                            f"你的同步率{data2['sync']}%是在致敬人类极限吗？我奶奶的缝纫机都比这同步！",
                            f"空速{data2['max_val']}？建议把键盘泡水里试试，说不定水流能帮你加速",
                            f"{winner.nickname}的地速{data1['pre']} vs 你的{data2['pre']}，这差距够我泡碗面了",
                            f"距离差{delta_distance:.1f}单位？刚好是你和人类平均反应速度的差距",

                            # 中度嘲讽（技术羞辱）
                            "刚才那波操作是闭眼打的？建议改名叫'帕金森流跳远'",
                            f"看你的{data2['strafes']}次摆速，我以为在欣赏慢动作回放",
                            "失败结算界面是你第二熟悉的画面吧？",
                            f"你这{data2['sync']}%的同步率去工地搬砖都怕你手脚不协调砸到脚",
                            "建议把游戏ID改成'禁言VIP会员'",

                            # 数据暴击（精准打击）
                            f"空速{data2['max_val']}+地速{data2['pre']}={total_speed_loser:.1f}？二进制选手？",
                            f"距离{data2['distance']}配{data2['strafes']}次摆速，完美诠释无效操作",
                            f"你{data2['sync']}%的同步率是想证明左右手互为陌生人？",

                            # 重度暴击（物理禁言梗）
                            "系统都看不过去帮你物理闭麦了",
                            "这10分钟禁言是给你时间练习用手走路吗？",
                            "刚才的跳跃数据是你用脚趾操作的吧？建议嘴也参与操作",
                            f"别挣扎了，你输掉的{pk_session.bet_coins}金币都够买副哑铃练手速了",

                            # 终极羞辱（结合游戏机制）
                            f"建议把{data2['distance']}的纪录刻在墓志铭上——这里埋葬着反重力战士",
                            "你掉落的金币在空中划出的弧线比你跳跃轨迹还优美",
                            f"系统税收的硬币都比你操作更有价值",
                            "刚检测到你键盘的WASD键正在发起集体罢工",
                            "失败者特效在你身上是常驻皮肤吧？"
                        ]
                        taunt = random.choice(taunt_messages)  # 省略 taunt_messages，保留原本内容
                        await accept_game.send(MessageSegment.at(int(loser.qid)) + " " + taunt)
                        await bot.set_group_ban(group_id=event.group_id, user_id=int(loser.qid), duration=10 * 60)
                    return None

                # 金币对战场
                tax = math.ceil(pk_session.bet_coins * 0.05)
                winner_gain = pk_session.bet_coins - tax
                winner.coins += winner_gain
                loser.coins -= pk_session.bet_coins
                bank = get_bank()
                bank.coins += tax

                session.add_all([
                    CoinTransaction(
                        user_id=loser.qid,
                        amount=-pk_session.bet_coins,
                        type=TransactionType.LJPK,
                        description=f"LJPK 输给 {winner.nickname}，扣除 {pk_session.bet_coins}"
                    ),
                    CoinTransaction(
                        user_id=winner.qid,
                        amount=winner_gain,
                        type=TransactionType.LJPK,
                        description=f"LJPK 战胜 {loser.nickname}，获得 {winner_gain}（税后）"
                    ),
                    CoinTransaction(
                        user_id="bank",
                        amount=tax,
                        type=TransactionType.LJPK,
                        description=f"LJPK 税收来自 {loser.nickname}"
                    )
                ])

                ljpk_history = LJPKRecord(
                    qid1=user1.qid,
                    qid2=user2.qid,
                    distance1=data1['distance'],
                    distance2=data2['distance'],
                    bet_amount=pk_session.bet_coins,
                    winner_qid=winner.qid,
                    mode='kzt'
                )

                session.add_all([winner, loser, bank, ljpk_history])
                session.commit()

                content = f'比赛开始！ 投入: {pk_session.bet_coins} 硬币\n'
                content += f'昵称 | {user1.nickname:<10} | {user2.nickname}\n'
                content += f'距离 | {data1["distance"]} | {data2["distance"]}\n'
                content += f'空速 | {data1["max_val"]}      | {data2["max_val"]}\n'
                content += f'地速 | {data1["pre"]}       | {data2["pre"]}\n'
                content += f'次数 | {data1["strafes"]:<16} | {data2["strafes"]}\n'
                content += f'同步 | {data1["sync"]:<11} | {data2["sync"]}\n'
                content += f'结果 | {"✅😎获胜" if winner == user1 else "❌😭失败"} | {"✅😎获胜" if winner == user2 else "❌😭失败"}\n'
                content += f'余额 | {user1.coins:,} ({f"+{winner_gain}" if winner == user1 else f"-{pk_session.bet_coins}"}) | {user2.coins:,} ({f"+{winner_gain}" if winner == user2 else f"-{pk_session.bet_coins}"})\n'
                content += f'税收 | {tax} 硬币\n'

                ljpk_sessions.remove(pk_session)
                return await accept_game.send(content, at_sender=True)

        return await accept_game.send("未找到该LJPK对局，或已被其他玩家接受，或已超过两分钟")
    return None
