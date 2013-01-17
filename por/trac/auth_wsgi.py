# -- Generated file --
import hashlib
import os
import transaction
from ConfigParser import ConfigParser
from time import time

from por.models import DBSession, includeme
from por.models.dashboard import User
from sqlalchemy.orm.exc import NoResultFound

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
    hash = hashlib.md5('%s:%s' % (login, password)).hexdigest()
    if int(time()) - cache.get(hash, 0) < TIMEOUT:
        return True

    db = DBSession()
    try:
	try:
            user = db.query(User).filter_by(svn_login=login).one()
        except NoResultFound:
	    return None
        if user.check_password(password):
            cache[hash] = int(time())
            return True
        else:
            return False
    finally:
	transaction.commit()

TIMEOUT=30
cache = {}
includeme(Config(os.environ['POR_INI']))

def main(*args):
    pass
