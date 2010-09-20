
import os
import sys

_EXT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '3rdParty')
for extension in ['SleekXMPP']:
    sys.path.append(os.path.join(_EXT_PATH, extension))

import sleekxmpp
import sleekxmpp.componentxmpp

__all__ = [sleekxmpp, sleekxmpp.componentxmpp]
