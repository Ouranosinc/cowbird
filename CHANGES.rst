.. explicit references must be used in this file (not references.rst) to ensure they are directly rendered on Github
.. :changelog:

Changes
*******

`Unreleased <https://github.com/Ouranosinc/cowbird/tree/master>`_ (latest)
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
