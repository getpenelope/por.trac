# inspired by https://github.com/dr4Ke/ldap-to-svn-authz/blob/master/sync_ldap_groups_to_svn_authz.py

from ConfigParser import ConfigParser
from pyramid.threadlocal import get_current_registry

from por.models import DBSession
from por.models.dashboard import User, Subversion


def repo_authz(repo, authz, users):
    if not repo.svn_name:
        return authz

    section = '%s:/' % repo.svn_name
    if not authz.has_section(section):
        authz.add_section(section)
    for user in users:
        roles = user.roles_in_context(repo.project).copy()
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


def generate_authz():
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
    settings = get_current_registry().settings
    svnauth_init = settings.get('por.svn.authz_init')

    db = DBSession()
    authz = ConfigParser()
    authz.read(svnauth_init)

    users = db.query(User).all()
    for repo in db.query(Subversion).all():
        repo_authz(repo, authz, users)

    authz_file = settings.get('por.svn.authz')
    with open(authz_file, 'wb') as configfile:
        authz.write(configfile)

    return authz
