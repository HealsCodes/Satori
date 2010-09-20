# encoding: utf-8
#
#  twitter_connector.py
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

import tweepy
import datetime
from config import Config

class TwitterConnector(object):
    def __init__(self, book_keeper, account_data):
        self._book_keeper = book_keeper
        self._account_data = account_data
        self._service_data = None
        self._user_cache = {}
        
        if self._account_data:
            self._jid = self._account_data.user.jid
            
            for service in Config.get().core.services:
                if not 'tag' in service or not 'type' in service:
                    continue
                
                if service['tag'] == self._account_data.atype.tag and \
                   service['type'] == self._account_data.atype.name:
                   self._service_data = service
                   break
            
        if self._service_data['type'] == 'twitter_oAuth':
            try:
                self._auth = tweepy.OAuthHandler(self._service_data['oAuthKey'],
                                                 self._service_data['oAuthSecret'])
                if self._account_data and \
                   self._account_data.key and \
                   self._account_data.secret:
                   self._auth.set_access_token(self._account_data.key,
                                               self._account_data.secret)
            except tweepy.TweepError, e:
                raise
        
        elif self._service_data['type'] == 'twitter_BasicAuth':
            try:
                self._auth = tweepy.BasicAuthHandler(self._account_data.key,
                                                     self._account_data.secret)
            except tweepy.TweepError, e:
                raise
        
        try:
            self._api = tweepy.API(self._auth)
        except tweepy.TweepError, e:
            raise
    
    def _update_screen_status(self, name, nick, stamp, core):
        if not nick in self._user_cache:
            self._user_cache[nick] = {}
            self._user_cache[nick]['name'] = name
            self._user_cache[nick]['away'] = False
            self._user_cache[nick]['last'] = stamp
            core.send_user_presence(self._jid, name, True)
        
        if self._user_cache[nick]['last'] - stamp > datetime.timedelta(0, 300, 0):
            if not self._user_cache[nick]['away']:
                self._user_cache[nick]['away'] = True
                core.send_user_presence(self._jid, name, False)
        else:
            if self._user_cache[nick]['away']:
                self._user_cache[nick]['away'] = False
                core.send_user_presence(self._jid, name, True)
        
        self._user_cache[nick]['last'] = stamp
        

    def handle_message(self, mto, mbody, is_direct=False):
        # it's up to us to decide if we actually *need* this message..
        try:
            if not mbody.startswith('@'):
                # out with it
                self._api.update_status(status=mbody)
                return '{0} '.format(self._service_data['tag'])
            
            if not mbody.startswith('@{0}:'.format(self._service_data['tag'])):
                # not our business
                return ''
            
            # targeted reply - parse it
            try:
                (tag, nick, status_id, message) = mbody.split(':')
            except ValueError:
                return ''
            
            try:
                self._api.get_status(status_id)
            except tweepy.TweepError:
                core.send_room_message(self._jid, None, '{0}: {1}'.format(self._service_data['tag'], str(e)))
                return ''
            
            # check if it is a 'command' or a reply..
            message = message.strip()
            if message.lower() == '/favor':
                # add a star
                self._api.create_favorite(status_id)
                
            elif message.lower() == '/retweet':
                # api-retweet
                self._api.retweet(status_id)
                
            elif message.lower() == '/block':
                # block user
                self._api.create_block(screen_name=nick)
                
            elif message.lower() == '/report':
                # report user for spamming
                self._api.report_spam(screen_name=nick)
                
            else:
                # just reply
                self._api.update_status(message, in_reply_to_status_id=status_id)
            
            return '{0} '.format(self._service_data['tag'])
            
        except tweepy.TweepError, e:
            core.send_room_message(self._jid, None, '{0}: {1}'.format(self._service_data['tag'], str(e)))
            return ''
    
    def perform_updates(self, core, show_history=False):        
        user_msgs = []
        user_dms = []
        status_ids = self._account_data.state.split(':')
        if len(status_ids) < 2:
            status_ids = ['0', '0']
        
        try:
            if self._account_data.state != '0':
                user_msgs = self._api.home_timeline(long(status_ids[0]))
                user_dms = self._api.direct_messages(long(status_ids[1]))
            else:
                user_msgs = self._api.home_timeline()
                user_dms = self._api.direct_messages()
                
        except tweepy.TweepError, e:
            core.send_room_message(self._jid, None, '{0}: {1}'.format(self._service_data['tag'], str(e)))
            core.schedule(60, self.perform_updates, [core])
            return
        
        user_msgs.sort(key=lambda x: x.id)
        user_dms.sort(key=lambda x: x.id)
        
        if show_history:
            # send initial presence for all known users
            known_users = {}
            for status in user_msgs:
                if not status.author.screen_name in known_users:
                    known_users[status.author.screen_name] = (status.author.name,
                                                              status.created_at)
            
            for status in user_dms:
                if not status.sender.screen_name in known_users:
                    known_users[status.sender.screen_name] = (status.sender.name,
                                                              status.created_at)
                    
            for name in known_users:
                self._update_screen_status(known_users[name][0], name, 
                                           known_users[name][1], core)
        
        for status in user_msgs:
            body = ''
            body = status.text + '\n'
            body += '[@{0}:{1}:{2} - from {3}]'.format(self._service_data['tag'],
                                                       status.author.screen_name,
                                                       status.id,
                                                       status.source)
            self._update_screen_status('{1}/{0}'.format(self._service_data['tag'], status.author.name),
                                       status.author.screen_name,
                                       status.created_at, core)
            
            if show_history:
                core.send_room_message(self._jid, status.author.name, body, status.created_at)
            else:
                core.send_room_message(self._jid, status.author.name, body)
            status_ids[0] = str(status.id)
            
        for status in user_dms:
            body = ''
            body = status.text + '\n'
            body += '[@{0}:{1}]'.format(status.sender.screen_name,
                                                   status.id)
            self._update_screen_status('{1}/{0}'.format(self._service_data['tag'], status.sender.name),
                                       status.sender.screen_name,
                                       status.created_at, core)
            
            if show_history:
                core.send_user_message(self._jid, status.sender.name, body, status.created_at)
            else:
                core.send_user_message(self._jid, status.sender.name, body)
            status_ids[1] = str(status.id)
        
        self._account_data.state = ':'.join(status_ids)
        core.schedule(60, self.perform_updates, [core])

        
