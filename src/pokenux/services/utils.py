from dataclasses import fields


def filter_valid_fields(data: dict, model_class) -> dict:
    """
    Filters the input data dictionary to only include keys that are valid fields of the given model class.

    Args:
        data (dict): The input data dictionary to filter.
        model_class: The dataclass model class to check against.

    Returns:
        dict: A new dictionary containing only the valid fields.
    """
    valid_fields = {f.name for f in fields(model_class)}
    return {k: v for k, v in data.items() if k in valid_fields}
