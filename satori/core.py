# encoding: utf-8
#
#  core.py
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

import sys
import os
from supay import Daemon
from xml.etree import cElementTree as ET

import satori
from satori.config import Config
from satori.book_keeper import BookKeeper
from satori.twitter_connector import TwitterConnector

sleekxmpp = satori.sleekxmpp

class Core(object):
    def __init__(self):
        self._config = Config.get().core
        self._book_keeper = BookKeeper(os.path.join(self._config.spool, 
                                                    'bookkeeper.db'))
        self._room_map = {}
        self._xmpp = sleekxmpp.componentxmpp.ComponentXMPP(
                        self._config.jid,
                        self._config.secret,
                        self._config.server,
                        self._config.port)
        
        # setup callbacks
        self._xmpp.add_event_handler('message', self._on_message)
        self._xmpp.add_event_handler('changed_status', self._on_presence)
        self._xmpp.add_event_handler('got_offline', self._on_presence)
        
        # load additional plugins
        for plugin in ['xep_0004', 'xep_0030', 'xep_0050']:
            self._xmpp.registerPlugin(plugin)
        
        # setup xmpp discovery information
        self._xmpp.plugin['xep_0030'].identities['main'] = []
        self._xmpp.plugin['xep_0030'].add_identity(category='client', itype='AI', name='Satori')
        self._xmpp.plugin['xep_0030'].add_identity(category='conference', itype='microblog', name='Satori')
        self._xmpp.plugin['xep_0030'].add_feature('http://jabber.org/protocol/muc')
        
        ## thank you libpurple.. jabber:iq:register would be so much easier!!
        ## but since you don't respect (or even show) register options..
        # self._xmpp.plugin['xep_0030'].add_feature('jabber:iq:register')
        # self._xmpp.add_handler("<iq type='get' xmlns='jabber:component:accept'><query xmlns='jabber:iq:register'/></iq>", self._onRegistration)
        # self._xmpp.add_handler("<iq type='set' xmlns='jabber:component:accept'><query xmlns='jabber:iq:register'/></iq>", self._onRegistration)

    # --- helper methods
    
    def _update_room_map_with_jid(self, jid, room_id):
        added = False
        if type(room_id) == str:
            room_id = sleekxmpp.xmlstream.stanzabase.JID(jid)
        if type(jid) == type(room_id):
            jid = jid.bare

        if not jid in self._room_map:
            self._room_map[jid] = {}
            added = True

        self._room_map[jid]['room'] = room_id.bare
        self._room_map[jid]['nick'] = room_id.resource
        self._room_map[jid]['services'] = []
        return added

    def _get_room_from_jid(self, jid):
        if type(jid) != str and type(jid) != unicode:
            jid = jid.bare

        if not jid in self._room_map:
            return None

        return self._room_map[jid]['room']

    def _make_room_user(self, jid, name):
        room = self._get_room_from_jid(jid)
        if not room:
            return None

        return '{0}/{1}'.format(room, name)

    def _make_muc_presence(self, pfrom, pto, pshow=None, ptype=None, prole=None, pcode=None):
        presence = self._xmpp.makePresence(pfrom=pfrom, pto=pto,
                                           pshow=pshow, ptype=ptype)
        if prole or pcode:
            x = ET.Element('{http://jabber.org/protocol/muc#user}x')
            if prole:
                item = ET.Element('item', {'affiliation' : 'member', 'role' : prole})
                x.append(item)
            if pcode:
                status = ET.Element('status', {'code' : pcode})
                x.append(status)

            presence.append(x)
        return presence

    # --- SleekXMPP event handlers
    
    def _on_message(self, event):
        mfrom = event['from']
        services = ''
        
        if type(event['from']) != str and type(event['from']) != unicode:
            mfrom = event['from'].bare
        
        if not mfrom in self._room_map:
            return
        
        for service in self._room_map[mfrom]['services']:
            # let the service decide about the message..
            services += service.handle_message(mfrom, event['body'])
        
        if services:
            services = 'Message was handled by {0}'.format(services)
            mfrom = self._make_room_user(event['from'], 'Satori')
            self._xmpp.sendMessage(event['from'], None, services, 'groupchat', None, mfrom)
        
    def _on_presence(self, event):
        if event['type'] == 'unavailable':
            # user got offline
            self._xmpp.send(self._make_muc_presence(event['to'],
                                                    event['from'],
                                                    'unavailable',
                                                    prole='member',
                                                    pcode='110'))
            return
        
        if not self._update_room_map_with_jid(event['from'], event['to']):
            # initial presence was already sent
            return
        
        # send initial presence
        pfrom = self._make_room_user(event['from'], 'Satori')
        self._xmpp.sendPresence(pfrom=pfrom, pto=event['from'])
        
        # check for subscribed accounts
        user = self._book_keeper.user(event['from'].bare)
        if user and user.accounts:
            for account in user.accounts:
                if not account.key or not account.secret:
                    continue
                
                try:
                    connector = TwitterConnector(self._book_keeper, account)
                    connector.perform_updates(self, True)
                    self._room_map[event['from'].bare]['services'].append(connector)
                    
                except Exception, e:
#                    print 'Failed to add Connector: {0}'.format(e)
                    pass

    # --- callbacks used by the backend connectors
    def schedule(self, delay, callback, args):
        self._xmpp.schedule(delay, callback, args)
    
    def send_room_message(self, mto, mfrom, mbody, mpubdate=None):
        mfrom = 'Satori' if not mfrom else mfrom
        mfrom = self._make_room_user(mto, mfrom)
        
        if not mfrom:
            return
        
        message = self._xmpp.makeMessage(mto, mbody, None, 'groupchat', None, mfrom)#mbody, mfrom)
        if mpubdate:
            delay = ET.Element('{urn:xmpp:delay}delay',
                               {'from' : mfrom,
                                'stamp': mpubdate.isoformat().split('.')[0] + 'Z'
                               })
            message.append(delay)
        self._xmpp.send(message)
        

    def send_user_message(self, mto, mfrom, mbody, mpubdate=None):
        mfrom = 'Satori' if not mfrom else mfrom
        mfrom = self._make_room_user(mto, mfrom)
        
        self._xmpp.sendMessage(mto, mbody, None, 'chat', None, mfrom)#mbody, mfrom)

    def send_user_presence(self, mto, mfrom, is_present):
        mfrom = 'Satori' if not mfrom else mfrom
        mfrom = self._make_room_user(mto, mfrom)
        
        if is_present:
            self._xmpp.sendPresence(pfrom=mfrom, pto=mto)
        else:
            self._xmpp.sendPresence(pfrom=mfrom, pto=mto, ptype='xa')

    def run(self):
        if self._xmpp.connect():
            self._xmpp.process(threaded=False)
        else:
            raise RuntimeError('Connection to server failed.')

def Run():
    import logging
    #logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s %(message)s')
    
    pid = Config.get().core.pid
    spool_dir = Config.get().core.spool
    args = Config.get().optargs
    (pid_dir, name) = os.path.split(pid)
    
    print name.split('.pid')[0]
    print pid_dir
    daemon = Daemon(name=name.split('.pid')[0], pid_dir=pid_dir,
                    stdin=spool_dir,
                    stdout=spool_dir,
                    stderr=spool_dir)
    
    if 'start' in args[0]:
        daemon.start()
        core = Core()
        core.run()
    
    elif 'stop' in args[0]:
        daemon.stop()
        
    elif 'status' in args[0]:
        daemon.status()
    else:
        print 'Wut?'
        print args
