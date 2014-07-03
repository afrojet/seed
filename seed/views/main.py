"""
:copyright: (c) 2014 Building Energy Inc
:license: BSD 3-Clause, see LICENSE for more details.
"""
# system imports
import json
import datetime
import uuid

# django imports
from django.contrib.auth.decorators import login_required, permission_required
from django.core.cache import cache
from django.conf import settings
from django.core.files.storage import DefaultStorage
from django.db.models import Q

# vendor imports
from annoying.decorators import render_to, ajax_request
from mcm import mapper


# BE imports
from data_importer.models import ImportFile, ImportRecord, ROW_DELIMITER
from landing.models import SEEDUser as User

from seed.tasks import (
    map_data,
    remap_data,
    match_buildings,
    save_raw_data as task_save_raw,
)

from superperms.orgs.decorators import has_perm
from seed import models, tasks
from seed.models import (
    get_column_mapping,
    save_snapshot_match,
    BuildingSnapshot,
    ColumnMapping,
    Project,
    ProjectBuilding,
    get_ancestors,
    unmatch_snapshot_tree as unmatch_snapshot,
)
from seed.views.accounts import _get_js_role
from superperms.orgs.models import Organization, OrganizationUser
from .. import utils
from .. import search
from .. import exporter

DEFAULT_CUSTOM_COLUMNS = [
    'project_id',
    'project_building_snapshots__status_label__name'
]


@render_to('seed/jasmine_tests/AngularJSTests.html')
def angular_js_tests(request):
    """Jasmine JS unit test code covering AngularJS unit tests and ran
       by ./manage.py harvest

    """
    return locals()


def _get_default_org(user):
    """Gets the default org for a user and returns the id, name, and
    role_level. If no default organization is set for the user, the first
    organization the user has access to is set as default if it exists.

    :param user: the user to get the default org
    :returns: tuple (Organization id, Organization name, OrganizationUser role)
    """
    org = user.default_organization
    # check if user is still in the org, i.e. s/he wasn't removed from his/her
    # default org or didn't have a set org and try to set the first one
    if (
        not org
        or not OrganizationUser.objects.filter(
            organization=org, user=user
        ).exists()
    ):
        org = user.orgs.first()
        user.default_organization = org
        user.save()
    if org:
        org_id = org.pk
        org_name = org.name
        ou = user.organizationuser_set.filter(organization=org).first()
        # parent org owner has no role (None) yet has access to the sub-org
        org_user_role = _get_js_role(ou.role_level) if ou else ""
        return org_id, org_name, org_user_role
    else:
        return "", "", ""


@render_to('seed/index.html')
@login_required
def home(request):
    """the main view for the app
        Sets in the context for the django template:
            app_urls: a json object of all the urls that is loaded in the JS
                      global namespace
            username: the request user's username (first and last name)
            AWS_UPLOAD_BUCKET_NAME: S3 direct upload bucket
            AWS_CLIENT_ACCESS_KEY: S3 direct upload client key
    """
    username = request.user.first_name + " " + request.user.last_name
    AWS_UPLOAD_BUCKET_NAME = settings.AWS_BUCKET_NAME
    AWS_CLIENT_ACCESS_KEY = settings.AWS_UPLOAD_CLIENT_KEY

    initial_org_id, initial_org_name, initial_org_user_role = _get_default_org(
        request.user
    )

    return locals()


@login_required
@permission_required('seed.can_access_admin')
@render_to('seed/admin.html')
def admin(request):
    return locals()


@ajax_request
@login_required
def export_buildings(request):
    """
    Begins a building export process. Expects something like this:
    {
      "export_name": "My Export",
      "export_type": "csv",
      "selected_building": [ '1234', ... ],
      "selected_fields": [ 'tax_lot_id', ... ], // optional, defaults to all
      "select_all_checkbox": True // optional, defaults to False
    }
    """
    body = json.loads(request.body)

    export_name = body.get('export_name')
    export_type = body.get('export_type')

    building_ids = body.get('building_ids')

    selected_fields = body.get('selected_fields', [])

    selected_building_ids = body.get('selected_buildings', [])

    project_id = body.get('project_id')

    if not body.get('select_all_checkbox', False):
        selected_buildings = utils.get_search_query(request.user, {})
        selected_buildings = selected_buildings.filter(
            pk__in=selected_building_ids
        )
    else:
        selected_buildings = utils.get_search_query(request.user, body)
        selected_buildings = selected_buildings.exclude(
            pk__in=selected_building_ids
        )

    export_id = str(uuid.uuid4())

    # If we receive a project ID, we don't actually want to export buildings,
    # we want to export ProjectBuildings -- but the frontend doesn't know that,
    # so we change the fieldnames on the backend instead so the exporter can
    # resolve them correctly
    if project_id:
        export_model = 'seed.ProjectBuilding'

        # Grab the project buildings associated with the given project id and
        # buildings list
        selected_building_ids = [
            x[0] for x in selected_buildings.values_list('pk')
        ]
        selected_buildings = ProjectBuilding.objects.filter(
            project_id=project_id,
            building_snapshot__in=selected_building_ids)

        # Swap the requested fieldnames to reflect the new point of reference
        _selected_fields = []
        for field in selected_fields:
            components = field.split("__", 1)
            if (components[0] == 'project_building_snapshots'
                    and len(components) > 1):
                _selected_fields.append(components[1])
            else:
                _selected_fields.append("building_snapshot__%s" % field)
        selected_fields = _selected_fields
    else:
        export_model = 'seed.BuildingSnapshot'

    building_ids = [x[0] for x in selected_buildings.values_list('pk')]

    cache.set("export_buildings__%s" % export_id, 0)

    tasks.export_buildings.delay(export_id,
                                 export_name,
                                 export_type,
                                 building_ids,
                                 export_model,
                                 selected_fields)

    return {
        "success": True,
        "status": "success",
        "export_id": export_id,
        "total_buildings": selected_buildings.count(),
    }


@ajax_request
@login_required
def export_buildings_progress(request):
    """
    Returns current progress on building export
    Expects: { "export_id": "1234" }
    """
    body = json.loads(request.body)
    export_id = body.get('export_id')
    return {
        "success": True,
        "status": "success",
        "buildings_processed": cache.get("export_buildings__%s" % export_id),
    }


@ajax_request
@login_required
def export_buildings_download(request):
    """
    Redirects to an export file
    """
    body = json.loads(request.body)
    export_id = body.get('export_id')

    export_subdir = exporter._make_export_subdirectory(export_id)
    keys = list(DefaultStorage().bucket.list(export_subdir))

    if not keys or len(keys) > 1:
        return {
            "success": False,
            "status": "error",
        }

    download_key = keys[0]
    download_url = download_key.generate_url(900)

    return {
        'success': True,
        "status": "success",
        "url": download_url
    }


@ajax_request
@login_required
def match_seed_record(request, import_record_pk):
    """deprecated"""
    pass


@ajax_request
@login_required
def match_seed_record_progress(request, import_record_pk):
    import_record = ImportRecord.objects.get(pk=import_record_pk)
    pct = cache.get(import_record.match_progress_key)
    return {"pct": pct}


@ajax_request
@login_required
@permission_required('seed.can_access_admin')
def get_users(request):
    users = []
    for u in User.objects.all():
        users.append({'email': u.email, 'user_id': u.pk})

    return {'users': users}


@ajax_request
@login_required
@permission_required('seed.can_access_admin')
def get_users_all(request):
    users = []
    for u in User.objects.all():
        users.append({'email': u.email, 'user_id': u.pk})

    return {'users': users}
    return users


@ajax_request
@login_required
def get_buildings_for_user(request):
    """gets all BuildingSnapshot inst. buildings a user has access to"""
    buildings = utils.get_buildings_for_user(request.user)
    return {'status': 'success', 'buildings': buildings}


@ajax_request
@login_required
def get_total_number_of_buildings_for_user(request):
    """gets a count of all buildings in the user's organaztions"""
    buildings_count = utils.get_buildings_for_user_count(request.user)

    return {'status': 'success', 'buildings_count': buildings_count}


@ajax_request
@login_required
@has_perm('requires_viewer')
def get_building(request):
    """gets a building"""
    building_id = request.GET.get('building_id')
    organization_id = request.GET.get('organization_id')
    org = Organization.objects.get(pk=organization_id)
    building = BuildingSnapshot.objects.get(pk=building_id)
    user_orgs = request.user.orgs.all()
    parent_org = user_orgs[0].get_parent()

    if (
        building.super_organization in user_orgs
        or parent_org in user_orgs
    ):
        building_dict = building.to_dict()
    else:
        # User isn't in the parent org or the building's org,
        # so only show shared fields.
        exportable_fields = parent_org.exportable_fields
        exportable_field_names = exportable_fields.values_list('name',
                                                               flat=True)
        building_dict = building.to_dict(exportable_field_names)

    ancestors = get_ancestors(building)
    imported_buildings_list = []
    for b in ancestors:
        d = b.to_dict()
        # get deleted import file names without throwing an error
        imp_file = ImportFile.raw_objects.get(pk=b.import_file_id)
        d['import_file_name'] = imp_file.filename_only
        # do not show deleted import file sources
        if not imp_file.deleted:
            imported_buildings_list.append(d)
    imported_buildings_list.sort(key=lambda x: x['source_type'])

    projects = utils.get_compliance_projects(building, org)
    ou = request.user.organizationuser_set.filter(
        organization=building.super_organization
    ).first()

    return {
        'status': 'success',
        'building': building_dict,
        'imported_buildings': imported_buildings_list,
        'compliance_projects': projects,
        'user_role': _get_js_role(ou.role_level) if ou else "",
        'user_org_id': ou.organization.pk if ou else "",
    }


@ajax_request
@login_required
@has_perm('requires_viewer')
def get_datasets_count(request):
    """returns the number of datasets within the orgs a user belongs"""
    organization_id = request.GET.get('organization_id', '')
    datasets_count = Organization.objects.get(
        pk=organization_id).import_records.all().distinct().count()

    return {'status': 'success', 'datasets_count': datasets_count}


@ajax_request
@login_required
def search_buildings(request):
    """returns a paginated list of BuildingSnapshot inst. buildings matching
       search params and pagination params
    """
    body = json.loads(request.body)

    q = body.get('q', '')
    other_search_params = body.get('filter_params', {})
    if 'exclude' in other_search_params:
        exclude = other_search_params['exclude']
        del(other_search_params['exclude'])
    else:
        exclude = {}

    order_by = body.get('order_by', 'tax_lot_id')
    if order_by == '':
        order_by = 'tax_lot_id'
    distinct_order_by = order_by
    sort_reverse = body.get('sort_reverse', False)
    page = int(body.get('page', 1))
    number_per_page = int(body.get('number_per_page', 10))
    if sort_reverse:
        order_by = "-%s" % order_by
    # get all buildings for a user's orgs and sibling orgs
    orgs = request.user.orgs.all()
    other_orgs = []
    if request.user.show_shared_buildings:
        for org in orgs:
            if org.parent_org:
                # this is a child org, so get all of the other
                # child orgs of this org's parents.
                other_orgs.extend(org.parent_org.child_orgs.all())
            else:
                # this is a parent org, so get all of the child orgs
                other_orgs.extend(org.child_orgs.all())
        # Also, find the parent org and add that.
        parent_org = orgs.first().get_parent()
        if parent_org not in orgs:
            other_orgs.append(parent_org)
    building_snapshots = create_building_queryset(
        orgs, exclude, distinct_order_by, other_orgs=other_orgs
    )

    buildings_queryset = search.search_buildings(
        q, queryset=building_snapshots
    )
    buildings_queryset = search.filter_other_params(
        buildings_queryset, other_search_params
    )
    parent_org = orgs.first().parent_org
    below_threshold = False
    if (
        parent_org
        and parent_org.query_threshold
        and buildings_queryset.count() < parent_org.query_threshold
    ):
        below_threshold = True
    buildings = search.generate_paginated_results(
        buildings_queryset,
        number_per_page=number_per_page,
        page=page,
        whitelist_orgs=orgs,
        below_threshold=below_threshold,
    )
    project_slug = None
    if other_search_params and 'project__slug' in other_search_params:
        project_slug = other_search_params['project__slug']
    if body.get('project_id'):
        buildings = utils.update_buildings_with_labels(
            buildings, body.get('project_id'))
    elif project_slug:
        project_id = Project.objects.get(slug=project_slug).pk
        buildings = utils.update_buildings_with_labels(buildings, project_id)

    return {
        'status': 'success',
        'buildings': buildings,
        'number_matching_search': buildings_queryset.count(),
        'number_returned': len(buildings)
    }


def create_building_queryset(orgs, exclude, order_by, other_orgs=None):
    """creats a querset of buildings within orgs. If ``other_orgs``, buildings
    in both orgs and other_orgs will be represented in the queryset.

    :param orgs: queryset of Organiazation inst.
    :param exclude: django query exclude dict.
    :param order_by: django query order_by str.
    :param other_orgs: list of other orgs to ``or`` the query
    """
    if other_orgs:
        return BuildingSnapshot.objects.order_by(
            order_by, 'pk'
        ).filter(
            (
                Q(super_organization__in=orgs) |
                Q(super_organization__in=other_orgs)
            ),
            canonicalbuilding__active=True
        ).exclude(**exclude).distinct(order_by, 'pk')
    else:
        return BuildingSnapshot.objects.order_by(
            order_by, 'pk'
        ).filter(
            super_organization__in=orgs,
            canonicalbuilding__active=True
        ).exclude(**exclude).distinct(order_by, 'pk')


@ajax_request
@login_required
def search_PM_buildings(request):
    """returns a paginated list of BuildingSnapshot inst. buildings matching
       search params and pagination params
    """

    body = json.loads(request.body)
    q = body.get('q', '')
    other_search_params = body.get('filter_params', {})
    order_by = body.get('order_by', 'pm_property_id')
    if not order_by or order_by == '':
        order_by = 'pm_property_id'
    sort_reverse = body.get('sort_reverse', False)
    page = int(body.get('page', 1))
    number_per_page = int(body.get('number_per_page', 10))
    import_file_id = body.get(
        'import_file_id'
    ) or other_search_params.get('import_file_id')
    if sort_reverse:
        order_by = "-%s" % order_by
    pm_buildings = BuildingSnapshot.objects.order_by(order_by).filter(
        import_file__pk=import_file_id,
        source_type__in=[2, 3]  # only search ASSESSED_BS, PORTFOLIO_BS
    )

    fieldnames = [
        'pm_property_id',
        'address_line_1',
        'property_name',
    ]

    buildings_queryset = search.search_buildings(q, fieldnames=fieldnames,
                                                 queryset=pm_buildings)
    buildings_queryset = search.filter_other_params(buildings_queryset,
                                                    other_search_params)
    buildings = search.generate_paginated_results(
        buildings_queryset, number_per_page=number_per_page, page=page)

    return {
        'status': 'success',
        'buildings': buildings,
        'number_matching_search': buildings_queryset.count(),
        'number_returned': len(buildings)
    }


@ajax_request
@login_required
def get_PM_building(request):
    """returns a paginated list of BuildingSnapshot inst. buildings matching
       search params and pagination params
    """
    body = json.loads(request.body)
    b = BuildingSnapshot.objects.get(pk=body['building_id'])
    # converts dates for JSON serialization
    building = b.__dict__.copy()
    for key, val in building.items():
        if type(val) == datetime.datetime or type(val) == datetime.date:
            building[key] = utils.convert_to_js_timestamp(val)
    del(building['_state'])
    c = b.canonical_building
    if c and c.canonical_snapshot:
        building['matched'] = True
        building['confidence'] = c.canonical_snapshot.confidence
    else:
        building['matched'] = False

    return {
        'status': 'success',
        'building': building,
    }


@ajax_request
@login_required
def get_PM_building_matches(request):
    """deprecated"""
    pass


@ajax_request
@login_required
def get_default_columns(request):
    """front end is expecting a JSON object with an array of field names
        i.e.
        {
            "columns": ["project_id", "name", "gross_floor_area"]
        }
    """
    columns = request.user.default_custom_columns

    if columns == '{}' or type(columns) == dict:
        initial_columns = True
        columns = DEFAULT_CUSTOM_COLUMNS
    else:
        initial_columns = False
    if type(columns) == unicode:
        # postgres 9.1 stores JSONField as unicode
        columns = json.loads(columns)

    return {
        'status': 'success',
        'columns': columns,
        'initial_columns': initial_columns,
    }


@ajax_request
@login_required
def set_default_columns(request):
    """sets the default value for the user's default_custom_columns"""
    body = json.loads(request.body)
    columns = body['columns']
    show_shared_buildings = body.get('show_shared_buildings')
    for x in DEFAULT_CUSTOM_COLUMNS[::-1]:
        if x not in columns:
            columns.insert(0, x)
    request.user.default_custom_columns = columns
    if show_shared_buildings is not None:
        request.user.show_shared_buildings = show_shared_buildings
    request.user.save()
    return {'status': 'success'}


@ajax_request
@login_required
def get_columns(request):
    """returns a JSON list of columns a user can select as his/her default"""
    is_project = request.GET.get('is_project', '')
    if is_project == 'true':
        project = Project.objects.get(slug=request.GET.get('project_slug'))
        is_project = project.has_compliance
    else:
        is_project = False
    return utils.get_columns(is_project)


@ajax_request
@login_required
@has_perm('can_modify_data')
def save_match(request):
    """adds and removes matches to/from an ImportedBuilding

        JSON payload:
            body = {
                'source_building_id': 123,
                'target_building_id': 512,
                'create_match': True
            }

       called from services.js building_factory.save_match

    """
    body = json.loads(request.body)
    create = body.get('create_match')
    b1_pk = body['source_building_id']
    b2_pk = body.get('target_building_id')
    child_id = None

    if create:
        child_id = save_snapshot_match(
            b1_pk, b2_pk, user=request.user, match_type=2
        )
        child_id = child_id.pk
    else:
        unmatch_snapshot(b1_pk)

    return {
        'status': 'success',
        'child_id': child_id,
    }


@ajax_request
@login_required
def get_PM_filter_by_counts(request):
    """returns the number of todo and done, in the future, it will return
       number of results in each confidence range

    """
    import_file_id = request.GET.get('import_file_id', '')

    matched = BuildingSnapshot.objects.filter(
        import_file__pk=import_file_id,
        source_type__in=[2, 3],
        children__isnull=False
    ).count()
    unmatched = BuildingSnapshot.objects.filter(
        import_file__pk=import_file_id,
        source_type__in=[2, 3],
        children__isnull=True
    ).count()
    return {
        'status': 'success',
        'matched': matched,
        'unmatched': unmatched,
    }


@ajax_request
@login_required
def get_column_mapping_suggestions(request):
    """Returns probabalistic structure for each dest column.

    Requires that we have a PK for the ImportFile to reference.

    """
    body = json.loads(request.body)
    import_file = ImportFile.objects.get(pk=body.get('import_file_id'))
    result = {'status': 'success'}
    column_types = utils.get_mappable_types()
    suggested_mappings = mapper.build_column_mapping(
        import_file.first_row_columns,
        column_types.keys(),
        previous_mapping=get_column_mapping,
        map_args=[import_file.import_record.super_organization],
        thresh=20  # percentage match we require
    )

    for m in suggested_mappings:
        dest, conf = suggested_mappings[m]
        if dest is None:
            suggested_mappings[m][0] = u''

    result['suggested_column_mappings'] = suggested_mappings
    result['building_columns'] = column_types.keys()
    result['building_column_types'] = column_types

    return result


@ajax_request
@login_required
def get_raw_column_names(request):
    """Returns a list of the raw column names."""
    body = json.loads(request.body)
    import_file = ImportFile.objects.get(pk=body.get('import_file_id'))

    return {
        'status': 'success',
        'raw_columns': import_file.first_row_columns
    }


@ajax_request
@login_required
def get_first_five_rows(request):
    """Returns a list of the raw column names."""
    body = json.loads(request.body)
    import_file = ImportFile.objects.get(pk=body.get('import_file_id'))

    rows = [
        r.split(ROW_DELIMITER)
        for r in import_file.cached_second_to_fifth_row.splitlines()
    ]

    return {
        'status': 'success',
        'first_five_rows': [
            dict(
                zip(import_file.first_row_columns, row)
            ) for row in rows
        ]
    }


@ajax_request
@login_required
@has_perm('requires_member')
def save_column_mappings(request):
    """User confirms, changes structure, we save those mappings.

    We expect that the body of our request is JSON serialized data like:
    {
        "import_file_id": 123,
        "mappings": [
            ["dest_field": "raw_field"],
            ["dest_field2": ["raw_field1", "raw_field2"],
            ...
        ]
    }

    valid source types are found in ``seed.models.SEED_DATA_SOURCES``

    """
    body = json.loads(request.body)
    import_file = ImportFile.objects.get(pk=body.get('import_file_id'))
    organization = import_file.import_record.super_organization
    mappings = body.get('mappings', [])
    # Because we store the ImportFile.source_type as a str, not an int..
    source_type = utils.get_source_type(
        import_file, source_type=body.get('source_type', '')
    )

    for mapping in mappings:
        dest_field, raw_field = mapping
        if dest_field == '':
            dest_field = None

        if isinstance(raw_field, list):
            # Turn this back into a string for DB storage.
            # We'll rehydrate in our tasks to pass to MCM.
            raw_field = json.dumps(raw_field)
        # unique together on organization, column_raw, and source_type
        column_mapping, created = ColumnMapping.objects.get_or_create(
            super_organization=organization,
            column_raw=raw_field,
            source_type=source_type,
        )
        column_mapping.user = request.user
        column_mapping.column_mapped = dest_field
        column_mapping.save()

    return {'status': 'success'}


@ajax_request
@login_required
@has_perm('can_modify_data')
def create_dataset(request):
    """User creates a new data set/import record from the add data set modal

    We expect that the body of our request is JSON serialized data like:
    {
        "name": "2013 city compliance dataset"
    }

    """
    body = json.loads(request.body)
    org = Organization.objects.get(pk=body['organization_id'])
    record = ImportRecord.objects.create(
        name=body['name'],
        app="seed",
        start_time=datetime.datetime.now(),
        created_at=datetime.datetime.now(),
        last_modified_by=request.user,
        super_organization=org,
        owner=request.user,
    )

    return {
        'status': 'success',
        'id': record.pk,
        'name': record.name,
    }


@ajax_request
@login_required
def get_datasets(request):
    """returns an array of datasets for a user's organization
        importfiles = [
        {
            name: "DC_CoveredBuildings_50k.csv",
            number_of_buildings: 511,
            number_of_mappings: 511,
            number_of_cleanings: 1349,
            source_type: "AssessorRaw",
            number_of_matchings: 403,
            id: 1
        },
        {
            name: "DC_ESPM_Report.csv",
            number_of_buildings: 511,
            number_of_matchings: 403,
            source_type: "PMRaw",
            id: 2
        }
    ];
    datasets = [
        {
            name: "DC 2013 data",
            last_modified: (new Date()).getTime(),
            last_modified_by: "john.s@buildingenergy.com",
            number_of_buildings: 89,
            id: 1,
            importfiles: mock_importfiles
        },
        ...
    ];
    """
    from seed.models import obj_to_dict
    org = Organization.objects.get(pk=request.GET.get('organization_id'))
    datasets = []
    for d in ImportRecord.objects.filter(super_organization=org):
        importfiles = [obj_to_dict(f) for f in d.files]
        dataset = obj_to_dict(d)
        dataset['importfiles'] = importfiles
        if d.last_modified_by:
            dataset['last_modified_by'] = d.last_modified_by.email
        dataset['number_of_buildings'] = BuildingSnapshot.objects.filter(
            import_file__in=d.files,
            canonicalbuilding__active=True,
        ).count()
        dataset['updated_at'] = utils.convert_to_js_timestamp(d.updated_at)
        datasets.append(dataset)

    return {
        'status': 'success',
        'datasets': datasets,
    }


@ajax_request
@login_required
def get_dataset(request):
    """returns an array of import files for a data set
        The data set/import record id comes in as a GET param
        returns:
        importfiles = [
        {
            name: "DC_CoveredBuildings_50k.csv",
            number_of_buildings: 511,
            number_of_mappings: 511,
            number_of_cleanings: 1349,
            source_type: "AssessorRaw",
            number_of_matchings: 403,
            id: 1
        },
        {
            name: "DC_ESPM_Report.csv",
            number_of_buildings: 511,
            number_of_matchings: 403,
            source_type: "PMRaw",
            id: 2
        }
    ];
    """
    from seed.models import obj_to_dict
    dataset_id = request.GET.get('dataset_id', '')
    orgs = request.user.orgs.all()
    # check if user has access to the dataset
    d = ImportRecord.objects.filter(
        super_organization__in=orgs, pk=dataset_id
    )
    if d.exists():
        d = d[0]
    else:
        return {
            'status': 'success',
            'dataset': {},
        }

    dataset = obj_to_dict(d)
    importfiles = []
    for f in d.files:
        importfile = obj_to_dict(f)
        importfile['name'] = f.filename_only
        importfiles.append(importfile)

    dataset['importfiles'] = importfiles
    if d.last_modified_by:
        dataset['last_modified_by'] = d.last_modified_by.email
    dataset['number_of_buildings'] = BuildingSnapshot.objects.filter(
        import_file__in=d.files
    ).count()
    dataset['updated_at'] = utils.convert_to_js_timestamp(d.updated_at)

    return {
        'status': 'success',
        'dataset': dataset,
    }


@ajax_request
@login_required
def get_import_file(request):
    """returns an import file if the user has permission
        The data set/ImportRecord id comes in as the GET param `import_file_id`
        returns:
        {
            "name": "DC_CoveredBuildings_50k.csv",
            "number_of_buildings": 511,
            "number_of_mappings": 511,
            "number_of_cleanings": 1349,
            "source_type": "AssessorRaw",
            "number_of_matchings": 403,
            "id": 1,
            "dataset": {
                "name": "DC dataset"
                "id": 1,
                "importfiles": [
                    {
                        "name": "DC_CoveredBuildings_50k.csv",
                        "id": 1
                    },
                    {
                        "name": "DC_PM_report.csv",
                        "id": 2
                    }
                ]
            }
        }
    """
    from seed.models import obj_to_dict
    import_file_id = request.GET.get('import_file_id', '')
    orgs = request.user.orgs.all()
    import_file = ImportFile.objects.get(
        pk=import_file_id
    )
    d = ImportRecord.objects.filter(
        super_organization__in=orgs, pk=import_file.import_record_id
    )
    # check if user has access to the import file
    if not d.exists():
        return {
            'status': 'success',
            'import_file': {},
        }

    f = obj_to_dict(import_file)
    f['name'] = import_file.filename_only
    f['dataset'] = obj_to_dict(import_file.import_record)
    # add the importfiles for the matching select
    f['dataset']['importfiles'] = []
    files = f['dataset']['importfiles']
    for i in import_file.import_record.files:
        files.append({
            'name': i.filename_only,
            'id': i.pk
        })
    # make the first element in the list the current import file
    i = files.index({
        'name': import_file.filename_only,
        'id': import_file.pk
    })
    files[0], files[i] = files[i], files[0]

    return {
        'status': 'success',
        'import_file': f,
    }


@ajax_request
@login_required
@has_perm('can_modify_data')  # TODO(gavin) need special perm for deleting data
def delete_file(request):
    """deletes a file from a data set/import record
    """
    file_id = request.GET.get('file_id', '')
    orgs = request.user.orgs.all()
    import_file = ImportFile.objects.get(pk=file_id)
    d = ImportRecord.objects.filter(
        super_organization__in=orgs, pk=import_file.import_record.pk
    )
    # check if user has access to the dataset
    if not d.exists():
        return {
            'status': 'error',
            'message': 'user does not have permission to delete file',
        }

    import_file.delete()
    return {
        'status': 'success',
    }


@ajax_request
@login_required
@has_perm('can_modify_data')  # TODO(gavin) need special perm for deleting data
def delete_dataset(request):
    """deletes a file from a data set/import record
    """
    dataset_id = request.GET.get('dataset_id', '')
    orgs = request.user.orgs.all()
    # check if user has access to the dataset
    d = ImportRecord.objects.filter(
        super_organization__in=orgs, pk=dataset_id
    )
    if not d.exists():
        return {
            'status': 'error',
            'message': 'user does not have permission to delete dataset',
        }
    d = d[0]
    d.delete()
    return {
        'status': 'success',
    }


@ajax_request
@login_required
@has_perm('can_modify_data')
def update_dataset(request):
    """updates a dataset's name
    """
    body = json.loads(request.body)
    orgs = request.user.orgs.all()
    # check if user has access to the dataset
    d = ImportRecord.objects.filter(
        super_organization__in=orgs, pk=body['dataset']['id']
    )
    if not d.exists():
        return {
            'status': 'error',
            'message': 'user does not have permission to update dataset',
        }
    d = d[0]
    d.name = body['dataset']['name']
    d.save()
    return {
        'status': 'success',
    }


@ajax_request
@login_required
@has_perm('can_modify_data')
def save_raw_data(request):
    """Initiate a save or raw data to DB for a given ImportFile."""
    body = json.loads(request.body)
    import_file_id = body.get('file_id')
    if not import_file_id:
        return {'status': 'error'}

    return task_save_raw(import_file_id)


@ajax_request
@login_required
@has_perm('can_modify_data')
def start_mapping(request):
    """"Map raw data to mapped data."""
    body = json.loads(request.body)
    import_file_id = body.get('file_id')
    if not import_file_id:
        return {'status': 'error'}

    return map_data(import_file_id)


@ajax_request
@login_required
@has_perm('can_modify_data')
def remap_buildings(request):
    """Remap buildings as if it hadn't happened at all.

    Deletes mapped buildings for a given ImportRecord, resets status.

    NB: will not work if buildings have been merged into CanonicalBuilings.

    """
    body = json.loads(request.body)
    import_file_id = body.get('file_id')
    if not import_file_id:
        return {'status': 'error', 'message': 'Import File does not exist'}

    return remap_data(import_file_id)


@ajax_request
@login_required
@has_perm('can_modify_data')
def start_system_matching(request):
    """"Match data in this import file to existin canonical buildings."""
    body = json.loads(request.body)
    import_file_id = body.get('file_id')
    if not import_file_id:
        return {'status': 'error'}

    return match_buildings(import_file_id)


@ajax_request
@login_required
def progress(request):
    """Get the progress (percent complete) for a task."""

    progress_key = json.loads(request.body).get('progress_key')

    return {
        'progress_key': progress_key,
        'progress': cache.get(progress_key) or 0
    }


@ajax_request
@login_required
@has_perm('can_modify_data')
def update_building(request):
    """"updates a building from the building detail page"""
    body = json.loads(request.body)
    # Will be a dict representation of a hydrated building, incl pk.
    building = body.get('building')
    old_snapshot = BuildingSnapshot.objects.get(pk=building['pk'])

    models.update_building(old_snapshot, building, request.user)

    return {'status': 'success'}


@ajax_request
@login_required
@permission_required('seed.can_access_admin')
def delete_organization_buildings(request):
    """deletes all BuildingSnapshot isinstances from an org

    :returns: Dict. with keys ``status`` and ``progress_key``
    """
    org_id = request.GET.get('org_id', '')
    return tasks.delete_organization_buildings(org_id)
