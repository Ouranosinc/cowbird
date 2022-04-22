import logging
import os
from typing import TYPE_CHECKING

import yaml

from cowbird.utils import get_logger, print_log, raise_log

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import List, Union

    from cowbird.typedefs import ConfigDict

LOGGER = get_logger(__name__)

SINGLE_TOKEN = "*"  # nosec: B105
MULTI_TOKEN = "**"  # nosec: B105


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


def validate_sync_services_config(sync_cfg):
    # type: (ConfigDict) -> None
    """
    Validates if services in the config have valid resource keys and use tokens properly.
    """
    res_key_list = []
    for svc, resources in sync_cfg["services"].items():
        for res_key, segments in resources.items():
            if res_key not in res_key_list:
                res_key_list.append(res_key)
            else:
                raise ConfigErrorInvalidResourceKey(f"Found duplicate resource key {res_key} in config. Config resource"
                                                    " keys should be unique even between different services.")
            has_multi_token = False
            for i in range(len(segments)):  # pylint: disable=consider-using-enumerate
                if segments[i]["name"] in [SINGLE_TOKEN, MULTI_TOKEN]:
                    while i < len(segments):
                        if segments[i]["name"] == MULTI_TOKEN:
                            if has_multi_token:
                                raise ConfigErrorInvalidTokens(f"Invalid config value for resource key {res_key} "
                                                               f"from service {svc}. Only one `{MULTI_TOKEN}` token is "
                                                               "permitted per resource.")
                            has_multi_token = True
                        elif segments[i]["name"] != SINGLE_TOKEN:
                            raise ConfigErrorInvalidTokens(f"Invalid config value. After a first `{MULTI_TOKEN}` or "
                                                           f"`{SINGLE_TOKEN}` value is found in the resource path, only"
                                                           " token values should follow but the name "
                                                           f"{segments[i]['name']} was found instead.")
                        i += 1


def validate_sync_mapping_config(sync_cfg):
    # type: (ConfigDict) -> None
    """
    Validates if mappings in the config have valid resource keys and use tokens properly.
    """

    def has_tokens(segment):
        return segment["name"] in [MULTI_TOKEN, SINGLE_TOKEN]

    for mapping in sync_cfg["permissions_mapping"]:
        res_with_tokens = []
        for res_key in mapping:
            res_segments = []
            for res_dict in sync_cfg["services"].values():
                res_segments = res_dict.get(res_key, [])
                if res_segments:
                    break
            if not res_segments:
                raise ConfigErrorInvalidResourceKey(f"Invalid config mapping references resource {res_key} which is "
                                                    "not defined in any service.")
            if any(has_tokens(seg) for seg in res_segments):
                res_with_tokens.append(res_key)
        if res_with_tokens and len(res_with_tokens) != len(mapping):
            raise ConfigErrorInvalidTokens(f"Invalid permission mapping using resources {mapping.keys()}. "
                                           f"Either all mapped resources should have `{MULTI_TOKEN}` or "
                                           f"`{SINGLE_TOKEN}` tokens or none should use them.")


def validate_sync_config(sync_cfg):
    # type: (ConfigDict) -> None
    validate_sync_services_config(sync_cfg)
    validate_sync_mapping_config(sync_cfg)
