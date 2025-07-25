from urllib.parse import quote_plus

from pydantic import BaseModel


class Config(BaseModel):
    api_base: str = 'http://127.0.0.1:8000'
    group_id: int = 188099455
    mini_group_id: int = 681119576
    bot_qid: int = 3788748445
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    token: str

    def get_connection_string(self) -> str:
        encoded_password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{encoded_password}@"
            f"{self.db_host}:{self.db_port}/{self.db_name}"
        )
