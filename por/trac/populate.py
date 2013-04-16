# -*- coding: utf-8 -*-
import os
import lipsum
import random
import tempfile
import subprocess
from datetime import date

from plone.i18n.normalizer import idnormalizer
from pyramid.threadlocal import get_current_registry
from trac.env import Environment
from trac.ticket.model import Ticket
from trac.admin.console import run

from por.models.dbsession import DBSession


def get_reports(**kwargs):
    return (
             ("All Tickets, Active Customer Request",
              """* List all tickets, active customer request.""",
              """SELECT
                 t.id AS ticket
                 , t.summary
                 , t.component 
                 , t.version 
                 , t.severity 
                 , t.milestone 
                 , t.status 
                 , t.owner
                 , t.reporter
                 , t.time AS created
                 , t.changetime AS modified  -- ## Dates are formatted
                 , c.value AS customerrequest
                 -- , t.description AS _description_  -- ## Uses a full row
              FROM ticket t
              INNER JOIN ticket_custom c ON (t.id = c.ticket AND c.name = 'customerrequest')
              INNER JOIN public.customer_requests cr ON c.value = cr.id AND cr.project_id = '%(project_id)s'
              WHERE cr.placement = 2
              """ % kwargs,),
    )


def _execute(cmd):
    handler, fname = tempfile.mkstemp()
    f = open(fname, 'w')
    try:
        try:
            ret = subprocess.call(cmd, stdout=f, stderr=f)
        except OSError, e:
            raise Exception('The cmd %r could not be executed, %r'
                            'full cmd args are: %r'
                                % (cmd[0], e, ' '.join(cmd)))
        if ret != 0:
            raise Exception('Error while executing %r' % ' '.join(cmd))
    finally:
        f.close()
        f = open(fname)
        f.close()
        os.remove(fname)
    return ret


def add_svn_to_project(application):
    from por.models.dashboard import Project

    project = DBSession.query(Project).get(application.project_id)
    settings = get_current_registry().settings

    svnenvs = settings.get('por.svn.envs')
    tracenvs = settings.get('por.trac.envs')

    if not os.path.exists(svnenvs):
        os.mkdir(svnenvs)

    svnname = application.svn_name
    if svnname:
        svn_path = '%s/%s' % (svnenvs, svnname)
        if not os.path.exists(svn_path):
            raise OSError, 'The path %s doesn\'t exists!' % svn_path
    else:
        idx = ''
        while (not svnname):
            svnname = idnormalizer.normalize("%s%s" % (project.id, idx))
            svn_path = '%s/%s' % (svnenvs, svnname)
            if os.path.exists(svn_path):
                idx = idx and (idx+1) or 1
                svnname = None

        _execute(['svnadmin', 'create', svn_path])

    for trac in project.tracs:
        tracname = str(trac.trac_name)
        trac_path = '%s/%s' % (tracenvs, tracname)
        run([trac_path, 'repository add %s %s' % (svnname, svn_path)])
        run([trac_path, 'repository resync %s' % (svnname)])
        run([trac_path, 'config set trac repository_sync_per_request %s' % svnname])

    application.api_uri = 'svn://%s' % svnname
    application.svn_name = svnname


def add_trac_to_project(application,
        smtp_enabled=True,
        privatecomments=True,
        sensitivetickets=True,
        batchmod=True,
        autocompleteusers=True,
        customfieldadmin=True,
        qafields=True,
        privatetickets=False,
        tracwysiwyg=True,
        attachment_max_size=10485760,
        ):

    from por.models.dashboard import Project
    
    project = DBSession.query(Project).get(application.project_id)

    settings = get_current_registry().settings or application.settings
    tracenvs = settings.get('por.trac.envs')

    if not os.path.exists(tracenvs):
        # TODO: logging bootstrap
        os.mkdir(tracenvs)

    tracname = None
    idx = ''
    while (not tracname):
        tracname = idnormalizer.normalize("%s%s" % (project.id, idx))
        trac_path = '%s/%s' % (tracenvs, tracname)
        if os.path.exists(trac_path):
            idx = idx and (idx+1) or 1
            tracname = None

    trac_perm = {
        'administrator': ['TRAC_ADMIN', 'EXTRA_TIMEENTRY'],
        'customer': ['TICKET_CREATE', 'TICKET_MODIFY', 'TICKET_VIEW',
            'WIKI_VIEW', 'XML_RPC',
            'CHANGESET_VIEW', 'FILE_VIEW',
            'LOG_VIEW', 'MILESTONE_VIEW',
            'REPORT_VIEW', 'REPORT_SQL_VIEW',
            'ROADMAP_VIEW', 'SEARCH_VIEW', 'TIMELINE_VIEW'],
        'developer': ['TICKET_CREATE', 'TICKET_MODIFY', 'TICKET_VIEW',
            'WIKI_VIEW', 'XML_RPC',
            'WIKI_CREATE', 'WIKI_MODIFY',
            'CHANGESET_VIEW', 'FILE_VIEW',
            'LOG_VIEW', 'MILESTONE_VIEW',
            'REPORT_VIEW', 'REPORT_SQL_VIEW',
            'ROADMAP_VIEW', 'SEARCH_VIEW',
            'TIMELINE_VIEW', 'REPORT_ADMIN'],
        'internal_developer': ['developer', 'TRAC_ADMIN', 'TIME_ENTRY_ADD'],
        'external_developer': ['developer'],
        'project_manager': ['administrator', 'TIME_ENTRY_ADD'],
    }
    

    pordb = str(DBSession.bind.url)
    run([trac_path, 'initenv "%s" "%s?schema=trac_%s"' % (
         tracname, 
         pordb.replace('postgresql://', 'postgres://'), 
         tracname)])

    tracenv = Environment(trac_path)

    # REPORTS
    cnx = tracenv.get_db_cnx().cnx
    cursor = cnx.cursor()
    cursor.executemany(\
        "INSERT INTO report (title, description, query) VALUES (%s, %s, %s)",
        get_reports(project_id=project.id))
    cursor.close()
    cnx.commit()

    # remove report 2
    cursor = cnx.cursor()
    cursor.execute("DELETE FROM report where id=2;")
    cursor.close()
    cnx.commit()

    # update reports
    cursor = cnx.cursor()
    cursor.execute("""UPDATE report set query='
        SELECT p.value AS __color__,
            t.id AS ticket, summary, t.type AS type, cr.name AS CR,
            owner, status,
            time AS created,
            changetime AS _changetime, t.description AS _description,
            reporter AS _reporter
        FROM ticket t
        LEFT JOIN enum p ON p.name = t.priority AND p.type = ''priority''
        LEFT JOIN ticket_custom tc ON t.id = tc.ticket
        LEFT JOIN public.customer_requests cr ON tc.value = cr.id
        WHERE status <> ''closed''
        AND tc.name = ''customerrequest'' 
        ORDER BY CAST(p.value AS int), milestone, t.type, time' where id=1;""")
    cursor.execute("""UPDATE report set query='
            SELECT p.value AS __color__,
               ''Milestone ''||milestone AS __group__,
               t.id AS ticket, summary, t.type AS type, 
               cr.name AS CR,
               owner, status, 
               time AS created,
               changetime AS _changetime, t.description AS _description,
               reporter AS _reporter
            FROM ticket t
            LEFT JOIN enum p ON p.name = t.priority AND p.type = ''priority''
            LEFT JOIN ticket_custom tc ON t.id = tc.ticket
            LEFT JOIN public.customer_requests cr ON tc.value = cr.id
            WHERE status <> ''closed''
            AND tc.name = ''customerrequest'' 
            ORDER BY (milestone IS NULL),milestone, CAST(p.value AS int), t.type, time' where id=3;""")
    cursor.execute("""UPDATE report set query='
            SELECT p.value AS __color__,
               owner AS __group__,
               t.id AS ticket, summary, milestone,  cr.name AS CR, t.type AS type, time AS created,
               changetime AS _changetime, t.description AS _description,
               reporter AS _reporter
            FROM ticket t
            LEFT JOIN enum p ON p.name = t.priority AND p.type = ''priority''
            LEFT JOIN ticket_custom tc ON t.id = tc.ticket
            LEFT JOIN public.customer_requests cr ON tc.value = cr.id
            WHERE status = ''accepted''
            AND tc.name = ''customerrequest''
            ORDER BY owner, CAST(p.value AS int), t.type, time'
            where id=4;""")
    cursor.execute("""UPDATE report set query='
            SELECT p.value AS __color__,
               owner AS __group__,
               t.id AS ticket, summary, milestone, t.type AS type, cr.name AS CR, time AS created,
               t.description AS _description_,
               changetime AS _changetime, reporter AS _reporter
            FROM ticket t
            LEFT JOIN enum p ON p.name = t.priority AND p.type = ''priority''
            LEFT JOIN ticket_custom tc ON t.id = tc.ticket
            LEFT JOIN public.customer_requests cr ON tc.value = cr.id
            WHERE status = ''accepted''
            AND tc.name = ''customerrequest'' 
            ORDER BY owner, CAST(p.value AS int), t.type, time'
            where id=5;""")
    cursor.execute("""UPDATE report set query='
            SELECT p.value AS __color__,
            (CASE status WHEN ''accepted'' THEN ''Accepted'' ELSE ''Owned'' END) AS __group__,
                 t.id AS ticket, summary, milestone, cr.name AS CR,
                 t.type AS type, priority, time AS created,
                 changetime AS _changetime, t.description AS _description,
                 reporter AS _reporter
            FROM ticket t
            LEFT JOIN enum p ON p.name = t.priority AND p.type = ''priority''
            LEFT JOIN ticket_custom tc ON t.id = tc.ticket
            LEFT JOIN public.customer_requests cr ON tc.value = cr.id
            WHERE t.status <> ''closed'' AND owner = $USER
            AND tc.name = ''customerrequest'' 
            ORDER BY (status = ''accepted'') DESC, CAST(p.value AS int), milestone, t.type, time'
            where id=7;""")
    cursor.execute("""UPDATE report set query='
            SELECT p.value AS __color__,
           (CASE owner 
            WHEN $USER THEN ''My Tickets''
                ELSE ''Active Tickets''
            END) AS __group__,
                t.id AS ticket, summary, milestone, t.type AS type, cr.name AS CR, 
                owner, status,
                time AS created,
                changetime AS _changetime, t.description AS _description,
                reporter AS _reporter
            FROM ticket t
            LEFT JOIN enum p ON p.name = t.priority AND p.type = ''priority''
            LEFT JOIN ticket_custom tc ON t.id = tc.ticket
            LEFT JOIN public.customer_requests cr ON tc.value = cr.id
            WHERE status <> ''closed''
            AND tc.name = ''customerrequest''
            ORDER BY (COALESCE(owner, '''') = $USER) DESC, CAST(p.value AS int), milestone, t.type, time'
            where id=8;""")
    cursor.close()
    cnx.commit()

    # remove default trac's milestones, components, versions
    cursor = cnx.cursor()
    cursor.execute("DELETE FROM milestone;")
    cursor.close()
    cnx.commit()

    cursor = cnx.cursor()
    cursor.execute("DELETE FROM component;")
    cursor.close()
    cnx.commit()

    cursor = cnx.cursor()
    cursor.execute("DELETE FROM version;")
    cursor.close()
    cnx.commit()


    # TODO: attualmente il riferimento dal trac al progetto dashboard è il project_id,
    #       considerando un'instalalzzione che condicide lo stesso stack wsgi,
    #       valutare se deve essere una uri (jsnorpc, xmlrpx, ...)
    #       o un dsn che punti al db, o ...
    tracenv.config.set('por-dashboard', 'project-id', application.project_id)

    # custom templates
    templates = settings.get('por.trac.templates')
    masterconfig = settings.get('por.trac.masterconfig')

    if templates:
        tracenv.config.set('inherit', 'templates_dir', templates)

    # master config
    if masterconfig:
        tracenv.config.set('inherit', 'file', masterconfig)

    # set name and description
    tracenv.config.set('project', 'name', getattr(application, 'project_name', u''))
    tracenv.config.set('project', 'descr', application.name)

    tracenv.config.set('notification', 'smtp_enabled', smtp_enabled and 'true' or 'false')

    tracenv.config.set('notification', 'always_notify_owner', 'true')
    tracenv.config.set('notification', 'always_notify_reporter', 'true')

    tracenv.config.set('attachment', 'max_size', attachment_max_size)

    tracenv.config.set('components', 'trac.por.*', 'enabled')
    tracenv.config.set('components', 'themeengine.admin.*', 'enabled')
    tracenv.config.set('components', 'themeengine.api.*', 'enabled')
    tracenv.config.set('components', 'themeengine.web_ui.*', 'enabled')
    tracenv.config.set('components', 'ticketrelations.*', 'enabled')
    tracenv.config.set('components', 'tracopt.perm.config_perm_provider.extrapermissionsprovider', 'enabled')

    # All the custom permission names are converted to uppercase.
    # It is not possible to have lowercase and distinguish them from the standard permissions.
    tracenv.config.set('extra-permissions', 'extra_timeentry', 'TIME_ENTRY_ADD')

    tracenv.config.set('theme','theme', 'por')
    # ticket-custom
    tracenv.config.set('ticket-custom', 'customerrequest', 'select')
    tracenv.config.set('ticket-custom', 'customerrequest.label', 'Customer Request')
    tracenv.config.set('ticket-custom', 'blocking', 'text')
    tracenv.config.set('ticket-custom', 'blocking.label', 'Blocking')
    tracenv.config.set('ticket-custom', 'blockedby', 'text')
    tracenv.config.set('ticket-custom', 'blockedby.label', 'Blocked By')
    # BBB: ii valori di customerrequest vengono caricati ondemand 
    tracenv.config.set('ticket-custom', 'customerrequest.options', '')

    # see ticket:80
    if qafields:
        tracenv.config.set('ticket-custom', 'issuetype', 'select')
        tracenv.config.set('ticket-custom', 'issuetype.label', 'Natura del problema')
        tracenv.config.set('ticket-custom', 'issuetype.options', '|'.join([u"",
                                u"sistemistica",
                                u"funzionalità",
                                u"design (grafica, layout...)",
                                u"prestazioni",
                                u"mi aspettavo che..."]))
        tracenv.config.set('ticket-custom', 'qa1', 'select')
        tracenv.config.set('ticket-custom', 'qa1.label', 'Verifica soluzione')
        tracenv.config.set('ticket-custom', 'qa1.options', 'non attuata|attuata')
        tracenv.config.set('ticket-custom', 'qa2', 'select')
        tracenv.config.set('ticket-custom', 'qa2.label', 'Efficacia soluzione')
        tracenv.config.set('ticket-custom', 'qa2.options', 'non efficace|efficace')
        tracenv.config.set('ticket-custom', 'esogeno', 'checkbox')
        tracenv.config.set('ticket-custom', 'esogeno.label', 'Ticket aperto dal Cliente')
        tracenv.config.set('ticket-custom', 'esogeno.value', 'false')
        tracenv.config.set('ticket-custom', 'fasesviluppo', 'select')
        tracenv.config.set('ticket-custom', 'fasesviluppo.label', 'Fase sviluppo')
        tracenv.config.set('ticket-custom', 'fasesviluppo.options', '|'.join([u"",
                                u"In lavorazione",
                                u"Per lo staging",
                                u"In staging",
                                u"Per la produzione",
                                u"In produzione"]))

    tracenv.config.set('ticket', 'restrict_owner', 'true')

    tracenv.config.set('ticket-custom', 'milestone.invalid_if', '')

    # WORKFLOW
    tracenv.config.set('ticket-workflow', 'accept', 'new,reviewing -> assigned')
    tracenv.config.set('ticket-workflow', 'accept.operations', 'set_owner_to_self')
    tracenv.config.set('ticket-workflow', 'accept.permissions', 'TICKET_MODIFY')
    tracenv.config.set('ticket-workflow', 'leave', '* -> *')
    tracenv.config.set('ticket-workflow', 'leave.default', '1')
    tracenv.config.set('ticket-workflow', 'leave.operations', 'leave_status')
    tracenv.config.set('ticket-workflow', 'reassign', 'new,assigned,accepted,reopened -> assigned')
    tracenv.config.set('ticket-workflow', 'reassign.operations', 'set_owner')
    tracenv.config.set('ticket-workflow', 'reassign.permissions', 'TICKET_MODIFY')
    tracenv.config.set('ticket-workflow', 'reassign_reviewing', 'reviewing -> *')
    tracenv.config.set('ticket-workflow', 'reassign_reviewing.name', 'reassign review')
    tracenv.config.set('ticket-workflow', 'reassign_reviewing.operations', 'set_owner')
    tracenv.config.set('ticket-workflow', 'reassign_reviewing.permissions', 'TICKET_MODIFY')
    tracenv.config.set('ticket-workflow', 'reopen', 'closed -> reopened')
    tracenv.config.set('ticket-workflow', 'reopen.operations', 'del_resolution')
    tracenv.config.set('ticket-workflow', 'reopen.permissions', 'TRAC_ADMIN')
    tracenv.config.set('ticket-workflow', 'resolve', 'new,assigned,reopened,reviewing -> closed')
    tracenv.config.set('ticket-workflow', 'resolve.operations', 'set_resolution')
    tracenv.config.set('ticket-workflow', 'resolve.permissions', 'TICKET_MODIFY')
    tracenv.config.set('ticket-workflow', 'review', 'new,assigned,reopened -> reviewing')
    tracenv.config.set('ticket-workflow', 'review.operations', 'set_owner')
    tracenv.config.set('ticket-workflow', 'review.permissions', 'TICKET_MODIFY')

    tracenv.config.set('milestone-groups', 'closed', 'closed')
    tracenv.config.set('milestone-groups', 'closed.order', '0')
    tracenv.config.set('milestone-groups', 'closed.query_args', 'group=resolution')
    tracenv.config.set('milestone-groups', 'closed.overall_completion', 'true')

    tracenv.config.set('milestone-groups', 'active', '*')
    tracenv.config.set('milestone-groups', 'active.order', '1')
    tracenv.config.set('milestone-groups', 'active.css_class', 'open')

    tracenv.config.set('milestone-groups', 'new', 'new,reopened')
    tracenv.config.set('milestone-groups', 'new.order', '2')


    # navigation
    tracenv.config.set('metanav', 'logout', 'disabled')

    # permissions
    tracenv.config.set('components', 'trac.por.users.*', 'enabled')
    tracenv.config.set('trac', 'permission_store', 'PorPermissionStore')
    tracenv.config.set('trac', 'show_email_addresses', 'true')

    # xmlrpc plugin
    tracenv.config.set('components', 'tracrpc.api.xmlrpcsystem', 'enabled')
    tracenv.config.set('components', 'tracrpc.xml_rpc.xmlrpcprotocol', 'enabled')
    tracenv.config.set('components', 'tracrpc.web_ui.rpcweb', 'enabled')
    tracenv.config.set('components', 'tracrpc.ticket.*', 'enabled')
    
    # DynamicFields Plugin
    tracenv.config.set('components', 'dynfields.rules.*','enabled')
    tracenv.config.set('components', 'dynfields.web_ui.*','enabled')

    # User & Roles (ReadOnly !!!)
    # tracenv.config.set('user_manager', 'user_store', 'PorUserStore')
    # tracenv.config.set('user_manager', 'attribute_provider', 'PorAttributeProvider')

    # BatchModifyPlugin
    if batchmod:
        tracenv.config.set('components', 'batchmod.web_ui.*', 'enabled')

    # Traccustomfieldadmin
    if customfieldadmin:
        tracenv.config.set('components', 'customfieldadmin.*', 'enabled')

    # PrivateCommentsPlugin
    if privatecomments:
        tracenv.config.set('components', 'privatecomments.privatecomments.*', 'enabled')

    # PrivateTicketPlugin
    if privatetickets:
        tracenv.config.set('components', 'privatetickets.policy.*', 'enabled')
        tracenv.config.set('trac', 'permission_policies',
            'PrivateTicketsPolicy, %s' % tracenv.config.get('trac', 'permission_policies'))
        trac_perm['customer'].append('TICKET_VIEW_SELF')

    # SensitiveTicketsPlugin
    if sensitivetickets:
        tracenv.config.set('components', 'sensitivetickets.*', 'enabled')
        tracenv.config.set('trac', 'permission_policies',
            'SensitiveTicketsPolicy, %s' % tracenv.config.get('trac', 'permission_policies'))
        tracenv.config.set('ticket-custom', 'sensitive.show_if_group', 'administrator|developer')
        # utilizzato se il default e' 1, se il default e' 0 non serve
        # tracenv.config.set('ticket-custom', 'sensitive.clear_on_hide', 'false')
        # tracenv.config.set('ticket-custom', 'sensitive.has_permission', 'SENSITIVE_VIEW')
        tracenv.config.set('ticket-custom', 'sensitive.value', '0')
        trac_perm['developer'].append('SENSITIVE_VIEW')

    # tracwysiwyg
    if tracwysiwyg:
        tracenv.config.set('components', 'tracwysiwyg.wysiwygmodule', 'enabled')

    # AutoCompleteUsers
    if autocompleteusers:
        tracenv.config.set('components', 'autocompleteusers.autocompleteusers', 'enabled')

    tracenv.config.set('wiki', 'max_size', 1048576)

    tracenv.config.set('logging', 'log_file', 'trac.log')
    tracenv.config.set('logging', 'log_level', 'INFO')
    tracenv.config.set('logging', 'log_type', 'file')

    tracenv.config.save()

    # let's remove notification config - it is set by the global config
    tracenv.config.remove('notification', 'smtp_from')
    tracenv.config.remove('notification', 'smtp_from_name')
    tracenv.config.remove('notification', 'replyto')
    tracenv.config.remove('notification', 'smtp_replyto')
    tracenv.config.remove('trac', 'repository_sync_per_request')
    tracenv.config.save()

    run([trac_path, 'upgrade --no-backup'])

    run([trac_path, 'permission remove anonymous *'])
    run([trac_path, 'permission remove authenticated *'])
    for role, perms in trac_perm.items():
        for perm in perms:
            run([trac_path, "permission add %s %s" % (role, perm)])

    run([trac_path, "ticket_type add verification"])

    # hack to minimize config size
    run([trac_path, 'config set browser color_scale True'])

    # add properly milestones
    milestones = getattr(application, 'milestones', [])
    milestones.append({'title': 'Backlog', 'due_date': date.today().replace(year=date.today().year+1)})

    for milestone in milestones:
        due = milestone['due_date']
        if due:
            due = milestone['due_date'].strftime('%Y-%m-%d')
            run([trac_path, 'milestone add "%s" %s' % (milestone['title'], due)])
        else:
            run([trac_path, 'milestone add "%s"' % milestone['title']])

    tickets = getattr(application, 'tickets', [])
    tracenv = Environment(trac_path)
    for ticket in tickets:
        # in this moment the customer request has a proper id
        ticket['customerrequest'] = ticket['customerrequest'].id
        ticket['status'] = 'new'
        t = Ticket(tracenv)
        t.populate(ticket)
        t.insert()

    # i ruoli vengono assegnati dinamicamente interrogando la dashboard
    # del progetto individuato da congif.por-dashboard.project_id
    #
    # for role, users in project.get_local_roles().items():
    #     for user in users:
    #         print "add role:%r to user:%r" % (role.lower(), user)
    #         run([trac_path, "permission add %s %s" % (user, role.lower())])

    application.api_uri = 'trac://%s' % tracname
    application.trac_name = tracname

# !!!!!!!!!
# !!!!!!!!!
# ADD RANDOM TICKETS
def add_trac_tickets(project, customer_request, settings, users):
    g = lipsum.Generator()
    tracname = idnormalizer.normalize(project.name)
    tracenvs = settings.get('por.trac.envs')
    trac_path = '%s/%s' % (tracenvs, tracname)
    tracenv = Environment(trac_path)
    for i in range(50):
        ticket = Ticket(tracenv)
        ticket.populate({
            'summary': g.generate_sentence(),
            'description': g.generate_paragraph(),
            # 'project_id': project.id,
            # 'customerrequest': "%s>%s>%s" % (project.id, customer_request.id, customer_request.name),
            'owner': random.choice(users).email,
            'customerrequest': "%s" % (customer_request.id),
            'status': 'new',
        })
        ticket.insert()
        yield ticket


