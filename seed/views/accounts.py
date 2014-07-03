"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
# system imports
import json

# django imports
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator

# vendor imports
from annoying.decorators import ajax_request

from superperms.orgs.decorators import has_perm, PERMS
from superperms.orgs.exceptions import TooManyNestedOrgs
from superperms.orgs.models import (
    ROLE_OWNER,
    ROLE_MEMBER,
    ROLE_VIEWER,
    Organization,
    OrganizationUser,
)

from seed.utils import create_organization, ASSESSOR_FIELDS_BY_COLUMN

# app imports
from seed.models import CanonicalBuilding
from landing.models import SEEDUser as User
from seed.tasks import (
    invite_to_seed,
)


def _dict_org(request, organizations):
    """returns a dictionary of an organization's data."""
    orgs = []
    for o in organizations:
        # We don't wish to double count sub organization memberships.
        owners = [
            {
                'first_name': ou.user.first_name,
                'last_name': ou.user.last_name,
                'email': ou.user.email,
                'id': ou.user.pk
            }
            for ou in OrganizationUser.objects.filter(
                organization=o, role_level=ROLE_OWNER
            )
        ]
        if OrganizationUser.objects.filter(
            organization=o, user=request.user
        ).exists():
            ou = OrganizationUser.objects.get(
                organization=o, user=request.user)
            role_level = _get_js_role(ou.role_level)
        else:
            role_level = None
        org = {
            'name': o.name,
            'org_id': o.pk,
            'id': o.pk,
            'number_of_users': o.users.count(),
            'user_is_owner': (
                request.user.pk in [own['id'] for own in owners]
            ),
            'user_role': role_level,
            'owners': owners,
            'sub_orgs': _dict_org(request, o.child_orgs.all()),
            'is_parent': o.is_parent,
            'num_buildings': CanonicalBuilding.objects.filter(
                canonical_snapshot__super_organization=o
            ).count(),
        }
        orgs.append(org)

    return orgs


def _get_js_role(role):
    """return the JS friendly role name for user

    :param role: role as defined in superperms.models
    :returns: (string) JS role name
    """
    roles = {
        ROLE_OWNER: 'owner',
        ROLE_VIEWER: 'viewer',
        ROLE_MEMBER: 'member',
    }
    return roles.get(role, 'viewer')


def _get_role_from_js(role):
    """return the OrganizationUser role_level from the JS friendly role name

    :param role: 'member', 'owner', or 'viewer'
    :returns: int role as definer in superperms.models
    """
    roles = {
        'owner': ROLE_OWNER,
        'viewer': ROLE_VIEWER,
        'member': ROLE_MEMBER,
    }
    return roles[role]


@ajax_request
@login_required
def get_organizations(request):
    """returns a list of organizations for the request user"""
    if request.user.is_superuser:
        qs = Organization.objects.all()
    else:
        qs = request.user.orgs.all()

    return {'organizations': _dict_org(request, qs)}


@ajax_request
@login_required
@has_perm('requires_member')
def get_organization(request):
    """returns an organization"""
    org_id = request.GET.get('organization_id', None)
    if org_id is None:
        return {
            'status': 'error',
            'message': 'no organazation_id sent'
        }

    try:
        org = Organization.objects.get(pk=org_id)
    except Organization.DoesNotExist:
        return {
            'status': 'error',
            'message': 'organization does not exist'
        }
    if (
        not request.user.is_superuser and
        not OrganizationUser.objects.filter(
            user=request.user,
            organization=org,
            role_level__in=[ROLE_OWNER, ROLE_MEMBER, ROLE_VIEWER]
        ).exists()
    ):
        # TODO: better permission and return 401 or 403
        return {
            'status': 'error',
            'message': 'user is not the owner of the org'
        }

    return {
        'status': 'success',
        'organization': _dict_org(request, [org])[0],
    }


@ajax_request
@login_required
@has_perm('requires_member')
def get_organizations_users(request):
    """gets users for an org
    TODO(ALECK/GAVIN): check permissions that request.user is owner or admin
    and get more info about the users.
    """
    body = json.loads(request.body)
    org = Organization.objects.get(pk=body['organization_id'])

    users = []
    for u in org.organizationuser_set.all():
        user = u.user
        users.append({
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'user_id': user.pk,
            'role': _get_js_role(u.role_level)
        })

    return {'status': 'success', 'users': users}


@ajax_request
@login_required
@has_perm('requires_owner')
def remove_user_from_org(request):
    """removes a user from an org

    request body should have a json payload like:
    {
        'organization_id': 10,
        'user_id': 2234
    }
    """
    body = json.loads(request.body)
    if body.get('organization_id') is None:
        return {
            'status': 'error',
            'message': 'missing the organization_id'
        }
    try:
        org = Organization.objects.get(pk=body['organization_id'])
    except Organization.DoesNotExist:
        return {
            'status': 'error',
            'message': 'organization does not exist'
        }
    if body.get('user_id') is None:
        return {
            'status': 'error',
            'message': 'missing the user_id'
        }
    try:
        user = User.objects.get(pk=body['user_id'])
    except User.DoesNotExist:
        return {
            'status': 'error',
            'message': 'user does not exist'
        }
    if not OrganizationUser.objects.filter(
        user=request.user, organization=org, role_level=ROLE_OWNER
    ).exists():
        return {
            'status': 'error',
            'message': 'only the organization owner can remove a member'
        }

    ou = OrganizationUser.objects.get(user=user, organization=org)
    ou.delete()

    return {'status': 'success'}


@ajax_request
@login_required
@has_perm('requires_parent_org_owner')
def add_org(request):
    body = json.loads(request.body)
    user = User.objects.get(pk=body['user_id'])
    org_name = body['organization_name']

    if Organization.objects.filter(name=org_name).exists():
        return {
            'status': 'error',
            'message': 'organization name already exists'
        }

    create_organization(user, org_name, org_name)
    return {'status': 'success', 'message': 'organization created'}


@ajax_request
@login_required
@has_perm('requires_owner')
def add_user_to_organization(request):
    """adds a user to an org"""
    body = json.loads(request.body)
    org = Organization.objects.get(pk=body['organization_id'])
    user = User.objects.get(pk=body['user_id'])

    org.add_member(user)

    return {'status': 'success'}


@ajax_request
@login_required
@has_perm('requires_owner')
def add_user(request):
    """creates a SEED user with a lowercase username
    json payload in the form:
    {
        u'organization_id': 1,
        u'first_name': u'Bob',
        u'last_name': u'Dole',
        u'role': {
            u'name': u'Member',
            u'value': u'member'
        },
        u'email': u'b.dol@be.com'
    }

    """
    body = json.loads(request.body)
    org_name = body.get('org_name')
    org_id = body.get('organization_id')
    if ((org_name and org_id) or (not org_name and not org_id)):
            return {
                'status': 'error',
                'message': 'Choose either an existing org or provide a new one'
            }

    if org_id:
        org = Organization.objects.get(pk=org_id)
        org_created = False
    else:
        org, org_created = Organization.objects.get_or_create(name=org_name)

    first_name = body['first_name']
    last_name = body['last_name']
    email = body['email']
    username = body['email']
    user, created = User.objects.get_or_create(username=username.lower())

    # Add the user to the org.  If this is the org's first user,
    # the user becomes the owner/admin automatically.
    # see Organization.add_member()
    if not org.is_member(user):
        org.add_member(user)
    if body.get('role') and body.get('role', {}).get('value'):
        OrganizationUser.objects.filter(
            organization_id=org.pk,
            user_id=user.pk
        ).update(role_level=_get_role_from_js(body['role']['value']))

    if created:
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
    user.save()
    try:
        domain = request.get_host()
    except Exception:
        domain = 'buildingenergy.com'
    invite_to_seed(domain, user.email,
                   default_token_generator.make_token(user), user.pk,
                   first_name)

    return {'status': 'success', 'message': user.email, 'org': org.name,
            'org_created': org_created, 'username': user.username}


@ajax_request
@login_required
@has_perm('requires_member')
def get_users(request):
    users = []
    for u in User.objects.all():
        users.append({'email': u.email, 'user_id': u.pk})

    return {'users': users}


@ajax_request
@login_required
@has_perm('requires_owner')
def update_role(request):
    """updates a SEED user's role
    json payload in the form:
    {
        u'organization_id': 1,
        u'user_id': 2,
        u'role': u'member'
    }
    """
    body = json.loads(request.body)
    role = _get_role_from_js(body['role'])

    OrganizationUser.objects.filter(
        user_id=body['user_id'],
        organization_id=body['organization_id']
    ).update(role_level=role)

    return {'status': 'success'}


@ajax_request
@login_required
@has_perm('requires_owner')
def save_org_settings(request):
    """saves and organzations settings: name, query threshold, shared fields

    for the fields ``checked`` indicates that the field has been selected
    json payload in the form:
    {
        u'organization_id: 2,
        u'organization': {
            u'owners': [...],
            u'query_threshold': 2,
            u'name': u'demo org',
            u'fields': [
                {
                    u'field_type': u'building_information',
                    u'sortable': True,
                    u'title': u'PM Property ID',
                    u'sort_column': u'pm_property_id',
                    u'class': u'is_aligned_right',
                    u'link': True,
                    u'checked': True,
                    u'static': False,
                    u'type': u'link',
                    u'title_class': u''
                },
                {
                    u'field_type': u'building_information',
                    u'sortable': True,
                    u'title': u'Tax Lot ID',
                    u'sort_column': u'tax_lot_id',
                    u'class': u'is_aligned_right',
                    u'link': True,
                    u'checked': True,
                    u'static': False,
                    u'type': u'link',
                    u'title_class': u''
                }
            ],
            u'org_id': 2,
            u'user_is_owner': True,
            u'number_of_users': 4,
            u'id': 2
        }
    }
    """
    body = json.loads(request.body)
    org = Organization.objects.get(pk=body['organization_id'])
    posted_org = body.get('organization', None)
    if posted_org is None:
        return {'status': 'error', 'message': 'malformed request'}

    desired_threshold = posted_org.get('query_threshold', None)
    if desired_threshold is not None:
        org.query_threshold = desired_threshold

    desired_name = posted_org.get('name', None)
    if desired_name is not None:
        org.name = desired_name
    org.save()

    # Update the selected exportable fields.
    new_fields = posted_org.get('fields', None)
    if new_fields is not None:
        old_fields = org.exportable_fields.filter(
            field_model='BuildingSnapshot'
        )
        old_fields_names = set(old_fields.values_list('name', flat=True))
        new_fields_names = set([f['sort_column'] for f in new_fields])

        # remove the fields that weren't posted
        to_remove = old_fields_names - new_fields_names
        org.exportable_fields.filter(name__in=to_remove).delete()

        # add new fields that were posted to the db
        # but only the new ones
        to_add = new_fields_names - old_fields_names
        for new_field_name in to_add:
            org.exportable_fields.create(name=new_field_name,
                                         field_model='BuildingSnapshot')

    return {'status': 'success'}


@ajax_request
@login_required
def get_query_threshold(request):
    """
    returns the ``query_threshold`` for an org
    """
    org_id = request.GET.get('organization_id')
    org = Organization.objects.get(pk=org_id)
    return {
        'status': 'success',
        'query_threshold': org.query_threshold,
    }


@ajax_request
@login_required
def get_shared_fields(request):
    """
    Returns the fields marked as exportable for this org.

    TODO:  Any permissions checks needed?
    TODO:  Are there fields other than those in the ASSESSOR_FIELDS list?
    """
    org_id = request.GET.get('organization_id')
    org = Organization.objects.get(pk=org_id)

    result = {'status': 'success',
              'shared_fields': []}

    for exportable_field in org.exportable_fields.all():
        field_name = exportable_field.name
        shared_field = ASSESSOR_FIELDS_BY_COLUMN[field_name]
        result['shared_fields'].append(shared_field)

    return result


@ajax_request
@login_required
def create_sub_org(request):
    """creates a sub org
    json payload:
    {
        u'parent_org_id': 2,
        u'sub_org': {
            u'name': u'JS',
            u'email': u'JAsd@asd.com'
        }
    }

    """
    body = json.loads(request.body)
    org = Organization.objects.get(pk=body['parent_org_id'])
    email = body['sub_org']['email']
    try:
        user = User.objects.get(username=email)
    except User.DoesNotExist:
        return {
            'status': 'error',
            'message': 'User with email address (%s) does not exist' % email
        }
    sub_org = Organization.objects.create(
        name=body['sub_org']['name']
    )
    org_user, user_added = OrganizationUser.objects.get_or_create(
        user=user, organization=sub_org
    )
    sub_org.parent_org = org

    try:
        sub_org.save()
    except TooManyNestedOrgs:
        sub_org.delete()
        return {
            'status': 'error',
            'message': 'Tried to create child of a child organization.'
        }

    return {'status': 'success'}


@ajax_request
@login_required
def get_actions(request):
    """returns all actions"""
    return {
        'status': 'success',
        'actions': PERMS.keys(),
    }


@ajax_request
@login_required
def is_authorized(request):
    """checks the auth for a given action, if user is the owner of the parent
    org then True is returned for each action

    json payload:
    {
        'organization_id': 2,
        'actions': ['can_invite_member', 'can_remove_member']
    }

    :param actions: from the json payload, a list of actions to check
    :returns: a dict of with keys equal to the actions, and values as bool
    """
    actions, org, error, message = _parse_is_authenticated_params(request)
    if error:
        return {'status': 'error', 'message': message}

    auth = _try_parent_org_auth(request.user, org, actions)
    if auth:
        return {'status': 'success', 'auth': auth}

    try:
        ou = OrganizationUser.objects.get(
            user=request.user, organization=org
        )
    except OrganizationUser.DoesNotExist:
        return {'status': 'error', 'message': 'user does not exist'}

    auth = {action: PERMS[action](ou) for action in actions}
    return {'status': 'success', 'auth': auth}


def _parse_is_authenticated_params(request):
    """checks if the org exists and if the actions are present

    :param request: the request
    :returns: tuple (actions, org, error, message)
    """
    error = False
    message = ""
    body = json.loads(request.body)
    if not body.get('actions'):
        message = 'no actions to check'
        error = True

    try:
        org = Organization.objects.get(pk=body.get('organization_id'))
    except Organization.DoesNotExist:
        message = 'organization does not exist'
        error = True
        org = None

    return (body.get('actions'), org, error, message)


def _try_parent_org_auth(user, organization, actions):
    """checks the parent org for permissions, if the user is not the owner of
    the parent org, then None is returned.

    :param user: the request user
    :param organization_id: id of org to check its parent
    :param actions: list of str actions to check
    :returns: a dict of action permission resolutions or None
    """
    try:
        ou = OrganizationUser.objects.get(
            user=user,
            organization=organization.parent_org,
            role_level=ROLE_OWNER
        )
    except OrganizationUser.DoesNotExist:
        return None

    return {
        action: PERMS['requires_owner'](ou) for action in actions
    }


@ajax_request
@login_required
def get_shared_buildings(request):
    """gets the request user's ``show_shared_buildings`` attr"""
    return {
        'status': 'success',
        'show_shared_buildings': request.user.show_shared_buildings,
    }


@ajax_request
@login_required
def set_default_organization(request):
    """sets the user's default organization"""
    body = json.loads(request.body)
    org = body['organization']
    request.user.default_organization_id = org['id']
    request.user.save()
    return {'status': 'success'}
