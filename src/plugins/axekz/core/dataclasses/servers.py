from ipaddress import IPv4Address
from typing import List

from pydantic import BaseModel, field_validator


class Player(BaseModel):
    name: str
    steamid: str
    steamid32: int
    steamid64: str
    duration: str
    ping: int
    loss: int
    state: str
    rate: int
    ip: IPv4Address

    @field_validator('ip', mode='before')
    def convert_ip_to_string(cls, v):
        if isinstance(v, IPv4Address):
            return str(v)
        return v


class Server(BaseModel):
    server_name: str
    map: str
    tier: int
    player_count: int
    max_players: int
    bot_count: int
    address: str
    players: List[Player]


class ServersInfo(BaseModel):
    servers: List[Server | None]
