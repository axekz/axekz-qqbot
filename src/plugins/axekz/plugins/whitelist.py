from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import on_command

from .general import bind_steamid
from .. import axekz_config
from ..core.db.models import User
from ..core.db.deps import SessionDep
from ..core.utils.convertors import convert_steamid
from ..core.utils.helpers import api_get, aio_get, api_post

wl = on_command('wl', aliases={'白名单', 'whitelist'})
add_wl = on_command('add_wl', permission=SUPERUSER)
ban = on_command('ban', permission=SUPERUSER)


# @ban.handle()
# async def _(event: MessageEvent, message: Message = CommandArg()):
#     args = message.extract_plain_text().split()
#     if len(args) != 3:
#         return await ban.send('参数不正确，格式 !ban <time> <steamid> <reason>')


@add_wl.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    steamid = args.extract_plain_text().strip()
    try:
        steamid = convert_steamid(steamid)
    except Exception as e:
        return await add_wl.send(repr(e))

    msg = await api_post('/servers/whitelist', data={'steamid': steamid, 'token': axekz_config.token},
                         timeout=15)
    return await add_wl.finish(msg)


@wl.handle()
async def _(event: MessageEvent, session: SessionDep):
    # await wl.finish('该功能已停用')
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    # check
    playtime_data = await api_get('/players/playtime', {'steamid': user.steamid}, timeout=15)
    if not playtime_data:
        return await wl.finish("获取游玩时间失败（你未在此服务器游玩过？)")

    purity_data = await aio_get(f'http://47.238.188.6:8000/records/purity/{user.steamid}', timeout=15)
    if not purity_data:
        return await wl.finish("获取游玩时间失败（你未上传过KZ全球记录？)")

    results = []

    # Basic conditions
    records_num_check = purity_data['records_num_on_this_server'] >= 150
    playtime_on_server_check = purity_data['playtime_on_this_server'] / 3600 >= 20
    playtime_percent_check = purity_data['playtime_percent'] >= 10
    
    results.append("====统计的在本服的记录====")
    results.append("======以下需全部满足======")
    results.append(f"{'✅' if records_num_check else '❌'} 全球计时次数 {purity_data['records_num_on_this_server']} >= 150")
    results.append(f"{'✅' if playtime_on_server_check else '❌'} 累计计时时间 {purity_data['playtime_on_this_server'] / 3600:.2f}h >= 20h")
    results.append(f"{'✅' if playtime_percent_check else '❌'} 计时时间比例 {purity_data['playtime_percent']:.2f}% >= 10%")

    # 进阶要求
    playtime_total_check = playtime_data['total'] / 3600 >= 100
    playtime_on_server_80_check = purity_data['playtime_on_this_server'] / 3600 >= 80
    playtime_percent_50_check = purity_data['playtime_percent'] > 50

    results.append("======以下需满足一项======")
    results.append(f"{'✅' if playtime_total_check else '❌'} 服务器游玩时间 {int(playtime_data['total'] / 3600):.2f}h >= 100h")
    results.append(f"{'✅' if playtime_on_server_80_check else '❌'} 累计计时时间　 {purity_data['playtime_on_this_server'] / 3600:.2f}h >= 80h")
    results.append(f"{'✅' if playtime_percent_50_check else '❌'} 计时时间比例　 {purity_data['playtime_percent']:.2f}% > 50%")

    result = False
    if (records_num_check and playtime_on_server_check and playtime_percent_check) and \
       (playtime_total_check or playtime_on_server_80_check or playtime_percent_50_check):
        result = True

    results.append(f"========最终结果========")
    results.append(f"{'✅✅✅ 通过 ✅✅✅\n' if result else '❌❌❌ 未通过 ❌❌❌'}")
    content = '\n'.join(results).strip()

    # if result is True:
    #     user.is_whitelist = True
    #     session.add(user)
    #     session.commit()
    #     session.refresh(user)
    #     msg = await api_post('/servers/whitelist', data={'steamid': user.steamid, 'token': axekz_config.token},
    #                          timeout=15)
    #     await wl.send(MessageSegment.reply(event.message_id) + msg)
    await wl.send(MessageSegment.reply(event.message_id) + content)
