import copy
import datetime

from seed import models
from seed.models import ASSESSED_RAW, BuildingSnapshot
from seed import search
from seed.utils import constants
from seed.utils import time


def get_source_type(import_file, source_type=''):
    """Used for converting ImportFile source_type into an int."""
    source_type_str = getattr(import_file, 'source_type', '') or ''
    source_type_str = source_type or source_type_str
    source_type_str = source_type_str.upper().replace(' ', '_')

    return getattr(models, source_type_str, ASSESSED_RAW)


def serialize_building_snapshot(b, pm_cb, building):
    """returns a dict that's safe to JSON serialize"""
    b_as_dict = b.__dict__.copy()
    for key, val in b_as_dict.items():
        if type(val) == datetime.datetime or type(val) == datetime.date:
            b_as_dict[key] = time.convert_to_js_timestamp(val)
    del(b_as_dict['_state'])
    # check if they're matched
    if b.canonical_building == pm_cb:
        b_as_dict['matched'] = True
    else:
        b_as_dict['matched'] = False
    if '_canonical_building_cache' in b_as_dict:
        del(b_as_dict['_canonical_building_cache'])
    return b_as_dict


def get_buildings_for_user(user):
    building_snapshots = BuildingSnapshot.objects.filter(
        super_organization__in=user.orgs.all()
    )

    buildings = []
    for b in building_snapshots[:10]:
        b_temp = copy.copy(b.__dict__)
        del(b_temp['_state'])
        buildings.append(b_temp)

    return buildings


def get_buildings_for_user_count(user):
    """returns the number of buildings in a user's orgs"""
    building_snapshots = BuildingSnapshot.objects.filter(
        super_organization__in=user.orgs.all(),
        canonicalbuilding__active=True,
    ).distinct('pk')

    return building_snapshots.count()


def get_search_query(user, params):
    other_search_params = params.get('filter_params', {})
    q = other_search_params.get('q', '')
    order_by = params.get('order_by', 'pk')
    sort_reverse = params.get('sort_reverse', False)

    if order_by:
        if sort_reverse:
            order_by = "-%s" % order_by
        building_snapshots = BuildingSnapshot.objects.order_by(
            order_by
        ).filter(
            super_organization__in=user.orgs.all(),
            canonicalbuilding__active=True,
        )
    else:
        building_snapshots = BuildingSnapshot.objects.filter(
            super_organization__in=user.orgs.all(),
            canonicalbuilding__active=True,
        )

    buildings_queryset = search.search_buildings(
        q, queryset=building_snapshots)
    buildings_queryset = search.filter_other_params(
        buildings_queryset, other_search_params)

    return buildings_queryset


def get_columns(is_project):
    """gets default columns, to be overriden in future

        title: HTML presented title of column
        sort_column: semantic name used by js and for searching DB
        class: HTML CSS class for row td elements
        title_class: HTML CSS class for column td elements
        type: 'string' or 'number', if number will get min and max input fields
        min, max: the django filter key e.g. gross_floor_area__gte
        field_type: assessor, pm, or compliance (currently not used)
        sortable: determines if the column is sortable
        checked: initial state of "edit columns" modal
        static: True if option can be toggle (ID is false because it is
            always needed to link to the building detail page)
        link: signifies that the cell's data should link to a building detail
            page

    """

    assessor_fields = constants.ASSESSOR_FIELDS[:]

    if is_project:
        assessor_fields.insert(1, {
            "title": "Status",
            "sort_column": "project_building_snapshots__status_label__name",
            "class": "",
            "title_class": "",
            "type": "string",
            "field_type": "assessor",
            "sortable": True,
            "checked": True,
            "static": True
        })
    columns = {
        'fields': assessor_fields,
    }

    return columns
