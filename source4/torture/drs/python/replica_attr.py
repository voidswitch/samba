#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Tests various schema replication scenarios
#
# Copyright (C) Kamen Mazdrashki <kamenim@samba.org> 2011
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

#
# Usage:
#  export DC1=dc1_dns_name
#  export DC2=dc2_dns_name
#  export SUBUNITRUN=$samba4srcdir/scripting/bin/subunitrun
#  PYTHONPATH="$PYTHONPATH:$samba4srcdir/torture/drs/python" $SUBUNITRUN replica_attr -U"$DOMAIN/$DC_USERNAME"%"$DC_PASSWORD"
#

import drs_base
import samba.tests
import time

from ldb import (
    SCOPE_BASE, LdbError, ERR_NO_SUCH_OBJECT)

from samba.kcc.kcc_utils import RepsFromTo
from samba.dcerpc import drsblobs
from samba.ndr import ndr_unpack

class DrsReplicaAttrTestCase(drs_base.DrsBaseTestCase):
    """Intended as a test case for replication attributes"""

    def setUp(self):
        super(DrsReplicaAttrTestCase, self).setUp()
        self.ou1 = None
        self.ou2 = None
        # last_attempt and last_success times
        self.last_attempt = {}
        self.last_success = {}

    def tearDown(self):
        # re-enable replication
        self._enable_inbound_repl(self.dnsname_dc1)
        self._enable_inbound_repl(self.dnsname_dc2)
        if self.ldb_dc2 is not None:
            if self.ou1 is not None:
                try:
                    self.ldb_dc2.delete('<GUID=%s>' % self.ou1, ["tree_delete:1"])
                except LdbError, (num, _):
                    self.assertEquals(num, ERR_NO_SUCH_OBJECT)
            if self.ou2 is not None:
                try:
                    self.ldb_dc2.delete('<GUID=%s>' % self.ou2, ["tree_delete:1"])
                except LdbError, (num, _):
                    self.assertEquals(num, ERR_NO_SUCH_OBJECT)

        super(DrsReplicaAttrTestCase, self).tearDown()

    def _create_ou(self, samdb, name):
        ldif = """
dn: %s,%s
objectClass: organizationalUnit
""" % (name, self.domain_dn)
        samdb.add_ldif(ldif)
        res = samdb.search(base="%s,%s" % (name, self.domain_dn),
                           scope=SCOPE_BASE, attrs=["objectGUID"])
        return self._GUID_string(res[0]["objectGUID"][0])

    def _validate_times(self):
        '''validate times have moved forward'''
        rt = self.ldb_dc1.search(base=self.domain_dn,scope=SCOPE_BASE,attrs=["repsTo"])

        for value in rt[0]["repsTo"]:
            # get repsTo
            repsTo = RepsFromTo(self.domain_dn,ndr_unpack(drsblobs.repsFromToBlob, value))
            objGUID = str(repsTo.source_dsa_obj_guid)

            # if we have already a value they must differ and the new value should not be 0
            if objGUID in self.last_attempt:
                self.assertNotEqual(repsTo.last_attempt, 0)
                self.assertTrue(self.last_attempt[objGUID] < repsTo.last_attempt)

            # set new value
            self.last_attempt[objGUID] = repsTo.last_attempt

            if objGUID in self.last_success:
                self.assertNotEqual(repsTo.last_success, 0)
                self.assertTrue(self.last_success[objGUID] < repsTo.last_success)

            # set new value
            self.last_success[objGUID] = repsTo.last_success


    def test_RepsTo(self):
        """Tests that repsTo is changed after replication"""

        self._validate_times()

        # Create OU on DC1
        self.ou1 = self._create_ou(self.ldb_dc1, "OU=Test1")

        # wait for sync of create to settle down
        time.sleep(10)

        # Check that DC2 got the DC1 object
        res1 = self.ldb_dc2.search(base="<GUID=%s>" % self.ou1,scope=SCOPE_BASE,attrs=["name"])

        self._validate_times()

        # clean up
        self.ldb_dc1.delete('<GUID=%s>' % self.ou1)

        # wait for sync of delete to settle down
        time.sleep(10)

        self._validate_times()
