.. include:: references.rst

.. _configuration:
.. _configuration_page:

Configuration
=============

At startup, `Cowbird` application will load multiple configuration files to define various behaviours or setup
operations. These are defined through the configuration settings presented in sections below.

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
manage :term:`Handler` components.
A basic `config.example.yml`_ file is provided, for sample definition of expected schemas per handler.

This config file contains the following required sections :

handlers:
#########

The ``handlers`` section contains the definition of managed handlers by Cowbird.
Each handler is provided as a string that must match an actual implementation in Cowbird.
Each handler must be further configured with one or more of the following parameters. If
a required parameter is missing for a handler it will throw a ``HandlerConfigurationException`` exception.
Additional parameters can be used for some handlers, such as ``admin_user`` and ``admin_password`` for a `Magpie`_
handler.
See also the :ref:`components_handlers` section for more details on individual handlers.

Parameters :

=================  =============  ======================================================================================
Parameter name     Default value  Description
=================  =============  ======================================================================================
``active``         ``False``      Bool allowing to deactivate a handler and stop managing it.
``priority``       ``math.inf``   Relative priority between handlers while handling events.
                                  Lower values have higher priority, default value is last.
``url``            ``None``       URI of the web service represented by this Cowbird handler.
                                  Some Cowbird handlers do not represent web services, but others will throw an
                                  exception if missing.
``workspace_dir``  ``None``       Location of the users workspace root.
                                  Required for the following handlers : ``FileSystem``, ``Catalog`` and ``Geoserver``.
=================  =============  ======================================================================================

Example :

.. code-block:: yaml

    handlers:
      Magpie:
        active: true
        url: https://${HOSTNAME}/magpie
        admin_user: ${MAGPIE_ADMIN_USER}
        admin_password: ${MAGPIE_ADMIN_PASSWORD}
      FileSystem:
        active: true
        priority: 1
        workspace_dir: ${WORKSPACE_DIR}
        jupyterhub_user_data_dir: ${JUPYTERHUB_USER_DATA_DIR}
        wps_outputs_dir: ${WPS_OUTPUTS_DIR}
        secure_data_proxy_name: ${SECURE_DATA_PROXY_NAME}
        public_workspace_wps_outputs_subpath: ${PUBLIC_WORKSPACE_WPS_OUTPUTS_SUBPATH}

sync_permissions:
#################

This section defines how to synchronize permissions between services when they share resources.
This is used only for the synchronization of permissions between `Magpie`_ services/resources.
The ``sync_permissions`` are defined first by a list of `Magpie`_ services and their associated resources,
defined in the :ref:`sync_permissions_services` section below.
The mappings defining how the resources should be synchronized are described in
the other section :ref:`permissions_mapping`.

.. _sync_permissions_services:

services
________

This section contains the different resources that can be synchronized, ordered by service type. The service types
found in this section of the config should also exist in `Magpie`_.

.. seealso::

    For more details on available service types on `Magpie`_, refer to these pages :

    - `Magpie available services <https://pavics-magpie.readthedocs.io/en/latest/services.html#available-services>`_
    - `Magpie services API <https://pavics-magpie.readthedocs.io/en/latest/autoapi/magpie/services/index.html>`_

Each service type defines a list of resource keys, which are custom names that define a resource path.
They should correspond to the names used in the :ref:`permissions_mapping` section below.
Each resource path contains the list of its segments, with their corresponding name and type.

.. py:currentmodule:: cowbird.config

The name of a segment can either be a string name, a variable or a :data:`MULTI_TOKEN` (``**``).

Variables are indicated by a name written between braces (ex.: ``{variable_name}``) and represent a single
segment name. A variable can be reused across different resource paths if they have
a matching segment name. A resource path can use any number of different variables, but
each variable can only be used one time per resource path.
They are useful to indicate the corresponding location of the resource segment in a mapped permission.
Note that all variables found in a target resource path should also be included in the source resource path.

:data:`MULTI_TOKEN` represent any number (0 or more) of names that fit with the corresponding type.
Also, the :data:`MULTI_TOKEN` can only be used one time in each list of path segments. This is to avoid ambiguous
cases that would result with using multiple :data:`MULTI_TOKEN`, since multiple ways of matching the resource path
would then be possible. For example with a tokenized path ``**/**`` and an input resource ``seg1/seg2/seg3``,
multiple choices of matching are possible.
We could match ``seg1/seg2`` with the first token, and ``seg3`` with the second token,
we could also match ``seg1`` with the first token, and ``seg2/seg3`` with the second token, etc.

The variables and tokens are useful to know the type of any segments that doesn't have a fixed name.

.. _permissions_mapping:

permissions_mapping
___________________

This section defines an array of permissions mapping between services.
Each item found in the ``permissions_mapping`` uses the following format :

.. code-block:: yaml

    "resource_key1 : <permissions1> <mapping> resource_key2 : <permissions2>"

The resource keys should correspond to resource keys defined in the :ref:`sync_permissions_services` section above.

``<permissionsX>`` is defined as a single permission or a list of permissions :

.. code-block:: yaml

    permission | [permission1, permission2, ...]

``<mapping>`` is defined as a unidirectional or bidirectional arrow :

.. code-block:: yaml

    -> | <- | <->

Each of the permissions can either use an implicit format (``<name>`` or ``<name>-match``)
or an explicit format (``<name>-<access>-<scope>``).
When using an implicit format, if the access and/or scope are not specified, it will use the default
access ``allow`` and/or the default scope ``recursive``.

.. seealso::

    For more info on `Magpie`_ permissions :

    - `Permission definition and modifiers <https://pavics-magpie.readthedocs.io/en/latest/permissions.html#permission-definition-and-modifiers>`_
    - `Permissions representation <https://pavics-magpie.readthedocs.io/en/latest/permissions.html#permissions-representation>`_

The arrows between the 2 resources indicate the direction of the synchronization, and which resources can be a
source or target resource.

In the case of the ``<->`` arrow, the synchronization of permissions can be done in either direction. Also, it is
important to note that, in this case, both mapped resources should have matching variable names if any. This means
each resource needs to match all the variables of the other mapped resource. Also, if one of the resource uses
the :data:`MULTI_TOKEN`, the other resource should also include it in its path, to know how to match the segments.

In the case of the ``->`` or ``<-`` arrow, the synchronization is only done one way. In this case, the source resource
path should include every variable names found in the target resource, but it can have more variables that
just won't be used in the target path. Also, if the target resource uses the :data:`MULTI_TOKEN`, the source
resource should have one too. The source can also use the ``**`` token even if the target doesn't include one.

In the case of a ``deleted`` webhook event, note that the related target permissions only get removed if
they are not in another sync mapping as a target where the source permission still exists.
Deleting the target permission would break that other sync mapping, having an existing source permission
but a deleted target permission.
Instead, a target permission only gets deleted when all related source permissions are also deleted.
For example, with the following mappings :

.. code-block:: yaml

    A -> C
    B -> C

    or
    [A,B] -> C

If the ``A -> C`` mapping was triggered for a ``deleted`` webhook event on ``A``, the ``C`` target permission
should only be deleted if both ``A`` and ``B`` permissions don't exist.
Else, the ``B -> C`` mapping would become invalid if ``B`` exists and ``C`` was deleted.


Settings and Constants
----------------------

Environment variables can be used to define all following configurations (unless mentioned otherwise with
``[constant]`` keyword next to the parameter name). Most values are parsed as plain strings, unless they refer to an
activable setting (e.g.: ``True`` or ``False``), or when specified with more specific ``[<type>]`` notation.

Configuration variables will be used by `Cowbird` on startup unless prior definition is found within `cowbird.ini`_.
All variables (i.e.: non-``[constant]`` parameters) can also be specified by their ``cowbird.[variable_name]`` setting
counterpart as described at the start of the :ref:`configuration` section.

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

  Configuration directory where to look for `cowbird.ini`_ file.

- ``COWBIRD_CONFIG_PATH`` [**required**]

  Explicit path where to find a `config.yml`_ configuration file to load at `Cowbird` startup.

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
at the start of the :ref:`configuration` section.

- | ``COWBIRD_URL``
  | (Default: ``"http://localhost:2001"``)

  Full hostname URL to use so that `Cowbird` can resolve his own running instance location.

  .. note::
    This value is notably useful to indicate the exposed proxy location where `Cowbird` should be invoked from
    within a server stack that integrates it.

- | ``COWBIRD_SSL_VERIFY``
  | (Default: ``true``)

  Specify if requests should enable SSL verification (*recommended*, should be disabled only for testing purposes).

- | ``COWBIRD_REQUEST_TIMEOUT``
  | (Default: ``5``, in seconds)

  Specify the connection timeout to be used when sending requests.

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
  :ref:`utilities`.
  Otherwise, the configured logging methodology in `cowbird.ini`_ is used (which can also define a console handler).

- | ``COWBIRD_LOG_REQUEST``
  | (Default: ``True``)

  Specifies whether `Cowbird` should log incoming request details.

  .. note::
    This can make `Cowbird` quite verbose if large quantity of requests are accomplished.

- | ``COWBIRD_LOG_EXCEPTION``
  | (Default: ``True``)

  Specifies whether `Cowbird` should log a raised exception during a process execution.
