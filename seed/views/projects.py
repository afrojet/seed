"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
# system imports
import json
import datetime

# django imports
from django.contrib.auth.decorators import login_required
from django.core.cache import cache

# vendor imports
from annoying.decorators import ajax_request
from dateutil import parser


# BE imports
from seed.tasks import (
    add_buildings,
    remove_buildings,
)

from superperms.orgs.decorators import has_perm
from seed.models import (
    Compliance,
    Project,
    ProjectBuilding,
    StatusLabel,
)

from .. import utils


DEFAULT_CUSTOM_COLUMNS = [
    'project_id',
    'project_building_snapshots__status_label__name'
]


@ajax_request
@login_required
@has_perm('requires_viewer')
def get_projects(request):
    """returns all projects in a user's organizations"""
    organization_id = request.GET.get('organization_id', '')
    projects = []

    for p in Project.objects.filter(
        super_organization_id=organization_id,
    ).distinct():
        if p.last_modified_by:
            first_name = p.last_modified_by.first_name
            last_name = p.last_modified_by.last_name
            email = p.last_modified_by.email
        else:
            first_name = None
            last_name = None
            email = None
        p_as_json = {
            'name': p.name,
            'slug': p.slug,
            'status': 'active',
            'number_of_buildings': p.project_building_snapshots.count(),
            # convert to JS timestamp
            'last_modified': int(p.modified.strftime("%s")) * 1000,
            'last_modified_by': {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
            },
            'is_compliance': p.has_compliance,
        }
        if p.has_compliance:
            compliance = p.get_compliance()
            p_as_json['end_date'] = utils.convert_to_js_timestamp(
                compliance.end_date)
            p_as_json['deadline_date'] = utils.convert_to_js_timestamp(
                compliance.deadline_date)
            p_as_json['compliance_type'] = compliance.compliance_type
        projects.append(p_as_json)

    return {'status': 'success', 'projects': projects}


@ajax_request
@login_required
@has_perm('requires_viewer')
def get_project(request):
    """gets a project"""
    project_slug = request.GET.get('project_slug', '')
    organization_id = request.GET.get('organization_id', '')
    project = Project.objects.get(slug=project_slug)
    if project.super_organization_id != int(organization_id):
        return {'status': 'error', 'message': 'Permission denied'}
    project_dict = project.__dict__
    project_dict['is_compliance'] = project.has_compliance
    if project_dict['is_compliance']:
        c = project.get_compliance()
        project_dict['end_date'] = utils.convert_to_js_timestamp(c.end_date)
        project_dict['deadline_date'] = utils.convert_to_js_timestamp(
            c.deadline_date)
        project_dict['compliance_type'] = c.compliance_type
    del(project_dict['_state'])
    del(project_dict['modified'])
    del(project_dict['created'])

    return {'status': 'success', 'project': project_dict}


@ajax_request
@login_required
@has_perm('requires_member')
def delete_project(request):
    """deletes a project"""
    body = json.loads(request.body)
    project_slug = body.get('project_slug', '')
    organization_id = body.get('organization_id')
    project = Project.objects.get(slug=project_slug)
    if project.super_organization_id != organization_id:
        return {'status': 'error', 'message': 'Permission denied'}
    project.delete()
    return {'status': 'success'}


@ajax_request
@login_required
@has_perm('requires_member')
def create_project(request):
    """creates a project"""
    body = json.loads(request.body)
    project_json = body.get('project')

    if Project.objects.filter(
        name=project_json['name'],
        super_organization_id=body['organization_id']
    ).exists():
        return {
            'status': 'error',
            'message': 'project already exists for user'
        }

    project, created = Project.objects.get_or_create(
        name=project_json['name'],
        owner=request.user,
        super_organization_id=body['organization_id'],
    )
    if not created:
        return {
            'status': 'error',
            'message': 'project already exists for the organization'
        }
    project.last_modified_by = request.user
    project.description = project_json.get('description')
    project.save()

    compliance_type = project_json.get('compliance_type', None)
    end_date = project_json.get('end_date', None)
    deadline_date = project_json.get('deadline_date', None)
    if ((compliance_type is not None
         and end_date is not None
         and deadline_date is not None)):
        c = Compliance(project=project)
        c.compliance_type = compliance_type
        c.end_date = parser.parse(project_json['end_date'])
        c.deadline_date = parser.parse(project_json['deadline_date'])
        c.save()

    return {'status': 'success', 'project_slug': project.slug}


@ajax_request
@login_required
@has_perm('requires_member')
def add_buildings_to_project(request):
    """adds buildings to a project"""
    body = json.loads(request.body)
    project_json = body.get('project')
    project = Project.objects.get(slug=project_json['project_slug'])
    add_buildings.delay(
        project_slug=project.slug, project_dict=project_json,
        user_pk=request.user.pk)

    key = project.adding_buildings_status_percentage_cache_key
    return {
        'status': 'success',
        'project_loading_cache_key': key
    }


@ajax_request
@login_required
@has_perm('requires_member')
def remove_buildings_from_project(request):
    """removes buildings from a project"""
    body = json.loads(request.body)
    project_json = body.get('project')
    project = Project.objects.get(slug=project_json['slug'])
    remove_buildings.delay(
        project_slug=project.slug, project_dict=project_json,
        user_pk=request.user.pk)

    key = project.removing_buildings_status_percentage_cache_key
    return {
        'status': 'success',
        'project_removing_cache_key': key
    }


@ajax_request
@login_required
@has_perm('requires_member')
def update_project(request):
    """updates a project details and compliance info"""
    body = json.loads(request.body)
    project_json = body.get('project')
    project = Project.objects.get(slug=project_json['slug'])
    project.name = project_json['name']
    project.last_modified_by = request.user
    project.save()

    if project_json['is_compliance']:
        if project.has_compliance:
            c = project.get_compliance()
        else:
            c = Compliance.objects.create(
                project=project,
            )
        c.end_date = parser.parse(project_json['end_date'])
        c.deadline_date = parser.parse(project_json['deadline_date'])
        c.compliance_type = project_json['compliance_type']
        c.save()
    elif not project_json['is_compliance'] and project.has_compliance:
        # delete compliance
        c = project.get_compliance()
        c.delete()

    return {
        'status': 'success',
        'message': 'project %s updated' % project.name
    }


@ajax_request
@login_required
def get_adding_buildings_to_project_status_percentage(request):
    """returns percentage status while adding buildings to a project"""
    body = json.loads(request.body)
    project_loading_cache_key = body.get('project_loading_cache_key')

    return {
        'status': 'success',
        'progress_object': cache.get(project_loading_cache_key)
    }


@ajax_request
@login_required
@has_perm('requires_viewer')
def get_projects_count(request):
    """returns the number of projects within the orgs a user belongs"""
    organization_id = request.GET.get('organization_id', '')
    projects_count = Project.objects.filter(
        super_organization_id=organization_id
    ).distinct().count()

    return {'status': 'success', 'projects_count': projects_count}


@ajax_request
@login_required
def update_project_building(request):
    """set the ProjectBuilding extra info"""
    body = json.loads(request.body)
    pb = ProjectBuilding.objects.get(
        project__pk=body['project_id'],
        building_snapshot__pk=body['building_id'])
    pb.approved_date = datetime.datetime.now()
    pb.approver = request.user
    status_label = StatusLabel.objects.get(pk=body['label']['id'])
    pb.status_label = status_label
    pb.save()
    return {
        'status': 'success',
        'approved_date': pb.approved_date.strftime("%m/%d/%Y"),
        'approver': pb.approver.email,
    }


@ajax_request
@login_required
def move_buildings(request):
    """moves buildings from source to target project where params are in
       the POST body as a JSON payload

        body = {
            "buildings": [
                "00010811",
                "00010809"
            ],
            "copy": false,
            "search_params": {
                "filter_params": {
                    "project__slug": "proj-1"
                },
                "project_slug": 34,
                "q": "hotels"
            },
            "select_all_checkbox": false,
            "source_project_slug": "proj-1",
            "target_project_slug": "proj-2"
        }

    """
    body = json.loads(request.body)

    utils.transfer_buildings(
        source_project_slug=body['source_project_slug'],
        target_project_slug=body['target_project_slug'],
        buildings=body['buildings'],
        select_all=body['select_all_checkbox'],
        search_params=body['search_params'],
        user=request.user,
        copy_flag=body['copy']
    )
    return {'status': 'success'}


@ajax_request
@login_required
def get_labels(request):
    """gets all lables for a user of any organization the user has access to"""
    labels = utils.get_labels(request.user)
    return {'status': 'success', 'labels': labels}


@ajax_request
@login_required
def add_label(request):
    """creates a StatusLabel inst. from POST body params

        body = {
            "label": {
                "color": "red",
                "id": 9,
                "label": "danger",
                "name": "non compliant"
            }
        }
    """
    body = json.loads(request.body)
    label = body['label']
    status_label, created = StatusLabel.objects.get_or_create(
        # need a better way to get this, maybe one per org
        super_organization=request.user.orgs.all()[0],
        name=label['name'],
        color=label['color'],
    )
    return {'status': 'success'}


@ajax_request
@login_required
def update_label(request):
    """updates a StatusLabel inst., updates in JSON payload params

        body = {
            "label": {
                "color": "orange",
                "id": 9,
                "label": "warning",
                "name": "in review"
            }
        }
    """
    body = json.loads(request.body)
    label = body['label']
    status_label = StatusLabel.objects.get(pk=label['id'])
    status_label.color = label['color']
    status_label.name = label['name']
    status_label.save()
    return {'status': 'success'}


@ajax_request
@login_required
def delete_label(request):
    """deletes a StatusLabel inst. defined in POST params

        body = {
            "label": {
                "color": "gray",
                "id": 18,
                "label": "default",
                "name": "expired"
            }
        }
    """
    body = json.loads(request.body)
    label = body['label']
    status_label = StatusLabel.objects.get(pk=label['id'])
    ProjectBuilding.objects.filter(
        status_label=status_label
    ).update(status_label=None)

    status_label.delete()
    return {'status': 'success'}


@ajax_request
@login_required
def apply_label(request):
    """applies a label to builings defined by params in POST body as a
       JSON payload

        body = {
            "buildings": [
                "IMP75-0004N0027"
            ],
            "label": {
                "color": "green",
                "id": 1,
                "label": "success",
                "name": "Compliant"
            },
            "project_slug": "proj-1",
            "search_params": {
                "filter_params": {
                    "project__slug": "proj-1"
                },
                "project_slug": 34,
                "q": ""
            },
            "select_all_checkbox": false
        }
    """
    body = json.loads(request.body)

    utils.apply_label(
        project_slug=body['project_slug'],
        buildings=body['buildings'],
        select_all=body['select_all_checkbox'],
        label=body['label'],
        search_params=body['search_params'],
        user=request.user,
    )
    return {'status': 'success'}


@ajax_request
@login_required
def remove_label(request):
    """removes a StatusLabel relation from a ProjectBuilding inst.
       The request POST body is a JSON payload with the project and building

        body = {
            "building": {
                ...
                "id": "0004N0027",
                ...
            },
            "project": {
                ...
                "id": 34,
                ...
            }
        }

    """
    body = json.loads(request.body)

    ProjectBuilding.objects.filter(
        project__pk=body['project']['id'],
        building_snapshot__pk=body['building']['id']
    ).update(
        status_label=None
    )

    return {'status': 'success'}
