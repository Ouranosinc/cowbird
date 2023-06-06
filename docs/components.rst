.. include:: references.rst

.. _components_page:

Components
==========

Components Diagram
-------------------

.. image:: _static/cowbird_components.png
  :width: 800
  :alt: Cowbird Components

.. _components_handlers:

Handlers
--------

Each handler is associated to a service and is used to process different events and to keep the different services of
the platform synchronized. Handlers are useful for example to process user or permission changes,
or to manage file modification events.

.. _components_geoserver:

Geoserver
~~~~~~~~~

The `Geoserver` handler is used to keep the internal representation on the `Geoserver` server along with the user
workspace in sync with the rest of the platform.

If a new user is created on `Magpie`_, a `Geoserver` workspace is automatically created for the user, along with a
datastore folder in the user workspace to contain the different shapefiles of the user. Similarly, if the user is
deleted on `Magpie`_, the `Geoserver` workspace of the user is automatically deleted to keep the services
synchronized.

The workspace and file permissions are also synchronized between `Magpie`_ and `Geoserver`. For example, if a
permission is added or removed in `Magpie`_, the file found in the user's datastore must have corresponding permissions
in order to reflect the actual user access permissions.

Since the `Magpie`_ permissions on a resource of type `Geoserver` are not the same as traditional Unix permissions
(ex.: ``rwx``) on the workspace/shapefiles, some design choices were done in order to have a coherent synchronization :

.. _geoserver_general_notes:

General notes
#############

Each permissions on `Magpie`_ on a resource of type `Geoserver` are classified as either ``read`` or ``write`` in
order to associate them to the actual path permissions.
If the path receives a ``read`` permission, every `Magpie`_ permissions fitting the ``read`` category will be enabled.

If a `Magpie`_ permissions of type ``read`` is added, the path will be updated to have ``read`` permissions. This
update on the file system will trigger a synchronization with `Magpie`_, to add all other ``read`` type permissions on
Magpie.

Note that permissions are only added to `Magpie`_ if necessary. For example, if a file needs to allow a ``read``
permission on `Magpie`_, but that permission already resolves to ``allow`` because of a recursive permission on a parent
resource, no permission will be added. The permission is already resolving to the required permission and avoiding to
add unnecessary permissions will simplify permission solving.

The permissions applied on the files and folders are only applied for a user, and no permissions are enabled on the
group or for other users. The reason for this is that workspaces are separated by user and we do not use a group
concept on the file system for now. This means that if a permission is applied to a group in `Magpie`_, `Cowbird`
will detect the permission change but will not do anything, since the group on the file system does not correspond to
the groups found on `Magpie`_. Also, it would not make sense to update the file associated to a resource for all the
users of a group, since the file is supposed to be associated to a single user anyway.

Note that even if group permission changes on `Magpie`_ are not handled by `Cowbird`, a group permission could still
have an impact on permission resolution. For example, if a shapefile needs to allow a ``read`` permission on `Magpie`_,
but that permission already resolves to ``allow`` because of a group permission, no permission will be added.

.. _geoserver_file_layer_permissions:

File/Layer permissions
######################

Also, file events will only be processed in the case of the ``.shp`` file, since it is considered to be the main
component of a shapefile. The other extensions associated with a shapefile will not be processed if they trigger an
event, and will only be updated in the case of a change on the ``.shp`` file.

Note that in the case where a user has all the ``read`` permissions on `Magpie`_ for example, and a single one of
them is deleted, `Cowbird` will not change the file permissions since other ``read`` permissions will still be found on
Magpie. This means that a synchronization will not be triggered and `Magpie`_ permissions will stay the same, meaning
all the ``read`` permissions activated except for the one removed.
If eventually a change is applied to the file (ex.: changing the permissions from ``r--`` to ``rw-``),
it would trigger a synchronization, and the one `Magpie`_ permission that was removed earlier would be reenabled,
because of the ``read`` permission found on the file.
The same would apply if we use ``write`` permissions in this last example.

Shapefiles will only be assigned ``read`` or ``write`` permissions on the file system. ``execute`` permissions are not
needed for shapefiles.

.. _geoserver_folder_workspace_permissions:

Folder/Workspace permissions
############################

Workspaces will always keep their ``execute`` permissions even if they don't have any permissions enabled on `Magpie`_.
This enables accessing the children files, in case the children resource has permissions enabled on `Magpie`_.
Since a children resource has priority on `Magpie`_ if its permissions are enabled, it makes sense to allow the access
to the file on the file system too. Note that if the folder only has ``execute`` permissions, the file will only be
accessible via a direct path or url, and it will not be accessible via a file browser, or on the JupyterLab file
browser. This should allow the user to still share his file using a path or url.

.. _geoserver_operations_to_avoid:

Operations to avoid
###################

Note also that some operations should be avoided, as they are undesirable and not supported for now.

- Renaming a folder :
    The folders associated with the `Geoserver` workspace are the user workspace (named by the user's name)
    and the datastore folder (which uses a default value. Both of these values should never change and renaming them
    manually might break the monitoring, preventing `Cowbird` from receiving future file events.

- Renaming a shapefile (.shp only) :
    This operation is actually supported, but it should be avoided if possible. It will trigger multiple events on the
    file system (an update on the parent directory, and a delete followed by a create event on the file), which should
    keep up to data info in `Geoserver` and `Magpie`_ by simply generating new resources. A risk with this is that the
    delete event will delete the other shapefile files, and the user could lose some data. It is better to have a copy
    of the shapefile before applying this operation. Note that renaming one of the other extension (not the .shp file)
    will not trigger any event since only the main file triggers events.

- Deleting a folder :
    This operation will only display a warning. It should never be done manually, since it will create inconsistencies
    with the `Geoserver` workspace and the `Magpie`_ resources. The user workspace and the datastore folder
    should only be deleted when a user is deleted via `Magpie`_.
