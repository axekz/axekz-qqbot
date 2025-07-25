import ssl

import aiohttp
from aiohttp import ClientTimeout

context = ssl.create_default_context()


async def aio_get(url, params=None, headers=None, timeout=5):
    conn = aiohttp.TCPConnector(ssl=context)
    async with aiohttp.ClientSession(connector=conn, timeout=ClientTimeout(total=timeout)) as session:
        async with session.get(url, params=params, headers=headers) as response:
            return await response.json()


async def api_get(router, params=None, headers=None, timeout=5):
    url = 'http://127.0.0.1:8000' + router
    conn = aiohttp.TCPConnector(ssl=context)
    async with aiohttp.ClientSession(connector=conn, timeout=ClientTimeout(total=timeout)) as session:
        async with session.get(url, params=params, headers=headers) as response:
            return await response.json()


async def aio_post(url, data=None, headers=None, timeout=60):
    async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
        async with session.post(url, json=data, headers=headers) as response:
            return await response.json()


async def api_post(router, data=None, headers=None, timeout=60):
    url = 'http://127.0.0.1:8000' + router
    async with aiohttp.ClientSession(timeout=ClientTimeout(total=timeout)) as session:
        async with session.post(url, json=data, headers=headers) as response:
            return await response.json()
