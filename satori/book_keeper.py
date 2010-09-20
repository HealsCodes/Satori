# encoding: utf-8
#
#  userdb.py
#
# Copyright (c) 2010 René Köcher <shirk@bitspin.org>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modifica-
# tion, are permitted provided that the following conditions are met:
# 
#   1.  Redistributions of source code must retain the above copyright notice,
#       this list of conditions and the following disclaimer.
# 
#   2.  Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY THE AUTHOR ''AS IS'' AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MER-
# CHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED.  IN NO
# EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPE-
# CIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTH-
# ERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED
# OF THE POSSIBILITY OF SUCH DAMAGE.
#

from sqlalchemy import create_engine
from sqlalchemy import MetaData, Column, Table, ForeignKey
from sqlalchemy import Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, mapper, relation, sessionmaker

Base = declarative_base()

# ----

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    jid = Column(String, nullable=False)
    
    def __init__(self, jid):
        self.jid = jid
    
    def __repr__(self):
        return '<User(\'{0}\')>'.format(self.jid)

class AccountType(Base):
    __tablename__ = 'account_types'
    
    id = Column(Integer, nullable=False, default=0, autoincrement=True)
    name = Column(String, nullable=False, primary_key=True)
    tag = Column(String, nullable=False, primary_key=True)
    
    def __init__(self, name, tag):
        self.name = name
        self.tag = tag
        
    def __repr__(self):
        return '<AccountType(\'{0}\', \'{1}\')>'.format(self.name, self.tag)

class AccountData(Base):
    __tablename__ = 'account_data'
    
    id = Column(Integer, primary_key=True)
    key = Column(String, nullable=True) # user for basic auth, key for oAuth
    secret = Column(String, nullable=True)
    state = Column(String, nullable=False, default='0')
    user_id = Column(Integer, ForeignKey('users.id'))
    type_id = Column(Integer, ForeignKey('account_types.id'))
    
    user = relation(User, backref=backref('accounts', order_by=id), 
                                          cascade='all, delete')
    atype = relation(AccountType, cascade='all, delete')

    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
    
    def __repr__(self):
        return '<AccountData(\'xxxx{0}\', \'xxxx{1}\')>'.format(self.key[-4:], self.secret[-4:])

class BookKeeper(object):
    def __init__(self, dbpath):
        self._engine = create_engine('sqlite:///%s' % dbpath)
        self._metadata = Base.metadata
        self._session = sessionmaker(bind=self._engine)()
        self._metadata.create_all(self._engine)

    def __del__(self):
        if self._session.dirty or self._session.new:
            self._session.commit()
        self._session.close()

    def update_records(self, obj=None):
        if obj:
            self._session.add(obj)
        
        if self._session.new or self._session.dirty:
            self._session.commit()

    def remove(self, obj):
        self._session.delete(obj)
        self._session.commit()

    def user(self, jid, create=False):
        sql = self._session.query(User).filter(User.jid == jid)
        if sql.first():
            return sql.first()
        
        if not create:
            return None
        
        user = User(jid)
        self._session.add(user)
        self._session.commit()
        
        return user
    
    def account_type(self, name, tag):
        sql = self._session.query(AccountType)
        sql = sql.filter(AccountType.name == name)
        sql = sql.filter(AccountType.tag == tag)
        
        if sql.first():
            return sql.first()
        
        account_type = AccountType(name, tag)
        self._session.add(account_type)
        self._session.commit()
        
        return account_type
    
    def account_data(self, jid, tag, key, secret, create=False):
        user  = self._session.query(User).filter(User.jid == jid).first()
        atype = self._session.query(AccountType).filter(AccountType.tag == tag).first()
        
        if not user or not atype:
            return None
            
        sql = self._session.query(AccountData)
        sql = sql.filter(AccountData.user == user)
        sql = sql.filter(AccountData.atype == atype)
        
        if sql.first():
            return sql.first()
            
        if not create or (create and (key is None or secret is None)):
            return None
        
        account_data = AccountData(key, secret)
        account_data.user = user
        account_data.atype = atype
        self._session.add(account_data)
        self._session.commit()
        
        return account_data
        

