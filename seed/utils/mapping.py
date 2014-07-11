from seed.models import BuildingSnapshot
from seed.utils import constants


def get_mappable_columns(exclude_fields=None):
    """Get a list of all the columns we're able to map to."""
    return get_mappable_types(exclude_fields).keys()


def get_mappable_types(exclude_fields=None):
    """Like get_mappable_columns, but with type information."""
    if not exclude_fields:
        exclude_fields = constants.EXCLUDE_FIELDS

    results = {}
    for f in BuildingSnapshot._meta.fields:
        if f.name not in exclude_fields and '_source' not in f.name:
            results[f.name] = f.get_internal_type()

    # Normalize the types for when we communicate with JS.
    for field in results:
        results[field] = results[field].lower().replace(
            'field', ''
        ).replace(
            'integer', 'float'
        ).replace(
            'time', ''
        ).replace(
            'text', ''
        ).replace(
            'char', ''
        )

    return results
