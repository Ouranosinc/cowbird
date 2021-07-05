.. include:: references.rst

.. _utilities_page:

CLI Utilities
=====================

.. _cli:

CLI Helpers and Commands
-------------------------

Multiple CLI helpers are provided.

The common functions provided allow invocation and result retrieval similar to the Web API, but from a terminal.
The :ref:`configuration` files must be available in default location, or provided as input to resolve operations.

Please refer to the corresponding usage detail of each helper by calling them with ``--help`` argument for more details.
More specifically:

.. code-block:: console

    # display available helpers
    cowbird --help

    # display available commands of 'services' helper
    cowbird services --help

    # display specific arguments and options of 'list' command of 'services' helper
    cowbird services list --help


The ``cowbird`` CLI should be available on your path directly following :ref:`installation` of the package.
When using an ``conda`` environment, you should activate it first to make the CLI available.

Source code of these helpers can be found `here <https://github.com/Ouranosinc/cowbird/tree/master/cowbird/cli>`_.
