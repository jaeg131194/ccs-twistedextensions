# -*- test-case-name: twext.who.opendirectory.test.test_service -*-
##
# Copyright (c) 2013 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##

from __future__ import print_function

"""
OpenDirectory directory service implementation.
"""

from zope.interface import implements

from twisted.python.constants import Names, NamedConstant
from twisted.internet.defer import succeed, fail
from twisted.cred.checkers import ICredentialsChecker
from twisted.cred.credentials import (
    IUsernamePassword, IUsernameHashedPassword, DigestedCredentials,
)
from twisted.cred.error import UnauthorizedLogin
# from twisted.web.guard import DigestCredentialFactory

from twext.python.log import Logger

from ..idirectory import (
    DirectoryServiceError, QueryNotSupportedError,
    FieldName as BaseFieldName, RecordType as BaseRecordType,
)
from ..directory import (
    DirectoryService as BaseDirectoryService,
    DirectoryRecord as BaseDirectoryRecord,
)
from ..expression import (
    # CompoundExpression, Operand,
    MatchExpression, MatchFlags,
)
from ..util import iterFlags, ConstantsContainer

from ._odframework import ODSession, ODNode, ODQuery
from ._constants import ODSearchPath, ODRecordType, ODAttribute, ODMatchType



#
# Exceptions
#

class OpenDirectoryError(DirectoryServiceError):
    """
    OpenDirectory error.
    """

    def __init__(self, message, odError=None):
        super(OpenDirectoryError, self).__init__(message)
        self.odError = odError



class OpenDirectoryConnectionError(OpenDirectoryError):
    """
    OpenDirectory connection error.
    """



class OpenDirectoryQueryError(OpenDirectoryError):
    """
    OpenDirectory query error.
    """


class OpenDirectoryDataError(OpenDirectoryError):
    """
    OpenDirectory data error.
    """



#
# Constants
#

class FieldName(Names):
    searchPath = NamedConstant()
    searchPath.description = u"search path"
    searchPath.multiValue = False

    metaNodeLocation = NamedConstant()
    metaNodeLocation.description = u"source OD node"
    metaNodeLocation.multiValue = False

    metaRecordName = NamedConstant()
    metaRecordName.description = u"meta record name"
    metaRecordName.multiValue = False



#
# Directory Service
#

class DirectoryService(BaseDirectoryService):
    """
    OpenDirectory directory service.
    """

    implements(ICredentialsChecker)
    credentialInterfaces = (IUsernamePassword, IUsernameHashedPassword)

    log = Logger()

    recordType = ConstantsContainer((
        BaseRecordType.user, BaseRecordType.group,
    ))

    fieldName = ConstantsContainer((BaseDirectoryService.fieldName, FieldName))



    def __init__(self, nodeName=ODSearchPath.search.value):
        """
        @param nodeName: the OpenDirectory node to query against.
        @type nodeName: bytes
        """
        self._nodeName = nodeName


    @property
    def nodeName(self):
        return self._nodeName


    @property
    def realmName(self):
        return u"OpenDirectory Node {self.nodeName!r}".format(self=self)


    @property
    def session(self):
        """
        Get the underlying directory session.
        """
        self._connect()
        return self._session


    @property
    def node(self):
        """
        Get the underlying (network) directory node.
        """
        self._connect()
        return self._node


    # @property
    # def localNode(self):
    #     """
    #     Get the local node from the search path (if any), so that we can
    #     handle it specially.
    #     """
    #     if not hasattr(self, "_localNode"):
    #         if self.nodeName == ODSearchPath.search.value:
    #             result = getNodeAttributes(
    #                 self.node, ODSearchPath.search.value,
    #                 (ODAttribute.searchPath.value,)
    #             )
    #             if (
    #                 ODSearchPath.local.value in
    #                 result[ODAttribute.searchPath.value]
    #             ):
    #                 try:
    #                     self._localNode = odInit(ODSearchPath.local.value)
    #                 except ODError, e:
    #                     self.log.error(
    #                         "Failed to open local node: {error}}",
    #                         error=e,
    #                     )
    #                     raise OpenDirectoryError("", e)
    #             else:
    #                 self._localNode = None

    #         elif self.nodeName == ODSearchPath.local.value:
    #             self._localNode = self.node

    #         else:
    #             self._localNode = None

    #     return self._localNode


    def _connect(self):
        """
        Connect to the directory server.

        @raises: L{OpenDirectoryConnectionError} if unable to connect.
        """
        if not hasattr(self, "_session"):
            session = ODSession.defaultSession()

            node, error = ODNode.nodeWithSession_name_error_(
                session, self.nodeName, None
            )

            if error:
                self.log.error(
                    "Error while trying to connect to OpenDirectory node "
                    "{source.nodeName!r}: {error}",
                    error=error
                )
                raise OpenDirectoryConnectionError(
                    "Unable to connect to OpenDirectory node",
                    error
                )

            self._session = session
            self._node = node


    # def _queryStringFromExpression(self, expression):
    #     """
    #     Converts either a MatchExpression or a CompoundExpression into a
    #     native OpenDirectory query string.

    #     @param expression: The expression
    #     @type expression: Either L{MatchExpression} or L{CompoundExpression}

    #     @return: A native OpenDirectory query string
    #     @rtype: C{unicode}
    #     """

    #     if isinstance(expression, MatchExpression):
    #         matchType = ODMatchType.fromMatchType(expression.matchType)
    #         if matchType is None:
    #             raise QueryNotSupportedError(
    #                 "Unknown match type: {0}".format(matchType)
    #             )

    #         if expression.fieldName is self.fieldName.uid:
    #             odAttr = ODAttribute.guid.value
    #             value = expression.fieldValue
    #         else:
    #             odAttr = ODAttribute.fromFieldName(expression.fieldName)
    #             if odAttr is None:
    #                 raise OpenDirectoryQueryError(
    #                     "Unknown field name: {0}"
    #                     .format(expression.fieldName)
    #                 )
    #             odAttr = odAttr.value
    #             value = expression.fieldValue

    #         value = unicode(value)

    #         # FIXME: Shouldn't the value be quoted somehow?
    #         queryString = {
    #             ODMatchType.equals.value: u"({attr}={value})",
    #             ODMatchType.startsWith.value: u"({attr}={value}*)",
    #             ODMatchType.endsWith.value: u"({attr}=*{value})",
    #             ODMatchType.contains.value: u"({attr}=*{value}*)",
    #             ODMatchType.lessThan.value: u"({attr}<{value})",
    #             ODMatchType.greaterThan.value: u"({attr}>{value})",
    #         }.get(matchType.value, u"({attr}=*{value}*)").format(
    #             attr=odAttr,
    #             value=value
    #         )

    #     elif isinstance(expression, CompoundExpression):
    #         queryString = u""
    #         operand = u"&" if expression.operand is Operand.AND else u"|"

    #         if len(expression.expressions) > 1:
    #             queryString += u"("
    #             queryString += operand

    #         for subExpression in expression.expressions:
    #             queryString += self._queryStringFromExpression(subExpression)

    #         if len(expression.expressions) > 1:
    #             queryString += u")"

    #     return queryString


    # def _queryFromCompoundExpression(self, expression):
    #     """
    #     Form an OpenDirectory query from a compound expression.

    #     @param expression: The compound expression.
    #     @type expression: L{CompoundExpression}

    #     @return: A native OpenDirectory query.
    #     @rtype: L{ODQuery}
    #     """

    #     queryString = self._queryStringFromExpression(expression)

    #     recordTypes = [t.value for t in ODRecordType.iterconstants()]
    #     attributes = [a.value for a in ODAttribute.iterconstants()]
    #     maxResults = 0

    #     query, error = ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
    #         self.node,
    #         recordTypes,
    #         None,
    #         ODMatchType.compound.value,
    #         queryString,
    #         attributes,
    #         maxResults,
    #         None
    #     )

    #     if error:
    #         self.log.error(
    #             "Error while forming OpenDirectory compound query: {error}",
    #             error=error
    #         )
    #         raise OpenDirectoryQueryError(
    #             "Unable to form OpenDirectory compound query", error
    #         )

    #     return query



    def _queryFromMatchExpression(self, expression):
        """
        Form an OpenDirectory query from a match expression.

        @param expression: The match expression.
        @type expression: L{MatchExpression}

        @return: A native OpenDirectory query.
        @rtype: L{ODQuery}
        """
        if not isinstance(expression, MatchExpression):
            raise TypeError(expression)

        matchType = ODMatchType.fromMatchType(expression.matchType)
        if matchType is None:
            raise QueryNotSupportedError(
                "Unknown match type: {0}".format(matchType)
            )

        if MatchFlags.caseInsensitive in iterFlags(expression.flags):
            caseInsensitive = 0x100
        else:
            caseInsensitive = 0x0

        attributes = [a.value for a in ODAttribute.iterconstants()]
        maxResults = 0

        if expression.fieldName is self.fieldName.recordType:
            recordTypes = ODRecordType.fromRecordType(expression.fieldValue)
            queryValue = None

        else:
            recordTypes = [t.value for t in ODRecordType.iterconstants()]
            queryValue = expression.fieldValue

        query, error = ODQuery.queryWithNode_forRecordTypes_attribute_matchType_queryValues_returnAttributes_maximumResults_error_(
            self.node,
            recordTypes,
            ODAttribute.fromFieldName(expression.fieldName).value,
            matchType.value | caseInsensitive,
            queryValue,
            attributes,
            maxResults,
            None
        )

        if error:
            self.log.error(
                "Error while forming OpenDirectory match query: {error}",
                error=error
            )
            raise OpenDirectoryQueryError(
                "Unable to form OpenDirectory match query", error
            )

        return query


    def _recordsFromQuery(self, query):
        """
        Executes a query and generates directory records from it.

        @param query: A query.
        @type query: L{ODQuery}

        @return: The records produced by executing the query.
        @rtype: iterable of L{DirectoryRecord}
        """

        # FIXME: This is blocking.
        # We can call scheduleInRunLoop:forMode:, which will call back to
        # its delegate...

        odRecords, error = query.resultsAllowingPartial_error_(False, None)

        if error:
            self.log.error(
                "Error while executing OpenDirectory query: {error}",
                error=error
            )
            raise OpenDirectoryQueryError(
                "Unable to execute OpenDirectory query", error
            )

        return succeed(DirectoryRecord(self, odr) for odr in odRecords)


    def recordsFromNonCompoundExpression(self, expression, records=None):
        if isinstance(expression, MatchExpression):
            try:
                query = self._queryFromMatchExpression(expression)
                return self._recordsFromQuery(query)

            except QueryNotSupportedError:
                pass

        return BaseDirectoryService.recordsFromNonCompoundExpression(
            self, expression
        )


    #
    # Commented out because:
    #  (a) generating queries as strings is janky; note that quoting is
    #      problematic, so queries with characters like ")" don't work.
    #  (b) it removes a lot of code.
    #
    # What I'd like to see is a way to nest ODQuery objects, but I can't see
    # any support for that in the OD framework.
    #
    # This seems to also work with the local node.  -wsanchez
    #
    # def recordsFromCompoundExpression(self, expression, records=None):
    #     try:
    #         query = self._queryFromCompoundExpression(expression)
    #         return (self._recordsFromQuery(query)

    #     except QueryNotSupportedError:
    #         return BaseDirectoryService.recordsFromCompoundExpression(
    #             self, expression
    #         )


    def _getUserRecord(self, username):
        """
        Fetch the OD record for a given user.

        @return: ODRecord, or None
        """
        record, error = self.node.recordWithRecordType_name_attributes_error_(
            ODRecordType.user.value, username, None, None
        )
        if error:
            self.log.error(
                "Error while looking up user: {error}",
                error=error
            )
            raise OpenDirectoryQueryError("Unable to look up user", error)

        return record


    def requestAvatarId(self, credentials):
        """
        Authenticate the credentials against OpenDirectory and return the
        corresponding directory record.

        @param: credentials: The credentials to authenticate.
        @type: credentials: L{ICredentials}

        @return: The directory record for the given credentials.
        @rtype: deferred L{DirectoryRecord}

        @raises: L{UnauthorizedLogin} if the credentials are not valid.
        """

        odRecord = self._getUserRecord(credentials.username)

        if odRecord is None:
            return fail(UnauthorizedLogin("No such user"))

        if IUsernamePassword.providedBy(credentials):
            result, error = odRecord.verifyPassword_error_(
                credentials.password, None
            )

            if error:
                return fail(UnauthorizedLogin(error))

            if result:
                return succeed(DirectoryRecord(self, odRecord))

        elif isinstance(credentials, DigestedCredentials):
            try:
                credentials.fields.setdefault("algorithm", "md5")
                challenge = (
                    'Digest realm="{realm}", nonce="{nonce}", '
                    'algorithm={algorithm}'
                    .format(**credentials.fields)
                )
                response = credentials.fields["response"]

            except KeyError as e:
                self.log.error(
                    "Error authenticating against OpenDirectory: "
                    "missing digest response field {field!r} in "
                    "{credentials.fields!r}",
                    field=e.args[0], credentials=credentials
                )
                return fail(UnauthorizedLogin("Invalid digest challenge"))

            result, m1, m2, error = odRecord.verifyExtendedWithAuthenticationType_authenticationItems_continueItems_context_error_(
                u"dsAuthMethodStandard:dsAuthNodeDIGEST-MD5",
                [
                    credentials.username,
                    challenge,
                    response,
                    credentials.method,
                ],
                None, None, None
            )

            if error:
                return fail(UnauthorizedLogin(error))

            if result:
                return succeed(DirectoryRecord(self, odRecord))

        else:
            return fail(UnauthorizedLogin(
                "Unknown credentials type: {0}".format(type(credentials))
            ))

        return fail(UnauthorizedLogin("Unknown authorization failure"))



# class CustomDigestCredentialFactory(DigestCredentialFactory):
#     """
#     DigestCredentialFactory without qop, to interop with OD.
#     """

#     def getChallenge(self, address):
#         result = DigestCredentialFactory.getChallenge(self, address)
#         del result["qop"]
#         return result



class DirectoryRecord(BaseDirectoryRecord):
    """
    OpenDirectory directory record.
    """

    log = Logger()

    # GUID is a required attribute for OD records.
    requiredFields = BaseDirectoryRecord.requiredFields + (BaseFieldName.guid,)


    def __init__(self, service, odRecord):
        details, error = odRecord.recordDetailsForAttributes_error_(None, None)

        if error:
            self.log.error(
                "Error while reading OpenDirectory record: {error}",
                error=error
            )
            raise OpenDirectoryDataError(
                "Unable to read OpenDirectory record", error
            )

        def coerceType(fieldName, value):
            # Record type field value needs to be looked up
            if fieldName is service.fieldName.recordType:
                return ODRecordType.lookupByValue(value).recordType

            # Otherwise, cast to the valueType specified by the field name
            valueType = service.fieldName.valueType(fieldName)
            try:
                return valueType(value)
            except BaseException as e:
                raise OpenDirectoryDataError(
                    "Unable to coerce OD value {0!r} to type {1}: {2}"
                    .format(value, valueType, e)
                )

        fields = {}
        for name, values in details.iteritems():
            if name == ODAttribute.metaRecordName.value:
                # We get this field even though we did not ask for it...
                continue

            try:
                attribute = ODAttribute.lookupByValue(name)
            except ValueError:
                self.log.debug(
                    "Unexpected OpenDirectory record attribute: {attribute}",
                    attribute=name
                )
                continue

            fieldName = attribute.fieldName

            if type(values) is bytes:
                values = (coerceType(fieldName, values),)
            else:
                values = tuple(coerceType(fieldName, v) for v in values)

            if service.fieldName.isMultiValue(fieldName):
                fields[fieldName] = values
            else:
                assert len(values) == 1
                fields[fieldName] = values[0]

        # Set uid from guid
        fields[service.fieldName.uid] = unicode(fields[service.fieldName.guid])

        super(DirectoryRecord, self).__init__(service, fields)
        self._odRecord = odRecord