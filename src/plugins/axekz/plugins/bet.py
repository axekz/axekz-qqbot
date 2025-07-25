from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from sqlmodel import select, func
from datetime import datetime

from ..core.db.deps import SessionDep
from ..core.db.models import User, BetEvent, BetOption, BetRecord

bet = on_command('bet')
bet_info = on_command('bet_info', aliases={'betinfo'})
checkout = on_command("checkout", aliases={"结账"}, permission=SUPERUSER)
signup = on_command("signup")
signup = on_command("signup", aliases={'bm', "报名"})
mybets = on_command("mybet", aliases={"mybets", "bets"})


@mybets.handle()
async def _(event: MessageEvent, session: SessionDep, arg: Message = CommandArg()):
    user_id = event.get_user_id()
    user = session.get(User, user_id)
    if not user:
        return await mybets.finish("用户不存在，请先绑定SteamID")

    now = datetime.now()
    # 优先查找当前进行中的赛事
    statement = select(BetEvent).where(BetEvent.start_time <= now, BetEvent.end_time > now).order_by(BetEvent.start_time.desc())
    events = session.exec(statement).all()

    if events:
        event_id = events[0].id
    else:
        # 如果没有正在进行的赛事，退而求其次找最新一场（已结束）赛事
        latest_event = session.exec(select(BetEvent).order_by(BetEvent.start_time.desc())).first()
        if not latest_event:
            return await mybets.finish("尚未创建任何赛事")
        event_id = latest_event.id

    stmt = (
        select(BetRecord, BetOption)
        .join(BetOption, (BetRecord.option_id == BetOption.option_id) & (BetRecord.event_id == BetOption.event_id))
        .where(BetRecord.user_id == user_id, BetRecord.event_id == event_id)
        .order_by(BetRecord.created_at.desc())
    )

    results = session.exec(stmt).all()
    if not results:
        return await mybets.finish("你在该赛事中尚未投注任何选项")

    bet_event = session.get(BetEvent, event_id)
    content = f"赛事: {bet_event.name}（ID: {bet_event.id}）的投注记录：\n"
    for record, option in results:
        content += (
            f"选手: {option.option_name}（ID: {option.option_id}）\n"
            f"投注金额: {record.bet_amount} 硬币\n"
            f"{'-------------------------'}\n"
        )

    await mybets.finish(content)


@signup.handle()
async def _(event: MessageEvent, session: SessionDep):
    user_id = event.get_user_id()
    user = session.get(User, user_id)
    if not user:
        return await signup.finish("用户不存在，请先绑定 SteamID")

    now = datetime.now()
    events = session.exec(
        select(BetEvent).where(BetEvent.start_time <= now, BetEvent.end_time > now)
    ).all()

    if not events:
        return await signup.finish("当前没有正在进行的赛事")
    if len(events) > 1:
        return await signup.finish("检测到多个正在进行的赛事，请联系管理员")

    current_event = events[0]

    # Check if already signed up
    existing = session.exec(
        select(BetOption).where(
            BetOption.event_id == current_event.id,
            BetOption.qid == user.qid
        )
    ).first()
    if existing:
        if existing.is_cancelled:
            existing.is_cancelled = False
            existing.updated_at = datetime.now()
            session.add(existing)
            session.commit()
            return await signup.finish("重新激活报名成功！")
        return await signup.finish("你已经报名过了！")

    # Assign option_id as 1-based incremental within this event
    max_option_id = session.exec(
        select(func.max(BetOption.option_id)).where(BetOption.event_id == current_event.id)
    ).one() or 0

    new_option = BetOption(
        option_id=max_option_id + 1,
        event_id=current_event.id,
        option_name=user.nickname,
        qid=user.qid,
        steamid=user.steamid,
        is_cancelled=False
    )
    session.add(new_option)
    session.commit()

    await signup.finish(f"报名成功！选手编号为 {new_option.option_id}")


@checkout.handle()
async def _(session: SessionDep, args: Message = CommandArg()):
    args = args.extract_plain_text().strip().split()
    if len(args) != 2:
        return await checkout.finish("Usage: /结账 <event_id> <option_id>")

    event_id, option_id = args
    try:
        event_id = int(event_id)
        option_id = int(option_id)
    except ValueError:
        return await checkout.finish("Event ID and Option ID must be integers.")

    bet_event = session.get(BetEvent, event_id)
    if not bet_event:
        return await checkout.finish(f"No event found with ID {event_id}")

    winning_option = session.get(BetOption, (option_id, event_id))  # ✅ tuple of keys
    if not winning_option or winning_option.event_id != event_id:
        return await checkout.finish(f"No valid option found with ID {option_id} for event {event_id}")

    bet_event.result_option_id = option_id

    total_bets_query = select(func.sum(BetRecord.bet_amount)).where(BetRecord.event_id == event_id)
    total_bets = session.exec(total_bets_query).one() or 0

    winning_bets_query = select(func.sum(BetRecord.bet_amount)).where(
        BetRecord.option_id == option_id,
        BetRecord.event_id == event_id
    )
    winning_bets = session.exec(winning_bets_query).one() or 0

    if winning_bets == 0:
        return await checkout.finish("No bets placed on the winning option.")

    odds = total_bets / winning_bets

    results = []
    net_wins = {}

    winning_bets_query = select(BetRecord).where(
        BetRecord.option_id == option_id,
        BetRecord.event_id == event_id
    )
    winning_bets = session.exec(winning_bets_query).all()
    for bet_ in winning_bets:
        user = session.get(User, bet_.user_id)
        if not user:
            continue
        win_amount = bet_.bet_amount * odds
        user.coins += int(win_amount)
        session.add(user)
        net_wins[user.qid] = net_wins.get(user.qid, 0) + win_amount - bet_.bet_amount
        results.append(f"{user.nickname} +{win_amount:.2f} 硬币")

    losing_bets_query = select(BetRecord).where(
        BetRecord.option_id != option_id,
        BetRecord.event_id == event_id
    )
    losing_bets = session.exec(losing_bets_query).all()
    for bet_ in losing_bets:
        user = session.get(User, bet_.user_id)
        if not user:
            continue
        lose_amount = bet_.bet_amount
        net_wins[user.qid] = net_wins.get(user.qid, 0) - lose_amount
        results.append(f"{user.nickname} -{lose_amount:.2f} 硬币")

    session.commit()
    result_message = "\n".join(results)
    await checkout.send(result_message)

    sorted_net_wins = sorted(net_wins.items(), key=lambda x: x[1], reverse=True)
    net_win_results = []
    for user_id, net_win in sorted_net_wins:
        user = session.get(User, user_id)
        if not user:
            continue
        net_win_results.append(f"{user.nickname} {'赢得了' if net_win >= 0 else '输掉了'} {abs(net_win):.2f} 硬币")

    net_win_message = "\n".join(net_win_results)
    await checkout.finish(net_win_message)


@bet.handle()
async def _(event: MessageEvent, session: SessionDep, arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip().split()
    if len(args) != 2:
        return await bet.finish("请使用正确的格式: /bet <选项ID或选手昵称> <金额>")

    name_or_id, amount_str = args
    try:
        amount = int(amount_str)
    except ValueError:
        return await bet.finish("金额必须是整数")

    if amount <= 0:
        return await bet.finish("投注金额必须大于0")

    user_id = event.get_user_id()
    user = session.get(User, user_id)
    if not user:
        return await bet.finish("用户不存在，请先绑定SteamID")

    if user.coins < amount:
        return await bet.finish(f"您的余额不足，当前余额: {user.coins}")

    now = datetime.now()
    statement = select(BetEvent).where(BetEvent.start_time <= now, BetEvent.end_time > now)
    events = session.exec(statement).all()

    if not events:
        return await bet.finish("当前没有正在进行的赛事")
    if len(events) > 1:
        return await bet.finish("检测到多个正在进行的赛事，请联系管理员")

    current_event = events[0]

    # 判断是ID还是昵称
    option: BetOption | None = None

    if name_or_id.isdigit():
        option_id = int(name_or_id)
        option = session.get(BetOption, (option_id, current_event.id))
        if not option:
            return await bet.finish("未找到相关选项，请检查选项ID是否正确")
    else:
        # 昵称匹配（模糊忽略大小写）
        options = session.exec(
            select(BetOption).where(
                BetOption.event_id == current_event.id,
                BetOption.option_name.ilike(f"%{name_or_id}%"),
                BetOption.is_cancelled == False
            )
        ).all()
        if not options:
            return await bet.finish("未找到匹配的选手昵称")
        if len(options) > 1:
            names = ", ".join([opt.option_name for opt in options])
            return await bet.finish(f"匹配到多个选手，请更具体一点：{names}")
        option = options[0]

    if option.is_cancelled:
        return await bet.finish("该选手已退出赛事，无法投注")

    if current_event.result_option_id is not None:
        return await bet.finish("该赛事已经结束，无法继续投注")

    user.coins -= amount
    session.add(user)

    # 判断是否已有投注记录，叠加金额
    existing_bet = session.exec(
        select(BetRecord).where(
            BetRecord.user_id == user_id,
            BetRecord.event_id == current_event.id,
            BetRecord.option_id == option.option_id
        )
    ).first()

    if existing_bet:
        existing_bet.bet_amount += amount
        session.add(existing_bet)
    else:
        bet_record = BetRecord(
            user_id=user_id,
            event_id=current_event.id,
            option_id=option.option_id,
            bet_amount=amount,
        )
        session.add(bet_record)

    session.commit()
    session.refresh(user)

    await bet.finish(
        f"投注成功！\n"
        f"选项ID: {option.option_id}\n"
        f"选手昵称: {option.option_name}\n"
        f"投注金额: {amount}\n"
        f"当前余额: {user.coins}"
    )


@bet_info.handle()
async def handle_bet_info(event: MessageEvent, session: SessionDep, arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip()
    now = datetime.now()

    if args:
        try:
            event_id = int(args)
        except ValueError:
            return await bet_info.finish("请输入有效的赛事ID")
        bet_event = session.get(BetEvent, event_id)
    else:
        statement = select(BetEvent).where(BetEvent.start_time <= now, BetEvent.end_time > now)
        events = session.exec(statement).all()

        if not events:
            return await bet_info.finish("当前没有正在进行的赛事")
        if len(events) > 1:
            return await bet_info.finish("检测到多个正在进行的赛事，请联系管理员")

        bet_event = events[0]

    if not bet_event:
        return await bet_info.finish("未找到相关赛事")

    statement = select(BetOption).where(BetOption.event_id == bet_event.id)
    options = session.exec(statement).all()

    if not options:
        return await bet_info.finish("该赛事暂无投注选项")

    total_bets_query = select(func.sum(BetRecord.bet_amount)).where(BetRecord.event_id == bet_event.id)
    total_bets = session.exec(total_bets_query).one() or 0

    content = f"赛事: {bet_event.name}\n描述: {bet_event.description}\n"
    content += "投注选项:\n"

    option_odds_list = []
    for option in options:
        option_bets_query = select(func.sum(BetRecord.bet_amount)).where(
            BetRecord.option_id == option.option_id,
            BetRecord.event_id == bet_event.id
        )
        option_bets = session.exec(option_bets_query).one() or 0
        odds = total_bets / option_bets if option_bets > 0 else 0
        option_odds_list.append({
            'id': option.option_id,
            'name': option.option_name,
            'odds': odds,
            'option_bets': option_bets
        })

    option_odds_list = sorted(
        option_odds_list,
        key=lambda x: (x['odds'] == 0, x['odds'])
    )

    for option in option_odds_list:
        content += (
            f"ID: {option['id']} - 选项: {option['name']} - "
            f"总计: {option['option_bets']} 硬币 - 赔率: {option['odds']:.2f}\n"
        )
    await bet_info.finish(content)
