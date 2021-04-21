import logging
import os
from typing import TYPE_CHECKING

import six
import yaml

from cowbird.utils import get_logger, print_log, raise_log

if TYPE_CHECKING:
    # pylint: disable=W0611,unused-import
    from typing import List, Union

    from cowbird.typedefs import ConfigDict, Str

LOGGER = get_logger(__name__)


class ConfigError(RuntimeError):
    """
    Generic error during configuration loading.
    """


def _load_config(path_or_dict, section, allow_missing=False):
    # type: (Union[Str, ConfigDict], Str, bool) -> ConfigDict
    """
    Loads a file path or dictionary as YAML/JSON configuration.
    """
    try:
        if isinstance(path_or_dict, str):
            cfg = yaml.safe_load(open(path_or_dict, "r"))
        else:
            cfg = path_or_dict
        return _expand_all(cfg[section])
    except KeyError:
        msg = "Config file section [{!s}] not found.".format(section)
        if allow_missing:
            print_log(msg, level=logging.WARNING, logger=LOGGER)
            return {}
        raise_log(msg, exception=ConfigError, logger=LOGGER)
    except Exception as exc:
        raise_log("Invalid config file [{!r}]".format(exc),
                  exception=ConfigError, logger=LOGGER)


def get_all_configs(path_or_dict, section, allow_missing=False):
    # type: (Union[Str, ConfigDict], Str, bool) -> List[ConfigDict]
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
        raise NotImplementedError("unknown parsing of config of type: {}".
                                  format(type(config)))
    return config
