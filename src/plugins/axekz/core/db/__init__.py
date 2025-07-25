
from sqlmodel import create_engine, SQLModel
import nonebot

from ... import axekz_config

engine = create_engine(axekz_config.get_connection_string())


async def create_tables():
    SQLModel.metadata.create_all(engine)


nonebot.get_driver().on_startup(create_tables)
