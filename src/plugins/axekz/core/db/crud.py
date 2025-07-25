from dataclasses import dataclass

from sqlmodel import select, Session, or_

from . import engine
from .deps import SessionDep
from .models import LJPKRecord, User
from ... import axekz_config


@dataclass
class LJPKStats:
    nickname: str
    winrate: float
    net_coins: int
    avg_distance: float
    total_matches: int


def get_bot_user() -> User | None:
    with Session(engine) as session:
        return session.get(User, axekz_config.bot_qid)


def get_user_lee() -> User | None:
    with Session(engine) as session:
        return session.get(User, 2678754694)


async def get_ljpk_stats(user_id: str | int) -> LJPKStats:
    with Session(engine) as session:
        # Query to get the user's nickname
        user = session.exec(select(User).where(User.qid == user_id)).one_or_none()
        if not user:
            raise ValueError(f"User with ID {user_id} not found")

        # Query to get all matches involving the user
        statement = select(LJPKRecord).where(
            or_(LJPKRecord.qid1 == user_id, LJPKRecord.qid2 == user_id)
        )
        results = session.exec(statement).all()

        if not results:
            return LJPKStats(
                nickname=user.nickname,
                winrate=0.00,
                net_coins=0,
                avg_distance=0.0000,
                total_matches=0
            )

        total_matches = len(results)
        wins = sum(1 for record in results if record.winner_qid == user_id)
        winrate = wins / total_matches * 100

        total_win_coins = sum(record.bet_amount for record in results if record.winner_qid == user_id)
        total_lose_coins = sum(record.bet_amount for record in results if record.winner_qid != user_id)

        net_coins = total_win_coins - total_lose_coins

        total_distance = sum(record.distance1 if record.qid1 == user_id else record.distance2 for record in results)
        avg_distance = total_distance / total_matches

        return LJPKStats(
            nickname=user.nickname,
            winrate=round(winrate, 2),
            net_coins=net_coins,
            avg_distance=round(avg_distance, 4),
            total_matches=total_matches
        )


async def get_top_ljpk_players() -> list[LJPKStats]:
    with Session(engine) as session:
        # Query all unique winner_qid
        statement = select(LJPKRecord.winner_qid).distinct()
        winner_qids = session.exec(statement).all()

        # For each unique winner_qid, calculate their stats
        player_stats = []
        for winner_qid in winner_qids:
            stats = await get_ljpk_stats(winner_qid)
            player_stats.append(stats)

        # Sort players by net_coins in descending order
        player_stats.sort(key=lambda x: x.net_coins, reverse=True)
        return player_stats
