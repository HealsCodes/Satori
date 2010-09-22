# encoding: utf-8
#
# config.py 
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

"""
.. module:: config
    :platform: Unix, MacOS
    :synopsis: Shared settings manager.

.. moduleauthor:: René Köcher <shirk@bitspin.org>

"""

try:
    import re
except:
    import sre as re

import sys, os, optparse, yaml

class _BaseConfig(yaml.YAMLObject):

    def __init__(self, **kwargs):
        self.verbose = False
        self.verbosity = 0
        self.settings = {}
        self.log_facility = 'syslog'
        self.log_filename = '/var/log/satori.log'
        self.log_when = 'D'
        self.log_interval = 1
        self.log_keep = 14
        self.log_traceback = None
        self.settings = {}

    def configure(self):
        if getattr(self, 'debug', None):
            self.verbose = self.debug.get('verbose', False)
            self.verbosity = self.debug.get('verbosity', 0)
            self.log_facility = self.debug.get('log_facility', 'syslog')
            self.log_filename = self.debug.get('log_filename', '/var/log/satori-mb.log')
            self.log_traceback = self.debug.get('log_traceback', None)
            self.log_when = self.debug.get('log_when', 'D')
            self.log_interval = self.debug.get('log_interval', 1)
            self.log_keep = self.debug.get('log_keep', 14)

class _SatoriCoreConfig(_BaseConfig):
    yaml_tag = u'tag:www.bitspin.org,2010:satori-mb/core'
    
    def __init__(self, **kwargs):
        super(_SatoriCoreConfig, self).__init__(**kwargs)

    def configure(self):
        super(_SatoriCoreConfig, self).configure()
        self.jid = self.settings.get('jid', 'satori.example.org')
        self.pid = self.settings.get('pid', '/var/run/jabber/satori-mb.pid')
        self.spool = self.settings.get('spoolDir', '/var/spool/jabber/satori-mb')
        self.server = self.settings.get('mainServer', '127.0.0.1')
        self.server_jid = self.settings.get('mainServerJid', 'example.org')
        self.port = self.settings.get('port', 5347)
        self.secret = self.settings.get('secret', 'secret')
        self.register_ok = self.settings.get('allowRegister', True)
        
        if getattr(self, 'services', None):
            for service in self.services:
                for key in ['tag', 'type', 'useHttps', 'apiHost', 'apiRoot']:
                    if not key in service:
                        raise RuntimeError('Missing "{0}" in service definition'.format(key))
                if service['type'] == 'twitter_oAuth':
                    for key in ['oAuthRoot', 'oAuthKey', 'oAuthSecret']:
                        if not key in service:
                            raise RuntimeError('Missing "{0}" in service definition for "{1}"'.format(key, service['tag']))
                elif service['type'] == 'twitter_BasicAuth':
                        pass
                else:
                    raise RuntimeError('Unknown service type "{0}" in service definition for "{1}"').format(service['type'], service['tag'])
        
                for (key, default) in [('useHttps', False), 
                                       ('searchRoot', None),
                                       ('searchHost', None)]:
                    if not key in service:
                        service[key] = default
        
        return self
    
class Config(object):
    """Global config manager"""
    
    _sharedConfig = None
    _parser       = None
    
    @classmethod
    def add_option(cls, *args, **kwargs):
        """
        Add a new option to the global set of parameters.
        
        After a call to :meth:`Config.get` the parsed options and arguments will
        be accessible as :attr:`Config.option` and :attr:`Config.optargs`.
        
        :param: \*args: positional arguments to passed to :meth:`optparse.OptionParser.add_option`
        :param: \**keywords: keyword arguments to passed to :meth:`optpars.OptionParser.add_option`
        :returns: None
        """
        
        if Config._parser == None:
            Config._parser = optparse.OptionParser()
            
        if args:
            Config._parser.add_option(*args, **kwargs)

    @classmethod
    def get(cls, *args):
        """
        Return the shared Config instance (initalizing it as needed).
        For the config syntax in use see `_synfu-config-syntax`.
        
        :param \*args: optional paths to search for synfu.conf
        :type \*args:  list of strings or None
        :rtype:        :class:`synfu.config.Config`
        :returns:      an initialized :class:`synfu.config.Config` instance
        """
        
        if Config._sharedConfig:
            return Config._sharedConfig
        
        Config.add_option('-c', '--config',
                          dest    = 'config_path',
                          action  = 'store',
                          default = None,
                          help    = 'Path to config file')
        
        paths = ['.', '/etc', '/usr/local/etc']
        paths.insert(0, os.path.join(os.getenv('HOME','/'),'.config'))
        
        if args:
            paths = list(args) + paths
        
        
        (opts, args) = Config._parser.parse_args(sys.argv[1:])
        if opts.config_path:
            paths.insert(0, opts.config_path)
        
        for path in paths:
            try:
                if not path.endswith('satori-mb.conf'):
                    conf_path = os.path.join(path, 'satori-mb.conf')
                else:
                    conf_path = path
                
                Config._sharedConfig = Config(conf_path, opts, args)
                return Config._sharedConfig
                
            except IOError,e:
                pass
        
        raise RuntimeError('Failed to load satori-mb.conf')
    
    def __init__(self, path, options, *optargs):
        super(Config, self).__init__()

        self.core = None
        self.options = options
        self.optargs = optargs
        
        with open(path, 'r') as data:
            for k in yaml.load_all(data.read()):
                if type(k) == _SatoriCoreConfig:
                    self.core = k.configure()

                else:
                    print('What is type(k) == {0} ?'.format(type(k)))
                    
        if not self.core:
            raise RuntimeError('Mandatory core configuration missing.')
    

