#!/usr/bin/env python
#
# -*-python-*-
#
#
# inspired by https://github.com/dr4Ke/ldap-to-svn-authz/blob/master/sync_ldap_groups_to_svn_authz.py
#

import sys
import os
import getopt
from ConfigParser import ConfigParser

from por.models import DBSession, includeme
from por.models.dashboard import User, Subversion

import beaker


beaker.cache.cache_regions.update({
    'calculate_matrix':{},
    'calculate_matrix.expire':3600,
})

_USAGE = '''
authz --ini=etc/production.ini
'''

class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg + _USAGE

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


def main(ini, svnauth_init):
    argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "hai=", ["help", "authz", "ini="])
        except getopt.error, msg:
             raise Usage(msg)

        authz = False
        for (k, v) in opts:
            if k == '--ini':
                ini = v
            if k == '--authz':
                authz = True

        if not ini:
            raise Usage('missing configuration file')

        includeme(Config(ini))

        if authz:
            write_authz(svnauth_init)

    except Usage, err:
        print >>sys.stderr, err.msg
        print >>sys.stderr, "for help use --help"
        return 2


def write_authz(svnauth_init):
    """
        [groups]
        @admin = haren

        ###
        ### deny all but admins to the tree
        ###

        [/]
        * = 
        @admin = rw

        ###
        ### allow more specific people on a per-repo basis below
        ###

        [repo1:/]
        ldap-user1 = rw
        file-user1 = rw

        [repo2:/]
        ldap-user2 = rw
        file-user2 = rw
    """
    db = DBSession()

    # TODO: load data from por.model
    # TODO: caching
    authz = ConfigParser()
    authz.read(svnauth_init)

    # IN REALTA' LA roles_in_context ESPLODE I GRUPPI E I PERMESSI,
    # GESTIRE QUINDI I GRUPPI QUI RISULTEREBBE DUPLICATO
    # authz.add_section('groups')
    # for g in db.query(Group).all():
    #    # TODO
    #    # authz.set('groups', '@admin', 'haren')

    # defaults
    #authz.add_section('/')
    #authz.set('/', '*', 'r')
    # authz.set('/', '@admin', 'rw')

    users = db.query(User).all()

    for repo in db.query(Subversion).all():
        # repos
        section = '%s:/' % repo.application_uri().split('/')[-1]
        authz.add_section(section)
        for user in users:
            roles = user.roles_in_context(repo.project).copy()
            if 'local_developer' in roles:
                roles.add(u'internal_developer')
            if 'local_project_manager' in roles:
                roles.add(u'project_manager')
            acl = [(a.role_id, a.permission_name) for a in repo.acl]
            acl.append(('administrator', 'edit'))
            acl.append(('administrator', 'view'))
            permissions = {}
            for x,y in acl:
                if x in roles:
                    permissions.setdefault(x, []).append(y)
            def perms(p):
                if 'edit' in p and 'view' in p:
                    return 'rw'
                elif 'edit' in p:
                    return 'w'
                elif 'view' in p:
                    return 'r'
            permissions = [perms(k[1]) for k in permissions.items()]
            # to be sure the first is the longest (rw)
            permissions.sort(lambda x,y: cmp(len(x), len(y)), reverse=True)
            if permissions:
                authz.set(section, user.svn_login, permissions[0])

    authz.write(sys.stdout)


if __name__ == "__main__":
    sys.exit(main())
