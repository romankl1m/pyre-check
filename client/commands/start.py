# Copyright (c) 2016-present, Facebook, Inc.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import logging
import os

from .. import FAILURE, SUCCESS, filesystem
from .error_handling import ErrorHandling


LOG = logging.getLogger(__name__)


class Start(ErrorHandling):
    NAME = "start"

    def __init__(self, arguments, configuration, source_directory) -> None:
        super(Start, self).__init__(arguments, configuration, source_directory)
        self._terminal = arguments.terminal
        self._no_watchman = arguments.no_watchman
        self._number_of_workers = configuration.number_of_workers

    def _run(self) -> int:
        while True:
            # Be optimistic in grabbing the lock in order to provide users with
            # a message when the lock is being waited on.
            blocking = False
            try:
                with filesystem.acquire_lock(".pyre/client.lock", blocking):
                    # This unsafe call is OK due to the client lock always
                    # being acquired before starting a server - no server can
                    # spawn in the interim which would cause a race.
                    try:
                        with filesystem.acquire_lock(
                            os.path.join(
                                self._source_directory, ".pyre", "server", "server.lock"
                            ),
                            blocking=False,
                        ):
                            pass
                    except OSError:
                        LOG.warning(
                            "Server at `%s` exists, skipping.", self._source_directory
                        )
                        return FAILURE

                    flags = self._flags()
                    filter_directories = self._get_directories_to_analyze()
                    # Check the length in order to only add the flag when we have a
                    # strict superset.
                    if len(filter_directories) > 1 and filter_directories.issuperset(
                        {self._source_directory}
                    ):
                        flags.extend(
                            ["-filter-directories", ",".join(list(filter_directories))]
                        )
                    if not self._no_watchman:
                        flags.append("-use-watchman")
                    if self._terminal:
                        flags.append("-terminal")
                    flags.extend(
                        [
                            "-workers",
                            str(self._number_of_workers),
                            "-typeshed",
                            str(self._configuration.get_typeshed()),
                            "-expected-binary-version",
                            str(self._configuration.get_version_hash()),
                        ]
                    )
                    search_path = self._configuration.get_search_path()
                    if search_path:
                        flags.extend(["-search-path", ",".join(search_path)])
                    self._call_client(command=self.NAME, flags=flags).check()

                    return SUCCESS
            except OSError:
                blocking = True
                LOG.info("Waiting on the pyre client lock.")
