.. explicit references must be used in this file (not references.rst) to ensure they are directly rendered on Github
.. :changelog:

Changes
*******

`Unreleased <https://github.com/Ouranosinc/cowbird/tree/master>`_ (latest)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Add permission synchronization between Magpie's permissions and Geoserver files permissions.

Bug Fixes
~~~~~~~~~~~~~~~~~~~~~
* Fix bug where the monitors saved on the database and the intermal monitors dictionary from the `Monitoring` class
  would be desynchronized, not always having the expected monitors, or having monitors that were not started properly.

`1.1.1 <https://github.com/Ouranosinc/cowbird/tree/1.1.1>`_ (2023-03-24)
------------------------------------------------------------------------------------

Features / Changes
~~~~~~~~~~~~~~~~~~~~~
* Return `HTTP 424 (Failed Dependency)` when the `celery` worker version cannot be retrieved on ``GET /version``.
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
