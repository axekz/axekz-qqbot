from sqlmodel import Session

from src.plugins.axekz.core.db import engine
from src.plugins.axekz.core.db.models import User

BANK_QID = "3788748445"


def get_bank() -> User:
    with Session(engine) as session:
        bank_obj = session.get(User, BANK_QID)
        if not bank_obj:
            raise RuntimeError("中央银行用户不存在")
        return bank_obj
