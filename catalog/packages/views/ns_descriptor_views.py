# Copyright 2018 ZTE Corporation.
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

from django.http import StreamingHttpResponse
from drf_yasg.utils import no_body, swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from catalog.packages.biz.ns_descriptor import NsDescriptor
from catalog.packages.const import TAG_NSD_API
from catalog.packages.serializers.create_nsd_info_request import CreateNsdInfoRequestSerializer
from catalog.packages.serializers.nsd_info import NsdInfoSerializer
from catalog.packages.serializers.nsd_infos import NsdInfosSerializer
from catalog.packages.views.common import validate_data
from catalog.pub.exceptions import CatalogException
from .common import view_safe_call_with_log

logger = logging.getLogger(__name__)


@swagger_auto_schema(
    method='GET',
    operation_description="Query a NSD",
    tags=[TAG_NSD_API],
    request_body=no_body,
    responses={
        status.HTTP_200_OK: NsdInfoSerializer(),
        status.HTTP_404_NOT_FOUND: 'NSDs do not exist',
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@swagger_auto_schema(
    method='DELETE',
    operation_description="Delete a NSD",
    tags=[TAG_NSD_API],
    request_body=no_body,
    responses={
        status.HTTP_204_NO_CONTENT: "No content",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@api_view(http_method_names=['GET', 'DELETE'])
@view_safe_call_with_log(logger=logger)
def ns_info_rd(request, **kwargs):
    nsd_info_id = kwargs.get("nsdInfoId")
    if request.method == 'GET':
        # Read information about an individual NS descriptor resource.
        data = NsDescriptor().query_single(nsd_info_id)
        nsd_info = validate_data(data, NsdInfoSerializer)
        return Response(data=nsd_info.data, status=status.HTTP_200_OK)
    if request.method == 'DELETE':
        # Delete an individual NS descriptor resource.
        NsDescriptor().delete_single(nsd_info_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


@swagger_auto_schema(
    method='POST',
    operation_description="Create a NSD",
    tags=[TAG_NSD_API],
    request_body=CreateNsdInfoRequestSerializer(),
    responses={
        status.HTTP_201_CREATED: NsdInfoSerializer(),
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@swagger_auto_schema(
    method='GET',
    operation_description="Query multiple NSDs",
    tags=[TAG_NSD_API],
    request_body=no_body,
    responses={
        status.HTTP_200_OK: NsdInfosSerializer(),
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@api_view(http_method_names=['POST', 'GET'])
@view_safe_call_with_log(logger=logger)
def ns_descriptors_rc(request):
    if request.method == 'POST':
        # Create a new NS descriptor resource.
        create_nsd_info_request = validate_data(request.data, CreateNsdInfoRequestSerializer)
        data = NsDescriptor().create(create_nsd_info_request.data)
        validate_data(data, NsdInfoSerializer)
        return Response(data=data, status=status.HTTP_201_CREATED)

    if request.method == 'GET':
        # Query information about multiple NS descriptor resources.
        nsdId = request.query_params.get("nsdId", None)
        data = NsDescriptor().query_multiple(nsdId)
        validate_data(data, NsdInfosSerializer)
        return Response(data=data, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='PUT',
    operation_description="Upload NSD content",
    tags=[TAG_NSD_API],
    request_body=no_body,
    responses={
        status.HTTP_204_NO_CONTENT: 'PNFD file',
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@swagger_auto_schema(
    method='GET',
    operation_description="Download NSD content",
    tags=[TAG_NSD_API],
    request_body=no_body,
    responses={
        status.HTTP_204_NO_CONTENT: "No content",
        status.HTTP_404_NOT_FOUND: 'NSD does not exist.',
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@api_view(http_method_names=['PUT', 'GET'])
@view_safe_call_with_log(logger=logger)
def nsd_content_ru(request, **kwargs):
    nsd_info_id = kwargs.get("nsdInfoId")
    if request.method == 'PUT':
        # Upload the content of a NSD.
        files = request.FILES.getlist('file')
        try:
            local_file_name = NsDescriptor().upload(nsd_info_id, files[0])
            NsDescriptor().parse_nsd_and_save(nsd_info_id, local_file_name)
            return Response(data=None, status=status.HTTP_204_NO_CONTENT)
        except CatalogException as e:
            NsDescriptor().handle_upload_failed(nsd_info_id)
            raise e
        except Exception as e:
            NsDescriptor().handle_upload_failed(nsd_info_id)
            raise e

    if request.method == 'GET':
        # Fetch the content of a NSD.
        file_range = request.META.get('HTTP_RANGE')
        file_iterator = NsDescriptor().download(nsd_info_id, file_range)
        return StreamingHttpResponse(file_iterator, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='PUT',
    operation_description="Update a NSD",
    request_body=no_body,
    responses={
        status.HTTP_202_ACCEPTED: "Successfully",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "Internal error"
    }
)
@api_view(http_method_names=['PUT'])
@view_safe_call_with_log(logger=logger)
def ns_descriptors_u(request, **kwargs):
    if request.method == 'PUT':
        nsd_info_id = kwargs.get("nsdInfoId")
        NsDescriptor().update(request.data, nsd_info_id)
        return Response(data=None, status=status.HTTP_202_ACCEPTED)
