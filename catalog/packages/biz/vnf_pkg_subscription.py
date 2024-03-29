# Copyright (C) 2019 Verizon. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import ast
import json
import logging
import os
import uuid
from collections import Counter

import requests
from requests.auth import HTTPBasicAuth
from rest_framework import status

from catalog.packages import const
from catalog.pub.database.models import VnfPkgSubscriptionModel
from catalog.pub.exceptions import VnfPkgSubscriptionException, \
    VnfPkgDuplicateSubscriptionException, SubscriptionDoesNotExistsException
from catalog.pub.utils.values import ignore_case_get

logger = logging.getLogger(__name__)

ROOT_FILTERS = {
    "notificationTypes": "notification_types",
    "vnfdId": "vnfd_id",
    "vnfPkgId": "vnf_pkg_id",
    "operationalState": "operation_states",
    "usageState": "usage_states"
}


def is_filter_type_equal(new_filter, existing_filter):
    return Counter(new_filter) == Counter(existing_filter)


class CreateSubscription(object):
    """
    Create subscription info
    """
    def __init__(self, data):
        self.data = data
        self.filter = ignore_case_get(self.data, "filter", {})
        self.callback_uri = ignore_case_get(self.data, "callbackUri")
        self.authentication = ignore_case_get(self.data, "authentication", {})
        self.notification_types = ignore_case_get(self.filter, "notificationTypes", [])
        self.operation_states = ignore_case_get(self.filter, "operationalState", [])
        self.usage_states = ignore_case_get(self.filter, "usageState", [])
        self.vnfd_id = ignore_case_get(self.filter, "vnfdId", [])
        self.vnf_pkg_id = ignore_case_get(self.filter, "vnfPkgId", [])
        self.vnf_products_from_provider = \
            ignore_case_get(self.filter, "vnfProductsFromProviders", [])

    def check_callbackuri_connection(self):
        """
        Check if the callback uri can access
        :return:
        """
        logger.debug("SubscribeNotification-post::> Sending GET request "
                     "to %s" % self.callback_uri)
        try:
            if self.authentication:
                if const.BASIC in self.authentication.get("authType", ''):
                    params = self.authentication.get("paramsBasic", {})
                    username = params.get("userName")
                    password = params.get("password")
                    response = requests.get(self.callback_uri, auth=HTTPBasicAuth(username, password), timeout=2,
                                            verify=False)
                elif const.OAUTH2_CLIENT_CREDENTIALS in self.authentication.get("authType", ''):
                    # todo
                    pass
                else:
                    # todo
                    pass
            else:
                response = requests.get(self.callback_uri, timeout=2, verify=False)
            if response.status_code != status.HTTP_204_NO_CONTENT:
                raise VnfPkgSubscriptionException(
                    "callbackUri %s returns %s status code." % (
                        self.callback_uri,
                        response.status_code
                    )
                )
        except Exception:
            raise VnfPkgSubscriptionException(
                "callbackUri %s didn't return 204 status code." % self.callback_uri
            )

    def do_biz(self):
        """
        Do business
        :return:
        """
        self.subscription_id = str(uuid.uuid4())
        self.check_valid_auth_info()
        self.check_callbackuri_connection()
        self.check_valid()
        self.save_db()
        subscription = VnfPkgSubscriptionModel.objects.get(
            subscription_id=self.subscription_id
        )
        if subscription:
            return subscription.toDict()

    def check_valid_auth_info(self):
        """
        Check if the Auth info is valid
        :return:
        """
        logger.debug("SubscribeNotification--post::> Validating Auth "
                     "details if provided")
        if self.authentication.get("paramsBasic", {}) and const.BASIC not in self.authentication.get("authType"):
            raise VnfPkgSubscriptionException('Auth type should be ' + const.BASIC)
        if self.authentication.get("paramsOauth2ClientCredentials", {}) \
                and const.OAUTH2_CLIENT_CREDENTIALS not in self.authentication.get("authType"):
            raise VnfPkgSubscriptionException('Auth type should be ' + const.OAUTH2_CLIENT_CREDENTIALS)

    def check_filter_exists(self, sub):
        # Check the usage states, operationStates
        for filter_type in ["operation_states", "usage_states"]:
            if not is_filter_type_equal(getattr(self, filter_type),
                                        ast.literal_eval(getattr(sub, filter_type))):
                return False
        # If all the above types are same then check id filter
        for id_filter in ["vnfd_id", "vnf_pkg_id"]:
            if not is_filter_type_equal(getattr(self, id_filter),
                                        ast.literal_eval(getattr(sub, id_filter))):
                return False
        return True

    def check_valid(self):
        links = ""
        logger.debug("SubscribeNotification--post::> Checking DB if "
                     "callbackUri already exists")
        subscriptions = VnfPkgSubscriptionModel.objects.filter(callback_uri=self.callback_uri)
        for subscription in subscriptions:
            if self.check_filter_exists(subscription):
                links = json.loads(subscription.links)
                logger.error("Subscriptions has already exists with the same callbackUri and filter:%s" % links)
                raise VnfPkgDuplicateSubscriptionException(
                    "/%s" % (links["self"]["href"]))

        return True

    def save_db(self):
        """
        Save the subscription info to DB
        :return:
        """
        logger.debug("SubscribeNotification--post::> Saving the subscription "
                     "%s to the database" % self.subscription_id)
        links = {
            "self": {
                "href": os.path.join(const.VNFPKG_SUBSCRIPTION_ROOT_URI, self.subscription_id)
            }
        }
        VnfPkgSubscriptionModel.objects.create(
            subscription_id=self.subscription_id,
            callback_uri=self.callback_uri,
            notification_types=json.dumps(self.notification_types),
            auth_info=json.dumps(self.authentication),
            usage_states=json.dumps(self.usage_states),
            operation_states=json.dumps(self.operation_states),
            vnf_products_from_provider=json.dumps(self.vnf_products_from_provider),
            vnfd_id=json.dumps(self.vnfd_id),
            vnf_pkg_id=json.dumps(self.vnf_pkg_id),
            links=json.dumps(links))
        logger.debug('Create Subscription[%s] success', self.subscription_id)


class QuerySubscription(object):
    """
    The class for query subscription
    """
    def query_multi_subscriptions(self, params):
        """
        Query subscriptions
        :param params:
        :return:
        """
        query_data = {}
        logger.debug("QuerySubscription--get--multi--subscriptions--biz::> Check "
                     "for filter in query params %s" % params)
        for query, value in list(params.items()):
            if query in ROOT_FILTERS:
                query_data[ROOT_FILTERS[query] + '__icontains'] = value
        # Query the database with filter if the request has fields in request params, else fetch all records
        if query_data:
            subscriptions = VnfPkgSubscriptionModel.objects.filter(**query_data)
        else:
            subscriptions = VnfPkgSubscriptionModel.objects.all()
        if not subscriptions.exists():
            return []
        return [subscription.toDict() for subscription in subscriptions]

    def query_single_subscription(self, subscription_id):
        """
        Query subscription by id
        :param subscription_id:
        :return:
        """
        logger.debug("QuerySingleSubscriptions--get--single--subscription--biz::> "
                     "ID: %s" % subscription_id)

        subscription = VnfPkgSubscriptionModel.objects.filter(
            subscription_id=subscription_id)
        if not subscription.exists():
            raise SubscriptionDoesNotExistsException("Subscription with ID: %s "
                                                     "does not exist" % subscription_id)
        return subscription[0].toDict()


class TerminateSubscription(object):
    """
    The class to terminate the subscription
    """
    def terminate(self, subscription_id):
        logger.debug("TerminateSubscriptions--delete--biz::> "
                     "ID: %s" % subscription_id)

        subscription = VnfPkgSubscriptionModel.objects.filter(
            subscription_id=subscription_id)
        if not subscription.exists():
            raise SubscriptionDoesNotExistsException("Subscription with ID: %s "
                                                     "does not exist" % subscription_id)
        subscription[0].delete()
