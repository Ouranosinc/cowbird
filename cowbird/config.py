import logging
import os
import re
from typing import TYPE_CHECKING

import yaml
from schema import Optional, Schema

from cowbird.utils import get_logger, print_log, raise_log

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import List, Union

    from cowbird.typedefs import ConfigDict

LOGGER = get_logger(__name__)

SINGLE_TOKEN = "*"  # nosec: B105
MULTI_TOKEN = "**"  # nosec: B105

PERMISSION_REGEX = r"(?:\w+|\[\s*\w+(?:\s*,\s*\w+)*\s*\])"  # Either a single word, or a list of words in array
DIRECTION_REGEX = r"(<->|<-|->)"
# Mapping format
# <res_key1> : <permission(s)> <direction> <res_key2> : <permission(s)>
MAPPING_REGEX = r"(\w+)\s*:\s*" + PERMISSION_REGEX + r"\s*" + DIRECTION_REGEX + \
                r"\s*(\w+)\s*:\s*" + PERMISSION_REGEX
NAMED_TOKEN_REGEX = r"^\{\s*(\w+)\s*\}$"


class ConfigError(RuntimeError):
    """
    Generic error during configuration loading.
    """


class ConfigErrorInvalidTokens(ConfigError):
    """
    Config error specific to invalid SINGLE_TOKEN or MULTI_TOKEN tokens.
    """


class ConfigErrorInvalidResourceKey(ConfigError):
    """
    Config error for invalid resource keys.
    """


def _load_config(path_or_dict, section, allow_missing=False):
    # type: (Union[str, ConfigDict], str, bool) -> ConfigDict
    """
    Loads a file path or dictionary as YAML/JSON configuration.
    """
    try:
        if isinstance(path_or_dict, str):
            with open(path_or_dict, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
        else:
            cfg = path_or_dict
        return _expand_all(cfg[section])
    except KeyError:
        msg = f"Config file section [{section!s}] not found."
        if allow_missing:
            print_log(msg, level=logging.WARNING, logger=LOGGER)
            return {}
        raise_log(msg, exception=ConfigError, logger=LOGGER)
    except Exception as exc:
        raise_log(f"Invalid config file [{exc!r}]",
                  exception=ConfigError, logger=LOGGER)


def get_all_configs(path_or_dict, section, allow_missing=False):
    # type: (Union[str, ConfigDict], str, bool) -> List[ConfigDict]
    """
    Loads all configuration files specified by the path (if a directory),
    a single configuration (if a file) or directly
    returns the specified dictionary section (if a configuration dictionary).
    :returns:
        - list of configurations loaded if input was a directory path
        - list of single configuration if input was a file path
        - list of single configuration if input was a JSON dict
        - empty list if none of the other cases where matched
    .. note::
        Order of file loading will be resolved by alphabetically sorted filename
        if specifying a directory path.
    """
    if isinstance(path_or_dict, str):
        if os.path.isdir(path_or_dict):
            dir_path = os.path.abspath(path_or_dict)
            known_extensions = [".cfg", ".yml", ".yaml", ".json"]
            cfg_names = list(sorted({fn for fn in os.listdir(dir_path)
                                     if any(fn.endswith(ext) for ext in
                                            known_extensions)}))
            return [_load_config(os.path.join(dir_path, fn),
                                 section,
                                 allow_missing) for fn in cfg_names]
        if os.path.isfile(path_or_dict):
            return [_load_config(path_or_dict, section, allow_missing)]
    elif isinstance(path_or_dict, dict):
        return [_load_config(path_or_dict, section, allow_missing)]
    return []


def _expand_all(config):
    # type: (ConfigDict) -> ConfigDict
    """
    Applies environment variable expansion recursively to all applicable fields of a configuration definition.
    """
    if isinstance(config, dict):
        for cfg in list(config):
            cfg_key = os.path.expandvars(cfg)
            if cfg_key != cfg:
                config[cfg_key] = config.pop(cfg)
            config[cfg_key] = _expand_all(config[cfg_key])
    elif isinstance(config, (list, set)):
        for i, cfg in enumerate(config):
            config[i] = _expand_all(cfg)
    elif isinstance(config, str):
        config = os.path.expandvars(str(config))
    elif isinstance(config, (int, bool, float, type(None))):
        pass
    else:
        raise NotImplementedError(f"unknown parsing of config of type: {type(config)}")
    return config


def validate_services_config_schema(services_cfg):
    """
    Validates the schema of the `services` section found in the config.
    """
    schema = Schema({
        str: {
            Optional("active"): bool,
            Optional("priority"): int,
            Optional("url"): str,
            Optional("workspace_dir"): str,
        }
    }, ignore_extra_keys=True)
    schema.validate(services_cfg)


def validate_sync_perm_config_schema(sync_cfg):
    """
    Validates the schema of the `sync_permissions` section found in the config.
    """
    schema = Schema({
        Optional(str): {
            "services": {
                str: {
                    str: [
                        {"name": str, "type": str}
                    ]
                }
            },
            "permissions_mapping": [str]
        }
    })
    schema.validate(sync_cfg)


def validate_and_get_resource_info(res_key, segments):
    # type: (str, List[dict[str, str]]) -> dict[str, Union[bool, set]]
    """
    Validates a resource_key and its related info from the config
    and returns the following info, relevant to the config mapping validation :
    - if the resource uses a MULTI_TOKEN in its resource_path
    - the list of named tokens found in the resource_path
    """
    named_tokens = set()
    has_multi_token = False
    for seg in segments:
        if seg["name"] == MULTI_TOKEN:
            if has_multi_token:
                raise ConfigErrorInvalidTokens(f"Invalid config value for resource key {res_key}. Only one "
                                               f"`{MULTI_TOKEN}` token is permitted per resource.")
            has_multi_token = True
        else:
            matched_groups = re.match(NAMED_TOKEN_REGEX, seg["name"])
            if matched_groups:
                # Save the first group as a named token, since there's only 1 matching group in the regex.
                if matched_groups.groups()[0] in named_tokens:
                    raise ConfigErrorInvalidTokens(f"Invalid config value for resource key {res_key}. Named token "
                                                   f"{matched_groups.groups()[0]} was found in multiple segments of "
                                                   "the resource path. Each named token should only be used once in a "
                                                   "resource path.")
                named_tokens.add(matched_groups.groups()[0])

    return {"has_multi_token": has_multi_token, "named_tokens": named_tokens}


def validate_bidirectional_mapping(mapping, res_info, res_key1, res_key2):
    # type: (str, dict[str, dict[str, Union[bool, set]]], str, str) -> None
    """
    Validates if both resources of a bidirectional mapping respect validation rules.
    Both should either use MULTI_TOKEN or not use it and both should use exactly the same named tokens.
    """
    if res_info[res_key1]["has_multi_token"] != res_info[res_key2]["has_multi_token"]:
        raise ConfigErrorInvalidTokens(f"Invalid permission mapping `{mapping}`. For a bidirectional mapping, "
                                       f"either all mapped resources should have `{MULTI_TOKEN}` "
                                       "or none should use them.")
    if res_info[res_key1]["named_tokens"] != res_info[res_key2]["named_tokens"]:
        raise ConfigErrorInvalidTokens(f"Invalid permission mapping `{mapping}`. For a bidirectional mapping, "
                                       "both resources should have exactly the same named_tokens. "
                                       f"({res_key1}: {res_info[res_key1]['named_tokens']}, "
                                       f"{res_key2}: {res_info[res_key2]['named_tokens']})")


def validate_unidirectional_mapping(mapping, src_info, tgt_info):
    # type: (str, dict[str, Union[bool, set]], dict[str, Union[bool, set]]) -> None
    """
    Validates if both source and target resource of a unidirectional mapping respect validation rules.
    Source resource should use MULTI_TOKEN if target uses it, and source resource should include all named tokens found
    in the target resource.
    """
    if not src_info["has_multi_token"] and tgt_info["has_multi_token"]:
        raise ConfigErrorInvalidTokens(f"Invalid permission mapping `{mapping}`. For a unidirectional mapping, "
                                       "the source resource should use a MULTI_TOKEN "
                                       "if the target is using one.")
    missing_named_tokens = tgt_info["named_tokens"] - src_info["named_tokens"]
    if missing_named_tokens:
        raise ConfigErrorInvalidTokens(f"Invalid permission mapping `{mapping}`. For a unidirectional mapping, "
                                       "all named tokens found in the target resource should also be found in "
                                       f"the source resource, but the tokens `{missing_named_tokens}` are "
                                       f"missing from the source.")


def validate_sync_mapping_config(sync_cfg, res_info):
    # type: (ConfigDict, dict[str, dict[str, Union[bool, set]]]) -> None
    """
    Validates if mappings in the config have valid resource keys and use tokens properly.
    """

    for mapping in sync_cfg["permissions_mapping"]:
        matched_groups = re.match(MAPPING_REGEX, mapping)
        if not matched_groups or len(matched_groups.groups()) != 3:
            raise ConfigError(f"Error parsing mapping `{mapping}`. "
                              "Couldn't find both resource keys and the direction token because of invalid format.")
        res_key1, direction, res_key2 = matched_groups.groups()

        for res_key in [res_key1, res_key2]:
            if res_key not in res_info:
                raise ConfigErrorInvalidResourceKey(f"Invalid config mapping references resource {res_key} which is "
                                                    "not defined in any service.")

        if direction == "<->":
            validate_bidirectional_mapping(mapping, res_info, res_key1, res_key2)
        else:
            if direction == "->":
                validate_unidirectional_mapping(mapping, src_info=res_info[res_key1], tgt_info=res_info[res_key2])
            else:
                validate_unidirectional_mapping(mapping, src_info=res_info[res_key2], tgt_info=res_info[res_key1])


def validate_sync_config(sync_cfg):
    # type: (ConfigDict) -> None

    # validate and get all resources info
    res_info = {}
    for svc, resources in sync_cfg["services"].items():
        for res_key in resources:
            if res_key in res_info:
                raise ConfigErrorInvalidResourceKey(f"Found duplicate resource key {res_key} in config. Config resource"
                                                    " keys should be unique even between different services.")
            res_info[res_key] = validate_and_get_resource_info(res_key, resources[res_key])

    validate_sync_mapping_config(sync_cfg, res_info)
