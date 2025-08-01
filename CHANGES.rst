.. explicit references must be used in this file (not references.rst) to ensure they are directly rendered on Github
.. :changelog:

Changes
*******

`Unreleased <https://github.com/Ouranosinc/cowbird/tree/master>`_ (latest)
------------------------------------------------------------------------------------

* Nothing yet.

`2.5.2 <https://github.com/Ouranosinc/cowbird/tree/2.5.2>`_ (2025-07-17)
------------------------------------------------------------------------------------

* Security update of dependencies.

`2.5.1 <https://github.com/Ouranosinc/cowbird/tree/2.5.1>`_ (2025-05-06)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Pin ``setuptools>78.1.1`` to fix flagged security issues.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`2.5.0 <https://github.com/Ouranosinc/cowbird/tree/2.5.0>`_ (2024-12-18)
------------------------------------------------------------------------------------

* Drop Python 3.8 support.
* Pin ``watchdog>=5`` to employ typing fixes.
* Pin ``requests>=2.32.3`` to fix security vulnerability.
* Pin ``setuptools>=70.0.0`` to fix security vulnerability.
* Do not treat handlers actions that have not been implemented as a dispatch failure.

`2.4.0 <https://github.com/Ouranosinc/cowbird/tree/2.4.0>`_ (2024-07-09)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Pin ``crim-ca/pyramid_celery==5.0.0a`` fork
  (`crim-ca/pyramid_celery@5.0.0a <https://github.com/crim-ca/pyramid_celery/tree/5.0.0a>`_)
  to support Python 3.12 and other package cross-dependency improvements
  (relates to `sontek/pyramid_celery#102 <https://github.com/sontek/pyramid_celery/pull/102>`_).
* Pin ``threddsclient==0.4.6`` to support Python 3.12
  (relates to `bird-house/threddsclient#17 <https://github.com/bird-house/threddsclient/pull/17>`_).
* Pin ``urllib3>=2.2.2`` to address CVE-2024-37891.
* Pin ``gunicorn>=22`` to address CVE-2024-1135.
* Pin Docker base to ``python:3.12.3-alpine`` for various security fixes.
* Update ``magpie==4.0.0`` for corresponding fixes
  (see `Changes: magpie @ 4.0.0 <https://github.com/Ouranosinc/Magpie/blob/master/CHANGES.rst#400-2024-04-26>`_).
* Pin ``watchdog>=4`` for latest typing additions.

`2.3.0 <https://github.com/Ouranosinc/cowbird/tree/2.3.0>`_ (2023-11-30)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Add optional key ``field`` and ``regex`` to be used in the ``sync_permissions`` section found in the config.
  This allows to sync permissions using a field other than ``resource_full_name`` when creating the ``name:type``
  from the segment ``ex.: /field1::type1/field2::type2``. Adds support to use ``resource_display_name``.
* The ``regex`` is used to extract the desired information from the ``nametype_path``. It should be used to do an
  exact match. This new search overrides the default way of matching each segment with the ``nametype_path``.
  In the case where a ``regex`` is found in the target segment, the data will be formed using the same ``resource_type``
  for every match in the same segment. Similarly, as using ``- name: "**"`` in the config to match multiple segment,
  it is possible to use a ``regex`` to match multiple resources in the same segment with ``regex: '(?<=:).*\/?(?=\/)'``

`2.2.0 <https://github.com/Ouranosinc/cowbird/tree/2.2.0>`_ (2023-11-16)
------------------------------------------------------------------------------------

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* The ``FileSystem`` handler now creates the WPS outputs data folder if it doesn't exist so that monitoring is setup
  properly.
* User permissions are set explicitly after creating his datastore folder to make sure the user can create and modify
  files in it.

`2.1.0 <https://github.com/Ouranosinc/cowbird/tree/2.1.0>`_ (2023-09-18)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Add monitoring to the ``FileSystem`` handler to watch WPS outputs data.
* Synchronize both public and user WPS outputs data to the workspace folder with hardlinks for user access.
* Add resync endpoint ``/handlers/{handler_name}/resync`` to trigger a handler's resync operations. Only the
  ``FileSystem`` handler is implemented for now, regenerating hardlinks associated to WPS outputs public data.

`2.0.0 <https://github.com/Ouranosinc/cowbird/tree/2.0.0>`_ (2023-07-21)
------------------------------------------------------------------------------------

* Update Docker image to use ``python:3.10-alpine`` instead of ``python:3.7-alpine`` for
  latest security updates and performance improvements.
* Update GitHub CI tests to include Python 3.9, 3.10 and 3.11, and use 3.10 by default for additional checks.
* Update multiple package dependencies flagged by PyUp as well as any relevant code changes to support updated packages.
* Move ``ports`` sections of example ``docker/docker-compose.*.yml`` files to the ``dev`` variant to reflect a realistic
  ``prod`` vs ``dev`` configuration scheme and allow ``ports`` overrides without merge of lists to avoid conflicts.
* Add typing requirements and ``check-types[-only]`` targets to ``Makefile``.
  To avoid breaking the CI on any minor typing issue, leave it as ``allow_failure: true`` for the moment.
  Further typing conversions and fixes can be applied gradually on a best-effort basis.
* Covert type comments to type annotations.
* Fix and improve ``Geoserver`` typings.
* Drop Python 3.7 that reached end-of-life.

`1.2.0 <https://github.com/Ouranosinc/cowbird/tree/1.2.0>`_ (2023-07-10)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Add permission synchronization between Magpie's permissions and Geoserver files permissions.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Fix bug where the monitors saved on the database and the internal monitors dictionary from the ``Monitoring`` class
  would be desynchronized, not always having the expected monitors, or having monitors that were not started properly.
* Fix failing permissions synchronizer by adding ``service_type`` to the Magpie webhooks and ignoring permissions from
  resources not defined in the config (relates to
  `Ouranosinc/Magpie#582 <https://github.com/Ouranosinc/Magpie/pull/582>`_).

`1.1.1 <https://github.com/Ouranosinc/cowbird/tree/1.1.1>`_ (2023-03-24)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Return `HTTP 424 (Failed Dependency)` when the ``celery`` worker version cannot be retrieved on ``GET /version``.
  Also, provide better error logs and detail messages in case of error to help debug the cause of the problem.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Fix incorrect typings and typographic errors.

`1.1.0 <https://github.com/Ouranosinc/cowbird/tree/1.1.0>`_ (2023-03-14)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Enforce specification of ``COWBIRD_CONFIG_PATH`` environment variable or ``cowbird.config_path`` INI configuration
  to provide the ``cowbird.yml`` file with definitions of services and permissions to manage, and raise directly at
  application startup otherwise. Without those definitions, `Cowbird` has no reason to exist.
* Add logging details when ``handlers`` are processed, succeed and failed their operation to provide insights
  about `Cowbird` integration with other services.
* Add ``COWBIRD_REQUEST_TIMEOUT`` environment variable and ``cowbird.request_timeout`` INI configuration parameters
  for specifying the connection timeout (default: ``5s``) to be applied when sending requests.
* Add missing ``COWBIRD_SSL_VERIFY`` configuration setting in documentation.
* Review ``FileSystem``'s handler for user workspace creation/deletion and to ensure compatibility with
  `birdhouse-deploy <https://github.com/bird-house/birdhouse-deploy>`_'s setup.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Add ``timeout`` to all request calls (``pylint`` recommended fix to avoid infinite lock).
* Minor typing fixes.

`1.0.0 <https://github.com/Ouranosinc/cowbird/tree/1.0.0>`_ (2022-08-18)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Renamed Cowbird ``services`` term to ``handlers``, to avoid confusion with Magpie services.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`0.5.0 <https://github.com/Ouranosinc/cowbird/tree/0.5.0>`_ (2022-08-15)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Add synchronization of Magpie permissions between different Magpie services, when receiving incoming webhooks.
* Update config's ``services`` sections under ``sync_permissions`` to use actual Magpie service names instead of
  Cowbird handler names (relates to `#22 <https://github.com/Ouranosinc/cowbird/issues/22>`_).
* Reorganize ``config.example.yml`` to support more sync cases, provide info on the type of each segment of a resource
  path and to use tokenized path.
* Add schema validation when starting cowbird app.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`0.4.1 <https://github.com/Ouranosinc/cowbird/tree/0.4.1>`_ (2022-03-09)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Add an SSL verification setting.
* Add Geoserver workspace and datastore creation/removal linked to user creation/removal.
* Add automated publishing of shapefiles to Geoserver when new files are found.
* Use ``pip`` legacy and faster resolver as per
  `pypa/pip#9187 (comment) <https://github.com/pypa/pip/issues/9187#issuecomment-853091201>`_
  since current one is endlessly failing to resolve development packages (linting tools from ``check`` targets).

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Pin ``pymongo<4`` to work with pinned ``celery`` version.

`0.4.0 <https://github.com/Ouranosinc/cowbird/tree/0.4.0>`_ (2021-08-05)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Basic users' workspaces management for new or removed users.
* Add a Mongo database backend to store/restore monitoring state across sessions.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Celery has now a proper result backend.
* Celery tasks are auto-discovered package-wide, no need to import them manually.

`0.3.0 <https://github.com/Ouranosinc/cowbird/tree/0.3.0>`_ (2021-07-06)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~

* Add the RequestTask celery task for handling external services requests.
* Add a docker image for the celery worker

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`0.2.0 <https://github.com/Ouranosinc/cowbird/tree/0.2.0>`_ (2021-05-12)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Preliminary design which includes:

  - Webhook API
  - Services interface
  - Permissions synchronizer
  - File system monitoring

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a

`0.1.0 <https://github.com/Ouranosinc/cowbird/tree/0.1.0>`_ (2021-02-18)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* First structured release which includes:

  - CI/CD utilities
  - Minimal testing of *utils*
  - Documentation of generic details (WebApp, CLI, OpenAPI, configs, etc.)
  - Metadata of the package
  - Minimal ``/services`` API route with dummy ``Service``
  - Corresponding ``cowbird services list`` CLI command

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
n/a
