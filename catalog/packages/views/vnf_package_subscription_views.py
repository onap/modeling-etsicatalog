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

import logging
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.packages.biz.vnf_pkg_subscription import CreateSubscription
from catalog.packages.biz.vnf_pkg_subscription import QuerySubscription
from catalog.packages.biz.vnf_pkg_subscription import TerminateSubscription
from catalog.packages.const import TAG_VNF_PACKAGE_API
from catalog.packages.serializers.response import ProblemDetailsSerializer
from catalog.packages.serializers.vnf_pkg_subscription import PkgmSubscriptionRequestSerializer
from catalog.packages.serializers.vnf_pkg_subscription import PkgmSubscriptionSerializer
from catalog.packages.serializers.vnf_pkg_subscription import PkgmSubscriptionsSerializer
from catalog.packages.serializers.vnf_pkg_notifications import PkgOnboardingNotificationSerializer
from catalog.packages.serializers.vnf_pkg_notifications import PkgChangeNotificationSerializer
from catalog.packages.views.common import validate_data, validate_req_data
from catalog.pub.exceptions import BadRequestException
from catalog.pub.exceptions import VnfPkgSubscriptionException
from .common import view_safe_call_with_log

logger = logging.getLogger(__name__)

VALID_FILTERS = [
    "callbackUri",
    "notificationTypes",
    "vnfdId",
    "vnfPkgId",
    "operationalState",
    "usageState"
]


class CreateQuerySubscriptionView(APIView):
    """
    This resource represents subscriptions.
    The client can use this resource to subscribe to notifications related to NS lifecycle management,
    and to query its subscriptions.
    """

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        request_body=PkgmSubscriptionRequestSerializer,
        responses={
            status.HTTP_201_CREATED: PkgmSubscriptionSerializer(),
            status.HTTP_400_BAD_REQUEST: ProblemDetailsSerializer(),
            status.HTTP_500_INTERNAL_SERVER_ERROR: ProblemDetailsSerializer()
        }
    )
    @view_safe_call_with_log(logger=logger)
    def post(self, request):
        """
        The POST method creates a new subscription
        :param request:
        :return:
        """
        logger.debug("Create VNF package Subscription> %s" % request.data)
        vnf_pkg_subscription_request = validate_req_data(request.data, PkgmSubscriptionRequestSerializer)
        data = CreateSubscription(vnf_pkg_subscription_request.data).do_biz()
        subscription_info = validate_data(data, PkgmSubscriptionSerializer)
        return Response(data=subscription_info.data, status=status.HTTP_201_CREATED)

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        responses={
            status.HTTP_200_OK: PkgmSubscriptionSerializer(),
            status.HTTP_400_BAD_REQUEST: ProblemDetailsSerializer(),
            status.HTTP_500_INTERNAL_SERVER_ERROR: ProblemDetailsSerializer()
        }
    )
    @view_safe_call_with_log(logger=logger)
    def get(self, request):
        """
        The GET method queries the list of active subscriptions of the functional block that invokes the method.
        It can be used e.g. for resynchronization after error situations.
        :param request:
        :return:
        """
        logger.debug("SubscribeNotification--get::> %s" % request.query_params)

        if request.query_params and not set(request.query_params).issubset(set(VALID_FILTERS)):
            raise BadRequestException("Not a valid filter")

        resp_data = QuerySubscription().query_multi_subscriptions(request.query_params)

        subscriptions_serializer = PkgmSubscriptionsSerializer(data=resp_data)
        if not subscriptions_serializer.is_valid():
            raise VnfPkgSubscriptionException(subscriptions_serializer.errors)

        return Response(data=subscriptions_serializer.data, status=status.HTTP_200_OK)


class QueryTerminateSubscriptionView(APIView):
    """
    This resource represents an individual subscription.
    It can be used by the client to read and to terminate a subscription to Notifications related to NS lifecycle management.
    """

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        responses={
            status.HTTP_200_OK: PkgmSubscriptionSerializer(),
            status.HTTP_404_NOT_FOUND: ProblemDetailsSerializer(),
            status.HTTP_500_INTERNAL_SERVER_ERROR: ProblemDetailsSerializer()
        }
    )
    @view_safe_call_with_log(logger=logger)
    def get(self, request, subscriptionId):
        """
        The GET method retrieves information about a subscription by reading an individual subscription resource.
        :param request:
        :param subscriptionId:
        :return:
        """
        logger.debug("SubscribeNotification--get::> %s" % subscriptionId)

        resp_data = QuerySubscription().query_single_subscription(subscriptionId)

        subscription_serializer = PkgmSubscriptionSerializer(data=resp_data)
        if not subscription_serializer.is_valid():
            raise VnfPkgSubscriptionException(subscription_serializer.errors)

        return Response(data=subscription_serializer.data, status=status.HTTP_200_OK)

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        responses={
            status.HTTP_204_NO_CONTENT: "",
            status.HTTP_404_NOT_FOUND: ProblemDetailsSerializer(),
            status.HTTP_500_INTERNAL_SERVER_ERROR: ProblemDetailsSerializer()
        }
    )
    @view_safe_call_with_log(logger=logger)
    def delete(self, request, subscriptionId):
        """
        The DELETE method terminates an individual subscription.
        :param request:
        :param subscriptionId:
        :return:
        """
        logger.debug("SubscribeNotification--get::> %s" % subscriptionId)

        TerminateSubscription().terminate(subscriptionId)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PkgOnboardingNotificationView(APIView):
    """
    This resource represents a notification endpoint about package onboarding
    """

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        request_body=PkgOnboardingNotificationSerializer,
        responses={
            status.HTTP_204_NO_CONTENT: ""
        }
    )
    def post(self):
        pass

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        responses={
            status.HTTP_204_NO_CONTENT: "",
            status.HTTP_500_INTERNAL_SERVER_ERROR: openapi.Response('error message',
                                                                    openapi.Schema(type=openapi.TYPE_STRING))}
    )
    def get(self):
        pass


class PkgChangeNotificationView(APIView):
    """
    This resource represents a notification endpoint about package change
    """

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        request_body=PkgChangeNotificationSerializer,
        responses={
            status.HTTP_204_NO_CONTENT: ""
        }
    )
    def post(self):
        pass

    @swagger_auto_schema(
        tags=[TAG_VNF_PACKAGE_API],
        responses={
            status.HTTP_204_NO_CONTENT: "",
            status.HTTP_500_INTERNAL_SERVER_ERROR: openapi.Response('error message',
                                                                    openapi.Schema(type=openapi.TYPE_STRING))}
    )
    def get(self):
        pass
