# -*- coding:utf-8 -*-

import logging
import asyncio
from aiohttp import web
from jinja2 import Environment, FileSystemLoader
from www.coroweb import add_routes, add_static
from datetime import datetime
from www import orm
import os
import json
import time

logging.basicConfig(level=logging.INFO)


# def index(request):
# 	return web.Response(body=b'<h1>Awesome<h1>', content_type='text/html')


def init_jinja2(app, **kw):
	logging.info('init jinja2...')
	options = dict(
		autoescape=kw.get('autoescape', True),
		block_start_string=kw.get('block_start_string', '{%'),
		block_end_string=kw.get('block_end_string', '%}'),
		variable_start_string=kw.get('variable_start_string', '{{'),
		variable_end_string=kw.get('variable_end_string', '}}'),
		auto_reload=kw.get('auto_reload', True)
	)
	path = kw.get('path', None)
	if path is None:
		path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
	logging.info('set jinja2 template path: %s' % path)
	env = Environment(loader=FileSystemLoader(path), **options)
	filters = kw.get('filters', None)
	if filter is not None:
		for name, f in filters.items():
			env.filters[name] = f
	app['__templating__'] = env


# 拦截器middleware：记录URL日志的logger
async def logger_factory(app, handler):
	async def logger(request):
		# 记录日志
		logging.info('Request: %s %s' % (request.method, request.path))
		# await asynico.sleep(0.3)
		# 继续处理请求
		return await handler(request)
	return logger


async def data_factory(app, handler):
	async def parse_data(request):
		if request.method == 'POST':
			if request.content_type.startswith('application/json'):
				request.__data__ = await request.json()
				logging.info('request json: %s' % str(request.__data__))
			elif request.content_type.startswith('application/x-www-form-urlencoded'):
				request.__data__ = await request.post()
				logging.info('request form: %s' % str(request.__data__))
		return await handler(request)
	return parse_data


# 拦截器middleware：把返回值转换为web.Response
async def response_factory(app, handler):
	async def response(request):
		logging.info('Response handler...')
		r = await handler(request)
		if isinstance(r, web.StreamResponse):
			return r
		if isinstance(r, bytes):
			resp = web.Response(body=r)
			resp.content_type = 'application/octet-stream'
			return resp
		if isinstance(r, str):
			if r.startswith('redirect:'):
				return web.HTTPFound(r[9:])
			resp = web.Response(body=r.encode('utf-8'))
			resp.content_type = 'text/html;charset=utf-8'
			return resp
		if isinstance(r, dict):
			template = r.get('__template__')
			if template is None:
				resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
				resp.content_type = 'application/json;charset=utf-8'
				return resp
			else:
				resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
				resp.content_type = 'text/html;charset=utf-8'
				return resp
		if isinstance(r, int) and 600 > r >= 100:
			return web.Response(r)
		if isinstance(r, tuple) and len(r) == 2:
			t, m = r
			if isinstance(t, int) and 600 > t >= 100:
				return web.Response(t, str(m))
		# default:
		resp = web.Response(body=str(r).encode('utf-8'))
		resp.content_type = 'text/plain;charset=utf-8'
		return resp
	return response


def datetime_filter(t):
	delta = int(time.time() - t)
	if delta < 60:
		return u'1分钟前'
	if delta < 3600:
		return u'%s分钟前' % (delta // 60)
	if delta < 86400:
		return u'%s小时前' % (delta // 3600)
	if delta < 604800:
		return u'%s天前' % (delta // 86400)
	dt = datetime.fromtimestamp(t)
	return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


# 生成器generator - 边循环边计算的机制；包含yield关键字的函数
# 变成generator的函数，在每次调用next()的时候执行，遇到yield语句返回，再次执行时从上次返回的yield语句处继续执行
# 协程coroutine
async def init(loop):
	await orm.create_pool(loop=loop, host='127.0.0.1', port=3306, user='www-data',password='www-data', db='awesome')
	app = web.Application(loop=loop, middlewares=[
		logger_factory, response_factory
	])
	init_jinja2(app, filters=dict(datetime=datetime_filter))
	add_routes(app, 'handlers')
	add_static(app)
	srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)  # 创建一个TCP服务器
	logging.info('server started at http://127.0.0.1:9000...')
	return srv

loop = asyncio.get_event_loop()  # 从asyncio模块中直接获取一个EventLoop的引用
loop.run_until_complete(init(loop))  # 把coroutine扔到EventLoop中执行
loop.run_forever()

