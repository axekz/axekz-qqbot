from nonebot import logger, get_bots, get_bot
from nonebot.plugin import on_command
from nonebot_plugin_apscheduler import scheduler

from .. import API_BASE
from ..core.dataclasses.servers import ServersInfo
from ..core.utils.helpers import aio_get

GROUP_ID = 188099455

serv = on_command("服务器", aliases={"s"}, priority=10, block=True)
list_ = on_command("ls", aliases={"list"}, priority=10, block=True)
status = on_command('status', aliases={'状态'}, priority=15)


@status.handle()
async def _():
    url = f"{API_BASE}/status/"
    data: dict = await aio_get(url, timeout=15)

    content = ""
    for k, v in data.items():
        content += f"{k}: {v}\n"
    await status.finish(content)


@serv.handle()
async def handle_serv_function():
    content = await fetch_and_format_servers_info(show_empty=False)
    if content == "":
        return await serv.finish("服务器暂无人游玩")
    return await serv.finish(content)


@list_.handle()
async def handle_list_function():
    content = await fetch_and_format_servers_info(show_empty=True)
    return await list_.finish(content)


async def fetch_and_format_servers_info(show_empty=False):
    url = f"{API_BASE}/servers/"
    data = await aio_get(url)
    servers_info = ServersInfo(servers=data)

    content = ""
    for s in servers_info.servers:
        # 检查服务器是否查询失败
        if s is None:
            content += f"╔═服务器查询失败🚫\n" if show_empty else ""
            continue

        if show_empty:
            content += f"╔═{s.server_name} ({s.player_count}/{s.max_players}) ╚═{s.map} (T{s.tier})\n"
            content += (" | ".join([p.name for p in s.players]) + "\n") if s.players else ""
        else:
            if s.players:
                content += f"╔═{s.server_name} ({s.player_count}/{s.max_players}) ╚═{s.map} (T{s.tier})\n"
                content += (" | ".join([p.name for p in s.players]) + "\n") if s.players else ""

        # if show_empty or s.players:
        #     content += f"╔═{s.server_name} ({s.player_count}/{s.max_players}) ╚═{s.map} (T{s.tier})\n"
        #     if s.players:
        #         content += " | ".join([p.name for p in s.players]) + "\n"

    return content


async def get_total_online_players() -> int:
    try:
        url = f"{API_BASE}/servers/"
        data = await aio_get(url, timeout=15)
        servers_info = ServersInfo(servers=data)
        return sum((s.player_count for s in servers_info.servers if s is not None), 0)
    except Exception as e:
        logger.warning(f"[GroupNameUpdater] Failed to fetch servers: {e}")
        return 0


@scheduler.scheduled_job("interval", minutes=1, id="update_group_name_every_minute")
async def update_group_name_every_minute():
    bot = get_bot()
    if not bot:
        return

    total = await get_total_online_players()
    new_card = f"千早爱音 {total}"

    try:
        # Use the OB11 adapter method (wraps set_group_card)
        await bot.set_group_card(group_id=GROUP_ID, user_id=bot.self_id, card=new_card)
        logger.debug(f"[GroupCardUpdater] Group card set to: {new_card}")
    except Exception as e:
        logger.warning(f"[GroupCardUpdater] Failed to set group card: {e}")
