import argparse
import shlex
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple

from nonebot.adapters.onebot.v11 import MessageEvent
from sqlmodel import Session
from nonebot import logger

from .formatters import format_kzmode
from ..db.models import User
from ...core.db import engine
from ...plugins import BIND_PROMPT


@dataclass
class CommandData:
    mode: str
    qid: str
    map_name: str
    steamid: str
    qid2: str | None = None
    steamid2: Optional[str] = None
    args: Tuple = field(default_factory=tuple)
    update: bool = False
    error: Optional[str] = None
    user1: User | None = None
    user2: User | None = None
    user: User | None = None

    def __init__(self, event, args):
        args = parse_args(args.extract_plain_text())
        self.qid = event.get_user_id()

        if 'error' in args:
            self.error = args['error']
            logger.info(f"Error during argument parsing: {self.error}")
            return

        with Session(engine) as session:
            user = session.get(User, self.qid)  # NOQA
            if not user or not user.steamid:
                self.error = BIND_PROMPT
                logger.info(self.error)
                return

            qid2 = args.get('qid', None)
            if qid2 is None:
                qid2 = get_at_user_id(event)

            # 提供了对手 QQ 号
            if qid2:
                self.qid2 = qid2
                user2 = session.get(User, self.qid2)
                if not user2 or not user2.steamid:
                    self.error = "你指定的用户未绑定steamid"
                    logger.info(self.error)
                    return
                self.steamid = user2.steamid
                self.steamid2 = user.steamid
                self.user1 = user
                self.user2 = user2
            # 未提供对手
            else:
                self.steamid = args.get('steamid') if args.get('steamid') else user.steamid
                self.steamid2 = user.steamid if args.get('steamid') else None
                self.user1 = user

        if self.qid == self.qid2 or self.steamid == self.steamid2:
            self.error = '你不能指定自己'
            return

        self.mode = format_kzmode(args.get('mode', user.mode), 'm') if args.get('mode') else user.mode
        self.map_name = args.get('map_name', "")
        self.update = args.get('update', False)
        self.args = args.get('args', ())
        self.user = self.user2 if self.user2 else self.user1

    def to_dict(self):
        return asdict(self)


def parse_args(text: str) -> dict:
    parser = argparse.ArgumentParser(description='Parse arguments from a text string.')
    parser.add_argument('args', nargs='*', help='Positional arguments before the flags')
    parser.add_argument('-M', '--map_name', type=str, help='Name of the map')
    parser.add_argument('-m', '--mode', type=str, help='KZ模式')
    parser.add_argument('-s', '--steamid', type=str, help='Steam ID')
    parser.add_argument('-q', '--qid', type=str, help='QQ ID')
    parser.add_argument('-u', '--update', action='store_true', help='Update flag')

    try:
        args = parser.parse_args(shlex.split(text))
        result = vars(args)
        result['args'] = tuple(result['args'])
        return result
    except argparse.ArgumentError as e:
        return {'error': f'Argument error: {str(e)}'}
    except SystemExit as e:
        return {'error': f'未指定参数'}
    except Exception as e:
        return {'error': str(e)}


def get_at_user_id(event: MessageEvent) -> str:
    at_msg = event.get_message().copy()
    for segment in at_msg:
        if segment.type == 'at':
            return str(segment.data['qq'])
