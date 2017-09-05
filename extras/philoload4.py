#!/usr/bin/env python

from __future__ import absolute_import
from __future__ import print_function
import imp
import os
import sys

from philologic.LoadOptions import LoadOptions
from philologic.Loader import Loader, setup_db_dir

# Load global config
config_file = imp.load_source("philologic4", "/etc/philologic/philologic4.cfg")

os.environ["LC_ALL"] = "C"  # Exceedingly important to get uniform sort order.
os.environ["PYTHONIOENCODING"] = "utf-8"

if __name__ == '__main__':
    load_options = LoadOptions()
    load_options.parse(sys.argv)
    setup_db_dir(load_options["db_destination"], load_options["web_app_dir"], force_delete=load_options.force_delete)

    # Database load
    l = Loader(**load_options.values)
    l.add_files(load_options.files)
    if load_options.bibliography:
        load_metadata = l.parse_bibliography_file(load_options.bibliography, load_options.sort_order)
    else:
        load_metadata = l.parse_metadata(load_options.sort_order, header=load_options.header)
    l.parse_files(load_options.cores, load_metadata)
    l.merge_objects()
    l.analyze()
    l.setup_sql_load()
    l.post_processing()
    l.finish()
    if l.deleted_files:
        print("The following files where not loaded due to invalid data in the header:\n{}".format("\n".join(l.deleted_files)))

    print("Application viewable at %s\n" % os.path.join(config_file.url_root, load_options.dbname))
