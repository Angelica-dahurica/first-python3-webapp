# -*- coding:utf-8 -*-

import logging
import asyncio
from aiohttp import web

logging.basicConfig(level=logging.INFO)


def index(request):
	return web.Response(body=b'<h1>Awesome<h1>', content_type='text/html')


# 生成器generator - 边循环边计算的机制；包含yield关键字的函数
# 变成generator的函数，在每次调用next()的时候执行，遇到yield语句返回，再次执行时从上次返回的yield语句处继续执行
# 协程coroutine
@asyncio.coroutine  # 把一个generator标记为coroutine类型
def init(loop):
	app = web.Application(loop=loop)
	app.router.add_route('GET', '/', index)
	srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', 9000)  # 创建一个TCP服务器
	logging.info('server started at http://127.0.0.1:9000...')
	return srv

loop = asyncio.get_event_loop()  # 从asyncio模块中直接获取一个EventLoop的引用
loop.run_until_complete(init(loop))  # 把coroutine扔到EventLoop中执行
loop.run_forever()
