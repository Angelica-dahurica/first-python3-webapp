import www.orm as orm
from www.models import User, Blog, Comment
import asyncio


async def test(loop):
	await orm.create_pool(loop=loop, user='www-data', password='www-data', db='awesome')
	# u = User(name='Test', email='test@example.com', passwd='1234567890',  image='about:blank')
	u = User.findAll()
	await u
	print(u)

loop = asyncio.get_event_loop()  # 从asyncio模块中直接获取一个EventLoop的引用
loop.run_until_complete(test(loop))  # 把coroutine扔到EventLoop中执行
