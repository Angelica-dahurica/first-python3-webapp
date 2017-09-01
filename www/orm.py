# -*- coding: utf-8 -*-
# object relational mapping

import asyncio
import logging
import aiomysql


def log(sql):
	logging.info('SQL: %s' % sql)


# 创建连接池
@asyncio.coroutine
def create_pool(loop, **kw):
	logging.info('-create database connection pool...')
	global __pool  # 创建一个全局的连接池，每个HTTP请求都可以从连接池中直接获取数据库连接
	__pool = yield from aiomysql.create_pool(
		host=kw.get('host', 'localhost'),
		port=kw.get('port', 3306),
		user=kw['user'],
		password=kw['password'],
		db=kw['db'],
		charset=kw.get('charset', 'utf8'),  # utf8编码
		autocommit=kw.get('autocommit', True),  # 自动提交事务
		maxsize=kw.get('maxsize', 10),
		minsize=kw.get('minsize', 1),
		loop=loop
	)


# SELECT
async def select(sql, args, size=None):
	log(sql)
	global __pool
	async with __pool.get() as conn:
		async with conn.cursor(aiomysql.DictCursor) as cur:
			await cur.execute(sql.replace('?', '%s'), args or ())  # SQL语句的占位符是?，而MySQL的占位符是%s
			if size:
				rs = await cur.fetchmany(size)
			else:
				rs = await cur.fetchall()
		logging.info('rows returned: %s' % len(rs))
		# with 语句适用于对资源进行访问的场合，确保不管使用过程中是否发生异常都会执行必要的“清理”操作，
		# 释放资源，比如文件使用后自动关闭、线程中锁的自动获取和释放等。
		return rs


# INSERT, UPDATE, DELETE
def execute(sql, args):
	log(sql)
	with(yield from __pool) as conn:
		try:
			cur = yield from conn.cursor()
			yield from cur.execute(sql.replace('?', '%s'), args)
			affected = cur.rowcount
			yield from cur.close()
		except BaseException as e:
			raise
		return affected


def create_args_string(num):
	L = []
	for n in range(num):
		L.append('?')
	return ', '.join(L)


class Field(object):
	def __init__(self, name, column_type, primary_key, default):
		self.name = name
		self.column_type = column_type
		self.primary_key = primary_key
		self.default = default

	def __str__(self):
		return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):
	def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100)'):
		super().__init__(name, ddl, primary_key, default)


class IntegerField(Field):
	def __init__(self, name=None, primary_key=False, default=0):
		super().__init__(name, 'bigint', primary_key, default)


class BooleanField(Field):
	def __init__(self, name=None, default=False):
		super().__init__(name, 'boolean', False, default)


class FloatField(Field):
	def __init__(self, name=None, primary_key=False, default=0.0):
		super().__init__(name, 'real', primary_key, default)


class TextField(Field):
	def __init__(self, name=None, default=None):
		super().__init__(name, 'text', False, default)


class ModelMetaclass(type):  # metaclass是创建类，所以必须从`type`类型派生：
	def __new__(mcs, name, bases, attrs):
		# 排除Model类本身
		if name == 'Model':
			return type.__new__(mcs, name, bases, attrs)

		# 获取table名称
		table_name = attrs.get('__table__', None) or name

		logging.info('found model %s (table: %s)' % (name, table_name))

		# 获取所有的Field和主键名
		mappings = dict()
		fields = []
		primary_key = None
		for k, v in attrs.items():
			if isinstance(v, Field):
				logging.info('found mapping: %s ==> %s' % (k, v))
				mappings[k] = v
				if v.primary_key:
					# 找到主键
					if primary_key:
						raise RuntimeError('Duplicate primary key for field: &s' % k)
					primary_key = k
				else:
					fields.append(k)
		if not primary_key:
			raise RuntimeError('Primary key not found.')
		for k in mappings.keys():
			attrs.pop(k)
		escaped_fields = list(map(lambda f: '`%s`' % f, fields))
		attrs['__mappings__'] = mappings  # 保存属性和列的映射关系
		attrs['__tables__'] = table_name
		attrs['__primary_key__'] = primary_key  # 主键属性名
		attrs['__fields__'] = fields  # 除主键外的属性名
		# 构造默认的SELECT, INSERT, UPDATE & DELETE语句
		attrs['__select__'] = 'select `%s`, %s from `%s`' % (primary_key, ','.join(escaped_fields), table_name)
		attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (table_name, ','.join(escaped_fields), primary_key, create_args_string(len(escaped_fields) + 1))
		attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (table_name, ','.join(map(lambda f : '`%s`=?' % (mappings.get(f).name or f), fields)), primary_key)
		attrs['__delete__'] = 'delete form `%s` where `%s`=?' % (table_name, primary_key)
		return type.__new__(mcs, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
	def __init__(self, **kw):
		super(Model, self).__init__(**kw)

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r'''Model' object has no attribute '%s''' % key)

	def __setattr__(self, key, value):
		self[key] = value

	def getValue(self, key):
		return getattr(self, key, None)

	def getValueOrDefault(self, key):
		vaule = getattr(self, key, None)
		if vaule is None:
			field = self.__mappings__[key]
			if field.default is not None:
				vaule = field.default() if callable(field.default) else field.default
				logging.debug('using default value foe %s: %s' % (key, str(vaule)))
		return vaule

	@classmethod
	async def find(cls, pk):
		'   find object by primary key.'
		rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), pk[1], 1)
		if len(rs) == 0:
			return None
		return cls(**rs[0])

	@classmethod
	async def findAll(cls, where=None, args=None, **kw):
		'   find objects by where cluse'
		sql = [cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args = []
		orderBy = kw.get('orderBy', None)
		if orderBy:
			sql.append('orderby')
			sql.append(orderBy)
		limit = kw.get('limit', None)
		if limit is not None:
			sql.append('limit')
			if isinstance(limit, int):
				sql.append('?')
				args.append(limit)
			elif isinstance(limit, tuple) and len(limit) == 2:
				sql.append('?,?')
				args.extend(limit)
			else:
				raise ValueError('Invalid limit value: %s' % str(limit))
		rs = await select(' '.join(sql), args)
		return [cls(**r) for r in rs]

	@classmethod
	async def findNumber(cls, selectField, where=None, args=None):
		'   find number by select and where'
		sql = ['selsect %s _num_ from `%s`' % (selectField, cls.__table__)]
		if where:
			sql.append('where')
			sql.append(where)
		rs = await select(' '.join(sql), args, 1)
		if len(rs) == 0:
			return None
		return rs[0]['_num_']

	@asyncio.coroutine
	def save(self):
		args = list(map(self.getValueOrDefault, self.__fields__))
		args.append(self.getValueOrDefault(self.__primary_key__))
		rows = yield from execute(self.__insert__, args)
		if rows != 1:
			logging.warning('failed to insert record: affected rows %s' % rows)

	async def update(self):
		args = list(map(self.getValue, self.__fields__))
		args.append(self.getValue(self.__primary_key__))
		rows = await execute(self.__update__, args)
		if rows != 1:
			logging.warning('failed to update by primary key: affected rows %s' % rows)

	async def remove(self):
		args = self.getValue(self.__primary_key__)
		rows = await execute(self.__delete__, args)
		if rows != 1:
			logging.warning('failed to remove by primary key: affected rows %s' % rows)
