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

import json
import os
import shutil
import urllib
import zipfile

import mock
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from catalog.packages.biz.vnf_package import VnfPackage, VnfPkgUploadThread
from catalog.packages.const import PKG_STATUS
from catalog.packages.tests.const import vnfd_data
from catalog.pub.config.config import CATALOG_ROOT_PATH
from catalog.pub.database.models import VnfPackageModel
from catalog.pub.utils import toscaparser

VNF_BASE_URL = "/api/vnfpkgm/v1/vnf_packages"


class MockReq():
    def read(self):
        return "1"

    def close(self):
        pass


class TestVnfPackage(TestCase):
    def setUp(self):
        self.client = APIClient()

    def tearDown(self):
        file_path = os.path.join(CATALOG_ROOT_PATH, "222")
        if os.path.exists(file_path):
            shutil.rmtree(file_path)

    @mock.patch.object(toscaparser, 'parse_vnfd')
    def test_upload_vnf_pkg(self, mock_parse_vnfd):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "empty.txt"), "rt")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        mock_parse_vnfd.return_value = json.JSONEncoder().encode(vnfd_data)
        response = self.client.put("%s/222/package_content" % VNF_BASE_URL, data=data)
        vnf_pkg = VnfPackageModel.objects.filter(vnfPackageId="222")
        self.assertEqual("00342b18-a5c7-11e8-998c-bf1755941f12", vnf_pkg[0].vnfdId)
        self.assertEqual(PKG_STATUS.ONBOARDED, vnf_pkg[0].onboardingState)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_upload_vnf_pkg_failed(self):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "empty.txt"), "rb")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
        )
        response = self.client.put("%s/222/package_content" % VNF_BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(toscaparser, 'parse_vnfd')
    @mock.patch.object(urllib.request, 'urlopen')
    def test_upload_nf_pkg_from_uri(self, mock_urlopen, mock_parse_vnfd):
        vnf_pkg = VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        mock_parse_vnfd.return_value = json.JSONEncoder().encode(vnfd_data)
        req_data = {"addressInformation": "https://127.0.0.1:1234/sdc/v1/hss.csar"}
        mock_urlopen.return_value = MockReq()
        vnf_pkg_id = vnf_pkg.vnfPackageId
        VnfPkgUploadThread(req_data, vnf_pkg_id).run()
        vnf_pkg1 = VnfPackageModel.objects.filter(vnfPackageId="222")
        self.assertEqual("00342b18-a5c7-11e8-998c-bf1755941f12", vnf_pkg1[0].vnfdId)

    def test_upload_from_uri_bad_req(self):
        req_data = {"username": "123"}
        response = self.client.post("%s/111/package_content/upload_from_uri" % VNF_BASE_URL, data=req_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch.object(urllib.request, 'urlopen')
    def test_upload_from_uri_failed(self, mock_urlopen):
        vnf_pkg = VnfPackageModel.objects.create(
            vnfPackageId="333",
            onboardingState="CREATED"
        )
        req_data = {"addressInformation": "error"}
        mock_urlopen.return_value = Exception('Boom!')
        vnf_pkg_id = vnf_pkg.vnfPackageId
        VnfPkgUploadThread(req_data, vnf_pkg_id).run()
        vnf_pkg1 = VnfPackageModel.objects.filter(vnfPackageId="333")
        self.assertEqual("CREATED", vnf_pkg1[0].onboardingState)

    def test_create_vnf_pkg(self):
        req_data = {
            "userDefinedData": {"a": "A"}
        }
        response = self.client.post(VNF_BASE_URL, data=req_data, format="json")
        resp_data = json.loads(response.content)
        expect_resp_data = {
            "id": resp_data.get("id"),
            "onboardingState": "CREATED",
            "operationalState": "DISABLED",
            "usageState": "NOT_IN_USE",
            "userDefinedData": {"a": "A"},
            "_links": None  # TODO
        }
        self.assertEqual(expect_resp_data, resp_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_query_single_vnf(self):
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            vnfdId="zte-hss-1.0",
            vnfVendor="zte",
            vnfdProductName="hss",
            vnfSoftwareVersion="1.0.0",
            vnfdVersion="1.0.0",
            checksum='{"algorithm":"111", "hash": "11"}',
            onboardingState="CREATED",
            operationalState="DISABLED",
            usageState="NOT_IN_USE",
            userDefinedData='{"a": "A"}'
        )
        response = self.client.get("%s/222" % VNF_BASE_URL)
        expect_data = {
            "id": "222",
            "vnfdId": "zte-hss-1.0",
            "vnfProductName": "hss",
            "vnfSoftwareVersion": "1.0.0",
            "vnfdVersion": "1.0.0",
            "checksum": {"algorithm": "111", "hash": "11"},
            "softwareImages": None,
            "additionalArtifacts": None,
            "onboardingState": "CREATED",
            "operationalState": "DISABLED",
            "usageState": "NOT_IN_USE",
            "userDefinedData": {"a": "A"},
            "_links": {'self': {'href': '/api/vnfpkgm/v1/vnf_packages/222'},
                       'vnfd': {
                           'href': '/api/vnfpkgm/v1/vnf_packages/222/vnfd'},
                       'packageContent': {
                           'href': '/api/vnfpkgm/v1/vnf_packages/222/package_content'}
                       }
        }
        self.assertEqual(response.data, expect_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_query_single_vnf_failed(self):
        response = self.client.get(VNF_BASE_URL + "/222")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_query_multiple_vnf(self):
        VnfPackageModel.objects.create(
            vnfPackageId="111",
            vnfdId="zte-hss-1.0",
            vnfVendor="zte",
            vnfdProductName="hss",
            vnfSoftwareVersion="1.0.0",
            vnfdVersion="1.0.0",
            checksum='{"algorithm":"111", "hash": "11"}',
            onboardingState="CREATED",
            operationalState="DISABLED",
            usageState="NOT_IN_USE",
            userDefinedData='{"a": "A"}'
        )
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            vnfdId="zte-hss-1.0",
            vnfVendor="zte",
            vnfdProductName="hss",
            vnfSoftwareVersion="1.0.0",
            vnfdVersion="1.0.0",
            checksum='{"algorithm":"111", "hash": "11"}',
            onboardingState="CREATED",
            operationalState="DISABLED",
            usageState="NOT_IN_USE",
            userDefinedData='{"a": "A"}'
        )
        response = self.client.get(VNF_BASE_URL)
        expect_data = [
            {
                "id": "111",
                "vnfdId": "zte-hss-1.0",
                "vnfProductName": "hss",
                "vnfSoftwareVersion": "1.0.0",
                "vnfdVersion": "1.0.0",
                "checksum": {"algorithm": "111", "hash": "11"},
                "softwareImages": None,
                "additionalArtifacts": None,
                "onboardingState": "CREATED",
                "operationalState": "DISABLED",
                "usageState": "NOT_IN_USE",
                "userDefinedData": {"a": "A"},
                "_links": {
                    "self": {
                        "href": "/api/vnfpkgm/v1/vnf_packages/111"
                    },
                    "vnfd": {
                        "href": "/api/vnfpkgm/v1/vnf_packages/111/vnfd"
                    },
                    "packageContent": {
                        "href": "/api/vnfpkgm/v1/vnf_packages/111/package_content"
                    }
                }
            },
            {
                "id": "222",
                "vnfdId": "zte-hss-1.0",
                "vnfProductName": "hss",
                "vnfSoftwareVersion": "1.0.0",
                "vnfdVersion": "1.0.0",
                "checksum": {"algorithm": "111", "hash": "11"},
                "softwareImages": None,
                "additionalArtifacts": None,
                "onboardingState": "CREATED",
                "operationalState": "DISABLED",
                "usageState": "NOT_IN_USE",
                "userDefinedData": {"a": "A"},
                "_links": {'self': {'href': '/api/vnfpkgm/v1/vnf_packages/222'},
                           'vnfd': {'href': '/api/vnfpkgm/v1/vnf_packages/222/vnfd'},
                           'packageContent': {
                               'href': '/api/vnfpkgm/v1/vnf_packages/222/package_content'}}
            }
        ]
        self.assertEqual(response.data, expect_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_delete_single_vnf_pkg(self):
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            vnfdId="zte-hss-1.0",
            vnfVendor="zte",
            vnfdProductName="hss",
            vnfSoftwareVersion="1.0.0",
            vnfdVersion="1.0.0",
            checksum='{"algorithm":"111", "hash": "11"}',
            onboardingState="CREATED",
            operationalState="DISABLED",
            usageState="NOT_IN_USE",
            userDefinedData='{"a": "A"}'
        )
        response = self.client.delete(VNF_BASE_URL + "/222")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.data, None)

    def test_delete_when_vnf_pkg_not_exist(self):
        response = self.client.delete(VNF_BASE_URL + "/222")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.data, None)

    def test_fetch_vnf_pkg(self):
        with open("vnfPackage.csar", "wt") as fp:
            fp.writelines("AAAABBBBCCCCDDDD")
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="ONBOARDED",
            localFilePath="vnfPackage.csar"
        )
        response = self.client.get(VNF_BASE_URL + "/222/package_content")
        file_content = ''
        for data in response.streaming_content:
            file_content = file_content + data.decode()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual('AAAABBBBCCCCDDDD', file_content)
        os.remove("vnfPackage.csar")

    def test_fetch_partical_vnf_pkg(self):
        with open("vnfPackage.csar", "wt") as fp:
            fp.writelines("AAAABBBBCCCCDDDD")
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="ONBOARDED",
            localFilePath="vnfPackage.csar"
        )
        response = self.client.get("%s/222/package_content" % VNF_BASE_URL, HTTP_RANGE="4-7")
        partial_file_content = ''
        for data in response.streaming_content:
            partial_file_content = partial_file_content + data.decode()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual('BBB', partial_file_content)
        os.remove("vnfPackage.csar")

    def test_fetch_last_partical_vnf_pkg(self):
        with open("vnfPackage.csar", "wt") as fp:
            fp.writelines("AAAABBBBCCCCDDDD")
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="ONBOARDED",
            localFilePath="vnfPackage.csar"
        )
        response = self.client.get(VNF_BASE_URL + "/222/package_content", HTTP_RANGE=" 4-")
        partial_file_content = ''
        for data in response.streaming_content:
            partial_file_content = partial_file_content + data.decode()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual('BBBBCCCCDDDD', partial_file_content)
        os.remove("vnfPackage.csar")

    def test_fetch_vnf_pkg_when_pkg_not_exist(self):
        response = self.client.get(VNF_BASE_URL + "/222/package_content")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_fetch_vnf_pkg_when_catch_cataloge_exception(self):
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED",
            localFilePath="vnfPackage.csar"
        )
        response = self.client.get(VNF_BASE_URL + "/222/package_content")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_download_vnfd(self):
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="ONBOARDED",
            localFilePath=os.path.join(CATALOG_ROOT_PATH, "resource_test.csar")
        )
        response = self.client.get(VNF_BASE_URL + "/222/vnfd")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        with open("vnfd.csar", 'wb') as local_file:
            for chunk in response.streaming_content:
                local_file.write(chunk)
        self.assertTrue(zipfile.is_zipfile("vnfd.csar"))
        os.remove("vnfd.csar")

    def test_download_vnfd_when_pkg_not_exist(self):
        response = self.client.get(VNF_BASE_URL + "/222/vnfd")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_vnfd_when_catch_cataloge_exception(self):
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED",
            localFilePath="vnfPackage.csar"
        )
        response = self.client.get(VNF_BASE_URL + "/222/vnfd")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(VnfPackage, "create_vnf_pkg")
    def test_create_vnf_pkg_when_catch_exception(self, mock_create_vnf_pkg):
        mock_create_vnf_pkg.side_effect = TypeError('integer type')
        req_data = {
            "userDefinedData": {"a": "A"}
        }
        response = self.client.post(VNF_BASE_URL, data=req_data, format="json")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(VnfPackage, "delete_vnf_pkg")
    def test_delete_single_when_catch_exception(self, mock_delete_vnf_pkg):
        mock_delete_vnf_pkg.side_effect = TypeError("integer type")
        response = self.client.delete(VNF_BASE_URL + "/222")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(VnfPackage, "query_single")
    def test_query_single_when_catch_exception(self, mock_query_single):
        mock_query_single.side_effect = TypeError("integer type")
        response = self.client.get(VNF_BASE_URL + "/222")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(VnfPackage, "query_multiple")
    def test_query_multiple_when_catch_exception(self, mock_query_muitiple):
        mock_query_muitiple.side_effect = TypeError("integer type")
        response = self.client.get(VNF_BASE_URL)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(toscaparser, 'parse_vnfd')
    def test_upload_when_catch_exception(self, mock_parse_vnfd):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "empty.txt"), "rb")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        mock_parse_vnfd.side_effect = TypeError("integer type")
        response = self.client.put(VNF_BASE_URL + "/222/package_content", data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(VnfPkgUploadThread, 'start')
    def test_upload_from_uri_when_catch_exception(self, mock_start):
        req_data = {"addressInformation": "https://127.0.0.1:1234/sdc/v1/hss.csar"}
        mock_start.side_effect = TypeError("integer type")
        response = self.client.post(VNF_BASE_URL + "/111/package_content/upload_from_uri", data=req_data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(VnfPackage, 'download')
    def test_fetch_vnf_pkg_when_catch_exception(self, mock_download):
        mock_download.side_effect = TypeError("integer type")
        response = self.client.get(VNF_BASE_URL + "/222/package_content")
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @mock.patch.object(toscaparser, 'parse_vnfd')
    def test_fetch_vnf_artifact(self, mock_parse_vnfd):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "resource_test.csar"), "rb")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        mock_parse_vnfd.return_value = json.JSONEncoder().encode(vnfd_data)
        response = self.client.put(VNF_BASE_URL + "/222/package_content", data=data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response = self.client.get(VNF_BASE_URL + "/222/artifacts/image")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.getvalue(), b"ubuntu_16.04\n")

    @mock.patch.object(toscaparser, 'parse_vnfd')
    def test_fetch_vnf_artifact_not_exists(self, mock_parse_vnfd):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "resource_test.csar"), "rb")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        mock_parse_vnfd.return_value = json.JSONEncoder().encode(vnfd_data)
        response = self.client.put(VNF_BASE_URL + "/222/package_content", data=data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response = self.client.get(VNF_BASE_URL + "/1451/artifacts/image")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @mock.patch.object(toscaparser, 'parse_vnfd')
    def test_fetch_vnf_artifact_vnf_not_exists(self, mock_parse_vnfd):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "resource_test.csar"), "rb")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        mock_parse_vnfd.return_value = json.JSONEncoder().encode(vnfd_data)
        response = self.client.put(VNF_BASE_URL + "/222/package_content", data=data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response = self.client.get(VNF_BASE_URL + "/222/artifacts/image1")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_upload_vnf_pkg_with_artifacts(self):
        data = {'file': open(os.path.join(CATALOG_ROOT_PATH, "vgw.csar"), "rb")}
        VnfPackageModel.objects.create(
            vnfPackageId="222",
            onboardingState="CREATED"
        )
        response = self.client.put("%s/222/package_content" % VNF_BASE_URL, data=data)
        vnf_pkg = VnfPackageModel.objects.filter(vnfPackageId="222")
        self.assertEqual(PKG_STATUS.ONBOARDED, vnf_pkg[0].onboardingState)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        response = self.client.get("%s/222" % VNF_BASE_URL)
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expact_response_data = {
            "id": "222",
            "vnfdId": "b1bb0ce7-2222-4fa7-95ed-4840d70a1177",
            "vnfProductName": "vcpe_vgw",
            "vnfSoftwareVersion": "1.0",
            "vnfdVersion": "1.0",
            "softwareImages": None,
            "additionalArtifacts": [
                {
                    "artifactPath": "MainServiceTemplate.yaml",
                    "checksum": {
                        "algorithm": "Null",
                        "hash": "Null"
                    }
                }
            ],
            "onboardingState": "ONBOARDED",
            "operationalState": "ENABLED",
            "usageState": "NOT_IN_USE",
            "_links": {
                "self": {
                    "href": "/api/vnfpkgm/v1/vnf_packages/222"
                },
                "vnfd": {
                    "href": "/api/vnfpkgm/v1/vnf_packages/222/vnfd"
                },
                "packageContent": {
                    "href": "/api/vnfpkgm/v1/vnf_packages/222/package_content"
                }
            }
        }
        self.assertEqual(response.data, expact_response_data)
