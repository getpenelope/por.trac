# -- Generated file --
from time import time
import hashlib
from ConfigParser import ConfigParser

from por.models import DBSession, includeme
from por.models.dashboard import User

# TODO: sostituire con un config parser vero?
class Config(object):
    ''' fake config parser ... '''
    def __init__(self, ini):
        self.cfg = ConfigParser()
        self.cfg.read(ini)

    @property
    def registry(self):
        class Registry:
            def __init__(self, cfg):
                self.cfg = cfg
            @property
            def settings(self):
                return dict(self.cfg.items('app:dashboard'))                
        return Registry(self.cfg)

# TODO: cache

def check_password(environ, login, password):
    hash = hashlib.md5('%s:%s').hexdigest()
    if int(time()) - cache.get(hash, 0) < TIMEOUT:
        return True
    else:
        db = DBSession()
        user = db.query(User).filter_by(svn_login=login).one()
        if user:
            if user.check_password(password):
                cache[hash] = int(time())
                return True
            else:
                return False
    return None

TIMEOUT=300
cache = {}

def main(ini, *args):
    includeme(Config(ini))
