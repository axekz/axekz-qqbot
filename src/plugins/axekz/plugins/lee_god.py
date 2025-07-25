import csv
import math
import random
from itertools import islice

from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import MessageEvent, Message
from nonebot.params import CommandArg
from sqlmodel import select, Session

from ..core import get_bank
from ..core.db import engine
from ..core.db.crud import get_user_lee
from ..core.db.deps import SessionDep
from ..core.db.models import User, LeeWords
from ..plugins.general import bind_steamid

try:
    with open('data/lee2.csv') as f:
        reader = csv.reader(f)
        LEE_LANGUAGES = list(reader)
except FileNotFoundError:
    logger.warning("Lee God File not found")
except Exception as e:
    logger.error(e)


def random_lee_word() -> str:
    with Session(engine) as session:
        statement = select(LeeWords).where(LeeWords.explicit == 0)
        results = session.exec(statement).all()
        if not results:
            return "No 李语 found in the database."
        return str(random.choice(results))


LEE_WORDS_ADMIN = [
    '986668919',
    '1281185125',
    '904063043',
    '947814132',
    '1350251771',
    '2678754694',
    '2863273825',
    '1240874189',
    '727303178',
    '262104274',
    '419332283',
]


lee_lang = on_command('lee', aliases={'li'})
lee_add = on_command('add_lee', aliases={'addlee', 'lee_add', 'leeadd'})
lee_set = on_command('set_lee', aliases={'setlee', 'lee_set'})
lee_all = on_command('lee_all')


@lee_all.handle()
async def _(event: MessageEvent, session: SessionDep):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    if user.qid not in LEE_WORDS_ADMIN:
        return await lee_all.send('非管理员，无法查看所有李语')

    statement = select(LeeWords)
    lee_words = session.exec(statement).all()
    if not lee_words:
        return await lee_all.send('No LeeWords')

    # Function to chunk the list
    def chunks(data, size):
        it = iter(data)
        for i in range(0, len(data), size):
            yield {i: v for i, v in zip(range(i, i + size), islice(it, size))}

    # Send 20 lee_words per message
    for chunk in chunks(lee_words, 20):
        content = '\n'.join(lw.info() for i, lw in chunk.items())
        await lee_all.send(content)
    return None


@lee_set.handle()
async def _(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    if user.qid not in LEE_WORDS_ADMIN:
        return await lee_set.send('非管理员，无法设置李语')

    try:
        id, content = args.extract_plain_text().split(' ', 1)
    except ValueError:
        return await lee_set.send("格式不正确, 应为 /lee_set <id> <content/is_explicit>")

    # try:
    #     is_explicit =
    # except TypeError:
    #     is_explicit = None

    lee_word: LeeWords = session.get(LeeWords, id)
    if not lee_word:
        return await lee_set.send(f'id {id} 的李语不存在')

    if content.lower() == 'true':
        lee_word.explicit = True
    elif content.lower() == 'false':
        lee_word.explicit = False
    else:
        lee_word.content = content

    session.add(lee_word)
    session.commit()
    session.refresh(lee_word)
    return await lee_set.send(lee_word.info())


@lee_add.handle()
async def send_lee_lang(event: MessageEvent, session: SessionDep, args: Message = CommandArg()):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    if user.qid not in LEE_WORDS_ADMIN:
        return await lee_lang.send('非管理员，无法添加李语')

    lee_words = LeeWords(
        content=args.extract_plain_text().strip(),
        explicit=False
    )
    session.add(lee_words)
    session.commit()
    session.refresh(lee_words)
    return await lee_add.send('李语添加成功!\n' + str(lee_words))


@lee_lang.handle()
async def send_lee_lang(event: MessageEvent, session: SessionDep):
    user_id = event.get_user_id()
    user: User | None = session.get(User, user_id)
    if not user:
        user = await bind_steamid(event, session)

    price = 10
    if user.coins < price:
        return await lee_lang.send(f'这样吧，你先给我 {price} 硬币，我就给你讲述一遍我的名言', at_sender=True)

    lee = get_user_lee()

    if user.qid != lee.qid:
        user.coins -= price

        # 拆分 price 的一半给 lee 和央行
        lee_share = math.floor(price / 2)   # 向下取整
        bank_share = math.ceil(price / 2)   # 向上取整，保证两者和为 price

        lee.coins += lee_share

        bank = get_bank()
        bank.coins += bank_share

        session.add(user)
        session.add(lee)
        session.add(bank)
        session.commit()

    await lee_lang.send(random_lee_word(), at_sender=True)
    return None
