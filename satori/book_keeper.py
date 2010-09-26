# encoding: utf-8
#
#  book_keeper.py
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

import thread, threading
from sqlalchemy import create_engine
from sqlalchemy import MetaData, Column, Table, ForeignKey
from sqlalchemy import Integer, String
from sqlalchemy.orm import backref, relationship, sessionmaker, scoped_session
from sqlalchemy.orm import mapper as sqla_mapper
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.exc import SQLAlchemyError

def _session_mapper(cls, scoped_session_):
    """
    support for scoped_session aware mapper class as described in
    http://www.sqlalchemy.org/trac/wiki/UsageRecipes/SessionAwareMapper
    """
    def mapper(cls, *args, **kwargs):
        cls.query = scoped_session_.query_property()
        return sqla_mapper(cls, *args, **kwargs)
    return mapper

_Session = scoped_session(sessionmaker())
_Base = declarative_base()
_mapper = _session_mapper(_Base, _Session)
_Base.mapper = _mapper

class Account(_Base):
    __tablename__ = 'account'
    
    user_id = Column(Integer, ForeignKey('user.id'), primary_key=True)
    service_id = Column(Integer, ForeignKey('service.id'), primary_key=True)
    
    auth_key = Column(String, nullable=False)
    auth_secret = Column(String, nullable=False)
    status = Column(String)
    

    def __init__(self, user, service, auth_key='', auth_secret=''):
        self.user_id = user.id_
        self.service_id = service.id_
        self.user = user
        self.service = service
        self.auth_key = auth_key
        self.auth_secret = auth_secret
        self.status = ''
    
    def __repr__(self):
        return '<Account(user_id={0}, service_id={1}, auth_key="{2}", auth_secret="{3}", status="{4}")>'.format(
            self.user_id, self.service_id, ('x' * 10) + self.auth_key[-4:],
            ('x' * 10) + self.auth_secret[-4:], self.status)


class Service(_Base):
    __tablename__ = 'service'
    
    id_ = Column('id', Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    type_id = Column(Integer, ForeignKey('service_type.id'), nullable=False)
    
    accounts = relationship(Account, backref='service', cascade='all, delete, delete-orphan')
    
    def __init__(self, name, service_type):
        self.name = name
        self.type_id = service_type.id_
        self.type_ = service_type
    
    def __repr__(self):
        return '<Service(id={0}, name="{1}", type_id={2})>'.format(
            self.id_, self.name, self.type_id)

class ServiceType(_Base):
    __tablename__ = 'service_type'

    id_ = Column('id', Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)

    services = relationship(Service, backref='type_', cascade='all, delete, delete-orphan')

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return '<ServiceType(id={0}, name="{1}")>'.format(self.id_, self.name)

class User(_Base):
    __tablename__ = 'user'

    id_ = Column('id', Integer, primary_key=True)
    jid = Column(String, nullable=False, unique=True)

    accounts = relationship(Account, backref='user', cascade='all, delete, delete-orphan')
    
    def __init__(self, jid):
        self.jid = jid

    def __repr__(self):
        return '<User(id={0}, jid="{1}")>'.format(self.id_, self.jid)


class BookKeeper(object):
    def __init__(self, dbpath):
        self._engine = create_engine('sqlite:///{0}'.format(dbpath))
        _Session.configure(bind=self._engine)
        _Base.metadata.create_all(self._engine)
        self._sessions = {}

    def _local_session(self):
        if not thread.get_ident() in self._sessions:
            self._sessions[thread.get_ident()] = _Session()
        return self._sessions[thread.get_ident()]

    def reflect_services(self, config):
        if not getattr(config, 'services', None):
            return
        
        try:
            session = self._local_session()
            # step 1, remove all services _not_ in the config file
            # this will cascade down to the accounts using them
            for service in session.query(Service).all():
                if not service.name in [x['tag'] for x in config.services]:
                    print '* removing obsolete {0}'.format(service)
                    session.delete(service)
            
            # step 2, add new service types (if any)
            known_service_types = [x[0] for x in session.query(ServiceType.name).all()]
            for service_type in [x['type'] for x in config.services if not x['type'] in known_service_types]:
                session.add(ServiceType(service_type))
                print '* creating new service_type {0}'.format(service_type)
            session.commit()
            
            # step 3, add new services (if any)
            known_services = [x[0] for x in session.query(Service.name).all()]
            for service in [x for x in config.services if not x['tag'] in known_services]:
                service_type = session.query(ServiceType).filter(ServiceType.name == service['type']).first()
                session.add(Service(service['tag'], service_type))
                print '* creating new service {0} - {1}'.format(service['tag'], service_type)
            
            # step 4, remove service types no longer in use
            for service_type in session.query(ServiceType):
                if not len(service_type.services):
                    print '* removing orphaned {0}'.format(service_type)
                    
            # step 5, remove orphaned users
            for user in session.query(User):
                if not len(user.accounts):
                    print '* removing orphaned {0}'.format(user)
            session.commit()
            return True
        except SQLAlchemyError as err:
            print '\n***'
            print 'Something went wrong - attempting a rollback!'
            print 'Error was: {0}'.format(err)
            print '***\n'
            session.rollback()
            return False
        
    def account(self, jid=None, service=None, create=False):
        sql = self._local_session().query(Account)
        if service:
            sql = sql.join(Service)
            sql = sql.filter(Account.service_id == Service.id_)
            sql = sql.filter(Service.name == service)
        if jid:
            sql = sql.join(User)
            sql = sql.filter(Account.user_id == User.id_)
            sql = sql.filter(User.jid == jid)
        
        res = sql.all()
        if create and jid and service and not res:
            user = self._local_session().query(User).filter(User.jid == jid).first()
            service_ = self._local_session().query(Service).filter(Service.name == service).first()
            res = [Account(user, service_)]
            self.commit(res[0])
        
        return res
    
    def user(self, jid=None, create=False):
        sql = self._local_session().query(User)
        if jid:
            sql = sql.filter(User.jid == jid)
        
        res = sql.all()
        if create and not res:
            res = [User(jid),]
            self.commit(res[0])
            
        return res
    
    def remove(self, obj):
        session = self._local_session()
        if obj:
            session.delete(obj)
        session.commit()
    
    def commit(self, obj):
        session = self._local_session()
        if obj:
            session.add(obj)
        session.commit()
    
    def release(self):
        if thread.get_ident() in self._sessions:
            self._sessions[thread.get_ident()].close()
            del self._sessions[thread.get_ident()]
    
    def do_tests(self):
        import time, random, thread, threading
        
        def _thread_updater(bookkeeper, jid):
                for i in range(0, 5):
                    account = bookkeeper.account(jid=jid)[0]
                    ident = thread.get_ident()
                    print '- thread {0}: updating data..'.format(ident)
                    print '- thread {0}: before: {1}'.format(ident, account)
                    account.status = '{0}:+{1}'.format(ident, i)
                    bookkeeper.commit(account)
                    print '- thread {0}: after : {1}'.format(ident, account)
                    time.sleep(random.randint(1, 10))
                print '- thread {0}: terminating'.format(thread.get_ident())
        
        users = []
        service_ids = []
        services = []
        accounts = []
        
        print '* Creating basic data..'
        try:
            session = self._local_session()
            users += self.user('john@example.org', create=True)
            users += self.user('jane@example.org', create=True)
            service_ids.append(ServiceType('twitter_oAuth'))
            service_ids.append(ServiceType('twitter_BasicAuth'))
            services.append(Service('twitter', service_ids[0]))
            services.append(Service('identi.ca', service_ids[1]))
            session.add_all(service_ids)
            session.add_all(services)
            session.commit()

            accounts += self.account(users[0].jid, services[0].name, create=True)
            accounts += self.account(users[0].jid, services[1].name, create=True)
            accounts += self.account(users[1].jid, services[0].name, create=True)
            accounts += self.account(users[1].jid, services[1].name, create=True)
            
            session.add_all(accounts)
            session.commit()

        
            print '* Recursive printout for users:'
            for user in users:
                print '- {0}'.format(user)
                for account in user.accounts:
                    print '    --- {0}'.format(account)
                    print '        --- {0}'.format(account.service)
                    print '            --- {0}'.format(account.service.type_)
                print ''
        
                print '* Recursive printout for service_ids:'
                for service_id in service_ids:
                    print '- {0}'.format(service_id)
                    for service in service_id.services:
                        print '    --- {0}'.format(service)
                        for account in service.accounts:
                            print '        --- {0}'.format(account)
                    print ''
            
            print '* Attempting to remove a single account..'
            del users[0].accounts[0]
            session.commit()
        
            print '- Nr. of Accounts for users[0]: {0}'.format(len(users[0].accounts))
            if len(users[0].accounts) != 1:
                print '\n***'
                print 'Somathing went wrong, I expected only one account!'
                print '***\n'
                return False
            else:
                print ''
        
            print '* Attempting a cascaded delete of service_ids[0]..'
            
            session.delete(service_ids[0])
            session.commit()
            res = session.query(Service).filter(Service.type_ == service_ids[0]).all()
            if res:
                print '\n***'
                print 'Something went wrong, I expected no remaining Services!'
                print 'Got: {0}'.format(res)
                print '***\n'
                return False
            else:
                print '- no Services left referencing this service_type'
                
            res = session.query(Account).filter(Account.service == services[0]).all()
            if res:
                print '\n***'
                print 'Something went wrong, I expected no remaining Accounts!'
                print 'Got: {0}'.format(res)
                print '***\n'
                return False
            else:
                print '- no Accounts left referencing this service_type'
                print '- OK\n'
                
            print '* Attempting a cascaded delete of all users[1]..'
            session.delete(users[1])
            session.commit()
            res = session.query(Account).filter(Account.user == users[1]).all()
            if res:
                print '\n***'
                print 'Something went wrong, I expected no remaining Accounts!'
                print 'Got: {0}'.format(res)
                print '***\n'
                return False
            else:
                print '- no Accounts left referencing this user'
                print '- OK\n'
            
            print '* Attempting a multi-threaded data update..'
            threading.Thread(target=_thread_updater, args=(self, users[0].jid,)).start()
            threading.Thread(target=_thread_updater, args=(self, users[0].jid,)).start()
            
            while threading.active_count() > 1:
                time.sleep(1)
            print '- OK\n'
            
        except SQLAlchemyError as err:
            print '\n***'
            print 'Something went wrong, please make sure "test.db" doesn\'t already exist.'
            print 'Error was: {0}'.format(err)
            print '***\n'
            return False
        
        print '--- Looks good :)'
        

if __name__ == '__main__':
    bookkeeper = BookKeeper('test.db')
    bookkeeper.do_tests()