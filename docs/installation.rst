.. include:: references.rst

.. _installation:
.. _installation_page:

Installation
=============

Basic Setup
~~~~~~~~~~~~

At the command line:

.. code-block:: console

    make install


This will create a ``conda`` environment named ``cowbird``, and install all required dependencies of the package in it.
You should be ready to employ `Cowbird` with example :ref:`configuration` files at this point.

Advanced
~~~~~~~~~~~~

To install in another environment, ``CONDA_ENV_NAME`` can be provided to ``make``.

Otherwise, following can be used to install with whichever ``python`` is detected (up to user to manage references):

.. code-block:: console

    make install-pkg


If you want the full setup for development (including dependencies for test execution), use:

.. code-block:: console

    make install-dev
