from datetime import datetime, date
from textwrap import dedent

from sqlalchemy import ForeignKeyConstraint, PrimaryKeyConstraint
from sqlmodel import Field, SQLModel, Column, DateTime, func, Text, Enum, UniqueConstraint, Date


class TransactionType(str, Enum):
    BET_PLACED = "bet_placed"            # 用户参与赛事下注，硬币减少
    BET_REWARD = "bet_reward"            # 赛事结算后获胜奖励
    BET_REFUND = "bet_refund"            # 赛事取消或选手退赛退款
    TAX = "tax"
    SIGN = 'sign'                        # 每日签到
    DAILY_ACTIVE_REWARD = "daily_active" # 每日活跃奖励
    LJPK = "ljpk"                 # LJPK

    PURCHASE = "purchase"                # 各类功能性花费，如 kick、mute、buy_admin

    GIVE = "give"                        # 打赏/收到打赏，依据 amount ± 判断方向

    MANUAL_ADJUST = "admin_adjust"       # 管理员手动调整


class CoinTransaction(SQLModel, table=True):
    __tablename__ = "coin_transactions"

    id: int = Field(default=None, primary_key=True)
    user_id: str = Field(index=True, nullable=False)
    amount: int = Field(nullable=False)  # 正数为收入，负数为支出
    type: TransactionType = Field(nullable=False)
    description: str = Field(default="", nullable=False)

    created_at: datetime = Field(
        default_factory=datetime.now,
        sa_column=Column(DateTime, default=func.now(), nullable=False)
    )
    model_config = {
        "arbitrary_types_allowed": True
    }


class User(SQLModel, table=True):
    __tablename__ = "qq_users"
    qid: str = Field(primary_key=True)
    steamid: str = Field(unique=True, index=True)
    nickname: str = Field(default='')
    mode: str = Field(default='kzt', nullable=False)
    coins: int = Field(default=0, nullable=False)
    is_whitelist: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))

    def __str__(self):
        return dedent(f"""
            QQ号:　　{self.qid}
            id64:　　 {self.steamid}
            昵称:　　 {self.nickname}
            模式:　　 {self.mode.upper()}
            硬币:　　 {self.coins}
            白名单:　 {self.is_whitelist}
            创建时间: {self.created_at}
            更新时间: {self.updated_at}
        """
                      ).strip()


class Sign(SQLModel, table=True):
    __tablename__ = "qq_signs"
    id: int | None = Field(primary_key=True, default=None)
    qid: str = Field(foreign_key="qq_users.qid", index=True)
    earned_coins: int = Field(default=0, nullable=False)
    signed_at: datetime = Field(default_factory=datetime.now,
                                sa_column=Column(DateTime, default=func.now(), nullable=False))


class Roll(SQLModel, table=True):
    __tablename__ = "qq_rolls"
    id: int | None = Field(primary_key=True, default=None)
    roll_date: datetime = Field(default_factory=datetime.now,
                                sa_column=Column(DateTime, default=func.now(), nullable=False))
    signers: int = Field(default=0, nullable=False)
    prize: int = Field(default=0, nullable=False)
    winner_qid: str = Field(foreign_key="qq_users.qid", nullable=False)


class LJPKRecord(SQLModel, table=True):
    __tablename__ = "qq_ljpk"
    id: int | None = Field(primary_key=True, default=None)
    match_date: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), nullable=False))
    qid1: str = Field(foreign_key="qq_users.qid", nullable=False)
    qid2: str = Field(foreign_key="qq_users.qid", nullable=False)
    distance1: float = Field(nullable=False)
    distance2: float = Field(nullable=False)
    bet_amount: int = Field(nullable=False)
    mode: str = Field(nullable=False)
    winner_qid: str = Field(foreign_key="qq_users.qid", nullable=False)

    def __str__(self):
        return dedent(f"""
            Match Date: {self.match_date}
            User1 QID: {self.qid1}
            User1 Distance: {self.distance1}
            User2 QID: {self.qid2}
            User2 Distance: {self.distance2}
            Winner QID: {self.winner_qid}
            """
                      ).strip()


class Allowance(SQLModel, table=True):
    __tablename__ = "qq_allowances"
    id: int = Field(default=None, primary_key=True)
    giver_qid: str = Field(foreign_key="qq_users.qid", nullable=False)
    receiver_qid: str = Field(foreign_key="qq_users.qid", nullable=False)
    amount: int = Field(nullable=False)
    date: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=datetime.now, nullable=False))

    def __str__(self):
        return f"Allowance from {self.giver_qid} to {self.receiver_qid} of {self.amount} coins on {self.date}"


class BetEvent(SQLModel, table=True):
    __tablename__ = "bet_events"
    id: int = Field(primary_key=True)
    name: str = Field(nullable=False)
    description: str = Field(nullable=True)
    start_time: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), nullable=False))
    end_time: datetime = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))
    result_option_id: int = Field(nullable=True)
    result_event_id: int = Field(nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["result_option_id", "result_event_id"],
            ["bet_options.option_id", "bet_options.event_id"],
            name="fk_result_option"
        ),
    )


class BetOption(SQLModel, table=True):
    __tablename__ = "bet_options"
    option_id: int = Field(primary_key=True)
    event_id: int = Field(foreign_key="bet_events.id", primary_key=True)
    option_name: str = Field(nullable=False)

    # Player info
    qid: str = Field(foreign_key="qq_users.qid", nullable=False)
    steamid: str = Field(nullable=False)

    # Whether the player has quit/been disqualified
    is_cancelled: bool = Field(default=False, nullable=False)

    created_at: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))

    __table_args__ = (
        PrimaryKeyConstraint('option_id', 'event_id'),
        UniqueConstraint('event_id', 'qid', name='uq_event_participant'),
    )


class BetRecord(SQLModel, table=True):
    __tablename__ = "bet_records"
    id: int | None = Field(primary_key=True)
    user_id: str = Field(foreign_key="qq_users.qid", nullable=False)
    event_id: int = Field(foreign_key="bet_events.id", nullable=False)
    option_id: int = Field(nullable=False)
    bet_amount: int = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), nullable=False))
    updated_at: datetime = Field(default_factory=datetime.now,
                                 sa_column=Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False))

    __table_args__ = (
        ForeignKeyConstraint(
            ['option_id', 'event_id'],
            ['bet_options.option_id', 'bet_options.event_id']
        ),
    )


class LeeWords(SQLModel, table=True):
    __tablename__ = "lee_words"
    id: int | None = Field(primary_key=True)
    content: str = Field(sa_column=Column(Text))
    explicit: bool = Field(nullable=False, default=False)
    created_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, default=func.now(), nullable=False))

    def __str__(self):
        return f"#{self.id} {self.content}"

    def info(self):
        return f"#{self.id} {self.explicit} {self.content}"


class TaskTypeEnum(str, Enum):
    DAILY_ONLINE = "每日登陆服务器"
    DAILY_MAP_PB = "每日地图PB完成"


class DailyTask(SQLModel, table=True):
    __tablename__ = "daily_tasks"
    __table_args__ = (UniqueConstraint('user_id', 'task_type', 'created_on'),)
    id: int | None = Field(primary_key=True)
    user_id: str = Field(foreign_key="qq_users.qid", nullable=False)
    task_type: TaskTypeEnum = Field(nullable=False)
    map_name: str | None = Field(nullable=True)
    mode: str | None = Field(nullable=True)
    bonus: int = Field(nullable=False, default=20)
    created_on: date = Field(default_factory=date.today, sa_column=Column(Date, nullable=False))
    finished_at: datetime | None = Field(sa_column=Column(DateTime, default=None, nullable=True))
    description: str | None = Field(nullable=True)

    class Config:
        arbitrary_types_allowed = True


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"
    id: int = Field(primary_key=True)
    user_id: str = Field(foreign_key="qq_users.qid", nullable=False)
    type: str = Field(nullable=False)
    amount: int = Field(nullable=False)

