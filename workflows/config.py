def require_value(config, key, workflow_name):
    if key not in config:
        raise ValueError(f"Missing required workflow config '{workflow_name}.{key}'")
    value = config[key]
    if value is None:
        raise ValueError(f"Missing required workflow config '{workflow_name}.{key}'")
    if value == "":
        raise ValueError(f"Missing required workflow config '{workflow_name}.{key}'")
    return value


def require_int(config, key, workflow_name):
    return int(require_value(config, key, workflow_name))


def require_mapping(config, key, workflow_name):
    value = require_value(config, key, workflow_name)
    if not isinstance(value, dict):
        raise ValueError(f"Workflow config '{workflow_name}.{key}' must be an object")
    return value


def require_list(config, key, workflow_name):
    value = require_value(config, key, workflow_name)
    if not isinstance(value, list) or not value:
        raise ValueError(f"Workflow config '{workflow_name}.{key}' must be a non-empty list")
    return value
