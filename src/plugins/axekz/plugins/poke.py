import random
from textwrap import dedent

from nonebot import on_type
from nonebot.adapters.onebot.v11 import PokeNotifyEvent
from nonebot.rule import to_me
from nonebot_plugin_capoo import pic

from .lee_god import random_lee_word
from ..core.db.deps import SessionDep
from ..core.db.models import User
from ..core.utils.helpers import api_get

poke_me = on_type(
    (PokeNotifyEvent,),
    rule=to_me(),
    priority=1,
    block=True,
)

group_poke = on_type(
    (PokeNotifyEvent,),
    priority=2,
    block=True,
)


@group_poke.handle()
async def _(event: PokeNotifyEvent, session: SessionDep):
    num = random.random()
    if num < 0.95:
        return

    user: User | None = session.get(User, event.user_id)
    if not user:
        return

    target_user: User | None = session.get(User, event.target_id)
    if not target_user:
        return

    num = random.random()
    args = f'-s {target_user.steamid} -m {target_user.mode}'
    if num < 0.25:
        await group_poke.send(f'/kz {args}')
    elif num < 0.5:
        await group_poke.send(f'/pr {args}')
    elif num < 0.75:
        await group_poke.send(f'/pb {args}')
    else:
        await group_poke.send(f'/rank {args}')


@poke_me.handle()
async def _(event: PokeNotifyEvent, session: SessionDep):
    user: User | None = session.get(User, event.user_id)
    if not user:
        return

    num = random.random()
    if num > 0.7:
        return await poke_me.send(random_lee_word())
    if num > 0.4:
        return await pic()

    else:
            data = await api_get('/misc/ip', params={'steamid': user.steamid})
            content = dedent(f"""
                来自 {data['province']} {data['city']} 的 {data['name']} 先生
                您戳我干什么呢  凸(^▽^)凸
            """).strip()
            await poke_me.finish(content)
