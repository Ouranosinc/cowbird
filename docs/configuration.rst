.. include:: references.rst

.. _configuration_page:

Configuration
=============

At startup, `Cowbird` application will load multiple configuration files to define various behaviours or setup
operations. These are defined though the configuration settings presented in below sections.

All generic `Cowbird` configuration settings can be defined through either the `cowbird.ini`_ file or environment
variables. Values defined in `cowbird.ini`_ are expected to follow the ``cowbird.[variable_name]`` format, and
corresponding ``COWBIRD_[VARIABLE_NAME]`` format is used for environment variables. Both of these alternatives match
the constants defined in `cowbird/constants.py`_ and can be used interchangeably.

.. _cowbird/constants.py: https://github.com/Ouranosinc/cowbird/tree/master/cowbird/constants.py


Configuration Files
-------------------

.. _ini_file:

File: cowbird.ini
~~~~~~~~~~~~~~~~~~~

This is the base configuration file that defines most of `Cowbird`'s lower level application configuration (API, CLI).
A basic `cowbird.example.ini`_ configuration is provided, which should allow any user to run the application locally.
It is recommended to create a copy of this file as `cowbird.ini`_ to customize settings to your linking
(this file is ignored for repository commits).

Furthermore, this file is used by default in each tagged `Docker`_ image, and mounted at
``${COWBIRD_CONFIG_DIR}/cowbird.ini`` location. If you want to provide different configuration, the file should be
overridden in the `Docker`_ image using a volume mount parameter, or by specifying an alternative path through the
environment variable ``COWBIRD_INI_FILE_PATH``.

.. _config_file:

File: config.yml
~~~~~~~~~~~~~~~~~~~

This is the core configuration file that defines most of `Cowbird`'s data configuration which it must work with to
manage :term:`services` components.
A basic `config.example.yml`_ file is provided, for sample definition of expected schemas per service.


Settings and Constants
----------------------

Environment variables can be used to define all following configurations (unless mentioned otherwise with
``[constant]`` keyword next to the parameter name). Most values are parsed as plain strings, unless they refer to an
activatable setting (e.g.: ``True`` or ``False``), or when specified with more specific ``[<type>]`` notation.

Configuration variables will be used by `Cowbird` on startup unless prior definition is found within `cowbird.ini`_.
All variables (i.e.: non-``[constant]`` parameters) can also be specified by their ``cowbird.[variable_name]`` setting
counterpart as described at the start of the `Configuration`_ section.

Loading Settings
~~~~~~~~~~~~~~~~~

These settings can be used to specify where to find other settings through custom configuration files.

- ``COWBIRD_MODULE_DIR`` [constant]

  Path to the top level :mod:`cowbird` module (ie: source code).

- ``COWBIRD_ROOT`` [constant]

  Path to the containing directory of `Cowbird`. This corresponds to the directory where the repository was cloned
  or where the package was installed.

- | ``COWBIRD_CONFIG_DIR``
  | (Default: ``${COWBIRD_ROOT}/config``)

  Configuration directory where to look for `cowbird.ini`_ and `config.yml`_ files.

- ``COWBIRD_CONFIG_PATH``

  Explicit path where to find a `config.yml`_ configuration file to load at `Cowbird` startup.

  .. note::
    When provided, ``COWBIRD_CONFIG_DIR`` is ignored in favour of definitions in this file.

  .. seealso::
    :ref:`config_file`

- ``COWBIRD_INI_FILE_PATH``

  Specifies where to find the initialization file to run `Cowbird` application.

  .. warning::
    This variable ignores the setting/env-var resolution order since settings cannot be defined without
    firstly loading the file referenced by its value.

  .. seealso::
    :ref:`ini_file`


Application Settings
~~~~~~~~~~~~~~~~~~~~~

Following configuration parameters are used to define values that are employed by `Cowbird` after loading
the `Loading Settings`_. All ``cowbird.[variable_name]`` counterpart definitions are also available as described
at the start of the `Configuration`_ section.

- | ``COWBIRD_URL``
  | (Default: ``"http://localhost:2001"``)

  Full hostname URL to use so that `Cowbird` can resolve his own running instance location.

  .. note::
    This value is notably useful to indicate the exposed proxy location where `Cowbird` should be invoked from
    within a server stack that integrates it.

- | ``COWBIRD_LOG_LEVEL``
  | (Default: ``INFO``)

  Logging level of operations. `Cowbird` will first use the complete logging configuration found in
  `cowbird.ini`_ in order to define logging formatters and handler referencing to the ``logger_cowbird`` section.
  If this configuration fail to retrieve an explicit logging level, this configuration variable is used instead to
  prepare a basic logger, after checking if a corresponding ``cowbird.log_level`` setting was instead specified.

  .. warning::
    When setting ``DEBUG`` level or lower, `Cowbird` could potentially dump some sensitive information in logs.
    It is important to avoid this setting for production systems.

- | ``COWBIRD_LOG_PRINT``
  | (Default: ``False``)

  Specifies whether `Cowbird` logging should also **enforce** printing the details to the console when using
  `utilities`_.
  Otherwise, the configured logging methodology in `cowbird.ini`_ is used (which can also define a console handler).

- | ``COWBIRD_LOG_REQUEST``
  | (Default: ``True``)

  Specifies whether `Cowbird` should log incoming request details.

  .. note::
    This can make `Cowbird` quite verbose if large quantity of requests are accomplished.

- | ``COWBIRD_LOG_EXCEPTION``
  | (Default: ``True``)

  Specifies whether `Cowbird` should log a raised exception during a process execution.
